import pytest

from channel_monitor.mailer import (
    SmtpConfig,
    build_message,
    config_from_env,
    send_email,
    send_message,
)


def cfg(**kwargs):
    base = dict(host="smtp.test", sender="a@test", recipients=("b@test",))
    base.update(kwargs)
    return SmtpConfig(**base)


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("CM_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("CM_SMTP_PORT", "465")
    monkeypatch.setenv("CM_SMTP_USER", "me@example.com")
    monkeypatch.setenv("CM_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("CM_SMTP_SSL", "true")
    monkeypatch.setenv("CM_MAIL_TO", "a@example.com, b@example.com; c@example.com")

    conf = config_from_env("CM_")
    assert conf.host == "smtp.example.com" and conf.port == 465 and conf.use_ssl
    assert conf.sender == "me@example.com"
    assert conf.recipients == ("a@example.com", "b@example.com", "c@example.com")
    assert conf.configured


def test_missing_reports_gaps():
    assert SmtpConfig().missing() == ["smtp_host", "sender", "recipients"]
    assert cfg(username="u").missing() == ["password"]
    assert cfg().missing() == []


def test_build_message_has_both_parts_and_attachment(tmp_path):
    attachment = tmp_path / "hits.csv"
    attachment.write_text("code,score\nTXG,80\n", encoding="utf-8")

    msg = build_message(cfg(), "subject", "<p>hello &amp; bye</p>", attachments=[attachment])
    assert msg["Subject"] == "subject" and msg["To"] == "b@test"
    types = {part.get_content_type() for part in msg.walk()}
    assert {"text/plain", "text/html", "text/csv"} <= types
    assert "hello" in msg.get_body(preferencelist=("plain",)).get_content()


def test_build_message_skips_missing_attachment(tmp_path):
    msg = build_message(cfg(), "s", "<p>x</p>", attachments=[tmp_path / "nope.png"])
    assert "application/octet-stream" not in {p.get_content_type() for p in msg.walk()}


def test_send_email_uses_transport():
    seen = {}
    ok = send_email(cfg(), "s", "<p>x</p>", transport=lambda c, m: seen.update(msg=m))
    assert ok and seen["msg"]["Subject"] == "s"


def test_send_email_refuses_incomplete_config():
    calls = []
    assert send_email(SmtpConfig(), "s", "<p>x</p>", transport=lambda c, m: calls.append(m)) is False
    assert not calls


def test_send_email_swallows_transport_errors():
    def boom(c, m):
        raise OSError("smtp down")

    assert send_email(cfg(), "s", "<p>x</p>", transport=boom) is False


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append("send")


@pytest.mark.parametrize("use_ssl", [False, True])
def test_send_message_transport(monkeypatch, use_ssl):
    _FakeSMTP.instances = []
    monkeypatch.setattr("channel_monitor.mailer.smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr("channel_monitor.mailer.smtplib.SMTP_SSL", _FakeSMTP)

    conf = cfg(username="u", password="p", use_ssl=use_ssl, port=465 if use_ssl else 587)
    send_message(conf, build_message(conf, "s", "<p>x</p>"))

    smtp = _FakeSMTP.instances[0]
    assert smtp.port == conf.port
    assert ("login", "u", "p") in smtp.calls and "send" in smtp.calls
    assert ("starttls" in smtp.calls) is (not use_ssl)
