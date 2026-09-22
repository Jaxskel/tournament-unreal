"""Temporary-filesystem checks; optional host compilation of pinned private source."""
import argparse
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('analytics_patch', HERE / 'patch-browser-analytics.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)
PRIVATE = None
ORIGINALS = (
    ('engine.cpp', (patcher.ENGINE_IF + '\nold branch\n#endif\n').encode(), 'engine'),
    ('game.cpp', ('void Initialize()\n{\n' + patcher.UT_START + '\n\t{ create(); }\n'
                  '\tLoginStatusChanged();\n' + patcher.UT_END + '\n}\n').encode(), 'game'),
)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'Engine/Build').mkdir(parents=True)
        (self.root / '.tournament-browser-port').write_text('test isolation marker')
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(dict(
            MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.specs = tuple((name, patcher.sha(raw), kind) for name, raw, kind in ORIGINALS)
        for name, raw, _ in ORIGINALS:
            (self.root / name).write_bytes(raw)

    def run_patch(self, apply=False):
        return patcher.patch(self.root, apply, self.specs)

    def assert_original(self):
        for name, raw, _ in ORIGINALS:
            self.assertEqual((self.root / name).read_bytes(), raw)

    def test_readonly_then_apply_idempotent_with_exact_backups(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        result = self.run_patch()
        self.assertTrue(result['requiresFreshBuild'])
        self.assertTrue(all(not r['alreadyPatched'] for r in result['files']))
        self.assert_original()
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))
        self.run_patch(True)
        after = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.run_patch(True)
        self.assertEqual(after, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        for name, raw, _ in ORIGINALS:
            self.assertEqual((self.root / (name + patcher.BACKUP)).read_bytes(), raw)

    def test_all_source_preflight_before_backups(self):
        (self.root / 'game.cpp').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.run_patch(True)
        self.assertFalse(list(self.root.glob('*' + patcher.BACKUP)))
        self.assertEqual((self.root / 'engine.cpp').read_bytes(), ORIGINALS[0][1])

    def test_missing_or_wrong_original_backup_refused(self):
        self.run_patch(True)
        backup = self.root / ('game.cpp' + patcher.BACKUP)
        backup.unlink()
        with self.assertRaises(ValueError): self.run_patch(True)
        backup.write_bytes(b'wrong original')
        with self.assertRaises(ValueError): self.run_patch(True)

    def test_backup_pair_precedes_first_replace_and_interrupted_pair_recovers(self):
        replace = patcher.os.replace
        calls = []
        def checked(src, dst):
            for name, raw, _ in ORIGINALS:
                self.assertEqual((self.root / (name + patcher.BACKUP)).read_bytes(), raw)
            calls.append(dst)
            if len(calls) == 2: raise OSError('injected second replacement failure')
            return replace(src, dst)
        with mock.patch.object(patcher.os, 'replace', side_effect=checked):
            with self.assertRaises(OSError): self.run_patch(True)
        self.assertIn(patcher.MARKER, (self.root / 'engine.cpp').read_text())
        self.assertEqual((self.root / 'game.cpp').read_bytes(), ORIGINALS[1][1])
        self.assertFalse(list(self.root.glob('.analytics-patch-*')))
        self.run_patch(True)
        self.assertTrue(all(r['alreadyPatched'] for r in self.run_patch()['files']))

    def test_changed_source_between_preflight_and_write_is_retained(self):
        original = patcher.recheck
        changed = False
        def mutate(saved):
            nonlocal changed
            if not changed:
                changed = True
                (self.root / 'game.cpp').write_bytes(b'late external source')
            return original(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=mutate):
            with self.assertRaises(ValueError): self.run_patch(True)
        self.assertEqual((self.root / 'game.cpp').read_bytes(), b'late external source')
        self.assertFalse(list(self.root.glob('*' + patcher.BACKUP)))

    def test_backup_corruption_before_replace_prevents_source_mutation(self):
        original = patcher.recheck
        changed = False
        def mutate(saved):
            nonlocal changed
            if not changed and (self.root / ('game.cpp' + patcher.BACKUP)).exists():
                changed = True
                (self.root / ('engine.cpp' + patcher.BACKUP)).write_bytes(b'late corruption')
            return original(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=mutate):
            with self.assertRaises(ValueError): self.run_patch(True)
        self.assert_original()

    def test_interrupted_second_backup_flush_leaves_retryable_originals(self):
        sync = patcher.os.fsync
        calls = 0
        def fail_second(fd):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('injected backup flush failure')
            return sync(fd)
        with mock.patch.object(patcher.os, 'fsync', side_effect=fail_second):
            with self.assertRaises(OSError): self.run_patch(True)
        self.assert_original()
        self.assertEqual((self.root / ('engine.cpp' + patcher.BACKUP)).read_bytes(), ORIGINALS[0][1])
        self.assertFalse((self.root / ('game.cpp' + patcher.BACKUP)).exists())
        self.assertFalse(list(self.root.glob('.analytics-backup-*')))
        self.run_patch(True)

    def test_exclusive_backup_publication_preserves_late_existing_file(self):
        link = patcher.os.link
        def collide(src, dst):
            Path(dst).write_bytes(b'late unrelated backup')
            return link(src, dst)
        with mock.patch.object(patcher.os, 'link', side_effect=collide):
            with self.assertRaises(FileExistsError): self.run_patch(True)
        self.assert_original()
        self.assertEqual((self.root / ('engine.cpp' + patcher.BACKUP)).read_bytes(), b'late unrelated backup')
        self.assertFalse(list(self.root.glob('.analytics-backup-*')))

    def test_temporary_link_cleanup_failure_retains_sources_and_refuses_adoption(self):
        unlink = Path.unlink
        def fail_owned(path, *args, **kwargs):
            if path.name.startswith('.analytics-backup-'):
                raise OSError('injected temporary link cleanup failure')
            return unlink(path, *args, **kwargs)
        with mock.patch.object(Path, 'unlink', fail_owned):
            with self.assertRaises(OSError): self.run_patch(True)
        self.assert_original()
        temporary, = self.root.glob('.analytics-backup-*')
        backup = self.root / ('engine.cpp' + patcher.BACKUP)
        self.assertEqual(temporary.stat().st_ino, backup.stat().st_ino)
        self.assertEqual(backup.stat().st_nlink, 2)
        self.assertEqual(backup.read_bytes(), ORIGINALS[0][1])
        with self.assertRaises(ValueError): self.run_patch(True)
        # Only the disposable fixture performs this explicitly verified recovery.
        temporary.unlink()
        self.run_patch(True)

    def test_marker_and_version_required_and_rechecked(self):
        version = self.root / 'Engine/Build/Build.version'
        version.write_text('{}')
        with self.assertRaises(ValueError): self.run_patch(True)
        self.assert_original()
        (self.root / '.tournament-browser-port').unlink()
        with self.assertRaises(ValueError): self.run_patch(True)

    def test_hardlinked_source_or_backup_refused(self):
        os.link(self.root / 'engine.cpp', self.root / 'alias')
        with self.assertRaises(ValueError): self.run_patch(True)
        (self.root / 'alias').unlink()
        os.link(self.root / 'engine.cpp', self.root / ('engine.cpp' + patcher.BACKUP))
        with self.assertRaises(ValueError): self.run_patch(True)
        self.assert_original()

    def test_symlink_and_reparse_ancestors_refused(self):
        real_lstat = Path.lstat
        class Reparse:
            st_mode = 0o040755
            st_file_attributes = 0x400
        def with_reparse(path, *a, **kw):
            return Reparse() if path == self.root else real_lstat(path, *a, **kw)
        with mock.patch.object(Path, 'lstat', with_reparse):
            with self.assertRaises(ValueError): self.run_patch(True)
        self.assert_original()

    def test_newline_bom_preservation_and_unknown_edits_refused(self):
        for source, entry in zip(ORIGINALS, self.specs):
            for crlf, bom in itertools.product((False, True), repeat=2):
                raw = source[1].replace(b'\n', b'\r\n') if crlf else source[1]
                if bom: raw = b'\xef\xbb\xbf' + raw
                fixed = patcher.transform(raw, entry)
                self.assertEqual(fixed.startswith(b'\xef\xbb\xbf'), bom)
                self.assertEqual(b'\r\n' in fixed, crlf)
                self.assertEqual(patcher.transform(fixed, entry), fixed)
                with self.assertRaises(ValueError): patcher.transform(fixed + b'// drift', entry)
                with self.assertRaises(ValueError): patcher.transform(fixed.replace(patcher.MARKER.encode(), b'altered', 1), entry)
        with self.assertRaises(ValueError):
            patcher.transform(ORIGINALS[0][1].replace(b'\n', b'\r\n', 1), self.specs[0])


def extract_body(text, signature):
    start = text.index(signature)
    start = text.index('{', start)
    depth = 1
    end = start + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


class ActualSourceTests(unittest.TestCase):
    def setUp(self):
        if PRIVATE is None: self.skipTest('Requires private pinned engine originals')
        self.raw = [(PRIVATE / Path(s[0]).name).read_bytes() for s in patcher.SPECS]
        for raw, entry in zip(self.raw, patcher.SPECS):
            self.assertEqual(patcher.sha(raw), entry[1])
        self.cxx = shutil.which('clang++') or shutil.which('g++')
        if not self.cxx: self.fail('Host C++ compiler required for requested private-source tests')

    def compile_run(self, code):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'test.cpp'
            binary = Path(tmp) / 'test'
            source.write_text(code)
            result = subprocess.run([self.cxx, '-std=c++11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_whole_files_roundtrip(self):
        for raw, entry in zip(self.raw, patcher.SPECS):
            fixed = patcher.transform(raw, entry)
            if entry[2] == 'engine':
                inverse = fixed.replace(patcher.ENGINE_NEW.encode(), patcher.ENGINE_IF.encode(), 1)
            else:
                inverse = fixed.replace(patcher.UT_OPEN.encode(), b'', 1).replace(patcher.UT_CLOSE.encode(), b'', 1)
            self.assertEqual(inverse, raw)
            self.assertEqual(patcher.transform(fixed, entry), fixed)

    def test_actual_engine_preprocessor_condition_native_matrix(self):
        original = self.raw[0].decode()
        fixed = patcher.transform(self.raw[0], patcher.SPECS[0]).decode()
        snippets = []
        for text, anchor in ((original, patcher.ENGINE_IF), (fixed, '// ' + patcher.MARKER)):
            start = text.index(anchor)
            snippets.append(text[start:text.index('#endif', start) + len('#endif')])
        code = ['#include <cassert>', 'struct Engine { bool editor,game; bool AreEditorAnalyticsEnabled(){return editor;} bool AreGameAnalyticsEnabled(){return game;} };']
        calls = []
        for index, (browser, debug, xbox, shipping) in enumerate(itertools.product((0, 1), repeat=4)):
            for name, value in zip(('PLATFORM_HTML5_BROWSER', 'UE_BUILD_DEBUG', 'PLATFORM_XBOXONE', 'UE_BUILD_SHIPPING'), (browser, debug, xbox, shipping)):
                code += ['#undef ' + name, '#define %s %d' % (name, value)]
            for variant, snippet in enumerate(snippets):
                code += ['bool f%d_%d(bool bIsEditorRun,bool bIsGameRun,Engine* GEngine){ (void)bIsEditorRun;(void)bIsGameRun;(void)GEngine;' % (index, variant), snippet, 'return bShouldInitAnalytics;}']
            calls.append('for(int m=0;m<16;++m){Engine e{bool(m&4),bool(m&8)}; bool old=f%d_0(m&1,m&2,&e), now=f%d_1(m&1,m&2,&e); assert(now==(%d?false:old));}' % (index, index, browser))
        code += ['int main(){', *calls, '}']
        self.compile_run('\n'.join(code))

    def test_actual_ut_initialize_preserves_local_state_and_native_paths(self):
        old = extract_body(self.raw[1].decode(), 'void FUTAnalytics::Initialize()')
        new = extract_body(patcher.transform(self.raw[1], patcher.SPECS[1]).decode(), 'void FUTAnalytics::Initialize()')
        prelude = r'''
#include <cassert>
#define TEXT(s) s
#define checkf(cond,...) assert(cond)
struct FString { FString(const char* = ""){} static FString Printf(const char*,const char*){return {};}
 const char* operator*()const{return "test";} FString operator+(const char*)const{return {};} };
struct UGeneralProjectSettings { FString ProjectVersion; };
template<class T> T* GetDefault(){static T value;return &value;}
'''
        code = [prelude]
        for ns, browser, body in (('old', 0, old), ('native', 0, new), ('browser', 1, new)):
            code += ['#undef PLATFORM_HTML5_BROWSER', '#define PLATFORM_HTML5_BROWSER %d' % browser, 'namespace '+ns+' {', r'''
bool commandlet=false,GIsEditor=false,GIsPlayInEditorWorld=false,bIsInitialized=false;
int guid=0,created=0,logins=0,names=0;
bool IsRunningCommandlet(){return commandlet;}
struct FGuid {static int NewGuid(){return ++guid;}};
int UniqueAnalyticSessionGuid=0;
struct Pointer {bool valid=false;bool IsValid(){return valid;} Pointer& operator=(int){valid=true;return *this;}} Analytics;
FString SecureAnalyticsEndpoint;
FString GetBuildType(){return {};}
struct FAnalyticsET {struct Config {Config(FString,FString,FString){}};
 static FAnalyticsET& Get(){static FAnalyticsET v;return v;} int CreateAnalyticsProvider(Config){return ++created;} };
void LoginStatusChanged(FString){++logins;}
void InitializeAnalyticParameterNames(){++names;}
void Initialize()
''', body, r'''
int run(int mask){commandlet=mask&1;GIsEditor=mask&2;GIsPlayInEditorWorld=mask&4;
 bIsInitialized=false;guid=created=logins=names=0;Analytics.valid=false;
 Initialize();return guid+created*2+logins*4+names*8+int(bIsInitialized)*16+int(Analytics.valid)*32;}
}''']
        code += ['int main(){for(int i=0;i<8;++i){assert(old::run(i)==native::run(i));assert(browser::run(i)==(i?1:25));} assert(native::run(0)==63);}']
        self.compile_run('\n'.join(code))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-source-dir', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE = args.private_source_dir
    unittest.main(argv=[__file__, *rest])
