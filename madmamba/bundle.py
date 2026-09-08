from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class DiagnosticBundleClosedError(RuntimeError):
    """Raised when a record is written after the bundle is closed."""


class DiagnosticRecordTooLargeError(ValueError):
    """Raised when one encoded JSONL record exceeds the configured bound."""


class DiagnosticBundleWriter:
    """Write a bounded, checksummed diagnostic JSONL bundle.

    The writer owns one append-only segment and a small manifest. Record writes are
    serialized so sequence assignment and byte accounting remain correct under
    free-threaded interpreters. Each successful record is flushed as one complete
    UTF-8 JSON line; close additionally fsyncs the segment before atomically
    replacing the manifest with its FINAL form.
    """

    MANIFEST_NAME = "madmamba-manifest.json"
    SEGMENT_NAME = "events.jsonl"
    DEFAULT_MAX_RECORD_BYTES = 1_048_576

    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
    ) -> None:
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_record_bytes = max_record_bytes
        self.segment_path = self.directory / self.SEGMENT_NAME
        self.manifest_path = self.directory / self.MANIFEST_NAME
        self._lock = threading.Lock()
        self._sequence = 0
        self._bytes = 0
        self._records = 0
        self._sha256 = hashlib.sha256()
        self._closed = False
        self._segment = self.segment_path.open("xb")
        self._write_manifest(state="OPEN")

    def __enter__(self) -> DiagnosticBundleWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def records_written(self) -> int:
        with self._lock:
            return self._records

    @property
    def bytes_written(self) -> int:
        with self._lock:
            return self._bytes

    def write(self, record_type: str, payload: Mapping[str, Any]) -> int:
        """Append one typed record and return its monotonically increasing sequence."""

        normalized_type = record_type.strip()
        if not normalized_type:
            raise ValueError("record_type must not be empty")
        with self._lock:
            if self._closed:
                raise DiagnosticBundleClosedError("diagnostic bundle is closed")
            sequence = self._sequence + 1
            record = {
                "payload": dict(payload),
                "recordType": normalized_type,
                "schemaVersion": 1,
                "sequence": sequence,
            }
            encoded = (
                json.dumps(
                    record,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n"
            )
            if len(encoded) > self.max_record_bytes:
                raise DiagnosticRecordTooLargeError(
                    f"encoded diagnostic record is {len(encoded)} bytes; "
                    f"limit is {self.max_record_bytes}"
                )
            try:
                self._segment.write(encoded)
                self._segment.flush()
            except OSError:
                self._poison_after_write_error()
                raise
            self._sha256.update(encoded)
            self._sequence = sequence
            self._records += 1
            self._bytes += len(encoded)
            return sequence

    def close(self) -> None:
        """Durably close the segment and atomically publish a FINAL manifest."""

        with self._lock:
            if self._closed:
                return
            self._segment.flush()
            os.fsync(self._segment.fileno())
            self._segment.close()
            self._closed = True
            self._write_manifest(state="FINAL")

    def _poison_after_write_error(self) -> None:
        """Best-effort publish FAILED state after an I/O error during a record write.

        A short/partial write can leave bytes in the segment that are absent from
        the in-memory checksum and counters. The bundle must therefore never
        accept another record or publish a FINAL manifest after such a failure.
        """

        self._closed = True
        try:
            self._segment.close()
        except OSError:
            pass
        try:
            self._write_manifest(state="FAILED")
        except OSError:
            # Preserve the original record-write error. The missing/OPEN manifest
            # still prevents the bundle from being mistaken for a valid FINAL one.
            pass

    def _manifest(self, *, state: str) -> dict[str, object]:
        file_entry: dict[str, object] = {
            "bytes": self._bytes,
            "path": self.SEGMENT_NAME,
            "records": self._records,
        }
        if state == "FINAL":
            file_entry["sha256"] = self._sha256.hexdigest()
        return {
            "bytes": self._bytes,
            "files": [file_entry],
            "format": "madmamba-diagnostic-bundle",
            "manifestVersion": 1,
            "records": self._records,
            "state": state,
        }

    def _write_manifest(self, *, state: str) -> None:
        payload = json.dumps(
            self._manifest(state=state),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.manifest_path)
        self._fsync_directory()

    def _fsync_directory(self) -> None:
        """Persist the manifest directory entry after atomic replacement on POSIX."""

        if os.name == "nt":
            return
        descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
