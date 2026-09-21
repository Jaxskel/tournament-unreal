import test from 'node:test';
import assert from 'node:assert/strict';
import { BINDINGS, EngineBindings } from '../bindings.mjs';

test('native settings wait for Ready, retry a rejected apply and avoid probing missing exports', () => {
  let ready = 0, attempts = 0;
  const calls = [];
  const module = { cwrap(name,result,args) {
    assert.equal(result,'number'); assert.deepEqual(args,BINDINGS[name]); calls.push(name); return module['_'+name];
  }, _TournamentBrowserReady: () => ready, _TournamentBrowserSessionEpoch: () => 1,
  _TournamentBrowserSetVolume: value => { assert.equal(value,.4); return ++attempts > 1 ? 1 : 0; } };
  const bridge = new EngineBindings(module,Object.keys(BINDINGS));
  bridge.poll({ volume:.4 }); assert.equal(attempts,0);
  assert.deepEqual(calls,['TournamentBrowserReady','TournamentBrowserSessionEpoch','TournamentBrowserSetVolume']);
  ready = 1;
  assert.equal(bridge.poll({ volume:.4 }).applied.volume,undefined);
  assert.equal(bridge.poll({ volume:.4 }).applied.volume,.4);
  bridge.poll({ volume:.4 }); assert.equal(attempts,2);
  assert.equal(bridge.poll({ volume:.4 }).available.sensitivity,false);
});

test('epoch change reapplies saved settings even when Ready never becomes false', () => {
  let epoch = 1;
  let sensitivity = .05;
  const writes = { sensitivity:0,volume:0,resolution:0 };
  const module = {
    _TournamentBrowserReady:()=>1, _TournamentBrowserSessionEpoch:()=>epoch,
    _TournamentBrowserSetSensitivity:value=>{ sensitivity=value; writes.sensitivity++; return 1; },
    _TournamentBrowserSetVolume:()=>{ writes.volume++; return 1; },
    _TournamentBrowserSetResolution:()=>{ writes.resolution++; return 1; },
    _TournamentBrowserWidth:()=>2560, _TournamentBrowserHeight:()=>1440,
    cwrap(name,result,args) { assert.equal(result,'number'); assert.deepEqual(args,BINDINGS[name]); return module['_'+name]; }
  };
  const bridge = new EngineBindings(module,Object.keys(BINDINGS));
  const saved = { sensitivity:.2,volume:.4,resolution:'1440p' };
  bridge.poll(saved); bridge.poll(saved);
  assert.deepEqual(writes,{ sensitivity:1,volume:1,resolution:1 });
  sensitivity=.05; epoch=2; // Replacement controller/world entirely between polls.
  const report=bridge.poll(saved);
  assert.equal(sensitivity,.2); assert.equal(report.epoch,2);
  assert.deepEqual(report.applied,saved);
  assert.deepEqual(writes,{ sensitivity:2,volume:2,resolution:2 });
  bridge.poll(saved);
  assert.deepEqual(writes,{ sensitivity:2,volume:2,resolution:2 });
});

test('unavailable or invalid epochs never cache or apply live settings', () => {
  let epoch;
  let calls=0;
  const module={ _TournamentBrowserReady:()=>1, _TournamentBrowserSetSensitivity:()=>{ calls++; return 1; },
    cwrap(name) { return module['_'+name]; } };
  const bridge=new EngineBindings(module,Object.keys(BINDINGS));
  assert.equal(bridge.poll({ sensitivity:.2 }).available.sensitivity,false);
  module._TournamentBrowserSessionEpoch=()=>epoch;
  for (epoch of [0,-1,NaN,Infinity,1.5,Number.MAX_SAFE_INTEGER+1]) {
    const report=bridge.poll({ sensitivity:.2 });
    assert.equal(report.epoch,null); assert.deepEqual(report.applied,{});
  }
  assert.equal(calls,0);
  epoch=1; assert.equal(bridge.poll({ sensitivity:.2 }).applied.sensitivity,.2);
  epoch=0; assert.deepEqual(bridge.poll({ sensitivity:.2 }).applied,{});
  epoch=1; bridge.poll({ sensitivity:.2 }); assert.equal(calls,2);
});

test('each new ready controller releases input in menu, with failed releases retried', () => {
  let epoch=1, released=0, accepted=1;
  const module={ _TournamentBrowserReady:()=>1, _TournamentBrowserSessionEpoch:()=>epoch,
    _TournamentBrowserReleaseInput:()=>{ released++; return accepted; },
    cwrap(name,result,args) { assert.equal(result,'number'); assert.deepEqual(args,[]); return module['_'+name]; } };
  const bridge=new EngineBindings(module,Object.keys(BINDINGS));
  bridge.poll({},true); bridge.poll({},true); assert.equal(released,1);
  epoch=2; bridge.poll({},true); bridge.poll({},true); assert.equal(released,2);
  epoch=3; bridge.poll({},false); assert.equal(released,2); // Travel during play must not release input.
  bridge.release(); assert.equal(released,3); // Opening menu still releases within an unchanged epoch.
  epoch=4; accepted=0; bridge.poll({},true); assert.equal(released,4);
  accepted=1; bridge.poll({},true); bridge.poll({},true); assert.equal(released,5);
});

test('failed setter in a new epoch retries without retaining the old applied value', () => {
  let ready=1,epoch=1,accepted=1,calls=0;
  const module={ _TournamentBrowserReady:()=>ready, _TournamentBrowserSessionEpoch:()=>epoch,
    _TournamentBrowserSetSensitivity:()=>{ calls++; return accepted; }, cwrap(name) { return module['_'+name]; } };
  const bridge=new EngineBindings(module,Object.keys(BINDINGS));
  bridge.poll({ sensitivity:.2 });
  ready=0; assert.deepEqual(bridge.poll({ sensitivity:.2 }).applied,{});
  assert.equal(calls,1);
  ready=1; epoch=2; accepted=0;
  assert.deepEqual(bridge.poll({ sensitivity:.2 }).applied,{});
  accepted=1; assert.equal(bridge.poll({ sensitivity:.2 }).applied.sensitivity,.2);
  assert.equal(calls,3);
});
test('late exports use exact signatures; input release waits for native readiness', () => {
  const module = {};
  const bridge = new EngineBindings(module,Object.keys(BINDINGS));
  bridge.release(); assert.equal(bridge.poll({}).ready,false);
  let released = 0;
  Object.assign(module, { _TournamentBrowserReady:()=>1, _TournamentBrowserReleaseInput:()=>{ released++; return 1; },
    cwrap(name,result,args) { assert.equal(result,'number'); assert.deepEqual(args,BINDINGS[name]); return module['_'+name]; } });
  bridge.poll({}); bridge.poll({}); assert.equal(released,1);
});

test('disposed bindings release module and wrappers and cannot call the old engine', () => {
  let calls=0;
  const module={_TournamentBrowserReady:()=>{calls++;return 1;},cwrap(name){return this['_'+name];}};
  const bridge=new EngineBindings(module,Object.keys(BINDINGS));
  bridge.poll({});assert.equal(calls,1);
  bridge.dispose();bridge.dispose();
  assert.equal(bridge.module,null);assert.deepEqual(bridge.functions,{});
  assert.equal(bridge.poll({}).ready,false);bridge.release();
  assert.equal(calls,1);
});
