from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_traceability", ROOT / "tools" / "validate_traceability.py")
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class TraceabilityValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = json.loads((ROOT / "requirements" / "traceability.json").read_text(encoding="utf-8"))

    def validate(self, data: object) -> None:
        validator.validate_catalogue(data, ROOT)

    def test_R0_ADR_001_catalogue_is_valid(self) -> None:
        self.validate(self.catalogue)

    def test_R0_ADR_001_all_R1_tasks_map_to_requirement(self) -> None:
        r1 = [task for task in self.catalogue["tasks"] if task["id"].startswith("R1-")]
        self.assertEqual(49, len(r1))
        self.assertTrue(all(task["requirements"] for task in r1))

    def test_R0_ADR_001_rejects_missing_implementation_link(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["requirements"][0]["implementation"] = []
        with self.assertRaisesRegex(validator.TraceabilityError, "implementation"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_missing_test_link(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["requirements"][0]["tests"] = []
        with self.assertRaisesRegex(validator.TraceabilityError, "tests"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_missing_documentation_link(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["requirements"][0]["documentation"] = []
        with self.assertRaisesRegex(validator.TraceabilityError, "documentation"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_unknown_requirement_mapping(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["tasks"][0]["requirements"] = ["FR-FAKE-999"]
        with self.assertRaisesRegex(validator.TraceabilityError, "unknown requirements"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_duplicate_requirement_id(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["requirements"].append(copy.deepcopy(broken["requirements"][0]))
        with self.assertRaisesRegex(validator.TraceabilityError, "duplicate requirement"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_duplicate_task_id(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["tasks"].append(copy.deepcopy(broken["tasks"][0]))
        with self.assertRaisesRegex(validator.TraceabilityError, "duplicate task"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_repository_path_escape(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["requirements"][0]["implementation"] = ["../secret.txt"]
        with self.assertRaisesRegex(validator.TraceabilityError, "escapes repository root"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_missing_concrete_path(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["requirements"][0]["implementation"] = ["src/does-not-exist.py"]
        with self.assertRaisesRegex(validator.TraceabilityError, "missing repository path"):
            self.validate(broken)

    def test_R0_ADR_001_rejects_unknown_root_field(self) -> None:
        broken = copy.deepcopy(self.catalogue)
        broken["unexpected"] = True
        with self.assertRaisesRegex(validator.TraceabilityError, "only schemaVersion"):
            self.validate(broken)

    def test_R0_ADR_001_parser_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                validator._load_json(path)

    def test_R0_ADR_001_privacy_canary_absent(self) -> None:
        forbidden = ("secret" + "-canary-value", "pass" + "word=", "authorization:" + " bearer", "private-key" + "-canary")
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            for canary in forbidden:
                self.assertNotIn(canary, lowered, f"privacy canary leaked into {path.relative_to(ROOT)}")


if __name__ == "__main__":
    unittest.main()
