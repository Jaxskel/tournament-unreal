import { GameVideoDecoder } from './video-client.js';
const $ = id => document.getElementById(id);
const canvas = $('game');
const ctx = canvas.getContext('2d', { alpha: false });
const held = new Set();
const keys = new Map(Object.entries({ KeyW:'W', KeyA:'A', KeyS:'S', KeyD:'D', Space:'SpaceBar', ShiftLeft:'LeftShift', ControlLeft:'LeftControl', Digit1:'One', Digit2:'Two', Digit3:'Three', Digit4:'Four', Digit5:'Five', Digit6:'Six', Digit7:'Seven', Digit8:'Eight', Digit9:'Nine', Tab:'Tab', Enter:'Enter', ArrowUp:'Up', ArrowDown:'Down', ArrowLeft:'Left', ArrowRight:'Right' }));
let socket = null;
let active = false;
let joining = false;
let videoDecoder = null;
let minRtt = Infinity;
let joinAbort = null;
let menuMode = false;
let pendingFrame = null;
let decoding = false;
let generation = 0;
let frames = 0;
let fps = 0;
let rtt = null;
let lastFrameAt = 0;
let dx = 0;
let dy = 0;
let exitingLock = false;
let lastEscapeAt = -Infinity;
let nextMouseAt = 0;
let animationFrames = 0;
let metricsAt = performance.now();
let lastPongAt = 0;
const pendingPings = new Map();
const INPUT_TIMEOUT_MS = 3000;
const MOUSE_INTERVAL_MS = 1000 / 120;
let healthLoading = false;
const locked = () => document.pointerLockElement === canvas;
function send(message) {
  if (!active || socket?.readyState !== WebSocket.OPEN) return;
  if (socket.bufferedAmount > 64 * 1024) { disconnect('Connection too slow. Please reconnect.'); return; }
  socket.send(JSON.stringify(message));
}
function reset() {
  held.clear();
  dx = dy = 0;
  send({ type: 'reset' });
}
function releaseMouse() {
  if (locked()) { exitingLock = true; document.exitPointerLock(); }
}
function inputHint() {
  $('capture-hint').hidden = !active || locked() || menuMode;
  $('menu').textContent = menuMode ? 'Close menu' : 'Menu';
  $('input-help').textContent = menuMode
    ? 'Menu input: click inside the game. After selecting Resume, use Capture mouse to aim again.'
    : 'Click the game to aim. Escape opens the game menu and releases your cursor.';
}
function setMenu(open) {
  if (!active) return;
  reset();
  menuMode = open;
  send({ type: 'menu-state', open });
  if (open) releaseMouse();
  canvas.focus({ preventScroll: true });
  inputHint();
}
function toggleMenu() { setMenu(!menuMode); }
async function captureMouse() {
  if (!active) return;
  canvas.focus({ preventScroll: true });
  try {
    if (!canvas.requestPointerLock) throw new Error('Pointer lock unavailable');
    await canvas.requestPointerLock();
  } catch {
    $('input-help').textContent = 'Mouse capture was denied. Click Capture mouse again; use a desktop browser with pointer lock support.';
  }
}
function setActive(value) {
  active = value;
  for (const id of ['capture', 'menu', 'disconnect']) $(id).disabled = !value;
  $('landing').hidden = value;
  if (!value) {
    $('stream-notice').hidden = true;
    $('connection').textContent = 'READY TO JOIN';
    $('metrics').textContent = '— FPS · — ms RTT';
    $('metrics').title = '';
  }
  inputHint();
}
function disconnect(message = 'Seat released. You can join again.') {
  joinAbort?.abort();
  joinAbort = null;
  // Do not call send()/reset() here: send() itself disconnects on backpressure.
  if (active && socket?.readyState === WebSocket.OPEN && socket.bufferedAmount <= 64 * 1024) socket.send(JSON.stringify({ type: 'reset' }));
  held.clear();
  dx = dy = 0;
  releaseMouse();
  videoDecoder?.close();
  videoDecoder = null;
  generation++;
  pendingPings.clear();
  pendingFrame = null;
  const previous = socket;
  socket = null;
  previous?.close(1000, 'Player left');
  menuMode = false;
  joining = false;
  setActive(false);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  $('play').disabled = false;
  $('play').textContent = 'PLAY AGAIN ↗';
  $('feedback').textContent = message;
  void refreshHealth();
}
async function decodeFrames() {
  if (decoding) return;
  decoding = true;
  try {
    while (pendingFrame) {
      const { blob, version } = pendingFrame;
      pendingFrame = null;
      let bitmap;
      try {
        bitmap = await decodeImage(blob);
        if (version !== generation || !active) continue;
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        frames++;
        lastFrameAt = performance.now();
        $('stream-notice').hidden = true;
      } catch {
        if (version === generation) {
          $('stream-notice').textContent = 'A frame could not be decoded. Waiting for the next frame…';
          $('stream-notice').hidden = false;
        }
      } finally { bitmap?.close?.(); }
    }
  } finally { decoding = false; }
}
function decodeImage(blob) {
  if ('createImageBitmap' in window) return createImageBitmap(blob);
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Invalid frame')); };
    img.src = url;
  });
}
async function waitForSeat(signal) {
  const deadline = performance.now() + 90000;
  while (!signal.aborted) {
    const response = await fetch('/api/join', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]) });
    const result = await response.json();
    signal.throwIfAborted();
    if (response.ok) return result;
    if (response.status !== 503) throw new Error(result.error || 'Could not join. Please try again.');
    if (performance.now() >= deadline) throw new Error('The game host is offline. Please try again shortly.');
    $('feedback').textContent = 'Reconnecting the arena… You’ll enter automatically when it’s ready.';
    await new Promise((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
      const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 1500);
      signal.addEventListener('abort', abort, { once: true });
      if (signal.aborted) abort();
    });
  }
  throw new DOMException('Cancelled', 'AbortError');
}
async function join() {
  if (joining || active) return;
  joining = true;
  const version = ++generation;
  joinAbort = new AbortController();
  $('play').disabled = false;
  $('play').textContent = 'CANCEL';
  $('feedback').textContent = 'Connecting…';
  try {
    const result = await waitForSeat(joinAbort.signal);
    if (version !== generation) return;
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/stream`);
    socket = ws;
    ws.binaryType = 'arraybuffer';
    const joinTimer = setTimeout(() => { if (socket === ws && !active) disconnect('Connection timed out. Please try again.'); }, 8000);
    ws.onopen = () => { ws.send(JSON.stringify({ type: 'auth', token: result.token })); };
    ws.onmessage = event => {
      if (socket !== ws) return;
      if (event.data instanceof ArrayBuffer) {
        if (videoDecoder) {
          try { videoDecoder.push(event.data); } catch { disconnect('Invalid video stream. Please reconnect.'); }
          return;
        }
        event = {data:new Blob([event.data],{type:'image/jpeg'})};
      }
      if (event.data instanceof Blob) {
        if (event.data.size > 4 * 1024 * 1024) { disconnect('Invalid frame size.'); return; }
        pendingFrame = { blob: event.data, version };
        void decodeFrames();
        return;
      }
      let packet;
      try { packet = JSON.parse(event.data); } catch { return; }
      if (packet.type === 'joined') {
        clearTimeout(joinTimer);
        joining = false;
        joinAbort = null;
        frames = fps = 0;
        rtt = null;
        minRtt = Infinity;
        lastFrameAt = performance.now();
        menuMode = false;
        lastPongAt = performance.now();
        nextMouseAt = 0;
        animationFrames = 0;
        metricsAt = performance.now();
        pendingPings.clear();
        setActive(true);
        if (packet.video === 'h264') {
          if (typeof VideoDecoder === 'undefined') { disconnect('This stream needs a browser with H.264 WebCodecs support. Open it in current Chrome or Edge.'); return; }
          videoDecoder = new GameVideoDecoder({
            send, fps:packet.fps ?? 60,
            draw: frame => {
              if (!active || generation !== version) return;
              ctx.drawImage(frame,0,0,canvas.width,canvas.height);
              frames++; lastFrameAt=performance.now(); $('stream-notice').hidden=true;
            },
            failure: (_error, fatal) => {
              if (fatal) { disconnect('H.264 decoding failed. Try current Chrome or Edge with an updated graphics driver.'); return; }
              $('stream-notice').textContent='Resynchronizing video…'; $('stream-notice').hidden=false;
            },
          });
        }
        $('connection').textContent = `LIVE · PLAYER ${packet.seat}`;
        $('stream-notice').textContent = 'Waiting for the game viewport…';
        $('stream-notice').hidden = false;
        canvas.focus({ preventScroll: true });
        void refreshHealth();
      } else if (packet.type === 'video-config' && videoDecoder) {
        const decoder = videoDecoder;
        void decoder.configureSupported(packet.codec).catch(() => {
          if (decoder === videoDecoder) disconnect('H.264 decoding is unavailable in this browser. Try current Chrome or Edge.');
        });
      } else if (packet.type === 'pong' && Number.isSafeInteger(packet.id)) {
        const sentAt = pendingPings.get(packet.id);
        if (sentAt !== undefined && performance.now() - sentAt < INPUT_TIMEOUT_MS) {
          rtt = Math.round(performance.now() - sentAt);
          if (videoDecoder && Number.isFinite(packet.serverTime) && rtt < minRtt) {
            minRtt = rtt; videoDecoder.serverOffset = packet.serverTime + rtt / 2 - Date.now();
          }
          lastPongAt = performance.now();
          pendingPings.delete(packet.id);
        }
      } else if (packet.type === 'input-state' && packet.state === 'suspended') {
        reset();
        releaseMouse();
        $('input-help').textContent = 'Input paused after a connection gap. Capture mouse to continue.';
      } else if (packet.type === 'stream-state' && packet.state === 'waiting') {
        reset();
        $('stream-notice').textContent = 'The game is reconnecting. Your seat is reserved…';
        $('stream-notice').hidden = false;
      }
    };
    ws.onclose = event => {
      clearTimeout(joinTimer);
      if (socket === ws) disconnect(event.code === 1008 ? 'Session rejected or expired. Please join again.' : 'Connection closed. Join again to reconnect.');
    };
    ws.onerror = () => { if (socket === ws) $('feedback').textContent = 'Could not reach the stream. Please try again.'; };
  } catch (error) {
    if (version !== generation) return;
    joinAbort = null;
    joining = false;
    $('play').disabled = false;
    $('play').textContent = 'PLAY AGAIN ↗';
    $('feedback').textContent = error.name === 'TimeoutError' ? 'The host took too long to respond. Please try again.' : error.message;
  }
}
async function refreshHealth() {
  if (healthLoading) return;
  healthLoading = true;
  try {
    const response = await fetch('/api/health', { signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw new Error();
    const health = await response.json();
    const ready = health.seats.filter(s => s.nativeConnected && s.frameAgeMs !== null && s.frameAgeMs < 10000 && !s.occupied).length;
    $('availability').textContent = ready ? `${ready} of 2 seats available` : health.seats.every(s => s.occupied) ? 'Arena full · try again shortly' : 'Arena reconnecting · Play will join when ready';
  } catch { $('availability').textContent = 'Waiting for the host'; }
  finally { healthLoading = false; }
}
$('play').addEventListener('click', () => joining ? disconnect('Connection cancelled.') : join());
$('disconnect').addEventListener('click', () => disconnect());
$('capture').addEventListener('click', captureMouse);
$('menu').addEventListener('click', toggleMenu);
$('fullscreen').addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $('stream-shell').requestFullscreen();
  } catch { $('input-help').textContent = 'Fullscreen is unavailable in this browser. You can still play in the page.'; }
});
canvas.addEventListener('contextmenu', event => event.preventDefault());
canvas.addEventListener('mousedown', event => {
  if (!active) return;
  event.preventDefault();
  canvas.focus({ preventScroll: true });
  if (!locked()) {
    if (menuMode && event.button === 0) {
      const rect = canvas.getBoundingClientRect();
      // Account for object-fit:contain letterboxing in fullscreen.
      const scale = Math.min(rect.width / canvas.width, rect.height / canvas.height);
      const w = canvas.width * scale;
      const h = canvas.height * scale;
      const x = (event.clientX - rect.left - (rect.width - w) / 2) / w;
      const y = (event.clientY - rect.top - (rect.height - h) / 2) / h;
      if (x >= 0 && x <= 1 && y >= 0 && y <= 1) send({ type: 'menu', x, y });
    } else if (!menuMode) void captureMouse();
    return;
  }
  const key = event.button === 0 ? 'LeftMouseButton' : event.button === 2 ? 'RightMouseButton' : null;
  if (key && !held.has(key)) { held.add(key); send({ type: 'key', key, down: true }); }
});
window.addEventListener('mouseup', event => {
  const key = event.button === 0 ? 'LeftMouseButton' : event.button === 2 ? 'RightMouseButton' : null;
  if (key && held.delete(key)) send({ type: 'key', key, down: false });
});
document.addEventListener('mousemove', event => { if (active && locked()) { dx += event.movementX; dy += event.movementY; } });
window.addEventListener('keydown', event => {
  if (!active) return;
  if (event.code === 'Escape') {
    event.preventDefault();
    if (!event.repeat && performance.now() - lastEscapeAt > 200) { lastEscapeAt = performance.now(); toggleMenu(); }
    return;
  }
  if (!locked() && !(menuMode && document.activeElement === canvas)) return;
  const key = keys.get(event.code);
  if (!key) return;
  event.preventDefault();
  if (!held.has(key)) { held.add(key); send({ type: 'key', key, down: true }); }
});
window.addEventListener('keyup', event => {
  const key = keys.get(event.code);
  if (key && held.delete(key)) { event.preventDefault(); send({ type: 'key', key, down: false }); }
});
document.addEventListener('pointerlockchange', () => {
  if (locked()) { exitingLock = false; setMenu(false); }
  else {
    reset();
    if (active && !exitingLock && !menuMode && !document.hidden && document.hasFocus()) { lastEscapeAt = performance.now(); setMenu(true); }
    exitingLock = false;
  }
  inputHint();
});
document.addEventListener('pointerlockerror', () => { $('input-help').textContent = 'Click Capture mouse to try again. Your browser must permit pointer lock.'; });
window.addEventListener('blur', reset);
document.addEventListener('visibilitychange', () => { if (document.hidden) { reset(); releaseMouse(); } });
window.addEventListener('pagehide', () => disconnect());
function animate() {
  const now = performance.now();
  animationFrames++;
  if ((dx || dy) && now + 0.5 >= nextMouseAt) {
    // Preserve the 120 Hz phase through sub-millisecond rAF jitter. Reset the
    // deadline after idle time; never replay missed sends as a catch-up burst.
    nextMouseAt = now - nextMouseAt > MOUSE_INTERVAL_MS
      ? now + MOUSE_INTERVAL_MS : nextMouseAt + MOUSE_INTERVAL_MS;
    const clamp = n => Math.max(-300, Math.min(300, n));
    send({ type: 'mouse', dx: clamp(dx), dy: clamp(dy) });
    dx = dy = 0;
  }
  requestAnimationFrame(animate);
}
setInterval(() => {
  const elapsed = Math.max(1, performance.now() - metricsAt);
  fps = Math.round(frames * 1000 / elapsed);
  const browserHz = Math.round(animationFrames * 1000 / elapsed);
  frames = animationFrames = 0;
  metricsAt = performance.now();
  if (!active) return;
  const age = videoDecoder?.frameAge;
  $('metrics').title = `${browserHz} Hz browser animation cadence. FPS counts decoded game frames, not physical screen refresh. RTT is network round-trip time; video age excludes input and screen scanout.`;
  $('metrics').textContent = `${fps} FPS · ${rtt === null ? '—' : rtt} ms RTT${videoDecoder ? ` · H.264${age === null ? '' : ` · ${Math.round(age)} ms video age`}` : ''}`;
  if (performance.now() - lastFrameAt > 3000) {
    $('stream-notice').textContent = 'Reconnecting game video…';
    $('stream-notice').hidden = false;
  }
  const now = performance.now();
  if (now - lastPongAt >= INPUT_TIMEOUT_MS) { disconnect('Connection timed out. Please join again.'); return; }
  for (const [id, sentAt] of pendingPings) if (now - sentAt >= INPUT_TIMEOUT_MS) pendingPings.delete(id);
  const id = Date.now();
  pendingPings.set(id, now);
  send({ type: 'ping', id });
}, 1000);
setInterval(() => {
  if (active && performance.now() - lastPongAt >= INPUT_TIMEOUT_MS) disconnect('Connection timed out. Please join again.');
}, 250);
setInterval(refreshHealth, 5000);
void refreshHealth();
requestAnimationFrame(animate);
