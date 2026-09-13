import json

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
