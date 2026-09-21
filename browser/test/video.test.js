import test from 'node:test';
import assert from 'node:assert/strict';
import { AccessUnitParser, inspectUnit, videoPacket, VideoWindow, RAW_BYTES } from '../video.js';
import { FrameParser } from '../protocol.js';
const aud = Buffer.from([0,0,0,1,9,0xf0]);
const idr = Buffer.concat([aud,Buffer.from([0,0,0,1,0x67,0x42,0xc0,0x20,0,0,1,0x65,55])]);
const delta = Buffer.concat([aud,Buffer.from([0,0,1,0x41,44])]);
test('Annex B access units survive every pipe split and byte-at-a-time delivery', () => {
  const stream=Buffer.concat([idr,delta,delta]);
  for(let split=0;split<=stream.length;split++){
    const units=[];const parser=new AccessUnitParser(unit=>units.push(Buffer.from(unit)));
    parser.push(stream.subarray(0,split));parser.push(stream.subarray(split));
    assert.deepEqual(units,[idr,delta],`split ${split}`);
  }
  const units=[];const parser=new AccessUnitParser(unit=>units.push(Buffer.from(unit)));
  for(const byte of stream)parser.push(Buffer.from([byte]));
  assert.deepEqual(units,[idr,delta]);
  assert.deepEqual(inspectUnit(idr),{key:true,codec:'avc1.42c020'});
});
test('raw framing rejects wrong sizes and encoded parser bounds memory',()=>{
  const frames=[];const parser=new FrameParser(frame=>frames.push(frame),RAW_BYTES);
  const header=Buffer.alloc(4);header.writeUInt32BE(RAW_BYTES);
  parser.push(header.subarray(0,2));parser.push(Buffer.concat([header.subarray(2),Buffer.alloc(RAW_BYTES)]));
  assert.equal(frames.length,1);assert.equal(frames[0].length,RAW_BYTES);
  header.writeUInt32BE(RAW_BYTES-1);
  assert.throws(()=>new FrameParser(()=>{},RAW_BYTES).push(header));
  assert.throws(()=>new AccessUnitParser(()=>{}).push(Buffer.alloc(4*1024*1024+1)));
});
test('slow receiver discards predictions until acknowledged and a fresh keyframe arrives',()=>{
  const sent=[];const ws={readyState:1,bufferedAmount:0,send:data=>sent.push(data)};
  const window=new VideoWindow();const frame=(seq,key=false)=>({seq,key,data:Buffer.from([seq])});
  assert.equal(window.send(ws,frame(1),0),false);
  assert.equal(window.send(ws,frame(2,true),0),true);
  assert.equal(window.send(ws,frame(3),201),false);
  assert.equal(window.ack(999),false);assert.equal(window.ack(2),true);
  assert.equal(window.send(ws,frame(4),202),false);
  assert.equal(window.send(ws,frame(5,true),203),true);
  window.reset();assert.equal(window.ack(5),true);
  assert.equal(window.send(ws,frame(6),204),false);
  assert.equal(sent.length,2);
});
test('video header preserves sequence, source clock, key flag, and Annex B payload',()=>{
  const packet=videoPacket(idr,123,12345678.5,true);
  assert.equal(packet[0],0x48);assert.equal(packet[1],1);assert.equal(packet[2],1);
  assert.equal(packet.readUInt32BE(4),123);assert.equal(packet.readDoubleBE(8),12345678.5);
  assert.deepEqual(packet.subarray(16),idr);
});

test('120 FPS acknowledgement window preserves the 200 ms bound without unnecessary half-rate drops',()=>{
  const sent=[];const ws={readyState:1,bufferedAmount:0,send:x=>sent.push(x)};
  const window=new VideoWindow(120);const frame=(seq,key=false)=>({seq,key,data:Buffer.from([seq])});
  for(let i=1;i<=24;i++)assert.equal(window.send(ws,frame(i,i===1),(i-1)*1000/120),true);
  assert.equal(window.send(ws,frame(25),200),false);assert.equal(window.pending.length,24);
  assert.equal(window.ack(24),true);assert.equal(window.send(ws,frame(26),210),false);
  assert.equal(window.send(ws,frame(27,true),220),true);assert.equal(window.pending.length,1);
});

test('encoder tolerates pipe backpressure but never queues more than three pictures',async()=>{
  const {HardwareEncoder}=await import('../video.js');
  let writes=0;const encoder={rawBytes:RAW_BYTES,closed:false,times:[],dropped:0,process:{stdin:{write:()=>{writes++;return false;}}}};
  const raw=Buffer.alloc(RAW_BYTES);
  for(let i=0;i<20;i++)HardwareEncoder.prototype.push.call(encoder,raw);
  assert.equal(writes,3);assert.equal(encoder.times.length,3);assert.equal(encoder.dropped,17);
  encoder.times.shift();HardwareEncoder.prototype.push.call(encoder,raw);
  assert.equal(writes,4);assert.equal(encoder.times.length,3);
});


test('HD raw frames accept only the selected bounded profile, without widening JPEG limits',async()=>{
  const {videoProfile}=await import('../video.js');
  for(const resolution of ['540p','720p','1080p']) {
    const {rawBytes,width,height}=videoProfile(resolution);
    assert.equal(rawBytes,width*height*4);
    const header=Buffer.alloc(4);header.writeUInt32BE(rawBytes);
    let length=0;const parser=new FrameParser(frame=>length=frame.length,rawBytes);
    parser.push(header);parser.push(Buffer.alloc(rawBytes));assert.equal(length,rawBytes);
    header.writeUInt32BE(rawBytes+4);assert.throws(()=>new FrameParser(()=>{},rawBytes).push(header));
  }
  assert.throws(()=>videoProfile('8k'));
  assert.throws(()=>new FrameParser(()=>{},999999999));
  const header=Buffer.alloc(4);header.writeUInt32BE(1920*1080*4);
  assert.throws(()=>new FrameParser(()=>{}).push(header));
});
