// Run through test_convert_asm_to_wasm.py, which generates the fixture adapter.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const fixture = process.env.CONVERTER_FIXTURE_JS;
if (!fixture) throw new Error('Run python3 -B test_convert_asm_to_wasm.py to generate the adapter fixture');
const source = await fs.readFile(fixture, 'utf8');
const wasmModule = await WebAssembly.compile(await fs.readFile(fixture.replace(/\.js$/, '.wasm')));

async function load(overrides = {}) {
  const Module = {wasmModule, ...overrides};
  const context = vm.createContext({Module, WebAssembly, console});
  vm.runInContext(source, context);
  assert.equal(context.Module, Module, 'legacy var Module must preserve the incoming object');
  await Module.gameRuntimeReady;
  return Module;
}

test('legacy guards reject before initialization and after exit; initialized WASM call works', async () => {
  const module = await load({arguments: []});
  assert.throws(() => module.probe(41), /runtime not initialized/);
  module.initialize();
  assert.equal(module.probe(41), 42);
  module.finish();
  assert.throws(() => module.probe(41), /runtime exited/);
});

for (const [name, overrides] of [['absent', {}], ['undefined', {arguments: undefined}]]) {
  test(`${name} arguments become an empty array, not the wrapper arguments object`, async () => {
    const module = await load(overrides);
    assert.ok(Array.isArray(module.arguments));
    assert.equal(module.arguments.length, 0);
  });
}

for (const args of [[], ['DM-DeckTest', '-ResX=1920']]) {
  test(`explicit ${args.length}-element arguments and lifecycle callbacks retain identity`, async () => {
    const preRun = [() => {}], postRun = [() => {}];
    const module = await load({arguments: args, preRun, postRun});
    assert.equal(module.arguments, args);
    assert.equal(module.preRun, preRun);
    assert.equal(module.postRun, postRun);
  });
}

test('converted adapter instantiates against the shared memory and fixed table', async () => {
  const module = await load({arguments: []});
  assert.equal(module.buffer, module.wasmMemory.buffer);
  assert.equal(module.asmLibraryArg.memory, module.wasmMemory);
  assert.equal(module.TOTAL_MEMORY, 16 * 1024 * 1024);
  assert.equal(module.asmLibraryArg.table.length, 1);
  assert.throws(() => module.wasmMemory.grow(1), RangeError);
  assert.throws(() => module.asmLibraryArg.table.grow(1), RangeError);
});
