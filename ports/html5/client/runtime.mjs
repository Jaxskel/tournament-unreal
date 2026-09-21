import { RESOLUTIONS, resolutionKey, engineArguments, argumentsForMode, validateManifest, validateGraphicsLimits, FrameMetrics } from './core.mjs';
import { EngineBindings } from './bindings.mjs';

const canvas = document.getElementById('canvas');
const metrics = new FrameMetrics();
const blobs = new Map();
const requests = new Set();
let started = false;
let failed = false;
let initialized = false;
let runtimeInitialized = false;
let bridge = null;
let bridgeReport = null;
let desiredSettings = { resolution: '1080p' };
let inMenu = true;
let launchMode = 'practice';
let pausedByMenu = false;
let requested = RESOLUTIONS['1080p'];
let reportTimer;
let lastResolution = '';
let engineDiagnostic = '';
const pressedKeys = new Map();
const send = (type, detail) => parent.postMessage({ channel: 'ut4-runtime', type, detail }, location.origin);

function fail(error) {
  if (failed) return;
  failed = true;
  clearInterval(reportTimer);
  for (const request of requests) request.abort();
  release();
  try { window.Module?.pauseMainLoop?.(); } catch { /* Frame will be destroyed by parent. */ }
  const message = String(error?.message ?? error);
  send('error', engineDiagnostic ? engineDiagnostic + '\n' + message : message);
}
function enginePrint(level, parts) {
  const line = parts.map(String).join(' ');
  // Legacy DebugBreak throws a bare Error. Retain its preceding native cause
  // so the menu shows the useful failure rather than an opaque WASM stack.
  if (/LogLoad:\s*Error:/i.test(line) || (!engineDiagnostic && /Fatal error:|Ensure condition failed:|Assertion failed:|LogOutputDevice:Error:/.test(line))) {
    engineDiagnostic = line.slice(0, 1800);
  }
  console[level]('[UT4]', ...parts);
}
function release() {
  if (document.pointerLockElement) document.exitPointerLock();
  canvas.blur();
}
function menu() {
  inMenu = true;
  // Release held movement keys before focus leaves the engine document.
  for (const [code, key] of pressedKeys) {
    canvas.dispatchEvent(new KeyboardEvent('keyup', { ...key, code, bubbles: true }));
  }
  pressedKeys.clear();
  bridge?.release();
  release();
  // Only use a matched exported pair. Do not pretend a menu pauses a live server.
  const module = window.Module;
  if (launchMode === 'practice' && !bridge?.names.length && initialized && !pausedByMenu && typeof module?.pauseMainLoop === 'function' && typeof module?.resumeMainLoop === 'function') {
    module.pauseMainLoop(); pausedByMenu = true;
  }
}
function resume() {
  inMenu = false;
  if (pausedByMenu) { pausedByMenu = false; window.Module.resumeMainLoop(); }
  canvas.focus();
}
let audioCaptureAttempt = 0;
function activateBrowserAudio() {
  const attempt = ++audioCaptureAttempt;
  const report = detail => { if (attempt === audioCaptureAttempt && !failed) send('audio', detail); };
  const rejected = error => report({ state: 'error', message: String(error?.message ?? error).slice(0, 500) });
  try {
    const module = window.Module;
    if (typeof module?.resumeBrowserAudio !== 'function') { report({ state: 'unavailable' }); return; }
    // Do not await or defer this call: pointer lock may consume activation.
    // Audio failures are nonfatal, and every subsequent capture retries.
    const result = module.resumeBrowserAudio();
    Promise.resolve(result).then(state => report({ state }), rejected);
  } catch (error) { rejected(error); }
}
window.captureUT4Pointer = function() {
  if (!initialized || failed) return;
  resume();
  activateBrowserAudio();
  if (!canvas.requestPointerLock) { send('pointer-error', 'Pointer lock is unavailable'); return; }
  const denied = error => send('pointer-error', 'Mouse capture denied' + (error?.message ? ': ' + error.name + ' — ' + error.message : '') + '; click the viewport to retry');
  try { canvas.requestPointerLock()?.catch(denied); }
  catch (error) { denied(error); }
};
canvas.addEventListener('click', () => { if (!inMenu) window.captureUT4Pointer(); });
canvas.addEventListener('contextmenu', event => event.preventDefault());
canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); fail('WebGL context lost. Stop or retry the experiment.'); });
document.addEventListener('pointerlockchange', () => {
  const locked = document.pointerLockElement === canvas;
  if (locked && inMenu) { release(); return; }
  if (!locked) menu();
  send('pointer', locked);
});
document.addEventListener('pointerlockerror', () => send('pointer-error', 'Mouse capture denied; click the viewport to retry'));
// Registered before engine listeners: Escape always remains a browser escape hatch.
window.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    event.preventDefault(); event.stopImmediatePropagation(); menu(); send('menu');
  } else if (inMenu) { event.stopImmediatePropagation(); }
  else pressedKeys.set(event.code, { key: event.key, keyCode: event.keyCode, which: event.which, location: event.location });
}, true);
window.addEventListener('keyup', event => pressedKeys.delete(event.code), true);
window.addEventListener('blur', () => {
  // Moving from the frame to a launcher button is not app focus loss. Sending
  // an asynchronous menu event there can cancel a new capture gesture.
  if (initialized && !inMenu && !parent.document.hasFocus()) { menu(); send('menu'); }
});
window.addEventListener('error', event => fail(event.error ?? event.message ?? 'Runtime script failed.'));
window.addEventListener('unhandledrejection', event => fail(event.reason ?? 'Runtime promise rejected.'));
window.addEventListener('pagehide', () => {
  clearInterval(reportTimer);
  for (const request of requests) request.abort();
  for (const value of blobs.values()) URL.revokeObjectURL(value);
});

function download(url, name, index, count) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    requests.add(xhr);
    let watchdog;
    const done = callback => value => { clearTimeout(watchdog); requests.delete(xhr); callback(value); };
    const bad = done(reject);
    const arm = () => {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => { bad(new Error(name + ': no download progress for 60 seconds.')); xhr.abort(); }, 60000);
    };
    xhr.open('GET', url);
    xhr.responseType = 'blob';
    xhr.onprogress = event => {
      arm();
      const total = event.lengthComputable ? event.total : 0;
      send('progress', { loaded: event.loaded, total,
        label: `File ${index}/${count} · ${name} · ${(event.loaded / 1048576).toFixed(1)} MiB${total ? ' / ' + (total / 1048576).toFixed(1) + ' MiB' : ' received (total unknown)'}` });
    };
    xhr.onload = () => {
      if (xhr.status !== 200) { bad(new Error(`${name}: HTTP ${xhr.status}; check runtime.json and asset hosting.`)); return; }
      if (new URL(xhr.responseURL).origin !== location.origin) { bad(new Error(name + ': cross-origin redirect rejected.')); return; }
      if (!xhr.response?.size) { bad(new Error(name + ': empty asset.')); return; }
      if (/text\/html/i.test(xhr.getResponseHeader('Content-Type') ?? '')) { bad(new Error(name + ': server returned HTML instead of an engine asset.')); return; }
      done(resolve)(xhr.response);
    };
    xhr.onerror = () => bad(new Error(name + ': network request failed.'));
    xhr.onabort = () => bad(new Error(name + ': download cancelled.'));
    send('progress', { loaded: 0, total: 0, label: `File ${index}/${count} · ${name} · requesting…` });
    arm(); xhr.send();
  });
}

function resolutionReport() {
  let engine = bridgeReport?.actual ?? null;
  try {
    const lib = window.UE_JSlib;
    if (!engine && typeof lib?.UE_GSystemResolution_ResX === 'function' && typeof lib?.UE_GSystemResolution_ResY === 'function') {
      engine = [lib.UE_GSystemResolution_ResX(), lib.UE_GSystemResolution_ResY()];
    }
  } catch { /* Getters can exist before the native state is initialized. */ }
  const detail = { canvas: [canvas.width, canvas.height], engine,
    matches: canvas.width === requested[0] && canvas.height === requested[1] && (!engine || (engine[0] === requested[0] && engine[1] === requested[1])) };
  const key = JSON.stringify(detail);
  if (key !== lastResolution) { lastResolution = key; send('resolution', detail); }
}

function updateSettings(settings = {}) {
  if (settings.resolution) desiredSettings.resolution = resolutionKey(settings.resolution);
  if (Number.isFinite(settings.volume)) desiredSettings.volume = Math.max(0,Math.min(1,settings.volume));
  if (Number.isFinite(settings.sensitivity)) desiredSettings.sensitivity = Math.max(.005,Math.min(.5,settings.sensitivity));
}
function pollBindings() {
  if (!bridge || !runtimeInitialized) return;
  bridgeReport = bridge.poll(desiredSettings, inMenu);
  const dimensions = RESOLUTIONS[desiredSettings.resolution];
  if (bridgeReport.applied.resolution === desiredSettings.resolution && bridgeReport.actual?.every((size,index) => size === dimensions[index])) {
    requested = dimensions;
    // Native viewport agreement precedes any drawing-buffer update.
    if (canvas.width !== requested[0]) canvas.width = requested[0];
    if (canvas.height !== requested[1]) canvas.height = requested[1];
  }
  send('bindings', bridgeReport);
}
async function start(resolution, settings, mode) {
  if (started) return;
  started = true;
  requested = RESOLUTIONS[resolutionKey(resolution)];
  updateSettings({ resolution, ...settings });
  [canvas.width, canvas.height] = requested;
  const manifestURL = new URL('./runtime.json', location.href).href;
  const response = await fetch(manifestURL, { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(25000) });
  if (!response.ok) throw new Error(`runtime.json: HTTP ${response.status}. Configure a local engine manifest; see client/README.md.`);
  const manifest = validateManifest(await response.json(), manifestURL);
  const args = engineArguments(argumentsForMode(manifest, mode), resolution);
  launchMode = mode;
  send('manifest');
  const probe = document.createElement('canvas');
  const gl = probe.getContext('webgl', { antialias: false }) || probe.getContext('experimental-webgl');
  if (!gl) throw new Error('WebGL is unavailable. Enable browser graphics acceleration or use a supported desktop GPU/browser.');
  try {
    send('graphics', validateGraphicsLimits({ fragment: gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS),
      vertex: gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS), combined: gl.getParameter(gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS) }));
    if (!gl.getExtension('OES_fbo_render_mipmap')) {
      throw new Error('This UT4 build requires WebGL cubemap mip rendering (OES_fbo_render_mipmap). This browser/GPU does not expose it; try a supported desktop browser with graphics acceleration enabled.');
    }
  } finally { gl.getExtension('WEBGL_lose_context')?.loseContext(); }
  const assets = new Map();
  const entries = Object.entries(manifest.files);
  for (let i = 0; i < entries.length; i++) {
    if (failed) return;
    const [name, url] = entries[i];
    assets.set(name, await download(url, name, i + 1, entries.length));
  }
  if (failed) return;
  const scripts = [...manifest.supportScripts, ...manifest.dataScripts, manifest.engine];
  for (const [name, blob] of assets) {
    blobs.set(name, URL.createObjectURL(new Blob([blob], { type: scripts.includes(name) ? 'text/javascript' : name === manifest.wasmBinary ? 'application/wasm' : 'application/octet-stream' })));
  }
  const locateFile = name => {
    if (blobs.has(name)) return blobs.get(name);
    // Some packagers pass the already-resolved URL, others the emitted basename.
    for (const [key, url] of Object.entries(manifest.files)) if (name === url) return blobs.get(key);
    if ([...blobs.values()].includes(name)) return name;
    throw new Error('Runtime requested undeclared asset: ' + name + '. Add its exact emitted name to runtime.json files.');
  };
  const module = window.Module = {
    canvas,
    arguments: args,
    noImageDecoding: true, noAudioDecoding: true,
    elementPointerLock: false,
    forcedAspectRatio: 16 / 9,
    websocket: { url: manifest.websocketUrl, subprotocol: 'binary' },
    locateFile,
    preInit: [() => { [canvas.width, canvas.height] = requested; }],
    preRun: [() => { send('status', 'Preparing engine filesystem and startup arguments…'); resolutionReport(); }],
    postRun: [() => {
      if (failed) return;
      initialized = true; resolutionReport(); send('initialized');
    }],
    preMainLoop: () => { metrics.begin(performance.now()); },
    postMainLoop: () => { metrics.end(performance.now()); },
    onRuntimeInitialized: () => { runtimeInitialized = true; send('status', 'Runtime initialized; waiting for engine postRun…'); },
    onAbort: reason => fail('Engine aborted: ' + reason),
    onExit: code => fail('Engine exited with status ' + code + '.'),
    print: (...parts) => enginePrint('info', parts),
    printErr: (...parts) => enginePrint('error', parts),
    setStatus: value => { if (value) send('status', String(value)); },
    monitorRunDependencies: left => send('status', left ? `Preparing engine · ${left} run dependencies remaining` : 'Engine dependencies resolved; waiting for startup…')
  };
  bridge = new EngineBindings(module, manifest.bindings);
  if (inMenu) bridge.release();
  if (manifest.totalMemory != null) {
    module.TOTAL_MEMORY = manifest.totalMemory;
    module.INITIAL_MEMORY = manifest.totalMemory;
  }
  send('initializing', { timeout: manifest.initializationTimeoutMs });
  if (manifest.memoryInitializer) module.memoryInitializerRequest = { status: 200, response: await assets.get(manifest.memoryInitializer).arrayBuffer() };
  if (manifest.wasmBinary) module.wasmBinary = new Uint8Array(await assets.get(manifest.wasmBinary).arrayBuffer());
  if (manifest.wasmModule) {
    send('progress', { loaded: 0, total: 0, label: 'Downloads complete · compiling converted WASM asynchronously' });
    module.wasmModule = await WebAssembly.compile(await assets.get(manifest.wasmModule).arrayBuffer());
  }
  assets.clear();
  send('progress', { loaded: 0, total: 0, label: 'Downloads complete · compiling and mounting engine assets' });
  reportTimer = setInterval(() => { pollBindings(); send('metrics', metrics.snapshot(performance.now())); resolutionReport(); }, 500);
  for (const name of scripts) {
    if (failed) return;
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = blobs.get(name);
      script.onload = resolve;
      script.onerror = () => reject(new Error(name + ': script could not execute. Check syntax, browser support and CSP blob: permissions.'));
      document.body.append(script);
    });
    if (name === manifest.engine && module.gameRuntimeReady?.then) {
      // Completion/rejection belongs to the async legacy wrapper. Its fulfillment
      // is NOT evidence of postRun or gameplay (run dependencies can remain).
      module.gameRuntimeReady.catch(fail);
    }
  }
}
window.addEventListener('message', event => {
  if (event.source !== parent || event.origin !== location.origin || event.data?.channel !== 'ut4-launcher') return;
  switch (event.data.type) {
    case 'start': start(event.data.resolution, event.data.settings, event.data.mode).catch(fail); break;
    case 'release': release(); break;
    case 'menu': menu(); break;
    case 'resume': resume(); break;
    case 'settings': updateSettings(event.data.detail); break;
  }
});
send('boot');
