"""Focused converter tests; no Binaryen install or licensed engine input needed.

Run: python3 -B ports/html5/test_convert_asm_to_wasm.py
The Python harness emits an adapter and runs its JS tests with real WebAssembly.
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
        cls.source.write_text(LEGACY)
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
        self.assertEqual(self.source.read_text(), LEGACY)
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
