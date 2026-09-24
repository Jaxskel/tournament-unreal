"""Malformed-evidence tests and inverse checks; full UE compilation is separate."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
import enforcer_consumer_report as report

HERE = Path(__file__).resolve().parent
PRIVATE = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private'


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inputs = Path(self.tmp.name) / 'inputs.json'
        self.log = Path(self.tmp.name) / 'native.log'
        self.pins = [{'package': p, 'file': 'F:/fixture/' + str(i) + '.uasset', 'bytes': 1, 'sha1': 'a' * 40}
                     for i, p in enumerate(report.PACKAGES)]
        self.inputs.write_text(json.dumps({'schema': 'ut4-enforcer-consumer-inputs-v1', 'packages': self.pins}))
        self.rows = [{'kind': 'begin'}]
        for i, pin in enumerate(self.pins):
            p = pin['package']; cls = 'Blueprint' if i < 3 else 'SkeletalMesh' if i < 5 else 'MaterialInstanceConstant'
            self.rows.append({'kind': 'root', 'file_pin': pin, 'object': p + '.' + p.rsplit('/', 1)[-1], 'class': '/Script/Engine.' + cls})
        for p in report.PACKAGES[:3]:
            c = p + '.' + p.rsplit('/', 1)[-1] + '_C'; cdo = p + '.Default__' + p.rsplit('/', 1)[-1] + '_C'
            self.rows += [{'kind': 'class', 'class': c, 'root_class': c, 'cdo': cdo},
                          {'kind': 'dual_defaults', 'cdo': cdo}, {'kind': 'component', 'mesh_component': True}]
        for p in report.PACKAGES[3:5]:
            obj = p + '.' + p.rsplit('/', 1)[-1]
            self.rows += [{'kind': 'mesh', 'mesh': obj, 'slot_count': 1},
                          {'kind': 'material_chain', 'context': obj + ':asset_slot', 'slot': 0}]
        self.rows.append({'kind': 'complete', 'root_packages': 7, 'blueprints': 3, 'components': 3,
                          'assets_saved': 0, 'selected_bytes_unchanged': True, 'runtime_behavior_verified': False, 'repair_authority': False})
        for i, row in enumerate(self.rows):
            row.update(schema='ut4-enforcer-consumer-v1', run=hashlib.sha1(self.inputs.read_bytes()).hexdigest(),
                       sequence=i, read_only=True, global_usage_complete=False, exclusive_runtime_consumption_proven=False)

    def read(self, encoding='utf-8'):
        self.log.write_text('\n'.join('Log: ' + report.PREFIX + json.dumps(r) for r in self.rows), encoding=encoding)
        return report.validate(self.log, self.inputs)

    def test_utf8_utf16_scope(self):
        for enc in ('utf-8', 'utf-16'):
            value = self.read(enc)
            self.assertTrue(value['observation_complete'])
            self.assertFalse(value['repair_authority'])

    def test_partial_rejected(self):
        self.rows.pop()
        with self.assertRaises(ValueError): self.read()

    def test_duplicate_sequence_rejected(self):
        self.rows[2]['sequence'] = 1
        with self.assertRaises(ValueError): self.read()

    def test_other_generation_rejected(self):
        self.rows[1]['run'] = 'b' * 40
        with self.assertRaises(ValueError): self.read()

    def test_root_pin_drift_rejected(self):
        self.rows[1]['file_pin'] = dict(self.pins[0], sha1='c' * 40)
        with self.assertRaises(ValueError): self.read()

    def test_runtime_or_save_claim_rejected(self):
        for key, value in [('assets_saved', 1), ('repair_authority', True), ('runtime_behavior_verified', True)]:
            old = self.rows[-1][key]; self.rows[-1][key] = value
            with self.assertRaises(ValueError): self.read()
            self.rows[-1][key] = old

    def test_wrong_class_rejected(self):
        self.rows[1]['class'] = '/Script/Engine.Material'
        with self.assertRaises(ValueError): self.read()

    def test_error_before_completion_rejected(self):
        self.rows[2]['kind'] = 'error'
        with self.assertRaises(ValueError): self.read()

    def test_missing_observation_rows_rejected(self):
        for kind in ('component', 'class', 'mesh', 'material_chain'):
            old = self.rows
            self.rows = [dict(r) for r in old if r['kind'] != kind]
            for i, row in enumerate(self.rows): row['sequence'] = i
            with self.assertRaises(ValueError): self.read()
            self.rows = old


class SourceBoundaryTests(unittest.TestCase):
    def test_old_report_default_inverse(self):
        s = (PRIVATE / 'WeaponGrenadeAssignmentReport.h').read_text()
        s = s.replace('    // Optional labels for another fixed read-only consumer query; defaults preserve this report.\n'
                      '    const TCHAR* Schema = TEXT("ut4-grenade-assignment-v1");\n'
                      '    const TCHAR* Prefix = TEXT("COMPAT_WEAPON_GRENADE_ASSIGNMENT");\n', '')
        s = s.replace('J->SetStringField(TEXT("schema"), Schema);', 'J->SetStringField(TEXT("schema"), TEXT("ut4-grenade-assignment-v1"));')
        s = s.replace('TEXT("%s %s"), Prefix, *Line', 'TEXT("COMPAT_WEAPON_GRENADE_ASSIGNMENT %s"), *Line')
        self.assertEqual(hashlib.sha256(s.encode()).hexdigest(), 'b90c2589f8c62cdb0fa6b7fa3d9c1bb879eb26943ab35aca78bbb72f9619b474')

    def test_fixed_scope_no_asset_mutation(self):
        s = (PRIVATE / 'EnforcerConsumerReport.h').read_text()
        roots = re.findall(r'R.Add\(TEXT\("([^"]+)"\)\);', s)
        self.assertEqual(roots, report.PACKAGES)
        self.assertIsNone(re.search(r'\b(SavePackage|SetMaterial|SetParentEditorOnly|SetDirtyFlag|NewObject|DuplicateObject|SpawnActor|LoadMap|ProcessEvent|PostEditChange)\s*\(', s))
        self.assertIn('if (!Inputs.Check()) return WFRStop(TEXT("enforcer-consumer-final-pins"))', s)
        self.assertIn('GetDefaultObject(false)', s)


if __name__ == '__main__': unittest.main()
