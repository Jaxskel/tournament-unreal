import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import http from 'node:http';
import dgram from 'node:dgram';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { createGateway } from '../server.js';
import { FrameParser, MAX_FRAME, MAX_BUFFERED, sendLatestFrame, validateControl } from '../protocol.js';

const jpeg = Buffer.from([0xff, 0xd8, 0x01, 0x02, 0xff, 0xd9]);
const frame = (payload = jpeg) => {
  const size = Buffer.alloc(4);
  size.writeUInt32BE(payload.length);
  return Buffer.concat([size, payload]);
};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, timeout = 2000) {
  const start = Date.now();
  while (!check()) {
    if (Date.now() - start > timeout) throw new Error('Condition timed out');
    await pause(5);
  }
}
async function fixture(t, options = {}) {
  const udps = [];
  const received = [[], []];
  for (let i = 0; i < 2; i++) {
    const socket = dgram.createSocket('udp4');
    await new Promise(resolve => socket.bind(0, '127.0.0.1', resolve));
    socket.on('message', data => received[i].push(JSON.parse(data.toString())));
    udps.push(socket);
  }
  const gateway = await createGateway({ port: 0, nativePorts: [0, 0], udpPorts: udps.map(s => s.address().port), ...options });
  const origin = `http://127.0.0.1:${gateway.port}`;
  const natives = [];
  const websockets = [];
  t.after(async () => {
    for (const ws of websockets) ws.terminate();
    for (const native of natives) native.destroy();
    await gateway.close();
    for (const udp of udps) udp.close();
  });
  async function native(id, data = frame()) {
    const socket = net.connect(gateway.nativePorts[id], '127.0.0.1');
    socket.on('error', () => {});
    natives.push(socket);
    await once(socket, 'connect');
    if (data) { socket.write(data); await until(() => gateway.status().seats[id].frameAgeMs !== null); }
    return socket;
  }
  async function join(body = '{}', overrideOrigin = origin) {
    const response = await fetch(`${origin}/api/join`, { method: 'POST', headers: { Origin: overrideOrigin, 'Content-Type': 'application/json' }, body });
    return { status: response.status, body: await response.json() };
  }
  async function ws(token, path = '/stream') {
    const socket = new WebSocket(`ws://127.0.0.1:${gateway.port}${path}`, { origin });
    const packets = [];
    socket.on('error', () => {});
    socket.on('message', (value, binary) => packets.push(binary ? Buffer.from(value) : JSON.parse(value.toString())));
    websockets.push(socket);
    await once(socket, 'open');
    if (token) socket.send(JSON.stringify({ type: 'auth', token }));
    return { socket, packets };
  }
  return { gateway, origin, received, native, join, ws };
}

test('TCP parser handles byte-fragmented headers/payloads and coalesced frames in order', () => {
  const result = [];
  const parser = new FrameParser(value => result.push(value));
  const a = frame();
  for (const byte of a) parser.push(Buffer.from([byte]));
  parser.push(Buffer.concat([a, a]));
  assert.equal(result.length, 3);
  for (const value of result) assert.deepEqual(value, jpeg);
});

test('TCP parser rejects oversized, zero-length and non-JPEG frames before publishing', () => {
  for (const size of [0, MAX_FRAME + 1, 0xffffffff]) {
    const bytes = Buffer.alloc(4); bytes.writeUInt32BE(size);
    const parser = new FrameParser(() => assert.fail('published invalid frame'));
    assert.throws(() => parser.push(bytes), /length/);
    assert.equal(parser.payload, null);
  }
  assert.throws(() => new FrameParser(() => assert.fail()).push(frame(Buffer.from('nope'))), /JPEG/);
});

test('strict input schema clamps relative mouse and rejects commands, seat claims, malformed values', () => {
  assert.deepEqual(validateControl({ type: 'mouse', dx: -9999, dy: 9999 }), { type: 'mouse', dx: -300, dy: 300 });
  for (const value of [null, [], {type:'exec',command:'quit'}, {type:'key',key:'F4',down:true}, {type:'key',key:'W',down:1}, {type:'key',key:'W',down:true,seat:1}, {type:'mouse',dx:NaN,dy:0}, {type:'mouse',dx:Infinity,dy:0}, {type:'menu',x:-0.1,y:0.2}, {type:'menu',x:0.1,y:1.1}, {type:'reset',extra:true}, {type:'heartbeat'}, {type:'menu-state',open:1}, {type:'menu-state',open:true,seat:1}]) assert.equal(validateControl(value), null);
  assert.deepEqual(validateControl({type:'menu-state',open:false}), {type:'menu-state',open:false});
  assert.deepEqual(validateControl({type:'menu',x:0,y:1}), {type:'menu',x:0,y:1});
  assert.deepEqual(validateControl({type:'key',key:'Nine',down:false}), {type:'key',key:'Nine',down:false});
});

test('slow frame receiver drops new frames without queueing and resumes with latest', () => {
  const sent = [];
  const ws = { readyState: 1, bufferedAmount: MAX_BUFFERED + 1, send: value => sent.push(value) };
  for (let n = 0; n < 1000; n++) assert.equal(sendLatestFrame(ws, jpeg), false);
  assert.equal(sent.length, 0);
  ws.bufferedAmount = 0;
  assert.equal(sendLatestFrame(ws, jpeg), true);
  assert.deepEqual(sent, [jpeg]);
  ws.readyState = 3;
  assert.equal(sendLatestFrame(ws, jpeg), false);
});

test('two browsers get independent seats, ordered controls, frames, and release/reset on disconnect', async t => {
  const f = await fixture(t);
  const native0 = await f.native(0);
  const native1 = await f.native(1);
  const a = await f.join();
  const b = await f.join();
  assert.equal(a.status, 201); assert.equal(b.status, 201);
  assert.notEqual(a.body.token, b.body.token);
  assert.equal((await f.join()).status, 409);
  const wa = await f.ws(a.body.token);
  const wb = await f.ws(b.body.token);
  await until(() => wa.packets.some(Buffer.isBuffer) && wb.packets.some(Buffer.isBuffer));
  assert.equal(wa.packets[0].seat, 1); assert.equal(wb.packets[0].seat, 2);
  await until(() => f.received.every(p => p.length >= 2));
  assert.deepEqual(f.received[0][0], {type:'reset'});
  assert.deepEqual(f.received[1][0], {type:'reset'});
  f.received[0].length = 0; f.received[1].length = 0;
  const controls = [{type:'key',key:'W',down:true}, {type:'mouse',dx:999,dy:-500}, {type:'key',key:'W',down:false}, {type:'menu',x:0.5,y:0.3}, {type:'reset'}];
  for (const value of controls) wa.socket.send(JSON.stringify(value));
  wb.socket.send(JSON.stringify({type:'key',key:'Nine',down:true}));
  await until(() => f.received[0].length >= 5 && f.received[1].length >= 1);
  assert.deepEqual(f.received[0].slice(0,5), controls.map(validateControl));
  assert.deepEqual(f.received[1][0], {type:'key',key:'Nine',down:true});
  const newJpeg0 = Buffer.from([255,216,5,6,255,217]);
  const newJpeg1 = Buffer.from([255,216,7,8,255,217]);
  native0.write(frame(newJpeg0)); native1.write(frame(newJpeg1));
  await until(() => wa.packets.some(p => Buffer.isBuffer(p) && p.equals(newJpeg0)) && wb.packets.some(p => Buffer.isBuffer(p) && p.equals(newJpeg1)));
  assert.ok(!wa.packets.some(p => Buffer.isBuffer(p) && p.equals(newJpeg1)));
  wa.socket.terminate();
  await until(() => !f.gateway.status().seats[0].occupied);
  await until(() => f.received[0].some(p => p.type === 'reset'));
  assert.equal(f.gateway.status().players, 1);
  assert.equal((await f.join()).status, 201);
});

test('one-shot tokens cannot be reused and unauthenticated browsers cannot control a seat', async t => {
  const f = await fixture(t);
  await f.native(0);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => owner.packets.length > 0);
  const intruder = await f.ws(lease.body.token);
  await until(() => intruder.socket.readyState === 3);
  assert.equal(f.gateway.status().players, 1);
  const unauthenticated = await f.ws();
  unauthenticated.socket.send(JSON.stringify({type:'key',key:'W',down:true}));
  await until(() => unauthenticated.socket.readyState === 3);
  assert.ok(!f.received.flat().some(p => p.type === 'key'));
});

test('origins, hosts, arbitrary routes, join bodies and WS query tokens are rejected', async t => {
  const f = await fixture(t);
  assert.equal((await f.join('{}', 'https://evil.example')).status, 403);
  assert.equal((await f.join('{"seat":1}')).status, 400);
  assert.equal((await f.join('x'.repeat(1025))).status, 400);
  assert.equal(await new Promise(resolve => http.get(`${f.origin}/api/health`, {headers:{Host:'evil.example'}}, res => {res.resume(); resolve(res.statusCode);})), 403);
  assert.equal((await fetch(`${f.origin}/../server.js`)).status, 404);
  for (const [path, origin] of [['/stream?token=secret',f.origin], ['/stream','https://evil.example']]) {
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(`${f.origin.replace('http:', 'ws:')}${path}`, {origin});
      ws.on('open', () => {ws.terminate(); reject(new Error('unexpected upgrade'));});
      ws.on('error', resolve);
    });
  }
  const health = await (await fetch(`${f.origin}/api/health`)).text();
  assert.ok(!health.includes('127.0.0.1'));
  assert.ok(!health.includes('9101'));
});

test('pending lease expiry and browser inactivity release a seat', async t => {
  const f = await fixture(t, {leaseMs:35, idleMs:60, sweepMs:10});
  await f.native(0);
  const expired = await f.join();
  await until(() => !f.gateway.status().seats[0].occupied);
  const rejected = await f.ws(expired.body.token);
  await until(() => rejected.socket.readyState === 3);
  const next = await f.join();
  const owner = await f.ws(next.body.token);
  await until(() => owner.packets.length > 0);
  await until(() => owner.socket.readyState === 3);
  assert.equal(f.gateway.status().players, 0);
  await until(() => f.received[0].some(p => p.type === 'reset'));
});

test('native fragmented frames work over TCP; oversized stream is disconnected and frame cleared', async t => {
  const f = await fixture(t);
  assert.equal((await f.join()).status, 503);
  const native = await f.native(0, null);
  assert.equal((await f.join()).status, 503);
  const bytes = frame();
  for (const byte of bytes) native.write(Buffer.from([byte]));
  await until(() => f.gateway.status().seats[0].frameAgeMs !== null);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => owner.packets.some(Buffer.isBuffer));
  const oversized = Buffer.alloc(4); oversized.writeUInt32BE(MAX_FRAME + 1);
  native.write(oversized);
  await until(() => !f.gateway.status().seats[0].nativeConnected);
  assert.equal(f.gateway.status().seats[0].frameAgeMs, null);
  await until(() => owner.packets.some(p => p.type === 'stream-state' && p.state === 'waiting'));
  // A native restart can resume the same controlling browser without exposing a different seat.
  await f.native(0);
  await until(() => owner.packets.filter(Buffer.isBuffer).length === 2);
});

test('server heartbeat reaches only authenticated seats; reset retains heartbeat, exit stops it', async t => {
  const f = await fixture(t, {heartbeatMs:20});
  await f.native(0);
  const lease = await f.join();
  await pause(30);
  assert.equal(f.received[0].length, 0);
  const owner = await f.ws(lease.body.token);
  await until(() => f.received[0].some(p => p.type === 'heartbeat'));
  owner.socket.send(JSON.stringify({type:'reset'}));
  await until(() => f.received[0].filter(p => p.type === 'reset').length === 2);
  const count = f.received[0].filter(p => p.type === 'heartbeat').length;
  await until(() => f.received[0].filter(p => p.type === 'heartbeat').length > count);
  assert.equal(f.received[1].length, 0);
  owner.socket.terminate();
  await until(() => !f.gateway.status().seats[0].occupied);
  await pause(30);
  const after = f.received[0].filter(p => p.type === 'heartbeat').length;
  await pause(50);
  assert.equal(f.received[0].filter(p => p.type === 'heartbeat').length, after);
});

test('invalid authenticated controls reset the owner and cannot target another seat', async t => {
  const f = await fixture(t);
  await f.native(0); await f.native(1);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => owner.packets.length > 0);
  owner.socket.send(JSON.stringify({type:'key',key:'W',down:true,seat:1}));
  await until(() => owner.socket.readyState === 3);
  await until(() => f.received[0].filter(p => p.type === 'reset').length === 2);
  assert.ok(!f.received.flat().some(p => p.type === 'key'));
  assert.equal(f.gateway.status().seats[0].occupied, false);
});

test('oversized WebSocket payload closes the session and resets held input', async t => {
  const f = await fixture(t);
  await f.native(0);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => owner.packets.length > 0);
  owner.socket.send('x'.repeat(1025));
  await until(() => owner.socket.readyState === 3);
  assert.equal(f.gateway.status().players, 0);
  await until(() => f.received[0].filter(p => p.type === 'reset').length === 2);
});

test('explicit forwarded/public origins work without trusting arbitrary forwarded headers', async t => {
  const f = await fixture(t, {publicOrigin:'https://arena.example', extraOrigins:['http://127.0.0.1:8791']});
  for (const host of ['arena.example','127.0.0.1:8791']) {
    assert.equal(await new Promise(resolve => http.get(`${f.origin}/api/health`, {headers:{Host:host}}, res => {res.resume(); resolve(res.statusCode);})), 200);
  }
  assert.equal(await new Promise(resolve => http.get(`${f.origin}/api/health`, {headers:{Host:'evil.example','X-Forwarded-Host':'arena.example'}}, res => {res.resume(); resolve(res.statusCode);})), 403);
});

test('browser activity watchdog resets stale input and stops heartbeats while retaining reservation', async t => {
  const f = await fixture(t, {inputTimeoutMs:70, heartbeatMs:15, sweepMs:5, idleMs:2000});
  await f.native(0);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => owner.packets.some(p => p.type === 'joined'));
  owner.socket.send(JSON.stringify({type:'key',key:'W',down:true}));
  await until(() => f.received[0].some(p => p.type === 'key'));
  await until(() => owner.packets.some(p => p.type === 'input-state' && p.state === 'suspended'));
  await until(() => f.received[0].filter(p => p.type === 'reset').length >= 2);
  const heartbeats = f.received[0].filter(p => p.type === 'heartbeat').length;
  assert.ok(heartbeats > 0);
  await pause(50);
  assert.equal(f.received[0].filter(p => p.type === 'heartbeat').length, heartbeats);
  assert.equal(f.gateway.status().seats[0].occupied, true);
  assert.equal(owner.socket.readyState, 1);
  owner.socket.send(JSON.stringify({type:'ping',id:1}));
  await until(() => owner.packets.some(p => p.type === 'pong' && p.id === 1));
  await until(() => f.received[0].filter(p => p.type === 'heartbeat').length > heartbeats);
});

test('absolute menu state is seat-scoped, repeatable, restored after native restart, and closed for next owner', async t => {
  const f = await fixture(t);
  const native = await f.native(0);
  await f.native(1);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => f.received[0].length >= 2);
  assert.deepEqual(f.received[0].slice(0,2), [{type:'reset'}, {type:'menu-state',open:false}]);
  owner.socket.send(JSON.stringify({type:'menu-state',open:true}));
  owner.socket.send(JSON.stringify({type:'menu-state',open:true}));
  await until(() => f.received[0].filter(p => p.type === 'menu-state' && p.open).length === 2);
  assert.equal(f.received[1].length, 0);
  native.destroy();
  await until(() => !f.gateway.status().seats[0].nativeConnected);
  await f.native(0);
  await until(() => f.received[0].filter(p => p.type === 'menu-state' && p.open).length === 3);
  owner.socket.terminate();
  await until(() => !f.gateway.status().seats[0].occupied);
  const next = await f.join();
  await f.ws(next.body.token);
  await until(() => f.received[0].filter(p => p.type === 'menu-state' && !p.open).length >= 3);
  assert.deepEqual(f.received[0].at(-1), {type:'menu-state',open:false});
});

test('late controls are preceded by reset even before a watchdog sweep', async t => {
  const f = await fixture(t, {inputTimeoutMs:35, sweepMs:1000, heartbeatMs:1000});
  await f.native(0);
  const lease = await f.join();
  const owner = await f.ws(lease.body.token);
  await until(() => f.received[0].length >= 2);
  f.received[0].length = 0;
  await pause(50);
  owner.socket.send(JSON.stringify({type:'key',key:'D',down:true}));
  await until(() => f.received[0].length >= 2);
  assert.deepEqual(f.received[0].slice(0,2), [{type:'reset'}, {type:'key',key:'D',down:true}]);
});

test('H264 seats stay isolated across video reset, stale acknowledgements, and encoder restart', async t => {
  const {RAW_BYTES,videoPacket}=await import('../video.js');
  const encoders=[];
  class TestEncoder {
    constructor(_path,onFrame){this.onFrame=onFrame;this.seq=0;this.closed=false;this.dropped=0;encoders.push(this);}
    push(raw){const key=raw[0]===1;const payload=Buffer.from([0,0,1,key?0x65:0x41,raw[1]]);this.onFrame({seq:++this.seq,key,codec:'avc1.42c020',capturedAt:Date.now(),data:videoPacket(payload,this.seq,Date.now(),key)});}
    close(){this.closed=true;}
  }
  const raw=(key,marker)=>{const bytes=Buffer.alloc(RAW_BYTES);bytes[0]=key?1:0;bytes[1]=marker;return frame(bytes);};
  const f=await fixture(t,{ffmpegPath:process.execPath,Encoder:TestEncoder});
  const a=await f.native(0,raw(true,11));await f.native(1,raw(true,22));
  const wa=await f.ws((await f.join()).body.token);const wb=await f.ws((await f.join()).body.token);
  await until(()=>wa.packets.some(Buffer.isBuffer)&&wb.packets.some(Buffer.isBuffer));
  assert.equal(wa.packets[0].video,'h264');assert.equal(wa.packets[1].type,'video-config');
  const picture=packets=>packets.filter(Buffer.isBuffer);
  assert.equal(picture(wa.packets)[0].at(-1),11);assert.equal(picture(wb.packets)[0].at(-1),22);
  wa.socket.send(JSON.stringify({type:'video-ack',seq:1}));
  wa.socket.send(JSON.stringify({type:'video-reset'}));await pause(10);
  a.write(raw(false,33));await pause(15);assert.equal(picture(wa.packets).length,1);
  a.write(raw(true,44));await until(()=>picture(wa.packets).length===2);
  const last=picture(wa.packets).at(-1).readUInt32BE(4);assert.equal(last,3);
  a.destroy();await until(()=>!f.gateway.status().seats[0].nativeConnected);
  assert.equal(encoders[0].closed,true);
  await f.native(0,raw(true,55));await until(()=>picture(wa.packets).length===3);
  wa.socket.send(JSON.stringify({type:'video-ack',seq:last}));await pause(15);
  assert.equal(wa.socket.readyState,1);assert.equal(f.gateway.status().players,2);
  assert.equal(picture(wa.packets).at(-1).readUInt32BE(4),4);
  assert.equal(picture(wb.packets).length,1);
  wa.socket.send(JSON.stringify({type:'video-ack',seq:999999}));await once(wa.socket,'close');
  assert.equal(f.gateway.status().seats[0].occupied,false);assert.equal(wb.socket.readyState,1);
});

test('video acknowledgements do not refresh the held-input watchdog', async t => {
  const {RAW_BYTES,videoPacket}=await import('../video.js');
  class Encoder {
    constructor(_path,onFrame){this.onFrame=onFrame;}
    push(){this.onFrame({seq:1,key:true,codec:'avc1.42c020',capturedAt:Date.now(),data:videoPacket(Buffer.from([0,0,1,0x65]),1,Date.now(),true)});}
    close(){}
  }
  const f=await fixture(t,{ffmpegPath:process.execPath,Encoder,inputTimeoutMs:50,sweepMs:5,heartbeatMs:10});
  await f.native(0,frame(Buffer.alloc(RAW_BYTES)));
  const wa=await f.ws((await f.join()).body.token);await until(()=>wa.packets.some(Buffer.isBuffer));
  wa.socket.send(JSON.stringify({type:'key',key:'W',down:true}));
  const ack=setInterval(()=>wa.socket.send(JSON.stringify({type:'video-ack',seq:1})),10);
  t.after(()=>clearInterval(ack));
  await until(()=>wa.packets.some(p=>p.type==='input-state'&&p.state==='suspended'));
  assert.ok(f.received[0].some(p=>p.type==='reset'));assert.equal(wa.socket.readyState,1);
});

test('stream frame rate is validated before binding any listener',async()=>{
  await assert.rejects(createGateway({fps:1000}),/Stream FPS/);
});
