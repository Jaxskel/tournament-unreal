"""Fixed-scope COW checks and opt-in host execution of pinned UE compile methods.

No editor, asset save, shader compiler, Windows call, or browser is executed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import weapon_fidelity as W

PRIVATE_SOURCE = None
PRIVATE_LOG = None
HEADER = W.HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponFidelityRepair.h'


class FixedScope(unittest.TestCase):
    def test_recipe_and_native_guard_match(self):
        recipe = W.load_recipe()
        self.assertIn('TEXT("' + W.RECIPE_SHA1 + '")', HEADER.read_text())
        plan = W.plan(recipe)
        self.assertEqual(len(plan['physical_destinations']), 23)
        self.assertEqual(len(plan['native_save_allowlist']), 9)
        self.assertEqual(len(plan['byte_identical_mics']), 14)
        self.assertFalse(plan['asset_writes_performed'])
        self.assertFalse(plan['shader_runtime_validated'])

    def test_recipe_byte_drift_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'recipe.json'
            p.write_bytes(W.RECIPE.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'reviewed exact'):
                W.load_recipe(p)

    def test_out_of_scope_parent_or_clone_refused(self):
        for key in ('direct_parents', 'instances'):
            r = W.load_recipe()
            r[key][0] = '/Game/Elsewhere'
            with self.assertRaises(ValueError):
                W.plan(r)
        r = W.load_recipe()
        r['clones'][next(iter(r['clones']))] = '/Game/Elsewhere'
        with self.assertRaises(ValueError):
            W.plan(r)

    def test_native_save_boundary_and_unsaved_parent_semantics(self):
        text = HEADER.read_text()
        body = text[text.index('bool Instance('):text.index('\n};\n')]
        self.assertNotIn('MRDescribe(', body)
        self.assertNotIn('MRHashPackage(', body)
        for field in ('parent_chain', 'static_overrides', 'static_effective', 'ScalarParameterValues',
                      'VectorParameterValues', 'TextureParameterValues', 'FontParameterValues', 'BasePropertyOverrides'):
            self.assertIn('TEXT("' + field + '")', body)
        self.assertEqual(text.count('UPackage::SavePackage('), 1)
        boundary = text.index('UPackage::SavePackage(')
        for predicate in ('if (!R.Graph(', 'if (!R.DiskPins())', 'if (!R.Policy.Check(P))'):
            self.assertLess(text.index(predicate), boundary)
        for forbidden in ('MakeSurface(', 'ClearParameterValues(', 'UpdateStaticPermutation(', 'SetDirtyFlag(false)', 'SaveAll'):
            self.assertNotIn(forbidden, text)
        self.assertIn('Saves.Append(R.Direct)', text)
        self.assertIn('Saves.Num() != 9', text)
        self.assertIn('Verify && Direct.Contains(KV.Key)', text)


class PhysicalView(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.original = self.root / 'original'
        self.project = self.root / 'private'
        self.recipe = W.load_recipe()
        for root in (self.original, self.project):
            (root / 'Content').mkdir(parents=True)
            (root / 'UnrealTournament.uproject').write_text('{}')
        for p in self.recipe['original_sha1']:
            data = p.encode()
            self.recipe['original_sha1'][p] = hashlib.sha1(data).hexdigest()
            path = self.original / 'Content' / W.cow.relative_asset(p)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if p in self.recipe['instances']:
                dest = self.project / 'Content' / W.cow.relative_asset(p)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        for p in self.recipe['clones'].values():
            (self.project / 'Content' / W.cow.relative_asset(p)).parent.mkdir(parents=True, exist_ok=True)
        self.mic = self.project / 'Content' / W.cow.relative_asset(self.recipe['instances'][0])

    def preflight(self):
        return W.preflight(self.project, self.original, self.recipe)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_prepared_view_receipt_readonly_exact23(self):
        before = self.snapshot()
        receipt = self.preflight()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(len(receipt['files']), 23)
        self.assertEqual(receipt['manifest_sha1'], W.RECIPE_SHA1)
        self.assertEqual(set(x['package'] for x in receipt['files']), set(W.plan(self.recipe)['physical_destinations']))

    def test_old_flattened_mic_is_not_accepted_or_overwritten(self):
        self.mic.write_bytes(b'old flattened fallback')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'MIC not restored'):
            self.preflight()
        self.assertEqual(before, self.snapshot())

    def test_original_hash_change_refused(self):
        path = self.original / 'Content' / W.cow.relative_asset(self.recipe['instances'][0])
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Original source bytes'):
            self.preflight()

    def test_existing_clone_refused(self):
        clone = self.project / 'Content' / W.cow.relative_asset(next(iter(self.recipe['clones'].values())))
        clone.write_bytes(b'previous generation')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.preflight()

    def test_missing_clone_parent_refused(self):
        parent = (self.project / 'Content' / W.cow.relative_asset(next(iter(self.recipe['clones'].values())))).parent
        parent.rmdir()
        with self.assertRaises(ValueError):
            self.preflight()

    def test_hardlink_mic_refused(self):
        import os
        source = self.original / 'Content' / W.cow.relative_asset(self.recipe['instances'][0])
        self.mic.unlink()
        os.link(source, self.mic)
        with self.assertRaisesRegex(ValueError, 'hardlink'):
            self.preflight()

    def test_symlink_ancestor_refused(self):
        content = self.project / 'Content'
        moved = self.project / 'OtherContent'
        content.rename(moved)
        content.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'reparse/symlink'):
            self.preflight()

    def test_nested_original_refused(self):
        with self.assertRaisesRegex(ValueError, 'disjoint'):
            W.preflight(self.original, self.original, self.recipe)

    def test_evidence_exclusive_and_outside_assets(self):
        content = self.project / 'Content'
        with self.assertRaisesRegex(ValueError, 'outside asset'):
            W.write_new(content / 'receipt.json', b'{}', (content,))
        output = self.root / 'receipt.json'
        W.write_new(output, b'first', (content,))
        with self.assertRaises(FileExistsError):
            W.write_new(output, b'second', (content,))
        self.assertEqual(output.read_bytes(), b'first')


def method(text, signature):
    start = text.index(signature)
    opened = text.index('{', start)
    depth = 1
    end = opened + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


class PinnedEvidence(unittest.TestCase):
    def test_actual_report_baseline_and_hierarchy(self):
        if PRIVATE_LOG is None:
            self.skipTest('pass --private-log for licensed native evidence')
        recipe = W.load_recipe()
        data = W.baseline(PRIVATE_LOG, recipe)
        rows = json.loads(data)['materials']
        master = W.report.MASTER
        direct = []
        for row in rows:
            p = row['material'].split('.', 1)[0]
            if p == master:
                self.assertEqual(len(row['nodes']), 720)
                continue
            chain = [x.split('.', 1)[0] for x in row['parent_chain']]
            self.assertTrue(set(chain) <= set(recipe['instances']) | {master})
            if chain[1] == master:
                direct.append(p)
            self.assertIn('FontParameterValues', row['properties'])
        self.assertEqual(set(direct), set(recipe['direct_parents']))
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / 'report.log'
            changed.write_bytes(Path(PRIVATE_LOG).read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'reviewed provenance'):
                W.baseline(changed, recipe)

    def test_pinned_lighting_identity_exception(self):
        if PRIVATE_SOURCE is None:
            self.skipTest('pass --private-source-dir for pinned identity lifecycle')
        raw = (PRIVATE_SOURCE / 'MaterialInterface.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '33f77f8526c95f3e5abd5e1f22c5f458534a155d7263969dc134fe6217722294')
        text = raw.decode('utf-8-sig')
        for signature in ('void UMaterialInterface::PostDuplicate(', 'void UMaterialInterface::PostEditChangeProperty('):
            self.assertIn('SetLightingGuid();', method(text, signature))
        self.assertIn('Skip.Add(TEXT("LightingGuid"))', HEADER.read_text())

    def test_actual_set_and_feature_compile_demand(self):
        if PRIVATE_SOURCE is None:
            self.skipTest('pass --private-source-dir for pinned private methods')
        raw = (PRIVATE_SOURCE / 'MaterialExpressions.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'aabf83778c557f3e68ff9a8ee003443b42ae12262fb2e87b406244e91f763d27')
        text = raw.decode('utf-8-sig')
        methods = '\n'.join(method(text, 'int32 ' + cls + '::Compile(') for cls in
                            ('UMaterialExpressionSetMaterialAttributes', 'UMaterialExpressionFeatureLevelSwitch'))
        stub = r'''
#include <cassert>
#include <functional>
#include <vector>
#include <cstdio>
using int32=int; using FGuid=int; using EMaterialValueType=int;
#define TEXT(x) x
#define check(x) assert(x)
#define checkf(x,...) assert(x)
#define ARRAY_COUNT(x) (sizeof(x)/sizeof((x)[0]))
constexpr int MP_MAX=99;
namespace ERHIFeatureLevel {enum Type {ES2,ES3_1,SM4,SM5,Num};}
struct FMaterialCompiler {int attribute=0; ERHIFeatureLevel::Type feature=ERHIFeatureLevel::ES2;
 int GetMaterialAttribute(){return attribute;} auto GetFeatureLevel(){return feature;}
 int Errorf(const char*){return -123;} int ValidCast(int x,int){return x;}};
struct FMaterialAttributeDefinitionMap {static int GetProperty(int x){return x;} static int GetValueType(int){return 0;}};
template<class T> struct TArray:std::vector<T> {using std::vector<T>::vector; int Num()const{return this->size();}
 bool Find(T x,int&i){for(i=0;i<Num();++i)if((*this)[i]==x)return true;return false;}};
struct Expr {std::function<int(FMaterialCompiler*,int)> evaluate;};
struct FExpressionInput {Expr* Expression=nullptr; int OutputIndex=0;
 int Compile(FMaterialCompiler*c){assert(Expression);return Expression->evaluate(c,OutputIndex);}};
struct UMaterialExpressionSetMaterialAttributes {TArray<int> AttributeSetTypes;TArray<FExpressionInput> Inputs;int Compile(FMaterialCompiler*,int);};
struct UMaterialExpressionFeatureLevelSwitch {FExpressionInput Default,Inputs[ERHIFeatureLevel::Num];int Compile(FMaterialCompiler*,int);};
'''
        harness = r'''
int main(){
 FMaterialCompiler c; int originalCalls=0,wpoCalls=0;
 Expr original{[&](auto*c,int){++originalCalls;return c->attribute==0?-99:42;}};
 Expr function{[&](auto*,int output){assert(output==1);++wpoCalls;return 73;}};
 UMaterialExpressionSetMaterialAttributes set;set.AttributeSetTypes={0};set.Inputs={{&original,0},{&function,1}};
 Expr wrapped{[&](auto*c,int i){return set.Compile(c,i);}};
 UMaterialExpressionFeatureLevelSwitch feature;feature.Default={&original,0};feature.Inputs[0]={&wrapped,0};
 assert(feature.Compile(&c,0)==73);assert(originalCalls==0&&wpoCalls==1);
 c.attribute=1;assert(feature.Compile(&c,0)==42);assert(originalCalls==1&&wpoCalls==1);
 for(int f=1;f<4;++f){c.feature=(ERHIFeatureLevel::Type)f;c.attribute=0;assert(feature.Compile(&c,0)==-99);
 c.attribute=1;assert(feature.Compile(&c,0)==42);}
 assert(wpoCalls==1);
 int aoCalls=0;Expr ao{[&](auto*,int){++aoCalls;return 19;}};Expr zero{[](auto*,int){return 0;}};
 UMaterialExpressionFeatureLevelSwitch aof;aof.Default={&ao,0};aof.Inputs[0]={&zero,0};c.feature=ERHIFeatureLevel::ES2;
 assert(aof.Compile(&c,0)==0&&aoCalls==0);c.feature=ERHIFeatureLevel::SM5;assert(aof.Compile(&c,0)==19&&aoCalls==1);
 aof.Default.Expression=nullptr;assert(aof.Compile(&c,0)==-123);
 set.AttributeSetTypes={0,0};assert(set.Compile(&c,0)==-123);
 puts("actual Set/Feature Compile demand checks PASS");
}
'''
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler, 'host C++ compiler required for requested private method test')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'demand.cpp'
            exe = Path(tmp) / 'demand'
            source.write_text(stub + methods + harness)
            built = subprocess.run([compiler, '-std=c++14', str(source), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('PASS', run.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-source-dir', type=Path)
    parser.add_argument('--private-log', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE_SOURCE, PRIVATE_LOG = args.private_source_dir, args.private_log
    unittest.main(argv=[sys.argv[0], *rest])
