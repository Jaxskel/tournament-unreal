import { RESOLUTIONS, resolutionKey, engineArguments, argumentsForMode, validateManifest, validateGraphicsLimits, FrameMetrics } from './core.mjs';
import { EngineBindings } from './bindings.mjs';

const canvas = document.getElementById('canvas');
const metrics = new FrameMetrics();
const blobs = new Map();
const assets = new Map();
const requests = new Set();
let disposed = false;
let restorePackageXHR = () => {};
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
const send = (type, detail) => { if (!disposed) parent.postMessage({ channel: 'ut4-runtime', type, detail }, location.origin); };

function releaseAssetUrls() {
  for (const value of blobs.values()) URL.revokeObjectURL(value);
  blobs.clear();
  assets.clear();
}
function dispose() {
  if (disposed) return;
  disposed = true;
  clearInterval(reportTimer);
  ++audioCaptureAttempt;
  try { bridge?.release(); } catch { /* Teardown must still release downloads. */ }
  try { window.Module?.pauseMainLoop?.(); } catch { /* The parent removes this document next. */ }
  for (const request of requests) request.abort();
  requests.clear();
  restorePackageXHR();
  releaseAssetUrls();
  bridge?.dispose();
  bridge = null;
  bridgeReport = null;
  pressedKeys.clear();
  release();
}
// Removing an iframe need not promptly collect its realm. Release browser-owned
// Blob resources synchronously before the parent starts another large download.
window.disposeUT4Runtime = dispose;

function fail(error) {
  if (failed || disposed) return;
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
  const expressionAssertion = /\bExpression '[^'\r\n]{1,256}' failed in [^\r\n]{1,1024}:\d+!/.test(line);
  if (expressionAssertion || /LogLoad:\s*Error:/i.test(line) || (!engineDiagnostic && /Fatal error:|Ensure condition failed:|Assertion failed:|LogOutputDevice:Error:/.test(line))) {
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
function pointerDenied(error) {
  if (failed || disposed) return;
  send('pointer-error', 'Mouse capture denied' + (error?.message ? ': ' + error.name + ' — ' + error.message : '') + '; click the viewport to retry');
}
// Legacy JSEvents also requests capture from deferred keyboard handlers and
// discards the browser promise. Handle rejection at this canvas only, before
// engine scripts load; unrelated unhandled rejections must still fail normally.
const browserRequestPointerLock = canvas.requestPointerLock || canvas.mozRequestPointerLock
  || canvas.webkitRequestPointerLock || canvas.msRequestPointerLock;
function guardedPointerLock(...args) {
  try {
    // Stay synchronous to preserve transient activation and the native receiver.
    const result = browserRequestPointerLock.apply(this, args);
    result?.then(undefined, pointerDenied);
    return result;
  } catch (error) { pointerDenied(error); }
}
if (typeof browserRequestPointerLock === 'function') canvas.requestPointerLock = guardedPointerLock;
window.captureUT4Pointer = function() {
  if (!initialized || failed) return;
  resume();
  activateBrowserAudio();
  if (!canvas.requestPointerLock) { send('pointer-error', 'Pointer lock is unavailable'); return; }
  try {
    const request = canvas.requestPointerLock;
    const result = request.call(canvas);
    // Retain launcher protection if a support script replaces the method later.
    if (request !== guardedPointerLock) result?.catch(pointerDenied);
  } catch (error) { pointerDenied(error); }
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
window.addEventListener('pagehide', dispose);

function observePackageDownloads(packages) {
  const OriginalXHR = window.XMLHttpRequest;
  class PackageXHR extends OriginalXHR {
    open(method, url, ...options) {
      super.open(method, url, ...options);
      const name = packages.get(String(url));
      if (!name) return;
      const xhr = this;
      let watchdog;
      const cleanup = () => {
        clearTimeout(watchdog);
        requests.delete(xhr);
        for (const [type, handler] of handlers) xhr.removeEventListener(type, handler);
      };
      const reject = (event, message) => {
        event?.stopImmediatePropagation();
        cleanup();
        fail(new Error(name + ': ' + message));
      };
      const arm = () => {
        clearTimeout(watchdog);
        watchdog = setTimeout(() => {
          reject(null, 'no download progress for 60 seconds.');
          xhr.abort();
        }, 60000);
      };
      const handlers = [
        ['progress', event => {
          arm();
          send('progress', { loaded:event.loaded, total:event.lengthComputable ? event.total : 0,
            label:`${name} · ${(event.loaded / 1048576).toFixed(1)} MiB received` });
        }],
        ['load', event => {
          if (xhr.status !== 200) return reject(event, `HTTP ${xhr.status}; check runtime.json and asset hosting.`);
          if (new URL(xhr.responseURL).origin !== location.origin) return reject(event, 'cross-origin redirect rejected.');
          if (/text\/html/i.test(xhr.getResponseHeader('Content-Type') ?? '')) return reject(event, 'server returned HTML instead of an engine asset.');
          if (xhr.responseType !== 'arraybuffer' || !xhr.response?.byteLength) return reject(event, 'empty or invalid package ArrayBuffer.');
          // The packager's own load handler now mounts this same buffer.
          cleanup();
        }],
        ['error', event => reject(event, 'network request failed.')],
        ['abort', event => { cleanup(); if (!disposed && !failed) reject(event, 'download cancelled.'); }]
      ];
      for (const [type, handler] of handlers) xhr.addEventListener(type, handler);
      requests.add(xhr);
      send('progress', { loaded:0, total:0, label:`${name} · requesting package…` });
      arm();
    }
  }
  window.XMLHttpRequest = PackageXHR;
  restorePackageXHR = () => {
    if (window.XMLHttpRequest === PackageXHR) window.XMLHttpRequest = OriginalXHR;
  };
}

function download(url, name, index, count) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    requests.add(xhr);
    let watchdog;
    let settled = false;
    const done = callback => value => {
      if (settled) return;
      settled = true;
      clearTimeout(watchdog);
      requests.delete(xhr);
      xhr.onload = xhr.onerror = xhr.onabort = xhr.onprogress = null;
      // Drop the completed response reference as soon as its Blob is handed on.
      xhr.abort();
      callback(value);
    };
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
  if (started || disposed) return;
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
  const scripts = [...manifest.supportScripts, ...manifest.dataScripts, manifest.engine];
  // The legacy packager already fetches .data as ArrayBuffer and mounts slices
  // without a heap copy. Give it the declared same-origin URL directly: an eager
  // Blob download followed by another XHR needlessly consumes browser Blob quota.
  const packages = new Map(manifest.packageFiles.map(name => [name, manifest.files[name]]));
  const entries = Object.entries(manifest.files).filter(([name]) => !packages.has(name));
  for (let i = 0; i < entries.length; i++) {
    if (failed || disposed) return;
    const [name, url] = entries[i];
    assets.set(name, await download(url, name, i + 1, entries.length));
  }
  if (failed || disposed) return;
  for (const [name, blob] of assets) {
    blobs.set(name, URL.createObjectURL(new Blob([blob], { type: scripts.includes(name) ? 'text/javascript' : name === manifest.wasmBinary ? 'application/wasm' : 'application/octet-stream' })));
  }
  const locateFile = name => {
    if (packages.has(name)) return packages.get(name);
    if ([...packages.values()].includes(name)) return name;
    if (blobs.has(name)) return blobs.get(name);
    // Some packagers pass the already-resolved URL, others the emitted basename.
    for (const [key, url] of Object.entries(manifest.files)) if (name === url) return blobs.get(key);
    if ([...blobs.values()].includes(name)) return name;
    throw new Error('Runtime requested undeclared asset: ' + name + '. Add its exact emitted name to runtime.json files.');
  };
  observePackageDownloads(new Map([...packages].map(([name, url]) => [url, name])));
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
      if (failed || disposed) return;
      // All startup run dependencies have completed. The mounted filesystem owns
      // its package bytes; retaining the download Blob adds another large copy
      // against the browser's Blob quota throughout play and reconnect.
      releaseAssetUrls();
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
  if (failed || disposed) return;
  assets.clear();
  send('progress', { loaded: 0, total: 0, label: 'Downloads complete · compiling and mounting engine assets' });
  reportTimer = setInterval(() => { pollBindings(); send('metrics', metrics.snapshot(performance.now())); resolutionReport(); }, 500);
  for (const name of scripts) {
    if (failed || disposed) return;
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
  if (disposed) return;
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
