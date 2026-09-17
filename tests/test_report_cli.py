from __future__ import annotations

import json

from madmamba import cli


def test_report_json_reuses_bounded_bundle_summary(monkeypatch, capsys):
    payload = {
        "state": "FINAL",
        "recovered": False,
        "records": 3,
        "recordTypes": {"event": 2, "lifecycle": 1},
        "discardedTailBytes": 0,
    }
    monkeypatch.setattr(cli, "inspect_bundle", lambda directory, recover_open=False: payload)

    assert cli.main(["report", "bundle", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_report_human_output_stays_aggregate(monkeypatch, capsys):
    payload = {
        "state": "OPEN",
        "recovered": True,
        "records": 2,
        "recordTypes": {"event": 2},
        "discardedTailBytes": 17,
    }
    monkeypatch.setattr(cli, "inspect_bundle", lambda directory, recover_open=False: payload)

    assert cli.main(["report", "bundle", "--recover-open"]) == 0
    output = capsys.readouterr().out
    assert "state: OPEN" in output
    assert "records: 2" in output
    assert "event: 2" in output
    assert "recovered: yes" in output
    assert "discarded tail bytes: 17" in output
