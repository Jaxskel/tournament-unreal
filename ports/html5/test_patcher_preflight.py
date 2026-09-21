"""Original small source fixtures; no licensed checkout or engine build needed.

Run: python3 -B ports/html5/test_patcher_preflight.py
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MODULES = {name: runpy.run_path(str(HERE / name)) for name in (
    'patch-networking.py', 'patch-webgl-shaders.py',
    'patch-browser-packaging.py', 'configure-legacy.py')}
NETWORK = 'Engine/Plugins/Experimental/HTML5Networking/Source/HTML5Networking'
SHADERS = 'Engine/Source/Developer/ShaderFormatOpenGL/Private'
PACKAGING = 'Engine/Source/Programs/AutomationTool/HTML5/HTML5Platform.Automation.cs'
SDK = 'Engine/Source/Programs/UnrealBuildTool/HTML5/HTML5SDKInfo.cs'
REPLAY = 'Engine/Source/Runtime/Engine/Private/DemoNetDriver.cpp'
DESKTOP = 'UnrealTournament/Source/UnrealTournament.Target.cs'
TARGET = 'UnrealTournament/Source/TournamentBrowser.Target.cs'
BYTE_ORDER = 'Engine/Source/Runtime/Online/ICMP/Private/BrowserByteOrder.cpp'
VERSION = {'MajorVersion': 4, 'MinorVersion': 15, 'PatchVersion': 0, 'Changelist': 3228288}


class Fixtures(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ut4-patcher-preflight-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.put('.tournament-browser-port', '')
        self.put('Engine/Build/Build.version', json.dumps(VERSION))
        # Windows-style originals exercise compatibility with the old patchers,
        # which kept byte-exact backups but rewrote patched sources using LF.
        self.put(NETWORK + '/Private/WebSocket.h', '#include <netinet/in.h>\nclass FWebSocket {\n\tint SockFd;\n};\n')
        cpp = ''.join('void FWebSocket::' + signature + '\n{\n#if !PLATFORM_HTML5\n'
                      '    NativeCall();\n#else // PLATFORM_HTML5\n    LegacyCall();\n#endif\n}\n'
                      for signature in ('OnRawRecieve(void* Data)', 'OnRawWebSocketWritable(void* Data)', 'HandlePacket()'))
        cpp += 'bool FWebSocket::Send(uint8* Data, uint32 Size)\n{\n    return true;\n}\nvoid FWebSocket::Close()\n{\n\tclose(SockFd);\n}\n'
        self.put(NETWORK + '/Private/WebSocket.cpp', cpp)
        self.put(NETWORK + '/Private/WebSocketNetDriver.cpp', '#include "WebSocketNetDriver.h"\nvoid Connect()\n{\n\tConnection->SetWebSocket(WebSocket);\n}\nvoid UWebSocketNetDriver::TickDispatch(float DeltaTime)\n{\n    NativeTick();\n}\n')
        self.put(NETWORK + '/Classes/WebSocketNetDriver.h', 'class Driver {\n\tint32 WebSocketPort;\n};\n')
        self.put(SHADERS + '/OpenGLShaderCompiler.cpp', 'void Compile() {\n\tconst int32 MaxSamplers = GetMaxSamplers(Version);\n}\n')
        self.put(SHADERS + '/ShaderFormatOpenGL.cpp', 'enum Versions {\n    UE_SHADER_GLSL_ES2_VER_WEBGL = 61,\n};\n')
        self.put(PACKAGING, 'public class HTML5Platform : Platform\n{\n    string arguments = "--preload . --js-output=";\n}\n')
        self.put(SDK, 'class SDK {\n\t\tpublic static string SetUpEmscriptenConfigFile()\n\t\t{ return "old"; }\n\n\t\tpublic static string EmscriptenVersion() { return "1.36.13"; }\n}\n')
        self.put(REPLAY, '#include "Engine/DemoNetDriver.h"\nvoid Replay() {}\n')
        self.put(DESKTOP, 'class DesktopTarget {}\n')
        (self.root / BYTE_ORDER).parent.mkdir(parents=True)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode())
        return path

    def read(self, name):
        return (self.root / name).read_text(encoding='utf-8-sig')

    def apply(self, name):
        with contextlib.redirect_stdout(io.StringIO()):
            if name == 'configure-legacy.py':
                MODULES[name]['patch'](self.root, HERE / 'TournamentBrowser.Target.cs')
            else:
                MODULES[name]['patch'](self.root)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def reject(self, name):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.apply(name)
        self.assertEqual(self.snapshot(), before, 'rejected preflight changed files or timestamps')

    def backup(self, name, suffix):
        path = self.root / name
        return path.with_suffix(path.suffix + suffix)


class CommonPreflightTests(Fixtures):
    def test_unmarked_roots_rejected_without_any_writes(self):
        (self.root / '.tournament-browser-port').unlink()
        for name in MODULES:
            with self.subTest(patcher=name):
                self.reject(name)

    def test_wrong_engine_versions_rejected_without_any_writes(self):
        for key in ('MajorVersion', 'MinorVersion', 'Changelist'):
            self.put('Engine/Build/Build.version', json.dumps({**VERSION, key: VERSION[key] + 1}))
            for name in MODULES:
                with self.subTest(patcher=name, field=key):
                    self.reject(name)

    def test_all_repeat_runs_preserve_bytes_and_timestamps(self):
        for name in MODULES:
            with self.subTest(patcher=name):
                self.apply(name)
                before = self.snapshot()
                self.apply(name)
                self.assertEqual(self.snapshot(), before)

    def test_conflicting_original_backups_rejected(self):
        for module, source, suffix in (
            ('patch-networking.py', NETWORK + '/Private/WebSocket.h', '.before-tournament-html5'),
            ('patch-webgl-shaders.py', SHADERS + '/ShaderFormatOpenGL.cpp', '.before-tournament-webgl'),
            ('patch-browser-packaging.py', PACKAGING, '.before-tournament-packaging'),
            ('configure-legacy.py', REPLAY, '.before-tournament-html5')):
            with self.subTest(patcher=module):
                backup = self.backup(source, suffix)
                backup.write_text('// another checkout\n' + self.read(source))
                self.reject(module)
                backup.unlink()

    def test_matching_existing_original_backups_preserved(self):
        for module, source, suffix in (
            ('patch-networking.py', NETWORK + '/Private/WebSocket.h', '.before-tournament-html5'),
            ('patch-webgl-shaders.py', SHADERS + '/ShaderFormatOpenGL.cpp', '.before-tournament-webgl'),
            ('patch-browser-packaging.py', PACKAGING, '.before-tournament-packaging'),
            ('configure-legacy.py', REPLAY, '.before-tournament-html5')):
            with self.subTest(patcher=module):
                backup = self.backup(source, suffix)
                backup.write_bytes((self.root / source).read_bytes())
                before = (backup.read_bytes(), backup.stat().st_mtime_ns)
                self.apply(module)
                self.apply(module)
                self.assertEqual((backup.read_bytes(), backup.stat().st_mtime_ns), before)


class NetworkingTests(Fixtures):
    module = 'patch-networking.py'

    def test_fresh_patch_changes_browser_branches_and_preserves_native_code(self):
        source = NETWORK + '/Private/WebSocket.cpp'
        original = (self.root / source).read_bytes()
        self.apply(self.module)
        text = self.read(source)
        self.assertEqual(text.count('    NativeCall();'), 3)
        self.assertNotIn('LegacyCall();', text)
        self.assertIn('OutgoingBuffer.Num() >= 128', text)
        self.assertIn('TournamentReceive.Feed(Chunk, Count,', text)
        self.assertIn('if (SockFd >= 0) close(SockFd);', text)
        self.assertEqual(self.backup(source, '.before-tournament-html5').read_bytes(), original)
        self.assertEqual((self.root / NETWORK / 'Private/BrowserPacketBuffer.h').read_bytes(),
                         (HERE / 'BrowserPacketBuffer.h').read_bytes())

    def test_bad_last_file_does_not_patch_earlier_files_or_copy_header(self):
        self.put(NETWORK + '/Classes/WebSocketNetDriver.h', 'class Driver {};\n')
        self.reject(self.module)
        self.assertFalse((self.root / NETWORK / 'Private/BrowserPacketBuffer.h').exists())

    def test_packet_header_directory_rejected_before_source_changes(self):
        (self.root / NETWORK / 'Private/BrowserPacketBuffer.h').mkdir()
        self.reject(self.module)

    def test_missing_or_duplicate_header_anchor_rejected(self):
        source = NETWORK + '/Private/WebSocket.h'
        original = self.read(source)
        for text in (original.replace('#include <netinet/in.h>', ''), original + '\n\tint SockFd;'):
            self.put(source, text)
            self.reject(self.module)

    def test_missing_branch_cannot_match_next_method(self):
        source = NETWORK + '/Private/WebSocket.cpp'
        self.put(source, self.read(source).replace('#else // PLATFORM_HTML5', '#else', 1))
        self.reject(self.module)

    def test_duplicate_method_rejected(self):
        source = NETWORK + '/Private/WebSocket.cpp'
        self.put(source, self.read(source) + '\nvoid FWebSocket::HandlePacket() {}\n')
        self.reject(self.module)

    def test_destructor_delimits_last_browser_method(self):
        source = NETWORK + '/Private/WebSocket.cpp'
        destructor = 'FWebSocket::~FWebSocket()\n{\n#if !PLATFORM_HTML5\n    NativeCleanup();\n#else // PLATFORM_HTML5\n\tclose(SockFd);\n#endif\n}\n'
        self.put(source, self.read(source).replace('bool FWebSocket::Send', destructor + 'bool FWebSocket::Send'))
        self.apply(self.module)
        self.assertIn('NativeCleanup();', self.read(source))
        self.assertIn('#else // PLATFORM_HTML5\n\tif (SockFd >= 0) close(SockFd);', self.read(source))

    def test_incomplete_previously_patched_file_rejected_without_restore(self):
        self.apply(self.module)
        source = NETWORK + '/Private/WebSocket.cpp'
        self.put(source, self.read(source).replace('TournamentSendOffset += Result;', '/* lost send accounting */'))
        self.reject(self.module)

    def test_partial_marker_without_original_backup_rejected(self):
        self.put(NETWORK + '/Private/WebSocket.h', '#include <netinet/in.h>\n\tint SockFd;\n// TournamentReceive\n')
        self.reject(self.module)


class ShaderTests(Fixtures):
    module = 'patch-webgl-shaders.py'

    def test_fresh_patch_keeps_pixel_only_limit_and_bumps_cache(self):
        source = SHADERS + '/OpenGLShaderCompiler.cpp'
        original = (self.root / source).read_bytes()
        self.apply(self.module)
        self.assertIn('ShaderInput.Target.Frequency == SF_Pixel', self.read(source))
        self.assertIn('? 16 : GetMaxSamplers(Version);', self.read(source))
        self.assertIn('UE_SHADER_GLSL_ES2_VER_WEBGL = 62,', self.read(SHADERS + '/ShaderFormatOpenGL.cpp'))
        self.assertEqual(self.backup(source, '.before-tournament-webgl').read_bytes(), original)

    def test_wrong_cache_version_leaves_compiler_untouched(self):
        self.put(SHADERS + '/ShaderFormatOpenGL.cpp', 'UE_SHADER_GLSL_ES2_VER_WEBGL = 99,\n')
        self.reject(self.module)

    def test_duplicate_patched_statement_rejected(self):
        self.apply(self.module)
        source = SHADERS + '/ShaderFormatOpenGL.cpp'
        self.put(source, self.read(source) * 2)
        self.reject(self.module)

    def test_original_and_patched_statement_together_rejected(self):
        self.apply(self.module)
        source = SHADERS + '/ShaderFormatOpenGL.cpp'
        self.put(source, self.read(source) + '\nUE_SHADER_GLSL_ES2_VER_WEBGL = 61,\n')
        self.reject(self.module)

    def test_legacy_partial_application_can_finish_after_full_preflight(self):
        self.apply(self.module)
        source = SHADERS + '/ShaderFormatOpenGL.cpp'
        (self.root / source).write_bytes(self.backup(source, '.before-tournament-webgl').read_bytes())
        compiler = self.root / SHADERS / 'OpenGLShaderCompiler.cpp'
        before = (compiler.read_bytes(), compiler.stat().st_mtime_ns)
        self.apply(self.module)
        self.assertEqual((compiler.read_bytes(), compiler.stat().st_mtime_ns), before)
        self.assertIn('UE_SHADER_GLSL_ES2_VER_WEBGL = 62,', self.read(source))


class PackagingTests(Fixtures):
    module = 'patch-browser-packaging.py'
    override = 'public override bool StageMovies { get { return false; } }'

    def test_both_changes_and_original_backup(self):
        original = (self.root / PACKAGING).read_bytes()
        self.apply(self.module)
        self.assertEqual(self.read(PACKAGING).count(self.override), 1)
        self.assertEqual(self.read(PACKAGING).count('--no-heap-copy --preload . --js-output='), 1)
        self.assertEqual(self.backup(PACKAGING, '.before-tournament-packaging').read_bytes(), original)

    def test_missing_or_modified_movie_override_not_accepted_as_complete(self):
        self.apply(self.module)
        original = self.read(PACKAGING)
        for modified in (original.replace(self.override, ''), original.replace('return false;', 'return true;')):
            self.put(PACKAGING, modified)
            self.reject(self.module)

    def test_missing_heap_flag_not_accepted_as_complete(self):
        self.apply(self.module)
        self.put(PACKAGING, self.read(PACKAGING).replace('--no-heap-copy ', ''))
        self.reject(self.module)

    def test_duplicate_or_mixed_preload_and_override_rejected(self):
        self.apply(self.module)
        original = self.read(PACKAGING)
        for extra in ('--preload . --js-output=', '--no-heap-copy --preload . --js-output=', self.override):
            self.put(PACKAGING, original + '\n' + extra)
            self.reject(self.module)

    def test_complete_old_patch_without_backup_remains_idempotent(self):
        self.apply(self.module)
        self.backup(PACKAGING, '.before-tournament-packaging').unlink()
        before = self.snapshot()
        self.apply(self.module)
        self.assertEqual(self.snapshot(), before)


class ConfigureTests(Fixtures):
    module = 'configure-legacy.py'

    def test_fresh_configuration_copies_inputs_and_preserves_originals(self):
        replay_original = (self.root / REPLAY).read_bytes()
        sdk_original = (self.root / SDK).read_bytes()
        desktop_original = (self.root / DESKTOP).read_bytes()
        self.apply(self.module)
        self.assertIn('#include "Engine/DemoNetDriver.h"\n#include "UnrealEngine.h"', self.read(REPLAY))
        self.assertEqual(self.backup(REPLAY, '.before-tournament-html5').read_bytes(), replay_original)
        self.assertEqual(self.backup(SDK, '.before-tournament-html5').read_bytes(), sdk_original)
        self.assertEqual(self.backup(DESKTOP, '.before-tournament-browser').read_bytes(), desktop_original)
        self.assertFalse((self.root / DESKTOP).exists())
        self.assertEqual((self.root / TARGET).read_bytes(), (HERE / 'TournamentBrowser.Target.cs').read_bytes())
        self.assertEqual((self.root / BYTE_ORDER).read_bytes(), (HERE / 'BrowserByteOrder.cpp').read_bytes())

    def test_missing_duplicate_or_commented_replay_anchor_rejects_before_sdk_write(self):
        anchor = '#include "Engine/DemoNetDriver.h"'
        for text in ('// missing\n', anchor + '\n' + anchor, '// ' + anchor):
            self.put(REPLAY, text)
            self.reject(self.module)

    def test_desktop_backup_conflict_rejected_before_any_source_write(self):
        self.backup(DESKTOP, '.before-tournament-browser').write_text('original from another tree')
        self.reject(self.module)

    def test_replay_backup_conflict_is_not_overwritten_even_after_patching(self):
        self.apply(self.module)
        self.backup(REPLAY, '.before-tournament-html5').write_text('unrelated original')
        self.reject(self.module)

    def test_existing_sdk_backup_cannot_clobber_local_changes(self):
        self.apply(self.module)
        self.put(SDK, self.read(SDK) + '\n// newer local edit\n')
        self.reject(self.module)

    def test_duplicate_sdk_anchor_rejected_before_any_write(self):
        self.put(SDK, self.read(SDK) + '\n\t\tpublic static string SetUpEmscriptenConfigFile() {}\n')
        self.reject(self.module)


if __name__ == '__main__':
    unittest.main(verbosity=2)
