import test from 'node:test';
import assert from 'node:assert/strict';
import { GameVideoDecoder } from '../public/video-client.js';
import { videoPacket } from '../video.js';
function harness(t, fps = 60) {
  const instances=[],sent=[],drawn=[],errors=[];
  class Decoder {
    constructor(callbacks){this.callbacks=callbacks;this.state='unconfigured';this.decodeQueueSize=0;this.chunks=[];instances.push(this);}
    configure(config){this.config=config;this.state='configured';}
    decode(chunk){this.chunks.push(chunk);}
    close(){assert.notEqual(this.state,'closed');this.state='closed';}
  }
  const oldDecoder=globalThis.VideoDecoder,oldChunk=globalThis.EncodedVideoChunk;
  t.after(()=>{globalThis.VideoDecoder=oldDecoder;globalThis.EncodedVideoChunk=oldChunk;});
  globalThis.VideoDecoder=Decoder;
  globalThis.EncodedVideoChunk=class {constructor(init){Object.assign(this,init);}};
  const client=new GameVideoDecoder({fps,send:m=>sent.push(m),draw:frame=>drawn.push(frame),failure:(error,fatal)=>errors.push({error,fatal})});
  client.configure('avc1.42c020');
  const push=(seq,key=false)=>{const b=videoPacket(Buffer.from([0,0,1,0x65]),seq,Date.now(),key);client.push(b.buffer.slice(b.byteOffset,b.byteOffset+b.length));};
  return {client,instances,sent,drawn,errors,push};
}
// Globals exist only in browsers; install placeholders so mock.method can restore them.
globalThis.VideoDecoder=class {};
globalThis.EncodedVideoChunk=class {};
test('decoder requires a keyframe initially and after packet loss',t=>{
  const h=harness(t);h.push(1);h.push(2,true);h.push(4);h.push(5);h.push(6,true);
  assert.deepEqual(h.instances[0].chunks.map(c=>c.type),['key','key']);
  assert.equal(h.sent.filter(m=>m.type==='video-ack').length,5);
});
test('decoder overload resets immediately and closes decoded frames',t=>{
  const h=harness(t);h.push(1,true);h.instances[0].decodeQueueSize=3;h.push(2);
  assert.equal(h.instances[0].state,'closed');assert.equal(h.instances.length,2);
  assert.equal(h.instances[1].chunks.length,0);h.push(3,true);
  let closed=0;const frame={timestamp:Math.round(3e6/60),close:()=>closed++};
  h.instances[1].callbacks.output(frame);
  assert.equal(h.drawn.length,1);assert.equal(closed,1);assert.equal(h.client.sources.size,0);
  assert.ok(h.sent.some(m=>m.type==='video-reset'));
  h.client.close();h.instances[1].callbacks.output(frame);
  assert.equal(h.drawn.length,1);assert.equal(closed,2);
});
test('closed decoder errors recover on the next keyframe without double closing',t=>{
  const h=harness(t);h.instances[0].state='closed';h.instances[0].callbacks.error(new Error('decode failed'));
  assert.doesNotThrow(()=>h.push(9,true));assert.equal(h.instances.length,2);
  assert.equal(h.instances[1].chunks.length,1);assert.equal(h.errors.length,1);
});
test('decoder memory stays bounded when outputs stop',t=>{
  const h=harness(t);h.push(1,true);for(let i=2;i<=10;i++)h.push(i);
  assert.equal(h.instances.length,2);assert.equal(h.client.sources.size,0);
  assert.equal(h.instances[0].state,'closed');
});

test('late output and errors from a replaced decoder cannot touch the current stream',t=>{
  const h=harness(t);h.push(1,true);const old=h.instances[0];h.client.configure('avc1.42c020');h.push(2,true);
  let closed=0;old.callbacks.output({timestamp:16667,close:()=>closed++});old.callbacks.error(new Error('stale'));
  assert.equal(closed,1);assert.equal(h.drawn.length,0);assert.equal(h.errors.length,0);
  assert.equal(h.client.waitKey,false);assert.equal(h.client.sources.size,1);
});

test('decoder feature detection selects supported software instead of failing hardware',async t=>{
  const h=harness(t);globalThis.VideoDecoder.isConfigSupported=async c=>({supported:c.hardwareAcceleration==='prefer-software'});
  await h.client.configureSupported('avc1.42c020');
  assert.equal(h.instances.at(-1).config.hardwareAcceleration,'prefer-software');
  h.instances.at(-1).state='closed';h.instances.at(-1).callbacks.error(new Error('software failed'));
  assert.equal(h.client.closed,true);assert.equal(h.errors.at(-1).fatal,true);
});
test('unsupported codecs and abandoned capability checks cannot create an endless blank session',async t=>{
  const h=harness(t);globalThis.VideoDecoder.isConfigSupported=async()=>({supported:false});
  await assert.rejects(h.client.configureSupported('avc1.42c020'),/No supported/);
  let complete;globalThis.VideoDecoder.isConfigSupported=()=>new Promise(resolve=>{complete=resolve;});
  const pending=h.client.configureSupported('avc1.42c020');h.client.close();complete({supported:true});await pending;
  assert.equal(h.instances.length,1);assert.equal(h.client.closed,true);
});

test('120 FPS stream uses 8.33 ms timestamps without changing the 60 FPS fallback',t=>{
  const h=harness(t);h.client.fps=120;h.push(1,true);h.push(2);h.push(3);
  assert.deepEqual(h.instances[0].chunks.map(c=>c.timestamp),[8333,16667,25000]);
  assert.throws(()=>new GameVideoDecoder({fps:1000}),/Invalid stream/);
});

test('120 Hz decoder accepts a brief network burst without losing prediction',t=>{
  const h=harness(t,120);h.push(1,true);
  for(let i=2;i<=12;i++){h.instances[0].decodeQueueSize=i-1;h.push(i);}
  assert.equal(h.instances.length,1);assert.equal(h.instances[0].chunks.length,12);
  h.instances[0].decodeQueueSize=13;h.push(13);
  assert.equal(h.instances.length,2);assert.equal(h.instances[0].state,'closed');assert.ok(h.client.sources.size<=16);
});


test('HD decoding uses full native dimensions and rejects unbounded sizes',()=>{
  for(const [width,height] of [[960,540],[1280,720],[1920,1080]]) {
    const client=new GameVideoDecoder({fps:120,width,height});
    assert.equal(client.config('avc1.640033').codedWidth,width);
    assert.equal(client.config('avc1.640033').codedHeight,height);
  }
  assert.throws(()=>new GameVideoDecoder({width:10000,height:10000}));
});
