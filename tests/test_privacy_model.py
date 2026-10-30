from __future__ import annotations
import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('validate_privacy_model',ROOT/'tools/validate_privacy_model.py'); assert SPEC and SPEC.loader
v=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(v)
DATA=json.loads((ROOT/'privacy/data-class-inventory.json').read_text())
class PrivacyModelTests(unittest.TestCase):
    def validate(self,d): v.validate_inventory(d)
    def test_R0_ADR_003_repository_inventory_is_valid(self): self.validate(DATA)
    def test_R0_ADR_003_covers_exact_config_baseline(self):
        got={p for paths in DATA['fieldGroups']['config'].values() for p in paths}; self.assertEqual(v.BASELINE_CONFIG_FIELDS,got)
    def test_R0_ADR_003_covers_exact_report_baseline(self):
        got={p for paths in DATA['fieldGroups']['report'].values() for p in paths}; self.assertEqual(v.BASELINE_REPORT_FIELDS,got)
    def test_R0_ADR_003_every_prohibited_class_has_canary_strategy(self):
        bad=[x['id'] for x in DATA['dataClasses'] if x['category']=='prohibited' and 'canaryStrategy' not in x]; self.assertEqual([],bad)
    def test_R0_ADR_003_canary_strategies_cover_all_sinks(self):
        for x in DATA['dataClasses']:
            if x['category']=='prohibited': self.assertEqual(v.REQUIRED_CANARY_SINKS,set(x['canaryStrategy']['sinks']))
    def test_R0_ADR_003_rejects_missing_field_mapping(self):
        d=copy.deepcopy(DATA); next(iter(d['fieldGroups']['config'].values())).pop(0)
        with self.assertRaisesRegex(v.PrivacyModelError,'unclassified'): self.validate(d)
    def test_R0_ADR_003_rejects_unknown_field_without_review(self):
        d=copy.deepcopy(DATA); next(iter(d['fieldGroups']['report'].values())).append('report.futureSecret')
        with self.assertRaisesRegex(v.PrivacyModelError,'require baseline review'): self.validate(d)
    def test_R0_ADR_003_rejects_unknown_class(self):
        d=copy.deepcopy(DATA); paths=d['fieldGroups']['config'].pop(next(iter(d['fieldGroups']['config']))); d['fieldGroups']['config']['safe.unknown']=paths
        with self.assertRaisesRegex(v.PrivacyModelError,'unknown data class'): self.validate(d)
    def test_R0_ADR_003_rejects_duplicate_mapping(self):
        d=copy.deepcopy(DATA); groups=list(d['fieldGroups']['config'].values()); groups[1].append(groups[0][0])
        with self.assertRaisesRegex(v.PrivacyModelError,'duplicate field mapping'): self.validate(d)
    def test_R0_ADR_003_rejects_prohibited_class_without_canary(self):
        d=copy.deepcopy(DATA); p=next(x for x in d['dataClasses'] if x['category']=='prohibited'); p.pop('canaryStrategy')
        with self.assertRaisesRegex(v.PrivacyModelError,'requires a complete canaryStrategy'): self.validate(d)
    def test_R0_ADR_003_rejects_incomplete_canary_sinks(self):
        d=copy.deepcopy(DATA); p=next(x for x in d['dataClasses'] if x['category']=='prohibited'); p['canaryStrategy']['sinks'].pop()
        with self.assertRaisesRegex(v.PrivacyModelError,'cover every required sink'): self.validate(d)
    def test_R0_ADR_003_rejects_wrong_task(self):
        d=copy.deepcopy(DATA); d['task']='R0-ADR-999'
        with self.assertRaisesRegex(v.PrivacyModelError,'task must be'): self.validate(d)
    def test_R0_ADR_003_rejects_invalid_path(self):
        d=copy.deepcopy(DATA); next(iter(d['fieldGroups']['config'].values()))[0]='../secret'
        with self.assertRaisesRegex(v.PrivacyModelError,'path is invalid'): self.validate(d)
    def test_R0_ADR_003_file_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.json'; p.write_text('x'*(v.MAX_FILE_BYTES+1))
            with self.assertRaisesRegex(v.PrivacyModelError,'exceeds'): v._load_bounded(p)
if __name__=='__main__': unittest.main()
