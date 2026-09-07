import json

import pytest

from madmamba import DiagnosticBundleIntegrityError
from madmamba.bundle_recovery import DiagnosticBundleRecovery


def _write_open_bundle(tmp_path, raw: bytes) -> None:
    (tmp_path / "events.jsonl").write_bytes(raw)
    (tmp_path / "madmamba-manifest.json").write_text(
        json.dumps(
            {
                "format": "madmamba-diagnostic-bundle",
                "manifestVersion": 1,
                "state": "OPEN",
                "files": [{"path": "events.jsonl"}],
            }
        ),
        encoding="utf-8",
    )


def _record(sequence: int, payload: dict[str, object] | None = None) -> bytes:
    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "sequence": sequence,
                "recordType": "runtime.event",
                "payload": payload or {"sequence": sequence},
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def test_recovers_complete_records_and_reports_partial_tail(tmp_path):
    tail = b'{"schemaVersion":1,"sequence":3'
    _write_open_bundle(tmp_path, _record(1) + _record(2) + tail)

    recovered = DiagnosticBundleRecovery(tmp_path).recover()

    assert [record["sequence"] for record in recovered.records] == [1, 2]
    assert recovered.discarded_tail_bytes == len(tail)


def test_clean_open_bundle_reports_no_discarded_tail(tmp_path):
    _write_open_bundle(tmp_path, _record(1))

    recovered = DiagnosticBundleRecovery(tmp_path).recover()

    assert len(recovered.records) == 1
    assert recovered.discarded_tail_bytes == 0


def test_corrupt_complete_record_fails_closed(tmp_path):
    _write_open_bundle(tmp_path, _record(1) + b"not-json\n")

    with pytest.raises(DiagnosticBundleIntegrityError, match="invalid complete JSONL"):
        DiagnosticBundleRecovery(tmp_path).recover()


def test_sequence_gap_in_complete_records_fails_closed(tmp_path):
    _write_open_bundle(tmp_path, _record(1) + _record(3))

    with pytest.raises(DiagnosticBundleIntegrityError, match="non-contiguous sequence"):
        DiagnosticBundleRecovery(tmp_path).recover()


def test_final_bundle_must_use_strict_reader(tmp_path):
    _write_open_bundle(tmp_path, _record(1))
    manifest_path = tmp_path / "madmamba-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["state"] = "FINAL"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DiagnosticBundleIntegrityError, match="only accepts interrupted OPEN"):
        DiagnosticBundleRecovery(tmp_path).recover()


def test_manifest_path_escape_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside.jsonl"
    outside.write_bytes(_record(1))
    (tmp_path / "madmamba-manifest.json").write_text(
        json.dumps(
            {
                "format": "madmamba-diagnostic-bundle",
                "manifestVersion": 1,
                "state": "OPEN",
                "files": [{"path": "../outside.jsonl"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiagnosticBundleIntegrityError, match="escapes bundle directory"):
        DiagnosticBundleRecovery(tmp_path).recover()
