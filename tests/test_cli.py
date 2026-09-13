import json
from datetime import date

import pytest

from channel_monitor import synthetic
from channel_monitor.cli import main, parse_lookbacks


def prepare(tmp_path):
    synthetic.ascending_channel(n=200, start="2025-11-03").to_csv(tmp_path / "HIT.csv")
    synthetic.ascending_channel(n=200, start="2025-11-03", breakout_bars=0).to_csv(tmp_path / "MISS.csv")
    return [
        "--markets", "nasdaq",
        "--symbols", "HIT,MISS",
        "--csv-dir", str(tmp_path),
        "--cache-dir", str(tmp_path / "cache"),
    ]


def test_parse_lookbacks():
    assert parse_lookbacks("90, 120,150") == [90, 120, 150]
    assert parse_lookbacks("") == [90, 120, 150]


def test_selftest_command_passes(capsys):
    assert main(["selftest"]) == 0
    assert "FAIL" not in capsys.readouterr().out


def test_scan_command_writes_outputs(tmp_path, capsys):
    args = ["scan"] + prepare(tmp_path) + [
        "--csv", str(tmp_path / "hits.csv"),
        "--json", str(tmp_path / "hits.json"),
    ]
    assert main(args) == 0
    assert "HIT" in capsys.readouterr().out
    payload = json.loads((tmp_path / "hits.json").read_text(encoding="utf-8"))
    assert len(payload["hits"]) == 1


def test_explain_command_exit_codes(tmp_path, capsys):
    base = prepare(tmp_path)[2:]  # drop --markets nasdaq
    assert main(["explain", "HIT", "--market", "nasdaq"] + base[2:]) == 0
    assert main(["explain", "MISS", "--market", "nasdaq"] + base[2:]) == 1
    out = capsys.readouterr().out
    assert "ok=True" in out and "ok=False" in out


def test_watch_once_records_alert_state(tmp_path, capsys):
    args = ["watch"] + prepare(tmp_path) + ["--once", "--state-file", str(tmp_path / "alerts.json")]
    assert main(args) == 0
    state = json.loads((tmp_path / "alerts.json").read_text(encoding="utf-8"))
    assert any("HIT" in key for key in state["seen"])

    assert main(args) == 0
    assert "new 0" in capsys.readouterr().out


def test_universe_command(capsys):
    assert main(["universe", "nasdaq", "--offline", "--limit", "3"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 3


def daily_config(tmp_path, **email_overrides):
    import json

    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    synthetic.ascending_channel(n=200, start="2025-11-03").to_csv(csv_dir / "HIT.csv")
    synthetic.ascending_channel(n=200, start="2025-11-03", breakout_bars=0).to_csv(csv_dir / "MISS.csv")

    email = {
        "enabled": True,
        "smtp_host": "smtp.test",
        "username": "me@test",
        "password": "pw",
        "sender": "me@test",
        "recipients": ["me@test"],
        "attach_charts": False,
    }
    email.update(email_overrides)
    config = {
        "markets": ["nasdaq"],
        "symbols": ["HIT", "MISS"],
        "lookbacks": [120, 150],
        "csv_dir": str(csv_dir),
        "out_dir": str(tmp_path / "out"),
        "state_file": str(tmp_path / "alerts.json"),
        "log_file": str(tmp_path / "daily.log"),
        "plot": False,
        "email": email,
    }
    path = tmp_path / "monitor.config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_daily_emails_new_breakouts(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("channel_monitor.cli.send_message", lambda cfg, msg: sent.append(msg))
    config = daily_config(tmp_path)

    assert main(["daily", "--config", str(config)]) == 0
    assert len(sent) == 1
    assert "HIT" in sent[0].get_body(preferencelist=("html",)).get_content()
    attached = {part.get_filename() for part in sent[0].walk() if part.get_filename()}
    assert f"hits-{date.today().isoformat()}.csv" in attached
    assert (tmp_path / "alerts.json").exists()
    assert list((tmp_path / "out").glob("report-*.html"))

    # a second run sees nothing new, so no second email
    assert main(["daily", "--config", str(config)]) == 0
    assert len(sent) == 1


def test_daily_dry_run_sends_nothing(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("channel_monitor.cli.send_message", lambda cfg, msg: sent.append(msg))
    config = daily_config(tmp_path)

    assert main(["daily", "--config", str(config), "--dry-run"]) == 0
    assert not sent
    assert not (tmp_path / "alerts.json").exists()


def test_daily_no_email_flag(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("channel_monitor.cli.send_message", lambda cfg, msg: sent.append(msg))
    config = daily_config(tmp_path)

    assert main(["daily", "--config", str(config), "--no-email"]) == 0
    assert not sent
    assert (tmp_path / "alerts.json").exists()


def test_daily_reports_delivery_failure(tmp_path, monkeypatch):
    def boom(cfg, msg):
        raise OSError("smtp refused")

    monkeypatch.setattr("channel_monitor.cli.send_message", boom)
    config = daily_config(tmp_path)
    assert main(["daily", "--config", str(config)]) == 2


def test_daily_send_when_empty(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("channel_monitor.cli.send_message", lambda cfg, msg: sent.append(msg))
    config = daily_config(tmp_path, send_when_empty=True)

    assert main(["daily", "--config", str(config)]) == 0
    assert main(["daily", "--config", str(config)]) == 0
    assert len(sent) == 2
    assert "No new breakouts" in sent[1].get_body(preferencelist=("html",)).get_content()


def test_daily_missing_config_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        main(["daily", "--config", str(tmp_path / "nope.json")])


def test_init_config_writes_loadable_file(tmp_path, capsys):
    target = tmp_path / "monitor.config.json"
    assert main(["init-config", str(target)]) == 0
    assert target.exists() and "wrote" in capsys.readouterr().out


def test_scan_sample_is_deterministic(tmp_path, capsys):
    args = ["scan"] + prepare(tmp_path) + ["--sample", "1", "--sample-seed", "3"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == first
