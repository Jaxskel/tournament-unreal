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
