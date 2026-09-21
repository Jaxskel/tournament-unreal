import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../public/app.js', import.meta.url), 'utf8').then(text => text.replace(/^import .*;\n/, ''));
function harness(joinResponses = []) {
  let joinRequests = 0;
  const timers = [];
  let time = 0;
  let frame = null;
  let nativeMenu = false;
  const intervals = [];
  const elements = new Map();
  const events = () => ({
    handlers: new Map(),
    addEventListener(name, fn) { this.handlers.set(name, fn); },
    dispatch(name, value = {}) { return this.handlers.get(name)?.({preventDefault() {}, ...value}); },
  });
  const document = {...events(), hidden:false, pointerLockElement:null, activeElement:null, hasFocus:() => true};
  const window = {...events()};
  class Socket {
    static OPEN = 1;
    static instances = [];
    constructor() { this.readyState = 1; this.bufferedAmount = 0; this.sent = []; Socket.instances.push(this); }
    send(raw) { const p = JSON.parse(raw); this.sent.push(p); if (p.type === 'menu-state') nativeMenu = p.open; }
    close() { this.readyState = 3; }
  }
  document.getElementById = id => {
    if (!elements.has(id)) elements.set(id, {
      ...events(), hidden:false, disabled:false, textContent:'', width:960, height:540,
      focus() { document.activeElement = this; },
      getContext:() => ({ clearRect() {}, drawImage() {} }),
      getBoundingClientRect:() => ({left:0,top:0,width:960,height:540}),
      requestPointerLock() { document.pointerLockElement = this; document.dispatch('pointerlockchange'); return Promise.resolve(); },
    });
    return elements.get(id);
  };
  document.exitPointerLock = () => { document.pointerLockElement = null; document.dispatch('pointerlockchange'); };
  const context = vm.createContext({
    document, window, WebSocket:Socket, Blob, ArrayBuffer,
    performance:{now:() => time}, Date:{now:() => 100000 + time},
    requestAnimationFrame:fn => { frame = fn; },
    setInterval:(fn, ms) => {intervals.push({fn,ms});}, setTimeout:(fn, ms) => { const timer = {fn,ms}; timers.push(timer); return timer; }, clearTimeout(timer) { if(timer) timer.cancelled = true; },
    DOMException, AbortController,
    location:{protocol:'http:',host:'test'}, AbortSignal,
    fetch:async url => {
      if (url === '/api/join') {
        joinRequests++;
        const response = joinResponses.shift() ?? {status:201, body:{token:'fixture'}};
        return {ok:response.status < 300,status:response.status,json:async () => response.body};
      }
      return {ok:true,json:async () => ({seats:[]})};
    },
  });
  vm.runInContext(source, context);
  const run = code => vm.runInContext(code, context);
  async function join() {
    await run('join()');
    const socket = Socket.instances.at(-1);
    socket.onopen();
    socket.onmessage({data:JSON.stringify({type:'joined',seat:1,width:960,height:540,audio:false})});
    return socket;
  }
  return {
    run, join, document, window, intervals, timers,
    joinRequests:() => joinRequests,
    sockets:Socket.instances,
    element:id => document.getElementById(id),
    advance:ms => {time += ms;},
    tickFrame:() => frame?.(),
    nativeMenu:() => nativeMenu,
    simulateResume:() => {nativeMenu = false;},
    setNativeMenu:value => {nativeMenu = value;},
  };
}

test('Resume then browser Close menu sends an absolute close, never reopens native menu', async () => {
  const h = harness(); const ws = await h.join();
  h.run('toggleMenu()'); assert.equal(h.nativeMenu(), true);
  h.simulateResume();
  h.run('toggleMenu()');
  assert.equal(h.nativeMenu(), false);
  assert.deepEqual(ws.sent.filter(p => p.type === 'menu-state').map(p => p.open), [true,false]);
  assert.ok(!ws.sent.some(p => p.key === 'Escape'));
});

test('capture always closes inherited native menu; Resume then capture stays closed', async () => {
  const h = harness(); await h.join();
  h.setNativeMenu(true);
  await h.run('captureMouse()');
  assert.equal(h.nativeMenu(), false);
  assert.equal(h.run('menuMode'), false);
  h.run('setMenu(true)'); h.simulateResume();
  await h.run('captureMouse()');
  assert.equal(h.nativeMenu(), false);
  assert.equal(h.document.pointerLockElement, h.element('game'));
});

test('menu canvas click forwards normalized coordinates without recapturing', async () => {
  const h = harness(); const ws = await h.join();
  h.run('setMenu(true)');
  h.element('game').dispatch('mousedown', {button:0,clientX:480,clientY:270});
  assert.deepEqual(ws.sent.at(-1), {type:'menu',x:0.5,y:0.5});
  assert.equal(h.document.pointerLockElement, null);
});

test('Escape plus pointer-lock release sends one open request', async () => {
  const h = harness(); const ws = await h.join();
  await h.run('captureMouse()'); ws.sent.length = 0;
  h.window.dispatch('keydown', {code:'Escape',repeat:false});
  assert.equal(h.document.pointerLockElement, null);
  assert.deepEqual(ws.sent.filter(p => p.type === 'menu-state'), [{type:'menu-state',open:true}]);
  // Browsers that emit pointerlockchange before Escape keydown are also de-duplicated.
  h.advance(300); await h.run('captureMouse()'); ws.sent.length = 0;
  h.document.pointerLockElement = null; h.document.dispatch('pointerlockchange');
  h.window.dispatch('keydown', {code:'Escape',repeat:false});
  assert.deepEqual(ws.sent.filter(p => p.type === 'menu-state'), [{type:'menu-state',open:true}]);
});

test('360 Hz and 1000 Hz display loops cap mouse packets at 60/sec and preserve accumulated deltas', async () => {
  for (const hz of [360,1000]) {
    const h = harness(); const ws = await h.join();
    await h.run('captureMouse()'); ws.sent.length = 0;
    for (let i = 0; i < hz; i++) {
      h.document.dispatch('mousemove', {movementX:1,movementY:-1});
      h.tickFrame(); h.advance(1000/hz);
    }
    const packets = ws.sent.filter(p => p.type === 'mouse');
    assert.ok(packets.length <= 60 && packets.length >= 45, `${hz}Hz produced ${packets.length} packets`);
    const forwarded = packets.reduce((sum,p) => sum + p.dx, 0);
    assert.ok(hz - forwarded < hz / 40);
    assert.ok(packets.every(p => p.dx === -p.dy && p.dx <= 300));
  }
});

test('missing server pong disconnects within three seconds and resets controls', async () => {
  const h = harness(); const ws = await h.join();
  await h.run('captureMouse()');
  h.window.dispatch('keydown', {code:'KeyW',repeat:false});
  h.advance(3001);
  h.intervals.find(i => i.ms === 250).fn();
  assert.equal(ws.readyState, 3);
  assert.equal(h.run('active'), false);
  assert.equal(h.document.pointerLockElement, null);
  assert.deepEqual(ws.sent.at(-1), {type:'reset'});
  assert.match(h.element('feedback').textContent, /timed out/);
});

test('fresh matching pong maintains connection; unmatched and stale pong cannot extend watchdog', async () => {
  const h = harness(); const ws = await h.join();
  h.advance(1000); h.intervals.find(i => i.ms === 1000).fn();
  const ping = ws.sent.find(p => p.type === 'ping');
  h.advance(50);
  ws.onmessage({data:JSON.stringify({type:'pong',id:ping.id})});
  assert.equal(h.run('rtt'), 50);
  h.advance(2200); h.intervals.find(i => i.ms === 250).fn();
  assert.equal(h.run('active'), true);
  ws.onmessage({data:JSON.stringify({type:'pong',id:999})});
  h.advance(801); h.intervals.find(i => i.ms === 250).fn();
  assert.equal(h.run('active'), false);
});

test('disconnect then rejoin gets a fresh generation and watchdog; blur resets but keeps lease', async () => {
  const h = harness(); const first = await h.join();
  h.window.dispatch('blur');
  assert.deepEqual(first.sent.at(-1), {type:'reset'});
  assert.equal(first.readyState, 1);
  h.run('disconnect()');
  h.advance(10000);
  const second = await h.join();
  h.intervals.find(i => i.ms === 250).fn();
  assert.equal(h.run('active'), true);
  assert.equal(second.readyState, 1);
  first.onclose({code:1000});
  assert.equal(h.run('active'), true);
});

const flush = () => new Promise(resolve => setImmediate(resolve));
test('one Play click retries a recovering host then opens the stream', async () => {
  const h = harness([{status:503,body:{code:'recovering'}}, {status:503,body:{code:'recovering'}}]);
  const joining = h.run('join()'); await flush();
  assert.equal(h.element('play').textContent, 'CANCEL');
  assert.equal(h.joinRequests(), 1);
  for (let i=0;i<2;i++) { h.timers.filter(t => t.ms === 1500).at(-1).fn(); await flush(); }
  await joining;
  assert.equal(h.joinRequests(), 3);
  assert.equal(h.sockets.length, 1);
});
test('Cancel aborts recovery without creating a socket or reviving the old join', async () => {
  const h = harness([{status:503,body:{}}]);
  const joining = h.run('join()'); await flush();
  h.element('play').dispatch('click'); await joining;
  assert.equal(h.run('joining'), false);
  assert.equal(h.sockets.length, 0);
  assert.equal(h.element('feedback').textContent, 'Connection cancelled.');
  assert.equal(h.timers.find(t => t.ms === 1500).cancelled, true);
  await h.join();
  assert.equal(h.run('active'), true);
});
test('recovery has a deadline and does not retry a full arena', async () => {
  const h = harness([{status:503,body:{}},{status:503,body:{}}]);
  const joining = h.run('join()'); await flush();
  h.advance(90001); h.timers.find(t => t.ms === 1500).fn(); await joining;
  assert.match(h.element('feedback').textContent, /offline/);
  assert.equal(h.run('joining'), false);
  const full = harness([{status:409,body:{error:'Both seats are in use.'}}]);
  await full.run('join()');
  assert.equal(full.joinRequests(), 1);
  assert.match(full.element('feedback').textContent, /Both seats/);
});
