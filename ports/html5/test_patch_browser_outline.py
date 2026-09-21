"""Original fixtures; temporary writes only. Optional licensed source stays private."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile
import unittest

P = runpy.run_path(str(Path(__file__).with_name('patch-browser-outline.py')))
SOURCE = '''AUTPlayerCameraManager::AUTPlayerCameraManager(const class FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    DefaultPPSettings.BloomIntensity = 0.20f;
    DefaultPPSettings.AddBlendable(OutlineMat, 1.0f);
    DefaultPPSettings.VignetteIntensity = 0.20f;
}
void AUTPlayerCameraManager::ApplyCameraModifiers(float DeltaTime, FMinimalViewInfo& InOutPOV)
{
    Super::ApplyCameraModifiers(DeltaTime, InOutPOV);
    if (GetWorld()->PostProcessVolumes.Num() == 0)
    {
        UsedDefault = true;
    }
    if (GetWorld()->PostProcessVolumes.Num() > 0)
    {
        BlendableOverrides.AddBlendable(OutlineMat, 1.0f);
    }
    UMaterialInterface* PPOverlay = NULL;
    AUTRemoteRedeemer* Redeemer = GetViewTargetPawn();
    if (Redeemer != NULL)
    {
        PPOverlay = Redeemer->GetPostProcessMaterial();
    }
    if (PPOverlay != NULL)
    {
        BlendableOverrides.AddBlendable(PPOverlay, 1.0f);
    }
    BlendableOverrides.BloomIntensity = 0.35f;
}
'''
HARNESS = r'''
#include <cassert>
#include <cstddef>
#include <vector>
class FObjectInitializer {};
struct FMinimalViewInfo {};
struct UMaterialInterface {};
UMaterialInterface outline, overlay;
struct Settings {
    float BloomIntensity=0, VignetteIntensity=0;
    std::vector<UMaterialInterface*> materials;
    void AddBlendable(UMaterialInterface* m, float weight) {
        assert(weight == 1.0f); materials.push_back(m);
    }
};
struct AUTRemoteRedeemer { UMaterialInterface* GetPostProcessMaterial() { return &overlay; } };
struct Volumes { int count=0; int Num() { return count; } };
struct World { Volumes PostProcessVolumes; };
struct Parent {
    Parent(const FObjectInitializer&) {}
    int calls=0;
    void ApplyCameraModifiers(float, FMinimalViewInfo&) { ++calls; }
};
struct AUTPlayerCameraManager : Parent {
    using Super=Parent;
    Settings DefaultPPSettings, BlendableOverrides;
    UMaterialInterface* OutlineMat=&outline;
    World world;
    bool UsedDefault=false;
    AUTRemoteRedeemer* redeemer=nullptr;
    World* GetWorld() { return &world; }
    AUTRemoteRedeemer* GetViewTargetPawn() { return redeemer; }
    AUTPlayerCameraManager(const FObjectInitializer&);
    void ApplyCameraModifiers(float, FMinimalViewInfo&);
};
'''
MAIN = r'''
int main() {
    for (int volumes : {0,1}) for (int useRedeemer : {0,1}) {
        FObjectInitializer init;
        AUTPlayerCameraManager camera(init);
        camera.world.PostProcessVolumes.count=volumes;
        AUTRemoteRedeemer redeemer;
        if (useRedeemer) camera.redeemer=&redeemer;
        FMinimalViewInfo view;
        camera.ApplyCameraModifiers(0.016f,view);
        assert(camera.calls==1 && camera.UsedDefault==(volumes==0));
        assert(camera.DefaultPPSettings.BloomIntensity==0.20f);
        assert(camera.DefaultPPSettings.VignetteIntensity==0.20f);
        assert(camera.BlendableOverrides.BloomIntensity==0.35f);
#if PLATFORM_HTML5_BROWSER
        assert(camera.DefaultPPSettings.materials.empty());
        assert(camera.BlendableOverrides.materials.size()==unsigned(useRedeemer));
#else
        assert(camera.DefaultPPSettings.materials.size()==1);
        assert(camera.DefaultPPSettings.materials[0]==&outline);
        assert(camera.BlendableOverrides.materials.size()==unsigned(volumes+useRedeemer));
        if (volumes) assert(camera.BlendableOverrides.materials[0]==&outline);
#endif
        if (useRedeemer) assert(camera.BlendableOverrides.materials.back()==&overlay);
    }
}
'''


class OutlinePatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ut4-outline-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root/'.tournament-browser-port').touch()
        self.version = self.root/'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.source = self.root/P['SOURCE_PATH']
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'\xef\xbb\xbf'+SOURCE.replace('\n','\r\n').encode())
        self.backup = Path(str(self.source)+P['BACKUP_SUFFIX'])

    def patch(self, apply=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return P['patch'](self.root, apply)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self):
        before = self.snapshot()
        with self.assertRaises(ValueError): self.patch()
        self.assertEqual(before, self.snapshot())

    def compiler(self):
        c = shutil.which('clang++') or shutil.which('c++')
        if not c: self.skipTest('No local C++ compiler')
        return c

    def test_preflight_no_writes(self):
        before=self.snapshot()
        self.assertEqual(self.patch(False)['status'],'would-patch')
        self.assertEqual(before,self.snapshot())

    def test_apply_backup_encoding_and_idempotence(self):
        original=self.source.read_bytes(); self.patch()
        self.assertEqual(self.backup.read_bytes(),original)
        updated=self.source.read_bytes()
        self.assertTrue(updated.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n',updated.replace(b'\r\n',b''))
        stamps=[p.stat().st_mtime_ns for p in (self.source,self.backup)]
        before=self.snapshot()
        self.assertEqual(self.patch()['status'],'already-patched')
        self.assertEqual(before,self.snapshot())
        self.assertEqual(stamps,[p.stat().st_mtime_ns for p in (self.source,self.backup)])

    def test_matching_existing_backup_preserved(self):
        self.backup.write_bytes(self.source.read_bytes())
        stamp=self.backup.stat().st_mtime_ns; self.patch()
        self.assertEqual(stamp,self.backup.stat().st_mtime_ns)

    def test_unmarked_checkout(self):
        (self.root/'.tournament-browser-port').unlink(); self.reject()

    def test_each_version_field_pinned(self):
        correct=json.loads(self.version.read_text())
        for key in correct:
            with self.subTest(key=key):
                self.version.write_text(json.dumps({**correct,key:correct[key]+1})); self.reject()

    def test_changed_calls_comments_and_duplicate_sites(self):
        call=P['CALLS'][0]
        for replacement in (call.replace('1.0f','0.5f'), '// '+call, '/* '+call+' */', call+'\n    '+call):
            with self.subTest(replacement=replacement):
                self.source.write_text(SOURCE.replace(call,replacement)); self.reject()

    def test_wrong_method_or_volume_context(self):
        for changed in (SOURCE.replace('ApplyCameraModifiers(float','Other(float'),
                        SOURCE.replace('PostProcessVolumes.Num() > 0','PostProcessVolumes.Num() == 0')):
            self.source.write_text(changed); self.reject()

    def test_unmarked_conditional_rejected(self):
        call=P['CALLS'][0]
        self.source.write_text(SOURCE.replace(call,'\n#if 0\n'+call+'\n#endif')); self.reject()

    def test_partial_altered_or_moved_guards(self):
        updated=P['transform'](SOURCE)
        first=P['guarded'](P['CALLS'][0],'    ','\n')
        for changed in (updated.replace(P['MARKER'],'other',1),
                        updated.replace('#if !PLATFORM_HTML5_BROWSER','#if PLATFORM_HTML5_BROWSER',1),
                        updated.replace(first,'    '+P['CALLS'][0],1)+'\n'+first):
            self.source.write_text(changed); self.reject()

    def test_conflicting_backup(self):
        self.backup.write_text('different original'); self.reject()

    def test_patched_missing_backup(self):
        self.patch(); self.backup.unlink(); self.reject()

    def test_modified_unrelated_source_rejected_after_apply(self):
        self.patch(); self.source.write_bytes(self.source.read_bytes()+b'\r\n// changed\r\n'); self.reject()

    def test_hardlinked_source(self):
        os.link(self.source,self.root/'shared.cpp'); self.reject()

    def test_hardlinked_backup(self):
        saved=self.root/'saved.cpp'; saved.write_bytes(self.source.read_bytes())
        os.link(saved,self.backup); self.reject()

    def test_symlink_source(self):
        actual=self.root/'actual.cpp'; self.source.rename(actual); self.source.symlink_to(actual); self.reject()

    def test_symlink_ancestor(self):
        parent=self.source.parent; actual=parent.with_name('actual')
        parent.rename(actual); parent.symlink_to(actual,target_is_directory=True); self.reject()

    def test_linked_marker_or_version(self):
        for path in (self.root/'.tournament-browser-port', self.version):
            actual=path.with_name(path.name+'.physical'); path.rename(actual); path.symlink_to(actual)
            self.reject(); path.unlink(); actual.rename(path)

    def test_mixed_newlines(self):
        self.source.write_bytes(self.source.read_bytes()+b'\n'); self.reject()

    def test_only_two_guards_added(self):
        updated=P['transform'](SOURCE)
        for call, indent in zip(P['CALLS'],('    ','        ')):
            updated=updated.replace(P['guarded'](call,indent,'\n'),indent+call)
        self.assertEqual(updated,SOURCE)

    def test_compiled_branches_preserve_settings_redeemer_and_volume_paths(self):
        path=self.root/'camera.cpp'
        path.write_text(HARNESS+P['transform'](SOURCE)+MAIN)
        for browser in (None,0,1):
            exe=self.root/('camera'+str(browser))
            flags=[] if browser is None else ['-DPLATFORM_HTML5_BROWSER='+str(browser)]
            subprocess.run([self.compiler(),'-std=c++11','-Wall','-Wextra','-Werror',*flags,str(path),'-o',str(exe)],
                           check=True,capture_output=True,text=True,timeout=30)
            subprocess.run([str(exe)],check=True,capture_output=True,timeout=10)

    @unittest.skipUnless(os.environ.get('TOURNAMENT_CAMERA_SOURCE'), 'Set TOURNAMENT_CAMERA_SOURCE to a private actual camera source snapshot')
    def test_actual_source_preprocessed_both_platforms(self):
        original=Path(os.environ['TOURNAMENT_CAMERA_SOURCE']).read_bytes().decode('utf-8-sig')
        updated=P['transform'](original)
        self.assertEqual(P['transform'](updated),updated)
        def preprocess(text,browser):
            # No includes, engine build or remote process: C++ preprocessor only.
            text=re.sub(r'(?m)^\s*#include[^\r\n]*','',text)
            flags=[] if browser is None else ['-DPLATFORM_HTML5_BROWSER='+str(browser)]
            return subprocess.run([self.compiler(),'-E','-P','-x','c++',*flags,'-'],input=text,
                                  capture_output=True,text=True,check=True,timeout=15).stdout
        for browser in (None,0,1):
            expected=original
            if browser==1:
                for call in P['CALLS']: expected=expected.replace(call,'')
            normalize=lambda text: re.sub(r'\s+',' ',text).strip()
            self.assertEqual(normalize(preprocess(updated,browser)),normalize(preprocess(expected,browser)))

    def test_build_invokes_once_and_checks_failure_before_ubt(self):
        text=Path(__file__).with_name('build-legacy.ps1').read_text()
        invocation='& py -3 "$PSScriptRoot\\patch-browser-outline.py" $root --apply'
        self.assertEqual(text.count('patch-browser-outline.py'),1)
        self.assertIn(invocation+"\nif($LASTEXITCODE){throw 'Browser Outline postprocess patch failed'}",text)
        self.assertLess(text.index(invocation),text.index('UnrealBuildTool.exe'))


if __name__=='__main__': unittest.main(verbosity=2)
