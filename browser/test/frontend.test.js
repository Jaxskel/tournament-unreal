import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../public/app.js', import.meta.url), 'utf8').then(text => text.replace(/^import .*;\n/, ''));
function harness(joinResponses = [], storage = new Map(), gateway = '') {
  let joinRequests = 0;
  const requestedURLs = [];
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
  const classes=new Set();
  const document = {body:{classList:{toggle(name,on){if(on)classes.add(name);else classes.delete(name);},contains:name=>classes.has(name)}},...events(), hidden:false, pointerLockElement:null, activeElement:null, hasFocus:() => true};
  document.querySelector = () => gateway ? {content:gateway} : null;
  const window = {...events()};
  class Socket {
    static OPEN = 1;
    static instances = [];
    constructor(url) { this.url=url; this.readyState = 1; this.bufferedAmount = 0; this.sent = []; Socket.instances.push(this); }
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
    document, window, WebSocket:Socket, Blob, ArrayBuffer, URL,
    localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    VideoDecoder:class {},
    GameVideoDecoder:class {
      constructor(options){Object.assign(this,options);}
      configureSupported(codec){this.codec=codec;return Promise.resolve();}
      close(){this.closed=true;}
    },
    performance:{now:() => time}, Date:{now:() => 100000 + time},
    requestAnimationFrame:fn => { frame = fn; },
    setInterval:(fn, ms) => {intervals.push({fn,ms});}, setTimeout:(fn, ms) => { const timer = {fn,ms}; timers.push(timer); return timer; }, clearTimeout(timer) { if(timer) timer.cancelled = true; },
    DOMException, AbortController,
    location:{protocol:'http:',host:'test'}, AbortSignal,
    fetch:async url => {
      requestedURLs.push(url);
      if (url.endsWith('/api/join')) {
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
    run, join, document, window, intervals, timers, requestedURLs,
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

test('360 Hz and 1000 Hz display loops cap mouse packets at 120/sec and preserve accumulated deltas', async () => {
  for (const hz of [360,1000]) {
    const h = harness(); const ws = await h.join();
    await h.run('captureMouse()'); ws.sent.length = 0;
    for (let i = 0; i < hz; i++) {
      h.document.dispatch('mousemove', {movementX:1,movementY:-1});
      h.tickFrame(); h.advance(1000/hz);
    }
    const packets = ws.sent.filter(p => p.type === 'mouse');
    assert.ok(packets.length <= 120 && packets.length >= 90, `${hz}Hz produced ${packets.length} packets`);
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


test('120 Hz aiming tolerates early animation callbacks without dropping to half rate', async () => {
  for (const gaps of [[1000/120], [8.0, 8.6666666667], [1000/119.88]]) {
    const h = harness(); const ws = await h.join();
    await h.run('captureMouse()'); ws.sent.length = 0;
    for (let i=0; i<120; i++) {
      h.document.dispatch('mousemove', {movementX:2,movementY:-1});
      h.tickFrame(); h.advance(gaps[i % gaps.length]);
    }
    const packets = ws.sent.filter(p => p.type === 'mouse');
    assert.ok(packets.length >= 119, `${gaps}: only ${packets.length} mouse updates`);
    assert.equal(packets.reduce((sum,p) => sum+p.dx,0), 240);
  }
});

test('mouse scheduling does not replay a burst after a long pause', async () => {
  const h = harness(); const ws = await h.join();
  await h.run('captureMouse()'); ws.sent.length=0;
  h.document.dispatch('mousemove', {movementX:5,movementY:0}); h.tickFrame();
  h.advance(2000);
  h.document.dispatch('mousemove', {movementX:7,movementY:0}); h.tickFrame();
  for(let i=0;i<50;i++) h.tickFrame();
  assert.deepEqual(ws.sent.filter(p => p.type==='mouse').map(p => p.dx), [5,7]);
});

test('arrow controls reach the native menu and release cleanly', async () => {
  const h = harness(); const ws = await h.join(); h.run('setMenu(true)'); ws.sent.length=0;
  for(const [code,key] of [['ArrowUp','Up'],['ArrowDown','Down'],['ArrowLeft','Left'],['ArrowRight','Right']]) {
    h.window.dispatch('keydown', {code,repeat:false});
    h.window.dispatch('keyup', {code});
    assert.deepEqual(ws.sent.slice(-2), [{type:'key',key,down:true},{type:'key',key,down:false}]);
  }
  h.window.dispatch('blur'); assert.deepEqual(ws.sent.at(-1), {type:'reset'});
});

test('FPS normalizes delayed timer intervals and distinguishes browser cadence', async () => {
  const h = harness(); await h.join();
  for(let i=0;i<90;i++) {h.advance(1000/60); h.tickFrame();}
  h.run('frames=180');
  h.intervals.find(i => i.ms===1000).fn();
  assert.match(h.element('metrics').textContent, /120 FPS/);
  assert.match(h.element('metrics').title, /60 Hz browser animation/);
});


test('1080p stream resizes the canvas instead of downsampling into the old 540p buffer',async()=>{
  const h=harness();const ws=await h.join();
  ws.onmessage({data:JSON.stringify({type:'joined',seat:1,width:1920,height:1080})});
  assert.equal(h.element('game').width,1920);assert.equal(h.element('game').height,1080);
  h.run('setMenu(true)');
  h.element('game').dispatch('mousedown',{button:0,clientX:480,clientY:270});
  assert.deepEqual(ws.sent.at(-1),{type:'menu',x:0.5,y:0.5});
  ws.onmessage({data:JSON.stringify({type:'joined',seat:1,width:99999,height:1080})});
  assert.equal(ws.readyState,3);assert.match(h.element('feedback').textContent,/resolution/);
});

test('saved resolution stays fixed through resize, reconnect, slow FPS and page reload',async()=>{
  const storage=new Map();const h=harness([],storage);
  h.element('resolution').value='1440p';h.element('resolution').dispatch('change');
  assert.equal(storage.get('tournament-resolution'),'1440p');
  const ws=await h.join();const joined={type:'joined',seat:1,width:1280,height:720,fps:120,video:'h264'};
  ws.onmessage({data:JSON.stringify(joined)});assert.deepEqual(ws.sent.at(-1),{type:'resolution',resolution:'1440p'});
  const old=h.run('videoDecoder');
  ws.onmessage({data:JSON.stringify({type:'video-config',codec:'avc1.640033',width:2560,height:1440,fps:120})});
  assert.equal(old.closed,true);assert.equal(h.element('game').width,2560);assert.equal(h.element('game').height,1440);
  assert.equal(h.element('resolution').value,'1440p');
  h.advance(1000);h.run('frames=12');h.intervals.find(i=>i.ms===1000).fn();
  assert.equal(h.run('preferredResolution'),'1440p');assert.match(h.element('metrics').textContent,/12 FPS/);
  h.run('disconnect()');const next=await h.join();next.onmessage({data:JSON.stringify(joined)});
  assert.deepEqual(next.sent.at(-1),{type:'resolution',resolution:'1440p'});
  assert.equal(harness([],storage).element('resolution').value,'1440p');
});

test('resolution change releases held input and mouse and never locks the selector on failure',async()=>{
  const h=harness();const ws=await h.join();
  ws.onmessage({data:JSON.stringify({type:'joined',seat:1,width:1280,height:720,fps:120,video:'h264'})});
  await h.run('captureMouse()');h.window.dispatch('keydown',{code:'KeyW'});
  h.element('resolution').value='1080p';h.element('resolution').dispatch('change');
  assert.equal(h.document.pointerLockElement,null);assert.equal(h.run('held.size'),0);assert.equal(h.nativeMenu(),false);
  assert.deepEqual(ws.sent.at(-1),{type:'resolution',resolution:'1080p'});
  h.advance(16000);h.run('updateResolutionHelp()');assert.match(h.element('resolution-help').textContent,/still selected/);
  assert.equal(h.element('resolution').disabled,false);
});

test('Escape immediately after recapturing always releases the mouse',async()=>{
  const h=harness();await h.join();await h.run('captureMouse()');
  h.window.dispatch('keydown',{code:'Escape',repeat:false});
  assert.equal(h.document.pointerLockElement,null);
  h.advance(30);await h.run('captureMouse()');h.advance(30);
  h.window.dispatch('keydown',{code:'Escape',repeat:false});
  assert.equal(h.document.pointerLockElement,null);assert.equal(h.nativeMenu(),true);
});

test('Escape also releases a new lock before its asynchronous change event arrives',async()=>{
  const h=harness();await h.join();h.run('setMenu(true)');
  h.window.dispatch('keydown',{code:'Escape',repeat:false});
  h.advance(30);h.document.pointerLockElement=h.element('game');
  // The browser exposes the new lock before it dispatches pointerlockchange.
  h.window.dispatch('keydown',{code:'Escape',repeat:false});
  assert.equal(h.document.pointerLockElement,null);assert.equal(h.nativeMenu(),true);
});


test('hosted frontend routes join, health and video directly to its build-configured HTTPS gateway',async()=>{
  const h=harness([],new Map(),'https://game.example');
  const ws=await h.join();
  assert.equal(ws.url,'wss://game.example/stream');
  assert.ok(h.requestedURLs.includes('https://game.example/api/join'));
  assert.ok(h.requestedURLs.includes('https://game.example/api/health'));
  assert.throws(()=>harness([],new Map(),'http://game.example'));
  assert.throws(()=>harness([],new Map(),'https://game.example/path'));
  assert.throws(()=>harness([],new Map(),'https://user:pass@game.example'));
});


test('play fills the viewport, aiming hides chrome, Escape restores controls and disconnect exits play mode',async()=>{
  const h=harness();await h.join();
  assert.equal(h.document.body.classList.contains('playing'),true);
  await h.run('captureMouse()');assert.equal(h.document.body.classList.contains('aiming'),true);
  h.window.dispatch('keydown',{code:'Escape',repeat:false});
  assert.equal(h.document.body.classList.contains('aiming'),false);
  assert.equal(h.document.body.classList.contains('playing'),true);
  h.run('disconnect()');assert.equal(h.document.body.classList.contains('playing'),false);
});


test('Escape cancels a pending mouse capture even when the browser grants it afterward',async()=>{
  const h=harness();await h.join();h.run('setMenu(true)');
  let grant;h.element('game').requestPointerLock=()=>new Promise(resolve=>{grant=()=>{h.document.pointerLockElement=h.element('game');h.document.dispatch('pointerlockchange');resolve()}});
  const pending=h.run('captureMouse()');
  h.window.dispatch('keydown',{code:'Escape',repeat:false});
  grant();await pending;
  assert.equal(h.document.pointerLockElement,null);
  assert.equal(h.nativeMenu(),true);
  assert.equal(h.document.body.classList.contains('aiming'),false);
});
