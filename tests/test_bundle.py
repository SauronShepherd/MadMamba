from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path

from madmamba.bundle import (
    DiagnosticBundleClosedError,
    DiagnosticBundleWriter,
    DiagnosticRecordTooLargeError,
)


class DiagnosticBundleWriterTests(unittest.TestCase):
    def test_final_manifest_matches_exact_jsonl_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                self.assertEqual(1, writer.write("runtime-start", {"interpreter": 17}))
                self.assertEqual(2, writer.write("runtime-stop", {"status": "ok"}))

            root = Path(directory)
            segment = (root / "events.jsonl").read_bytes()
            lines = segment.splitlines()
            self.assertEqual(2, len(lines))
            records = [json.loads(line) for line in lines]
            self.assertEqual([1, 2], [record["sequence"] for record in records])
            self.assertEqual(
                ["runtime-start", "runtime-stop"],
                [record["recordType"] for record in records],
            )

            manifest = json.loads((root / "madmamba-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("FINAL", manifest["state"])
            self.assertEqual(2, manifest["records"])
            self.assertEqual(len(segment), manifest["bytes"])
            self.assertEqual(2, manifest["files"][0]["records"])
            self.assertEqual(hashlib.sha256(segment).hexdigest(), manifest["files"][0]["sha256"])

    def test_failed_encoding_does_not_consume_sequence_or_append_partial_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                with self.assertRaises(ValueError):
                    writer.write("metric", {"value": float("nan")})
                self.assertEqual(1, writer.write("metric", {"value": 1.0}))
                self.assertEqual(1, writer.records_written)

            lines = (Path(directory) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(lines))
            self.assertEqual(1, json.loads(lines[0])["sequence"])

    def test_record_size_bound_is_enforced_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory, max_record_bytes=96) as writer:
                with self.assertRaises(DiagnosticRecordTooLargeError):
                    writer.write("oversized", {"value": "x" * 256})
                self.assertEqual(0, writer.records_written)
                self.assertEqual(0, writer.bytes_written)

            self.assertEqual(b"", (Path(directory) / "events.jsonl").read_bytes())

    def test_concurrent_writers_preserve_unique_contiguous_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with DiagnosticBundleWriter(directory) as writer:
                barrier = threading.Barrier(8)

                def emit(worker: int) -> None:
                    barrier.wait()
                    for value in range(50):
                        writer.write("sample", {"value": value, "worker": worker})

                threads = [threading.Thread(target=emit, args=(worker,)) for worker in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=10)
                    self.assertFalse(thread.is_alive())

                self.assertEqual(400, writer.records_written)

            lines = (Path(directory) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines]
            self.assertEqual(400, len(records))
            self.assertEqual(list(range(1, 401)), [record["sequence"] for record in records])

    def test_close_is_idempotent_and_rejects_future_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = DiagnosticBundleWriter(directory)
            writer.close()
            writer.close()
            with self.assertRaises(DiagnosticBundleClosedError):
                writer.write("late", {})


if __name__ == "__main__":
    unittest.main()
