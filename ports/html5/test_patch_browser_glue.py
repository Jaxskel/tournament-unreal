"""Run: python3 -B ports/html5/test_patch_browser_glue.py (requires Node.js).

Original miniature fixtures model the confirmed source contexts; no engine build
or installed checkout is modified. Node executes the patched JS with canaries.
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

PATCHER = runpy.run_path(str(Path(__file__).with_name('patch-browser-glue.py')))
JS = '''mergeInto(LibraryManager.library, {
  UE_GetCurrentCultureName: function(address, outsize) {
    var culture_name = navigator.language || navigator.browserLanguage;
    if (culture_name.lenght >= outsize) return 0;
    Module.writeAsciiToMemory(culture_name, address);
    return 1;
  }
});
'''
URL_BLOCK = '''var hoststring = location.href.substring(0, location.href.lastIndexOf('/'));
        var buffer = Module._malloc(hoststring.length);
        Module.writeAsciiToMemory(hoststring, buffer);
        return buffer;'''
CPP = '''void FMapPakDownloader::Init()
{
    // Quoted braces must not confuse function boundaries: { }
    const char* Unrelated = "}";
    char* LocationString = (char*)EM_ASM_INT({
        ''' + URL_BLOCK + '''
    });
    HostName = FString(ANSI_TO_TCHAR(LocationString));
}
void FMapPakDownloader::Other()
{
    EM_ASM_INT({ ''' + URL_BLOCK + ''' });
}
'''

NODE = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let library;
const heap = new Uint8Array(2048);
let writes = 0, allocations = [];
const Module = {
  writeAsciiToMemory(text, ptr) {
    writes++;
    for (let i = 0; i < text.length; i++) heap[ptr + i] = text.charCodeAt(i);
    heap[ptr + text.length] = 0;
  },
  _malloc(size) { allocations.push(size); return 32; }
};
const navigator = {};
vm.runInNewContext(input.culture, {
  navigator, Module, LibraryManager: {library: {}},
  mergeInto(target, value) { library = value; }
});
let cases = 0;
for (const [language, browserLanguage, expected] of [
  ['en-US', undefined, 'en-US'], [undefined, 'fr', 'fr'],
  [undefined, undefined, null], [42, undefined, null], [{}, undefined, null]
]) {
  navigator.language = language; navigator.browserLanguage = browserLanguage;
  for (const capacity of [0, 1, 2, 5, 6, 12]) {
    heap.fill(0xa5); writes = 0;
    const ok = expected !== null && expected.length < capacity;
    const result = library.UE_GetCurrentCultureName(32, capacity);
    assert.equal(result, ok ? 1 : 0);
    assert.equal(writes, ok ? 1 : 0);
    if (ok) {
      assert.equal(new TextDecoder().decode(heap.subarray(32, 32 + expected.length)), expected);
      assert.equal(heap[32 + expected.length], 0);
    } else assert.ok(heap.every(byte => byte === 0xa5), 'rejected culture wrote to memory');
    assert.equal(heap[31], 0xa5);
    assert.ok(heap.subarray(32 + capacity).every(byte => byte === 0xa5), 'culture exceeded capacity');
    cases++;
  }
}
const getURL = new Function('Module', 'location', input.url);
for (const length of [0, 1, 15, 16, 31, 32, 255]) {
  const host = 'x'.repeat(length);
  heap.fill(0xa5); writes = 0; allocations = [];
  const ptr = getURL(Module, {href: host + '/index.html'});
  assert.equal(ptr, 32);
  assert.deepEqual(allocations, [length + 1]);
  assert.equal(new TextDecoder().decode(heap.subarray(ptr, ptr + length)), host);
  assert.equal(heap[ptr + length], 0);
  assert.equal(heap[ptr - 1], 0xa5);
  assert.ok(heap.subarray(ptr + allocations[0]).every(byte => byte === 0xa5), 'URL exceeded allocation');
  cases++;
}
console.log(cases + ' JS bounds cases passed');
'''


class BrowserGlueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ut4-glue-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.tournament-browser-port').touch()
        self.version = self.root / 'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.version.write_text(json.dumps({'MajorVersion': 4, 'MinorVersion': 15, 'Changelist': 3228288}))
        self.js = self.root / PATCHER['CULTURE_PATH']
        self.cpp = self.root / PATCHER['URL_PATH']
        for path, text in ((self.js, JS), (self.cpp, CPP)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode())

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            PATCHER['patch'](self.root)

    def backup(self, path):
        return path.with_name(path.name + PATCHER['BACKUP_SUFFIX'])

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def rejected_without_writes(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_byte_exact_backups_encoding_scope_and_idempotence(self):
        originals = {path: path.read_bytes() for path in (self.js, self.cpp)}
        self.apply()
        for path, original in originals.items():
            self.assertEqual(self.backup(path).read_bytes(), original)
            patched = path.read_bytes()
            self.assertTrue(patched.startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\n', patched.replace(b'\r\n', b''))
        text = self.cpp.read_text(encoding='utf-8-sig')
        self.assertEqual(text[text.index('void FMapPakDownloader::Other'):], CPP[CPP.index('void FMapPakDownloader::Other'):])
        self.assertIn('HostName = FString(ANSI_TO_TCHAR(LocationString));', text)
        snapshot = self.snapshot()
        stamps = {p: p.stat().st_mtime_ns for p in (self.js, self.cpp, self.backup(self.js), self.backup(self.cpp))}
        self.apply()
        self.assertEqual(self.snapshot(), snapshot)
        self.assertEqual({p: p.stat().st_mtime_ns for p in stamps}, stamps)

    def test_unmarked_checkout_is_rejected(self):
        (self.root / '.tournament-browser-port').unlink()
        self.rejected_without_writes()

    def test_exact_engine_revision_is_required(self):
        for key, wrong in [('MajorVersion', 5), ('MinorVersion', 16), ('Changelist', 3228289)]:
            with self.subTest(key=key):
                version = {'MajorVersion': 4, 'MinorVersion': 15, 'Changelist': 3228288, key: wrong}
                self.version.write_text(json.dumps(version))
                self.rejected_without_writes()

    def test_unknown_second_file_does_not_partially_patch_first(self):
        self.cpp.write_text(CPP.replace('Module._malloc', 'DifferentAllocator'))
        self.rejected_without_writes()

    def test_duplicate_culture_function_is_rejected(self):
        self.js.write_text(JS + JS)
        self.rejected_without_writes()

    def test_duplicate_url_blocks_inside_init_are_rejected(self):
        self.cpp.write_text(CPP.replace(URL_BLOCK, URL_BLOCK + '\n' + URL_BLOCK, 1))
        self.rejected_without_writes()

    def test_partial_or_mixed_patches_are_rejected(self):
        self.js.write_text(JS.replace('culture_name.lenght', 'culture_name.length'))
        self.rejected_without_writes()
        self.js.write_text(JS)
        mixed = URL_BLOCK + '\n' + URL_BLOCK.replace('hoststring.length)', 'hoststring.length + 1)')
        self.cpp.write_text(CPP.replace(URL_BLOCK, mixed, 1))
        self.rejected_without_writes()

    def test_conflicting_backup_is_not_overwritten(self):
        self.backup(self.cpp).write_bytes(b'other revision')
        self.rejected_without_writes()

    def test_already_patched_first_file_can_complete_second(self):
        original = self.js.read_bytes()
        self.js.write_text(PATCHER['culture'](JS))
        self.backup(self.js).write_bytes(original)
        self.apply()
        self.assertEqual(self.backup(self.js).read_bytes(), original)
        self.assertIn('hoststring.length + 1', self.cpp.read_text())

    def test_real_js_bounds_with_missing_language_exact_fit_and_aligned_urls(self):
        self.apply()
        culture = self.js.read_text(encoding='utf-8-sig')
        text = self.cpp.read_text(encoding='utf-8-sig')
        start = text.index('var hoststring')
        end = text.index('return buffer;', start) + len('return buffer;')
        result = subprocess.run(['node', '-e', NODE], input=json.dumps({'culture': culture, 'url': text[start:end]}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('37 JS bounds cases passed', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
