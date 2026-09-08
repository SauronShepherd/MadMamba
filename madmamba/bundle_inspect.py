from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .bundle_reader import DiagnosticBundleIntegrityError, DiagnosticBundleReader
from .bundle_recovery import DiagnosticBundleRecovery


def inspect_bundle(
    directory: str | os.PathLike[str], *, recover_open: bool = False
) -> dict[str, Any]:
    """Return a bounded, non-secret summary of a diagnostic bundle.

    FINAL bundles are always read through strict integrity verification. OPEN
    bundles are rejected unless ``recover_open`` is explicit, in which case
    only complete records accepted by ``DiagnosticBundleRecovery`` contribute
    to the summary.
    """

    root = Path(directory)
    manifest_path = root / DiagnosticBundleReader.MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DiagnosticBundleIntegrityError("manifest is missing or invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise DiagnosticBundleIntegrityError("manifest must be an object")

    state = manifest.get("state")
    discarded_tail_bytes = 0
    recovered = False
    if state == "FINAL":
        records = DiagnosticBundleReader(root).read_records()
    elif state == "OPEN" and recover_open:
        recovery = DiagnosticBundleRecovery(root).recover()
        records = list(recovery.records)
        discarded_tail_bytes = recovery.discarded_tail_bytes
        recovered = True
    elif state == "OPEN":
        raise DiagnosticBundleIntegrityError(
            "diagnostic bundle is OPEN; pass --recover-open for best-effort complete-record recovery"
        )
    else:
        raise DiagnosticBundleIntegrityError("diagnostic bundle has unsupported state")

    counts: dict[str, int] = {}
    for record in records:
        record_type = str(record["recordType"])
        counts[record_type] = counts.get(record_type, 0) + 1

    return {
        "state": state,
        "recovered": recovered,
        "records": len(records),
        "recordTypes": dict(sorted(counts.items())),
        "discardedTailBytes": discarded_tail_bytes,
    }
