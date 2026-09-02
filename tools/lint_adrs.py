#!/usr/bin/env python3
"""Lint MadMamba architecture decision records using only the Python standard library."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ADR_ID_RE = re.compile(r"^ADR-[0-9]{4}$")
TITLE_RE = re.compile(r"^# (ADR-[0-9]{4}): .+$")
REQ_RE = re.compile(r"^(?:(?:FR|NFR)-[A-Z0-9]+-[0-9]{3}|SEC-[0-9]{3})$")
REQUIRED_META = ("Status", "Date", "Task", "Requirements", "Supersedes", "Superseded-By")
REQUIRED_SECTIONS = ("Context", "Decision", "Alternatives", "Consequences")
ALLOWED_STATUS = {"Proposed", "Accepted", "Deprecated", "Superseded"}
MAX_ADR_FILES = 256
MAX_FILE_BYTES = 64 * 1024
MAX_LINE_CHARS = 1000
MAX_REFERENCE_COUNT = 32


class AdrLintError(ValueError):
    """Raised when an ADR set violates the R0-ADR-002 contract."""


@dataclass(frozen=True)
class Adr:
    adr_id: str
    path: Path
    metadata: dict[str, str]
    sections: frozenset[str]


def _read_bounded(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise AdrLintError(f"{path.name}: file exceeds {MAX_FILE_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > MAX_LINE_CHARS:
            raise AdrLintError(f"{path.name}:{number}: line exceeds {MAX_LINE_CHARS} characters")
    return text


def _split_refs(value: str, *, label: str) -> tuple[str, ...]:
    if value == "None":
        return ()
    refs = tuple(part.strip() for part in value.split(",") if part.strip())
    if not refs:
        raise AdrLintError(f"{label}: empty reference list")
    if len(refs) > MAX_REFERENCE_COUNT:
        raise AdrLintError(f"{label}: more than {MAX_REFERENCE_COUNT} references")
    return refs


def parse_adr(path: Path) -> Adr:
    text = _read_bounded(path)
    lines = text.splitlines()
    if not lines:
        raise AdrLintError(f"{path.name}: empty ADR")
    match = TITLE_RE.fullmatch(lines[0])
    if not match:
        raise AdrLintError(f"{path.name}: invalid ADR title")
    adr_id = match.group(1)
    if not path.name.startswith(f"{adr_id}-"):
        raise AdrLintError(f"{path.name}: filename does not match {adr_id}")

    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.startswith("## "):
            break
        if not line.strip():
            continue
        if ": " not in line:
            raise AdrLintError(f"{path.name}: malformed metadata line: {line}")
        key, value = line.split(": ", 1)
        if key in metadata:
            raise AdrLintError(f"{path.name}: duplicate metadata key {key}")
        metadata[key] = value.strip()

    missing_meta = [key for key in REQUIRED_META if not metadata.get(key)]
    if missing_meta:
        raise AdrLintError(f"{path.name}: missing metadata: {', '.join(missing_meta)}")
    unknown_meta = sorted(set(metadata) - set(REQUIRED_META))
    if unknown_meta:
        raise AdrLintError(f"{path.name}: unknown metadata: {', '.join(unknown_meta)}")
    if metadata["Status"] not in ALLOWED_STATUS:
        raise AdrLintError(f"{path.name}: invalid status {metadata['Status']}")
    if metadata["Task"] != "R0-ADR-002":
        raise AdrLintError(f"{path.name}: task must be R0-ADR-002")

    requirements = _split_refs(metadata["Requirements"], label=f"{path.name}: Requirements")
    for requirement in requirements:
        if not REQ_RE.fullmatch(requirement):
            raise AdrLintError(f"{path.name}: invalid requirement ID {requirement}")

    sections = frozenset(line[3:].strip() for line in lines if line.startswith("## ") and line[3:].strip())
    missing_sections = [section for section in REQUIRED_SECTIONS if section not in sections]
    if missing_sections:
        raise AdrLintError(f"{path.name}: missing sections: {', '.join(missing_sections)}")
    return Adr(adr_id=adr_id, path=path, metadata=metadata, sections=sections)


def lint_repository(repo_root: Path) -> list[Adr]:
    adr_dir = repo_root / "docs" / "adr"
    architecture_doc = repo_root / "docs" / "architecture" / "decision-map.md"
    paths = sorted(adr_dir.glob("ADR-*.md"))
    if not paths:
        raise AdrLintError("no ADR files found")
    if len(paths) > MAX_ADR_FILES:
        raise AdrLintError(f"ADR count exceeds {MAX_ADR_FILES}")

    adrs = [parse_adr(path) for path in paths]
    by_id: dict[str, Adr] = {}
    for adr in adrs:
        if adr.adr_id in by_id:
            raise AdrLintError(f"duplicate ADR ID: {adr.adr_id}")
        by_id[adr.adr_id] = adr

    for adr in adrs:
        supersedes = _split_refs(adr.metadata["Supersedes"], label=f"{adr.path.name}: Supersedes")
        superseded_by = _split_refs(adr.metadata["Superseded-By"], label=f"{adr.path.name}: Superseded-By")
        for ref in supersedes + superseded_by:
            if not ADR_ID_RE.fullmatch(ref):
                raise AdrLintError(f"{adr.path.name}: invalid supersession ADR ID {ref}")
            if ref == adr.adr_id:
                raise AdrLintError(f"{adr.path.name}: ADR cannot supersede itself")
            if ref not in by_id:
                raise AdrLintError(f"{adr.path.name}: unknown supersession target {ref}")
        for ref in supersedes:
            reverse = _split_refs(by_id[ref].metadata["Superseded-By"], label=f"{by_id[ref].path.name}: Superseded-By")
            if adr.adr_id not in reverse:
                raise AdrLintError(f"{adr.path.name}: {ref} lacks reciprocal Superseded-By link")
        for ref in superseded_by:
            reverse = _split_refs(by_id[ref].metadata["Supersedes"], label=f"{by_id[ref].path.name}: Supersedes")
            if adr.adr_id not in reverse:
                raise AdrLintError(f"{adr.path.name}: {ref} lacks reciprocal Supersedes link")

    architecture = _read_bounded(architecture_doc)
    for adr in adrs:
        if adr.adr_id not in architecture:
            raise AdrLintError(f"architecture decision map does not reference {adr.adr_id}")
    for referenced in set(re.findall(r"ADR-[0-9]{4}", architecture)):
        if referenced not in by_id:
            raise AdrLintError(f"architecture decision map references unknown {referenced}")
    return adrs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        adrs = lint_repository(args.repo.resolve())
    except (OSError, UnicodeError, AdrLintError) as exc:
        print(f"ADR lint failed: {exc}", file=sys.stderr)
        return 1
    print(f"ADR lint passed: {len(adrs)} ADRs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
