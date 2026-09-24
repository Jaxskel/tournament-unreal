"""Run: python3 -B ports/html5/test_patch_browser_logging.py

Optionally set TOURNAMENT_RUNTIME_JS to a generated legacy engine JS file for
an additional Node check against its actual formatter. No engine build occurs.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PATCHER = runpy.run_path(str(HERE / 'patch-browser-logging.py'))
# Original small fixture with the two confirmed call statements, plus decoys
# outside the target method to detect accidental file-wide substitutions.
SINCE = 'Format = FString::Printf( TEXT( "[%07.2f][%3d]" ), RealTime, GFrameCounter % 1000 );'
UTC = 'Format = FString::Printf(TEXT("[%s][%3d]"), *FDateTime::UtcNow().ToString(TEXT("%Y.%m.%d-%H.%M.%S:%s")), GFrameCounter % 1000);'
SOURCE = '''FString FOutputDeviceHelper::FormatLogLine(ELogTimes::Type LogTime)
{
    const char* Brace = "}"; // } not the end of the function
    FString Format;
    switch (LogTime) {
        case ELogTimes::SinceGStartTime: {
            const double RealTime = 12.5;
            ''' + SINCE + '''
            break;
        }
        case ELogTimes::UTC:
            ''' + UTC + '''
            break;
    }
    return Format;
}
void Other()
{
    ''' + UTC + '''
}
'''

NODE = r'''
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(process.env.TOURNAMENT_RUNTIME_JS, 'utf8');
const begin = source.indexOf('function __formatString(');
const end = source.indexOf('function _emscripten_log_js', begin);
const prep = source.indexOf('prepVararg:(') + 'prepVararg:('.length;
const prepEnd = source.indexOf('),getAlignSize:', prep);
assert.ok(begin >= 0 && end > begin && prepEnd > prep);
const buffer = new ArrayBuffer(1024), heap = new Uint8Array(buffer), view = new DataView(buffer);
const context = {HEAP8: new Int8Array(buffer), HEAPU8: heap, HEAP32: new Int32Array(buffer), HEAPF64: new Float64Array(buffer),
  assert: x => assert.ok(x), i64Math: null,
  Runtime: {}, reSign: (x, bits) => bits === 32 ? x | 0 : x, unSign: (x, bits) => bits === 32 ? x >>> 0 : x,
  _strlen: p => {let n = 0; while (heap[p+n]) n++; return n;}};
vm.createContext(context);
context.Runtime.prepVararg = vm.runInContext('(' + source.slice(prep, prepEnd) + ')', context);
vm.runInContext(source.slice(begin, end), context);
const put = (p, s) => heap.set(Buffer.from(s + '\0'), p);
put(32, '[%s][%3d]'); put(128, 'timestamp');
let cases = 0;
for (const poison of [1668248144, 1953719634]) {
  for (const frame of [0n, 1n, 999n, 1000n, 4294967296n, 18446744073709551615n]) {
    const value = frame % 1000n;
    view.setUint32(256, 128, true);
    view.setUint32(260, poison, true); // padding after the string pointer
    view.setBigUint64(264, value, true); // original uint64 vararg is eight-byte aligned
    const bad = String.fromCharCode(...context.__formatString(32, 256));
    assert.equal(bad, '[timestamp][' + poison + ']');
    view.setInt32(260, Number(value), true); // correctly packed int32 argument
    const good = String.fromCharCode(...context.__formatString(32, 256));
    assert.equal(good, '[timestamp][' + String(value).padStart(3, ' ') + ']');
    cases++;
  }
}
console.log(cases + ' actual-formatter varargs cases passed');
'''


class LoggingPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ut4-logging-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.tournament-browser-port').touch()
        self.version = self.root / 'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.version.write_text(json.dumps({'MajorVersion': 4, 'MinorVersion': 15, 'PatchVersion': 0, 'Changelist': 3228288}))
        self.path = self.root / PATCHER['SOURCE_PATH']
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'\xef\xbb\xbf' + SOURCE.replace('\n', '\r\n').encode())
        self.header = self.root / PATCHER['GLOBALS_PATH']
        self.header.parent.mkdir(parents=True)
        self.header.write_text('extern CORE_API uint64 GFrameCounter;\n')
        self.backup = self.path.with_name(self.path.name + PATCHER['BACKUP_SUFFIX'])

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            PATCHER['patch'](self.root)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject_without_writes(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_only_two_arguments_change_with_exact_backup_and_encoding(self):
        original = self.path.read_bytes()
        expected = SOURCE.replace('GFrameCounter % 1000', 'static_cast<int32>(GFrameCounter % 1000)', 2)
        self.apply()
        self.assertEqual(self.backup.read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), b'\xef\xbb\xbf' + expected.replace('\n', '\r\n').encode())

    def test_repeat_run_does_not_rewrite_source_or_backup(self):
        self.apply()
        before = self.snapshot()
        stamps = [p.stat().st_mtime_ns for p in (self.path, self.backup)]
        self.apply()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([p.stat().st_mtime_ns for p in (self.path, self.backup)], stamps)

    def test_unmarked_checkout_rejected(self):
        (self.root / '.tournament-browser-port').unlink()
        self.reject_without_writes()

    def test_exact_revision_required(self):
        correct = json.loads(self.version.read_text())
        for key in correct:
            with self.subTest(key=key):
                wrong = {**correct, key: correct[key] + 1}
                self.version.write_text(json.dumps(wrong))
                self.reject_without_writes()

    def test_counter_type_must_match_confirmed_source(self):
        self.header.write_text('extern CORE_API uint32 GFrameCounter;\n')
        self.reject_without_writes()

    def test_unknown_format_and_wrong_cast_rejected(self):
        for modified in [SOURCE.replace('[%s][%3d]', '[%s][%3u]'),
                         SOURCE.replace('GFrameCounter % 1000', 'static_cast<int32>(GFrameCounter) % 1000', 2)]:
            with self.subTest(source=modified):
                self.path.write_text(modified)
                self.reject_without_writes()

    def test_partial_patch_rejected(self):
        self.path.write_text(SOURCE.replace('GFrameCounter % 1000', 'static_cast<int32>(GFrameCounter % 1000)', 1))
        self.reject_without_writes()

    def test_duplicate_call_or_function_rejected(self):
        for modified in [SOURCE.replace(SINCE, SINCE + '\n' + SINCE), SOURCE + SOURCE]:
            with self.subTest(source=modified):
                self.path.write_text(modified)
                self.reject_without_writes()

    def test_call_in_line_comment_does_not_satisfy_guard(self):
        self.path.write_text(SOURCE.replace(SINCE, '// ' + SINCE))
        self.reject_without_writes()

    def test_call_in_block_comment_does_not_satisfy_guard(self):
        self.path.write_text(SOURCE.replace(SINCE, '/*\n' + SINCE + '\n*/'))
        self.reject_without_writes()

    def test_commented_counter_declaration_does_not_satisfy_guard(self):
        self.header.write_text('/*\nextern CORE_API uint64 GFrameCounter;\n*/\n')
        self.reject_without_writes()

    def test_conflicting_backup_preserved(self):
        self.backup.write_bytes(b'other revision')
        self.reject_without_writes()

    def test_matching_existing_backup_is_not_rewritten(self):
        self.backup.write_bytes(self.path.read_bytes())
        stamp = self.backup.stat().st_mtime_ns
        self.apply()
        self.assertEqual(self.backup.stat().st_mtime_ns, stamp)

    @unittest.skipUnless(os.environ.get('TOURNAMENT_RUNTIME_JS'), 'set TOURNAMENT_RUNTIME_JS for actual legacy formatter check')
    def test_actual_legacy_formatter_consumes_the_correct_int32_slot(self):
        result = subprocess.run(['node', '-e', NODE], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('12 actual-formatter varargs cases passed', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
