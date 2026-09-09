from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from madmamba.bundle import (
    DiagnosticBundleClosedError,
    DiagnosticBundleWriter,
    DiagnosticRecordTooLargeError,
)


class _PartialWriteFailure:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write(self, data: bytes) -> int:
        midpoint = max(1, len(data) // 2)
        self._stream.write(data[:midpoint])  # type: ignore[attr-defined]
        self._stream.flush()  # type: ignore[attr-defined]
        raise OSError("simulated partial write")

    def flush(self) -> None:
        self._stream.flush()  # type: ignore[attr-defined]

    def fileno(self) -> int:
        return self._stream.fileno()  # type: ignore[attr-defined,no-any-return]

    def close(self) -> None:
        self._stream.close()  # type: ignore[attr-defined]


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

    def test_open_manifest_tracks_committed_record_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = DiagnosticBundleWriter(directory)
            root = Path(directory)
            initial = json.loads((root / "madmamba-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("OPEN", initial["state"])
            self.assertEqual(0, initial["records"])
            self.assertEqual(0, initial["bytes"])

            writer.write("metric", {"value": 1})
            segment = (root / "events.jsonl").read_bytes()
            progress = json.loads((root / "madmamba-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("OPEN", progress["state"])
            self.assertEqual(1, progress["records"])
            self.assertEqual(len(segment), progress["bytes"])
            self.assertEqual(1, progress["files"][0]["records"])
            self.assertNotIn("sha256", progress["files"][0])
            writer.close()

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

    @unittest.skipIf(os.name == "nt", "directory fsync is POSIX-only")
    def test_manifest_replace_fsyncs_directory_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = DiagnosticBundleWriter(directory)
            with (
                mock.patch("madmamba.bundle.os.open", return_value=123) as open_mock,
                mock.patch("madmamba.bundle.os.fsync") as fsync_mock,
                mock.patch("madmamba.bundle.os.close") as close_mock,
            ):
                writer.close()

            open_mock.assert_called_once_with(writer.directory, os.O_RDONLY)
            fsync_mock.assert_any_call(123)
            close_mock.assert_called_once_with(123)

    def test_partial_write_oserror_poison_bundle_and_rejects_future_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = DiagnosticBundleWriter(directory)
            writer._segment = _PartialWriteFailure(writer._segment)  # type: ignore[assignment]

            with self.assertRaisesRegex(OSError, "simulated partial write"):
                writer.write("metric", {"value": 1})

            self.assertEqual(0, writer.records_written)
            self.assertEqual(0, writer.bytes_written)
            with self.assertRaises(DiagnosticBundleClosedError):
                writer.write("late", {})

            root = Path(directory)
            manifest = json.loads((root / "madmamba-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("FAILED", manifest["state"])
            self.assertEqual(0, manifest["records"])
            self.assertEqual(0, manifest["bytes"])
            self.assertNotIn("sha256", manifest["files"][0])
            self.assertNotEqual(b"", (root / "events.jsonl").read_bytes())

    def test_open_manifest_write_failure_poison_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            writer = DiagnosticBundleWriter(directory)
            original = writer._write_manifest
            calls = 0

            def fail_first_progress(*, state: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 1 and state == "OPEN":
                    raise OSError("simulated manifest progress failure")
                original(state=state)

            writer._write_manifest = fail_first_progress  # type: ignore[method-assign]
            with self.assertRaisesRegex(OSError, "simulated manifest progress failure"):
                writer.write("metric", {"value": 1})
            with self.assertRaises(DiagnosticBundleClosedError):
                writer.write("late", {})

            manifest = json.loads(
                (Path(directory) / "madmamba-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("FAILED", manifest["state"])
            self.assertEqual(1, manifest["records"])
            self.assertGreater(manifest["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
