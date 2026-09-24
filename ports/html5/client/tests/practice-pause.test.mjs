import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createContext, runInContext } from 'node:vm';
import * as core from '../core.mjs';
import { EngineBindings, BINDINGS, REQUIRED_BINDINGS } from '../bindings.mjs';

function engine() {
  const state = { ready:0, epoch:1, frame:0, status:0, acceptPause:true, acceptResume:true,
    width:1920, height:1080, requested:null, movement:0, orders:[] };
  const module = {
    _TournamentBrowserReady:() => state.ready,
    _TournamentBrowserSessionEpoch:() => state.epoch,
    _TournamentBrowserFrame:() => state.frame,
    _TournamentBrowserMenuPauseStatus:epoch => { assert.equal(epoch,state.epoch); return state.status; },
    _TournamentBrowserSetMenuPaused:(paused,epoch) => {
      assert.equal(epoch,state.epoch); state.orders.push(['pause',paused]);
      if (!(paused ? state.acceptPause : state.acceptResume)) return 0;
      state.status = paused ? 1 : 0; return 1;
    },
    _TournamentBrowserReleaseInput:() => { state.orders.push(['release']); return 1; },
    _TournamentBrowserSetResolution:(w,h) => { state.requested=[w,h]; return 1; },
    _TournamentBrowserWidth:() => state.width,
    _TournamentBrowserHeight:() => state.height,
    _TournamentBrowserSetVolume:v => { state.orders.push(['volume',v]); return 1; },
    cwrap(name, result, args) { assert.equal(result,'number'); assert.deepEqual(args,BINDINGS[name]); return this['_'+name]; }
  };
  const bridge = new EngineBindings(module,Object.keys(BINDINGS));
  function tick(delta=1) {
    bridge.beforeFrame();
    if (state.status !== 1) state.movement += delta;
    if (state.requested) [state.width,state.height]=state.requested;
    ++state.frame;
    return bridge.afterFrame();
  }
  return { state,module,bridge,tick, calls:() => state.orders.filter(x=>x[0]==='pause') };
}

test('menu before Ready retains intent without pausing the engine scheduler; early resume cancels it', () => {
  for (const resumeEarly of [false,true]) {
    const e=engine();
    e.bridge.poll({},true,true);
    assert.deepEqual(e.calls(),[]);
    if (resumeEarly) e.bridge.poll({},false,true);
    e.state.ready=1;
    const report=e.bridge.poll({},!resumeEarly,true);
    assert.equal(report.pause.state,resumeEarly?'running':'paused');
    assert.deepEqual(e.calls(),resumeEarly?[]:[['pause',1]]);
    e.bridge.poll({},!resumeEarly,true);
    assert.equal(e.calls().length,resumeEarly?0:1);
  }
});

test('resume needs an effective paused frame beginning after the request; background delta stays paused', () => {
  const e=engine();e.state.ready=1;e.bridge.poll({},true,true);
  e.tick(); // A frame before resume cannot satisfy the resume fence.
  e.bridge.poll({},false,true);e.bridge.poll({},false,true);
  assert.equal(e.bridge.afterFrame(),false);
  assert.equal(e.bridge.pause.pending,true);
  assert.equal(e.tick(60000),true);
  assert.equal(e.state.movement,0);
  assert.equal(e.bridge.pause.pending,false);
  assert.deepEqual(e.calls(),[['pause',1],['pause',0]]);
  e.tick(1);assert.equal(e.state.movement,1);
  for (let i=0;i<e.state.orders.length;i++) if(e.state.orders[i][0]==='pause') {
    assert.equal(e.state.orders[i-1][0],'release');
  }
});

test('skipped callbacks, PauseDelay and reopening menu cannot satisfy a pending resume', () => {
  const e=engine();e.state.ready=1;e.bridge.poll({},true,true);e.bridge.poll({},false,true);
  e.bridge.beforeFrame();assert.equal(e.bridge.afterFrame(),false); // Counter did not advance.
  e.state.status=3;
  e.bridge.beforeFrame();e.state.status=1;++e.state.frame;
  assert.equal(e.bridge.afterFrame(),false); // Pause only became effective during callback.
  e.bridge.beforeFrame();++e.state.frame;e.bridge.poll({},true,true);
  assert.equal(e.bridge.afterFrame(),false);
  assert.deepEqual(e.calls(),[['pause',1]]);
});

test('native refusals remain truthful and retry; failed unpause keeps input pending', () => {
  const e=engine();e.state.ready=1;e.state.acceptPause=false;
  assert.equal(e.bridge.poll({},true,true).pause.state,'unavailable');
  e.state.acceptPause=true;assert.equal(e.bridge.poll({},true,true).pause.state,'paused');
  e.state.acceptResume=false;e.bridge.poll({},false,true);e.tick();
  assert.equal(e.bridge.pause.state,'resuming');assert.equal(e.bridge.pause.pending,true);
  e.state.acceptResume=true;e.tick();assert.equal(e.bridge.pause.state,'running');
});

test('world/epoch replacement cancels a stale frame fence and applies only current intent', () => {
  const e=engine();e.state.ready=1;e.bridge.poll({},true,true);e.bridge.poll({},false,true);
  e.bridge.beforeFrame();e.state.epoch=2;e.state.status=0;++e.state.frame;
  assert.equal(e.bridge.afterFrame(),false);assert.deepEqual(e.calls(),[['pause',1]]);
  assert.equal(e.bridge.poll({},false,true).pause.state,'running');
  e.bridge.poll({},true,true);assert.deepEqual(e.calls(),[['pause',1],['pause',1]]);
  e.state.ready=0;e.bridge.poll({},true,true);e.state.ready=1;e.state.epoch=3;e.state.status=0;
  assert.equal(e.bridge.poll({},true,true).pause.state,'paused');
});

test('paused engine callbacks complete deferred resize and volume changes without gameplay advancing', () => {
  const e=engine();e.state.ready=1;e.bridge.poll({},true,true);
  for (const [resolution,dimensions,volume] of [['1440p',[2560,1440],.2],['1080p',[1920,1080],.8]]) {
    const pending=e.bridge.poll({resolution,volume},true,true);
    assert.notDeepEqual(pending.actual,dimensions);
    e.tick(5000);
    assert.deepEqual(e.bridge.poll({resolution,volume},true,true).actual,dimensions);
    assert.equal(e.state.movement,0);assert.equal(e.bridge.pause.state,'paused');
  }
  assert.deepEqual(e.state.orders.filter(x=>x[0]==='volume'),[['volume',.2],['volume',.8]]);
});

test('multiplayer never calls either pause export; foreign pauses are not adopted or resumed', () => {
  const e=engine();e.state.ready=1;
  e.module._TournamentBrowserMenuPauseStatus=()=>assert.fail('multiplayer pause getter');
  e.bridge.poll({},true,false);e.bridge.poll({},false,false);e.tick();assert.deepEqual(e.calls(),[]);
  const f=engine();f.state.ready=1;f.state.status=2;
  assert.equal(f.bridge.poll({},true,true).pause.state,'external');
  f.bridge.poll({},false,true);f.tick();assert.deepEqual(f.calls(),[]);
  assert.equal(f.bridge.pause.pending,false);
});

test('older nine-export builds, invalid epochs and disposal cannot become permanently input-blocked', () => {
  assert.equal(REQUIRED_BINDINGS.length,9);
  const e=engine();e.state.ready=1;
  e.bridge.names=[...REQUIRED_BINDINGS];
  assert.equal(e.bridge.poll({},true,true).pause.state,'unavailable');
  assert.equal(e.bridge.poll({},false,true).pause.pending,false);assert.deepEqual(e.calls(),[]);
  const f=engine();f.state.ready=1;
  for (const epoch of [0,-1,NaN,Infinity,1.5,Number.MAX_SAFE_INTEGER+1]) {
    f.state.epoch=epoch;f.bridge.poll({},true,true);assert.deepEqual(f.calls(),[]);
  }
  f.state.epoch=1;f.bridge.poll({},true,true);f.bridge.poll({},false,true);f.bridge.beforeFrame();
  f.bridge.dispose();++f.state.frame;assert.equal(f.bridge.afterFrame(),false);
  assert.equal(f.bridge.pause.pending,false);assert.deepEqual(f.calls(),[['pause',1]]);
});

const runtimeSource=(await readFile(new URL('../runtime.mjs',import.meta.url),'utf8')).replace(/^import .*;\n/gm,'');
function runtimeSurface(names=Object.keys(BINDINGS)) {
  const e=engine(), messages=[], gestures=[], releases=[];
  function surface() {
    const listeners=new Map();
    return {
      addEventListener(type,callback) { if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(callback); },
      dispatch(type,details={}) {
        const event={...details,blocked:false,preventDefault(){},stopImmediatePropagation(){this.blocked=true;}};
        for(const callback of listeners.get(type)??[]){callback(event);if(event.blocked)break;}
        return event;
      }
    };
  }
  const canvas=Object.assign(surface(),{width:1920,height:1080,focus(){},blur(){},
    dispatchEvent(event){releases.push(event);},requestPointerLock(){gestures.push('pointer');}});
  const document=Object.assign(surface(),{getElementById:()=>canvas,pointerLockElement:null,exitPointerLock(){},hasFocus:()=>true});
  let schedulerPauses=0;
  Object.assign(e.module,{pauseMainLoop(){++schedulerPauses;},resumeMainLoop(){},resumeBrowserAudio(){gestures.push('audio');return 'running';}});
  const window=Object.assign(surface(),{Module:e.module});
  const context=createContext({...core,EngineBindings,BINDINGS,window,document,console,URL,
    parent:{postMessage:m=>messages.push(m),document},location:{origin:'http://localhost'},
    clearInterval(){},performance,KeyboardEvent:class{constructor(type,fields){this.type=type;Object.assign(this,fields);}}});
  runInContext(runtimeSource,context);
  const evaluate=code=>runInContext(code,context);
  evaluate(`bridge=new EngineBindings(window.Module,${JSON.stringify(names)});initialized=true;runtimeInitialized=true;`);
  return {...e,window,canvas,document,context,evaluate,messages,gestures,releases,schedulerPauses:()=>schedulerPauses};
}

test('actual runtime menu releases held input immediately and keeps native scheduler running through capture/resume', () => {
  const r=runtimeSurface();r.state.ready=1;r.evaluate('resume()');
  assert.equal(r.window.dispatch('keydown',{key:'w',code:'KeyW'}).blocked,false);
  r.evaluate('menu()');assert.equal(r.state.status,1);
  assert.equal(r.releases[0].code,'KeyW');assert.equal(r.releases[0].type,'keyup');
  assert.equal(r.schedulerPauses(),0);
  r.window.captureUT4Pointer();
  assert.deepEqual(r.gestures,['audio','pointer']);
  assert.equal(r.state.status,1,'gesture must not unpause before an engine callback');
  assert.equal(r.window.dispatch('keydown',{key:'w',code:'KeyW'}).blocked,true);
  assert.equal(r.canvas.dispatch('mousedown',{button:0}).blocked,true);
  r.evaluate('beforeEngineFrame()');++r.state.frame;r.evaluate('afterEngineFrame()');
  assert.equal(r.state.status,0);
  assert.equal(r.window.dispatch('keydown',{key:'w',code:'KeyW'}).blocked,false);
  assert.equal(r.canvas.dispatch('mousedown',{button:0}).blocked,false);
  assert.equal(r.schedulerPauses(),0);
});

test('actual runtime waits for Ready, preserves deferred canvas sizing, and older builds resume without pause claims', () => {
  const r=runtimeSurface();r.evaluate('menu()');assert.equal(r.state.status,0);assert.equal(r.schedulerPauses(),0);
  r.state.ready=1;r.evaluate('pollBindings();updateSettings({resolution:"1440p",volume:.7});pollBindings()');
  assert.equal(r.state.status,1);assert.equal(r.canvas.width,1920);
  [r.state.width,r.state.height]=r.state.requested;
  r.evaluate('beforeEngineFrame()');++r.state.frame;r.evaluate('afterEngineFrame();pollBindings()');
  assert.equal(r.canvas.width,2560);assert.equal(r.canvas.height,1440);assert.equal(r.state.status,1);
  const old=runtimeSurface(REQUIRED_BINDINGS);old.state.ready=1;old.evaluate('menu();resume()');
  assert.equal(old.window.dispatch('keydown',{key:'w',code:'KeyW'}).blocked,false);
  assert.equal(old.schedulerPauses(),0);
  assert.equal(old.messages.some(m=>m.type==='status'&&m.detail==='Practice paused.'),false);
});

function body(source, signature) {
  const start=source.indexOf(signature);assert.ok(start>=0,signature);
  let depth=0;
  for(let i=source.indexOf('{',start);i<source.length;i++) {
    if(source[i]==='{')++depth;
    if(source[i]==='}' && --depth===0)return source.slice(start,i+1);
  }
  throw Error('Unclosed body');
}

test('actual native exports enforce readiness/epoch/network/ownership and confirm real pause state', async t => {
  const compiler=process.env.CXX || 'c++';
  if(spawnSync(compiler,['--version']).error){t.skip('C++ compiler unavailable');return;}
  const controls=await readFile(new URL('../../../../Plugins/TournamentBridge/Source/TournamentBridge/Private/TournamentHTML5Controls.cpp',import.meta.url),'utf8');
  const pause=controls.slice(controls.indexOf('namespace {\nstruct FBrowserMenuPause'),controls.indexOf('#ifndef TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS'));
  assert.ok(pause.includes('TournamentBrowserSetMenuPaused'));
  const source=String.raw`
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <initializer_list>
#define EMSCRIPTEN_KEEPALIVE
using uint32=uint32_t;
bool GameThread=true;
bool IsInGameThread(){return GameThread;}
struct FMath {static bool IsFinite(double x){return std::isfinite(x);}};
template<class T>struct TWeakObjectPtr {
 T* Pointer=nullptr; T* Get()const{return Pointer;} void Reset(){Pointer=nullptr;}
 TWeakObjectPtr& operator=(T* p){Pointer=p;return *this;}
};
enum ENetMode{NM_Standalone,NM_Client,NM_ListenServer,NM_DedicatedServer};
struct APlayerState {};
struct AWorldSettings {APlayerState* Pauser=nullptr;};
struct APlayerController;
struct UWorld {
 bool Begun=true,Auth=true,Delay=false,External=false;void* Driver=nullptr;ENetMode Mode=NM_Standalone;
 AWorldSettings Settings;APlayerController* Player=nullptr;
 bool HasBegunPlay(){return Begun;} APlayerController* GetFirstPlayerController(){return Player;}
 AWorldSettings* GetWorldSettings(){return &Settings;} void* GetAuthGameMode(){return Auth?this:nullptr;}
 ENetMode GetNetMode(){return Mode;} void* GetNetDriver(){return Driver;}
 bool IsPaused(){return External || (Settings.Pauser && !Delay);}
};
struct APlayerController {
 virtual ~APlayerController(){} UWorld* World=nullptr;APlayerState State;APlayerState* PlayerState=&State;
 bool Local=true,Allow=true,Clear=true;int PauseCalls=0,ResumeCalls=0,Releases=0,LastRelease=0;
 UWorld* GetWorld(){return World;} bool IsLocalController(){return Local;}
 bool IsPaused(){return World->Settings.Pauser!=nullptr;}
 bool SetPause(bool pause){assert(Releases>LastRelease);LastRelease=Releases;
  if(pause){++PauseCalls;if(!Allow)return false;World->Settings.Pauser=PlayerState;return true;}
  ++ResumeCalls;if(Clear)World->Settings.Pauser=nullptr;return true;
 }
};
struct ATournamentPlayerController:APlayerController{};
template<class T>T* Cast(APlayerController* p){return dynamic_cast<T*>(p);}
struct FWorldContext {void* PendingNetGame=nullptr;};
struct ViewportClient {UWorld* World=nullptr;void* Viewport=nullptr;UWorld* GetWorld(){return World;}};
struct Engine {ViewportClient* GameViewport=nullptr;FWorldContext Context;bool HasContext=true;
 FWorldContext* GetWorldContextFromWorld(UWorld*){return HasContext?&Context:nullptr;}};
Engine* GEngine=nullptr;
`+[body(controls,'UWorld* BrowserWorld()'),body(controls,'APlayerController* BrowserPlayer()'),
    body(controls,'int TournamentBrowserReady()'),body(controls,'double TournamentBrowserSessionEpoch()')].join('\n')+
String.raw`
int TournamentBrowserReleaseInput(){++BrowserPlayer()->Releases;return 1;}
`+pause+String.raw`
int main(){
 assert(TournamentBrowserSetMenuPaused(1,1)==0);
 Engine engine;GEngine=&engine;ViewportClient viewport;engine.GameViewport=&viewport;
 UWorld world;viewport.World=&world;viewport.Viewport=&world;
 ATournamentPlayerController pc;pc.World=&world;world.Player=&pc;
 double epoch=TournamentBrowserSessionEpoch();assert(epoch>0);
 for(double bad:{0.,-1.,epoch+.5,epoch+1,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
  assert(TournamentBrowserMenuPauseStatus(bad)==-1);assert(TournamentBrowserSetMenuPaused(1,bad)==0);
 }
 assert(TournamentBrowserSetMenuPaused(2,epoch)==0);
 for(ENetMode mode:{NM_Client,NM_ListenServer,NM_DedicatedServer}){world.Mode=mode;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);}
 world.Mode=NM_Standalone;world.Driver=&world;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);world.Driver=nullptr;
 engine.Context.PendingNetGame=&world;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);engine.Context.PendingNetGame=nullptr;
 engine.HasContext=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);engine.HasContext=true;
 GameThread=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);GameThread=true;
 world.Begun=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);world.Begun=true;
 world.Auth=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);world.Auth=true;
 pc.Local=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);pc.Local=true;
 pc.PlayerState=nullptr;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);pc.PlayerState=&pc.State;
 assert(pc.PauseCalls==0);
 APlayerState foreign;world.Settings.Pauser=&foreign;
 assert(TournamentBrowserMenuPauseStatus(epoch)==2);assert(TournamentBrowserSetMenuPaused(1,epoch)==0);
 assert(TournamentBrowserSetMenuPaused(0,epoch)==0);assert(world.Settings.Pauser==&foreign);
 world.Settings.Pauser=nullptr;world.External=true;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);world.External=false;
 pc.Allow=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);assert(TournamentBrowserMenuPauseStatus(epoch)==0);pc.Allow=true;
 world.Delay=true;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);assert(TournamentBrowserMenuPauseStatus(epoch)==3);
 const int pauses=pc.PauseCalls;assert(TournamentBrowserSetMenuPaused(1,epoch)==0);assert(pc.PauseCalls==pauses);
 world.Delay=false;assert(TournamentBrowserSetMenuPaused(1,epoch)==1);assert(pc.PauseCalls==pauses);
 assert(TournamentBrowserMenuPauseStatus(epoch)==1);
 pc.Clear=false;assert(TournamentBrowserSetMenuPaused(0,epoch)==0);assert(TournamentBrowserMenuPauseStatus(epoch)==1);
 pc.Clear=true;assert(TournamentBrowserSetMenuPaused(0,epoch)==1);assert(TournamentBrowserMenuPauseStatus(epoch)==0);
 const int resumes=pc.ResumeCalls;assert(TournamentBrowserSetMenuPaused(0,epoch)==1);assert(pc.ResumeCalls==resumes);
 assert(TournamentBrowserSetMenuPaused(1,epoch)==1);
 ATournamentPlayerController replacement;replacement.World=&world;world.Player=&replacement;
 const double next=TournamentBrowserSessionEpoch();assert(next!=epoch);
 assert(TournamentBrowserSetMenuPaused(0,epoch)==0);assert(TournamentBrowserMenuPauseStatus(next)==2);
 assert(TournamentBrowserSetMenuPaused(0,next)==0);assert(pc.ResumeCalls==resumes);
 // Pinned PC::Destroyed -> UTBaseGameMode::ForceClearUnpauseDelegates clears
 // the retired controller's pause. Model that engine lifecycle boundary here.
 world.Settings.Pauser=nullptr;assert(TournamentBrowserSetMenuPaused(1,next)==1);
 UWorld travel;travel.Player=&replacement;replacement.World=&travel;viewport.World=&travel;
 const double third=TournamentBrowserSessionEpoch();assert(third!=next);
 assert(TournamentBrowserSetMenuPaused(0,next)==0);assert(TournamentBrowserMenuPauseStatus(third)==0);
 assert(TournamentBrowserSetMenuPaused(1,third)==1);assert(replacement.PauseCalls==2);
}
`;
  const dir=await mkdtemp(join(tmpdir(),'ut4-pause-'));t.after(()=>rm(dir,{recursive:true,force:true}));
  const exe=join(dir,'check'+(process.platform==='win32'?'.exe':''));
  const compile=spawnSync(compiler,['-std=c++11','-x','c++','-o',exe,'-'],{input:source,encoding:'utf8',timeout:30000});
  assert.equal(compile.status,0,compile.stderr||compile.error?.message);
  const result=spawnSync(exe,[],{encoding:'utf8',timeout:5000});assert.equal(result.status,0,result.stderr||result.error?.message);
});
