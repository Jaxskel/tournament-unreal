"""Focused converter tests; no Binaryen install or licensed engine input needed.

Run: python3 -B ports/html5/test_convert_asm_to_wasm.py
The Python harness emits an adapter and runs its JS tests with real WebAssembly.
Optional CONVERTER_ACTUAL_RUNTIME_JS uses private source setter/_alSourcei bodies
in the miniature adapter. It does not execute the game or copy assets into repo.
"""
import contextlib
import io
import json
import os
import re
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CONVERTER = runpy.run_path(str(HERE / 'convert-asm-to-wasm.py'))


def uint(value):
    result = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


def string(value):
    data = value.encode()
    return uint(len(data)) + data


def section(kind, data):
    return bytes([kind]) + uint(len(data)) + data


def probe_wasm():
    # (import "env" "memory" (memory 256 256))
    # (import "env" "table" (table 1 1 funcref))
    # (func (export "_probe") (param i32) (result i32)
    #   local.get 0 i32.const 1 i32.add)
    memory = string('env') + string('memory') + b'\x02\x01' + uint(256) * 2
    table = string('env') + string('table') + b'\x01\x70\x01\x01\x01'
    body = b'\x00\x20\x00\x41\x01\x6a\x0b'
    return (b'\0asm\x01\0\0\0' + section(1, b'\x01\x60\x01\x7f\x01\x7f') +
            section(2, b'\x02' + memory + table) + section(3, b'\x01\x00') +
            section(7, b'\x01' + string('_probe') + b'\x00\x00') +
            section(10, b'\x01' + uint(len(body)) + body))


# Original bounded audio fixture; preserves the pinned call shapes, not gameplay.
AUDIO_FIXTURE = '''
Module.fixtureCreateSource = function() { return {
  _velocity: [0,0,0], position: [1,2,3], refDistance: 1, maxDistance: 50, rolloffFactor: 0.5,
  get velocity(){return this._velocity},
  set velocity(val){this._velocity[0]=val[0];this._velocity[1]=val[1];this._velocity[2]=val[2];if(this.panner)this.panner.setVelocity(val[0],val[1],val[2])}
}; };
Module.fixtureSpatialize = function(src) {
  var panner=src.panner=AL.currentContext.ctx.createPanner();
  panner.panningModel="equalpower";panner.distanceModel="linear";
  panner.refDistance=src.refDistance;panner.maxDistance=src.maxDistance;panner.rolloffFactor=src.rolloffFactor;
  panner.setPosition(src.position[0],src.position[1],src.position[2]);
  panner.setVelocity(src.velocity[0],src.velocity[1],src.velocity[2]);
  panner.connect(AL.currentContext.gain);src.gain.disconnect();src.gain.connect(panner);
};
'''

# Original miniature fixture reproducing the relevant legacy runtime contracts:
# incoming Module overrides, browser arguments fallback, and export guards.
LEGACY = '''var Module;
if (!Module) Module = {};
var moduleOverrides = {};
for (var key in Module) if (Module.hasOwnProperty(key)) moduleOverrides[key] = Module[key];
if (typeof arguments !== 'undefined') Module.arguments = arguments;
if (!Module.arguments) Module.arguments = [];
Module.preRun = []; Module.postRun = [];
for (var key in moduleOverrides) Module[key] = moduleOverrides[key];
var buffer = Module.buffer;
// Test-only injection; the generated production helper never exposes AL/ctx.
var AL = { currentContext: null, contexts: [] };
Module.fixtureSetAudioContext = function(ctx) { AL.currentContext = ctx ? {ctx: ctx, gain: ctx.fixtureGain, src: {}} : null; };
''' + AUDIO_FIXTURE + '''
Module.asmGlobalArg = {}; Module.asmLibraryArg = {};
var runtimeInitialized = false, runtimeExited = false;
function assert(condition, message) { if (!condition) throw new Error(message); }
// EMSCRIPTEN_START_ASM
var asm=(function(global,env,buffer) {
  "use asm";
  function probe(value) { value=value|0; return (value+1)|0; }
  return {_probe: probe};
})
// EMSCRIPTEN_END_ASM
(Module.asmGlobalArg,Module.asmLibraryArg,buffer);
var realProbe = asm._probe;
asm._probe = function(value) {
  assert(runtimeInitialized, 'runtime not initialized');
  assert(!runtimeExited, 'runtime exited');
  return realProbe(value);
};
Module.probe = asm._probe;
Module.initialize = function() { runtimeInitialized = true; };
Module.finish = function() { runtimeExited = true; };
'''


class ConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ut4-converter-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        cls.source = root / 'Legacy.js'
        cls.output = root / 'converted' / 'Renamed.js'
        cls.legacy = LEGACY
        if os.environ.get('CONVERTER_ACTUAL_RUNTIME_JS'):
            actual = Path(os.environ['CONVERTER_ACTUAL_RUNTIME_JS']).read_text()
            # Validate the entire private runtime profile, not just extracted sites.
            CONVERTER['guard_legacy_audio_velocity'](actual)
            setter = re.search(r'set velocity\(val\)\{[^{}]*\}', actual)
            source_i = re.search(r'function _alSourcei\(source,param,value\)\{.*?\}\}Module\[', actual)
            if not setter or not source_i:
                raise AssertionError('Unexpected private legacy audio body boundaries')
            create_source = AUDIO_FIXTURE.split('Module.fixtureSpatialize =', 1)[0]
            create_source = re.sub(r'set velocity\(val\)\{[^{}]*\}', lambda _: setter[0], create_source)
            actual_fixture = create_source + source_i[0][:-len('Module[')] + '''
Module.fixtureSpatialize = function(src) {
  AL.currentContext.src[1] = src; _alSourcei(1,514,0);
};
'''
            cls.legacy = LEGACY.replace(AUDIO_FIXTURE, actual_fixture)
        cls.source.write_text(cls.legacy)
        cls.memory = Path(str(cls.source) + '.mem')
        cls.memory.write_bytes(b'original-memory-initializer')

        def compile_fixture(command, *, check):
            # Mock only the external compiler; use the real metadata parser and
            # converter, then instantiate the emitted module in Node.
            assert check is True
            assert '--total-memory=16777216' in command
            Path(command[command.index('-o') + 1]).write_bytes(probe_wasm())

        with patch('subprocess.run', side_effect=compile_fixture), contextlib.redirect_stdout(io.StringIO()):
            CONVERTER['convert'](cls.source, cls.output, root / 'binaryen', 16)

    def test_preserves_source_and_original_memory_basename(self):
        self.assertEqual(self.source.read_text(), self.legacy)
        self.assertEqual((self.output.parent / 'Legacy.js.mem').read_bytes(), self.memory.read_bytes())
        self.assertFalse((self.output.parent / 'Renamed.js.mem').exists())

    def test_parses_actual_memory_and_table_imports(self):
        metadata = json.loads(self.output.with_suffix('.wasm-imports.json').read_text())
        self.assertEqual(metadata, {
            'env.memory': {'initial': 256, 'maximum': 256},
            'env.table': {'initial': 1, 'maximum': 1},
        })

    def test_generated_adapter_behavior_in_javascript(self):
        result = subprocess.run(
            ['node', '--test', str(HERE / 'converter-runtime.test.mjs')],
            env={**os.environ, 'CONVERTER_FIXTURE_JS': str(self.output)},
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')


class CubemapExtensionTests(unittest.TestCase):
    def test_enables_extension_once_without_removing_other_extensions(self):
        source = 'var automaticallyEnabledExtensions=["OES_texture_half_float","WEBGL_depth_texture","EXT_shader_texture_lod"];rest();'
        patcher = CONVERTER['enable_cubemap_mips']
        result = patcher(source)
        self.assertIn('"OES_fbo_render_mipmap"', result)
        self.assertEqual(patcher(result), result)
        self.assertEqual(result.count('OES_fbo_render_mipmap'), 1)
        self.assertTrue(result.endswith(';rest();'))

    def test_rejects_changed_or_ambiguous_gl_profiles(self):
        for source in ('initExtensions:function(){}',
                       'var automaticallyEnabledExtensions=[];',
                       'var automaticallyEnabledExtensions=[];var automaticallyEnabledExtensions=[];'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                CONVERTER['enable_cubemap_mips'](source)

    def test_preserves_programs_without_gl(self):
        self.assertEqual(CONVERTER['enable_cubemap_mips'](LEGACY), LEGACY)


class AudioVelocityTests(unittest.TestCase):
    def test_exact_profile_is_idempotent_and_only_inserts_guards(self):
        patcher = CONVERTER['guard_legacy_audio_velocity']
        result = patcher(AUDIO_FIXTURE)
        self.assertEqual(patcher(result), result)
        self.assertEqual(result.replace('&&typeof this.panner.setVelocity==="function"', '')
                         .replace('if(typeof panner.setVelocity==="function")', ''), AUDIO_FIXTURE)
        self.assertEqual(patcher('unrelated();'), 'unrelated();')

    def test_unknown_duplicate_and_incomplete_profiles_are_rejected(self):
        for source in (AUDIO_FIXTURE + 'listener.setVelocity(1,2,3);',
                       AUDIO_FIXTURE * 2,
                       AUDIO_FIXTURE.replace('if(this.panner)this.panner.setVelocity(val[0],val[1],val[2])', ''),
                       AUDIO_FIXTURE.replace('src.velocity[2]', 'src.velocity[3]')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                CONVERTER['guard_legacy_audio_velocity'](source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
