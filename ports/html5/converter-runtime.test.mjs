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
  assert.equal(context.AL, undefined, 'AL must remain closure-local');
  assert.equal(Module.AL, undefined, 'do not expose the audio backend');
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

test('audio activation tolerates missing/closed/running contexts and missing resume', async () => {
  const module = await load();
  assert.equal(await module.resumeBrowserAudio(), 'unavailable');
  for (const state of ['closed', 'running', 'unknown-future-state']) {
    module.fixtureSetAudioContext({state, resume() { assert.fail('must not resume this state'); }});
    assert.equal(await module.resumeBrowserAudio(), state);
  }
  for (const state of ['suspended', 'interrupted']) {
    module.fixtureSetAudioContext({state});
    assert.equal(await module.resumeBrowserAudio(), 'unavailable');
  }
  module.fixtureSetAudioContext(null);
  assert.equal(await module.resumeBrowserAudio(), 'unavailable');
});

for (const state of ['suspended', 'interrupted']) {
test(`audio resume from ${state} is synchronous, retries on capture only, and reports actual state`, async () => {
  const module = await load();
  let calls = 0;
  const ctx = {state, resume() { assert.equal(this, ctx); calls++; return Promise.resolve(); }};
  module.fixtureSetAudioContext(ctx);
  const first = module.resumeBrowserAudio();
  assert.equal(calls, 1, 'resume must happen before returning to the gesture handler');
  assert.equal(await first, state, 'fulfilled resume is not proof of running');
  assert.equal(calls, 1, 'an unchanged state must not trigger an automatic retry loop');
  ctx.resume = function() { calls++; this.state = 'running'; return Promise.resolve(); };
  assert.equal(await module.resumeBrowserAudio(), 'running');
  assert.equal(calls, 2);
});

test(`recreated context replaces ${state} context during pending resume`, async () => {
  const module = await load();
  let finish, oldCalls = 0, newCalls = 0;
  const old = {state, resume() { oldCalls++; return new Promise(resolve => { finish = resolve; }); }};
  const current = {state, resume() { newCalls++; this.state = 'running'; }};
  module.fixtureSetAudioContext(old);
  const pending = module.resumeBrowserAudio();
  module.fixtureSetAudioContext(current);
  old.state = 'running'; finish();
  assert.equal(await pending, 'context-changed');
  assert.equal(await module.resumeBrowserAudio(), 'running');
  assert.equal(oldCalls, 1); assert.equal(newCalls, 1);
});

test(`resume from ${state}: rejection and synchronous exception remain catchable and permit retry`, async () => {
  const module = await load();
  let calls = 0;
  const ctx = {state, resume() {
    calls++;
    if (calls === 1) return Promise.reject(Error('fixture autoplay rejection'));
    if (calls === 2) throw Error('fixture synchronous rejection');
    this.state = 'running';
  }};
  module.fixtureSetAudioContext(ctx);
  await assert.rejects(module.resumeBrowserAudio(), /autoplay rejection/);
  await assert.rejects(module.resumeBrowserAudio(), /synchronous rejection/);
  assert.equal(await module.resumeBrowserAudio(), 'running');
  assert.equal(calls, 3);
});
}

test('a suspension that transitions to interrupted can be resumed on the next capture', async () => {
  const module = await load();
  let calls = 0;
  const ctx = {state: 'suspended', resume() {
    this.state = ++calls === 1 ? 'interrupted' : 'running';
    return Promise.resolve();
  }};
  module.fixtureSetAudioContext(ctx);
  assert.equal(await module.resumeBrowserAudio(), 'interrupted');
  assert.equal(calls, 1);
  assert.equal(await module.resumeBrowserAudio(), 'running');
  assert.equal(calls, 2);
});

for (const velocityAPI of ['missing', 'non-callable', 'legacy']) {
test(`spatial source creation and updates with ${velocityAPI} velocity API preserve the audio graph`, async () => {
  const module = await load();
  const calls = [];
  const output = {};
  const panner = {
    setPosition(...xyz) { calls.push(['position', ...xyz]); },
    connect(target) { assert.equal(target, output); calls.push(['panner-connect']); },
  };
  if (velocityAPI === 'non-callable') panner.setVelocity = null;
  if (velocityAPI === 'legacy') panner.setVelocity = function(...xyz) {
    assert.equal(this, panner); calls.push(['velocity', ...xyz]);
  };
  module.fixtureSetAudioContext({fixtureGain: output, createPanner() { return panner; }});
  const src = module.fixtureCreateSource();
  src.gain = {
    disconnect() { calls.push(['gain-disconnect']); },
    connect(target) { assert.equal(target, panner); calls.push(['gain-connect']); },
  };
  const storedVelocity = src.velocity;
  src.velocity = [4,5,6]; // Relative source: no panner yet.
  module.fixtureSpatialize(src); // Original failure was here in _alSourcei.
  src.velocity = [7,8,9]; // The second removed API call must also be safe.
  assert.equal(src.velocity, storedVelocity);
  assert.deepEqual(Array.from(storedVelocity), [7,8,9]);
  assert.equal(src.panner, panner);
  assert.equal(panner.panningModel, 'equalpower');
  assert.equal(panner.distanceModel, 'linear');
  for (const property of ['refDistance', 'maxDistance', 'rolloffFactor']) {
    assert.equal(panner[property], src[property]);
  }
  assert.deepEqual(calls, [
    ['position', 1,2,3],
    ...(velocityAPI === 'legacy' ? [['velocity', 4,5,6]] : []),
    ['panner-connect'], ['gain-disconnect'], ['gain-connect'],
    ...(velocityAPI === 'legacy' ? [['velocity', 7,8,9]] : []),
  ]);
  if (velocityAPI === 'missing') assert.equal('setVelocity' in panner, false, 'no fake method installed');
});
}

test('velocity guards do not swallow real panner exceptions', async () => {
  const module = await load();
  const failure = Error('actual method failed');
  const panner = {setPosition() {}, setVelocity() { throw failure; }};
  module.fixtureSetAudioContext({createPanner() { return panner; }});
  const src = module.fixtureCreateSource();
  assert.throws(() => module.fixtureSpatialize(src), error => error === failure);
  assert.throws(() => { src.velocity = [4,5,6]; }, error => error === failure);
  assert.deepEqual(Array.from(src.velocity), [4,5,6]);
});
