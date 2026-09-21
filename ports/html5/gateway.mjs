// Original game-packet proxy. Never accepts a destination from a browser.
import http from 'node:http';
import dgram from 'node:dgram';
import { pathToFileURL } from 'node:url';
import { WebSocketServer, WebSocket } from 'ws';

const MAX_PACKET = 16384;
const MAX_BACKLOG = 256 * 1024;
const MAX_QUEUED_PACKETS = 256;
const CONNECT_TIMEOUT = 10000;

export function createGateway({ gameHost, gamePort, origins, maxPlayers = 6 }) {
  if (typeof gameHost !== 'string' || !gameHost.trim() || gameHost !== gameHost.trim() ||
      !Number.isInteger(gamePort) || gamePort < 1 || gamePort > 65535)
    throw new Error('Configure one game server host and port');
  const allowed = new Set(typeof origins === 'string' ? [] : origins);
  if (!allowed.size || [...allowed].some(value => {
    try {
      const url = new URL(value);
      return !['http:', 'https:'].includes(url.protocol) || url.origin !== value;
    } catch { return true; }
  })) throw new Error('Configure exact browser origins');
  if (!Number.isInteger(maxPlayers) || maxPlayers < 1 || maxPlayers > 64)
    throw new Error('Invalid player limit');
  const sessions = new Set();
  const connections = new Set();
  let stopping = false, shutdown;
  const server = http.createServer((req, res) => {
    res.writeHead(req.url === '/health' ? 200 : 404, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'});
    res.end(JSON.stringify(req.url === '/health' ? { transport: 'game-packets', players: sessions.size, maxPlayers } : { error: 'not-found' }));
  });
  server.on('connection', socket => {
    connections.add(socket);
    socket.once('close', () => connections.delete(socket));
    if (stopping) socket.destroy();
  });
  const sockets = new WebSocketServer({ noServer: true, maxPayload: 65536, perMessageDeflate: false,
    maxFragments: 1024, maxBufferedChunks: 1024, closeTimeout: 1000,
    handleProtocols: protocols => protocols.has('binary') ? 'binary' : false });
  server.on('upgrade', (req, socket, head) => {
    const protocols = (req.headers['sec-websocket-protocol'] || '').split(',').map(s => s.trim());
    const status = stopping ? 503 : req.url !== '/game' ? 404 : !allowed.has(req.headers.origin) ? 403 :
      !protocols.includes('binary') ? 400 : sessions.size >= maxPlayers ? 503 : 0;
    if (status) {
      socket.on('error', () => socket.destroy());
      socket.setTimeout(1000, () => socket.destroy());
      socket.end(`HTTP/1.1 ${status} Rejected\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`, () => socket.destroy());
      return;
    }
    sockets.handleUpgrade(req, socket, head, ws => sockets.emit('connection', ws));
  });
  sockets.on('connection', ws => {
    let udp, udpClosed = false, wsClosed = false, finish;
    const done = new Promise(resolve => { finish = resolve; });
    const session = { ws, alive: true, done, close };
    sessions.add(session);
    let closed = false, ready = false, pending = [], carry = Buffer.alloc(0), connectTimer;
    let queuedBytes = 0, queuedPackets = 0, replyBytes = 0, replyPackets = 0;
    let budget = 1000, lastRefill = performance.now();
    function release() {
      // Keep admission reserved until both transports actually finish closing.
      if (wsClosed && udpClosed) { sessions.delete(session); finish(); }
    }
    function closeUDP() {
      if (!udp || udpClosed) return;
      try { udp.close(); } catch (error) {
        if (error.code === 'ERR_SOCKET_DGRAM_NOT_RUNNING') { udpClosed = true; release(); }
        else throw error;
      }
    }
    function close(code = 1000, reason = '') {
      if (closed) return;
      closed = true; pending = []; carry = Buffer.alloc(0);
      clearTimeout(connectTimer);
      closeUDP();
      if (ws.readyState === WebSocket.OPEN) ws.close(code, reason);
    }
    function dispatch(packet) {
      if (closed) return;
      try {
        if (udp.getSendQueueSize() + packet.length > MAX_BACKLOG ||
            udp.getSendQueueCount() >= MAX_QUEUED_PACKETS) return close(1013, 'Network backlog');
        udp.send(packet, error => {
          queuedBytes -= packet.length; queuedPackets--;
          if (error) close(1011, 'Game server unavailable');
        });
      } catch { close(1011, 'Game server unavailable'); }
    }
    function send(packet) {
      if (closed) return;
      // Include connect-time packets and sends waiting for their callbacks. The
      // native UDP queue alone does not account for all retained JS buffers.
      if (queuedBytes + packet.length > MAX_BACKLOG || queuedPackets >= MAX_QUEUED_PACKETS)
        return close(1013, 'Connection backlog');
      queuedBytes += packet.length; queuedPackets++;
      // Do not pin an entire coalesced WebSocket message for a small datagram.
      packet = Buffer.from(packet);
      if (!ready) pending.push(packet);
      else dispatch(packet);
    }
    ws.on('message', (data, binary) => {
      if (closed) return;
      if (!binary) return close(1003, 'Binary game packets required');
      const now = performance.now();
      budget = Math.min(1000, budget + (now - lastRefill) / 2); lastRefill = now;
      // Charge bytes as well as message count, including incomplete fragments.
      budget -= Math.max(1, data.length / 1024);
      if (budget < 0) return close(1008, 'Packet rate exceeded');
      const chunk = carry.length ? Buffer.concat([carry, data]) : data;
      let offset = 0;
      while (chunk.length - offset >= 4) {
        const size = chunk.readUInt32LE(offset);
        if (!size || size > MAX_PACKET) return close(1009, 'Invalid packet size');
        if (chunk.length - offset < size + 4) break;
        if (--budget < 0) return close(1008, 'Packet rate exceeded');
        send(chunk.subarray(offset + 4, offset + 4 + size));
        if (closed) return;
        offset += 4 + size;
      }
      // Copy only the incomplete tail; never retain a large WebSocket frame.
      carry = Buffer.from(chunk.subarray(offset));
    });
    ws.on('pong', () => { session.alive = true; });
    ws.on('close', () => { wsClosed = true; close(); release(); });
    ws.on('error', () => close());
    try { udp = dgram.createSocket('udp4'); }
    catch { udpClosed = true; close(1011, 'Game server unavailable'); return; }
    udp.on('close', () => { udpClosed = true; close(1011, 'Game server unavailable'); release(); });
    udp.on('error', () => {
      // close() can have been queued behind an implicit bind that then failed.
      if (closed) closeUDP();
      else close(1011, 'Game server unavailable');
    });
    udp.on('message', packet => {
      if (closed || ws.readyState !== WebSocket.OPEN) return;
      if (!packet.length || packet.length > MAX_PACKET) return close(1009, 'Invalid server packet');
      const frameBytes = 4 + packet.length;
      const wireBytes = frameBytes + (frameBytes < 126 ? 2 : 4);
      if (Math.max(ws.bufferedAmount, replyBytes) + wireBytes > MAX_BACKLOG ||
          replyPackets >= MAX_QUEUED_PACKETS) return close(1013, 'Network backlog');
      const frame = Buffer.allocUnsafe(frameBytes);
      frame.writeUInt32LE(packet.length); packet.copy(frame, 4);
      replyBytes += wireBytes; replyPackets++;
      try {
        ws.send(frame, {binary: true}, error => {
          replyBytes -= wireBytes; replyPackets--;
          if (error) close(1011, 'Connection lost');
        });
      } catch { close(1011, 'Connection lost'); }
    });
    connectTimer = setTimeout(() => close(1011, 'Game server unavailable'), CONNECT_TIMEOUT);
    connectTimer.unref();
    // Connected UDP filters replies to this configured server and isolates peers.
    try {
      udp.connect(gamePort, gameHost, error => {
        if (closed) { closeUDP(); return; }
        if (error) return close(1011, 'Game server unavailable');
        clearTimeout(connectTimer);
        ready = true;
        const queued = pending; pending = [];
        for (const packet of queued) {
          dispatch(packet);
          if (closed) break;
        }
      });
    } catch { close(1011, 'Game server unavailable'); }
  });
  const heartbeat = setInterval(() => {
    for (const session of sessions) {
      if (session.ws.readyState !== WebSocket.OPEN) continue;
      if (!session.alive) { session.close(); session.ws.terminate(); continue; }
      session.alive = false; session.ws.ping();
    }
  }, 30000); heartbeat.unref();
  return {
    server,
    close() {
      if (shutdown) return shutdown;
      stopping = true;
      clearInterval(heartbeat);
      const httpClosed = new Promise(resolve => server.close(resolve));
      const active = [...sessions];
      for (const session of active) { session.close(); session.ws.terminate(); }
      for (const socket of connections) socket.destroy();
      shutdown = Promise.all([httpClosed, new Promise(resolve => sockets.close(resolve)),
        ...active.map(session => session.done)]).then(() => {});
      return shutdown;
    }
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const gateway = createGateway({ gameHost: process.env.GAME_HOST || '127.0.0.1',
    gamePort: Number(process.env.GAME_PORT || 7787),
    origins: (process.env.BROWSER_ORIGINS || 'http://127.0.0.1:8000').split(',') });
  gateway.server.listen(Number(process.env.PORT || 9080), '127.0.0.1', () => console.log('Local game-packet gateway ready'));
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => gateway.close());
}
