#!/usr/bin/env node
// Real-runtime verification only. No fixture/server/assets and no synthetic frames.
import { realpathSync, statSync } from 'node:fs';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { isAbsolute, relative, sep, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { validateManifest, argumentsForMode } from './core.mjs';
import { REQUIRED_BINDINGS } from './bindings.mjs';

const repo = realpathSync(fileURLToPath(new URL('../../../', import.meta.url)));
const help = `Real UT4 launcher verification (never part of npm test)
Required:
  --url URL             Existing private launcher index.html/operator URL
  --manifest-url URL    Its existing same-origin runtime.json (no overrides)
  --out-dir ABS_PATH    Existing directory outside the repository; creates unique run directory
Optional:
  --resolution both|1080p|1440p   Default both, each in a fresh browser
  --mode practice|multiplayer    Default practice; uses operator arguments
  --seconds N                   Measured interval, 5..600 (default 30)
  --warmup-seconds N             0..120 (default 5)
  --ready-timeout-seconds N      World readiness deadline, 10..1800 (default 300)
  --stall-seconds N              Native tick inactivity limit, 2..120 (default 15)
  --webgl-sample-seconds N       Optional draw/target evidence before timing, 0..5 (default 0/off)
  --channel chrome|chromium      Default chrome; chromium uses Playwright's installed browser
  --headed                      Default headless; results record this choice
  --validate-only               Validate CLI/paths only: no browser, network or artifacts
  --self-test-args               Run argument validation checks only
  --self-test-diagnostics        Test exact legacy notices and error/fatal near-misses
No FPS target, gameplay/handshake guarantee, manifest rewriting or packaged assets.`;

function inside(path, root) {
  const rel = relative(root, path);
  return rel === '' || (!rel.startsWith('..' + sep) && rel !== '..' && !isAbsolute(rel));
}
export function parseArgs(argv) {
  const flags = new Set(['headed', 'validate-only']);
  const names = new Set(['url','manifest-url','out-dir','resolution','mode','seconds','warmup-seconds','ready-timeout-seconds','stall-seconds','webgl-sample-seconds','channel',...flags]);
  const values = {};
  for (let i=0; i<argv.length; i++) {
    const key=argv[i].startsWith('--') ? argv[i].slice(2) : '';
    if (!names.has(key) || Object.hasOwn(values,key)) throw Error('Unknown or repeated option: '+argv[i]);
    if (flags.has(key)) values[key]=true;
    else {
      const value=argv[++i];
      if (!value || value.startsWith('--')) throw Error('Missing value for --'+key);
      values[key]=value;
    }
  }
  for (const key of ['url','manifest-url','out-dir']) if (!values[key]) throw Error('--'+key+' is required.');
  const httpURL = value => {
    const url=new URL(value);
    if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw Error('URLs must be HTTP(S), without credentials, query or fragment.');
    if (/\/tests\/|fixture/i.test(url.pathname)) throw Error('Fixture/test URLs are not real-runtime inputs.');
    return url.href;
  };
  const url=httpURL(values.url), manifestURL=httpURL(values['manifest-url']);
  if (manifestURL !== new URL('./runtime.json',url).href) throw Error('--manifest-url must equal the launcher\'s existing ./runtime.json URL.');
  if (!isAbsolute(values['out-dir'])) throw Error('--out-dir must be absolute.');
  const outDir=realpathSync(values['out-dir']); // Resolve symlinks before checking repository containment.
  if (!statSync(outDir).isDirectory() || inside(outDir,repo)) throw Error('--out-dir must be an existing directory outside the repository.');
  const choice=(key,fallback,allowed)=>{
    const value=values[key] ?? fallback;
    if (!allowed.includes(value)) throw Error('--'+key+' must be '+allowed.join('|'));
    return value;
  };
  const number=(key,fallback,min,max)=>{
    const value=values[key] === undefined ? fallback : Number(values[key]);
    if (!Number.isFinite(value) || String(values[key] ?? fallback).trim()==='' || value<min || value>max) throw Error('--'+key+' must be '+min+'..'+max);
    return value;
  };
  return { url,manifestURL,outDir,resolution:choice('resolution','both',['both','1080p','1440p']),
    mode:choice('mode','practice',['practice','multiplayer']),channel:choice('channel','chrome',['chrome','chromium']),
    seconds:number('seconds',30,5,600),warmupSeconds:number('warmup-seconds',5,0,120),
    readyTimeoutSeconds:number('ready-timeout-seconds',300,10,1800),stallSeconds:number('stall-seconds',15,2,120),
    webglSampleSeconds:number('webgl-sample-seconds',0,0,5),
    headed:!!values.headed,validateOnly:!!values['validate-only'] };
}

function bounded(promise, ms, label) {
  let timer;
  return Promise.race([promise,new Promise((_,reject)=>{ timer=setTimeout(()=>reject(Error(label)),ms); })]).finally(()=>clearTimeout(timer));
}
export function remainingStartupMs(deadline, now=Date.now()) {
  const remaining=deadline-now;
  if (!Number.isFinite(remaining) || remaining<=0) throw Error('World readiness timeout; global startup deadline exhausted.');
  return remaining;
}

export async function startupOperation(operation,label,deadline,failed,now=Date.now) {
  const remaining=remainingStartupMs(deadline,now());
  // A synchronous engine load can block both iframe and parent for >15 seconds.
  // Spend only the remaining shared startup budget, including Playwright waits.
  // Put the fatal race inside bounded so a fatal also cancels its timeout timer.
  const value=await bounded(Promise.race([operation(remaining),failed]),remaining,
    label+' timed out at the global startup deadline');
  remainingStartupMs(deadline,now());
  return value;
}

const browserServerClosures=new WeakMap();
export function trackBrowserServer(server) {
  if (!browserServerClosures.has(server)) {
    const state={closed:false};
    browserServerClosures.set(server,state);
    // Playwright emits this after ChildProcess 'close' and starts shutting down
    // its WebSocket server, before awaiting temporary-profile directory removal.
    server.once('close',()=>{state.closed=true;});
  }
  return server;
}

export async function cleanupVerification(server,result,primaryError,{closeMs=10000,killMs=5000,browser}={}) {
  if (!server) return;
  trackBrowserServer(server);
  const owned=server.process();
  const closed=()=>browserServerClosures.get(server).closed && owned
    && (typeof owned.exitCode==='number' || typeof owned.signalCode==='string');
  const completedShutdown=async error=>{
    if (!closed() || !/^Browser (close|kill) timed out$/.test(String(error?.message))) return false;
    // A connected Browser.close() disconnects this client, not an unrelated
    // browser. The BrowserServer already owns process/WebSocket shutdown.
    if (browser) await bounded(browser.close(),killMs,'Browser client disconnect timed out');
    result.cleanupWarning='Owned browser closed; Playwright temporary-directory cleanup remains pending: '+error.message;
    return true;
  };
  try { await bounded(Promise.resolve().then(()=>server.close()),closeMs,'Browser close timed out'); }
  catch (closeError) {
    try { if (await completedShutdown(closeError)) return; } catch (disconnectError) { closeError=disconnectError; }
    try { await bounded(Promise.resolve().then(()=>server.kill()),killMs,'Browser kill timed out'); }
    catch (killError) {
      try { if (await completedShutdown(killError)) return; } catch (disconnectError) { killError=disconnectError; }
      let message='Browser cleanup failed: '+String(closeError?.message ?? closeError)+'; '+String(killError?.message ?? killError);
      try {
        // This ChildProcess belongs to our launchServer call. Never look up or
        // kill a browser by executable name, remote endpoint, or a reused PID.
        if (owned && owned.exitCode===null && owned.signalCode===null) {
          message+=owned.kill('SIGKILL') ? '; SIGKILL requested for owned browser' : '; owned browser SIGKILL was not sent';
        }
      } catch (forceError) { message+='; force kill: '+String(forceError?.message ?? forceError); }
      result.cleanupError=message;
      result.status='failed';
      // Throwing from finally would otherwise replace the actual engine error.
      if (!primaryError) { result.error=message; throw Error(message); }
    }
  }
}
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
const fatalPattern = /DebugBreak|\bfatal(?: error)?\b|Assertion failed|Ensure condition failed|\bcheckf? failed|\babort(?:ed|ing|\()|\bRuntimeError\b|memory access out of bounds|out of memory|\bLog\w*:\s*Error:/i;
export function isFailureDiagnostic(type, text) {
  // Verified in the actual matching legacy adapter: run() prints dependency wait
  // and integer Date.now() elapsed time; _sigaction prints its notice and returns 0.
  // Keep every notice in the report. Do not exempt other stubs or generic stderr.
  // Negative lookahead enforces the true end (JS $ also accepts a final newline).
  const expectedNotice = text === '[UT4] run() called, but dependencies remain, so not running'
    || text === '[UT4] Calling stub instead of sigaction()'
    || /^\[UT4\] pre-main prep time: (?:0|[1-9][0-9]*) ms(?![\s\S])/.test(text);
  return fatalPattern.test(text) || (type === 'error' && !expectedNotice);
}

// Installed before page code; observes the real canvas context without creating one.
export function installProbe({ webglSample=false }={}) {
  if (window === top) return;
  const original=HTMLCanvasElement.prototype.getContext;
  window.__ut4Verify={ gl:null, samples:[], issues:[], measuring:false, completedCallbacks:0 };
  HTMLCanvasElement.prototype.getContext=function(...args) {
    const context=Reflect.apply(original,this,args);
    if (this.id==='canvas' && ['webgl','webgl2','experimental-webgl'].includes(args[0]) && context) {
      const probe=window.__ut4Verify;
      probe.gl=context;
      if (webglSample && !probe.webgl) probe.webgl=observe(context);
    }
    return context;
  };

  function observe(gl) {
    // WebGL 1 cannot query a texture's dimensions. Observe allocation calls from
    // context creation; retain metadata weakly, never retain image/texture data.
    const textures=new WeakMap(), renderbuffers=new WeakMap(), ids=new WeakMap();
    const restores=[], errors=[];
    let nextId=1, active=false, start=0, deadline=0, draws=0, omitted=0, capped=false;
    const groups=new Map();
    const limit=10000, groupLimit=128;
    const issue=error=>{ if (errors.length<8) errors.push(String(error.message ?? error)); };
    const id=object=>{ if (!ids.has(object)) ids.set(object,nextId++); return ids.get(object); };
    const wrap=(object,name,after)=>{
      if (typeof object[name]!=='function') return;
      const own=Object.getOwnPropertyDescriptor(object,name), original=object[name];
      const wrapped=function(...args) {
        const result=Reflect.apply(original,this,args);
        try { after(args); } catch (error) { issue(error); }
        return result;
      };
      try {
        Object.defineProperty(object,name,{configurable:true,writable:true,value:wrapped});
        restores.push(()=>{ if (object[name]===wrapped) { if (own) Object.defineProperty(object,name,own); else delete object[name]; } });
      } catch (error) { issue(error); }
    };
    const texture=(target,level,width,height)=>{
      const cube=target>=gl.TEXTURE_CUBE_MAP_POSITIVE_X && target<=gl.TEXTURE_CUBE_MAP_NEGATIVE_Z;
      const binding=target===gl.TEXTURE_2D?gl.TEXTURE_BINDING_2D:cube?gl.TEXTURE_BINDING_CUBE_MAP:null;
      if (binding===null || !Number.isInteger(level) || level<0 || level>31) return;
      const object=gl.getParameter(binding);
      if (!object) return;
      let levels=textures.get(object); if (!levels) textures.set(object,levels=new Map());
      levels.set(target+':'+level,Number.isInteger(width) && width>=0 && Number.isInteger(height) && height>=0?[width,height]:null);
    };
    wrap(gl,'texImage2D',args=>{
      const source=args[5];
      texture(args[0],args[1],args.length>=9?args[3]:source?.videoWidth ?? source?.naturalWidth ?? source?.width,
        args.length>=9?args[4]:source?.videoHeight ?? source?.naturalHeight ?? source?.height);
    });
    wrap(gl,'compressedTexImage2D',a=>texture(a[0],a[1],a[3],a[4]));
    wrap(gl,'copyTexImage2D',a=>texture(a[0],a[1],a[5],a[6]));
    wrap(gl,'texStorage2D',a=>{
      for (let level=0;level<Math.min(a[1],32);level++) {
        const faces=a[0]===gl.TEXTURE_CUBE_MAP?Array.from({length:6},(_,i)=>gl.TEXTURE_CUBE_MAP_POSITIVE_X+i):[a[0]];
        for (const face of faces) texture(face,level,Math.max(1,Math.floor(a[3]/2**level)),Math.max(1,Math.floor(a[4]/2**level)));
      }
    });
    wrap(gl,'renderbufferStorage',a=>{
      const object=gl.getParameter(gl.RENDERBUFFER_BINDING);
      if (object) renderbuffers.set(object,{size:[a[2],a[3]],samples:0});
    });
    wrap(gl,'renderbufferStorageMultisample',a=>{
      const object=gl.getParameter(gl.RENDERBUFFER_BINDING);
      if (object) renderbuffers.set(object,{size:[a[3],a[4]],samples:a[1]});
    });
    const attachment=(target,point)=>{
      const type=gl.getFramebufferAttachmentParameter(target,point,gl.FRAMEBUFFER_ATTACHMENT_OBJECT_TYPE);
      if (type===gl.NONE) return null;
      const object=gl.getFramebufferAttachmentParameter(target,point,gl.FRAMEBUFFER_ATTACHMENT_OBJECT_NAME);
      if (!object) return {kind:'unknown',size:null};
      if (type===gl.RENDERBUFFER) return {kind:'renderbuffer',id:id(object),size:null,...renderbuffers.get(object)};
      if (type!==gl.TEXTURE) return {kind:'unknown',size:null};
      const level=gl.getFramebufferAttachmentParameter(target,point,gl.FRAMEBUFFER_ATTACHMENT_TEXTURE_LEVEL);
      const face=gl.getFramebufferAttachmentParameter(target,point,gl.FRAMEBUFFER_ATTACHMENT_TEXTURE_CUBE_MAP_FACE) || gl.TEXTURE_2D;
      return {kind:'texture',id:id(object),level,face,size:textures.get(object)?.get(face+':'+level) ?? null};
    };
    const record=()=>{
      if (!active || performance.now()>deadline) return;
      if (draws>=limit) { capped=true; return; }
      if (gl.isContextLost()) return;
      draws++;
      const framebuffer=gl.getParameter(gl.DRAW_FRAMEBUFFER_BINDING ?? gl.FRAMEBUFFER_BINDING);
      const target=gl.DRAW_FRAMEBUFFER ?? gl.FRAMEBUFFER;
      const entry={framebuffer:framebuffer?'offscreen':'default',framebufferId:framebuffer?id(framebuffer):0,
        viewport:Array.from(gl.getParameter(gl.VIEWPORT)),drawingBuffer:[gl.drawingBufferWidth,gl.drawingBufferHeight],
        color0:framebuffer?attachment(target,gl.COLOR_ATTACHMENT0):null,
        depth:framebuffer?attachment(target,gl.DEPTH_ATTACHMENT):null,
        stencil:framebuffer?attachment(target,gl.STENCIL_ATTACHMENT):null};
      const key=JSON.stringify(entry), existing=groups.get(key);
      if (existing) existing.drawCalls++;
      else if (groups.size<groupLimit) groups.set(key,{...entry,drawCalls:1});
      else omitted++;
    };
    for (const name of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced','drawRangeElements']) wrap(gl,name,record);
    // UE4's WebGL 1 instanced draws can use the extension rather than core methods.
    const extensions=new WeakSet();
    const originalExtension=gl.getExtension, ownExtension=Object.getOwnPropertyDescriptor(gl,'getExtension');
    const getExtension=function(...args) {
      const result=Reflect.apply(originalExtension,this,args);
      if (result && args[0]==='ANGLE_instanced_arrays' && !extensions.has(result)) {
        extensions.add(result);
        for (const name of ['drawArraysInstancedANGLE','drawElementsInstancedANGLE']) wrap(result,name,record);
      }
      return result;
    };
    try {
      Object.defineProperty(gl,'getExtension',{configurable:true,writable:true,value:getExtension});
      restores.push(()=>{ if (gl.getExtension===getExtension) { if (ownExtension) Object.defineProperty(gl,'getExtension',ownExtension); else delete gl.getExtension; } });
    } catch (error) { issue(error); }
    return {
      begin(seconds) { start=performance.now(); deadline=start+seconds*1000; active=true; },
      finish() {
        active=false;
        for (const restore of restores.reverse()) restore();
        return {status:gl.isContextLost()?'context-lost':draws?'observed':'no-draws',
          requestedSeconds:(deadline-start)/1000,observedDrawCalls:draws,drawCap:limit,drawCapReached:capped,
          omittedDrawCalls:omitted,groupLimit,groups:Array.from(groups.values()),issues:errors};
      }
    };
  }
}

export function beginWebGLSample({seconds,expected}) {
  const p=window.__ut4Verify;
  if (!p?.webgl || p.api.TournamentBrowserReady()!==1) throw Error('WebGL sample requires the actual ready game context.');
  p.webglStart={epoch:p.api.TournamentBrowserSessionEpoch(),nativeFrame:p.api.TournamentBrowserFrame(),expected};
  p.webgl.begin(seconds);
}
export function finishWebGLSample() {
  const p=window.__ut4Verify, report=p.webgl.finish();
  return {...report,...p.webglStart,finalNativeFrame:p.api.TournamentBrowserFrame(),
    worldUnchanged:p.api.TournamentBrowserReady()===1 && p.api.TournamentBrowserSessionEpoch()===p.webglStart.epoch,
    source:'Actual WebGL draw calls after game readiness; viewport and bound framebuffer attachment metadata',
    limitations:'Viewport is the configured rasterization extent, not proof of scene resolution. Color0/depth/stencil only; allocation dimensions are observed requests, not queried texture storage. Smaller shadow/postprocess targets are expected. A full-size default framebuffer can contain an upscaled scene. Unknown attachments remain null. No scene-pass identification, GPU timing, presented FPS or gameplay proof. Sampling is separate from tick timing.'};
}

// Executes only in the real runtime iframe. No global UE_JSlib dependency.
function snapshot(required) {
  const m=window.Module, probe=window.__ut4Verify;
  if (window.fixture) throw Error('Fixture runtime detected; real-runtime verification refused.');
  if (!m) return { ready:false,missing:required };
  if (m.noInitialRun) throw Error('noInitialRun is set: allocator/runtime smoke is not world readiness.');
  const missing=required.filter(name=>typeof m['_'+name]!=='function');
  if (typeof m.cwrap!=='function') missing.push('Module.cwrap');
  if (missing.length) return { ready:false,missing };
  probe.api ??= Object.fromEntries(required.map(name=>[name,m.cwrap(name,'number',
    name==='TournamentBrowserSetResolution'?['number','number']:['TournamentBrowserSetSensitivity','TournamentBrowserSetVolume'].includes(name)?['number']:[])]));
  const api=probe.api;
  const ready=api.TournamentBrowserReady()===1;
  if (!ready) return { ready:false,missing:[] };
  const gl=probe.gl;
  if (gl && !probe.graphics) {
    const debug=gl.getExtension('WEBGL_debug_renderer_info');
    probe.graphics={ version:gl.getParameter(gl.VERSION),renderer:gl.getParameter(gl.RENDERER),
      unmaskedRenderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):null,
      unmaskedVendor:debug?gl.getParameter(debug.UNMASKED_VENDOR_WEBGL):null };
  }
  return { ready,epoch:api.TournamentBrowserSessionEpoch(),nativeFrame:api.TournamentBrowserFrame(),
    native:[api.TournamentBrowserWidth(),api.TournamentBrowserHeight()],canvas:[m.canvas?.width,m.canvas?.height],
    drawingBuffer:gl?[gl.drawingBufferWidth,gl.drawingBufferHeight]:null,
    contextLost:gl?.isContextLost(),contextAttributes:gl?.getContextAttributes(),graphics:probe.graphics,
    hooks:{ pre:typeof m.preMainLoop,post:typeof m.postMainLoop },issues:probe.issues.slice() };
}

function beginMeasurement(seconds) {
  const m=window.Module,p=window.__ut4Verify,api=p.api;
  if (typeof m.preMainLoop!=='function' || typeof m.postMainLoop!=='function') throw Error('Missing real Emscripten main-loop hooks.');
  if (p.installed) throw Error('Measurement already installed.');
  p.installed=true; p.start=performance.now(); p.deadline=p.start+seconds*1000;
  p.initialFrame=api.TournamentBrowserFrame(); p.lastFrame=p.initialFrame; p.lastTick=null;
  p.lastAdvance=p.start; p.measuring=true; p.epoch=api.TournamentBrowserSessionEpoch();
  const original=m.postMainLoop;
  m.postMainLoop=function(...args) {
    const result=Reflect.apply(original,this,args);
    if (!p.measuring) return result;
    const now=performance.now();
    if (now>p.deadline) return result; // Node polls do not define or add engine samples.
    p.completedCallbacks++;
    const frame=api.TournamentBrowserFrame(),epoch=api.TournamentBrowserSessionEpoch();
    if (!Number.isSafeInteger(frame) || frame<p.lastFrame) { p.issues.push('Native frame counter invalid/regressed.'); p.measuring=false; return result; }
    if (epoch!==p.epoch || api.TournamentBrowserReady()!==1) { p.issues.push('World/controller changed during measured interval.'); p.measuring=false; return result; }
    if (frame!==p.lastFrame) {
      if (frame-p.lastFrame!==1) { p.issues.push('Multiple native ticks between callbacks: per-tick p95 cannot be resolved.'); p.measuring=false; return result; }
      if (p.lastTick!==null) p.samples.push(now-p.lastTick);
      p.lastTick=now; p.lastAdvance=now; p.lastFrame=frame;
      if (p.samples.length>1000000) { p.issues.push('Tick sample cap exceeded.'); p.measuring=false; }
    }
    return result;
  };
  p.wrappedPost=m.postMainLoop;
}

function readMeasurement() {
  const p=window.__ut4Verify;
  if (Module.postMainLoop!==p.wrappedPost) throw Error('Engine replaced the measurement hook.');
  return { now:performance.now(),start:p.start,deadline:p.deadline,lastAdvance:p.lastAdvance,
    completedCallbacks:p.completedCallbacks,ticks:p.lastFrame-p.initialFrame,issues:p.issues.slice() };
}
function finishMeasurement() {
  const p=window.__ut4Verify;
  p.measuring=false;
  const sorted=p.samples.slice().sort((a,b)=>a-b), seconds=(p.deadline-p.start)/1000;
  return { state:'measured',source:'Native GFrameCounter advances observed in real Module.postMainLoop callbacks',
    seconds,initialNativeFrame:p.initialFrame,lastNativeFrame:p.lastFrame,nativeTicks:p.lastFrame-p.initialFrame,
    completedCallbacks:p.completedCallbacks,engineTickFPS:(p.lastFrame-p.initialFrame)/seconds,
    p95TickIntervalMs:sorted.length?sorted[Math.ceil(sorted.length*.95)-1]:null,
    tickIntervalsMs:p.samples,issues:p.issues.slice(),
    limitations:'Observed engine ticks, not GPU/presented FPS, server tick rate, handshake or gameplay validation.' };
}

async function verifyResolution(config,resolution,directory,report) {
  const { chromium }=await import('playwright');
  const result={ resolution,status:'running',metrics:{state:'uninitialized'},events:[],droppedEvents:0 };
  report.runs.push(result);
  let server,browser,page,cleaning=false,fatal,primaryError;
  let rejectFatal;
  const failed=new Promise((_,reject)=>{ rejectFatal=reject; }); failed.catch(()=>{});
  const record=(kind,text)=>{
    if (result.events.length<5000) result.events.push({ at:new Date().toISOString(),kind,text:String(text).slice(0,8000) });
    else result.droppedEvents++;
  };
  const fail=text=>{ if (!cleaning && !fatal) { fatal=Error(text); record('failure',text); rejectFatal(fatal); } };
  const op=(promise,label,ms=15000)=>Promise.race([bounded(promise,ms,label+' timed out'),failed]);
  const [width,height]=resolution==='1440p'?[2560,1440]:[1920,1080];
  const assertState=state=>{
    if (!state.ready) throw Error('World readiness lost.');
    if (!Number.isSafeInteger(state.epoch) || state.epoch<=0) throw Error('Invalid session epoch.');
    if (!Number.isSafeInteger(state.nativeFrame) || state.nativeFrame<0) throw Error('Invalid native frame counter.');
    for (const key of ['native','canvas','drawingBuffer']) if (state[key]?.[0]!==width || state[key]?.[1]!==height) throw Error(key+' differs from fixed '+width+'x'+height+': '+JSON.stringify(state[key]));
    if (state.contextLost || state.issues?.length) throw Error('Context or instrumentation failure: '+JSON.stringify(state));
  };
  const screenshot=async name=>{
    const path=join(directory,resolution+'-'+name+'.png');
    await bounded(page.screenshot({ path,timeout:5000 }),6000,'Screenshot timed out');
    (result.screenshots ??=[]).push(path);
  };
  try {
    server=trackBrowserServer(await chromium.launchServer({ headless:!config.headed,...(config.channel==='chrome'?{channel:'chrome'}:{}),timeout:30000 }));
    browser=await chromium.connect(server.wsEndpoint(),{timeout:15000});
    browser.on('disconnected',()=>fail('Browser disconnected before verification finished.'));
    const context=await op(browser.newContext({ viewport:{width:1440,height:1000},deviceScaleFactor:1 }),'Browser context');
    await op(context.addInitScript(installProbe,{webglSample:config.webglSampleSeconds>0}),'Canvas observer installation');
    page=await op(context.newPage(),'Browser page');
    page.on('crash',()=>fail('Browser page crashed.'));
    page.on('pageerror',error=>fail('Page/engine error: '+error.message));
    page.on('console',message=>{
      const text=message.text(); record('console:'+message.type(),text);
      if (isFailureDiagnostic(message.type(),text)) fail('Engine/browser diagnostic: '+text);
    });
    page.on('response',response=>{
      if (response.status()>=400) fail('HTTP '+response.status()+': '+response.url());
      if (response.url()===config.manifestURL) {
        response.body().then(bytes=>{
          const hash=createHash('sha256').update(bytes).digest('hex');
          if (hash!==report.manifestSha256) fail('Operator manifest changed during verification; rerun against one stable manifest.');
          result.manifestSha256=hash;
        }).catch(error=>fail('Could not verify actual launcher manifest: '+error.message));
      }
    });
    page.on('requestfailed',request=>fail('Request failed: '+request.url()+' '+request.failure()?.errorText));
    await op(page.exposeFunction('__ut4Report',(type,detail)=>{
      record('runtime:'+type,JSON.stringify(detail));
      if (type==='error') fail('Runtime error: '+detail);
      if (type==='status' && fatalPattern.test(String(detail))) fail('Runtime fatal status: '+detail);
    }),'Runtime report binding');
    await op(page.addInitScript(()=>{
      if (window!==top) return;
      window.addEventListener('message',event=>{
        if (event.origin===location.origin && event.source===document.querySelector('#viewport iframe')?.contentWindow && event.data?.channel==='ut4-runtime') {
          window.__ut4Report(event.data.type,event.data.detail);
        }
      });
    }),'Runtime message observer');
    await op(page.goto(config.url,{waitUntil:'domcontentloaded'}),'Launcher navigation');
    await op(page.locator('#mode').selectOption(config.mode),'Mode selection');
    await op(page.locator('#settings').click(),'Settings');
    await op(page.locator('#resolution').selectOption(resolution),'Resolution selection');
    // Exercise actual exported settings via the existing launcher after world readiness.
    await op(page.evaluate(()=>{
      localStorage.setItem('tournament.local-ut4.volume','0.4');
      localStorage.setItem('tournament.local-ut4.sensitivity','0.04');
    }),'Verification settings');
    await op(page.reload({waitUntil:'domcontentloaded'}),'Reload saved settings');
    const deadline=Date.now()+config.readyTimeoutSeconds*1000;
    const startup=(operation,label)=>startupOperation(operation,label,deadline,failed);
    await startup(timeout=>page.locator('#launch').click({timeout}),'Launch');
    let frame,state;
    while (Date.now()<deadline) {
      if (fatal) throw fatal;
      const error=await startup(timeout=>page.locator('#error').textContent({timeout}),'Launcher status read');
      if (error?.trim()) throw Error('Launcher error: '+error);
      frame=page.frames().find(item=>item.url()===new URL('./runtime.html',config.url).href);
      // Never call C exports while the async runtime is still initializing.
      if (frame && await startup(()=>page.locator('#resume').isVisible(),'postRun readiness')) {
        state=await startup(()=>frame.evaluate(snapshot,REQUIRED_BINDINGS),'World/control read');
        result.lastReadiness=state;
        if (state.missing?.length) throw Error('Missing native control exports after postRun: '+state.missing.join(', '));
        if (state.ready) break;
      }
      await startup(remaining=>delay(Math.min(250,remaining)),'Readiness poll');
    }
    if (!state?.ready || !frame) throw Error('World readiness timeout; postRun/exit code alone is not success. Last state: '+JSON.stringify(state));
    assertState(state); result.worldReady=state;
    result.controls=await op(frame.evaluate(()=>{
      const api=window.__ut4Verify.api;
      return { resolution:api.TournamentBrowserSetResolution(Module.canvas.width,Module.canvas.height),
        sensitivity:api.TournamentBrowserSetSensitivity(.04),volume:api.TournamentBrowserSetVolume(.4),releaseInput:api.TournamentBrowserReleaseInput() };
    }),'Control exports');
    if (Object.values(result.controls).some(value=>value!==1)) throw Error('A control export rejected the request: '+JSON.stringify(result.controls));
    await op(page.locator('#resume').click(),'Return to actual engine');
    for (const viewport of [{width:960,height:900},{width:1600,height:1000}]) {
      await op(page.setViewportSize(viewport),'Window resize'); await op(delay(300),'Resize settle');
      assertState(await op(frame.evaluate(snapshot,REQUIRED_BINDINGS),'Fixed framebuffer check'));
    }
    await screenshot('world');
    if (config.webglSampleSeconds>0) {
      await op(frame.evaluate(beginWebGLSample,{seconds:config.webglSampleSeconds,expected:[width,height]}),'Begin WebGL evidence sample');
      await op(delay(config.webglSampleSeconds*1000+50),'WebGL evidence interval');
      result.webgl=await op(frame.evaluate(finishWebGLSample),'Read WebGL draw evidence');
      if (!result.webgl.worldUnchanged) throw Error('World changed during WebGL sample.');
    }
    const warmupEnd=Date.now()+config.warmupSeconds*1000;
    while (Date.now()<warmupEnd) {
      assertState(await op(frame.evaluate(snapshot,REQUIRED_BINDINGS),'Warmup health'));
      await op(delay(250),'Warmup');
    }
    await op(frame.evaluate(beginMeasurement,config.seconds),'Install engine tick observer');
    let progress;
    do {
      await op(delay(250),'Measurement poll');
      assertState(await op(frame.evaluate(snapshot,REQUIRED_BINDINGS),'Measured world/framebuffer health'));
      progress=await op(frame.evaluate(readMeasurement),'Native tick health');
      result.lastMeasurement=progress;
      if (progress.issues.length) throw Error(progress.issues.join('; '));
      if (Math.min(progress.now,progress.deadline)-progress.lastAdvance>config.stallSeconds*1000) throw Error('Native engine tick stall; no fabricated FPS.');
    } while (progress.now<progress.deadline);
    result.metrics=await op(frame.evaluate(finishMeasurement),'Read engine tick samples');
    if (result.metrics.nativeTicks<3 || result.metrics.p95TickIntervalMs===null || result.metrics.issues.length) throw Error('Insufficient valid native tick samples; metrics remain uninitialized.');
    result.final=await op(frame.evaluate(snapshot,REQUIRED_BINDINGS),'Final world/framebuffer read'); assertState(result.final);
    await screenshot('measured');
    if (fatal) throw fatal;
    result.status='passed';
  } catch (error) {
    primaryError=error;
    result.status='failed'; result.error=error.message;
    if (page) try { await screenshot('failure'); } catch (captureError) { result.screenshotError=captureError.message; }
    throw error;
  } finally {
    cleaning=true;
    await cleanupVerification(server,result,primaryError,{browser});
  }
}

async function main() {
  const argv=process.argv.slice(2);
  if (argv.length===1 && argv[0]==='--help') { console.log(help); return; }
  if (argv.length===1 && argv[0]==='--self-test-diagnostics') {
    const { default:assert }=await import('node:assert/strict');
    let checks=0;
    const check=(type,text,expected)=>{ assert.equal(isFailureDiagnostic(type,text),expected,JSON.stringify({type,text})); checks++; };
    const notices=['[UT4] run() called, but dependencies remain, so not running',
      '[UT4] Calling stub instead of sigaction()',
      ...[0,1,223,10000].map(ms=>'[UT4] pre-main prep time: '+ms+' ms')];
    for (const text of notices) {
      check('error',text,false);
      for (const near of [' '+text,text+' ',text+'\n',text+'\r\n','prefix '+text,text+' suffix',
        text.replace('[UT4] ',''),text.replace('[UT4]','[ut4]'),text+' DebugBreak()',text+'\nLogParty:Error: World missing']) check('error',near,true);
    }
    for (const value of ['-1','1.5','NaN','Infinity','1e3','01','+1','']) check('error','[UT4] pre-main prep time: '+value+' ms',true);
    for (const text of ['[UT4] Calling stub instead of signal()', '[UT4] pre-main prep time: 223 seconds',
      '[UT4] pre-main prep time: 223 ms failed', '[UT4] missing pak', '[UT4] Source map information is not available',
      '[UT4] still waiting on run dependencies:', '[UT4] exit(0) called']) check('error',text,true);
    for (const type of ['error','info','warning','log']) {
      for (const text of ['DebugBreak() called!', '[UT4] Fatal error: missing Deck',
        "[UT4] [2026.09.21-19.03.50:093][ 97]LogEngine: ERROR: Failed to load special material '/Engine/EngineMaterials/RemoveSurfaceMaterial.RemoveSurfaceMaterial'.",
        '[UT4] LogPakFile:Error: missing pak', '[UT4] Ensure condition failed: World [Party.cpp:162]',
        '[UT4] Assertion failed: World', '[UT4] abort(0)', '[UT4] RuntimeError: memory access out of bounds']) check(type,text,true);
    }
    console.log('Diagnostic regression checks passed: '+checks+'. No runtime contacted.'); return;
  }
  if (argv.length===1 && argv[0]==='--self-test-args') {
    const { default:assert }=await import('node:assert/strict');
    const base=['--url','http://127.0.0.1:8000/','--manifest-url','http://127.0.0.1:8000/runtime.json','--out-dir',realpathSync(tmpdir())];
    assert.equal(parseArgs(base).resolution,'both');
    assert.equal(parseArgs([...base,'--validate-only']).validateOnly,true);
    assert.equal(parseArgs([...base,'--seconds','10','--resolution','1440p','--headed']).seconds,10);
    for (const extra of [['--seconds','0'],['--seconds','NaN'],['--seconds','Infinity'],['--seconds',' '],['--seconds','601'],['--warmup-seconds','-1'],['--stall-seconds','1'],['--ready-timeout-seconds','1801'],['--mode','host'],['--resolution','720p'],['--channel','other'],['--seconds'],['--unknown'],['--headed','--headed']]) assert.throws(()=>parseArgs([...base,...extra]));
    for (const [key,value] of [['--url','file:///tmp/index.html'],['--url','http://user:pw@127.0.0.1:8000/'],['--url','http://127.0.0.1:8000/?override=1'],['--url','http://127.0.0.1:8000/tests/fixtures/index.html'],['--manifest-url','http://example.invalid/runtime.json'],['--out-dir',repo],['--out-dir',join(repo,'ports/html5/client')],['--out-dir','.']]) {
      const changed=base.slice(); changed[changed.indexOf(key)+1]=value; assert.throws(()=>parseArgs(changed));
    }
    assert.throws(()=>parseArgs([]));
    console.log('Argument validation passed. No network, browser, assets or output files used.'); return;
  }
  const config=parseArgs(argv);
  if (config.validateOnly) { console.log(JSON.stringify({ valid:true,config,note:'Arguments only; manifest/runtime not contacted.' },null,2)); return; }
  const directory=await mkdtemp(join(config.outDir,'ut4-runtime-'));
  const report={ version:1,started:new Date().toISOString(),status:'failed',config,runs:[],
    scope:'Operator-supplied real runtime; no assets copied. Not proof of gameplay, handshake, audio quality, input feel or performance guarantees.' };
  try {
    const response=await fetch(config.manifestURL,{redirect:'error',signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw Error('Manifest HTTP '+response.status);
    const bytes=await bounded(response.text(),15000,'Manifest body timed out');
    if (bytes.length>1048576) throw Error('Manifest exceeds 1 MiB.');
    const manifest=validateManifest(JSON.parse(bytes),config.manifestURL);
    argumentsForMode(manifest,config.mode);
    if (REQUIRED_BINDINGS.some(name=>!manifest.bindings.includes(name))) throw Error('Manifest must list all nine control exports, including TournamentBrowserSessionEpoch.');
    if (Object.entries(manifest.files).some(([name,url])=>/fixture|\/tests\//i.test(name+' '+url))) throw Error('Fixture asset detected; refused.');
    report.manifestSha256=createHash('sha256').update(bytes).digest('hex');
    for (const resolution of config.resolution==='both'?['1080p','1440p']:[config.resolution]) {
      console.log('Verifying actual runtime at '+resolution+'; world readiness required.');
      await verifyResolution(config,resolution,directory,report);
    }
    report.status='passed';
  } catch (error) { report.error=error.message; process.exitCode=1; }
  finally {
    report.finished=new Date().toISOString();
    await writeFile(join(directory,'report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(report.status.toUpperCase()+': '+join(directory,'report.json'));
    if (report.error) console.error(report.error);
  }
}
if (process.argv[1] && fileURLToPath(import.meta.url)===realpathSync(process.argv[1])) {
  main().catch(error=>{ console.error(error.message); process.exitCode=2; });
}
