import { spawn } from 'node:child_process';

export function videoProfile(resolution = '720p', fps = 120) {
  const sizes = {'540p':[960,540,6,4], '720p':[1280,720,12,8], '1080p':[1920,1080,24,16], '1440p':[2560,1440,40,28]};
  if (!Object.hasOwn(sizes, resolution) || ![60,120].includes(fps)) throw new Error('Invalid video profile');
  const [width,height,fastMbps,normalMbps] = sizes[resolution];
  return {width,height,rawBytes:width*height*4,bitrateMbps:fps===120?fastMbps:normalMbps};
}
export const RAW_BYTES = videoProfile().rawBytes;
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
  constructor(path, onFrame, onFailure, {fps = 120, resolution = '720p'} = {}) {
    if (![60,120].includes(fps)) throw new Error('Stream FPS must be 60 or 120');
    const profile = videoProfile(resolution, fps);
    this.rawBytes = profile.rawBytes;
    const bitrate = `${profile.bitrateMbps}M`;
    this.closed = false; this.times = []; this.seq = 0; this.codec = null;
    this.dropped = 0; this.error = ''; this.lastInput = 0; this.lastOutput = Date.now();
    this.process = spawn(path, [
      '-hide_banner', '-loglevel', 'error', '-filter_threads', '1', '-threads', '1', '-f', 'rawvideo', '-pixel_format', 'bgra',
      '-video_size', `${profile.width}x${profile.height}`, '-framerate', String(fps), '-i', 'pipe:0', '-an',
      '-c:v', 'h264_nvenc', '-preset', 'p3', '-tune', 'ull', '-zerolatency', '1', '-delay', '0',
      '-rc', 'cbr', '-b:v', bitrate, '-maxrate', bitrate, '-bufsize', `${profile.bitrateMbps * 32}k`,
      '-g', '10', '-bf', '0', '-rc-lookahead', '0', '-aud', '1',
      '-profile:v', 'high', '-pix_fmt', 'nv12', '-fps_mode', 'passthrough',
      '-flush_packets', '1', '-f', 'h264', 'pipe:1',
    ], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    const fail = error => { if (!this.closed) { this.close(); onFailure(error); } };
    this.process.on('error', fail);
    this.process.on('exit', code => fail(new Error(`Encoder exited (${code}): ${this.error}`)));
    this.process.stdin.on('error', fail);
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
    if (frame.length !== this.rawBytes) throw new Error('Invalid raw frame size');
    // At most three pictures total across the pipe, encoder and AU delimiter.
    // A large write exceeding Node's small high-water mark is not itself a
    // reason to lose the next picture; the explicit in-flight bound controls it.
    if (this.closed || this.times.length >= 3) { this.dropped++; return; }
    this.times.push(Date.now());
    this.process.stdin.write(frame);
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
  constructor(fps = 60) { this.maxPending = Math.ceil(fps / 5); this.reset(); }
  reset() { this.pending = []; this.lastSent ??= 0; this.waitKey = true; this.dropped = 0; }
  ack(seq) {
    if (!Number.isSafeInteger(seq) || seq < 0 || seq > this.lastSent) return false;
    this.pending = this.pending.filter(frame => frame.seq > seq);
    return true;
  }
  send(ws, frame, now = Date.now()) {
    if (ws.readyState !== 1) return false;
    if (this.pending.length >= this.maxPending || ws.bufferedAmount > 64 * 1024 || (this.pending.length && now - this.pending[0].at > 200)) {
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
