#!/usr/bin/env python3
"""Validate MadMamba's requirement/task traceability catalogue using stdlib only."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQ_ID = re.compile(r"^((FR|NFR)-[A-Z0-9]+-[0-9]{3}|SEC-[0-9]{3})$")
TASK_ID = re.compile(r"^R[0-9]+-[A-Z0-9]+-[0-9]{3}$")
REF_PREFIXES = ("planned:", "spec:")
REQUIRED_LINK_FIELDS = ("implementation", "tests", "documentation")


class TraceabilityError(ValueError):
    """Raised when traceability data violates the MadMamba catalogue contract."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TraceabilityError(f"{label} must be a non-empty string")
    return value


def _validate_reference(repo_root: Path, ref: Any, label: str) -> None:
    ref = _require_nonempty_string(ref, label)
    if ref.startswith(REF_PREFIXES):
        return
    candidate = (repo_root / ref).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise TraceabilityError(f"{label} escapes repository root: {ref}") from exc
    if not candidate.exists():
        raise TraceabilityError(f"{label} points to missing repository path: {ref}")


def validate_catalogue(data: Any, repo_root: Path) -> None:
    if not isinstance(data, dict):
        raise TraceabilityError("catalogue root must be an object")
    if set(data) != {"schemaVersion", "requirements", "tasks"}:
        raise TraceabilityError("catalogue must contain only schemaVersion, requirements, and tasks")
    if data["schemaVersion"] != "1.0.0":
        raise TraceabilityError("unsupported schemaVersion")

    requirements = data["requirements"]
    tasks = data["tasks"]
    if not isinstance(requirements, list) or not requirements:
        raise TraceabilityError("requirements must be a non-empty list")
    if not isinstance(tasks, list) or not tasks:
        raise TraceabilityError("tasks must be a non-empty list")

    requirement_ids: set[str] = set()
    for index, requirement in enumerate(requirements):
        label = f"requirements[{index}]"
        if not isinstance(requirement, dict):
            raise TraceabilityError(f"{label} must be an object")
        expected = {"id", "summary", "source", "implementation", "tests", "documentation", "releaseClaim"}
        if set(requirement) != expected:
            raise TraceabilityError(f"{label} fields must be exactly {sorted(expected)}")
        req_id = _require_nonempty_string(requirement["id"], f"{label}.id")
        if not REQ_ID.fullmatch(req_id):
            raise TraceabilityError(f"invalid requirement id: {req_id}")
        if req_id in requirement_ids:
            raise TraceabilityError(f"duplicate requirement id: {req_id}")
        requirement_ids.add(req_id)
        _require_nonempty_string(requirement["summary"], f"{label}.summary")
        source = _require_nonempty_string(requirement["source"], f"{label}.source")
        if not source.startswith("spec:"):
            raise TraceabilityError(f"{label}.source must use spec: reference")
        _require_nonempty_string(requirement["releaseClaim"], f"{label}.releaseClaim")
        for field in REQUIRED_LINK_FIELDS:
            refs = requirement[field]
            if not isinstance(refs, list) or not refs:
                raise TraceabilityError(f"{label}.{field} must be a non-empty list")
            for ref_index, ref in enumerate(refs):
                _validate_reference(repo_root, ref, f"{label}.{field}[{ref_index}]")

    task_ids: set[str] = set()
    r1_tasks = 0
    for index, task in enumerate(tasks):
        label = f"tasks[{index}]"
        if not isinstance(task, dict):
            raise TraceabilityError(f"{label} must be an object")
        expected = {"id", "stage", "requirements", "acceptance"}
        if set(task) != expected:
            raise TraceabilityError(f"{label} fields must be exactly {sorted(expected)}")
        task_id = _require_nonempty_string(task["id"], f"{label}.id")
        if not TASK_ID.fullmatch(task_id):
            raise TraceabilityError(f"invalid task id: {task_id}")
        if task_id in task_ids:
            raise TraceabilityError(f"duplicate task id: {task_id}")
        task_ids.add(task_id)
        _require_nonempty_string(task["stage"], f"{label}.stage")
        _require_nonempty_string(task["acceptance"], f"{label}.acceptance")
        mapped = task["requirements"]
        if not isinstance(mapped, list) or not mapped:
            raise TraceabilityError(f"{label}.requirements must be a non-empty list")
        missing = [req_id for req_id in mapped if req_id not in requirement_ids]
        if missing:
            raise TraceabilityError(f"{task_id} references unknown requirements: {', '.join(missing)}")
        if task_id.startswith("R1-"):
            r1_tasks += 1

    if r1_tasks == 0:
        raise TraceabilityError("catalogue must include R1 task mappings")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "catalogue",
        nargs="?",
        type=Path,
        default=Path("requirements/traceability.json"),
        help="Path to traceability catalogue (default: requirements/traceability.json)",
    )
    args = parser.parse_args(argv)
    catalogue = args.catalogue.resolve()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        validate_catalogue(_load_json(catalogue), repo_root)
    except (OSError, json.JSONDecodeError, TraceabilityError) as exc:
        print(f"traceability validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"traceability validation passed: {catalogue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
