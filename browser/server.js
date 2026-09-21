import http from 'node:http';
import net from 'node:net';
import dgram from 'node:dgram';
import { randomBytes } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';
import { FrameParser, MAX_BUFFERED, sendLatestFrame, validateControl } from './protocol.js';

const LOOPBACK = '127.0.0.1';
const sendJSON = (ws, value) => {
  if (ws.readyState === 1 && ws.bufferedAmount <= MAX_BUFFERED) ws.send(JSON.stringify(value));
};
const json = (res, code, body) => {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(body));
};
function normalizeOrigin(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== value || url.username || url.password) throw new Error('PUBLIC_ORIGIN must be an exact http(s) origin without a trailing slash');
  return url;
}
function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, LOOPBACK, () => { server.off('error', reject); resolve(server.address().port); });
  });
}
async function emptyJson(req) {
  if (req.headers['content-type']?.split(';')[0] !== 'application/json') throw new Error('Expected JSON');
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1024) throw new Error('Request too large');
    chunks.push(chunk);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString() || '{}');
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length) throw new Error('No seat or other parameters accepted');
}

export async function createGateway(options = {}) {
  const publicOrigin = options.publicOrigin ? normalizeOrigin(options.publicOrigin) : null;
  const extraOrigins = (options.extraOrigins ?? []).map(normalizeOrigin);
  const leaseMs = options.leaseMs ?? 10_000;
  const idleMs = options.idleMs ?? 90_000;
  const inputTimeoutMs = options.inputTimeoutMs ?? 3000;
  const authMs = options.authMs ?? 5_000;
  const frameFreshMs = options.frameFreshMs ?? 10_000;
  const udpPorts = options.udpPorts ?? [9101, 9102];
  const nativePorts = options.nativePorts ?? [9001, 9002];
  if (udpPorts.length !== 2 || nativePorts.length !== 2) throw new Error('Exactly two seats required');
  const configuredOrigins = [...(publicOrigin ? [publicOrigin] : []), ...extraOrigins];
  const origins = new Set(configuredOrigins.map(url => url.origin));
  const hosts = new Set(configuredOrigins.map(url => url.host));
  const assets = new Map(await Promise.all([
    ['/', 'index.html', 'text/html; charset=utf-8'],
    ['/app.js', 'app.js', 'text/javascript; charset=utf-8'],
    ['/style.css', 'style.css', 'text/css; charset=utf-8'],
  ].map(async ([route, file, type]) => [route, { data: await readFile(new URL(`./public/${file}`, import.meta.url)), type }])));
  const udp = dgram.createSocket('udp4');
  udp.on('error', () => {}); // Missing native listener does not crash the HTTP gateway.
  await new Promise(resolve => udp.bind(0, LOOPBACK, resolve));
  const seats = [0, 1].map(id => ({ id, native: null, frame: null, frameAt: 0, frames: 0, dropped: 0, lease: null }));
  const leases = new Map();
  const sockets = new Set();
  const httpSockets = new Set();
  let closed = false;
  function control(seat, message) {
    if (!closed) udp.send(Buffer.from(JSON.stringify(message)), udpPorts[seat.id], LOOPBACK, () => {});
  }
  function release(lease, code = 1000, reason = 'Seat released') {
    if (!lease || leases.get(lease.token) !== lease) return;
    leases.delete(lease.token);
    if (lease.seat.lease === lease) lease.seat.lease = null;
    control(lease.seat, { type: 'reset' });
    control(lease.seat, { type: 'menu-state', open: false });
    if (lease.ws && lease.ws.readyState < 2) lease.ws.close(code, reason);
  }
  function suspendStaleInput(lease, now) {
    if (!lease.ws || now - lease.lastActivity < inputTimeoutMs) return false;
    if (!lease.inputStale) {
      lease.inputStale = true;
      control(lease.seat, { type: 'reset' });
      sendJSON(lease.ws, { type: 'input-state', state: 'suspended' });
    }
    return true;
  }
  function markActivity(lease, now) {
    // Catch a late message even if the periodic watchdog has not run yet.
    suspendStaleInput(lease, now);
    lease.lastActivity = now;
    lease.inputStale = false;
  }
  function status() {
    return {
      service: 'Tournament Unreal live demo', rewards: false, audio: false,
      players: seats.filter(s => s.lease?.ws?.readyState === 1).length,
      capacity: 2,
      seats: seats.map(s => ({ seat: s.id + 1, nativeConnected: !!s.native, frameAgeMs: s.frameAt ? Date.now() - s.frameAt : null, occupied: !!s.lease })),
    };
  }
  const allowedHost = req => typeof req.headers.host === 'string' && hosts.has(req.headers.host);
  const sameOrigin = req => {
    if (!allowedHost(req) || !origins.has(req.headers.origin)) return false;
    return new URL(req.headers.origin).host === req.headers.host;
  };
  const server = http.createServer({ maxHeaderSize: 8192, requestTimeout: 10_000, headersTimeout: 10_000 }, async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
    res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), fullscreen=(self)');
    if (!allowedHost(req)) return json(res, 403, { error: 'Unrecognized host' });
    if (req.method === 'GET' && req.url === '/api/health') return json(res, 200, status());
    if (req.method === 'POST' && req.url === '/api/join') {
      if (!sameOrigin(req)) return json(res, 403, { error: 'Same-origin request required' });
      try { await emptyJson(req); } catch { return json(res, 400, { error: 'Expected an empty JSON object (max 1024 bytes)' }); }
      const now = Date.now();
      for (const lease of leases.values()) if (!lease.ws && now > lease.expiresAt) release(lease);
      const seat = seats.find(s => !s.lease && s.native && now - s.frameAt < frameFreshMs && s.frame);
      if (!seat) {
        const full = seats.every(s => s.lease);
        return json(res, full ? 409 : 503, { error: full ? 'Both seats are in use. Try again when a player leaves.' : 'The arena is reconnecting.', code: full ? 'full' : 'recovering' });
      }
      const token = randomBytes(32).toString('base64url');
      const lease = { token, seat, expiresAt: now + leaseMs, lastActivity: now, inputStale: false, menuOpen: false, ws: null };
      seats[seat.id].lease = lease;
      leases.set(token, lease);
      return json(res, 201, { token, expiresInMs: leaseMs, websocket: '/stream' });
    }
    if ((req.method === 'GET' || req.method === 'HEAD') && assets.has(req.url)) {
      const asset = assets.get(req.url);
      res.writeHead(200, { 'Content-Type': asset.type, 'Content-Length': asset.data.length });
      return res.end(req.method === 'HEAD' ? undefined : asset.data);
    }
    json(res, 404, { error: 'Not found' });
  });
  server.on('connection', socket => { httpSockets.add(socket); socket.on('close', () => httpSockets.delete(socket)); });
  server.on('clientError', (_error, socket) => socket.destroy());
  const wss = new WebSocketServer({ noServer: true, maxPayload: 1024, perMessageDeflate: false, closeTimeout: 1000 });
  server.on('upgrade', (req, socket, head) => {
    if (req.url !== '/stream' || !sameOrigin(req) || sockets.size >= 8) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
      return;
    }
    wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws));
  });
  wss.on('connection', ws => {
    sockets.add(ws);
    let owned = null;
    let budget = 480;
    let budgetAt = Date.now();
    const timer = setTimeout(() => ws.close(1008, 'Authentication timeout'), authMs);
    timer.unref();
    ws.on('error', () => {});
    ws.on('close', () => { clearTimeout(timer); sockets.delete(ws); release(owned); });
    ws.on('message', (raw, binary) => {
      if (ws.readyState !== 1) return;
      let value;
      try { if (binary) throw new Error(); value = JSON.parse(raw.toString()); } catch { ws.close(1008, 'Invalid JSON control'); return; }
      if (!owned) {
        if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'token,type' || value.type !== 'auth' || typeof value.token !== 'string') { ws.close(1008, 'Authentication required'); return; }
        const lease = leases.get(value.token);
        if (!lease || lease.ws || Date.now() > lease.expiresAt) { ws.close(1008, 'Invalid or expired lease'); return; }
        owned = lease;
        lease.ws = ws;
        lease.lastActivity = Date.now();
        clearTimeout(timer);
        control(lease.seat, { type: 'reset' });
        control(lease.seat, { type: 'menu-state', open: false });
        sendJSON(ws, { type: 'joined', seat: lease.seat.id + 1, width: 960, height: 540, audio: false });
        if (lease.seat.frame) sendLatestFrame(ws, lease.seat.frame);
        return;
      }
      const now = Date.now();
      budget = Math.min(480, budget + (now - budgetAt) * 0.24);
      budgetAt = now;
      if (--budget < 0) { release(owned, 1008, 'Control rate exceeded'); return; }
      if (value?.type === 'ping' && Object.keys(value).sort().join(',') === 'id,type' && Number.isSafeInteger(value.id) && value.id >= 0) {
        markActivity(owned, now);
        sendJSON(ws, { type: 'pong', id: value.id });
        return;
      }
      const validated = validateControl(value);
      if (!validated) { release(owned, 1008, 'Unsupported control'); return; }
      markActivity(owned, now);
      if (validated.type === 'menu-state') owned.menuOpen = validated.open;
      if (owned.seat.native || validated.type === 'reset') control(owned.seat, validated);
    });
  });
  const nativeServers = seats.map(seat => net.createServer(socket => {
    if (seat.native || closed) { socket.destroy(); return; }
    seat.native = socket;
    // Restore the controlling browser's requested menu state after native restart.
    // Only for a leased seat; unleased native startup receives no control traffic.
    if (seat.lease?.ws?.readyState === 1) {
      control(seat, { type: 'reset' });
      control(seat, { type: 'menu-state', open: seat.lease.menuOpen });
    }
    socket.setNoDelay(true);
    socket.setTimeout(15_000, () => socket.destroy());
    const parser = new FrameParser(frame => {
      seat.frame = frame;
      seat.frameAt = Date.now();
      seat.frames++;
      if (seat.lease?.ws && !sendLatestFrame(seat.lease.ws, frame)) seat.dropped++;
    });
    socket.on('error', () => {});
    socket.on('data', chunk => { try { parser.push(chunk); } catch { socket.destroy(); } });
    socket.on('close', () => {
      if (seat.native !== socket) return;
      seat.native = null;
      seat.frame = null;
      seat.frameAt = 0;
      control(seat, { type: 'reset' });
      const ws = seat.lease?.ws;
      if (ws?.readyState === 1) sendJSON(ws, { type: 'stream-state', state: 'waiting' });
    });
  }));
  const interval = setInterval(() => {
    const now = Date.now();
    for (const lease of leases.values()) {
      suspendStaleInput(lease, now);
      if ((!lease.ws && now > lease.expiresAt) || (lease.ws && now - lease.lastActivity > idleMs)) release(lease, 1000, 'Session expired');
    }
  }, options.sweepMs ?? 100);
  interval.unref();
  const heartbeat = setInterval(() => {
    const now = Date.now();
    for (const seat of seats) {
      const lease = seat.lease;
      if (lease?.ws?.readyState === 1 && !suspendStaleInput(lease, now)) control(seat, { type: 'heartbeat' });
    }
  }, options.heartbeatMs ?? 1000);
  heartbeat.unref();
  let port;
  let actualNativePorts;
  async function close() {
    if (closed) return;
    clearInterval(interval);
    clearInterval(heartbeat);
    for (const lease of leases.values()) release(lease, 1001, 'Gateway stopping');
    // Allow queued loopback reset datagrams to be handed to the OS before close.
    await new Promise(resolve => setImmediate(resolve));
    closed = true;
    for (const ws of sockets) ws.terminate();
    for (const seat of seats) seat.native?.destroy();
    for (const socket of httpSockets) socket.destroy();
    await Promise.all([server, ...nativeServers].map(s => new Promise(resolve => s.close(() => resolve()))));
    wss.close();
    await new Promise(resolve => udp.close(resolve));
  }
  try {
    port = await listen(server, options.port ?? 8890);
    origins.add(`http://127.0.0.1:${port}`);
    origins.add(`http://localhost:${port}`);
    hosts.add(`127.0.0.1:${port}`);
    hosts.add(`localhost:${port}`);
    actualNativePorts = await Promise.all(nativeServers.map((s, i) => listen(s, nativePorts[i])));
  } catch (error) { await close(); throw error; }
  return { port, nativePorts: actualNativePorts, close, status };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const portFromEnv = (name, fallback) => {
    const port = Number(process.env[name] ?? fallback);
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`Invalid ${name}`);
    return port;
  };
  try {
    const gateway = await createGateway({
      port: portFromEnv('PORT', 8890), publicOrigin: process.env.PUBLIC_ORIGIN,
      extraOrigins: process.env.EXTRA_ORIGINS?.split(',').map(s => s.trim()).filter(Boolean),
      nativePorts: [portFromEnv('SEAT0_FRAME_PORT', 9001), portFromEnv('SEAT1_FRAME_PORT', 9002)],
      udpPorts: [portFromEnv('SEAT0_INPUT_PORT', 9101), portFromEnv('SEAT1_INPUT_PORT', 9102)],
    });
    console.log(`Tournament browser gateway: http://127.0.0.1:${gateway.port}`);
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => gateway.close().then(() => process.exit(0)));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
