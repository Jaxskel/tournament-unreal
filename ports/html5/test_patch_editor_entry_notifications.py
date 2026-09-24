"""Synthetic publication tests; exact private engine capture is optional."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
LOADER = importlib.util.spec_from_file_location('entry_notification_patch', HERE / 'patch-editor-entry-notifications.py')
patcher = importlib.util.module_from_spec(LOADER)
LOADER.loader.exec_module(patcher)
PRIVATE_SOURCE_DIR = None


def synthetic_spec(path='UnrealEdGlobals.cpp'):
    old, new = patcher.SPEC['old'], patcher.SPEC['new']
    source = b'head\n' + old + b'\n original_mainframe_body();\n}\n'
    output = source.replace(old, new, 1)
    return ({'path': path, 'source_sha256': hashlib.sha256(source).hexdigest(), 'source_bytes': len(source),
             'output_sha256': hashlib.sha256(output).hexdigest(), 'output_bytes': len(output),
             'old': old, 'new': new}, source, output)


class TransformTests(unittest.TestCase):
    def test_exact_transform_inverse_and_modified_inputs_rejected(self):
        spec, source, output = synthetic_spec()
        self.assertEqual(patcher.transform(source, spec), output)
        self.assertEqual(patcher.inverse(output, spec), source)
        self.assertEqual(patcher.transform(output, spec), output)
        for bad in (source + b' ', output + b' ', output.replace(b'IsUnattended', b'IsInteractive')):
            with self.subTest(bad=hashlib.sha256(bad).hexdigest()):
                with self.assertRaises(ValueError):
                    patcher.transform(bad, spec)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'Engine/Build').mkdir(parents=True)
        (self.root / '.tournament-browser-port').write_text('synthetic isolated root')
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(
            dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.spec, self.source_bytes, self.output_bytes = synthetic_spec()
        self.source = self.root / self.spec['path']
        self.source.write_bytes(self.source_bytes)
        self.backup = Path(str(self.source) + patcher.BACKUP)

    def run_patch(self, apply=False):
        return patcher.patch(self.root, apply, self.spec)

    def test_default_readonly_then_apply_backup_and_idempotence(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob('*'))
        self.assertFalse(self.run_patch()['apply'])
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob('*')))
        self.run_patch(True)
        self.assertEqual(self.backup.read_bytes(), self.source_bytes)
        self.assertEqual(self.source.read_bytes(), self.output_bytes)
        with mock.patch.object(patcher.os, 'replace', side_effect=AssertionError('unexpected replace')):
            self.assertTrue(self.run_patch(True)['files'][0]['alreadyPatched'])

    def test_already_patched_without_exact_backup_and_wrong_source_rejected(self):
        self.source.write_bytes(self.output_bytes)
        with self.assertRaisesRegex(ValueError, 'requires its exact original backup'):
            self.run_patch(True)
        self.backup.write_bytes(b'wrong backup')
        with self.assertRaisesRegex(ValueError, 'backup differs'):
            self.run_patch(True)
        with self.assertRaises(ValueError):
            patcher.transform(self.source_bytes + b'changed', self.spec)

    def test_drift_after_staging_is_not_overwritten(self):
        original_recheck = patcher.recheck
        seen = 0
        def inject(saved):
            nonlocal seen
            if saved['path'] == self.source:
                seen += 1
                staging = list(self.root.glob('.entry-notification-patch-*'))
                if seen == 4:  # pre-replace recheck, after staged file is flushed
                    self.assertEqual(len(staging), 1)
                    self.source.write_bytes(b'external concurrent edit')
            original_recheck(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=inject):
            with self.assertRaisesRegex(ValueError, 'changed after preflight'):
                self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), b'external concurrent edit')
        self.assertEqual(self.backup.read_bytes(), self.source_bytes)
        self.assertEqual(list(self.root.glob('.entry-notification-patch-*')), [])

    def test_wrong_build_and_hardlinked_source_refused(self):
        (self.root / 'Engine/Build/Build.version').write_text('{}')
        with self.assertRaises(ValueError):
            self.run_patch(True)
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(
            dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        alias = self.root / 'alias.cpp'
        os.link(self.source, alias)
        with self.assertRaises(ValueError):
            self.run_patch(True)
        self.assertFalse(self.backup.exists())


class EntryPredicateTests(unittest.TestCase):
    def test_actual_inserted_predicate_all_flag_combinations(self):
        # Compile the exact inserted C++ on both platform branches. The shim parses
        # space-separated exact flags; Windows CLI tokenization belongs to engine FParse.
        predicate = patcher.SPEC['new'].decode().split('#if PLATFORM_WINDOWS',1)[1].split('\tif (bTournamentEntryReflectionNoMainFrame)')[0]
        predicate = '#if PLATFORM_WINDOWS'+predicate
        harness = r'''#include <string>
#include <sstream>
#include <set>
#include <cassert>
#define TEXT(x) x
static bool unattended;
static std::string args;
struct FApp { static bool IsUnattended() { return unattended; } };
struct FCommandLine { static const char* Get() { return args.c_str(); } };
struct FParse { static bool Param(const char* a, const char* wanted) {
    std::istringstream input(a); std::string token;
    while (input >> token) if (token == std::string("-") + wanted) return true;
    return false;
} };
bool selected() {
PREDICATE
return bTournamentEntryReflectionNoMainFrame;
}
int main() {
 const char* flags[] = {"TournamentEntryReflectionNoMainFrame", "EntryReflectionDiagnostic",
 "immersive", "VREditor", "ForceVREditor", "AutomatedMapBuild", "nullrhi", "game"};
 for (int mask=0; mask<256; ++mask) for(int u=0; u<2; ++u) {
   args.clear(); unattended=u;
   for(int j=0;j<8;++j) if(mask & (1<<j)) args += std::string(" -")+flags[j];
   const bool expected = PLATFORM_WINDOWS && u && mask==3;
   assert(selected()==expected);
 }
}
'''.replace('PREDICATE', predicate)
        with tempfile.TemporaryDirectory() as tmp:
            cpp = Path(tmp)/'predicate.cpp'; cpp.write_text(harness)
            for platform in (0, 1):
                binary = Path(tmp)/('predicate'+str(platform))
                subprocess.run(['c++','-std=c++11','-DPLATFORM_WINDOWS='+str(platform),str(cpp),'-o',str(binary)],check=True,capture_output=True)
                subprocess.run([str(binary)],check=True,capture_output=True)


class PrivateSourceTests(unittest.TestCase):
    def test_private_inverse_and_actual_begin_tick_controlflow(self):
        if not PRIVATE_SOURCE_DIR:
            self.skipTest('private notification source not supplied')
        raw=(Path(PRIVATE_SOURCE_DIR)/'GlobalEditorNotification.cpp').read_bytes()
        updated=patcher.transform(raw)
        self.assertEqual(patcher.inverse(updated),raw)
        self.assertTrue(updated.endswith(raw.split(patcher.SPEC['old'],1)[1]))
        text=updated.decode()
        body=text[text.index('TSharedPtr<SNotificationItem> FGlobalEditorNotification::BeginNotification()'):text.index('bool FGlobalEditorNotification::IsTickable()')]
        harness=r'''#include <memory>
#include <string>
#include <sstream>
#include <cassert>
#define TEXT(x) x
static bool unattended=true;
static std::string args;
struct FApp {static bool IsUnattended(){return unattended;}};
struct FCommandLine {static const char* Get(){return args.c_str();}};
struct FParse {static bool Param(const char* a,const char* flag){std::istringstream s(a);std::string v;while(s>>v)if(v==std::string("-")+flag)return true;return false;}};
template<class T> struct TSharedPtr {std::shared_ptr<T> p; TSharedPtr(){} TSharedPtr(std::shared_ptr<T> x):p(x){} bool IsValid()const{return bool(p);} T* operator->()const{return p.get();}};
template<class T> struct TWeakPtr {TSharedPtr<T> p; TSharedPtr<T> Pin(){return p;} void Reset(){p=TSharedPtr<T>();} TWeakPtr& operator=(TSharedPtr<T> x){p=x;return *this;}};
struct FText {static FText GetEmpty(){return FText();}};
struct EVisibility {enum {HitTestInvisible};};
struct SNotificationItem {enum {CS_Pending,CS_Success};int state=CS_Pending;void ExpireAndFadeout(){} void SetCompletionState(int s){state=s;}int GetCompletionState(){return state;} void SetVisibility(int){}void SetText(FText){} };
struct FNotificationInfo {FNotificationInfo(FText){}bool bFireAndForget=true;double FadeOutDuration=1,ExpireDuration=1;};
static int windows=0;
struct FSlateNotificationManager {static FSlateNotificationManager& Get(){static FSlateNotificationManager m;return m;} TSharedPtr<SNotificationItem> AddNotification(const FNotificationInfo&){++windows;return TSharedPtr<SNotificationItem>(std::make_shared<SNotificationItem>());} };
struct FPlatformTime {static double Seconds(){return 1.;}};
struct FGlobalEditorNotification {TWeakPtr<SNotificationItem> NotificationPtr;double NextEnableTimeInSeconds=0,EnableDelayInSeconds=0;int polls=0,texts=0;bool show=true;
 TSharedPtr<SNotificationItem> BeginNotification();void EndNotification();void Tick(float);
 bool ShouldShowNotification(bool){++polls;return show;}void SetNotificationText(TSharedPtr<SNotificationItem>){++texts;}
};
BODY
int main(){
 for(int disabled=0;disabled<2;++disabled){
  windows=0;args=disabled?"-TournamentEntryReflectionNoMainFrame -EntryReflectionDiagnostic":"";
  FGlobalEditorNotification n;n.Tick(0);n.Tick(0);assert(n.polls==2);
  if(PLATFORM_WINDOWS && disabled){assert(windows==0 && n.texts==0 && !n.NotificationPtr.Pin().IsValid());}
  else {assert(windows==1 && n.texts==2 && n.NotificationPtr.Pin().IsValid());}
  n.show=false;n.Tick(0);assert(n.polls==3);
 }
}
'''.replace('BODY',body)
        with tempfile.TemporaryDirectory() as tmp:
            cpp=Path(tmp)/'notification.cpp';cpp.write_text(harness)
            for platform in (0,1):
                binary=Path(tmp)/('notification'+str(platform))
                subprocess.run(['c++','-std=c++11','-DPLATFORM_WINDOWS='+str(platform),str(cpp),'-o',str(binary)],check=True,capture_output=True)
                subprocess.run([str(binary)],check=True,capture_output=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-source-dir')
    args, remaining = parser.parse_known_args()
    PRIVATE_SOURCE_DIR = args.private_source_dir
    unittest.main(argv=[__file__, *remaining])
