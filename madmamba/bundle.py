from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from .sanitizer import sanitize_diagnostic_payload


class DiagnosticBundleClosedError(RuntimeError):
    """Raised when a record is written after the bundle is closed."""


class DiagnosticRecordTooLargeError(ValueError):
    """Raised when one encoded JSONL record exceeds the configured bound."""


class DiagnosticBundleWriter:
    """Write a bounded, checksummed, multi-segment diagnostic JSONL bundle."""

    MANIFEST_NAME = "madmamba-manifest.json"
    SEGMENT_NAME = "events.jsonl"
    DEFAULT_MAX_RECORD_BYTES = 1_048_576
    DEFAULT_MAX_SEGMENT_BYTES = 10 * 1024 * 1024

    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
        max_segment_bytes: int = DEFAULT_MAX_SEGMENT_BYTES,
    ) -> None:
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive")
        if max_segment_bytes < max_record_bytes:
            raise ValueError("max_segment_bytes must be at least max_record_bytes")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_record_bytes = max_record_bytes
        self.max_segment_bytes = max_segment_bytes
        self.manifest_path = self.directory / self.MANIFEST_NAME
        self._lock = threading.Lock()
        self._sequence = 0
        self._bytes = 0
        self._records = 0
        self._closed = False
        self._segment_index = 1
        self._segment_path = self.directory / self._segment_name(self._segment_index)
        self._segment: BinaryIO = self._segment_path.open("xb")
        self._segment_bytes = 0
        self._segment_records = 0
        self._segment_sha256 = hashlib.sha256()
        self._completed_segments: list[dict[str, object]] = []
        self._write_manifest(state="OPEN")

    @staticmethod
    def _segment_name(index: int) -> str:
        return DiagnosticBundleWriter.SEGMENT_NAME if index == 1 else f"events-{index:06d}.jsonl"

    @property
    def segment_path(self) -> Path:
        return self._segment_path

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
        normalized_type = record_type.strip()
        if not normalized_type:
            raise ValueError("record_type must not be empty")
        sanitized_payload = sanitize_diagnostic_payload(payload)
        with self._lock:
            if self._closed:
                raise DiagnosticBundleClosedError("diagnostic bundle is closed")
            sequence = self._sequence + 1
            record = {
                "payload": sanitized_payload,
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
                    f"encoded diagnostic record is {len(encoded)} bytes; limit is {self.max_record_bytes}"
                )
            if self._segment_records and self._segment_bytes + len(encoded) > self.max_segment_bytes:
                self._rotate_segment()
            try:
                self._segment.write(encoded)
                self._segment.flush()
            except OSError:
                self._poison_after_write_error()
                raise
            self._segment_sha256.update(encoded)
            self._segment_records += 1
            self._segment_bytes += len(encoded)
            self._sequence = sequence
            self._records += 1
            self._bytes += len(encoded)
            try:
                self._write_manifest(state="OPEN")
            except OSError:
                self._poison_after_write_error()
                raise
            return sequence

    def _rotate_segment(self) -> None:
        self._segment.flush()
        os.fsync(self._segment.fileno())
        self._segment.close()
        self._completed_segments.append(self._current_segment_entry(finalized=True))
        self._segment_index += 1
        self._segment_path = self.directory / self._segment_name(self._segment_index)
        self._segment = self._segment_path.open("xb")
        self._segment_bytes = 0
        self._segment_records = 0
        self._segment_sha256 = hashlib.sha256()
        self._write_manifest(state="OPEN")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._segment.flush()
            os.fsync(self._segment.fileno())
            self._segment.close()
            self._closed = True
            self._write_manifest(state="FINAL")

    def _poison_after_write_error(self) -> None:
        self._closed = True
        try:
            self._segment.close()
        except OSError:
            pass
        try:
            self._write_manifest(state="FAILED")
        except OSError:
            pass

    def _current_segment_entry(self, *, finalized: bool) -> dict[str, object]:
        entry: dict[str, object] = {
            "bytes": self._segment_bytes,
            "path": self._segment_name(self._segment_index),
            "records": self._segment_records,
        }
        if finalized:
            entry["sha256"] = self._segment_sha256.hexdigest()
        return entry

    def _manifest(self, *, state: str) -> dict[str, object]:
        files = [dict(entry) for entry in self._completed_segments]
        current = self._current_segment_entry(finalized=state == "FINAL")
        if current["records"] or not files:
            files.append(current)
        return {
            "bytes": self._bytes,
            "files": files,
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
        if os.name == "nt":
            return
        descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)