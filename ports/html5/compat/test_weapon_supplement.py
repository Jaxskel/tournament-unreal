"""Fixed supplemental-report contracts and existing native target provenance.

No native editor, asset mutation, Windows or new report generation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponSupplementReport.h'
SPEC = HERE / 'report.weapon-supplement.json'
PRIVATE = None
BIO = '/Game/RestrictedAssets/Weapons/BioRifle/New/'
AMMO = '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/'
TARGETS = {BIO + n for n in ('BIO_HazyGlass_1p', 'BIO_Weapon3p', 'BIO_Weapon_1p_Inst', 'Bio_HazyGlass')} | {
    AMMO + 'Grenade/MIC_Grenade', AMMO + 'Material_ThirdPerson/MIC_Grenade_3P'}
GLASS = BIO + 'Bio_HazyGlass'


class Supplement(unittest.TestCase):
    def setUp(self):
        self.code = HEADER.read_text()
        self.spec = json.loads(SPEC.read_text())

    def test_exact_six_packages_and_only_glass_graph(self):
        self.assertEqual(set(self.spec['targets']), TARGETS)
        self.assertEqual(len(self.spec['targets']), 6)
        self.assertEqual(self.spec['graph_materials'], [GLASS])
        self.assertTrue(self.spec['read_only'])
        self.assertTrue(self.spec['original_project_view_required'])
        literal_paths = re.findall(r'TEXT\("(/Game/[^"\n]+)"\)', self.code)
        self.assertEqual(set(literal_paths), TARGETS)
        self.assertIn('WRExactPaths(Spec, TEXT("targets"), Paths)', self.code)
        self.assertIn('WRExactPaths(Spec, TEXT("graph_materials"), Graphs)', self.code)

    def test_original_files_checked_before_load_and_after_all_rows(self):
        first_load = self.code.index('LoadObject<UMaterialInterface>')
        self.assertLess(self.code.index('FPackageName::DoesPackageExist'), first_load)
        self.assertLess(self.code.index('A.Equals(B, ESearchCase::IgnoreCase)'), first_load)
        self.assertLess(self.code.index('Physical(Original, false)'), first_load)
        self.assertIn('FindPackage(nullptr, *P)', self.code)
        completion = self.code.index('Output.Emit(Done, TEXT("complete"))')
        for text in ('WSRUnchanged(ProjectFiles, BeforeHashes)', 'WSRUnchanged(OriginalFiles, BeforeHashes)'):
            self.assertLess(self.code.index(text), completion)
        self.assertIn('return Fail(TEXT("WeaponSupplementReport file bytes changed:', self.code)

    def test_actual_class_and_graph_scope_not_four_bio_mics(self):
        self.assertIn('IsGlassParent ? UMaterial::StaticClass() : UMaterialInstanceConstant::StaticClass()', self.code)
        self.assertIn('ObjectPath(GlassFamily ? WSRGlass() : WRMaster())', self.code)
        self.assertIn('GraphRows != 1', self.code)
        self.assertIn('MaterialRows != 6', self.code)
        self.assertIn('else if (J->GetArrayField(TEXT("nodes")).Num() != 0', self.code)
        self.assertNotIn('MRGraph(', self.code)

    def test_reuses_full_native_description_and_records_provenance(self):
        self.assertEqual(self.code.count('MRDescribe(M, Registry, J)'), 1)
        for name in ('package_dirty_before_description', 'original_content_root', 'original_file',
                     'project_file', 'original_sha1_before', 'selected_original_bytes_match'):
            self.assertIn('TEXT("' + name + '")', self.code)
        for prop in ('MP_Metallic', 'MP_Roughness', 'MP_Specular'):
            self.assertIn('GetExpressionInputForProperty(' + prop + ')', self.code)
        mr = (HEADER.parent / 'MaterialPreflightReport.h').read_text()
        for required in ('MRProperties(M, true)', 'MRStatic(MI->GetStaticParameters())',
                         'GetStaticParameterValues(Effective)', 'scalar_parameters', 'vector_parameters',
                         'parent_chain', 'package_sha1', 'package_dirty_after_load'):
            self.assertIn(required, mr)

    def test_no_asset_mutation_or_apply_entry(self):
        for prohibited in ('SavePackage(', '.Save(', 'SaveStringToFile(', 'CopyFile(', 'SetDirtyFlag(',
                           'MarkPackageDirty(', 'PostEditChange(', 'SetParentEditorOnly(', 'NewObject<',
                           'DuplicateObject<', 'SetMaterialFunction(', 'Apply=true'):
            self.assertNotIn(prohibited, self.code)
        for field in ('Manifest=', 'Receipt=', 'NoDependsGathering'):
            self.assertIn('TEXT("' + field + '")', self.code)
        self.assertIn('!GIsEditor || !IsInGameThread()', self.code)
        self.assertIn('SetBoolField(TEXT("apply_ready"), false)', self.code)

    def test_budget_and_serialization_fail_closed(self):
        self.assertIn('!FJsonSerializer::Serialize(', self.code)
        self.assertIn('Text.Len() > 8 * 1024 * 1024', self.code)
        self.assertIn('Characters > 16 * 1024 * 1024 - Text.Len()', self.code)
        self.assertIn('incomplete report', self.code)
        self.assertIn('if (!Output.Emit(J, TEXT("material"))) return 1', self.code)
        self.assertIn('return Output.Emit(Done, TEXT("complete")) ? 0 : 1', self.code)

    def test_private_captured_paths_and_classes(self):
        if PRIVATE is None:
            self.skipTest('pass --private-report-dir to verify existing native evidence')
        native = json.loads((PRIVATE / 'material-report-combat.json').read_text())
        observed = {}
        for row in native:
            if 'material' in row:
                observed[row['material'].split('.', 1)[0]] = row['class']
        data = (PRIVATE / 'material-report-all.log').read_bytes()
        text = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
        for line in text.splitlines():
            if 'COMPAT_REPORT ' not in line:
                continue
            row = json.loads(line.split('COMPAT_REPORT ', 1)[1])
            if row.get('mesh', '').endswith(('Grenade_Launcher_1p.Grenade_Launcher_1p', 'Grenade_Launcher_3p.Grenade_Launcher_3p')):
                slot = row['slots'][4]
                self.assertEqual(slot['slot_name'], 'ammo')
                observed[slot['material'].split('.', 1)[0]] = slot['class']
        self.assertTrue(TARGETS <= observed.keys())
        for target in TARGETS:
            self.assertEqual(observed[target], 'Material' if target == GLASS else 'MaterialInstanceConstant')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-report-dir', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE = args.private_report_dir
    unittest.main(argv=[sys.argv[0], *rest])
