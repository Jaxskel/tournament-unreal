import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';
import { chromium } from 'playwright';
import { DEFAULT_ARGUMENTS, validateGraphicsLimits } from '../core.mjs';
import { BINDINGS } from '../bindings.mjs';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
let server, browser, origin, mode = 'normal';
let requests = [];
function manifest() {
  const value = { version:1, format:'asmjs', engine:'engine.js', supportScripts:['support.js'], dataScripts:['game.data.js'],
    files: { 'support.js':'tests/fixtures/support.js', 'game.data.js':'tests/fixtures/game.data.js', 'fixture.data':'fixture.data',
      'fixture.mem':'fixture.mem', 'engine.js':'tests/fixtures/engine.js' },
    memoryInitializer:'fixture.mem', totalMemory:1610612736, websocketUrl:'ws://127.0.0.1:9080/game', initializationTimeoutMs:1500 };
  if (mode === 'invalid') value.version = 9;
  if (mode === 'multiplayer') value.multiplayerArguments = ['127.0.0.1:7787','-ResX=800','-Fullscreen'];
  if (mode === 'missing') value.files['fixture.data'] = 'missing.data';
  if (mode === 'throw' || mode === 'stall') value.files['engine.js'] = 'fault.js';
  if (mode === 'wasm') {
    value.format = 'wasm'; value.wasmBinary = 'fixture.wasm';
    value.files['fixture.wasm'] = 'fixture.wasm'; delete value.memoryInitializer; delete value.files['fixture.mem'];
  }
  if (mode === 'converted' || mode === 'bad-wasm') {
    value.format = 'wasm'; value.wasmModule = 'fixture.wasm'; value.files['fixture.wasm'] = 'fixture.wasm';
    value.files['engine.js'] = 'tests/fixtures/converted.js';
  }
  if (mode === 'async-fail') value.files['engine.js'] = 'fault.js';
  if (mode === 'bindings') {
    value.bindings = Object.keys(BINDINGS);
    value.files['bindings.js'] = 'tests/fixtures/bindings.js'; value.supportScripts.push('bindings.js');
  }
  if (mode === 'audio') {
    value.files['audio.js'] = 'tests/fixtures/audio.js'; value.supportScripts.push('audio.js');
  }
  return value;
}
before(async () => {
  server = createServer(async (req,res) => {
    const path = new URL(req.url, 'http://test').pathname;
    requests.push(path);
    if (path === '/runtime.json') {
      res.setHeader('Content-Type','application/json');
      if (mode === 'no-manifest') { res.writeHead(404).end(); return; }
      res.end(JSON.stringify(manifest())); return;
    }
    if (path === '/fixture.data') {
      res.setHeader('Content-Type','application/octet-stream'); res.setHeader('Content-Length','131072');
      res.write(Buffer.alloc(32768, 70));
      let remaining = 3;
      const interval = setInterval(() => { res.write(Buffer.alloc(32768, 70)); if (!--remaining) { clearInterval(interval); res.end(); } }, 80);
      res.on('close', () => clearInterval(interval)); return;
    }
    if (path === '/fixture.mem') { res.end('FIXTURE MEMORY'); return; }
    if (path === '/fixture.wasm') { res.end(mode === 'bad-wasm' ? Buffer.from('invalid wasm') : Buffer.from([0,97,115,109,1,0,0,0])); return; }
    if (path === '/fault.js') { res.end(mode === 'throw' ? 'throw new Error("fixture startup exception")' : mode === 'async-fail' ? 'Module.gameRuntimeReady = new Promise((resolve,reject) => setTimeout(() => reject(Error("fixture async failure")),100));' : '/* intentionally no lifecycle hooks */'); return; }
    const file = resolve(root, '.' + (path === '/' ? '/index.html' : path));
    if (!file.startsWith(root + sep) && file !== root) { res.writeHead(403).end(); return; }
    try {
      res.setHeader('Content-Type', ({ '.html':'text/html', '.mjs':'text/javascript', '.js':'text/javascript', '.css':'text/css' })[extname(file)] ?? 'application/octet-stream');
      res.end(await readFile(file));
    } catch { res.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  origin = 'http://127.0.0.1:' + server.address().port;
  browser = await chromium.launch({ headless:!process.env.HEADED, ...(process.env.CHROME_CHANNEL ? { channel:process.env.CHROME_CHANNEL } : {}) });
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });
async function session(t, scenario='normal', graphics={}) {
  mode = scenario; requests = [];
  const context = await browser.newContext({ viewport:{ width:1440,height:1000 } });
  t.after(() => context.close());
  if (graphics !== null) await context.addInitScript(options => {
    // Lifecycle fixtures draw a labeled 2D canvas; they do not test a GPU/game.
    // Stub only the runtime's detached preflight canvas, never engine rendering.
    // The separate real-capability test below opts out of this entire hook.
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      if (location.pathname !== '/runtime.html' || this.isConnected || !['webgl','experimental-webgl'].includes(type)) {
        return original.call(this, type, ...args);
      }
      if (options.available === false) return null;
      return {
        MAX_TEXTURE_IMAGE_UNITS: 34930, MAX_VERTEX_TEXTURE_IMAGE_UNITS: 35660, MAX_COMBINED_TEXTURE_IMAGE_UNITS: 35661,
        getParameter(name) { return ({34930:options.fragment ?? 16,35660:options.vertex ?? 8,35661:options.combined ?? 24})[name]; },
        getExtension(name) {
          if (name === 'OES_fbo_render_mipmap') return options.mipmap === false ? null : {};
          if (name === 'WEBGL_lose_context') return {loseContext() {}};
          return null;
        },
      };
    };
  }, graphics);
  const page = await context.newPage(); await page.goto(origin);
  return page;
}
async function waitVisible(page, selector) { await page.locator(selector).waitFor({ state:'visible' }); }
async function launch(page) { await page.locator('#launch').click(); await waitVisible(page,'#resume'); }
const runtime = page => page.frames().find(frame => frame.url().endsWith('/runtime.html'));

test('audio capture runs in the gesture before pointer lock, never waits, and retries nonfatal failures', async t => {
  const page = await session(t, 'audio');
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.evaluate(() => {
    window.audioEvents = [];
    window.addEventListener('message', event => {
      if (event.data?.channel === 'ut4-runtime' && event.data.type === 'audio') audioEvents.push(event.data.detail);
    });
  });
  await launch(page);
  for (const behavior of ['suspended', 'reject', 'throw', 'pending', 'running']) {
    await runtime(page).evaluate(value => { fixture.audioBehavior = value; fixture.audioCalls = []; }, behavior);
    await page.evaluate(() => { audioEvents.length = 0; });
    await page.locator('#capture').click();
    assert.deepEqual(await runtime(page).evaluate(() => fixture.audioCalls), [['audio', true], ['pointer', true]]);
    if (behavior !== 'pending') {
      await page.waitForFunction(() => audioEvents.length === 1);
      const result = await page.evaluate(() => audioEvents[0]);
      assert.equal(result.state, ['reject', 'throw'].includes(behavior) ? 'error' : behavior);
      if (result.state === 'error') assert.match(result.message, /fixture audio/);
    }
    assert.equal(await page.locator('#error').isVisible(), false);
    await page.locator('#menu').click();
  }
  // An older pending attempt must not overwrite the latest capture's state.
  await runtime(page).evaluate(() => fixture.finishAudio('suspended'));
  await runtime(page).evaluate(() => new Promise(resolve => setTimeout(resolve, 30)));
  assert.deepEqual(await page.evaluate(() => audioEvents), [{state: 'running'}]);
  assert.deepEqual(errors, [], 'audio rejection must not become an unhandled engine error');
});

test('capture works without the optional audio adapter', async t => {
  const page = await session(t);
  await launch(page);
  await runtime(page).evaluate(() => {
    Module.canvas.requestPointerLock = () => { fixture.pointerRequested = true; };
  });
  await page.locator('#capture').click();
  assert.equal(await runtime(page).evaluate(() => fixture.pointerRequested), true);
  assert.equal(await page.locator('#error').isVisible(), false);
});

test('fixture lifecycle, ordered scripts, heap override, packet URL, explicit resolution and truthful metrics', async t => {
  const page = await session(t);
  await page.locator('#launch').click();
  await page.waitForFunction(() => document.querySelector('#progress-text').textContent.includes('fixture.data') && document.querySelector('#progress').hasAttribute('value'));
  await waitVisible(page,'#resume');
  const data = await runtime(page).evaluate(() => ({ fixture:fixture.moduleAtStart, order:fixture.order, size:[Module.canvas.width, Module.canvas.height], bytes:fixture.packageBytes }));
  assert.deepEqual(data.order,['support','data-script','engine','data-prerun']);
  assert.equal(data.bytes,131072); assert.equal(data.fixture.totalMemory,1610612736); assert.equal(data.fixture.initialMemory,1610612736);
  assert.equal(data.fixture.websocket.url,'ws://127.0.0.1:9080/game'); assert.equal(data.fixture.websocket.subprotocol,'binary');
  assert.equal(data.fixture.noAudioDecoding,true); assert.equal(data.fixture.noImageDecoding,true);
  assert.equal(data.fixture.arguments[0],DEFAULT_ARGUMENTS[0]);
  assert.deepEqual(data.size,[1920,1080]);
  await page.waitForFunction(() => document.querySelector('#timing').textContent.includes('No engine main-loop'));
  assert.equal(await page.locator('#fps').textContent(),'— engine FPS');
  await page.locator('#resume').click();
  await runtime(page).waitForFunction(() => fixture.paused === false);
  await runtime(page).evaluate(async () => { for(let i=0;i<12;i++) { Module.preMainLoop(); Module.postMainLoop(); await new Promise(r => setTimeout(r,16)); } });
  await page.waitForFunction(() => /^\d/.test(document.querySelector('#fps').textContent));
  await page.waitForFunction(() => document.querySelector('#timing').textContent.includes('paused or stalled'));
  assert.equal(await page.locator('#fps').textContent(),'— engine FPS');
  assert.equal(requests.filter(path => path === '/fixture.data').length,1);
  await runtime(page).evaluate(() => Module.onAbort('fixture abort'));
  await waitVisible(page,'#error'); assert.match(await page.locator('#error').textContent(),/fixture abort/);
  assert.equal(page.frames().length,1);
});

test('1440p persists through reload, viewport/fullscreen resize and settings require relaunch', async t => {
  const page = await session(t);
  await page.locator('#settings').click(); await page.locator('#resolution').selectOption('1440p');
  await page.reload(); await launch(page);
  const sizes = async () => runtime(page).evaluate(() => [Module.canvas.width,Module.canvas.height]);
  assert.deepEqual(await sizes(),[2560,1440]);
  for (const viewport of [{width:800,height:1000},{width:1800,height:800}]) {
    await page.setViewportSize(viewport);
    await page.waitForFunction(() => { const r=document.querySelector('#viewport').getBoundingClientRect(); const s=document.querySelector('#stage').getBoundingClientRect(); return Math.abs(r.width/r.height-16/9)<.001 && Math.abs(r.x+r.width/2-s.x-s.width/2)<1 && Math.abs(r.y+r.height/2-s.y-s.height/2)<1; });
    assert.deepEqual(await sizes(),[2560,1440]);
  }
  await page.locator('#fullscreen').click();
  await page.waitForFunction(() => !!document.fullscreenElement);
  assert.deepEqual(await sizes(),[2560,1440]);
  await page.locator('#fullscreen').click();
  await page.waitForFunction(() => !document.fullscreenElement);
  await page.locator('#settings').click(); await page.locator('#resolution').selectOption('1080p');
  assert.deepEqual(await sizes(),[2560,1440]);
  await page.locator('#close-settings').click();
  await page.locator('#stop').click(); await launch(page);
  assert.deepEqual(await sizes(),[1920,1080]);
});

test('legacy bare abort retains its bounded native diagnostic', async t => {
  const page = await session(t);
  await launch(page);
  await runtime(page).evaluate(() => {
    Module.print('Ensure condition failed: World [Party.cpp] ' + 'x'.repeat(4000));
    Module.onAbort('Error');
  });
  await waitVisible(page, '#error');
  const message = await page.locator('#error').textContent();
  assert.match(message, /Ensure condition failed: World \[Party.cpp\]/);
  assert.match(message, /Engine aborted: Error/);
  assert.ok(message.length < 1900);
  assert.equal(page.frames().length, 1);
});

test('failed-map diagnostic survives secondary renderer ensures', async t => {
  const page = await session(t);
  await launch(page);
  await runtime(page).evaluate(() => {
    Module.print('LogLoad:Error: Failed to enter DM-DeckTest: missing package');
    Module.print('Ensure condition failed: CVS.bTimesSet [SceneView.cpp]');
    Module.onAbort('Error');
  });
  await waitVisible(page, '#error');
  assert.match(await page.locator('#error').textContent(), /Failed to enter DM-DeckTest: missing package/);
  assert.doesNotMatch(await page.locator('#error').textContent(), /CVS.bTimesSet/);
});

test('Escape, settings and capture denial cannot strand the menu', async t => {
  const page = await session(t);
  await page.evaluate(() => { window.pointerEvents=[]; window.addEventListener('message',event => { if (['pointer','pointer-error','menu'].includes(event.data?.type)) window.pointerEvents.push(event.data); }); });
  await launch(page); await page.locator('#resume').click();
  await runtime(page).locator('#canvas').focus(); await page.keyboard.press('Escape');
  await waitVisible(page,'#panel'); assert.equal(await runtime(page).evaluate(() => fixture.paused),true);
  await page.locator('#settings').click(); await waitVisible(page,'#settings-panel');
  await page.keyboard.press('Escape'); assert.equal(await page.locator('#settings-panel').isVisible(),false);
  await runtime(page).evaluate(() => { window.realPointerLock = Module.canvas.requestPointerLock; Module.canvas.requestPointerLock=()=>Promise.reject(Error('fixture denial')); });
  await page.locator('#capture').click();
  await page.waitForFunction(() => document.querySelector('#input-status').textContent.includes('denied'));
  await page.locator('#menu').click(); await waitVisible(page,'#resume');
  await t.test('native pointer capture/release (requires a headed browser)', { skip:!process.env.HEADED }, async () => {
  const cdp = await page.context().newCDPSession(page);
  const { targetInfo } = await cdp.send('Target.getTargetInfo');
  // Isolated test context only. Chromium rejects native pointer lock under
  // Playwright's synthetic focus emulation, even when document.hasFocus() is true.
  await cdp.send('Browser.grantPermissions', { origin, browserContextId:targetInfo.browserContextId, permissions:['pointerLock'] });
  await cdp.send('Emulation.setFocusEmulationEnabled', { enabled:false });
  await page.bringToFront();
  await runtime(page).evaluate(() => { Module.canvas.requestPointerLock=window.realPointerLock; });
  await page.locator('#capture').click();
  await page.waitForFunction(() => document.querySelector('#shell').classList.contains('captured'), null, { timeout:5000 }).catch(async error => {
    throw new Error(error.message + ' / ' + JSON.stringify(await page.evaluate(() => window.pointerEvents)));
  });
  // Headless OS Escape behavior differs; exercise the native release event as well as Escape above.
  await runtime(page).evaluate(() => document.exitPointerLock());
  await waitVisible(page,'#panel');
  assert.equal(await page.locator('#shell').evaluate(el => el.classList.contains('captured')),false);
  });
  await page.locator('#stop').click(); assert.equal(page.frames().length,1);
});

for (const [scenario, message] of [['no-manifest',/runtime.json: HTTP 404/], ['invalid',/version must be 1/], ['missing',/fixture.data: HTTP 404/], ['throw',/fixture startup exception/], ['stall',/initialization timed out|Loading took too long/], ['bad-wasm',/WebAssembly/], ['async-fail',/fixture async failure/]]) {
  test(`${scenario}: visible error, clean retry, no stale runtime state`, async t => {
    const page = await session(t,scenario);
    await page.locator('#launch').click(); await waitVisible(page,'#error');
    assert.match(await page.locator('#error').textContent(),message);
    assert.equal(page.frames().length,1); assert.equal(await page.locator('#capture').isEnabled(),false);
    mode='normal'; await page.locator('#retry').click(); await waitVisible(page,'#resume');
    assert.equal(page.frames().length,2); assert.equal(await page.locator('#error').isVisible(),false);
    await page.locator('#stop').click();
    assert.equal(await page.locator('#launch').isVisible(),true); assert.equal(page.frames().length,1);
  });
}
test('future WASM Module adapter uses actual binary bytes; fixture is not a game build', async t => {
  const page = await session(t,'wasm'); await launch(page);
  assert.equal(await runtime(page).evaluate(() => fixture.wasm),true);
  assert.match(await page.locator('#description').textContent(),/Beta · Features may be incomplete/);
});
test('converted legacy WASM compiles before engine script, retains mem and waits for async postRun', async t => {
  const page = await session(t,'converted');
  await page.locator('#launch').click();
  await page.waitForFunction(() => {
    const child = document.querySelector('iframe')?.contentWindow;
    return !!child?.Module?.gameRuntimeReady;
  });
  assert.equal(await page.locator('#resume').isVisible(),false);
  await waitVisible(page,'#resume');
  assert.equal(await runtime(page).evaluate(() => fixture.converted),true);
  assert.match(await page.locator('#engine-resolution').textContent(),/getters unavailable/);
  assert.equal(await page.locator('#fps').textContent(),'— engine FPS');
  assert.equal(requests.filter(path => path === '/fixture.mem').length,1);
  assert.equal(requests.filter(path => path === '/fixture.wasm').length,1);
});
for (const [name, graphics, message] of [
  ['no context', {available:false}, /WebGL is unavailable/],
  ['fragment limit', {fragment:8}, /Unsupported GPU\/WebGL.*at least 16 fragment, 8 vertex and 24 combined/],
  ['vertex limit', {vertex:4}, /Unsupported GPU\/WebGL.*at least 16 fragment, 8 vertex and 24 combined/],
  ['combined limit', {combined:16}, /Unsupported GPU\/WebGL.*at least 16 fragment, 8 vertex and 24 combined/],
  ['missing cubemap mip extension', {mipmap:false}, /requires WebGL cubemap mip rendering \(OES_fbo_render_mipmap\)/],
]) {
test(`fixture preflight ${name}: rejection before assets and clean retry`, async t => {
  const page = await session(t, 'normal', graphics);
  await page.locator('#launch').click(); await waitVisible(page,'#error');
  assert.match(await page.locator('#error').textContent(),message);
  assert.equal(requests.includes('/fixture.data'),false);
  assert.equal(requests.includes('/tests/fixtures/engine.js'),false);
  assert.equal(page.frames().length,1);
  assert.equal(await page.locator('#retry').isVisible(),true);
  await page.locator('#retry').click(); await waitVisible(page,'#error');
  assert.match(await page.locator('#error').textContent(),message);
  assert.equal(page.frames().length,1);
  assert.equal(requests.includes('/fixture.data'),false);
});
}

test('unstubbed browser capability agrees with production preflight; fixture launch is not gameplay', async t => {
  const page = await session(t, 'normal', null);
  const capability = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl', {antialias:false}) || canvas.getContext('experimental-webgl');
    if (!gl) return null;
    try {
      return {fragment:gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS), vertex:gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS),
        combined:gl.getParameter(gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS), mipmap:!!gl.getExtension('OES_fbo_render_mipmap')};
    } finally { gl.getExtension('WEBGL_lose_context')?.loseContext(); }
  });
  t.diagnostic(JSON.stringify({browser:browser.version(), capability}));
  let rejection;
  if (!capability) rejection = /WebGL is unavailable/;
  else {
    try { validateGraphicsLimits(capability); } catch { rejection = /Unsupported GPU\/WebGL/; }
    if (!rejection && !capability.mipmap) rejection = /requires WebGL cubemap mip rendering \(OES_fbo_render_mipmap\)/;
  }
  if (rejection) {
    await page.locator('#launch').click(); await waitVisible(page,'#error');
    assert.match(await page.locator('#error').textContent(),rejection);
    assert.equal(requests.includes('/fixture.data'),false);
    assert.equal(page.frames().length,1);
  } else {
    await launch(page);
    assert.equal(await page.locator('#error').isVisible(),false);
    assert.equal(await runtime(page).evaluate(() => fixture.packageBytes),131072);
  }
});
test('menu/settings remain scroll-accessible at small viewport sizes', async t => {
  const page = await session(t);
  if (process.env.CAPTURE_UI) {
    await mkdir(resolve(root,'test-results'),{ recursive:true });
    await page.screenshot({ path:resolve(root,'test-results/launcher.png'), fullPage:true });
  }
  await page.setViewportSize({ width:480,height:600 });
  await page.locator('#settings').click();
  await page.locator('#resolution').selectOption('1440p');
  await page.locator('#close-settings').click();
  assert.equal(await page.locator('#settings-panel').isVisible(),false);
  if (process.env.CAPTURE_UI) await page.screenshot({ path:resolve(root,'test-results/launcher-small.png'), fullPage:true });
});
test('optional C bindings defer saved settings until world Ready and apply live resolution without console commands', async t => {
  const page = await session(t,'bindings');
  await page.evaluate(() => {
    localStorage.setItem('tournament.local-ut4.volume','.37');
    localStorage.setItem('tournament.local-ut4.sensitivity','.04');
  });
  await page.reload(); await launch(page); await page.locator('#settings').click();
  assert.equal(await page.locator('#volume').isEnabled(),false);
  assert.deepEqual(await runtime(page).evaluate(() => fixture.nativeCalls),[]);
  assert.equal(await runtime(page).evaluate(() => fixture.paused),false);
  await runtime(page).evaluate(() => { fixture.nativeReady = true; });
  await page.waitForFunction(() => !document.querySelector('#volume').disabled);
  const calls = await runtime(page).evaluate(() => fixture.nativeCalls);
  assert.ok(calls.some(call => call[0] === 'volume' && call[1] === .37));
  assert.ok(calls.some(call => call[0] === 'sensitivity' && call[1] === .04));
  assert.ok(calls.some(call => call[0] === 'release'));
  assert.match(await page.locator('#native-frame').textContent(),/123/);
  await page.locator('#resolution').selectOption('1440p');
  await runtime(page).waitForFunction(() => Module.canvas.width === 2560 && Module.canvas.height === 1440);
  await page.locator('#volume').fill('0.6'); await page.locator('#volume').dispatchEvent('change');
  await page.waitForFunction(() => document.querySelector('#volume-value').textContent === '0.6 · applied');
  assert.equal(await page.evaluate(() => localStorage.getItem('tournament.local-ut4.volume')),'0.6');
  await runtime(page).evaluate(() => {
    fixture.nativeCalls=[];
    fixture.nativeDimensions=[1920,1080];
    fixture.nativeEpoch++; // Simulate travel between polls; nativeReady stays true.
  });
  await runtime(page).waitForFunction(() => fixture.nativeCalls.some(call => call[0] === 'sensitivity' && call[1] === .04)
    && fixture.nativeCalls.some(call => call[0] === 'volume' && call[1] === .6)
    && fixture.nativeCalls.some(call => call[0] === 'resolution' && call[1] === 2560)
    && fixture.nativeCalls.some(call => call[0] === 'release'));
  await page.locator('#close-settings').scrollIntoViewIfNeeded();
  if (process.env.CAPTURE_UI) await page.screenshot({ path:resolve(root,'test-results/engine-settings.png'), fullPage:true });
  await page.setViewportSize({ width:480,height:600 });
  await page.locator('#close-settings').click();
  assert.equal(await page.locator('#settings-panel').isVisible(),false);
});

test('multiplayer is disabled without operator configuration and Practice keeps six-bot arguments', async t => {
  const page=await session(t);
  await page.waitForFunction(()=>document.querySelector('#mode-help').textContent.includes('Multiplayer unavailable'));
  assert.equal(await page.locator('#multiplayer-option').isDisabled(),true);
  assert.equal(await page.locator('#mode').inputValue(),'practice');
  await launch(page);
  assert.equal((await runtime(page).evaluate(()=>Module.arguments))[0],DEFAULT_ARGUMENTS[0]);
  assert.equal(await page.locator('#reconnect').isVisible(),false);
});

test('multiplayer mode survives reload, clean retry and reconnect; Stop permits Practice', async t => {
  const page=await session(t,'multiplayer');
  await page.waitForFunction(()=>!document.querySelector('#multiplayer-option').disabled);
  await page.locator('#mode').selectOption('multiplayer');
  await page.locator('#settings').click(); await page.locator('#resolution').selectOption('1440p');
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#launch').disabled);
  assert.equal(await page.locator('#mode').inputValue(),'multiplayer');
  await launch(page);
  const check=async()=>{
    assert.equal(await page.locator('#mode').inputValue(),'multiplayer');
    assert.equal(await page.locator('#mode').isDisabled(),true);
    const actual=await runtime(page).evaluate(()=>({ args:Module.arguments,websocket:Module.websocket.url,dirty:window.oldRuntimeMarker }));
    assert.deepEqual(actual.args,['127.0.0.1:7787','-ResX=2560','-ResY=1440','-ForceRes','-Windowed']);
    assert.equal(actual.websocket,'ws://127.0.0.1:9080/game');
    assert.equal(actual.dirty,undefined);
    assert.equal(await runtime(page).evaluate(()=>fixture.paused),false);
    assert.equal(await page.locator('#status').textContent(),'Tournament Beta · Select Resume to continue.');
  };
  await check();
  await runtime(page).evaluate(()=>{ window.oldRuntimeMarker=true; Module.onAbort('fixture disconnect'); });
  await waitVisible(page,'#retry'); await page.locator('#retry').click(); await waitVisible(page,'#resume'); await check();
  await runtime(page).evaluate(()=>{ window.oldRuntimeMarker=true; });
  await page.locator('#reconnect').click(); await waitVisible(page,'#resume'); await check();
  await page.locator('#stop').click();
  assert.equal(await page.locator('#mode').isEnabled(),true);
  await page.locator('#mode').selectOption('practice'); await launch(page);
  assert.deepEqual(await runtime(page).evaluate(()=>Module.arguments),[...DEFAULT_ARGUMENTS,'-ResX=2560','-ResY=1440','-ForceRes','-Windowed']);
  assert.equal(await page.evaluate(()=>localStorage.getItem('tournament.local-ut4.mode')),'practice');
});

test('removed multiplayer configuration fails clean reconnect without fallback or asset downloads', async t => {
  const page=await session(t,'multiplayer');
  await page.waitForFunction(()=>!document.querySelector('#multiplayer-option').disabled);
  await page.locator('#mode').selectOption('multiplayer'); await launch(page);
  mode='normal'; requests=[];
  await page.locator('#reconnect').click(); await waitVisible(page,'#error');
  assert.match(await page.locator('#error').textContent(),/Multiplayer unavailable/);
  assert.equal(await page.locator('#mode').inputValue(),'multiplayer');
  assert.ok(!requests.includes('/fixture.data'));
  assert.equal(page.frames().length,1);
  mode='multiplayer';
  await page.locator('#retry').click(); await waitVisible(page,'#resume');
  assert.equal((await runtime(page).evaluate(()=>Module.arguments))[0],'127.0.0.1:7787');
});
