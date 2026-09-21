import test from 'node:test';
import assert from 'node:assert/strict';
import { once, EventEmitter } from 'node:events';
import net from 'node:net';
import dgram from 'node:dgram';
import { WebSocket, WebSocketServer } from 'ws';
import { createGateway } from './gateway.mjs';
const origin = 'http://127.0.0.1:8000';
const frame = text => { const body = Buffer.from(text); const out = Buffer.alloc(4 + body.length); out.writeUInt32LE(body.length); body.copy(out, 4); return out; };
async function fixture(t, maxPlayers = 6) {
  const udp = dgram.createSocket('udp4');
  const peers = new Set();
  udp.on('message', (message, peer) => { peers.add(peer.port); udp.send(message, peer.port, peer.address); });
  udp.bind(0, '127.0.0.1'); await once(udp, 'listening');
  const gateway = createGateway({gameHost: '127.0.0.1', gamePort: udp.address().port, origins: [origin], maxPlayers});
  gateway.server.listen(0, '127.0.0.1'); await once(gateway.server, 'listening');
  t.after(async () => { await gateway.close(); await new Promise(resolve => udp.close(resolve)); });
  const url = `ws://127.0.0.1:${gateway.server.address().port}/game`;
  return { peers, url, udp, gateway, async connect() {const ws = new WebSocket(url, 'binary', {origin}); await once(ws, 'open'); return ws;} };
}

test('two players have isolated UDP sessions; closing one leaves the other working', {timeout:5000}, async t => {
  const f = await fixture(t); const a = await f.connect(); const b = await f.connect();
  const ra = once(a, 'message'); const rb = once(b, 'message');
  a.send(frame('alpha')); b.send(frame('bravo'));
  assert.deepEqual((await ra)[0], frame('alpha')); assert.deepEqual((await rb)[0], frame('bravo'));
  assert.equal(f.peers.size, 2);
  a.close(); await once(a, 'close');
  const next = once(b, 'message'); b.send(frame('still connected')); assert.deepEqual((await next)[0], frame('still connected'));
});
test('split headers, split bodies and coalesced packets retain every byte', {timeout:5000}, async t => {
  const f = await fixture(t); const ws = await f.connect(); const packets = [];
  const complete = new Promise(resolve => ws.on('message', data => { packets.push(data); if (packets.length === 3) resolve(); }));
  const wire = Buffer.concat([frame('one'), frame('two'), frame('three')]);
  ws.send(wire.subarray(0,2)); ws.send(wire.subarray(2,6)); ws.send(wire.subarray(6));
  await complete; assert.deepEqual(packets, ['one','two','three'].map(frame));
});
for (const [name, data, binary, expected] of [
  ['zero length',Buffer.alloc(4),true,1009],
  ['oversized length',Buffer.from([1,64,0,0]),true,1009],
  ['negative-looking length',Buffer.from([255,255,255,255]),true,1009],
  ['text packet','hello',false,1003]
]) test(`rejects ${name}`, {timeout:5000}, async t => {
  const f = await fixture(t); const ws = await f.connect(); const closed = once(ws,'close'); ws.send(data,{binary});
  assert.equal((await closed)[0], expected); assert.equal(f.peers.size,0);
});
async function rejected(url, headers, expected, protocols = 'binary') {
  const ws = new WebSocket(url,protocols,headers);
  ws.on('error',()=>{});
  const [req,res] = await once(ws,'unexpected-response');
  assert.equal(res.statusCode,expected); res.resume(); req.destroy(); ws.terminate();
}
test('rejects wrong origins, destination injection and excess players', {timeout:5000}, async t => {
  const f = await fixture(t,1);
  await rejected(f.url,{origin:'https://wrong.example'},403);
  await rejected(f.url+'?server=attacker',{origin},404);
  await f.connect(); await rejected(f.url,{origin},503);
});
test('bounds coalesced packet queues', {timeout:5000}, async t => {
  const f = await fixture(t); const ws = await f.connect(); const closed = once(ws,'close');
  const flood = Buffer.concat(Array.from({length:1100},()=>frame('x'))); ws.send(flood);
  assert.equal((await closed)[0],1013);
});

// Control completion independently of native queue sizes: the OS may report an
// empty queue while Node still retains buffers waiting for send callbacks.
class FakeUDP extends EventEmitter {
  sent = [];
  callbacks = [];
  queueBytes = 0;
  queueCount = 0;
  closeCalls = 0;
  connect(port, host, callback) {
    this.destination = {port, host};
    this.connected = callback;
    if (this.connectError) throw this.connectError;
  }
  send(packet, callback) {
    if (this.sendError) throw this.sendError;
    this.sent.push(Buffer.from(packet));
    if (this.autoSend) callback();
    else this.callbacks.push(callback);
  }
  getSendQueueSize() { return this.queueBytes; }
  getSendQueueCount() { return this.queueCount; }
  close() {
    this.closeCalls++;
    if (!this.holdClose) this.finishClose();
  }
  finishClose() {
    if (this.closed) return;
    this.closed = true;
    this.emit('close');
  }
}
class FakeWS extends EventEmitter {
  readyState = WebSocket.OPEN;
  bufferedAmount = 0;
  replies = [];
  callbacks = [];
  send(packet, options, callback) {
    assert.equal(options.binary, true);
    if (this.sendError) throw this.sendError;
    this.replies.push(Buffer.from(packet));
    this.callbacks.push(callback);
  }
  close(code, reason) {
    this.closeCode = code;
    this.closeReason = reason;
    this.readyState = WebSocket.CLOSING;
    if (!this.holdClose) queueMicrotask(() => this.terminate());
  }
  terminate() {
    if (this.readyState === WebSocket.CLOSED) return;
    this.readyState = WebSocket.CLOSED;
    this.emit('close');
  }
  ping() {}
}
function controlled(t, {udpOptions = {}, wsOptions = {}, maxPlayers = 1} = {}) {
  let next;
  const created = [];
  t.mock.method(dgram, 'createSocket', () => next.udp);
  t.mock.method(WebSocketServer.prototype, 'handleUpgrade', function(req, socket, head, callback) {
    created.push(next);
    callback(next.ws);
  });
  const gateway = createGateway({gameHost: 'fixed.example', gamePort: 7787, origins: [origin], maxPlayers});
  t.after(async () => {
    for (const {udp} of created) { udp.holdClose = false; udp.finishClose(); }
    await gateway.close();
  });
  return {gateway, connect() {
    next = {udp: Object.assign(new FakeUDP(), udpOptions), ws: Object.assign(new FakeWS(), wsOptions)};
    const socket = new EventEmitter();
    socket.setTimeout = () => {};
    socket.destroy = () => {};
    socket.end = (response, callback) => { next.response = response; callback(); };
    gateway.server.emit('upgrade', {url: '/game', headers: {origin, 'sec-websocket-protocol': 'binary'}}, socket, Buffer.alloc(0));
    return next;
  }};
}
const deliver = (ws, data) => ws.emit('message', data, true);

test('failed asynchronous UDP connect discards queued packets and closes the session', async t => {
  const f = controlled(t); const {ws, udp} = f.connect();
  deliver(ws, frame('queued'));
  udp.connected(new Error('lookup failed'));
  assert.equal(ws.closeCode, 1011);
  assert.equal(udp.sent.length, 0);
  assert.equal(udp.closed, true);
  deliver(ws, frame('late'));
  assert.equal(udp.sent.length, 0);
});
for (const operation of ['connect', 'send']) test(`synchronous UDP ${operation} failure is contained`, async t => {
  const f = controlled(t, {udpOptions: {[`${operation}Error`]: new Error('socket failed')}});
  const {ws, udp} = f.connect();
  if (operation === 'send') { udp.connected(); deliver(ws, frame('hello')); }
  assert.equal(ws.closeCode, 1011);
  assert.equal(udp.closed, true);
});
test('asynchronous UDP send failure stops forwarding and late callbacks are harmless', async t => {
  const f = controlled(t); const {ws, udp} = f.connect();
  udp.connected(); deliver(ws, Buffer.concat([frame('a'), frame('b')]));
  udp.callbacks[0](new Error('send failed')); udp.callbacks[1]();
  deliver(ws, frame('late'));
  assert.equal(ws.closeCode, 1011); assert.equal(udp.sent.length, 2);
});
test('delayed connect flushes packets in order to the fixed destination', async t => {
  const f = controlled(t); const {ws, udp} = f.connect();
  deliver(ws, Buffer.concat([frame('a'), frame('b')]));
  assert.equal(udp.sent.length, 0);
  udp.connected();
  assert.deepEqual(udp.destination, {host: 'fixed.example', port: 7787});
  assert.deepEqual(udp.sent, [Buffer.from('a'), Buffer.from('b')]);
});
test('closing before connect prevents queued or late traffic and retries a failed bind cleanup', async t => {
  const f = controlled(t, {udpOptions: {holdClose: true}}); const {ws, udp} = f.connect();
  deliver(ws, frame('queued')); ws.terminate();
  assert.equal(udp.closeCalls, 1);
  udp.holdClose = false;
  udp.emit('error', new Error('implicit bind failed'));
  assert.equal(udp.closed, true);
  udp.connected(); udp.emit('message', Buffer.from('late'));
  assert.equal(udp.sent.length, 0); assert.equal(ws.replies.length, 0);
});
for (const ready of [false, true]) {
  test(`packet count bounds ${ready ? 'in-flight' : 'pre-connect'} UDP sends`, async t => {
    const f = controlled(t); const {ws, udp} = f.connect();
    if (ready) udp.connected();
    deliver(ws, Buffer.concat(Array.from({length: 256}, () => frame('x'))));
    assert.equal(ws.readyState, WebSocket.OPEN);
    deliver(ws, frame('x'));
    assert.equal(ws.closeCode, 1013);
    assert.equal(udp.sent.length, ready ? 256 : 0);
  });
  test(`byte count bounds ${ready ? 'in-flight' : 'pre-connect'} UDP sends`, async t => {
    const f = controlled(t); const {ws, udp} = f.connect();
    if (ready) udp.connected();
    for (let i = 0; i < 16; i++) deliver(ws, frame(Buffer.alloc(16384)));
    assert.equal(ws.readyState, WebSocket.OPEN);
    deliver(ws, frame('x'));
    assert.equal(ws.closeCode, 1013);
    assert.equal(udp.sent.length, ready ? 16 : 0);
  });
}
test('successful callbacks release UDP queue capacity', async t => {
  const f = controlled(t); const {ws, udp} = f.connect(); udp.connected();
  deliver(ws, Buffer.concat(Array.from({length: 256}, () => frame('x'))));
  for (const callback of udp.callbacks.splice(0)) callback();
  deliver(ws, frame('another'));
  assert.equal(ws.readyState, WebSocket.OPEN); assert.equal(udp.sent.length, 257);
});
for (const [name, options] of [
  ['bytes including the next packet', {queueBytes: 256 * 1024}],
  ['packet count', {queueCount: 256}]
]) test(`native UDP queue bounds ${name}`, async t => {
  const f = controlled(t, {udpOptions: options}); const {ws, udp} = f.connect(); udp.connected();
  deliver(ws, frame('x'));
  assert.equal(ws.closeCode, 1013); assert.equal(udp.sent.length, 0);
});
for (const [name, size, count] of [['packet count', 1, 256], ['bytes', 16384, 15]]) {
  test(`server replies bound ${name} while send callbacks are pending`, async t => {
    const f = controlled(t); const {ws, udp} = f.connect(); udp.connected();
    for (let i = 0; i < count; i++) udp.emit('message', Buffer.alloc(size));
    assert.equal(ws.readyState, WebSocket.OPEN);
    udp.emit('message', Buffer.alloc(size));
    assert.equal(ws.closeCode, 1013); assert.equal(ws.replies.length, count);
    for (const callback of ws.callbacks) callback();
  });
}
test('reply bound includes the next packet and framing, and callbacks release capacity', async t => {
  const f = controlled(t); const {ws, udp} = f.connect(); udp.connected();
  for (let i = 0; i < 256; i++) udp.emit('message', Buffer.from('x'));
  for (const callback of ws.callbacks.splice(0)) callback();
  udp.emit('message', Buffer.from('y'));
  assert.equal(ws.readyState, WebSocket.OPEN);
  ws.bufferedAmount = 256 * 1024 - 6;
  udp.emit('message', Buffer.from('z'));
  assert.equal(ws.closeCode, 1013); assert.equal(ws.replies.length, 257);
});
for (const asynchronous of [false, true]) test(`${asynchronous ? 'async' : 'sync'} WebSocket reply errors clean up UDP`, async t => {
  const f = controlled(t); const {ws, udp} = f.connect(); udp.connected();
  if (!asynchronous) ws.sendError = new Error('write failed');
  udp.emit('message', Buffer.from('x'));
  if (asynchronous) ws.callbacks[0](new Error('write failed'));
  assert.equal(ws.closeCode, 1011); assert.equal(udp.closed, true);
});
for (const size of [0, 16385]) test(`invalid ${size}-byte server packet is rejected`, async t => {
  const f = controlled(t); const {ws, udp} = f.connect(); udp.connected(); udp.emit('message', Buffer.alloc(size));
  assert.equal(ws.closeCode, 1009); assert.equal(ws.replies.length, 0);
});
test('admission remains reserved through WebSocket and UDP cleanup', async t => {
  const f = controlled(t, {wsOptions: {holdClose: true}, udpOptions: {holdClose: true}});
  const {ws, udp} = f.connect(); deliver(ws, Buffer.alloc(4));
  assert.match(f.connect().response, /^HTTP\/1.1 503 /);
  ws.terminate();
  assert.match(f.connect().response, /^HTTP\/1.1 503 /);
  udp.finishClose();
  assert.equal(f.connect().response, undefined);
});
test('shutdown is idempotent, waits for UDP closure and blocks admission', async t => {
  const f = controlled(t, {udpOptions: {holdClose: true}}); const {udp, ws} = f.connect();
  const closing = f.gateway.close(); let finished = false; closing.then(() => { finished = true; });
  assert.equal(f.gateway.close(), closing);
  assert.match(f.connect().response, /^HTTP\/1.1 503 /);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(finished, false); assert.equal(ws.readyState, WebSocket.CLOSED);
  udp.finishClose(); await closing;
  udp.connected(); assert.equal(udp.sent.length, 0);
});
test('connect timeout releases a stalled session', async t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const f = controlled(t); const {ws, udp} = f.connect(); deliver(ws, frame('queued'));
  t.mock.timers.tick(10000);
  assert.equal(ws.closeCode, 1011); assert.equal(udp.closed, true);
  udp.connected(); assert.equal(udp.sent.length, 0);
});
test('packet-rate budget counts each coalesced datagram even with immediate sends', async t => {
  const f = controlled(t, {udpOptions: {autoSend: true}}); const {ws, udp} = f.connect(); udp.connected();
  deliver(ws, Buffer.concat(Array.from({length: 1100}, () => frame('x'))));
  assert.equal(ws.closeCode, 1008); assert.ok(udp.sent.length < 1000);
});
test('byte-rate budget charges partial application packets', async t => {
  const f = controlled(t, {udpOptions: {autoSend: true}}); const {ws, udp} = f.connect(); udp.connected();
  const packet = frame(Buffer.alloc(16384));
  for (let i = 0; i < 100 && ws.readyState === WebSocket.OPEN; i++) {
    deliver(ws, packet.subarray(0, 16000)); deliver(ws, packet.subarray(16000));
  }
  assert.equal(ws.closeCode, 1008);
});
test('empty binary message floods consume the message budget', async t => {
  const f = controlled(t); const {ws, udp} = f.connect();
  for (let i = 0; i < 1100; i++) deliver(ws, Buffer.alloc(0));
  assert.equal(ws.closeCode, 1008); assert.equal(udp.sent.length, 0);
});

test('real WebSocket fragmentation preserves application framing', {timeout: 5000}, async t => {
  // Stay below platform-specific UDP datagram limits (macOS defaults to 9216).
  const f = await fixture(t); const ws = await f.connect(); const expected = frame(Buffer.alloc(2048, 42));
  const reply = once(ws, 'message');
  ws.send(expected.subarray(0, 2), {fin: false}); ws.send(expected.subarray(2, 100), {fin: false}); ws.send(expected.subarray(100));
  assert.deepEqual((await reply)[0], expected);
});
test('fragmented oversized WebSocket messages are rejected before UDP forwarding', {timeout: 5000}, async t => {
  const f = await fixture(t); const ws = await f.connect(); const closed = once(ws, 'close');
  ws.send(Buffer.alloc(40000), {fin: false}); ws.send(Buffer.alloc(30000));
  assert.equal((await closed)[0], 1009); assert.equal(f.peers.size, 0);
});
test('excessive empty WebSocket fragments are bounded before a complete message', {timeout: 5000}, async t => {
  const f = await fixture(t); const ws = await f.connect(); const closed = once(ws, 'close');
  for (let i = 0; i < 1025; i++) ws.send(Buffer.alloc(0), {fin: false});
  assert.equal((await closed)[0], 1008); assert.equal(f.peers.size, 0);
});
test('valid packet followed by a malformed header never forwards the malformed tail', {timeout: 5000}, async t => {
  const f = await fixture(t); const ws = await f.connect();
  const warmup = once(ws, 'message'); ws.send(frame('warmup')); await warmup;
  const received = []; f.udp.on('message', packet => received.push(packet.toString()));
  const closed = once(ws, 'close'); ws.send(Buffer.concat([frame('valid'), Buffer.alloc(4), frame('ignored')]));
  assert.equal((await closed)[0], 1009);
  assert.ok(received.every(packet => packet === 'valid'));
});
test('connected UDP filters a foreign sender while accepting the fixed server', {timeout: 5000}, async t => {
  const f = await fixture(t); const ws = await f.connect();
  const rogue = dgram.createSocket('udp4'); t.after(() => new Promise(resolve => rogue.close(resolve)));
  const replies = []; ws.on('message', packet => replies.push(packet));
  const first = once(ws, 'message'); ws.send(frame('first')); await first;
  const [port] = f.peers;
  await new Promise((resolve, reject) => rogue.send(Buffer.from('foreign'), port, '127.0.0.1', error => error ? reject(error) : resolve()));
  const next = once(ws, 'message'); ws.send(frame('second')); await next;
  assert.deepEqual(replies, [frame('first'), frame('second')]);
});
test('origins match exactly, binary protocol is required and rejected upgrades consume no slots', {timeout: 5000}, async t => {
  const f = await fixture(t, 1);
  for (const value of [undefined, 'null', origin + '/', origin + '.evil', 'http://localhost:8000', 'https://127.0.0.1:8000', 'http://127.0.0.1:8001']) {
    await rejected(f.url, value ? {origin: value} : {}, 403);
  }
  await rejected(f.url, {origin}, 400, 'other');
  await rejected(f.url, {origin}, 400, []);
  const ws = await f.connect(); assert.equal(ws.protocol, 'binary');
});
test('configuration rejects non-web or non-canonical origins and invalid destinations', () => {
  const valid = {gameHost: '127.0.0.1', gamePort: 7787, origins: [origin]};
  for (const origins of [[], ['null'], ['ftp://example.com'], ['blob:https://example.com/id'], [origin + '/'], ['http://user@example.com'], ['http://EXAMPLE.com'], ['https://example.com:443'], [42], origin]) {
    assert.throws(() => createGateway({...valid, origins}), /exact browser origins/);
  }
  for (const gameHost of [42, {}, '', '   ', ' 127.0.0.1']) assert.throws(() => createGateway({...valid, gameHost}), /game server/);
  for (const gamePort of [0, -1, 65536, 1.5, '7787']) assert.throws(() => createGateway({...valid, gamePort}), /game server/);
  for (const maxPlayers of [0, 65, 1.5]) assert.throws(() => createGateway({...valid, maxPlayers}), /player limit/);
});
test('shutdown closes incomplete HTTP connections and active game sessions', {timeout: 5000}, async t => {
  const f = await fixture(t); const ws = await f.connect();
  const raw = net.connect(f.gateway.server.address().port, '127.0.0.1');
  raw.on('error', error => assert.equal(error.code, 'ECONNRESET'));
  t.after(() => raw.destroy()); await once(raw, 'connect'); raw.write('GET /health HTTP/1.1\r\n');
  const rawClosed = new Promise(resolve => raw.once('close', resolve)); const wsClosed = once(ws, 'close');
  await f.gateway.close(); await Promise.all([rawClosed, wsClosed]);
  assert.equal(f.gateway.server.listening, false);
});
