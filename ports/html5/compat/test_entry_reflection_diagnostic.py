"""Focused contract tests for the fixed UT-Entry in-memory capture diagnostic.

These tests exercise extracted native predicates and source ordering only. They do
not compile UE, run an editor, recapture a map, or authorize package saving.
"""
import argparse
import hashlib
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/EntryReflectionDiagnostic.h'
EDITOR_API = None
REFLECTION_SOURCE = None
EDITOR_PINS = {
    'AutoReimportManager.cpp': 'e27e82c4a7dc328c5795efdcd4c35dda1476e5ac288a118438b813e49d7ff4ad',
    'UnrealEdMisc.cpp': 'd648f9e0bd2fab466df5e6807831388f9d56dec2582f3e6fb2b19fce26bf9bf1',
}
REFLECTION_PINS = {
    'ReflectionCaptureComponent.cpp': '92414bf58ffce0c3cc9ac93b422d5abe20410bf6ea41f953e609b639ff570965',
    'ReflectionCaptureComponent.h': '61bfa9b13926a5511fd6b2aaeb058650a57cbfec020d417823315776ecac7c3e',
}


def native_predicate(name, parameters, main):
    text = HEADER.read_text()
    tail = text.split('static bool ' + name + '(', 1)[1]
    signature, body = tail.split('}\n', 1)[0].split(')\n{', 1)
    return f'''#include <cassert>
using int32=int;
bool {name}({signature}) {{ {body}
}}
int main(){{ {main} }}
'''


def compile_run(code):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise unittest.SkipTest('host C++ compiler unavailable')
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / 'test.cpp'
        exe = Path(td) / 'test'
        src.write_text(code)
        built = subprocess.run([compiler, '-std=c++14', str(src), '-o', str(exe)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stderr)
        ran = subprocess.run([str(exe)], capture_output=True, text=True)
        if ran.returncode:
            raise AssertionError(ran.stdout + ran.stderr)


class EntryReflectionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.text = HEADER.read_text()

    def test_actual_admission_predicate_fails_closed_for_every_gate(self):
        code = native_predicate('ERDAllowed', (), r'''
assert(ERDAllowed(true,false,true,true,true,true,true,true,true,true,true,true));
assert(!ERDAllowed(false,false,true,true,true,true,true,true,true,true,true,true));
assert(!ERDAllowed(true,true,true,true,true,true,true,true,true,true,true,true));
assert(!ERDAllowed(true,false,false,true,true,true,true,true,true,true,true,true));
assert(!ERDAllowed(true,false,true,false,true,true,true,true,true,true,true,true));
assert(!ERDAllowed(true,false,true,true,false,true,true,true,true,true,true,true));
assert(!ERDAllowed(true,false,true,true,true,false,true,true,true,true,true,true));
assert(!ERDAllowed(true,false,true,true,true,true,false,true,true,true,true,true));
assert(!ERDAllowed(true,false,true,true,true,true,true,false,true,true,true,true));
assert(!ERDAllowed(true,false,true,true,true,true,true,true,false,true,true,true));
assert(!ERDAllowed(true,false,true,true,true,true,true,true,true,false,true,true));
assert(!ERDAllowed(true,false,true,true,true,true,true,true,true,true,false,true));
assert(!ERDAllowed(true,false,true,true,true,true,true,true,true,true,true,false));''')
        compile_run(code)

    def test_actual_map_pin_predicate_requires_distinct_physical_exact_bytes(self):
        code = native_predicate('ERDMapPinAccepted', (), r'''
assert(ERDMapPinAccepted(true,true,true,true,true));
assert(!ERDMapPinAccepted(false,true,true,true,true));
assert(!ERDMapPinAccepted(true,false,true,true,true));
assert(!ERDMapPinAccepted(true,true,false,true,true));
assert(!ERDMapPinAccepted(true,true,true,false,true));
assert(!ERDMapPinAccepted(true,true,true,true,false));''')
        compile_run(code)

    def test_fixed_map_hashes_and_explicit_optin(self):
        self.assertIn('TEXT("/Game/RestrictedAssets/Maps/UT-Entry")', self.text)
        self.assertIn('653a6eb7a37f00c5238d210e5f45d7729117a246', self.text)
        self.assertIn('FParse::Param(*Params, TEXT("EntryReflectionDiagnostic"))', self.text)
        self.assertIn('EntryReflectionOriginalContent=', self.text)
        self.assertIn('EntryReflectionOutput=', self.text)
        self.assertIn('FParse::Param(*Params, TEXT("EntryReflectionDiagnostic"))', self.text)
        self.assertIn('ERDDeadlineSeconds = 180.0', self.text)

    def test_source_admission_snapshot_mutation_and_virtual_readback_order(self):
        self.assertNotIn('.Broadcast(', self.text)
        self.assertIn('if (!ERDAllowed(', self.text)
        self.assertLess(self.text.index('bMonitorContentDirectories = false'), self.text.index('AddTicker('))
        self.assertLess(self.text.index('BeforeObjects, BeforeDigest'), self.text.index('Target->SetCaptureIsDirty()'))
        self.assertEqual(self.text.count('Target->SetCaptureIsDirty()'), 1)
        self.assertEqual(self.text.count('UReflectionCaptureComponent::UpdateReflectionCaptureContents(World)'), 1)
        self.assertIn('UObject* VirtualTarget = Target;', self.text)
        self.assertIn('VirtualTarget->PreSave(nullptr)', self.text)
        self.assertNotRegex(self.text, r'(?<![A-Za-z])Target->PreSave\(')

    def test_readonly_contract_and_process_settings_restoration(self):
        self.assertIn('bAutoSaveEnable = false', self.text)
        self.assertIn('bAutoCreateAssets = false', self.text)
        self.assertIn('bAutoDeleteAssets = false', self.text)
        for field in ('OldMonitor', 'OldAutoSave', 'OldAutoCreate', 'OldAutoDelete'):
            self.assertIn(field, self.text)
        self.assertIn('Settings->bMonitorContentDirectories = OldMonitor', self.text)
        self.assertIn('FPlatformMisc::RequestExit(false)', self.text)
        for forbidden in ('SavePackage(', 'SaveConfig(', 'SaveDirtyPackages(', 'MarkPackageDirty('):
            self.assertNotIn(forbidden, self.text)
        self.assertIn('native_save_authorized"), false', self.text)
        self.assertIn('package_saved"), false', self.text)

    def test_snapshot_and_payload_are_bounded_and_zero_is_descriptive(self):
        self.assertIn('CPF_Transient | CPF_DuplicateTransient | CPF_NonPIEDuplicateTransient', self.text)
        self.assertIn('Name == TEXT("StateId")', self.text)
        self.assertIn('GetActorTransform().ToHumanReadableString()', self.text)
        self.assertIn('GetComponentTransform().ToHumanReadableString()', self.text)
        self.assertIn('Count > 150000', self.text)
        self.assertIn('Bytes > 100663296', self.text)
        self.assertIn('FMath::IsFinite(V[I])', self.text)
        self.assertIn('ZeroChannels', self.text)
        self.assertIn('zero-channel count is descriptive only', self.text)

    def test_map_pin_identity_is_rechecked_before_and_after_in_memory_work(self):
        self.assertIn('SelectedIdentity = A.Identity', self.text)
        self.assertIn('A.Identity == SelectedIdentity && B.Identity == OriginalIdentity', self.text)
        body = self.text.split('bool Tick(float)', 1)[1]
        self.assertIn('CheckMapPins()', body)
        self.assertIn('Finish(TEXT("diagnostic_completed")', body)

    def test_optional_pinned_reimport_source_proves_monitor_teardown_gate(self):
        if EDITOR_API is None:
            self.skipTest('pass --editor-api-dir for pinned AutoReimportManager.cpp and UnrealEdMisc.cpp')
        for filename, expected in EDITOR_PINS.items():
            raw = (EDITOR_API / filename).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
        manager = (EDITOR_API / 'AutoReimportManager.cpp').read_text(errors='replace')
        self.assertIn('if (Settings->bMonitorContentDirectories)', manager)
        lifecycle = EDITOR_API / 'LaunchEngineLoop.cpp'
        editor = EDITOR_API / 'UnrealEdEngine.cpp'
        self.assertEqual(hashlib.sha256(lifecycle.read_bytes()).hexdigest(), '5f30752a0090674da9b0778862c455928f82ceeef466d43a6ac995ba41271125')
        self.assertEqual(hashlib.sha256(editor.read_bytes()).hexdigest(), '7251b86ba8f61c63beaf94f16099799eefe7afe3e70bdd1d2f7400ded8ab4929')
        launch = lifecycle.read_text()
        self.assertLess(launch.index('if ( !LoadStartupModules() )'), launch.index('GEngine = GEditor = GUnrealEd = NewObject'))
        native = editor.read_text()
        gate = native.index('FPaths::IsProjectFilePathSet() && GIsEditor && !FApp::IsUnattended()')
        self.assertIn('AutoReimportManager->Initialize()', native[gate:gate+250])
        self.assertIn('!FApp::IsUnattended() || GEngine || GEditor', self.text)

    def test_exclusive_evidence_precedes_settings_and_capture(self):
        self.assertIn('CREATE_NEW', self.text)
        self.assertIn('FILE_APPEND_DATA, FILE_SHARE_READ', self.text)
        self.assertIn('FlushFileBuffers(EvidenceHandle)', self.text)
        start = self.text.index('static int32 EntryReflectionDiagnostic(')
        body = self.text[start:]
        self.assertLess(body.index('CreateFileW('), body.index('bAutoSaveEnable = false'))
        self.assertIn('Within(Output, EngineRoot) || Within(Output, OriginalEngineRoot)', body)
        self.assertIn('Output.ToLower().Contains(TEXT("/content/"))', body)
        self.assertIn('!Physical(FPaths::GetPath(Output), false)', body)

    def test_finish_does_not_reenable_autosave_before_exit(self):
        finish = self.text.split('void Finish(', 1)[1].split('bool Tick(', 1)[0]
        self.assertNotIn('RestoreSettings()', finish)
        shutdown = self.text.split('static void ShutdownEntryReflectionDiagnostic()', 1)[1]
        self.assertLess(shutdown.index('RemoveTicker'), shutdown.index('RestoreSettings'))
        self.assertIn('Settings = SettingsOwner.Get()', self.text)
        self.assertIn('CloseHandle(S->EvidenceHandle)', shutdown)

    def test_world_identity_and_settings_are_used_at_real_mutation_gate(self):
        tick = self.text.split('bool Tick(float)', 1)[1].split('static TSharedPtr<FERDState>', 1)[0]
        self.assertIn('World->PersistentLevel->GetPathName()', tick)
        self.assertIn('C->GetOwner()->GetLevel() != World->PersistentLevel', tick)
        self.assertIn('WorldCaptures != 1', tick)
        self.assertIn('World->WorldType != EWorldType::Editor', tick)
        gate = tick.index('if (!ERDAllowed(')
        self.assertLess(gate, tick.index('Target->SetCaptureIsDirty()'))
        self.assertIn('SettingsDisabled', tick[gate:tick.index('Target->SetCaptureIsDirty()')])
        self.assertIn('WorldOwner.Get() != World || TargetOwner.Get() != Target', tick)
        self.assertIn('HDR->CubemapSize & (HDR->CubemapSize - 1)', self.text)
        self.assertIn('GetReflectionCaptureSize_GameThread()', self.text)

    def test_optional_pinned_capture_api_proves_only_readback_path_used(self):
        if REFLECTION_SOURCE is None:
            self.skipTest('pass --reflection-source-dir for pinned reflection component sources')
        for filename, expected in REFLECTION_PINS.items():
            raw = (REFLECTION_SOURCE / filename).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
        hdr = (REFLECTION_SOURCE / 'ReflectionCaptureComponent.h').read_text(errors='replace')
        cpp = (REFLECTION_SOURCE / 'ReflectionCaptureComponent.cpp').read_text(errors='replace')
        self.assertIn('ENGINE_API void SetCaptureIsDirty()', hdr)
        self.assertIn('ENGINE_API static void UpdateReflectionCaptureContents(UWorld* WorldToUpdate)', hdr)
        self.assertIn('ENGINE_API const FReflectionCaptureFullHDR* GetFullHDRData() const', hdr)
        self.assertIn('void UReflectionCaptureComponent::PreSave(', cpp)
        self.assertIn('ReadbackFromGPU(World)', cpp)
        self.assertNotIn('ReadbackFromGPU(', self.text)


class PerformanceMonitorTests(unittest.TestCase):
    def test_actual_process_setting_scope_restore(self):
        text=HEADER.read_text()
        body=text.split('// ENTRY_PERFORMANCE_MONITOR_BEGIN\n',1)[1].split('// ENTRY_PERFORMANCE_MONITOR_END',1)[0]
        code=r'''#include <cassert>
#define check(x) assert(x)
struct UEditorPerProjectUserSettings {bool bMonitorEditorPerformance;};
template<class T> struct TWeakObjectPtr {T* p=nullptr;T* Get()const{return p;}TWeakObjectPtr& operator=(T* x){p=x;return *this;}};
BODY
int main(){for(int old=0;old<2;++old){UEditorPerProjectUserSettings s{bool(old)};FERDPerformanceMonitor m;assert(!m.IsDisabled());m.Disable(&s);assert(m.IsDisabled()&&!s.bMonitorEditorPerformance);m.Restore();assert(s.bMonitorEditorPerformance==bool(old));assert(!m.Saved);m.Restore();assert(s.bMonitorEditorPerformance==bool(old));}
UEditorPerProjectUserSettings s{true};FERDPerformanceMonitor m;m.Disable(&s);s.bMonitorEditorPerformance=true;assert(!m.IsDisabled());m.Owner.p=nullptr;m.Restore();assert(!m.Saved);
}
'''.replace('BODY',body)
        compile_run(code)
        start=text.split('static int32 EntryReflectionDiagnostic(',1)[1]
        self.assertLess(start.index('CreateFileW('),start.index('PerformanceMonitor.Disable('))
        self.assertLess(start.index('PerformanceMonitor.Disable('),start.index('AddTicker('))
        self.assertIn('&& PerformanceMonitor.IsDisabled()',text)
        self.assertNotIn('PerformanceMonitor.Restore()',text.split('void Finish(',1)[1].split('bool Tick(',1)[0])

    def test_pinned_performance_setting_api_and_gate(self):
        if EDITOR_API is None:self.skipTest('private editor API not supplied')
        for name,h in {'PerformanceMonitor.cpp':'54c8af452d669eea5ae115e8fcf198c6130bc009e1ab58cf85107d0fec42f224','EditorPerProjectUserSettings.h':'132401e6e595609acba469dc6c0526a79503d3b5efa9802898129acd4a72483c'}.items():
            self.assertEqual(hashlib.sha256((EDITOR_API/name).read_bytes()).hexdigest(),h)
        h=(EDITOR_API/'EditorPerProjectUserSettings.h').read_text();self.assertIn('UCLASS(minimalapi',h);self.assertIn('uint32 bMonitorEditorPerformance:1;',h)
        c=(EDITOR_API/'PerformanceMonitor.cpp').read_text().split('void FPerformanceMonitor::Tick(float DeltaTime)',1)[1]
        self.assertLess(c.index('!bMonitorEditorPerformance || !bIsNotificationAllowed'),c.index('ShowPerformanceWarning('))

    def test_only_performance_delta_inverse(self):
        text=HEADER.read_text()
        a=text.index('// ENTRY_PERFORMANCE_MONITOR_BEGIN');b=text.index('// ENTRY_PERFORMANCE_MONITOR_END',a)+len('// ENTRY_PERFORMANCE_MONITOR_END\n\n')
        text=text[:a]+text[b:]
        text=''.join(line for line in text.splitlines(keepends=True) if not any(tag in line for tag in ('ENTRY_PERFORMANCE_MEMBER','ENTRY_PERFORMANCE_RESTORE','ENTRY_PERFORMANCE_GET','ENTRY_PERFORMANCE_DISABLE')))
        text=text.replace('!Settings->bAutoCreateAssets && !Settings->bAutoDeleteAssets && PerformanceMonitor.IsDisabled(); // ENTRY_PERFORMANCE_GATE','!Settings->bAutoCreateAssets && !Settings->bAutoDeleteAssets;')
        text=text.replace('if (!Settings || !PerformanceSettings)', 'if (!Settings)')
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),'07540eb4ae0bf65116bd992ace9006ac3cc39ff8354691b15a5a99d84db301c6')
        cpp=(HEADER.parent/'UT4Html5Compat.cpp').read_bytes().replace(b'#include "Editor/EditorPerProjectUserSettings.h"\n',b'')
        # The independently checked map-save integration is separate from this older performance delta.
        for tag in (b'DECL',b'START',b'INCLUDE',b'VERIFY'):
            cpp,count=re.subn(rb'(?m)^[ \t]*// ENTRY_MAP_REPAIR_'+tag+rb'_BEGIN\n.*?^[ \t]*// ENTRY_MAP_REPAIR_'+tag+rb'_END\n',b'',cpp,flags=re.S)
            self.assertEqual(count,1)
        cpp=cpp.replace(b'UT4Compat::ShutdownEntryReflectionMapSave(); ',b'',1)
        self.assertEqual(hashlib.sha256(cpp).hexdigest(),'030fd1ac3f62955cbe5088735671666d99d098311499712a89fc83b71c4a0410')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--editor-api-dir', type=Path)
    parser.add_argument('--reflection-source-dir', type=Path)
    args, rest = parser.parse_known_args()
    EDITOR_API = args.editor_api_dir
    REFLECTION_SOURCE = args.reflection_source_dir
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
