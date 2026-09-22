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


def without_uv0(text):
    """Remove only the reviewed opt-in delta; retain the historical inverse checks."""
    for name in ('NODE', 'PIN'):
        text = re.sub(r'^    [^\n]*// WFR_UV0_' + name + r'_BEGIN\n.*?^    [^\n]*// WFR_UV0_' + name + r'_END\n',
                      '', text, flags=re.M | re.S)
    for line in (
        '    bool UV0 = false; // Explicit fresh Apply/Verify variant; never adopts existing clones.\n',
        '        UMaterialExpression* UV = UV0 ? UV0Node(M) : nullptr;\n',
        '        if (UV0 && !UV) return false;\n',
        '        if (UV0 && (!Pin(Set->Inputs[2], UV) || Set->AttributeSetTypes[1] != FMaterialAttributeDefinitionMap::GetID(MP_CustomizedUVs0))) return false;\n',
        '    R.UV0 = FParse::Param(*Params, TEXT("WeaponUV0"));\n',
        '    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_REPAIR variant=%s"), R.UV0 ? TEXT("es2-uv0-passthrough") : TEXT("original-six-node"));\n',
    ):
        if text.count(line) != 1:
            raise AssertionError('unexpected UV0 delta: ' + line)
        text = text.replace(line, '')
    for new, old in (('Set->Inputs.Num() != (UV0 ? 3 : 2)', 'Set->Inputs.Num() != 2'),
                     ('Set->AttributeSetTypes.Num() != (UV0 ? 2 : 1)', 'Set->AttributeSetTypes.Num() != 1'),
                     ('Added != (UV0 ? 7 : 6)', 'Added != 6')):
        if text.count(new) != 1:
            raise AssertionError('unexpected UV0 predicate: ' + new)
        text = text.replace(new, old)
    return text


def prove_uv0_identity(master):
    """Follow attribute demand through the captured graph, all switch arms included.

    This proves a finite-alpha value identity, not compilation success. Alpha is
    intentionally not evaluated: eager alpha compilation is the failing path.
    Function interfaces are joined by serialized GUID, never display name.
    Unknown nodes, masked attribute wires, cycles and disconnected required inputs fail.
    """
    nodes = {n['path']: n for n in master['nodes']}
    assert len(nodes) == len(master['nodes'])
    uv_id = 'D30EC284E13A416087BB52302ED115DC'
    seen, blends, switches, leaves = set(), set(), set(), set()
    calls = 0
    completed = {}

    def wire(pin, context, active):
        assert pin['expression'] and not any(pin['mask']), 'missing/masked attribute wire'
        return visit(pin['expression'], pin['output_index'], context, active)

    def visit(path, output, context, active):
        nonlocal calls
        calls += 1
        assert calls <= 10000 and len(active) < 128, 'walk budget'
        key = (path, output, tuple(frame['call'] for frame in context))
        assert key not in active, 'attribute cycle'
        if key in completed:
            return completed[key]
        active = active | {key}
        result = evaluate(path, output, context, active)
        completed[key] = result
        return result

    def evaluate(path, output, context, active):
        n = nodes[path]; p = n['properties']; ins = n['inputs']; kind = n['class']
        seen.add(path)
        if kind == 'MaterialExpressionMaterialFunctionCall':
            ids = re.findall(r'ExpressionInputId=([A-F0-9]{32})', p['FunctionInputs'])
            outs = re.findall(r'ExpressionOutputId=([A-F0-9]{32})', p['FunctionOutputs'])
            assert len(ids) == len(ins) and len(ids) == len(set(ids))
            target = [x for x in nodes.values() if x['owner'] == n['function'] and
                      x['class'] == 'MaterialExpressionFunctionOutput' and x['properties']['Id'] == outs[output]]
            assert len(target) == 1
            frame = {'call': path, 'owner': n['function'], 'pins': dict(zip(ids, ins)), 'outer': context}
            return visit(target[0]['path'], 0, context + (frame,), active)
        if kind == 'MaterialExpressionFunctionInput':
            assert output == 0 and p['InputType'] == 'FunctionInput_MaterialAttributes'
            assert context and context[-1]['owner'] == n['owner']
            frame = context[-1]; pin = frame['pins'][p['Id']]
            if pin['expression']:
                return wire(pin, frame['outer'], active)
            assert p['bUsePreviewValueAsDefault'] == 'True' and len(ins) == 1
            return wire(ins[0], context, active)
        if kind == 'MaterialExpressionFunctionOutput':
            assert output == 0 and len(ins) == 1
            return wire(ins[0], context, active)
        if kind == 'MaterialExpressionSetMaterialAttributes':
            assert output == 0 and uv_id not in p['AttributeSetTypes']
            return wire(ins[0], context, active)
        if kind == 'MaterialExpressionGetMaterialAttributes':
            assert output == 0, 'only the attributes passthrough is equivalent'
            return wire(ins[0], context, active)
        if kind == 'MaterialExpressionMakeMaterialAttributes':
            assert output == 0
            pin = next(i for i in ins if i['name'] == 'CustomizedUVs0')
            assert not pin['expression'], 'custom UV0 overrides the default'
            leaves.add(path)
            return 'uv0'
        if kind == 'MaterialExpressionBlendMaterialAttributes':
            assert output == 0 and p['VertexAttributeBlendType'] == ''
            assert wire(ins[0], context, active) == wire(ins[1], context, active) == 'uv0'
            blends.add(path)
            return 'uv0'
        if kind in ('MaterialExpressionStaticSwitchParameter', 'MaterialExpressionStaticSwitch'):
            assert output == 0
            assert wire(ins[0], context, active) == wire(ins[1], context, active) == 'uv0'
            switches.add(path)
            return 'uv0'
        if kind in ('MaterialExpressionFeatureLevelSwitch', 'MaterialExpressionQualitySwitch'):
            assert output == 0 and ins[0]['expression']
            for pin in ins:
                if pin['expression']:
                    assert wire(pin, context, active) == 'uv0'
            switches.add(path)
            return 'uv0'
        raise AssertionError('unsupported attribute producer: ' + path)

    assert wire(master['roots']['MaterialAttributes'], (), set()) == 'uv0'
    return {'visited': seen, 'blends': blends, 'switches': switches, 'leaves': leaves}


class UV0Passthrough(unittest.TestCase):
    def master(self):
        if PRIVATE_LOG is None:
            self.skipTest('pass --private-log for licensed native evidence')
        rows = json.loads(W.baseline(PRIVATE_LOG, W.load_recipe()))['materials']
        return next(r for r in rows if r['material'].split('.', 1)[0] == W.report.MASTER)

    def test_opt_in_delta_and_existing_state_admission(self):
        text = HEADER.read_text()
        self.assertEqual(hashlib.sha256(without_uv0(text).encode()).hexdigest(),
                         '00b0e0e27a7dd08ce43fa8a9b650b253cacef3de8a96ec8a89730290c99e8fd5')
        self.assertIn('R.UV0 = FParse::Param(*Params, TEXT("WeaponUV0"));', text)
        self.assertIn('(!Verify && FPackageName::DoesPackageExist(KV.Value))', text)
        self.assertIn('Added != (UV0 ? 7 : 6)', text)
        self.assertIn('Set->Inputs.Num() != (UV0 ? 3 : 2)', text)
        self.assertIn('!Pin(Set->Inputs[2], UV)', text)
        self.assertIn('TEXT("/Script/Engine.MaterialExpressionTextureCoordinate")', text)
        self.assertIn('E->GetClass() != Class', text)
        self.assertIn('E->Material != M || E->Function || E->GetInputs().Num() != 0', text)
        self.assertIn('!P->TryGetStringField(Keys[I], Value) || Value != Values[I]', text)
        self.assertIn('TEXT(""), TEXT("1.000000"), TEXT("1.000000"), TEXT(""), TEXT("")', text)
        self.assertEqual(text.count('UPackage::SavePackage('), 1)
        self.assertIn('Saves.Num() != 9', text)

    def test_graph_wide_and_all_reachable_uv0_branches(self):
        master = self.master()
        makes = [n for n in master['nodes'] if n['class'] == 'MaterialExpressionMakeMaterialAttributes']
        sets = [n for n in master['nodes'] if n['class'] == 'MaterialExpressionSetMaterialAttributes']
        self.assertEqual(len(makes), 8)
        self.assertEqual(len(sets), 15)
        for n in makes:
            pins = [i for i in n['inputs'] if i['name'].startswith('CustomizedUVs')]
            self.assertEqual(len(pins), 8)
            self.assertTrue(all(not p['expression'] for p in pins), n['path'])
        for n in sets:
            self.assertNotIn('D30EC284E13A416087BB52302ED115DC', n['properties']['AttributeSetTypes'])
        proof = prove_uv0_identity(master)
        self.assertEqual({k: len(v) for k, v in proof.items()},
                         {'visited': 104, 'blends': 8, 'switches': 10, 'leaves': 2})
        # Both blend operands resolve to the SAME symbol UV0. For finite alpha,
        # U + alpha*(U-U) = U; this is not a promise for NaNs/infinite alpha or
        # bit-identical rounding of alternative hardware lerp implementations.
        from fractions import Fraction
        for u in (Fraction(-13, 7), Fraction(0), Fraction(1, 65536), Fraction(128)):
            for a in (Fraction(-1000), Fraction(-1, 3), Fraction(0), Fraction(1), Fraction(1000)):
                self.assertEqual(u + a * (u - u), u)

    def test_graph_proof_refuses_modified_or_unknown_attribute_paths(self):
        master = self.master()
        proof = prove_uv0_identity(master)
        mutations = ('make', 'set', 'unknown', 'mask', 'cycle')
        for mutation in mutations:
            changed = copy.deepcopy(master)
            nodes = {n['path']: n for n in changed['nodes']}
            root = nodes[changed['roots']['MaterialAttributes']['expression']]
            if mutation == 'make':
                n = nodes[next(iter(proof['leaves']))]
                next(i for i in n['inputs'] if i['name'] == 'CustomizedUVs0')['expression'] = root['path']
            elif mutation == 'set':
                root['properties']['AttributeSetTypes'] += 'D30EC284E13A416087BB52302ED115DC'
            elif mutation == 'unknown':
                root['class'] = 'UnknownAttributesProducer'
            elif mutation == 'mask':
                root['inputs'][0]['mask'][0] = 1
            else:
                root['inputs'][0]['expression'] = root['path']
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                prove_uv0_identity(changed)

    def test_only_nonzero_explicit_uv_channel_is_disabled_for_selected_instances(self):
        master = self.master()
        for node in master['nodes']:
            if 'ConstCoordinate' in node['properties']:
                self.assertIn(node['properties']['ConstCoordinate'], ('', '0'), node['path'])
            if node['class'] == 'MaterialExpressionCustom':
                self.assertEqual(node['properties']['Code'], 'PaniniProjection(OM, D, S)')
        uv1 = [n for n in master['nodes'] if n['class'] == 'MaterialExpressionTextureCoordinate' and
               n['properties']['CoordinateIndex'] not in ('', '0')]
        self.assertEqual(len(uv1), 1)
        self.assertEqual(uv1[0]['properties']['CoordinateIndex'], '1')
        consumers = [(n, pin) for n in master['nodes'] for pin in n['inputs'] if pin['expression'] == uv1[0]['path']]
        self.assertEqual(len(consumers), 1)
        switch, pin = consumers[0]
        self.assertEqual(switch['class'], 'MaterialExpressionStaticSwitchParameter')
        self.assertEqual(switch['properties']['ParameterName'], 'Overlay Map use UV1')
        self.assertEqual(pin['index'], 0)  # true arm, not the selected false arm
        rows = json.loads(W.baseline(PRIVATE_LOG, W.load_recipe()))['materials']
        for row in rows:
            if row is master or row['class'] != 'MaterialInstanceConstant':
                continue
            values = [s['value'] for s in row['static_effective']['switches'] if s['name'] == 'Overlay Map use UV1']
            self.assertEqual(values, [False], row['material'])
        # This evidence justifies ONLY UV0. It does not authorize eight overrides
        # or claim a complete shader compiler demand trace.

    def test_pinned_default_uv_is_texture_coordinate_not_stored_zero_vector(self):
        if PRIVATE_SOURCE is None:
            self.skipTest('pass --private-source-dir for pinned private methods')
        raw = (PRIVATE_SOURCE / 'MaterialShared.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '1dff15c0b80b3818055d654144dba9a346d8d471540854f17d4d572492f37f32')
        text = raw.decode('utf-8-sig')
        body = method(text, 'int32 FMaterialAttributeDefintion::CompileDefaultValue(')
        self.assertIn('if (TexCoordIndex == INDEX_NONE)', body)
        self.assertIn('Ret = Compiler->TextureCoordinate(TexCoordIndex, false, false);', body)
        entry = next(line for line in text.splitlines() if 'TEXT("CustomizedUV0")' in line)
        self.assertIn('MP_CustomizedUVs0, MCT_Float2, FVector4(0,0,0,0), SF_Vertex, 0', entry)


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


class Diagnostics(unittest.TestCase):
    @staticmethod
    def erase_call(text, name, replacement):
        # Balanced parentheses/quoted strings: preserve the first argument verbatim.
        needle = name + '('
        while needle in text:
            start = text.index(needle)
            pos = start + len(needle)
            depth, quoted, escaped, comma = 1, False, False, None
            for end in range(pos, len(text)):
                ch = text[end]
                if quoted:
                    if escaped:
                        escaped = False
                    elif ch == chr(92):
                        escaped = True
                    elif ch == '"':
                        quoted = False
                    continue
                if ch == '"':
                    quoted = True
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        break
                elif ch == ',' and depth == 1 and comma is None:
                    comma = end
            else:
                raise AssertionError('unterminated diagnostic call')
            first = text[pos:comma if comma is not None else end]
            text = text[:start] + (first if replacement is None else replacement) + text[end + 1:]
        return text

    def test_diagnostic_inverse_recovers_frozen_repair_byte_exact(self):
        text = without_uv0(HEADER.read_text())
        text = re.sub(r'                // WFR_REBIND_BEGIN\n.*?                // WFR_REBIND_END\n', '', text, flags=re.S)
        text, count = re.subn(r'// WFR_DIAGNOSTICS_BEGIN\n.*?// WFR_DIAGNOSTICS_END\n', '', text, flags=re.S)
        self.assertEqual(count, 1)
        text, count = re.subn(r'    WFRStage\(TEXT\("[^"\n]+"\)\); // WFR_DIAGNOSTIC_STAGE\n', '', text)
        self.assertEqual(count, 13)
        text = self.erase_call(text, 'WFRGate', None)
        text = self.erase_call(text, 'WFRStop', '1')
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         '7aa3e67cf02200e0357736d4a11f93e38d58eb8758c4078828491b175df5cf9f')

    def test_rebind_only_delta_to_reviewed_diagnostic_header(self):
        text, count = re.subn(r'                // WFR_REBIND_BEGIN\n.*?                // WFR_REBIND_END\n', '', without_uv0(HEADER.read_text()), flags=re.S)
        self.assertEqual(count, 1)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         '920496faf814a183396c65d6fda5f7f84e3759b955f4434a249d1850a1fb4809')
        body = HEADER.read_text()
        block = body.split('// WFR_REBIND_BEGIN')[1].split('// WFR_REBIND_END')[0]
        self.assertIn('if (Dest)', block)
        self.assertIn('Call->UpdateFromFunctionResource(false);', block)
        self.assertIn('R.Same(MRValue(Before), MRValue(MRProperties(Call, true)))', block)
        self.assertIn('!Input.ExpressionInput', block)
        self.assertIn('!Output.ExpressionOutput', block)
        self.assertLess(body.index('Call->UpdateFromFunctionResource(false)'), body.index('Call->SetMaterialFunction('))
        self.assertLess(body.index('if (!Verify)\n    {\n        for (const auto& KV : R.Clones)'), body.index('// WFR_REBIND_BEGIN'))

    def test_every_main_failure_has_bounded_diagnostic_context(self):
        text = HEADER.read_text()
        body = text[text.index('static int32 WeaponFidelityRepair('):]
        self.assertNotIn('return 1;', body)
        self.assertEqual(body.count('return WFRStop('), 31)
        for gate in ('original-already-loaded', 'clone-loaded-or-existing', 'baseline-duplicate',
                     'recipe-hash', 'baseline-hash', 'original-master-snapshot', 'save-policy', 'save-package'):
            self.assertIn('TEXT("' + gate + '")', body)
        helper = text.split('// WFR_DIAGNOSTICS_BEGIN\n')[1].split('// WFR_DIAGNOSTICS_END')[0]
        self.assertIn('Context.Left(320)', helper)
        self.assertIn('return Passed;', helper)
        for forbidden in ('LoadObject', 'SavePackage', 'MarkPackageDirty', 'HashFile', 'SetParent', 'ReadJson'):
            self.assertNotIn(forbidden, helper)
        self.assertIn('return WFRGate(X && Y && Same(*X, *Y), TEXT("field-mismatch"), Key);', text)


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


    def test_actual_guid_rebind_then_name_remap_preserves_connections(self):
        if PRIVATE_SOURCE is None:
            self.skipTest('pass --private-source-dir for pinned rebind/remap bodies')
        raw = (PRIVATE_SOURCE / 'MaterialExpressions.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'aabf83778c557f3e68ff9a8ee003443b42ae12262fb2e87b406244e91f763d27')
        header = (PRIVATE_SOURCE / 'MaterialExpressionMaterialFunctionCall.h').read_text(encoding='utf-8-sig')
        self.assertIn('ENGINE_API void UpdateFromFunctionResource(bool bRecreateAndLinkNode = true);', header)
        text = raw.decode('utf-8-sig')
        signatures = (
            'static const FFunctionExpressionInput* FindInputById(',
            'static const FFunctionExpressionInput* FindInputByName(',
            'static int32 FindOutputIndexById(', 'static int32 FindOutputIndexByName(',
            'static void FixupReferencingInputs(',
            'void UMaterialExpressionMaterialFunctionCall::FixupReferencingExpressions(',
            'void UMaterialExpressionMaterialFunctionCall::UpdateFromFunctionResource(',
            'bool UMaterialExpressionMaterialFunctionCall::SetMaterialFunction(')
        actual = '\n'.join(method(text, signature) for signature in signatures)
        stub = r'''
#include <cassert>
#include <vector>
#include <string>
#include <cstdio>
using int32=int; using FGuid=int; using FString=std::string;
#define WITH_EDITOR 1
#define check(x) assert(x)
#define NSLOCTEXT(...) 0
constexpr int INDEX_NONE=-1,MP_MAX=2;
using EMaterialProperty=int;
namespace EAppMsgType {enum Type {Ok};}
struct FMessageDialog {static void Open(EAppMsgType::Type,int){assert(false);}};
template<class T> struct TArray:std::vector<T> {using std::vector<T>::vector;
 int Num()const{return this->size();} void Empty(int=0){this->clear();}
 void Add(const T&x){this->push_back(x);} bool IsValidIndex(int i)const{return i>=0&&i<Num();}};
struct UMaterialExpression;
struct FExpressionInput {UMaterialExpression* Expression=nullptr;int OutputIndex=-1,Mask=0,MaskR=0,MaskG=0,MaskB=0,MaskA=0;FString InputName;};
struct FExpressionOutput {FString OutputName;};
struct UMaterialExpressionFunctionInput {FString InputName;};
struct UMaterialExpressionFunctionOutput {FString OutputName;};
struct FFunctionExpressionInput {UMaterialExpressionFunctionInput* ExpressionInput=nullptr;FGuid ExpressionInputId=0;FExpressionInput Input;};
struct FFunctionExpressionOutput {UMaterialExpressionFunctionOutput* ExpressionOutput=nullptr;FGuid ExpressionOutputId=0;FExpressionOutput Output;};
struct UMaterialExpression {virtual TArray<FExpressionInput*> GetInputs(){return {};}};
struct UMaterialGraphNode {void RecreateAndLinkNode(){assert(false);}};
template<class T>T* CastChecked(void*p){return static_cast<T*>(p);}
struct UMaterial {TArray<UMaterialExpression*> Expressions;FExpressionInput roots[MP_MAX];FExpressionInput* GetExpressionInputForProperty(int i){return &roots[i];}};
struct UMaterialFunction {TArray<UMaterialExpression*> FunctionExpressions;TArray<FFunctionExpressionInput> inputs;TArray<FFunctionExpressionOutput> outputs;
 bool IsDependent(UMaterialFunction*){return false;} void UpdateFromFunctionResource(){}
 void GetInputsAndOutputs(TArray<FFunctionExpressionInput>&i,TArray<FFunctionExpressionOutput>&o){i=inputs;o=outputs;}};
struct UMaterialExpressionMaterialFunctionCall:UMaterialExpression {
 TArray<FFunctionExpressionInput> FunctionInputs;TArray<FFunctionExpressionOutput> FunctionOutputs;TArray<FExpressionOutput> Outputs;
 UMaterialFunction* MaterialFunction=nullptr;UMaterialFunction* Function=nullptr;UMaterial* Material=nullptr;void* GraphNode=nullptr;
 TArray<FExpressionInput*> GetInputs()override{TArray<FExpressionInput*> result;for(auto&i:FunctionInputs)result.Add(&i.Input);return result;}
 void UpdateFromFunctionResource(bool=true);bool SetMaterialFunction(UMaterialFunction*,UMaterialFunction*,UMaterialFunction*);
 void FixupReferencingExpressions(const TArray<FFunctionExpressionOutput>&,const TArray<FFunctionExpressionOutput>&,TArray<UMaterialExpression*>&,TArray<FExpressionInput*>&,bool);
};
struct Consumer:UMaterialExpression {FExpressionInput input;TArray<FExpressionInput*> GetInputs()override{return {&input};}};
bool samePin(const FExpressionInput&a,const FExpressionInput&b){return a.Expression==b.Expression&&a.OutputIndex==b.OutputIndex&&a.Mask==b.Mask&&a.MaskR==b.MaskR&&a.MaskG==b.MaskG&&a.MaskB==b.MaskB&&a.MaskA==b.MaskA&&a.InputName==b.InputName;}
'''
        harness = r'''
int main(){for(bool materialOwner:{false,true}){
 UMaterialExpression upstream;UMaterialExpressionFunctionInput oldInput{"In"},newInput{"In"};
 UMaterialExpressionFunctionOutput old0{"Result"},old1{"WPO Only"},new0{"Result"},new1{"WPO Only"};
 UMaterialFunction original,clone,owner;UMaterial material;Consumer consumer;
 original.inputs={{&oldInput,10,{}}};original.inputs[0].Input.InputName="In";
 clone.inputs={{&newInput,10,{}}};clone.inputs[0].Input.InputName="In";
 original.outputs={{&old0,20,{"Result"}},{&old1,21,{"WPO Only"}}};
 clone.outputs={{&new0,20,{"Result"}},{&new1,21,{"WPO Only"}}};
 UMaterialExpressionMaterialFunctionCall call;call.MaterialFunction=&original;
 call.FunctionInputs=original.inputs;call.FunctionOutputs=original.outputs;
 call.FunctionInputs[0].ExpressionInput=nullptr;
 for(auto&o:call.FunctionOutputs)o.ExpressionOutput=nullptr;
 auto&pin=call.FunctionInputs[0].Input;pin.Expression=&upstream;pin.OutputIndex=3;pin.Mask=1;pin.MaskR=1;pin.MaskB=1;pin.MaskA=1;
 FExpressionInput before=pin;consumer.input.Expression=&call;consumer.input.OutputIndex=1;consumer.input.Mask=1;consumer.input.MaskG=1;
 FExpressionInput consumerBefore=consumer.input;
 if(materialOwner){call.Material=&material;material.Expressions={&call,&consumer};material.roots[0]=consumer.input;}
 else {call.Function=&owner;owner.FunctionExpressions={&call,&consumer};}
 call.UpdateFromFunctionResource(false);
 assert(call.MaterialFunction==&original&&call.FunctionInputs[0].ExpressionInput==&oldInput);
 assert(call.FunctionOutputs[0].ExpressionOutput==&old0&&call.FunctionOutputs[1].ExpressionOutput==&old1);
 assert(call.FunctionInputs[0].ExpressionInputId==10&&call.FunctionOutputs[1].ExpressionOutputId==21);
 assert(samePin(before,call.FunctionInputs[0].Input)&&samePin(consumerBefore,consumer.input));
 assert(call.SetMaterialFunction(materialOwner?nullptr:&owner,&original,&clone));
 assert(call.MaterialFunction==&clone&&call.FunctionInputs[0].ExpressionInput==&newInput);
 assert(call.FunctionOutputs[1].ExpressionOutput==&new1);
 assert(samePin(before,call.FunctionInputs[0].Input)&&samePin(consumerBefore,consumer.input));
 if(materialOwner)assert(samePin(consumerBefore,material.roots[0]));
 // Missing GUIDs really can break connections: the repair must retain its strict snapshot/graph gates.
 call.FunctionOutputs[1].ExpressionOutputId=999;
 call.UpdateFromFunctionResource(false);
 assert(consumer.input.Expression==nullptr&&consumer.input.OutputIndex==INDEX_NONE);
 }
 puts("actual GUID rebind/name remap preserves pins; missing GUID rejected by structural boundary");}
'''
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as tmp:
            source, exe = Path(tmp) / 'rebind.cpp', Path(tmp) / 'rebind'
            source.write_text(stub + actual + harness)
            result = subprocess.run([compiler, '-std=c++14', str(source), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('actual GUID rebind', result.stdout)

    def test_actual_set_and_feature_compile_demand(self):
        if PRIVATE_SOURCE is None:
            self.skipTest('pass --private-source-dir for pinned private methods')
        raw = (PRIVATE_SOURCE / 'MaterialExpressions.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'aabf83778c557f3e68ff9a8ee003443b42ae12262fb2e87b406244e91f763d27')
        text = raw.decode('utf-8-sig')
        methods = '\n'.join(method(text, 'int32 ' + cls + '::Compile(') for cls in
                            ('UMaterialExpressionSetMaterialAttributes', 'UMaterialExpressionFeatureLevelSwitch',
                             'UMaterialExpressionTextureCoordinate', 'UMaterialExpressionBlendMaterialAttributes'))
        self.assertEqual(hashlib.sha256((PRIVATE_SOURCE / 'MaterialExpressionTextureCoordinate.h').read_bytes()).hexdigest(),
                         '43058ea161365402f089e66747fd44134a911a89a9a644d38b7e6f66be3f51da')
        stub = r'''
#include <cassert>
#include <functional>
#include <vector>
#include <cstdio>
#include <cmath>
using int32=int; using FGuid=int; using EMaterialValueType=int;
#define TEXT(x) x
#define check(x) assert(x)
#define checkf(x,...) assert(x)
#define ARRAY_COUNT(x) (sizeof(x)/sizeof((x)[0]))
constexpr int MP_MAX=99;
constexpr float SMALL_NUMBER=0.00001f;
struct FMath {static float Abs(float x){return std::fabs(x);}};
enum EShaderFrequency {SF_Vertex,SF_Hull,SF_Domain,SF_Pixel};
namespace EMaterialAttributeBlend {enum Type {Blend,UseA,UseB};}
namespace ERHIFeatureLevel {enum Type {ES2,ES3_1,SM4,SM5,Num};}
struct FMaterialCompiler {int attribute=0; ERHIFeatureLevel::Type feature=ERHIFeatureLevel::ES2;
 int GetMaterialAttribute(){return attribute;} auto GetFeatureLevel(){return feature;}
 int Errorf(const char*,...){return -123;} int ValidCast(int x,int){return x;}
 int TextureCoordinate(int i,bool u,bool v){assert(i==0&&!u&&!v);return 37;}
 int Constant(float v){assert(v==1);return 1;} int Constant2(float,float){assert(false);return 0;}
 int Mul(int x,int y){return x*y;} int Lerp(int x,int y,int a){return x+a*(y-x);}};
using MaterialAttributeBlendFunction=int(*)(FMaterialCompiler*,int,int,int);
struct FMaterialAttributeDefinitionMap {static int GetProperty(int x){return x;} static int GetValueType(int){return 0;}
 static EShaderFrequency GetShaderFrequency(int){return SF_Vertex;}
 static MaterialAttributeBlendFunction GetBlendFunction(int){return nullptr;}};
template<class T> struct TArray:std::vector<T> {using std::vector<T>::vector; int Num()const{return this->size();}
 bool Find(T x,int&i){for(i=0;i<Num();++i)if((*this)[i]==x)return true;return false;}};
struct Expr {std::function<int(FMaterialCompiler*,int)> evaluate;};
struct FExpressionInput {Expr* Expression=nullptr; int OutputIndex=0;
 int Compile(FMaterialCompiler*c){assert(Expression);return Expression->evaluate(c,OutputIndex);}
 int CompileWithDefault(FMaterialCompiler*c,int){return Compile(c);}};
struct UMaterialExpressionSetMaterialAttributes {TArray<int> AttributeSetTypes;TArray<FExpressionInput> Inputs;int Compile(FMaterialCompiler*,int);};
struct UMaterialExpressionFeatureLevelSwitch {FExpressionInput Default,Inputs[ERHIFeatureLevel::Num];int Compile(FMaterialCompiler*,int);};
struct UMaterialExpressionTextureCoordinate {int CoordinateIndex=0;bool UnMirrorU=false,UnMirrorV=false;
 float UTiling=1,VTiling=1;int Compile(FMaterialCompiler*,int);};
struct UMaterialExpressionBlendMaterialAttributes {FExpressionInput A,B,Alpha;
 EMaterialAttributeBlend::Type VertexAttributeBlendType=EMaterialAttributeBlend::Blend,PixelAttributeBlendType=EMaterialAttributeBlend::Blend;
 int Compile(FMaterialCompiler*,int);};
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
 // Actual TextureCoordinate Compile: unit tiling and no unmirror return UV0.
 UMaterialExpressionTextureCoordinate tc;int uvCalls=0;
 Expr uv{[&](auto*c,int i){++uvCalls;return tc.Compile(c,i);}};
 set.AttributeSetTypes={0,2};set.Inputs={{&original,0},{&function,1},{&uv,0}};
 c.feature=ERHIFeatureLevel::ES2;c.attribute=2;int before=originalCalls;
 assert(feature.Compile(&c,0)==37&&originalCalls==before&&uvCalls==1);
 // WPO/current-or-previous share the same requested attribute; remain output1.
 c.attribute=0;assert(feature.Compile(&c,0)==73&&wpoCalls==2);
 c.attribute=1;assert(feature.Compile(&c,0)==42);
 c.attribute=3;assert(feature.Compile(&c,0)==42); // no blanket UV-channel override
 for(int f=1;f<4;++f){c.feature=(ERHIFeatureLevel::Type)f;c.attribute=2;
 assert(feature.Compile(&c,0)==42&&uvCalls==1);}
 // Pinned Blend Compile evaluates alpha even when both UV inputs are identical.
 int operands=0,alphaCalls=0,alpha=0;
 Expr operand{[&](auto*,int){++operands;return 37;}};
 Expr mask{[&](auto*,int){++alphaCalls;return alpha;}};
 UMaterialExpressionBlendMaterialAttributes blend;blend.A={&operand,0};blend.B={&operand,0};blend.Alpha={&mask,0};
 for(int a : {-1000,-1,0,1,1000}){alpha=a;assert(blend.Compile(&c,0)==37);}
 assert(operands==10&&alphaCalls==5);
 int aoCalls=0;Expr ao{[&](auto*,int){++aoCalls;return 19;}};Expr zero{[](auto*,int){return 0;}};
 UMaterialExpressionFeatureLevelSwitch aof;aof.Default={&ao,0};aof.Inputs[0]={&zero,0};c.feature=ERHIFeatureLevel::ES2;
 assert(aof.Compile(&c,0)==0&&aoCalls==0);c.feature=ERHIFeatureLevel::SM5;assert(aof.Compile(&c,0)==19&&aoCalls==1);
 aof.Default.Expression=nullptr;assert(aof.Compile(&c,0)==-123);
 set.AttributeSetTypes={0,0};assert(set.Compile(&c,0)==-123);
 puts("actual Set/Feature/TextureCoordinate/Blend Compile demand checks PASS");
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
