from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lint_adrs", ROOT / "tools" / "lint_adrs.py")
assert SPEC and SPEC.loader
linter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = linter
SPEC.loader.exec_module(linter)


class AdrLintTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        shutil.copytree(ROOT / "docs" / "adr", root / "docs" / "adr")
        (root / "docs" / "architecture").mkdir(parents=True)
        shutil.copy2(ROOT / "docs" / "architecture" / "decision-map.md", root / "docs" / "architecture")
        return temp, root

    def test_R0_ADR_002_repository_is_valid(self) -> None:
        adrs = linter.lint_repository(ROOT)
        self.assertEqual([f"ADR-{number:04d}" for number in range(1, 6)], [adr.adr_id for adr in adrs])

    def test_R0_ADR_002_all_records_are_accepted(self) -> None:
        self.assertTrue(all(adr.metadata["Status"] == "Accepted" for adr in linter.lint_repository(ROOT)))

    def test_R0_ADR_002_rejects_missing_decision(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0001-per-interpreter-runtime.md"
        path.write_text(path.read_text().replace("## Decision", "## Deliberation"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "missing sections: Decision"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_missing_alternatives(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0002-sys-monitoring-policy.md"
        path.write_text(path.read_text().replace("## Alternatives", "## Options"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "Alternatives"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_missing_consequences(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0003-jsonl-bundle.md"
        path.write_text(path.read_text().replace("## Consequences", "## Effects"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "Consequences"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_invalid_status(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0004-local-first-viewer.md"
        path.write_text(path.read_text().replace("Status: Accepted", "Status: Maybe"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "invalid status"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_missing_supersession_metadata(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0005-experimental-injection-separation.md"
        path.write_text(path.read_text().replace("Supersedes: None\n", ""), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "missing metadata"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_unknown_supersession_target(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0005-experimental-injection-separation.md"
        path.write_text(path.read_text().replace("Supersedes: None", "Supersedes: ADR-9999"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "unknown supersession target"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_nonreciprocal_supersession(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0005-experimental-injection-separation.md"
        path.write_text(path.read_text().replace("Supersedes: None", "Supersedes: ADR-0004"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "reciprocal"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_architecture_map_missing_adr(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "architecture" / "decision-map.md"
        path.write_text(path.read_text().replace("ADR-0003", "ADR-XXXX"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "does not reference ADR-0003"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_architecture_map_unknown_adr(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "architecture" / "decision-map.md"
        path.write_text(path.read_text() + "\nADR-9999\n", encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "references unknown ADR-9999"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_invalid_requirement_id(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0002-sys-monitoring-policy.md"
        path.write_text(path.read_text().replace("FR-MON-010", "FR-MON-X"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "invalid requirement ID"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_wrong_task_id(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0001-per-interpreter-runtime.md"
        path.write_text(path.read_text().replace("Task: R0-ADR-002", "Task: R0-ADR-003"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "task must be R0-ADR-002"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_filename_id_mismatch(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        old = root / "docs" / "adr" / "ADR-0001-per-interpreter-runtime.md"; new = root / "docs" / "adr" / "ADR-0006-per-interpreter-runtime.md"; old.rename(new)
        with self.assertRaisesRegex(linter.AdrLintError, "filename does not match"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_oversized_file(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0001-per-interpreter-runtime.md"; path.write_text("x" * (linter.MAX_FILE_BYTES + 1), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "file exceeds"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_excessive_line_length(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "architecture" / "decision-map.md"; path.write_text(path.read_text() + "\n" + "x" * (linter.MAX_LINE_CHARS + 1), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "line exceeds"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_too_many_adrs(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        source = root / "docs" / "adr" / "ADR-0001-per-interpreter-runtime.md"
        for number in range(6, linter.MAX_ADR_FILES + 2):
            copy = root / "docs" / "adr" / f"ADR-{number:04d}-copy.md"; copy.write_text(source.read_text().replace("ADR-0001", f"ADR-{number:04d}"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "ADR count exceeds"): linter.lint_repository(root)

    def test_R0_ADR_002_rejects_too_many_supersession_refs(self) -> None:
        temp, root = self.fixture(); self.addCleanup(temp.cleanup)
        path = root / "docs" / "adr" / "ADR-0001-per-interpreter-runtime.md"
        refs = ", ".join(f"ADR-{number:04d}" for number in range(1000, 1000 + linter.MAX_REFERENCE_COUNT + 1))
        path.write_text(path.read_text().replace("Supersedes: None", f"Supersedes: {refs}"), encoding="utf-8")
        with self.assertRaisesRegex(linter.AdrLintError, "more than"): linter.lint_repository(root)


if __name__ == "__main__": unittest.main()
