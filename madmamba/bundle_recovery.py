from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle_reader import DiagnosticBundleIntegrityError


@dataclass(frozen=True)
class RecoveredDiagnosticBundle:
    """Best-effort recovery result for an interrupted diagnostic bundle."""

    records: tuple[dict[str, Any], ...]
    discarded_tail_bytes: int


class DiagnosticBundleRecovery:
    """Recover only complete, structurally valid records from an OPEN bundle.

    Recovery is intentionally narrower than normal reading: FINAL bundles must be
    consumed with ``DiagnosticBundleReader`` so their checksums and totals remain
    authoritative. For an interrupted OPEN bundle, only complete newline-terminated
    JSONL records with contiguous sequence numbers are returned. A final partial
    line may be discarded, but corruption in any complete record fails closed.
    """

    MANIFEST_NAME = "madmamba-manifest.json"
    FORMAT = "madmamba-diagnostic-bundle"
    MANIFEST_VERSION = 1
    RECORD_SCHEMA_VERSION = 1

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.manifest_path = self.directory / self.MANIFEST_NAME

    def recover(self) -> RecoveredDiagnosticBundle:
        manifest = self._read_open_manifest()
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != 1:
            raise DiagnosticBundleIntegrityError("manifest must describe exactly one segment")
        entry = files[0]
        if not isinstance(entry, dict):
            raise DiagnosticBundleIntegrityError("manifest file entry must be an object")
        relative_path = entry.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            raise DiagnosticBundleIntegrityError("manifest file path must be a non-empty string")

        raw = self._safe_child(relative_path).read_bytes()
        complete_end = raw.rfind(b"\n") + 1
        complete = raw[:complete_end]
        discarded_tail_bytes = len(raw) - complete_end

        records: list[dict[str, Any]] = []
        expected_sequence = 1
        for line_number, line in enumerate(complete.splitlines(), start=1):
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise DiagnosticBundleIntegrityError(
                    f"invalid complete JSONL record at line {line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise DiagnosticBundleIntegrityError(f"record {line_number} must be an object")
            if value.get("schemaVersion") != self.RECORD_SCHEMA_VERSION:
                raise DiagnosticBundleIntegrityError(
                    f"record {line_number} has unsupported schemaVersion"
                )
            if value.get("sequence") != expected_sequence:
                raise DiagnosticBundleIntegrityError(
                    f"record {line_number} has non-contiguous sequence"
                )
            record_type = value.get("recordType")
            if not isinstance(record_type, str) or not record_type.strip():
                raise DiagnosticBundleIntegrityError(
                    f"record {line_number} has invalid recordType"
                )
            if not isinstance(value.get("payload"), dict):
                raise DiagnosticBundleIntegrityError(f"record {line_number} has invalid payload")
            records.append(value)
            expected_sequence += 1

        return RecoveredDiagnosticBundle(tuple(records), discarded_tail_bytes)

    def _read_open_manifest(self) -> dict[str, Any]:
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
        if manifest.get("state") != "OPEN":
            raise DiagnosticBundleIntegrityError(
                "recovery only accepts interrupted OPEN diagnostic bundles"
            )
        return manifest

    def _safe_child(self, relative_path: str) -> Path:
        candidate = (self.directory / relative_path).resolve()
        root = self.directory.resolve()
        if candidate.parent != root:
            raise DiagnosticBundleIntegrityError("manifest segment path escapes bundle directory")
        if not candidate.is_file():
            raise DiagnosticBundleIntegrityError("manifest segment file is missing")
        return candidate
