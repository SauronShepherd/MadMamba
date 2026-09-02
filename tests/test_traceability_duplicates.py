from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_traceability", ROOT / "tools" / "validate_traceability.py"
)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)

with (ROOT / "requirements" / "traceability.json").open(encoding="utf-8") as handle:
    CATALOGUE = json.load(handle)


class TraceabilityDuplicateTests(unittest.TestCase):
    def test_rejects_duplicate_requirement_links(self) -> None:
        data = copy.deepcopy(CATALOGUE)
        requirement = data["requirements"][0]
        requirement["documentation"].append(requirement["documentation"][0])
        with self.assertRaisesRegex(
            validator.TraceabilityError, "must not contain duplicate entries"
        ):
            validator.validate_catalogue(data, ROOT)

    def test_rejects_duplicate_task_requirement_mapping(self) -> None:
        data = copy.deepcopy(CATALOGUE)
        task = data["tasks"][0]
        task["requirements"].append(task["requirements"][0])
        with self.assertRaisesRegex(
            validator.TraceabilityError, "must not contain duplicate entries"
        ):
            validator.validate_catalogue(data, ROOT)


if __name__ == "__main__":
    unittest.main()
