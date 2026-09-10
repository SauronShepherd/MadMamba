from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from madmamba.bundle import DiagnosticBundleWriter
from madmamba.bundle_reader import DiagnosticBundleIntegrityError, DiagnosticBundleReader


class DiagnosticBundleReaderTests(unittest.TestCase):
    def test_reads_valid_finalized_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                writer.write("runtime-start", {"interpreter": 17})
                writer.write("runtime-stop", {"status": "ok"})

            records = DiagnosticBundleReader(directory).read_records()
            self.assertEqual([1, 2], [record["sequence"] for record in records])
            self.assertEqual(
                ["runtime-start", "runtime-stop"],
                [record["recordType"] for record in records],
            )

    def test_reads_rotated_segments_as_one_contiguous_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(
                directory,
                max_record_bytes=256,
                max_segment_bytes=256,
            ) as writer:
                for index in range(8):
                    writer.write("sample", {"index": index, "value": "x" * 80})

            root = Path(directory)
            manifest = json.loads((root / "madmamba-manifest.json").read_text(encoding="utf-8"))
            self.assertGreater(len(manifest["files"]), 1)
            records = DiagnosticBundleReader(directory).read_records()
            self.assertEqual(list(range(1, 9)), [record["sequence"] for record in records])
            self.assertEqual(list(range(8)), [record["payload"]["index"] for record in records])

            second_segment = root / manifest["files"][1]["path"]
            second_segment.write_bytes(second_segment.read_bytes().replace(b'"index":1', b'"index":9'))
            with self.assertRaisesRegex(DiagnosticBundleIntegrityError, "SHA-256 mismatch"):
                DiagnosticBundleReader(directory).read_records()

    def test_rejects_open_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = DiagnosticBundleWriter(directory)
            try:
                with self.assertRaisesRegex(DiagnosticBundleIntegrityError, "not finalized"):
                    DiagnosticBundleReader(directory).read_records()
            finally:
                writer.close()

    def test_rejects_tampered_segment_before_returning_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                writer.write("sample", {"value": 1})
            segment = Path(directory) / "events.jsonl"
            segment.write_bytes(segment.read_bytes().replace(b'"value":1', b'"value":2'))

            with self.assertRaisesRegex(DiagnosticBundleIntegrityError, "SHA-256 mismatch"):
                DiagnosticBundleReader(directory).read_records()

    def test_rejects_noncontiguous_sequence_even_with_updated_integrity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                writer.write("sample", {"value": 1})
                writer.write("sample", {"value": 2})

            root = Path(directory)
            segment_path = root / "events.jsonl"
            records = [json.loads(line) for line in segment_path.read_bytes().splitlines()]
            records[1]["sequence"] = 3
            raw = b"".join(
                json.dumps(record, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
                for record in records
            )
            segment_path.write_bytes(raw)

            manifest_path = root / "madmamba-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["bytes"] = len(raw)
            manifest["files"][0]["bytes"] = len(raw)
            manifest["files"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(DiagnosticBundleIntegrityError, "non-contiguous"):
                DiagnosticBundleReader(directory).read_records()

    def test_rejects_manifest_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                writer.write("sample", {"value": 1})
            manifest_path = Path(directory) / "madmamba-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["path"] = "../outside.jsonl"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(DiagnosticBundleIntegrityError):
                DiagnosticBundleReader(directory).read_records()


if __name__ == "__main__":
    unittest.main()
