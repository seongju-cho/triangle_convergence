import json

import pytest

from channel_monitor.settings import (
    DailySettings,
    from_dict,
    load_settings,
    write_example_config,
)


def test_defaults_are_usable():
    settings = DailySettings()
    assert settings.markets == ["nasdaq", "kospi"]
    assert settings.lookbacks == [90, 120, 150]
    assert settings.email.enabled


def test_load_settings_merges_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "markets": ["kospi"],
                "min_score": 70,
                "unknown_key": 1,
                "email": {"recipients": ["me@test"], "sender": "me@test", "bogus": True},
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.markets == ["kospi"] and settings.min_score == 70
    assert settings.lookbacks == [90, 120, 150]  # untouched default
    assert settings.email.recipients == ["me@test"]


def test_email_password_comes_from_env(monkeypatch):
    monkeypatch.setenv("MY_SMTP_PW", "app-password")
    settings = from_dict(
        {"email": {"password_env": "MY_SMTP_PW", "sender": "a@b", "recipients": ["a@b"],
                   "smtp_host": "smtp.test"}}
    )
    smtp = settings.email.smtp()
    assert smtp.password == "app-password" and smtp.configured


def test_email_sender_falls_back_to_username():
    settings = from_dict({"email": {"username": "me@test", "recipients": ["me@test"]}})
    assert settings.email.smtp().sender == "me@test"


def test_missing_file_is_reported():
    with pytest.raises(FileNotFoundError):
        load_settings("does-not-exist.json")


def test_non_object_json_is_rejected(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_bad_email_section_is_rejected():
    with pytest.raises(ValueError):
        from_dict({"email": "yes"})


def test_example_config_roundtrips(tmp_path):
    path = write_example_config(tmp_path / "monitor.config.json")
    settings = load_settings(path)
    assert settings.email.password_env == "CHANNEL_MONITOR_SMTP_PASSWORD"
    assert settings.markets == ["nasdaq", "kospi"]


def test_load_settings_without_path_returns_defaults():
    assert load_settings(None).markets == DailySettings().markets
