"""Synthetic native-report contract tests, not engine/material compilation tests."""
import copy
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch

import material_preflight as mp


def fixture():
    spec = json.loads(mp.SPEC.read_text())
    targets = {mp.object_path(t['package']): t for t in spec['targets']}
    result = []
    for path, t in targets.items():
        chain = [path]
        current = t
        while current['role'] != 'parent':
            parent = current['expected_parent'] or mp.object_path(current['package'].removesuffix('_Inst'))
            chain.append(parent)
            current = targets[parent]
        nodes = {}
        def node(name):
            if name not in nodes:
                nodes[name] = dict(path=path + ':' + name, name=name, owner=path,
                                   **{'class': name.rsplit('_', 1)[0]}, properties={}, inputs=[])
            return nodes[name]
        def pin(name):
            return dict(expression=node(name)['path'], output_index=0, mask=[0, 0, 0, 0, 0], available=True)
        roots = {k: dict(expression='', output_index=0, mask=[0]*5, available=True) for k in sorted(mp.ROOTS)} if t['role'] == 'parent' else {}
        for edge, expected in t['assert_edges'].items():
            p = pin(expected)
            if '.' in edge:
                n, inp = edge.split('.')
                p.update(name=inp, index=len(node(n)['inputs']))
                node(n)['inputs'].append(p)
            else:
                roots[edge] = p
        props = {k: '()' for k in ('ScalarParameterValues', 'VectorParameterValues', 'TextureParameterValues', 'FontParameterValues', 'BasePropertyOverrides')}
        r = dict(schema='ut4-material-report-v1', kind='material', material=path,
                 **{'class': t['expected_class']}, base_material=chain[-1],
                 parent_chain=chain, blend=t['expected_blend'], shading=t['expected_shading'],
                 two_sided=False, opacity_mask_clip=0.3333, registry_scan_complete=True,
                 package_dirty_after_load=False, properties=props, nodes=list(nodes.values()), roots=roots,
                 package_sha1={p.split('.')[0]: 'a' * 40 for p in chain},
                 scalar_parameters=[dict(name='Power', value=2)],
                 vector_parameters=[dict(name='Effect Color', value=[1, 0, 4, 50])], texture_parameters=[],
                 direct_referencers=['/Game/Example/Dependent'], transitive_referencers=['/Game/Example/Dependent'])
        if t['role'] == 'variant':
            r.update(static_overrides=dict(switches=[], masks=[], terrain=[]),
                     static_effective=dict(switches=[], masks=[], terrain=[]))
        result.append(r)
    return result


def log(records, complete=True):
    rows = list(records)
    if complete:
        rows.append(dict(schema='ut4-material-report-v1', kind='complete', count=11, read_only=True))
    return '\n'.join('LogCompat: Display: ' + mp.PREFIX + json.dumps(r) for r in rows)


class MaterialPreflightTests(unittest.TestCase):
    def test_exact_scope_and_hdr_alpha_preserved(self):
        report = mp.validate(mp.read_log(log(fixture())))
        self.assertFalse(report['apply_ready'])
        self.assertEqual(len(report['materials']), 11)
        self.assertEqual(report['materials'][0]['vector_parameters'][0]['value'][-1], 50)
        spec = json.loads(mp.SPEC.read_text())
        self.assertEqual(sum(t['role'] == 'parent' for t in spec['targets']), 5)
        self.assertEqual(sum(t['role'] == 'variant' for t in spec['targets']), 6)

    def test_truncated_duplicate_and_extra_records_fail(self):
        with self.assertRaisesRegex(ValueError, 'completion'):
            mp.read_log(log(fixture(), False))
        rows = fixture(); rows[-1] = copy.deepcopy(rows[0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            mp.validate(mp.read_log(log(rows)))
        with self.assertRaisesRegex(ValueError, 'after completion'):
            mp.read_log(log(fixture()) + '\n' + log(fixture()))
        rows = fixture(); rows[0]['material'] = '/Game/NotSelected.NotSelected'
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            mp.validate(rows)

    def test_parent_and_effective_blend_not_inferred(self):
        rows = fixture()
        variant = next(r for r in rows if r['material'].endswith('BeamMaterial_Inst_Translucent.BeamMaterial_Inst_Translucent'))
        variant['blend'] = 0
        with self.assertRaisesRegex(ValueError, 'blend'):
            mp.validate(rows)
        rows = fixture(); variant = next(r for r in rows if r['class'] != 'Material')
        variant['parent_chain'][1] = '/Game/Other.Other'
        with self.assertRaisesRegex(ValueError, 'parent|base'):
            mp.validate(rows)

    def test_missing_native_masks_and_wrong_edges_fail(self):
        rows = fixture(); r = next(r for r in rows if r['roots'])
        next(iter(r['roots'].values())).pop('mask')
        with self.assertRaisesRegex(ValueError, 'mask'):
            mp.validate(rows)
        rows = fixture(); r = next(r for r in rows if r['roots'])
        next(p for p in r['roots'].values() if p['expression'])['expression'] = ''
        with self.assertRaisesRegex(ValueError, 'edge mismatch'):
            mp.validate(rows)

    def test_native_index_none_only_for_disconnected_inputs(self):
        disconnected = dict(expression='', output_index=-1, mask=[0]*5)
        mp.pin_valid(disconnected, 'optional function input', {'node'})
        for invalid in (-2, 1.5):
            with self.assertRaisesRegex(ValueError, 'output index'):
                mp.pin_valid({**disconnected, 'output_index': invalid}, 'bad', {'node'})
        with self.assertRaisesRegex(ValueError, 'output index'):
            mp.pin_valid({**disconnected, 'expression': 'node'}, 'connected', {'node'})

    def test_missing_refraction_root_is_not_complete_evidence(self):
        rows = fixture()
        next(r for r in rows if r['roots'])['roots'].pop('Refraction')
        with self.assertRaisesRegex(ValueError, 'incomplete root coverage'):
            mp.validate(rows)

    def test_dangling_function_graph_and_missing_hash_fail(self):
        rows = fixture(); r = next(r for r in rows if r['nodes'])
        r['nodes'][0]['inputs'].append(dict(name='Broken', index=99, expression='/Game/Missing.Node', output_index=0, mask=[0]*5))
        with self.assertRaisesRegex(ValueError, 'dangling'):
            mp.validate(rows)
        rows = fixture(); r = next(r for r in rows if r['nodes'])
        r['nodes'][0]['function'] = '/Game/Function.Function'
        with self.assertRaisesRegex(ValueError, 'function package hash'):
            mp.validate(rows)

    def test_overrides_registry_and_dirty_load_are_required(self):
        for mutate in [lambda r: r['properties'].pop('BasePropertyOverrides'),
                       lambda r: r.pop('static_overrides'),
                       lambda r: r.update(registry_scan_complete=False),
                       lambda r: r.update(package_dirty_after_load=True)]:
            rows = fixture(); variant = next(r for r in rows if r['class'] != 'Material')
            mutate(variant)
            with self.assertRaises(ValueError):
                mp.validate(rows)

    def test_snapshot_drift_in_masks_overrides_and_dependents(self):
        baseline = mp.validate(fixture())
        for mutate in [lambda rows: next(r for r in rows if r['roots'])['roots'][next(iter(next(r for r in rows if r['roots'])['roots']))].update(mask=[1,1,0,0,0]),
                       lambda rows: rows[0]['properties'].update(BasePropertyOverrides='(bOverride_BlendMode=True)'),
                       lambda rows: rows[0]['direct_referencers'].append('/Game/AdditionalDependent'),
                       lambda rows: rows[0]['vector_parameters'][0].update(value=[1,0,4,1])]:
            rows = fixture(); mutate(rows)
            self.assertNotEqual(mp.validate(rows), baseline)

    def test_cli_never_overwrites_or_writes_on_failed_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root/'report.log'; out = root/'review.json'
            source.write_text(log(fixture()))
            with patch('builtins.print'):
                mp.main(['--report-log', str(source), '--out', str(out)])
            before = out.read_bytes()
            with self.assertRaises(SystemExit):
                mp.main(['--report-log', str(source), '--out', str(out)])
            self.assertEqual(out.read_bytes(), before)
            source.write_text(log(fixture(), False))
            with self.assertRaises(SystemExit):
                mp.main(['--report-log', str(source), '--out', str(root/'bad.json')])
            self.assertFalse((root/'bad.json').exists())

    def test_cli_baseline_drift_fails_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); baseline=root/'baseline.json'; source=root/'native.log'; out=root/'new.json'
            baseline.write_text(json.dumps(mp.validate(fixture())))
            rows=fixture(); rows[0]['direct_referencers'].append('/Game/NewConsumer'); source.write_text(log(rows))
            with self.assertRaises(SystemExit):
                mp.main(['--report-log', str(source), '--out', str(out), '--baseline', str(baseline)])
            self.assertFalse(out.exists())

    def test_read_only_spec_is_rejected_by_actual_cow_parser(self):
        import prepare_cow
        with self.assertRaises(prepare_cow.Unsafe):
            prepare_cow.load_manifest(mp.SPEC)

    def test_inconsistent_parent_hash_is_rejected(self):
        rows = fixture()
        variant = next(r for r in rows if len(r['parent_chain']) > 1)
        variant['package_sha1'][variant['parent_chain'][-1].split('.')[0]] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'inconsistent package hash'):
            mp.validate(rows)

    def test_actual_native_pin_body_preserves_output_and_masks(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable for actual MRPin body test')
        header = (mp.SPEC.parent/'UT4Html5Compat/Source/UT4Html5Compat/Private/MaterialPreflightReport.h').read_text()
        start = header.index('static TSharedPtr<FJsonObject> MRPin(')
        end = header.index('static bool MRHashPackage', start)
        body = header[start:end]
        harness = r"""
#include <cassert>
#include <memory>
#include <string>
#include <map>
#include <vector>
#define TEXT(x) x
using int32 = int;
template<class T> using TSharedPtr = std::shared_ptr<T>;
template<class T> TSharedPtr<T> MakeShareable(T* p) { return TSharedPtr<T>(p); }
template<class T> struct TArray : std::vector<T> { void Add(T v) { this->push_back(v); } };
struct FJsonValue { double value; explicit FJsonValue(double v):value(v) {} };
struct FJsonValueNumber : FJsonValue { using FJsonValue::FJsonValue; };
struct FJsonObject {
 std::map<std::string,std::string> strings;
 std::map<std::string,double> numbers;
 std::map<std::string,bool> booleans;
 std::map<std::string,TArray<TSharedPtr<FJsonValue>>> arrays;
 void SetStringField(const char* k, std::string v) { strings[k]=v; }
 void SetNumberField(const char* k, double v) { numbers[k]=v; }
 void SetBoolField(const char* k, bool v) { booleans[k]=v; }
 void SetArrayField(const char* k, TArray<TSharedPtr<FJsonValue>> v) { arrays[k]=v; }
};
struct Expression { std::string GetPathName() { return "/Game/Selected.Selected:ParticleColor"; } };
struct FExpressionInput { struct Expression* Expression; int OutputIndex, Mask,MaskR,MaskG,MaskB,MaskA; };
""" + body + r"""
int main() {
 Expression expr;
 FExpressionInput input{&expr,3,15,1,0,1,0};
 auto p=MRPin(&input);
 assert(p->strings["expression"]==expr.GetPathName());
 assert(p->numbers["output_index"]==3 && p->booleans["available"]);
 int expected[]={15,1,0,1,0};
 for(int i=0;i<5;++i) assert(p->arrays["mask"][i]->value==expected[i]);
 input.Expression=nullptr;
 auto disconnected=MRPin(&input);
 assert(disconnected->strings["expression"].empty());
 assert(disconnected->numbers["output_index"]==3);
 auto absent=MRPin(nullptr);
 assert(!absent->booleans["available"] && absent->arrays["mask"].size()==5);
 for(auto v:absent->arrays["mask"]) assert(v->value==0);
}
"""
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'pin.cpp'; binary=Path(td)/'pin'
            source.write_text(harness)
            built=subprocess.run([compiler,'-std=c++14','-Wall','-Wextra',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            subprocess.run([str(binary)],check=True,timeout=10)

    def test_report_route_precedes_apply_and_has_no_mutators(self):
        private=mp.SPEC.parent/'UT4Html5Compat/Source/UT4Html5Compat/Private'
        source=(private/'UT4Html5Compat.cpp').read_text()
        main=source[source.index('int32 UUT4Html5CompatCommandlet::Main'):]
        self.assertLess(main.index('return MaterialPreflightReport(Params)'), main.index('ParseManifest('))
        helper=(private/'MaterialPreflightReport.h').read_text()
        for forbidden in ('SavePackage(', 'PostEditChange(', 'MarkPackageDirty(', 'SetParentEditorOnly(', 'UpdateStaticPermutation(', 'AddGameNameRedirect('):
            self.assertNotIn(forbidden, helper)
        for field in ('GetInputs()', 'OutputIndex', 'MaskR', 'GetBlendMode()', 'GetStaticParameters()', 'GetStaticParameterValues(', 'GetReferencers(', 'SearchAllAssets(true)', 'Paths != MRScope()'):
            self.assertIn(field, helper)
        self.assertNotIn('CPF_Edit)', helper)  # FunctionInputs are not necessarily CPF_Edit.


if __name__ == '__main__':
    unittest.main()
