// H.264 Annex B is decoded by the browser's media decoder, not a JPEG/image loop.
export class GameVideoDecoder {
  constructor({draw, send, failure, fps = 60, width = 960, height = 540}) {
    if (![60,120].includes(fps)) throw new Error('Invalid stream frame rate');
    if (![[960,540],[1280,720],[1920,1080],[2560,1440]].some(([w,h])=>width===w&&height===h)) throw new Error('Invalid video size');
    this.width = width; this.height = height;
    this.fps = fps;
    this.maxDecodeQueue = fps === 120 ? 12 : 2;
    this.maxSources = fps === 120 ? 16 : 8;
    this.draw = draw; this.send = send; this.failure = failure;
    this.decoder = null; this.waitKey = true; this.seq = 0; this.codec = null;
    this.sources = new Map(); this.frameAge = null; this.serverOffset = null;
    this.configVersion = 0; this.acceleration = 'prefer-hardware'; this.generation = 0; this.bytes = 0; this.dropped = 0; this.closed = false;
  }
  async configureSupported(codec) {
    const version = ++this.configVersion;
    for (const acceleration of ['prefer-hardware', 'prefer-software']) {
      const {supported} = await VideoDecoder.isConfigSupported(this.config(codec, acceleration));
      if (this.closed || version !== this.configVersion) return;
      if (supported) { this.acceleration = acceleration; this.configure(codec); return; }
    }
    throw new Error('No supported H.264 decoder');
  }
  config(codec, acceleration = this.acceleration) {
    return {codec,codedWidth:this.width,codedHeight:this.height,optimizeForLatency:true,hardwareAcceleration:acceleration};
  }
  configure(codec) {
    const generation = ++this.generation;
    this.codec = codec;
    if (this.decoder && this.decoder.state !== 'closed') this.decoder.close(); this.sources.clear(); this.waitKey = true;
    this.decoder = new VideoDecoder({
      output: frame => {
        try {
          const source = this.sources.get(frame.timestamp);
          this.sources.delete(frame.timestamp);
          if (this.closed || generation !== this.generation) return;
          if (source !== undefined && this.serverOffset !== null) this.frameAge = Math.max(0,Date.now() + this.serverOffset - source);
          this.draw(frame);
        } finally { frame.close(); }
      },
      error: error => {
        if (this.closed || generation !== this.generation) return;
        this.waitKey = true; this.sources.clear();
        this.send({type:'video-reset'});
        // Some Windows/headless drivers advertise a decoder that fails at use.
        // Try software once; never loop forever on an unsupported configuration.
        if (this.acceleration === 'prefer-hardware') {
          this.acceleration = 'prefer-software';
          try { this.configure(this.codec); this.failure(error, false); }
          catch (fallbackError) { this.close(); this.failure(fallbackError, true); }
        } else { this.close(); this.failure(error, true); }
      },
    });
    this.decoder.configure(this.config(codec));
  }
  push(buffer) {
    const data = new Uint8Array(buffer);
    if (data.length < 20 || data.length > 4 * 1024 * 1024 || data[0] !== 0x48 || data[1] !== 1 || data[2] > 1) throw new Error('Invalid video packet');
    const header = new DataView(buffer);
    const seq = header.getUint32(4);
    const sourceAt = header.getFloat64(8);
    if (!Number.isFinite(sourceAt)) throw new Error('Invalid capture time');
    this.bytes += data.length;
    // Receipt acknowledgements bound the network queue. Decoder pressure has a
    // separate bounded queue; 120 Hz allows a short packet burst to decode
    // without treating normal network batching as a broken codec.
    this.send({type:'video-ack',seq});
    const key = !!data[2];
    if (seq !== this.seq + 1) this.waitKey = true;
    this.seq = seq;
    if (!this.decoder || this.closed) return;
    if (this.decoder.state === 'closed' || this.decoder.decodeQueueSize > this.maxDecodeQueue) {
      this.configure(this.codec); this.send({type:'video-reset'}); this.dropped++;
    }
    if (this.waitKey && !key) { this.dropped++; return; }
    this.waitKey = false;
    const timestamp = Math.round(seq * 1000000 / this.fps);
    this.sources.set(timestamp, sourceAt);
    try { this.decoder.decode(new EncodedVideoChunk({type:key?'key':'delta',timestamp,data:data.subarray(16)})); }
    catch (error) { this.waitKey=true; this.sources.clear(); this.send({type:'video-reset'}); this.failure(error); }
    // Bounded even if a decoder accepts pictures without producing outputs.
    if (this.sources.size > this.maxSources) {
      if (this.acceleration === 'prefer-hardware') {
        this.acceleration = 'prefer-software'; this.configure(this.codec); this.send({type:'video-reset'});
      } else { this.close(); this.failure(new Error('Video decoder stopped producing pictures'), true); }
    }
  }
  close() { this.closed = true; if (this.decoder && this.decoder.state !== 'closed') this.decoder.close(); this.sources.clear(); }
}


// One retained decoded frame, presented on the browser's refresh callback.
// Bursty delivery replaces old pictures instead of drawing a catch-up burst.
export class LatestFramePresenter {
  constructor({draw, now = () => performance.now()}) {
    this.draw=draw;this.now=now;this.pending=null;this.replaced=0;
    this.gaps=[];this.lastPresentedAt=null;this.stalls=0;this.age=null;
  }
  submit(frame, age=null) {
    const copy=frame.clone();
    if(this.pending){this.pending.frame.close();this.replaced++;}
    this.pending={frame:copy,at:this.now(),age};
  }
  present() {
    const pending=this.pending;if(!pending)return false;
    this.pending=null;
    try {
      const now=this.now();
      this.age=pending.age===null?null:pending.age+Math.max(0,now-pending.at);
      this.draw(pending.frame);
      if(this.lastPresentedAt!==null){
        const gap=now-this.lastPresentedAt;this.gaps.push(gap);
        if(this.gaps.length>240)this.gaps.shift();
        if(gap>50)this.stalls++;
      }
      this.lastPresentedAt=now;
      return true;
    }finally{pending.frame.close();}
  }
  get p95(){const sorted=[...this.gaps].sort((a,b)=>a-b);return sorted.length?sorted[Math.floor((sorted.length-1)*.95)]:null;}
  clear(){if(this.pending)this.pending.frame.close();this.pending=null;this.age=null;this.gaps=[];this.lastPresentedAt=null;this.stalls=0;this.replaced=0;}
}
