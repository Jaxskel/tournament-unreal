"""Original synthetic guard/branch tests. All writes and stub builds use tempdirs."""
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

P = runpy.run_path(str(Path(__file__).with_name('patch-browser-window.py')))
SOURCE = '''void createWindow() {
    WindowHandle = SDL_CreateWindow("HTML5", SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED, 800, 600,
        SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE);
}
void resizeWindow() { SDL_SetWindowSize(WindowHandle, 2560, 1440); }
'''
HARNESS = r'''
#include <cassert>
using Uint32 = unsigned;
constexpr Uint32 SDL_WINDOW_OPENGL = 2, SDL_WINDOW_SHOWN = 4, SDL_WINDOW_RESIZABLE = 32;
constexpr int SDL_WINDOWPOS_CENTERED = 0;
struct Window { int w, h; Uint32 flags; };
Window* WindowHandle;
Window* SDL_CreateWindow(const char*, int, int, int w, int h, Uint32 flags) {
    static Window window; window = {w,h,flags}; return &window;
}
void SDL_SetWindowSize(Window* window, int w, int h) { window->w=w; window->h=h; }
'''
MAIN = r'''
int main() {
    createWindow();
    assert(WindowHandle->w == 800 && WindowHandle->h == 600);
    assert((WindowHandle->flags & (SDL_WINDOW_OPENGL|SDL_WINDOW_SHOWN)) == 6);
#if PLATFORM_HTML5_BROWSER
    assert(!(WindowHandle->flags & SDL_WINDOW_RESIZABLE));
#else
    assert(WindowHandle->flags & SDL_WINDOW_RESIZABLE);
#endif
    resizeWindow();
    assert(WindowHandle->w == 2560 && WindowHandle->h == 1440);
}
'''


def compile_branches(source, directory):
    compiler = shutil.which('clang++') or shutil.which('c++')
    if not compiler:
        raise unittest.SkipTest('No local C++ compiler')
    path = directory/'branch.cpp'
    path.write_text(HARNESS + source + MAIN)
    for browser in (0, 1):
        exe = directory/('branch'+str(browser))
        subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror',
                        '-DPLATFORM_HTML5_BROWSER='+str(browser),str(path),'-o',str(exe)],
                       check=True,capture_output=True,text=True)
        subprocess.run([str(exe)],check=True,capture_output=True)


class WindowPatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ut4-window-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root/'.tournament-browser-port').touch()
        self.version = self.root/'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.version.write_text(json.dumps(dict(MajorVersion=4,MinorVersion=15,PatchVersion=0,Changelist=3228288)))
        self.source = self.root/P['SOURCE_PATH']
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'\xef\xbb\xbf'+SOURCE.replace('\n','\r\n').encode())
        self.backup = Path(str(self.source)+P['BACKUP_SUFFIX'])
    def patch(self, apply=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return P['patch'](self.root, apply)
    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def reject(self):
        before=self.snapshot()
        with self.assertRaises(ValueError):self.patch()
        self.assertEqual(before,self.snapshot())
    def test_preflight_no_writes(self):
        before=self.snapshot();self.assertEqual(self.patch(False)['status'],'would-patch')
        self.assertEqual(before,self.snapshot())
    def test_apply_backup_encoding_idempotence(self):
        before=self.source.read_bytes();self.patch()
        self.assertEqual(self.backup.read_bytes(),before)
        result=self.source.read_bytes()
        self.assertTrue(result.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n',result.replace(b'\r\n',b''))
        state=self.snapshot();self.assertEqual(self.patch()['status'],'already-patched')
        self.assertEqual(self.snapshot(),state)
    def test_missing_marker(self):
        (self.root/'.tournament-browser-port').unlink();self.reject()
    def test_wrong_version(self):
        self.version.write_text('{}');self.reject()
    def test_altered_call(self):
        self.source.write_text(SOURCE.replace('800, 600','801, 600'));self.reject()
    def test_duplicate_call(self):
        self.source.write_text(SOURCE+SOURCE);self.reject()
    def test_conflicting_backup(self):
        self.backup.write_text('original mismatch');self.reject()
    def test_patched_missing_backup(self):
        self.patch();self.backup.unlink();self.reject()
    def test_modified_patch(self):
        self.patch();self.source.write_bytes(self.source.read_bytes().replace(b'#if PLATFORM_HTML5_BROWSER',b'#if !PLATFORM_HTML5_BROWSER'));self.reject()
    def test_modified_unrelated_source_after_patch(self):
        self.patch();self.source.write_bytes(self.source.read_bytes()+b'\r\n// changed\r\n');self.reject()
    def test_hardlink_source(self):
        other=self.root/'shared.cpp';os.link(self.source,other);self.reject()
    def test_hardlink_backup(self):
        other=self.root/'saved.cpp';other.write_bytes(self.source.read_bytes());os.link(other,self.backup);self.reject()
    def test_symlink_source(self):
        other=self.root/'real.cpp';self.source.rename(other);self.source.symlink_to(other);self.reject()
    def test_symlink_ancestor(self):
        parent=self.source.parent;physical=parent.with_name('physical');parent.rename(physical);parent.symlink_to(physical,target_is_directory=True);self.reject()
    def test_mixed_line_endings(self):
        self.source.write_bytes(self.source.read_bytes()+b'\n');self.reject()
    def test_preserves_resize_function(self):
        self.assertIn(SOURCE[SOURCE.index('void resizeWindow'):],P['transform'](SOURCE))
    def test_compile_browser_and_native_actual_transformed_block(self):
        compile_branches(P['transform'](SOURCE),self.root)
    def test_build_integration(self):
        text=Path(__file__).with_name('build-legacy.ps1').read_text()
        self.assertEqual(text.count('patch-browser-window.py'),1)
        self.assertLess(text.index('patch-browser-window.py'), text.index('$root link --selection'))
        helper = Path(__file__).with_name('prepare-browser-optimizer.py').read_text()
        self.assertIn('Engine/Binaries/DotNET/UnrealBuildTool.exe', helper)
        self.assertIn('patch-browser-window.py" $root --apply',text)

if __name__=='__main__':unittest.main()
