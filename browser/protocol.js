export const MAX_FRAME = 4 * 1024 * 1024;
export const MAX_BUFFERED = 512 * 1024;
export const KEYS = new Set([
  'W', 'A', 'S', 'D', 'SpaceBar', 'LeftShift', 'LeftControl',
  'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
  'Escape', 'Tab', 'Enter', 'Up', 'Down', 'Left', 'Right', 'LeftMouseButton', 'RightMouseButton',
]);
const exact = (value, fields) => Object.keys(value).sort().join(',') === fields.sort().join(',');
export function validateControl(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  if (value.type === 'menu-state' && exact(value, ['type', 'open']) && typeof value.open === 'boolean') return { type: 'menu-state', open: value.open };
  if (value.type === 'reset' && exact(value, ['type'])) return { type: 'reset' };
  if (value.type === 'key' && exact(value, ['type', 'key', 'down']) && KEYS.has(value.key) && typeof value.down === 'boolean') {
    return { type: 'key', key: value.key, down: value.down };
  }
  if (value.type === 'mouse' && exact(value, ['type', 'dx', 'dy']) && Number.isFinite(value.dx) && Number.isFinite(value.dy)) {
    const clamp = n => Math.max(-300, Math.min(300, n));
    return { type: 'mouse', dx: clamp(value.dx), dy: clamp(value.dy) };
  }
  if (value.type === 'menu' && exact(value, ['type', 'x', 'y']) && Number.isFinite(value.x) && Number.isFinite(value.y) && value.x >= 0 && value.x <= 1 && value.y >= 0 && value.y <= 1) {
    return { type: 'menu', x: value.x, y: value.y };
  }
  return null;
}

// A bounded streaming parser: four header bytes and at most one allocated frame.
export class FrameParser {
  constructor(onFrame, rawBytes = 0) {
    if (![0,960*540*4,1280*720*4,1920*1080*4].includes(rawBytes)) throw new Error('Invalid raw frame profile');
    this.rawBytes = rawBytes;
    this.onFrame = onFrame;
    this.header = Buffer.alloc(4);
    this.headerBytes = 0;
    this.payload = null;
    this.payloadBytes = 0;
  }
  push(chunk) {
    let offset = 0;
    while (offset < chunk.length) {
      if (!this.payload) {
        const count = Math.min(4 - this.headerBytes, chunk.length - offset);
        chunk.copy(this.header, this.headerBytes, offset, offset + count);
        this.headerBytes += count;
        offset += count;
        if (this.headerBytes < 4) continue;
        const length = this.header.readUInt32BE(0);
        if ((this.rawBytes && length !== this.rawBytes) || length < 4 || length > (this.rawBytes || MAX_FRAME)) throw new Error('Invalid frame length');
        this.payload = Buffer.allocUnsafe(length);
        this.payloadBytes = 0;
        this.headerBytes = 0;
      }
      const count = Math.min(this.payload.length - this.payloadBytes, chunk.length - offset);
      chunk.copy(this.payload, this.payloadBytes, offset, offset + count);
      this.payloadBytes += count;
      offset += count;
      if (this.payloadBytes === this.payload.length) {
        const frame = this.payload;
        this.payload = null;
        this.payloadBytes = 0;
        if (!this.rawBytes && (frame[0] !== 0xff || frame[1] !== 0xd8 || frame[frame.length - 2] !== 0xff || frame[frame.length - 1] !== 0xd9)) throw new Error('Expected JPEG markers');
        this.onFrame(frame);
      }
    }
  }
}
export function sendLatestFrame(socket, frame) {
  if (!socket || socket.readyState !== 1 || socket.bufferedAmount > MAX_BUFFERED) return false;
  socket.send(frame, { binary: true, compress: false });
  return true;
}
