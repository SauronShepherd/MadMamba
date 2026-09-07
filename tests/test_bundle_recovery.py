import json
import tempfile
import unittest
from pathlib import Path

from madmamba import DiagnosticBundleIntegrityError
from madmamba.bundle_recovery import DiagnosticBundleRecovery


def _write_open_bundle(directory: Path, raw: bytes) -> None:
    (directory / "events.jsonl").write_bytes(raw)
    (directory / "madmamba-manifest.json").write_text(
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


class DiagnosticBundleRecoveryTests(unittest.TestCase):
    def test_recovers_complete_records_and_reports_partial_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tail = b'{"schemaVersion":1,"sequence":3'
            _write_open_bundle(root, _record(1) + _record(2) + tail)

            recovered = DiagnosticBundleRecovery(root).recover()

            self.assertEqual([record["sequence"] for record in recovered.records], [1, 2])
            self.assertEqual(recovered.discarded_tail_bytes, len(tail))

    def test_clean_open_bundle_reports_no_discarded_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_open_bundle(root, _record(1))

            recovered = DiagnosticBundleRecovery(root).recover()

            self.assertEqual(len(recovered.records), 1)
            self.assertEqual(recovered.discarded_tail_bytes, 0)

    def test_corrupt_complete_record_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_open_bundle(root, _record(1) + b"not-json\n")

            with self.assertRaisesRegex(DiagnosticBundleIntegrityError, "invalid complete JSONL"):
                DiagnosticBundleRecovery(root).recover()

    def test_sequence_gap_in_complete_records_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_open_bundle(root, _record(1) + _record(3))

            with self.assertRaisesRegex(DiagnosticBundleIntegrityError, "non-contiguous sequence"):
                DiagnosticBundleRecovery(root).recover()

    def test_final_bundle_must_use_strict_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_open_bundle(root, _record(1))
            manifest_path = root / "madmamba-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["state"] = "FINAL"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(
                DiagnosticBundleIntegrityError, "only accepts interrupted OPEN"
            ):
                DiagnosticBundleRecovery(root).recover()

    def test_manifest_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "bundle"
            root.mkdir()
            outside = Path(parent) / "outside.jsonl"
            outside.write_bytes(_record(1))
            (root / "madmamba-manifest.json").write_text(
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

            with self.assertRaisesRegex(
                DiagnosticBundleIntegrityError, "escapes bundle directory"
            ):
                DiagnosticBundleRecovery(root).recover()


if __name__ == "__main__":
    unittest.main()
