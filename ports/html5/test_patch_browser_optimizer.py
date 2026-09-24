"""Original safety/semantics fixtures; all writes are inside temporary directories.

python3 -B test_patch_browser_optimizer.py [--private-source-dir PRIVATE_DIRECTORY]
The optional directory contains pinned original optimizer.cpp/js-optimizer.js;
these files are read only. Actual-rule checks explicitly skip without it.
No SDK invocation, native build, network, source installation, or licensed fixture.
Node is needed for the source-extracted JS predicate regression.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
MODULE = importlib.util.spec_from_file_location('optimizer_patch', Path(__file__).with_name('patch-browser-optimizer.py'))
P = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(P)
PRIVATE = os.environ.get('UT4_OPTIMIZER_PRIVATE_SOURCE_DIR')


def synthetic_specs():
    specs, sources = [], []
    for spec in P.SPECS:
        # Original inert source: exercises insertion and filesystem policy only.
        data = b'// synthetic fixture\r\n    if (eligible) {\r\n        observe();\r\n    }\r\n'
        fixed = data.replace(b'if (', b'if (' + spec['guard'])
        specs.append({**spec, 'line': 2, 'before': P.digest(data), 'after': P.digest(fixed)})
        sources.append(data)
    return tuple(specs), sources


class SafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ut4-optimizer-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        specs, sources = synthetic_specs()
        self.mock = mock.patch.object(P, 'SPECS', specs)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        (self.root / '.tournament-browser-port').touch()
        version = self.root / 'Engine/Build/Build.version'
        version.parent.mkdir(parents=True)
        version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        for spec, data in zip(specs, sources):
            file = self.root / spec['path']
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        (self.root / P.SDK / 'emscripten-version.txt').write_text('"1.36.13"\r\n')

    def patch(self, apply=True, root=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.patch(root or self.root, apply)

    def source(self, index=0):
        return self.root / P.SPECS[index]['path']

    def backup(self, index=0):
        return Path(str(self.source(index)) + P.BACKUP_SUFFIX)

    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, root=None):
        before = self.snapshot()
        with self.assertRaises((ValueError, OSError)):
            self.patch(root=root)
        self.assertEqual(before, self.snapshot())

    def test_default_preflight_writes_nothing(self):
        before = self.snapshot()
        self.assertEqual(self.patch(False)['status'], 'would-patch')
        self.assertEqual(before, self.snapshot())

    def test_both_apply_exact_backups_and_idempotent(self):
        original = [self.source(i).read_bytes() for i in range(2)]
        result = self.patch()
        self.assertEqual(result['status'], 'patched')
        self.assertFalse(result['nativeExecutableRebuilt'])
        for i, spec in enumerate(P.SPECS):
            self.assertEqual(self.backup(i).read_bytes(), original[i])
            self.assertEqual(P.digest(self.source(i).read_bytes()), spec['after'])
            self.assertEqual(self.source(i).read_bytes().count(b'\r\n'), original[i].count(b'\r\n'))
        before = self.snapshot()
        times = [self.source(i).stat().st_mtime_ns for i in range(2)]
        self.assertEqual(self.patch()['status'], 'already-patched')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(times, [self.source(i).stat().st_mtime_ns for i in range(2)])

    def test_bad_second_file_blocks_first_and_all_backups(self):
        self.source(1).write_bytes(self.source(1).read_bytes() + b'changed')
        self.reject()
        self.assertFalse(self.backup().exists())

    def test_backup_conflict_blocks_both(self):
        self.backup(1).write_bytes(b'wrong original')
        self.reject()
        self.assertFalse(self.backup().exists())

    def test_matching_backup_reused(self):
        self.backup().write_bytes(self.source().read_bytes())
        timestamp = self.backup().stat().st_mtime_ns
        self.patch()
        self.assertEqual(timestamp, self.backup().stat().st_mtime_ns)

    def test_missing_or_altered_backup_after_apply_rejected(self):
        self.patch()
        saved = self.backup().read_bytes()
        self.backup().unlink()
        self.reject()
        self.backup().write_bytes(saved + b'altered')
        self.reject()

    def test_recover_interrupted_pair_with_valid_backup(self):
        original = self.source().read_bytes()
        self.backup().write_bytes(original)
        self.source().write_bytes(P.transform(original, P.SPECS[0]))
        self.assertEqual(self.patch()['status'], 'patched')
        self.assertEqual(self.patch()['status'], 'already-patched')

    def test_marker_engine_and_sdk_versions(self):
        marker = self.root / '.tournament-browser-port'
        marker.unlink()
        self.reject()
        marker.touch()
        version = self.root / 'Engine/Build/Build.version'
        original = version.read_bytes()
        for field in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist'):
            data = json.loads(original)
            data[field] += 1
            version.write_text(json.dumps(data))
            self.reject()
        version.write_bytes(original)
        (self.root / P.SDK / 'emscripten-version.txt').write_text('1.36.14')
        self.reject()

    def test_hardlinked_source_and_backup_rejected(self):
        alias = self.root / 'alias'
        os.link(self.source(), alias)
        self.reject()
        alias.unlink()
        self.backup().write_bytes(self.source().read_bytes())
        os.link(self.backup(), alias)
        self.reject()

    def test_symlink_source_backup_and_ancestor_rejected(self):
        source = self.source()
        saved = source.read_bytes()
        alias = self.root / 'alias'
        alias.write_bytes(saved)
        source.unlink()
        source.symlink_to(alias)
        self.reject()
        source.unlink()
        source.write_bytes(saved)
        self.backup().symlink_to(alias)
        self.reject()
        self.backup().unlink()
        link = self.root / 'linked-root'
        link.symlink_to(self.root, target_is_directory=True)
        self.reject(root=link)

    def test_reparse_attribute_rejected(self):
        original = Path.lstat
        def inspect(path):
            info = original(path)
            if path == self.source():
                return type('Info', (), dict(st_mode=info.st_mode, st_nlink=1, st_file_attributes=0x400))()
            return info
        with mock.patch.object(Path, 'lstat', inspect):
            with self.assertRaisesRegex(ValueError, 'reparse'):
                P.physical(self.source())

    def test_source_race_rejected_before_replace(self):
        item = P.inspect(self.root, P.SPECS[0])
        self.source().write_bytes(b'concurrent change')
        with self.assertRaisesRegex(ValueError, 'changed'):
            P.replace(item)
        self.assertFalse(self.backup().exists())

    def test_modified_patch_and_source_newlines_rejected(self):
        data = self.source().read_bytes()
        for changed in (data.replace(b'\r\n', b'\n'), P.transform(data, P.SPECS[0])+b'changed'):
            with self.assertRaises(ValueError):
                P.transform(changed, P.SPECS[0])


@unittest.skipUnless(PRIVATE, 'provide --private-source-dir for pinned actual-rule tests')
class ActualSourceTests(unittest.TestCase):
    def test_pinned_both_outputs_inverse_and_outside_bytes(self):
        for spec in P.SPECS:
            data = (Path(PRIVATE) / spec['path'].name).read_bytes()
            fixed = P.transform(data, spec)
            self.assertEqual(P.digest(fixed), spec['after'])
            self.assertEqual(fixed.replace(b'if ('+spec['guard'], b'if (', 1), data)
            self.assertEqual(P.transform(fixed, spec), fixed)

    def test_actual_js_rule_operands_and_effects(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node required for actual-rule evaluation')
        spec = P.SPECS[1]
        before = (Path(PRIVATE) / spec['path'].name).read_bytes()
        after = P.transform(before, spec)
        def block(data):
            text = data.decode()
            marker = text.index('// if a seq ends in an |0, remove an external |0')
            start = text.rfind('var value = node[3];', 0, marker)
            open_brace = text.index('{', start)
            depth = 1
            end = open_brace + 1
            while depth:
                depth += (text[end] == '{') - (text[end] == '}')
                end += 1
            return text[start:end]
        # Original evaluator and AST inputs. Only the optimizer rule is extracted.
        harness = r'''
const assert=require('assert/strict'),fs=require('fs');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const ops=Object.fromEntries(['<<','>>','|','&','^'].map(x=>[x,1]));
const original=new Function('node','USEFUL_BINARY_OPS',input.before);
const fixed=new Function('node','USEFUL_BINARY_OPS',input.after);
const N=x=>['num',x],seq=()=>['seq',N(0),['binary','|',N(1),N(0)]];
function evalNode(n,c){switch(n[0]){case'num':return n[1];case'name':return c[n[1]];case'call':c.calls++;return 2;case'seq':evalNode(n[1],c);return evalNode(n[2],c);case'binary':{const a=evalNode(n[2],c),b=evalNode(n[3],c);return n[1]==='|'?a|b:a&b;}default:throw Error(n[0]);}}
let count=0;
for(const [label,left,right,reduce] of [
 ['rightZero',seq(),N(0),true],['negativeZero',seq(),N(-0),true],
 ['leftZero',N(0),seq(),true],['leftNegativeZero',N(-0),seq(),true],
 ['positiveLiteral',seq(),N(2),false],['negativeLiteral',seq(),N(-1),false],
 ['dynamicPositive',seq(),['name','positive'],false],['dynamicNegative',seq(),['name','negative'],false],
 ['dynamicSignMask',seq(),['binary','&',['name','negative'],N(-2147483648)],false],
 ['rhsCall',seq(),['call'],false]]){
 const ast=['assign',true,['name','result'],['binary','|',left,right]];
 const a=structuredClone(ast),b=structuredClone(ast);
 const c={calls:0,positive:2,negative:-2147483648},d={...c},e={...c};
 const expected=evalNode(ast[3],c);original(a,ops);fixed(b,ops);
 const broken=evalNode(a[3],d),actual=evalNode(b[3],e);
 assert.equal(actual,expected,label);assert.equal(e.calls,c.calls,label);
 assert.equal(b[3][0]==='seq',reduce,label);
 if(!reduce)assert.notEqual(broken,expected,label);
 count++;
}
console.log('PASS '+count+' actual-rule operand/effect cases');
'''
        with tempfile.TemporaryDirectory(prefix='ut4-or-rule-') as temp:
            root = Path(temp)
            (root/'input.json').write_text(json.dumps(dict(before=block(before), after=block(after))))
            (root/'run.cjs').write_text(harness)
            result = subprocess.run([node, str(root/'run.cjs'), str(root/'input.json')], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS 10', result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-source-dir')
    args, remaining = parser.parse_known_args()
    if args.private_source_dir:
        PRIVATE = args.private_source_dir
        ActualSourceTests.__unittest_skip__ = False
    unittest.main(argv=[sys.argv[0], *remaining])
