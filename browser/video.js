import { spawn } from 'node:child_process';

export const RAW_BYTES = 960 * 540 * 4;
const START = Buffer.from([0, 0, 1]);
const MAX_UNIT = 4 * 1024 * 1024;
// NVENC emits one AUD per picture. Keep only the current access unit and handle
// delimiters split across pipe reads. No assumptions about stdout chunk sizes.
export class AccessUnitParser {
  constructor(onUnit) { this.buffer = Buffer.alloc(0); this.scan = 0; this.start = -1; this.onUnit = onUnit; }
  push(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    for (;;) {
      const p = this.buffer.indexOf(START, this.scan);
      if (p < 0 || p + 3 >= this.buffer.length) { this.scan = Math.max(this.scan, this.buffer.length - 4); break; }
      this.scan = p + 4;
      if ((this.buffer[p + 3] & 31) !== 9) continue;
      const boundary = p > 0 && this.buffer[p - 1] === 0 ? p - 1 : p;
      if (this.start >= 0 && boundary > this.start) {
        this.onUnit(this.buffer.subarray(this.start, boundary));
        this.buffer = this.buffer.subarray(boundary);
        this.scan -= boundary;
        this.start = 0;
      } else this.start = boundary;
    }
    if (this.buffer.length > MAX_UNIT) throw new Error('Oversized encoded access unit');
  }
}
export function inspectUnit(data) {
  let key = false, codec = null;
  for (let p = data.indexOf(START); p >= 0; p = data.indexOf(START, p + 3)) {
    const type = data[p + 3] & 31;
    if (type === 5) key = true;
    if (type === 7 && p + 6 < data.length) codec = `avc1.${data.subarray(p + 4, p + 7).toString('hex')}`;
  }
  return { key, codec };
}
export function videoPacket(data, seq, capturedAt, key) {
  const header = Buffer.alloc(16);
  header[0] = 0x48; header[1] = 1; header[2] = key ? 1 : 0;
  header.writeUInt32BE(seq >>> 0, 4);
  header.writeDoubleBE(capturedAt, 8);
  return Buffer.concat([header, data]);
}
export class HardwareEncoder {
  constructor(path, onFrame, onFailure) {
    this.closed = false; this.blocked = false; this.times = []; this.seq = 0; this.codec = null;
    this.dropped = 0; this.error = ''; this.lastInput = 0; this.lastOutput = Date.now();
    this.process = spawn(path, [
      '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'bgra',
      '-video_size', '960x540', '-framerate', '60', '-i', 'pipe:0', '-an',
      '-c:v', 'h264_nvenc', '-preset', 'p1', '-tune', 'ull', '-zerolatency', '1', '-delay', '0',
      '-rc', 'cbr', '-b:v', '4M', '-maxrate', '4M', '-bufsize', '128k',
      '-g', '10', '-bf', '0', '-rc-lookahead', '0', '-aud', '1',
      '-profile:v', 'baseline', '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough',
      '-flush_packets', '1', '-f', 'h264', 'pipe:1',
    ], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    const fail = error => { if (!this.closed) { this.close(); onFailure(error); } };
    this.process.on('error', fail);
    this.process.on('exit', code => fail(new Error(`Encoder exited (${code}): ${this.error}`)));
    this.process.stdin.on('error', fail);
    this.process.stdin.on('drain', () => { this.blocked = false; });
    this.process.stderr.on('data', data => { this.error = (this.error + data.toString()).slice(-2000); });
    const parser = new AccessUnitParser(data => {
      this.lastOutput = Date.now();
      const {key, codec} = inspectUnit(data);
      if (codec) this.codec = codec;
      const capturedAt = this.times.shift();
      if (capturedAt === undefined || !this.codec) return;
      onFrame({ data: videoPacket(data, ++this.seq, capturedAt, key), key, codec: this.codec, seq: this.seq, capturedAt });
    });
    this.process.stdout.on('data', data => { try { parser.push(data); } catch (error) { fail(error); } });
    this.watchdog = setInterval(() => {
      if (Date.now() - this.lastInput < 2000 && Date.now() - this.lastOutput > 5000) fail(new Error('Video encoder stopped producing frames'));
    }, 1000);
    this.watchdog.unref();
  }
  push(frame) {
    this.lastInput = Date.now();
    if (frame.length !== RAW_BYTES) throw new Error('Invalid raw frame size');
    // At most one stdin write plus two pictures in the encoder/demuxer. Drop at
    // the raw boundary, before inter-frame prediction creates dependencies.
    if (this.closed || this.blocked || this.times.length >= 3) { this.dropped++; return; }
    this.times.push(Date.now());
    this.blocked = !this.process.stdin.write(frame);
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    clearInterval(this.watchdog);
    this.process.stdin.destroy(); this.process.stdout.destroy();
    this.process.kill(); this.times.length = 0;
  }
}

// Browser acknowledgements bound queues beyond the Cloudflare TCP endpoint.
// A dropped predicted frame makes subsequent deltas unusable until an IDR.
export class VideoWindow {
  constructor() { this.reset(); }
  reset() { this.pending = []; this.lastSent ??= 0; this.waitKey = true; this.dropped = 0; }
  ack(seq) {
    if (!Number.isSafeInteger(seq) || seq < 0 || seq > this.lastSent) return false;
    this.pending = this.pending.filter(frame => frame.seq > seq);
    return true;
  }
  send(ws, frame, now = Date.now()) {
    if (ws.readyState !== 1) return false;
    if (this.pending.length >= 12 || ws.bufferedAmount > 64 * 1024 || (this.pending.length && now - this.pending[0].at > 200)) {
      this.waitKey = true; this.dropped++; return false;
    }
    if (this.waitKey && !frame.key) { this.dropped++; return false; }
    this.waitKey = false;
    this.lastSent = frame.seq;
    this.pending.push({seq:frame.seq,at:now});
    ws.send(frame.data, {binary:true,compress:false});
    return true;
  }
}
