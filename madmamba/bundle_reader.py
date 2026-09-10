from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class DiagnosticBundleIntegrityError(ValueError):
    """Raised when a diagnostic bundle fails structural or integrity validation."""


class DiagnosticBundleReader:
    """Load and validate a finalized MadMamba diagnostic bundle.

    Validation is fail-closed: records are returned only after manifest metadata,
    every segment size and SHA-256, per-segment record counts, schema versions,
    global sequence continuity, and aggregate totals have all been verified.
    """

    MANIFEST_NAME = "madmamba-manifest.json"
    FORMAT = "madmamba-diagnostic-bundle"
    MANIFEST_VERSION = 1
    RECORD_SCHEMA_VERSION = 1

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.manifest_path = self.directory / self.MANIFEST_NAME

    def read_records(self) -> list[dict[str, Any]]:
        manifest = self._read_manifest()
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise DiagnosticBundleIntegrityError("manifest must describe at least one segment")

        records: list[dict[str, Any]] = []
        expected_sequence = 1
        total_bytes = 0
        total_records = 0
        seen_paths: set[str] = set()

        for segment_number, entry in enumerate(files, start=1):
            if not isinstance(entry, dict):
                raise DiagnosticBundleIntegrityError("manifest file entry must be an object")

            relative_path = entry.get("path")
            if not isinstance(relative_path, str) or not relative_path:
                raise DiagnosticBundleIntegrityError("manifest file path must be a non-empty string")
            if relative_path in seen_paths:
                raise DiagnosticBundleIntegrityError("manifest contains a duplicate segment path")
            seen_paths.add(relative_path)
            segment_path = self._safe_child(relative_path)

            expected_bytes = self._nonnegative_int(entry.get("bytes"), "file bytes")
            expected_records = self._nonnegative_int(entry.get("records"), "file records")
            expected_sha = entry.get("sha256")
            if (
                not isinstance(expected_sha, str)
                or len(expected_sha) != 64
                or any(character not in "0123456789abcdef" for character in expected_sha)
            ):
                raise DiagnosticBundleIntegrityError("final manifest requires a SHA-256 digest")

            raw = segment_path.read_bytes()
            if len(raw) != expected_bytes:
                raise DiagnosticBundleIntegrityError(
                    f"segment byte count mismatch: expected {expected_bytes}, got {len(raw)}"
                )
            if hashlib.sha256(raw).hexdigest() != expected_sha:
                raise DiagnosticBundleIntegrityError("segment SHA-256 mismatch")
            if raw and not raw.endswith(b"\n"):
                raise DiagnosticBundleIntegrityError("segment ends with an incomplete JSONL record")

            segment_records = 0
            for line_number, line in enumerate(raw.splitlines(), start=1):
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise DiagnosticBundleIntegrityError(
                        f"invalid JSONL record in segment {segment_number} at line {line_number}"
                    ) from exc
                if not isinstance(value, dict):
                    raise DiagnosticBundleIntegrityError(
                        f"record {line_number} in segment {segment_number} must be an object"
                    )
                if value.get("schemaVersion") != self.RECORD_SCHEMA_VERSION:
                    raise DiagnosticBundleIntegrityError(
                        f"record {line_number} in segment {segment_number} has unsupported schemaVersion"
                    )
                if value.get("sequence") != expected_sequence:
                    raise DiagnosticBundleIntegrityError(
                        f"record {line_number} in segment {segment_number} has non-contiguous sequence"
                    )
                record_type = value.get("recordType")
                if not isinstance(record_type, str) or not record_type.strip():
                    raise DiagnosticBundleIntegrityError(
                        f"record {line_number} in segment {segment_number} has invalid recordType"
                    )
                if not isinstance(value.get("payload"), dict):
                    raise DiagnosticBundleIntegrityError(
                        f"record {line_number} in segment {segment_number} has invalid payload"
                    )
                records.append(value)
                segment_records += 1
                expected_sequence += 1

            if segment_records != expected_records:
                raise DiagnosticBundleIntegrityError(
                    f"segment record count mismatch: expected {expected_records}, got {segment_records}"
                )
            total_bytes += expected_bytes
            total_records += expected_records

        if manifest.get("bytes") != total_bytes or manifest.get("records") != total_records:
            raise DiagnosticBundleIntegrityError("manifest totals do not match segment metadata")
        return records

    def _read_manifest(self) -> dict[str, Any]:
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DiagnosticBundleIntegrityError("manifest is missing or invalid JSON") from exc
        if not isinstance(manifest, dict):
            raise DiagnosticBundleIntegrityError("manifest must be an object")
        if manifest.get("format") != self.FORMAT:
            raise DiagnosticBundleIntegrityError("unsupported diagnostic bundle format")
        if manifest.get("manifestVersion") != self.MANIFEST_VERSION:
            raise DiagnosticBundleIntegrityError("unsupported manifest version")
        if manifest.get("state") != "FINAL":
            raise DiagnosticBundleIntegrityError("diagnostic bundle is not finalized")
        return manifest

    def _safe_child(self, relative_path: str) -> Path:
        candidate = (self.directory / relative_path).resolve()
        root = self.directory.resolve()
        if candidate.parent != root:
            raise DiagnosticBundleIntegrityError("manifest segment path escapes bundle directory")
        if not candidate.is_file():
            raise DiagnosticBundleIntegrityError("manifest segment file is missing")
        return candidate

    @staticmethod
    def _nonnegative_int(value: object, label: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DiagnosticBundleIntegrityError(f"manifest {label} must be a non-negative integer")
        return value
