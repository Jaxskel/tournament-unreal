// Observer tests only: synthetic GL state is never reported as real-game evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { tmpdir } from 'node:os';
import { realpathSync } from 'node:fs';
import { installProbe, beginWebGLSample, finishWebGLSample, parseArgs } from '../verify-runtime.mjs';

function setup(enabled=true) {
  let clock=0,ready=1,epoch=7,frame=10;
  const gl={TEXTURE_2D:3553,TEXTURE_CUBE_MAP:34067,TEXTURE_CUBE_MAP_POSITIVE_X:34069,TEXTURE_CUBE_MAP_NEGATIVE_Z:34074,
    TEXTURE_BINDING_2D:32873,TEXTURE_BINDING_CUBE_MAP:34068,RENDERBUFFER_BINDING:36007,
    FRAMEBUFFER_BINDING:36006,FRAMEBUFFER:36160,VIEWPORT:2978,
    FRAMEBUFFER_ATTACHMENT_OBJECT_TYPE:36048,FRAMEBUFFER_ATTACHMENT_OBJECT_NAME:36049,
    FRAMEBUFFER_ATTACHMENT_TEXTURE_LEVEL:36050,FRAMEBUFFER_ATTACHMENT_TEXTURE_CUBE_MAP_FACE:36051,
    NONE:0,RENDERBUFFER:36161,TEXTURE:5890,COLOR_ATTACHMENT0:36064,DEPTH_ATTACHMENT:36096,STENCIL_ATTACHMENT:36128,
    drawingBufferWidth:1920,drawingBufferHeight:1080,viewportValue:[0,0,1920,1080],bound:null,texture:{},renderbuffer:{},
    calls:0,queries:0,lost:false,
    getParameter(name) { this.queries++; if(name===this.VIEWPORT)return this.viewportValue;
      if(name===this.FRAMEBUFFER_BINDING)return this.bound;
      if(name===this.RENDERBUFFER_BINDING)return this.renderbuffer;
      return this.texture; },
    getFramebufferAttachmentParameter(target,point,name) {
      const a=this.bound?.[point];
      if(name===this.FRAMEBUFFER_ATTACHMENT_OBJECT_TYPE)return a?.type ?? 0;
      if(name===this.FRAMEBUFFER_ATTACHMENT_OBJECT_NAME)return a?.object ?? null;
      if(name===this.FRAMEBUFFER_ATTACHMENT_TEXTURE_LEVEL)return a?.level ?? 0;
      if(name===this.FRAMEBUFFER_ATTACHMENT_TEXTURE_CUBE_MAP_FACE)return a?.face ?? 0;
    },
    texImage2D(){},compressedTexImage2D(){},copyTexImage2D(){},texStorage2D(){},renderbufferStorage(){},renderbufferStorageMultisample(){},
    drawArrays(){this.calls++;return 17;},drawElements(){this.calls++;return 18;},drawArraysInstanced(){this.calls++;},
    getExtension(name){return name==='ANGLE_instanced_arrays'?angle:null;},isContextLost(){return this.lost;}};
  const angle={drawArraysInstancedANGLE(){gl.calls++;return 19;},drawElementsInstancedANGLE(){gl.calls++;}};
  class Canvas { constructor(){this.id='canvas';} getContext(){return gl;} }
  const context=vm.createContext({HTMLCanvasElement:Canvas,top:{},performance:{now:()=>clock}});
  vm.runInContext('window=globalThis',context);
  vm.runInContext(`(${installProbe})(${JSON.stringify({webglSample:enabled})})`,context);
  const canvas=new Canvas();canvas.getContext('webgl');
  const probe=context.__ut4Verify;
  probe.api={TournamentBrowserReady:()=>ready,TournamentBrowserSessionEpoch:()=>epoch,TournamentBrowserFrame:()=>frame};
  const run=(fn,arg)=>vm.runInContext(`(${fn})(${JSON.stringify(arg)})`,context);
  return {gl,angle,canvas,probe,context,advance:ms=>clock+=ms,setReady:x=>ready=x,setEpoch:x=>epoch=x,setFrame:x=>frame=x,
    begin:seconds=>run(beginWebGLSample,{seconds,expected:[1920,1080]}),finish:()=>JSON.parse(JSON.stringify(run(finishWebGLSample)))};
}
function attach(gl,width,height) {
  const texture={};gl.texture=texture;gl.texImage2D(gl.TEXTURE_2D,0,6408,width,height,0,6408,5121,null);
  const depth={};gl.renderbuffer=depth;gl.renderbufferStorage(gl.RENDERBUFFER,33189,width,height);
  gl.bound={[gl.COLOR_ATTACHMENT0]:{object:texture,type:gl.TEXTURE},[gl.DEPTH_ATTACHMENT]:{object:depth,type:gl.RENDERBUFFER}};
  gl.viewportValue=[0,0,width,height];return texture;
}

test('CLI sampling remains off by default and bounded/optional',()=>{
  const args=['--url','http://127.0.0.1:8000/','--manifest-url','http://127.0.0.1:8000/runtime.json','--out-dir',realpathSync(tmpdir())];
  assert.equal(parseArgs(args).webglSampleSeconds,0);
  assert.equal(parseArgs([...args,'--webgl-sample-seconds','1.5']).webglSampleSeconds,1.5);
  for(const value of ['-1','6','NaN','Infinity',' '])assert.throws(()=>parseArgs([...args,'--webgl-sample-seconds',value]));
});
test('disabled observer only records context and does not wrap GL',()=>{
  const {gl,probe}=setup(false);assert.equal(probe.gl,gl);assert.equal(probe.webgl,undefined);
  assert.equal(gl.drawArrays(),17);assert.equal(gl.queries,0);
});
test('captures default, full-resolution color+depth, and smaller shadow target separately',()=>{
  const s=setup(),{gl}=s;
  attach(gl,1920,1080);const full=gl.bound;
  attach(gl,512,512);const shadow=gl.bound;
  s.begin(1);gl.bound=full;gl.viewportValue=[0,0,1920,1080];gl.drawArrays();gl.drawElements();
  gl.bound=shadow;gl.viewportValue=[0,0,512,512];gl.drawArrays();
  gl.bound=null;gl.viewportValue=[0,0,1920,1080];gl.drawArrays();
  const report=s.finish();assert.equal(report.groups.length,3);
  assert.deepEqual(report.groups[0].color0.size,[1920,1080]);assert.deepEqual(report.groups[0].depth.size,[1920,1080]);
  assert.equal(report.groups[0].drawCalls,2);assert.deepEqual(report.groups[1].viewport,[0,0,512,512]);
  assert.deepEqual(report.groups[1].depth.size,[512,512]);assert.equal(report.groups[2].framebuffer,'default');
  assert.equal(report.groups[2].color0,null);assert.equal(report.worldUnchanged,true);
  assert.match(report.limitations,/upscaled/);assert.equal(report.finalNativeFrame,10);
});
test('viewport alone never supplies an unknown texture storage size',()=>{
  const s=setup(),{gl}=s;gl.bound={[gl.COLOR_ATTACHMENT0]:{object:{},type:gl.TEXTURE}};
  s.begin(1);gl.drawArrays();const group=s.finish().groups[0];
  assert.deepEqual(group.viewport,[0,0,1920,1080]);assert.equal(group.color0.size,null);
});
test('tracks reallocation and exact mip/cube face without treating subimages as storage',()=>{
  const s=setup(),{gl}=s,texture={};gl.texture=texture;
  gl.texStorage2D(gl.TEXTURE_CUBE_MAP,3,6408,256,128);
  gl.bound={[gl.COLOR_ATTACHMENT0]:{object:texture,type:gl.TEXTURE,face:gl.TEXTURE_CUBE_MAP_POSITIVE_X,level:2}};
  s.begin(1);gl.drawArrays();
  gl.copyTexImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X,2,6408,0,0,48,24,0);gl.drawArrays();
  const groups=s.finish().groups;assert.deepEqual(groups.map(g=>g.color0.size),[[64,32],[48,24]]);
});
test('tracks DOM-source/compressed allocation and multisample renderbuffers',()=>{
  const s=setup(),{gl}=s;gl.texImage2D(gl.TEXTURE_2D,0,6408,6408,5121,{width:400,height:300});
  gl.bound={[gl.COLOR_ATTACHMENT0]:{object:gl.texture,type:gl.TEXTURE}};
  s.begin(1);gl.drawArrays();gl.compressedTexImage2D(gl.TEXTURE_2D,0,123,200,150,0,new Uint8Array());gl.drawArrays();
  gl.renderbufferStorageMultisample(gl.RENDERBUFFER,4,6408,1920,1080);
  gl.bound={[gl.COLOR_ATTACHMENT0]:{object:gl.renderbuffer,type:gl.RENDERBUFFER}};gl.drawArrays();
  const groups=s.finish().groups;assert.deepEqual(groups.map(g=>g.color0.size),[[400,300],[200,150],[1920,1080]]);
  assert.equal(groups[2].color0.samples,4);
});
test('only counts draws after ready and before deadline; never creates frame callbacks',()=>{
  const s=setup(),{gl}=s;gl.drawArrays();s.setReady(0);assert.throws(()=>s.begin(1),/ready/);
  s.setReady(1);s.begin(1);gl.drawArrays();s.advance(1001);gl.drawArrays();
  const report=s.finish();assert.equal(report.observedDrawCalls,1);assert.equal(gl.calls,3);
  assert.equal(report.nativeFrame,10);assert.equal(report.finalNativeFrame,10);
});
test('ANGLE draws are observed once and all methods are restored after sampling',()=>{
  const s=setup(),{gl,angle}=s;const nativeAngle=angle.drawArraysInstancedANGLE;
  const extension=gl.getExtension('ANGLE_instanced_arrays');assert.equal(gl.getExtension('ANGLE_instanced_arrays'),extension);
  s.begin(1);assert.equal(extension.drawArraysInstancedANGLE(),19);assert.equal(gl.drawArrays(),17);
  const report=s.finish();assert.equal(report.observedDrawCalls,2);assert.equal(angle.drawArraysInstancedANGLE,nativeAngle);
  const queries=gl.queries;gl.drawArrays();assert.equal(gl.queries,queries);assert.equal(gl.calls,3);
});
test('caps groups and draw inspection while forwarding every draw',()=>{
  const s=setup(),{gl}=s;s.begin(1);
  for(let i=0;i<140;i++){gl.viewportValue=[0,0,i+1,10];gl.drawArrays();}
  for(let i=140;i<10003;i++)gl.drawArrays();
  const report=s.finish();assert.equal(report.groups.length,128);assert.equal(report.observedDrawCalls,10000);
  assert.equal(report.drawCapReached,true);assert.equal(report.omittedDrawCalls,9872);assert.equal(gl.calls,10003);
});
test('context loss and changed world are explicit, not resolution success',()=>{
  const s=setup();s.begin(1);s.gl.lost=true;s.gl.drawArrays();s.setEpoch(8);
  const report=s.finish();assert.equal(report.status,'context-lost');assert.equal(report.worldUnchanged,false);
  assert.equal(report.observedDrawCalls,0);
});
test('observation failure cannot swallow a real draw return or exception',()=>{
  const s=setup(),{gl}=s;s.begin(1);gl.getParameter=()=>{throw Error('query failed');};
  assert.equal(gl.drawArrays(),17);assert.deepEqual(s.finish().issues,['query failed']);
});

test('real browser WebGL1/2 attachment evidence preserves bindings and GL error state',async()=>{
  const {chromium}=await import('playwright');
  const browser=await chromium.launch({headless:true,...(process.env.CHROME_CHANNEL?{channel:process.env.CHROME_CHANNEL}:{})});
  try {
    const page=await browser.newPage();await page.setContent('<iframe src="about:blank"></iframe>');
    const frame=page.frames().find(f=>f!==page.mainFrame());
    for(const version of ['webgl','webgl2']) {
      await frame.goto('about:blank');await frame.evaluate(installProbe,{webglSample:true});
      const result=await frame.evaluate(({version,begin,finish})=>{
        const canvas=document.createElement('canvas');canvas.id='canvas';canvas.width=320;canvas.height=240;document.body.append(canvas);
        const gl=canvas.getContext(version);if(!gl)throw Error(version+' context unavailable');
        const p=window.__ut4Verify;p.api={TournamentBrowserReady:()=>1,TournamentBrowserSessionEpoch:()=>1,TournamentBrowserFrame:()=>5};
        const originalDraw=Object.getPrototypeOf(gl).drawArrays;
        function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
        const program=gl.createProgram(),v2=version==='webgl2';
        gl.attachShader(program,shader(gl.VERTEX_SHADER,v2?'#version 300 es\nvoid main(){gl_Position=vec4(0,0,0,1);gl_PointSize=1.0;}':'void main(){gl_Position=vec4(0,0,0,1);gl_PointSize=1.0;}'));
        gl.attachShader(program,shader(gl.FRAGMENT_SHADER,v2?'#version 300 es\nprecision mediump float;out vec4 color;void main(){color=vec4(1);}':'precision mediump float;void main(){gl_FragColor=vec4(1);}'));
        gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
        const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,160,120,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
        gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
        const depth=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,depth);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,160,120);
        const fbo=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,fbo);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,texture,0);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,depth);
        if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('Incomplete fixture framebuffer');
        (0,eval)('('+begin+')')({seconds:1,expected:[320,240]});
        gl.viewport(0,0,160,120);gl.drawArrays(gl.POINTS,0,1);
        const statePreserved=gl.getParameter(gl.FRAMEBUFFER_BINDING)===fbo&&gl.getParameter(gl.TEXTURE_BINDING_2D)===texture&&gl.getParameter(gl.RENDERBUFFER_BINDING)===depth;
        gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,320,240);gl.drawArrays(gl.POINTS,0,1);
        const report=(0,eval)('('+finish+')')();return {report,statePreserved,error:gl.getError(),restored:gl.drawArrays===originalDraw};
      },{version,begin:beginWebGLSample.toString(),finish:finishWebGLSample.toString()});
      assert.equal(result.error,0,version);assert.equal(result.statePreserved,true);assert.equal(result.restored,true);
      assert.equal(result.report.observedDrawCalls,2);assert.deepEqual(result.report.issues,[]);
      assert.deepEqual(result.report.groups[0].color0.size,[160,120]);assert.deepEqual(result.report.groups[0].depth.size,[160,120]);
      assert.deepEqual(result.report.groups[0].viewport,[0,0,160,120]);assert.equal(result.report.groups[1].framebuffer,'default');
      assert.deepEqual(result.report.groups[1].drawingBuffer,[320,240]);
    }
  } finally {await browser.close();}
});
