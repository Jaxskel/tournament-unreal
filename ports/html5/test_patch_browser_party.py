"""Original synthetic tests; all patch writes and native stub builds use tempdirs.

Run: python3 -B ports/html5/test_patch_browser_party.py
No licensed source, editor, engine build, network, or Windows process is used.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

PATCHER = runpy.run_path(str(Path(__file__).with_name('patch-browser-party.py')))
# Small independently constructed callback-contract fixture and instrumented stubs.
CALLBACK = '''void UParty::OnPostLoadMap()
{
  // Synthetic callback contract; the braces in this comment are inert: }
  if (!HasAnyFlags(RF_ClassDefaultObject)) {
    RegisterIdentityDelegates();
    RegisterPartyDelegates();
  }
}
'''
SOURCE = CALLBACK + '''void UParty::RegisterIdentityDelegates() {
  auto World = GetWorld();
  if (ensure(World)) { ++identityCalls; }
}
void UParty::RegisterPartyDelegates() {
  auto World = GetWorld();
  if (ensure(World)) { ++partyCalls; }
}
void OtherCallback() { check(true); }
'''
HARNESS = r'''
#include <cassert>
static int worldChecks = 0;
static int diagnostics = 0;
#define RF_ClassDefaultObject 1
#define ensure(x) (++worldChecks, assert(x), bool(x))
#define check(x) assert(x)
#define TEXT(x) x
#define UE_LOG(...) (++diagnostics)
class UParty {
public:
  bool cdo = false;
  int* world = nullptr;
  int identityCalls = 0, partyCalls = 0;
  bool HasAnyFlags(int) const { return cdo; }
  int* GetWorld() const { return world; }
  void OnPostLoadMap();
  void RegisterIdentityDelegates();
  void RegisterPartyDelegates();
};
'''
MAIN = r'''
int main() {
  UParty p;
  p.cdo = true;
  p.OnPostLoadMap();
  assert(diagnostics == 0 && worldChecks == 0);
  p.cdo = false;
  p.OnPostLoadMap();
  assert(diagnostics == 1 && worldChecks == 0);
  assert(p.identityCalls == 0 && p.partyCalls == 0);
  int world = 1;
  p.world = &world;
  p.OnPostLoadMap();
  assert(worldChecks == 2 && p.identityCalls == 1 && p.partyCalls == 1);
  p.world = nullptr;
  p.OnPostLoadMap();
  assert(diagnostics == 2 && worldChecks == 2);
  p.world = &world;
  p.OnPostLoadMap();
  assert(worldChecks == 4 && p.identityCalls == 2 && p.partyCalls == 2);
}
'''


class PartyPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ut4-party-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.tournament-browser-port').touch()
        self.version = self.root / 'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.source = self.root / PATCHER['SOURCE_PATH']
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'\xef\xbb\xbf' + SOURCE.replace('\n', '\r\n').encode())
        self.backup = Path(str(self.source) + PATCHER['BACKUP_SUFFIX'])

    def run_patch(self, apply=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return PATCHER['patch'](self.root, apply)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.run_patch()
        self.assertEqual(before, self.snapshot())

    def test_default_check_is_read_only(self):
        before = self.snapshot()
        self.assertEqual(self.run_patch(False)['status'], 'would-patch')
        self.assertEqual(before, self.snapshot())

    def test_exact_insertion_backup_encoding_and_asserts_preserved(self):
        original = self.source.read_bytes()
        self.run_patch()
        insertion = ''.join('    ' + line + '\r\n' for line in PATCHER['INSERT'].splitlines()).encode()
        expected = original.replace(b'    RegisterIdentityDelegates();', insertion + b'    RegisterIdentityDelegates();', 1)
        self.assertEqual(self.source.read_bytes(), expected)
        self.assertEqual(self.backup.read_bytes(), original)
        self.assertEqual(expected.count(b'ensure(World)'), 2)
        self.assertEqual(expected.count(b'check(true)'), 1)

    def test_repeat_apply_preserves_contents_and_timestamps(self):
        self.run_patch()
        before = self.snapshot()
        stamps = [p.stat().st_mtime_ns for p in (self.source, self.backup)]
        self.assertEqual(self.run_patch()['status'], 'already-patched')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(stamps, [p.stat().st_mtime_ns for p in (self.source, self.backup)])

    def test_unmarked_or_wrong_revision_rejected(self):
        marker = self.root / '.tournament-browser-port'
        marker.unlink()
        self.reject()
        marker.touch()
        correct = json.loads(self.version.read_text())
        for key in correct:
            with self.subTest(key=key):
                self.version.write_text(json.dumps({**correct, key: correct[key] + 1}))
                self.reject()

    def test_unknown_duplicate_commented_or_reordered_callback_rejected(self):
        variants = [SOURCE + CALLBACK, SOURCE.replace('!HasAnyFlags', 'HasAnyFlags'),
                    SOURCE.replace('    RegisterPartyDelegates();', '    // RegisterPartyDelegates();'),
                    SOURCE.replace('    RegisterIdentityDelegates();', '    check(true);\n    RegisterIdentityDelegates();'),
                    SOURCE.replace('ensure(World)', 'true', 1)]
        for variant in variants:
            with self.subTest(variant=variant):
                self.source.write_text(variant)
                self.reject()

    def test_partial_or_misplaced_marker_rejected(self):
        patched = PATCHER['transform'](SOURCE)
        insertion = ''.join('    ' + line + '\n' for line in PATCHER['INSERT'].splitlines())
        variants = [patched.replace('GetWorld() == nullptr', 'GetWorld() != nullptr'),
                    patched.replace('    return;\n', ''), SOURCE + '// ' + PATCHER['MARKER'],
                    patched.replace(insertion, '').replace('    RegisterPartyDelegates();', insertion + '    RegisterPartyDelegates();')]
        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError):
                    PATCHER['transform'](variant)

    def test_conflicting_backup_and_missing_patched_backup_rejected(self):
        self.backup.write_bytes(b'private unrelated backup')
        self.reject()
        self.backup.unlink()
        self.run_patch()
        self.backup.unlink()
        self.reject()

    def test_matching_backup_not_rewritten(self):
        self.backup.write_bytes(self.source.read_bytes())
        stamp = self.backup.stat().st_mtime_ns
        self.run_patch()
        self.assertEqual(stamp, self.backup.stat().st_mtime_ns)

    def test_hardlinked_source_and_backup_rejected(self):
        alias = self.root / 'synthetic-alias'
        os.link(self.source, alias)
        self.reject()
        alias.unlink()
        self.backup.write_bytes(self.source.read_bytes())
        os.link(self.backup, alias)
        self.reject()

    def test_symlink_source_and_ancestor_rejected(self):
        saved = self.source.with_name('synthetic-source')
        self.source.rename(saved)
        self.source.symlink_to(saved)
        self.reject()
        self.source.unlink()
        saved.rename(self.source)
        parent = self.source.parent
        moved = parent.with_name('synthetic-private')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        self.reject()

    def test_patched_callback_executes_null_world_cdo_and_recovery_paths(self):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('A local C++ compiler is needed for the synthetic callback probe')
        fixture = self.root / 'callback-probe.cpp'
        binary = self.root / 'callback-probe'
        fixture.write_text(HARNESS + PATCHER['transform'](SOURCE) + MAIN)
        built = subprocess.run([compiler, '-std=c++11', str(fixture), '-o', str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(built.returncode, 0, built.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
