import { RESOLUTIONS, STORAGE_KEY, MODE_STORAGE_KEY, readMode, readResolution, resolutionKey, fit16by9, validateManifest } from './core.mjs';

const $ = id => document.getElementById(id);
let storage;
try { storage = localStorage; } catch { /* Storage can be disabled. */ }
let selected = readResolution(storage);
let selectedMode = readMode(storage);
let multiplayerAvailable = false;
let modeHelp = 'Checking multiplayer availability…';
let manifestCheck = 0;
const settings = {};
for (const [key,min,max] of [['volume',0,1],['sensitivity',.005,.5]]) {
  try {
    const value = storage.getItem('tournament.local-ut4.' + key);
    if (value !== null && Number.isFinite(Number(value))) settings[key] = Math.max(min,Math.min(max,Number(value)));
  } catch { /* Storage unavailable: keep native defaults until the user sets a value. */ }
  if (settings[key] != null) { $(key).value = settings[key]; $(key+'-value').textContent = settings[key] + ' · saved, waiting to apply'; }
}
let activeResolution = null;
let frame = null;
let phase = 'idle';
let initialized = false;
let menuOpen = true;
let captured = false;
let bootstrapTimer;
let engineTimer;
let lastMetrics;

function command(type, detail) {
  frame?.contentWindow?.postMessage({ channel: 'ut4-launcher', type, detail }, location.origin);
}
function fit() {
  const rect = $('stage').getBoundingClientRect();
  const size = fit16by9(rect.width, rect.height);
  Object.assign($('viewport').style, { width: size.width + 'px', height: size.height + 'px' });
}
new ResizeObserver(fit).observe($('stage'));
document.addEventListener('fullscreenchange', () => {
  fit();
  $('fullscreen').textContent = document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen';
});
function showResolution() {
  $('resolution').value = selected;
  $('resolution-status').textContent = 'Selected: ' + RESOLUTIONS[selected].join(' × ') +
    (activeResolution ? ' · Current: ' + RESOLUTIONS[activeResolution].join(' × ') : '');
}
function render() {
  $('shell').classList.toggle('captured', captured);
  $('panel').classList.toggle('settings-open', !$('settings-panel').hidden);
  $('panel').hidden = !menuOpen;
  $('launch').hidden = phase !== 'idle';
  $('launch').disabled = selectedMode === 'multiplayer' && !multiplayerAvailable;
  $('mode').value = selectedMode;
  $('mode').disabled = phase !== 'idle';
  $('multiplayer-option').disabled = !multiplayerAvailable;
  $('mode-help').textContent = modeHelp + (phase !== 'idle' ? ' Exit to menu to change mode.' : '');
  $('reconnect').hidden = !initialized || phase === 'error' || selectedMode !== 'multiplayer';
  $('retry').hidden = phase !== 'error';
  $('resume').hidden = !initialized || phase === 'error';
  $('stop').hidden = phase === 'idle';
  $('loading').hidden = phase !== 'loading';
  $('capture').disabled = !initialized || phase === 'error' || captured;
  $('release').disabled = !captured;
  $('input-status').textContent = captured ? 'Mouse captured · Esc releases / opens menu' : 'Mouse released · Esc opens menu';
  $('panel-title').textContent = !$('settings-panel').hidden ? 'Settings.' : phase === 'error' ? 'Unable to continue.' : initialized ? 'Menu.' : phase === 'loading' ? 'Loading Tournament.' : 'Enter the arena.';
}
async function checkMultiplayer() {
  const check = ++manifestCheck;
  multiplayerAvailable = false;
  modeHelp = 'Checking multiplayer availability…';
  render();
  try {
    const url = new URL('./runtime.json', location.href);
    const response = await fetch(url, { cache:'no-store', redirect:'error', signal:AbortSignal.timeout(25000) });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const manifest = validateManifest(await response.json(), url.href);
    if (check !== manifestCheck) return;
    multiplayerAvailable = !!manifest.multiplayerArguments?.length;
    modeHelp = multiplayerAvailable ? 'Multiplayer Beta.' : 'Multiplayer unavailable. Choose Practice.';
  } catch {
    if (check !== manifestCheck) return;
    modeHelp = 'Multiplayer unavailable. Select Play to check practice availability.';
  }
  render();
}
function openMenu(settings = false) {
  menuOpen = true;
  captured = false;
  command('release');
  command('menu');
  $('settings-panel').hidden = !settings;
  render();
  $('panel').scrollTop = 0;
  (settings ? $('resolution') : initialized ? $('resume') : phase === 'error' ? $('retry') : $('settings')).focus();
}
function resetMetrics() {
  lastMetrics = null;
  $('fps').textContent = '— engine FPS';
  $('timing').textContent = 'Not initialized · no engine frames observed';
  $('engine-resolution').textContent = 'Engine resolution: uninitialized';
  $('graphics-status').textContent = 'WebGL capability preflight: not checked';
  $('native-frame').textContent = 'Native frame counter: unavailable';
  $('engine-settings').hidden = true;
  $('volume').disabled = true; $('sensitivity').disabled = true;
  $('bindings-help').textContent = 'Resolution applies next time you play. Volume and sensitivity become available when supported.';
}
function destroyRuntime() {
  clearTimeout(bootstrapTimer);
  clearTimeout(engineTimer);
  command('release');
  frame?.remove();
  frame = null;
  initialized = false;
  captured = false;
  activeResolution = null;
}
function fail(message) {
  destroyRuntime();
  phase = 'error';
  resetMetrics();
  $('error').hidden = false;
  $('error').textContent = message;
  $('status').textContent = 'Unable to continue. Select Retry to try again.';
  showResolution();
  openMenu();
}
function launch() {
  destroyRuntime();
  phase = 'loading';
  menuOpen = true;
  activeResolution = selected;
  resetMetrics();
  $('error').hidden = true;
  $('settings-panel').hidden = true;
  $('status').textContent = 'Loading Tournament…';
  $('progress').removeAttribute('value');
  $('progress-text').textContent = 'Preparing your game';
  frame = document.createElement('iframe');
  frame.title = 'Tournament Beta';
  frame.src = './runtime.html';
  $('viewport').append(frame);
  bootstrapTimer = setTimeout(() => fail('Loading did not respond within 30 seconds. Please retry.'), 30000);
  showResolution();
  render();
}
function returnToEngine(capture = false) {
  if (!initialized || phase === 'error') return;
  menuOpen = false;
  $('settings-panel').hidden = true;
  render();
  command('resume');
  frame.contentWindow.focus();
  if (capture) {
    // Call in the user gesture: a postMessage alone can lose transient activation.
    try { frame.contentWindow.captureUT4Pointer(); } catch (error) { $('input-status').textContent = 'Mouse capture unavailable: ' + error.message; }
  }
}

window.addEventListener('message', event => {
  if (!frame || event.source !== frame.contentWindow || event.origin !== location.origin || event.data?.channel !== 'ut4-runtime') return;
  const { type, detail } = event.data;
  switch (type) {
    case 'boot':
      frame.contentWindow.postMessage({ channel: 'ut4-launcher', type: 'start', mode:selectedMode, resolution: activeResolution, settings:{ ...settings, resolution:selected } }, location.origin);
      break;
    case 'manifest': clearTimeout(bootstrapTimer); break;
    case 'progress':
      $('progress-text').textContent = detail.label;
      if (detail.total > 0) { $('progress').max = detail.total; $('progress').value = detail.loaded; }
      else $('progress').removeAttribute('value');
      break;
    case 'initializing':
      $('status').textContent = 'Starting Tournament…';
      $('progress').removeAttribute('value');
      // Parent timer survives a blocked frame event loop where browser scheduling allows it.
      engineTimer = setTimeout(() => fail('Loading took too long. Select Retry to try again.'), detail.timeout);
      break;
    case 'status': $('status').textContent = 'Loading Tournament…'; break;
    case 'initialized':
      clearTimeout(engineTimer);
      initialized = true;
      phase = 'running';
      $('status').textContent = 'Tournament Beta · Select Resume to continue.';
      command('menu');
      render();
      break;
    case 'error': fail(detail); break;
    case 'menu': openMenu(); break;
    case 'pointer':
      captured = detail;
      if (captured && menuOpen) { command('release'); captured = false; }
      else if (!captured) openMenu();
      render();
      break;
    case 'pointer-error': $('input-status').textContent = detail + ' · Use Menu or Esc to return.'; break;
    case 'resolution':
      $('engine-resolution').textContent = 'Drawing buffer: ' + detail.canvas.join(' × ') +
        (detail.engine ? ' · Engine reports: ' + detail.engine.join(' × ') : ' · Native/UE resolution getters unavailable') +
        (detail.matches ? '' : ' · Engine differs from requested resolution; see integration notes.');
      break;
    case 'graphics':
      $('graphics-status').textContent = `WebGL preflight: ${detail.fragment} fragment / ${detail.vertex} vertex / ${detail.combined} combined texture slots · Actual game context still requires verification`;
      break;
    case 'bindings':
      $('engine-settings').hidden = !detail.available.volume && !detail.available.sensitivity;
      for (const key of ['volume','sensitivity']) {
        $(key).disabled = !detail.ready || !detail.available[key];
        if (settings[key] != null) $(key+'-value').textContent = settings[key] + (detail.applied[key] === settings[key] ? ' · applied' : ' · saved, waiting to apply');
      }
      $('bindings-help').textContent = detail.ready
        ? (detail.available.resolution ? 'Resolution changes apply now.' : 'Resolution changes apply next time you play.') + ' Unavailable controls stay disabled.'
        : 'Loading your game settings. Saved changes will apply when available.';
      if (detail.applied.resolution && detail.actual?.join('x') === RESOLUTIONS[detail.applied.resolution]?.join('x')) { activeResolution = detail.applied.resolution; showResolution(); }
      $('native-frame').textContent = detail.nativeFrame == null ? 'Native frame counter: unavailable' : 'Native GFrameCounter: ' + detail.nativeFrame + ' · not presented-frame FPS';
      break;
    case 'metrics':
      lastMetrics = performance.now();
      $('fps').textContent = detail.state === 'measuring' ? detail.fps.toFixed(1) + ' engine FPS' : '— engine FPS';
      $('timing').textContent = detail.state === 'measuring'
        ? `${detail.frameMs.toFixed(1)} ms/frame · p95 ${detail.p95Ms.toFixed(1)} ms · CPU callback ${detail.cpuMs.toFixed(1)} ms`
        : ({ uninitialized: 'No engine main-loop callbacks observed', warming: 'Engine frames observed · collecting samples', stalled: 'No recent engine frames · paused or stalled' }[detail.state]);
      break;
  }
});
// UI watchdog, never a frame source or FPS counter.
setInterval(() => {
  if (lastMetrics !== null && performance.now() - lastMetrics > 2500) {
    $('fps').textContent = '— engine FPS';
    $('timing').textContent = 'Runtime metrics unresponsive · no current measurement';
  }
}, 1000);
$('launch').addEventListener('click', launch);
$('retry').addEventListener('click', launch);
$('reconnect').addEventListener('click', launch);
$('mode').addEventListener('change', () => {
  if (phase !== 'idle') { render(); return; }
  const value = $('mode').value;
  if (value !== 'practice' && (value !== 'multiplayer' || !multiplayerAvailable)) { render(); return; }
  selectedMode = value;
  try { storage.setItem(MODE_STORAGE_KEY, selectedMode); } catch { /* Keep the selection for clean retries within this page. */ }
  render();
});
$('stop').addEventListener('click', () => {
  destroyRuntime(); phase = 'idle'; resetMetrics(); showResolution();
  $('error').hidden = true; $('status').textContent = 'Tournament Beta · Choose a mode to play.';
  openMenu();
  checkMultiplayer();
});
$('resume').addEventListener('click', () => returnToEngine());
$('capture').addEventListener('click', () => returnToEngine(true));
$('release').addEventListener('click', () => openMenu());
$('menu').addEventListener('click', () => openMenu());
$('settings').addEventListener('click', () => openMenu(true));
$('close-settings').addEventListener('click', () => openMenu());
$('resolution').addEventListener('change', () => {
  selected = resolutionKey($('resolution').value);
  try { storage.setItem(STORAGE_KEY, selected); }
  catch { $('resolution-help').textContent = 'Browser storage unavailable. This selection applies for this page only.'; }
  showResolution();
  command('settings', { ...settings, resolution:selected });
});
for (const key of ['volume','sensitivity']) {
  $(key).addEventListener('change', () => {
    settings[key] = Number($(key).value);
    try { storage.setItem('tournament.local-ut4.' + key, String(settings[key])); } catch { /* Applies in this page even if persistence is unavailable. */ }
    $(key+'-value').textContent = settings[key] + ' · waiting to apply';
    command('settings', { ...settings, resolution:selected });
  });
}
$('fullscreen').addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $('shell').requestFullscreen();
  } catch { $('input-status').textContent = 'Fullscreen unavailable. Windowed mode remains available.'; }
});
window.addEventListener('keydown', event => {
  if (event.key === 'Escape') { event.preventDefault(); openMenu(); }
});
window.addEventListener('blur', () => {
  // Moving focus into our engine is expected; switching apps while locked is not.
  if (captured && document.activeElement !== frame) openMenu();
});
document.addEventListener('visibilitychange', () => { if (document.hidden && frame) openMenu(); });
showResolution(); render(); fit(); checkMultiplayer();
