"""Native report contract and malformed-evidence tests; no engine/assets/browser."""
import copy
import json
from pathlib import Path
import re
import unittest
import weapon_preflight as w

ROOT = Path(__file__).resolve().parent
HEADER = ROOT / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponPreflightReport.h'


def skin_fixture():
    return dict(resource='GetResourceForRendering: existing ImportedResource', is_editor=True,
                runtime_component_observed=False, es2_bone_limit=75, sm5_bone_limit=256,
                lods=[dict(lod=0, num_vertices=10, num_tex_coords=1, vertex_buffer_vertices=10,
                           vertex_buffer_tex_coords=1, vertex_buffer_extra_influences=False,
                           sections=[dict(section=0, bone_map_count=75, max_bone_influences=4,
                                          extra_influences=False, num_vertices=10, num_triangles=5, disabled=False)])])


def fixture():
    spec = json.loads((ROOT / 'report.weapons.json').read_text())
    base = w.object_path(w.MASTER)
    function = '/Game/Test/FirstPerson.FirstPerson'
    paths = [base + ':Call', function + ':Output']
    def pin(expr=''):
        return dict(expression=expr, output_index=0, available=True, mask=[0]*5)
    hashes = {p: 'a'*40 for p in spec['targets'] + spec['meshes'] + ['/Game/Test/FirstPerson']}
    rows = []
    for package in spec['targets']:
        master = package == w.MASTER
        rows.append(dict(schema=w.SCHEMA, kind='material', material=w.object_path(package),
                         base_material=base, parent_chain=[base] if master else [w.object_path(package), base],
                         **{'class': 'Material' if master else 'MaterialInstanceConstant'},
                         package_sha1=hashes.copy(), package_dirty_after_load=False,
                         package_dirty_before_description=False,
                         properties={k: '()' for k in ('ScalarParameterValues', 'VectorParameterValues', 'TextureParameterValues', 'BasePropertyOverrides')},
                         static_overrides=dict(switches=[], masks=[], terrain=[]),
                         static_effective=dict(switches=[], masks=[], terrain=[]),
                         scalar_parameters=[dict(name='Panini', value=1.0)],
                         vector_parameters=[dict(name='Color', value=[1, 0.5, 0.2, 2.0])],
                         texture_parameters=[dict(name='Actor Normal Map', value='/Game/T.T')],
                         roots={k: pin(paths[0]) for k in w.ROOTS | {'Metallic', 'Roughness', 'Specular'}} if master else {},
                         nodes=[dict(path=paths[0], owner=base, properties={'FunctionInputs': '(Input=...)'}, inputs=[pin(paths[1])], function=function),
                                dict(path=paths[1], owner=function, properties={'OutputName': 'WPO Only'}, inputs=[])] if master else []))
    for package in spec['meshes']:
        rows.append(dict(schema=w.SCHEMA, kind='mesh', mesh=w.object_path(package), package_sha1=hashes.copy(),
                         package_dirty_after_load=False,
                         skin=skin_fixture(), slots=[dict(slot=0, slot_name='Body', material=w.object_path(spec['targets'][0]))]))
    return rows


def log(rows):
    complete = dict(schema=w.SCHEMA, kind='complete', materials=19, meshes=4, read_only=True, apply_ready=False)
    return '\n'.join('Log: '+w.PREFIX+json.dumps(r) for r in rows+[complete])


class WeaponReportTests(unittest.TestCase):
    def test_exact_native_spec_matches_eighteen_fallback_targets(self):
        spec = json.loads((ROOT/'report.weapons.json').read_text())
        manifest = json.loads((ROOT/'manifest.browser-surfaces.json').read_text())
        expected = {a['package'] for a in manifest['assets'] if a['operation'] == 'fallback_textured'} | {w.MASTER}
        self.assertEqual(set(spec['targets']), expected)
        self.assertEqual(len(spec['targets']), 19)
        source = HEADER.read_text()
        scope = source.split('static TArray<FString> WRScope()', 1)[1].split('static TArray<FString> WRMeshes()', 1)[0]
        self.assertEqual(set(re.findall(r'Paths.Add\(TEXT\("([^"]+)"\)\)', scope)), expected)
        self.assertIs(spec['read_only'], True)
        meshes = source.split('static TArray<FString> WRMeshes()', 1)[1].split('static bool WRExactPaths', 1)[0]
        self.assertEqual(set(re.findall(r'Paths.Add\(TEXT\("([^"]+)"\)\)', meshes)), set(spec['meshes']))

    def test_native_getters_and_fail_closed_report_contract(self):
        source = HEADER.read_text()
        for token in ['Values->Num() != Expected.Num()', 'V->Type != EJson::String', 'Paths == Expected',
                      '!IsInGameThread()', 'TEXT("Manifest=")', 'TEXT("Receipt=")',
                      'MRDescribe(M, Registry, J)', 'MP_Metallic', 'MP_Roughness', 'MP_Specular',
                      'Mesh->Materials.Num() > 16', '8 * 1024 * 1024', '32 * 1024 * 1024 - Text.Len()',
                      'package_dirty_before_description', 'SetBoolField(TEXT("apply_ready"), false)']:
            self.assertIn(token, source)
        self.assertIsNone(re.search(r'\b(SavePackage|SetDirtyFlag|MarkPackageDirty|SetMaterial|SetParentEditorOnly|ClearParameterValuesEditorOnly|UpdateStaticPermutation|PostEditChange|NewObject|DuplicateObject|SpawnActor)\s*\(', source))

    def test_skin_raw_native_fields_and_no_unexported_methods(self):
        source = HEADER.read_text().split('static bool WRSkin(', 1)[1].split('static int32 WeaponPreflightReport', 1)[0]
        for text in ['Mesh->GetResourceForRendering()', '16 - TotalLODs', '256 - TotalSections - Sections',
                     'Section.BoneMap.Num()', 'Section.MaxBoneInfluences', 'Section.HasExtraBoneInfluences()',
                     'LOD.VertexBufferGPUSkin.HasExtraBoneInfluences()', 'GetNumTexCoords()',
                     'ERHIFeatureLevel::ES2', 'ERHIFeatureLevel::SM5']:
            self.assertIn(text, source)
        for method in ['GetMaxBonesPerSection', 'RequiresCPUSkinning', 'Resource->HasExtraBoneInfluences']:
            self.assertNotIn(method, source)

    def test_later_disabled_lod_extra_influences_count_even_if_buffer_flag_false(self):
        mesh = fixture()[-1]
        later = copy.deepcopy(mesh['skin']['lods'][0]); later['lod'] = 1
        later['sections'][0].update(max_bone_influences=8, extra_influences=True, disabled=True)
        mesh['skin']['lods'].append(later)
        value = w.skin_evidence([mesh])[mesh['mesh']]
        self.assertTrue(value['requires_cpu_skinning_es2'])
        self.assertFalse(value['requires_cpu_skinning_sm5'])
        self.assertFalse(value['vertex_buffer_extra_influences'])

    def test_buffer_flag_not_resource_predicate_and_exact_palette_boundary(self):
        mesh = fixture()[-1]; mesh['skin']['lods'][0]['vertex_buffer_extra_influences'] = True
        self.assertFalse(w.skin_evidence([mesh])[mesh['mesh']]['requires_cpu_skinning_es2'])
        section = mesh['skin']['lods'][0]['sections'][0]
        for count, es2, sm5 in [(76, True, False), (256, True, False), (257, True, True)]:
            section['bone_map_count'] = count
            result = w.skin_evidence([mesh])[mesh['mesh']]
            self.assertEqual((result['requires_cpu_skinning_es2'], result['requires_cpu_skinning_sm5']), (es2, sm5))

    def test_skin_total_budgets_reject_not_truncate(self):
        mesh = fixture()[-1]
        mesh['skin']['lods'] = [dict(copy.deepcopy(mesh['skin']['lods'][0]), lod=i) for i in range(16)]
        self.assertEqual(w.skin_evidence([mesh])[mesh['mesh']]['lods'], 16)
        with self.assertRaisesRegex(ValueError, 'LOD budget'): w.skin_evidence([mesh, fixture()[-2]])
        mesh = fixture()[-1]; section = mesh['skin']['lods'][0]['sections'][0]
        mesh['skin']['lods'][0]['sections'] = [dict(section, section=i) for i in range(256)]
        w.skin_evidence([mesh])
        with self.assertRaisesRegex(ValueError, 'section budget'): w.skin_evidence([mesh, fixture()[-2]])

    def test_complete_original_report_keeps_wpo_and_hdr_evidence(self):
        rows = fixture()
        original = copy.deepcopy(rows)
        result = w.validate(w.read_log(log(rows)))
        self.assertFalse(result['apply_ready'])
        self.assertEqual(result['master_nodes'], 2)
        self.assertEqual(result['unexpected_base_materials'], [])
        self.assertEqual(rows, original)

    def test_partial_duplicate_after_complete_and_wrong_schema_rejected(self):
        text = log(fixture())
        for bad in ['\n'.join(text.splitlines()[:-1]), text+'\n'+text.splitlines()[0],
                    text.replace(w.SCHEMA, 'wrong'), log(fixture()[:-1])]:
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError): w.read_log(bad)
        rows = fixture(); rows[0] = copy.deepcopy(rows[1])
        with self.assertRaisesRegex(ValueError, 'scope'): w.validate(rows)

    def test_engine_functions_have_same_hash_and_owner_requirements(self):
        rows = fixture()
        old, new = '/Game/Test/FirstPerson', '/Engine/Functions/FirstPerson'
        rows = json.loads(json.dumps(rows).replace(old, new))
        self.assertEqual(w.validate(rows)['functions'], [new + '.FirstPerson'])
        for row in rows:
            del row['package_sha1'][new]
        with self.assertRaisesRegex(ValueError, 'function provenance'): w.validate(rows)

    def test_missing_function_nodes_and_dangling_root_rejected(self):
        rows = fixture(); master = next(r for r in rows if r.get('material') == w.object_path(w.MASTER))
        master['nodes'][1]['owner'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'function expressions'): w.validate(rows)
        rows = fixture(); master = next(r for r in rows if r.get('material') == w.object_path(w.MASTER))
        master['roots']['MaterialAttributes']['expression'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'dangling'): w.validate(rows)

    def test_missing_overrides_never_accepted_as_empty(self):
        rows = fixture(); instance = next(r for r in rows if r.get('class') == 'MaterialInstanceConstant')
        del instance['properties']['BasePropertyOverrides']
        with self.assertRaisesRegex(ValueError, 'override bag'): w.validate(rows)

    def test_provenance_conflicts_rejected(self):
        rows = fixture(); rows[1]['package_sha1'][w.MASTER] = 'b'*40
        with self.assertRaisesRegex(ValueError, 'inconsistent'): w.validate(rows)

    def test_dirty_and_reparented_materials_reported_never_apply_ready(self):
        rows = fixture(); instance = next(r for r in rows if r.get('class') == 'MaterialInstanceConstant')
        instance['package_dirty_after_load'] = True
        other = '/Game/HTML5Compat/Fallback'
        instance['parent_chain'][-1] = instance['base_material'] = w.object_path(other)
        instance['package_sha1'][other] = 'c'*40
        result = w.validate(rows)
        self.assertIn(instance['material'], result['unexpected_base_materials'])
        self.assertTrue(result['dirty_packages'])
        self.assertFalse(result['apply_ready'])

    def test_nonfinite_truncated_masks_and_bad_slot_indices_rejected(self):
        for field in ('nan', 'mask', 'slot'):
            rows = fixture()
            if field == 'nan': rows[0]['scalar_parameters'][0]['value'] = float('nan')
            elif field == 'mask':
                master = next(r for r in rows if r.get('material') == w.object_path(w.MASTER))
                master['roots']['Normal']['mask'] = [1]
            else: rows[-1]['slots'][0]['slot'] = 3
            with self.subTest(field=field), self.assertRaises(ValueError): w.validate(rows)


if __name__ == '__main__': unittest.main()
