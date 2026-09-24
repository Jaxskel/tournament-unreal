import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_ARGUMENTS, engineArguments, argumentsForMode, readMode, fit16by9, readResolution, FrameMetrics, validateManifest, validateGraphicsLimits } from '../core.mjs';

const url = 'http://127.0.0.1:8000/client/runtime.json';
const manifest = () => ({ version: 1, format: 'asmjs', engine: 'game.js', files: { 'game.js': './engine/game.js' }, websocketUrl: 'ws://127.0.0.1:9080/game' });
test('resolution is explicit, persisted defensively and never derived from window size', () => {
  assert.equal(readResolution({ getItem: () => '1440p' }), '1440p');
  assert.equal(readResolution({ getItem: () => '720p' }), '1080p');
  assert.equal(readResolution({ getItem: () => { throw Error('disabled'); } }), '1080p');
  assert.deepEqual(engineArguments([...DEFAULT_ARGUMENTS, '-ResX=800', '-resy=600', '-Fullscreen', '-log'], '1440p'),
    [...DEFAULT_ARGUMENTS, '-log', '-ResX=2560', '-ResY=1440', '-ForceRes', '-Windowed']);
  for (const [w,h] of [[400,900], [3440,1440], [1920,1080]]) {
    const fitted = fit16by9(w,h);
    assert.ok(fitted.width <= w && fitted.height <= h);
    assert.equal(fitted.width / fitted.height, 16/9);
  }
});
test('manifest resolves only same-origin assets, validates memory and supports explicit WASM', () => {
  const raw = manifest();
  const parsed = validateManifest(raw, url);
  assert.equal(parsed.files['game.js'], 'http://127.0.0.1:8000/client/engine/game.js');
  assert.deepEqual(parsed.arguments, DEFAULT_ARGUMENTS);
  assert.equal(parsed.totalMemory, undefined);
  assert.equal(validateManifest({ ...raw, totalMemory: 1610612736 }, url).totalMemory, 1610612736);
  for (const change of [
    { version: 2 }, { format: 'unknown' }, { dataScripts: ['missing.js'] },
    { files: { 'game.js': 'https://example.org/engine.js' } }, { files: { 'game.js': 'javascript:alert(1)' } },
    { totalMemory: -1 }, { totalMemory: 16777217 }, { arguments: 'bad' },
    { websocketUrl: 'https://example.org/game' }, { websocketUrl: 'ws://localhost/game?destination=x' },
    { format: 'wasm' }, { initializationTimeoutMs: 0 }, { supportScripts: ['game.js'] }
  ]) assert.throws(() => validateManifest({ ...raw, ...change }, url), /runtime.json/);
  assert.throws(() => validateManifest(raw, 'https://example.org/runtime.json'), /HTTPS requires/);
  const wasm = validateManifest({ ...raw, format:'wasm', files: { ...raw.files, 'game.wasm':'game.wasm' }, wasmBinary:'game.wasm' }, url);
  assert.equal(wasm.wasmBinary, 'game.wasm');
});
test('metrics count paired completed engine callbacks only; stale and uninitialized differ', () => {
  const metrics = new FrameMetrics();
  assert.deepEqual(metrics.snapshot(10000), { state:'uninitialized', frames:0 });
  metrics.end(10);
  assert.equal(metrics.snapshot(10).frames, 0);
  metrics.begin(0); metrics.end(2);
  assert.equal(metrics.snapshot(2).state, 'warming');
  for (let i=1; i<=120; i++) { metrics.begin(i*10); metrics.end(i*10+2); }
  const measured = metrics.snapshot(1202);
  assert.equal(measured.frames, 121);
  assert.equal(measured.fps, 100);
  assert.equal(measured.cpuMs, 2);
  assert.equal(measured.p95Ms, 10);
  assert.equal(metrics.snapshot(3000).state, 'stalled');
  metrics.reset();
  assert.equal(metrics.snapshot(3000).state, 'uninitialized');
});
test('WebGL preflight enforces all three sampler limits including invalid queries', () => {
  const valid = { fragment:16,vertex:8,combined:24 };
  assert.deepEqual(validateGraphicsLimits(valid),valid);
  for (const change of [{ fragment:15 },{ vertex:7 },{ combined:23 },{ fragment:undefined }]) {
    assert.throws(() => validateGraphicsLimits({ ...valid,...change }), /Unsupported GPU\/WebGL/);
  }
});

test('operator multiplayer arguments are separate, validated identically and receive fixed resolution', () => {
  const raw=manifest();
  const practice=['/OperatorPractice?BotFill=7','-log'];
  const multiplayer=['127.0.0.1:7787','-ResX=800','-ResY=600','-Fullscreen'];
  const parsed=validateManifest({ ...raw,arguments:practice,multiplayerArguments:multiplayer },url);
  assert.deepEqual(argumentsForMode(parsed,'practice'),practice);
  for (const mode of ['practice','multiplayer']) {
    for (const [resolution,dimensions] of [['1080p',[1920,1080]],['1440p',[2560,1440]]]) {
      const args=engineArguments(argumentsForMode(parsed,mode),resolution);
      assert.equal(args[0],mode==='practice'?practice[0]:multiplayer[0]);
      assert.deepEqual(args.slice(-4),['-ResX='+dimensions[0],'-ResY='+dimensions[1],'-ForceRes','-Windowed']);
      assert.equal(args.filter(arg=>arg.startsWith('-ResX=')).length,1);
      assert.ok(!args.includes('-Fullscreen'));
    }
  }
  assert.equal(parsed.websocketUrl,'ws://127.0.0.1:9080/game');
  assert.deepEqual(multiplayer,['127.0.0.1:7787','-ResX=800','-ResY=600','-Fullscreen']);
  for (const invalid of [null,'127.0.0.1:7787',[17],['host\0evil'],{}]) {
    assert.throws(()=>validateManifest({ ...raw,multiplayerArguments:invalid },url),/multiplayerArguments/);
    if (invalid!==null) assert.throws(()=>validateManifest({ ...raw,arguments:invalid },url),/arguments/);
  }
  for (const extra of [{},{ multiplayerArguments:[] }]) {
    const unavailable=validateManifest({ ...raw,...extra },url);
    assert.throws(()=>argumentsForMode(unavailable,'multiplayer'),/Multiplayer unavailable/);
    assert.deepEqual(argumentsForMode(unavailable,'practice'),DEFAULT_ARGUMENTS);
  }
  assert.throws(()=>argumentsForMode(parsed,'127.0.0.1:9999'),/Unknown launch mode/);
});

test('mode persistence accepts only the two modes and tolerates unavailable storage', () => {
  for (const [saved,expected] of [['multiplayer','multiplayer'],['practice','practice'],['arbitrary-host','practice'],[null,'practice']]) {
    assert.equal(readMode({ getItem:()=>saved }),expected);
  }
  assert.equal(readMode({ getItem:()=>{ throw Error('disabled'); } }),'practice');
  assert.equal(readMode(undefined),'practice');
});

test('direct package list is explicit, unique and cannot alias bootstrap assets', () => {
  const raw={...manifest(),dataScripts:['pack.js'],files:{'game.js':'game.js','pack.js':'pack.js','archive':'payload.bin','alias':'game.js','memory':'game.mem','wasm':'game.wasm'},memoryInitializer:'memory'};
  assert.deepEqual(validateManifest(raw,url).packageFiles,[]);
  assert.deepEqual(validateManifest({...raw,packageFiles:['archive']},url).packageFiles,['archive']);
  for(const packageFiles of [null,'archive',{},[null],['unknown'],['archive','archive'],['game.js'],['pack.js'],['memory'],['alias']]) {
    assert.throws(()=>validateManifest({...raw,packageFiles},url),/runtime.json/);
  }
  assert.throws(()=>validateManifest({...raw,dataScripts:[],packageFiles:['archive']},url),/data script/);
  for(const wasmKey of ['wasmModule','wasmBinary']) assert.throws(()=>validateManifest({...raw,format:'wasm',[wasmKey]:'wasm',packageFiles:['wasm']},url),/WASM/);
});
