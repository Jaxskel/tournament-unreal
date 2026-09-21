"""Convert the matching legacy asm.js engine without changing its C/C++ ABI.

Experimental: no Binaryen optimization passes (the pinned converter's -O2 produced
invalid i64 code in the regression probe). The source asm.js is already optimized.
The launcher must asynchronously compile output.wasm and set Module.wasmModule
before loading the converted JS. Epic-generated code stays outside this repo.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def imports(data):
    if data[:8] != b'\0asm\x01\0\0\0':
        raise ValueError('Expected WebAssembly version 1')
    offset = 8

    def uint():
        nonlocal offset
        result = 0
        for shift in range(0, 35, 7):
            byte = data[offset]; offset += 1
            result |= (byte & 127) << shift
            if not byte & 128:
                return result
        raise ValueError('Oversized Wasm integer')

    def string():
        nonlocal offset
        size = uint(); value = data[offset:offset + size].decode('utf-8'); offset += size
        return value

    def limits():
        flags = uint()
        if flags not in (0, 1):
            raise ValueError('Unexpected shared or 64-bit Wasm limits')
        minimum = uint(); maximum = uint() if flags else None
        return {'initial': minimum, 'maximum': maximum}

    result = {}
    while offset < len(data):
        section = data[offset]; offset += 1
        size = uint(); end = offset + size
        if end > len(data):
            raise ValueError('Truncated Wasm section')
        if section == 2:
            for _ in range(uint()):
                module, name = string(), string()
                kind = data[offset]; offset += 1
                if kind == 0:
                    uint()
                elif kind == 1:
                    element = data[offset]; offset += 1
                    if element != 0x70:
                        raise ValueError('Expected function table')
                    result[f'{module}.{name}'] = limits()
                elif kind == 2:
                    result[f'{module}.{name}'] = limits()
                elif kind == 3:
                    offset += 2
                else:
                    raise ValueError('Unsupported Wasm import')
            if offset != end:
                raise ValueError('Invalid import section')
            return result
        offset = end
    raise ValueError('No Wasm imports')


def convert(source, output, binaryen, memory_mib):
    source, output, binaryen = Path(source), Path(output), Path(binaryen)
    if source.resolve() == output.resolve():
        raise ValueError('Preserve the validated original asm.js output')
    text = source.read_text(encoding='utf-8')
    start = text.index('// EMSCRIPTEN_START_ASM')
    end = text.index('// EMSCRIPTEN_END_ASM', start)
    body = text[start:end].split('var asm=(', 1)[1].strip()
    if not body.startswith('function(') or not body.endswith(')'):
        raise ValueError('Unexpected legacy asm.js wrapper')
    output.parent.mkdir(parents=True, exist_ok=True)
    asm = output.with_suffix('.asm.js')
    asm.write_text(body[:-1].replace('function(', 'function asmModule(', 1) + '\n', encoding='utf-8')
    wasm = output.with_suffix('.wasm')
    executable = binaryen / 'bin' / ('asm2wasm.exe' if (binaryen / 'bin/asm2wasm.exe').exists() else 'asm2wasm')
    memory = Path(str(source) + '.mem')
    if not memory.is_file():
        raise ValueError('Matching memory initializer is required')
    subprocess.run([str(executable), str(asm), f'--total-memory={memory_mib * 1024 * 1024}',
        '-o', str(wasm)], check=True)
    metadata = imports(wasm.read_bytes())
    memory_limits, table_limits = metadata['env.memory'], metadata['env.table']
    if memory_limits['initial'] * 65536 != memory_mib * 1024 * 1024:
        raise ValueError('Unexpected Wasm memory size')
    prefix = '''// Original adapter: preserve the legacy runtime's memory and import ABI.
var Module = typeof Module !== 'undefined' ? Module : {};
Module.gameRuntimeReady = (async function(Module) {
if (!Module.wasmModule) throw new Error('Compile the Wasm module before loading the game runtime');
// The legacy browser prologue must not adopt this wrapper's arguments object.
if (Module.arguments === undefined) Module.arguments = [];
Module.wasmMemory = Module.wasmMemory || new WebAssembly.Memory(MEMORY_LIMITS);
Module.buffer = Module.wasmMemory.buffer;
Module.TOTAL_MEMORY = Module.buffer.byteLength;
// AL stays inside the legacy closure. Resolve its active context on every
// capture, including after context recreation; never resume retired contexts.
// Result is a context state, not proof of audible playback.
Module.resumeBrowserAudio = function() {
  function activeContext() {
    return typeof AL !== 'undefined' && AL && AL.currentContext && AL.currentContext.ctx;
  }
  try {
    var ctx = activeContext();
    if (!ctx) return Promise.resolve('unavailable');
    // WebKit also exposes recoverable interruptions. Attempt once per gesture;
    // an ongoing system interruption may keep resume pending or reject it.
    if (ctx.state !== 'suspended' && ctx.state !== 'interrupted') return Promise.resolve(ctx.state || 'unavailable');
    if (typeof ctx.resume !== 'function') return Promise.resolve('unavailable');
    // This call must execute synchronously in the user's capture gesture.
    return Promise.resolve(ctx.resume()).then(function() {
      return activeContext() === ctx ? (ctx.state || 'unavailable') : 'context-changed';
    });
  } catch (error) { return Promise.reject(error); }
};
'''.replace('MEMORY_LIMITS', json.dumps(memory_limits))
    replacement = '''// EMSCRIPTEN_START_ASM
var asm=await (async function(global,env,buffer) {
  if (buffer !== Module.wasmMemory.buffer) throw new Error('Mismatched game memory');
  env.memory = Module.wasmMemory;
  env.table = new WebAssembly.Table(TABLE_LIMITS);
  env.__memory_base = 0; env.__table_base = 0;
  var instance = await WebAssembly.instantiate(Module.wasmModule, {
    env: env, global: global, 'global.Math': Math,
    asm2wasm: {'f64-to-int': function(value) { return value|0; }}
  });
  // Legacy ASSERTIONS installs guards by replacing properties on the asm object.
  return Object.assign({}, instance.exports);
})
'''.replace('TABLE_LIMITS', json.dumps(dict(table_limits, element='anyfunc')))
    suffix = '''\n}).call(globalThis, Module);
Module.gameRuntimeReady.catch(function(error) {
  if (Module.onAbort) Module.onAbort(error);
  console.error(error);
});
'''
    output.write_text(prefix + text[:start] + replacement + text[end:] + suffix, encoding='utf-8')
    # The unchanged old runtime loads this initializer exactly once. Do not
    # embed it in Wasm too: legacy ASSERTIONS correctly rejects prefilled memory.
    # Keep the original basename because its loader embeds that name.
    destination = output.parent / memory.name
    if destination.resolve() != memory.resolve():
        shutil.copy2(memory, destination)
    output.with_suffix('.wasm-imports.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'javascript': str(output), 'wasm': str(wasm), 'memory': memory_limits,
        'table': table_limits, 'status': 'converted; runtime verification required'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_js')
    parser.add_argument('output_js')
    parser.add_argument('--binaryen', required=True)
    parser.add_argument('--memory-mib', type=int, choices=[16,256,512,1024,1536,2048], default=1536)
    args = parser.parse_args()
    convert(args.source_js, args.output_js, args.binaryen, args.memory_mib)
