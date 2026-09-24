"""Disposable publication tests and compiled guard matrix; no engine execution.

--private-source is the exact captured UTPlayerState.cpp, never bundled here.
The compiled test uses the transformed guard with instrumented continuation;
it does not pretend to compile UE's complete writer or HTTP implementation.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
LOADER = importlib.util.spec_from_file_location('cloud_stats_patch', HERE / 'patch-browser-cloud-stats.py')
patcher = importlib.util.module_from_spec(LOADER)
LOADER.loader.exec_module(patcher)
PRIVATE = None
RAW = (b'// Original synthetic fixture, not UE implementation.\n'
       + patcher.ANCHOR.encode() + b'    fixture_continuation();\n}\n')
FIXED = RAW.replace(patcher.ANCHOR.encode(), (patcher.ANCHOR + patcher.GUARD).encode())
SPEC = ('writer.cpp', patcher.sha(RAW), len(RAW), patcher.sha(FIXED))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'Engine/Build').mkdir(parents=True)
        (self.root / '.tournament-browser-port').write_text('disposable fixture')
        self.version = self.root / 'Engine/Build/Build.version'
        self.version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15,
                                               PatchVersion=0, Changelist=3228288)))
        self.source = self.root / SPEC[0]
        self.source.write_bytes(RAW)
        self.backup = Path(str(self.source) + patcher.BACKUP)

    def run_patch(self, apply=False):
        return patcher.patch(self.root, apply, (SPEC,))

    def test_readonly_apply_exact_backup_idempotence(self):
        before = sorted(self.root.rglob('*'))
        result = self.run_patch()
        self.assertFalse(result['apply'])
        self.assertTrue(result['requiresExplicitNoMCP'])
        self.assertFalse(result['files'][0]['alreadyPatched'])
        self.assertEqual(self.source.read_bytes(), RAW)
        self.assertEqual(before, sorted(self.root.rglob('*')))
        self.run_patch(True)
        self.assertEqual(self.backup.read_bytes(), RAW)
        self.assertEqual(self.source.read_bytes(), FIXED)
        with mock.patch.object(patcher.os, 'replace', side_effect=AssertionError('unexpected rewrite')):
            self.assertTrue(self.run_patch(True)['files'][0]['alreadyPatched'])

    def test_exact_source_and_guard_pins_reject_drift(self):
        for bad in (RAW + b' ', RAW.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + RAW,
                    FIXED.replace(b'NoMCP', b'Other'), FIXED + b' ',
                    FIXED.replace(patcher.GUARD.encode(), b'', 1) + b'// unrelated'):
            with self.subTest(bad=hashlib.sha256(bad).hexdigest()):
                with self.assertRaises(ValueError): patcher.transform(bad, SPEC)
        self.assertEqual(patcher.inverse(FIXED, SPEC), RAW)
        self.assertEqual(patcher.transform(FIXED, SPEC), FIXED)
        with self.assertRaises(ValueError): patcher.inverse(RAW, SPEC)
        self.source.write_bytes(b'unknown')
        with self.assertRaises(ValueError): self.run_patch(True)
        self.assertFalse(self.backup.exists())

    def test_fixed_production_schema_rejects_synthetic_without_test_spec(self):
        with self.assertRaises(ValueError): patcher.transform(RAW)
        self.assertEqual(len(patcher.SPECS), 1)
        self.assertEqual(patcher.SPECS[0][2], 117366)
        self.assertEqual(patcher.SPECS[0][0],
                         'UnrealTournament/Source/UnrealTournament/Private/UTPlayerState.cpp')

    def test_missing_wrong_or_guarded_backup_refused(self):
        self.source.write_bytes(FIXED)
        for bad in (None, b'wrong', FIXED):
            if self.backup.exists(): self.backup.unlink()
            if bad is not None: self.backup.write_bytes(bad)
            with self.assertRaises(ValueError): self.run_patch(True)
            self.assertEqual(self.source.read_bytes(), FIXED)

    def test_marker_version_and_reparse_required(self):
        self.version.write_text('{}')
        with self.assertRaises(ValueError): self.run_patch(True)
        (self.root / '.tournament-browser-port').unlink()
        with self.assertRaises(ValueError): self.run_patch(True)
        real = Path.lstat
        class Reparse:
            st_mode = 0o040755
            st_file_attributes = 0x400
        def replacement(path, *a, **kw):
            return Reparse() if path == self.root else real(path, *a, **kw)
        with mock.patch.object(Path, 'lstat', replacement):
            with self.assertRaisesRegex(ValueError, 'reparse'): patcher.physical(self.source)

    def test_hardlinked_source_and_backup_refused(self):
        alias = self.root / 'alias'
        os.link(self.source, alias)
        with self.assertRaises(ValueError): self.run_patch(True)
        alias.unlink()
        os.link(self.source, self.backup)
        with self.assertRaises(ValueError): self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), RAW)

    def test_readonly_rechecks_inputs(self):
        original = patcher.recheck
        def mutate(saved):
            if saved['path'] == self.source: self.source.write_bytes(b'drift')
            original(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=mutate):
            with self.assertRaises(ValueError): self.run_patch()
        self.assertFalse(self.backup.exists())

    def test_drift_before_backup_preserved(self):
        original = patcher.recheck
        def mutate(saved):
            if saved['path'] == self.source: self.source.write_bytes(b'external change')
            original(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=mutate):
            with self.assertRaises(ValueError): self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), b'external change')
        self.assertFalse(self.backup.exists())

    def test_backup_drift_blocks_install(self):
        original = patcher.recheck
        def mutate(saved):
            if self.backup.exists(): self.backup.write_bytes(b'corrupt')
            original(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=mutate):
            with self.assertRaises(ValueError): self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), RAW)

    def test_backup_flush_failure_retryable(self):
        with mock.patch.object(patcher.os, 'fsync', side_effect=OSError('injected flush failure')):
            with self.assertRaises(OSError): self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), RAW)
        self.assertFalse(self.backup.exists())
        self.assertFalse(list(self.root.glob('.cloud-stats-*')))
        self.run_patch(True)

    def test_exclusive_backup_does_not_overwrite(self):
        link = patcher.os.link
        def collide(src, dst):
            Path(dst).write_bytes(b'other evidence')
            link(src, dst)
        with mock.patch.object(patcher.os, 'link', side_effect=collide):
            with self.assertRaises(FileExistsError): self.run_patch(True)
        self.assertEqual(self.backup.read_bytes(), b'other evidence')
        self.assertEqual(self.source.read_bytes(), RAW)

    def test_backup_precedes_replace_and_failed_install_retryable(self):
        def stop(src, dst):
            self.assertEqual(self.backup.read_bytes(), RAW)
            self.assertEqual(Path(src).read_bytes(), FIXED)
            raise OSError('injected replace failure')
        with mock.patch.object(patcher.os, 'replace', side_effect=stop):
            with self.assertRaises(OSError): self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), RAW)
        self.assertFalse(list(self.root.glob('.cloud-stats-*')))
        self.run_patch(True)


def compiled_matrix(case, guard):
    cxx = shutil.which('clang++') or shutil.which('g++')
    if not cxx: case.fail('Host C++ compiler required for guard matrix')
    code = ['#include <cassert>', '#include <cstring>', '#define TEXT(x) x',
            'static bool noMcp; static int parses,requests,callbacks; static bool wrote;',
            'struct FCommandLine {static const char* Get(){return "fixture";}};',
            'struct FParse {static bool Param(const char*,const char* key){',
            'assert(std::strcmp(key,"NoMCP")==0); ++parses; return noMcp;}};']
    for index, browser in enumerate((None, 0, 1)):
        code.append('#undef PLATFORM_HTML5_BROWSER')
        if browser is not None: code.append('#define PLATFORM_HTML5_BROWSER %d' % browser)
        code += ['void run%d(){' % index, guard,
                 '// Instrumented continuation, not the UE HTTP implementation.',
                 '++requests; ++callbacks; wrote=true;', '}']
    code += ['int main(){']
    for index, browser in enumerate((None, 0, 1)):
        for no_mcp in (False, True):
            for initial_wrote in (False, True):
                skipped = browser == 1 and no_mcp
                code += ['noMcp=%d; parses=requests=callbacks=0; wrote=%d; run%d();' %
                         (no_mcp, initial_wrote, index),
                         'assert(parses==%d && requests==%d && callbacks==%d && wrote==%d);' %
                         (browser == 1, not skipped, not skipped,
                          initial_wrote if skipped else True)]
    code += ['}']
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'guard.cpp'
        binary = Path(folder) / ('guard.exe' if os.name == 'nt' else 'guard')
        source.write_text('\n'.join(code))
        result = subprocess.run([cxx, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                                 str(source), '-o', str(binary)], capture_output=True, text=True)
        case.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        case.assertEqual(result.returncode, 0, result.stderr)


class GuardTests(unittest.TestCase):
    def test_compiled_guard_matrix_no_fake_success(self):
        fixed = patcher.transform(RAW, SPEC)
        guard = fixed[len(RAW.split(patcher.ANCHOR.encode())[0]) + len(patcher.ANCHOR):]
        guard = guard[:len(patcher.GUARD)].decode()
        self.assertEqual(guard, patcher.GUARD)
        compiled_matrix(self, guard)

    def test_private_complete_source_inverse_and_actual_guard(self):
        if PRIVATE is None: self.skipTest('Pass --private-source with pinned UTPlayerState.cpp')
        raw = PRIVATE.read_bytes()
        self.assertEqual(len(raw), patcher.SPECS[0][2])
        self.assertEqual(patcher.sha(raw), patcher.SPECS[0][1])
        fixed = patcher.transform(raw)
        self.assertEqual(patcher.inverse(fixed), raw)
        self.assertEqual(patcher.transform(fixed), fixed)
        offset = raw.index(patcher.ANCHOR.encode()) + len(patcher.ANCHOR)
        self.assertEqual(fixed[:offset], raw[:offset])
        self.assertEqual(fixed[offset + len(patcher.GUARD):], raw[offset:])
        compiled_matrix(self, fixed[offset:offset + len(patcher.GUARD)].decode())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-source', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE = args.private_source
    unittest.main(argv=[__file__] + rest)
