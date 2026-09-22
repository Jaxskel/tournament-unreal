import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareEngine } from '../startup.mjs';

const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };
const turn = () => new Promise(resolve => setImmediate(resolve));

test('package transfer starts during compilation; engine waits for both prerequisites', async () => {
  const compilation = deferred(), support = deferred(), packageScript = deferred(), events=[];
  const run = prepareEngine({compile:()=>{events.push('compile');return compilation.promise;},
    supportScripts:['support'],dataScripts:['package'],engine:'engine',stopped:()=>false,
    loadScript:async name=>{events.push(name); if(name==='support')await support.promise; if(name==='package')await packageScript.promise;}});
  await turn(); assert.deepEqual(new Set(events),new Set(['support','compile']));
  support.resolve(); await turn(); assert.equal(events.at(-1),'package');
  compilation.resolve(); await turn(); assert.equal(events.includes('engine'),false);
  packageScript.resolve(); assert.equal(await run,true); assert.equal(events.at(-1),'engine');
});

test('data scripts retain declared order and cannot start engine before compilation',async()=>{
  const compilation=deferred(), events=[];
  const run=prepareEngine({compile:()=>compilation.promise,supportScripts:['a','b'],dataScripts:['c','d'],engine:'engine',stopped:()=>false,loadScript:async name=>events.push(name)});
  await turn(); assert.deepEqual(events,['a','b','c','d']); compilation.resolve(); await run; assert.deepEqual(events,['a','b','c','d','engine']);
});

test('failed compilation rejects promptly without executing engine; pending script can finish safely',async()=>{
  const pending=deferred(), events=[]; let stopped=false;
  const error=new Error('compile failed');
  const run=prepareEngine({compile:()=>Promise.reject(error),supportScripts:['a','b'],dataScripts:['c'],engine:'engine',stopped:()=>stopped,loadScript:async name=>{events.push(name);await pending.promise;}});
  await assert.rejects(run,e=>e===error); stopped=true; pending.resolve(); await turn(); assert.deepEqual(events,['a']);
});

test('script failure observes late compilation rejection without executing engine',async()=>{
  const pending=deferred(), events=[];
  const error=new Error('script failed');
  const run=prepareEngine({compile:()=>pending.promise,supportScripts:[],dataScripts:['data'],engine:'engine',stopped:()=>false,loadScript:async name=>{events.push(name);throw error;}});
  await assert.rejects(run,e=>e===error); pending.reject(new Error('late compile failure')); await turn(); assert.deepEqual(events,['data']);
});

test('disposal during startup prevents remaining scripts and engine execution',async()=>{
  const pending=deferred(), events=[];let stopped=false;
  const run=prepareEngine({compile:()=>pending.promise,supportScripts:['a'],dataScripts:['data'],engine:'engine',stopped:()=>stopped,loadScript:async name=>{events.push(name);stopped=true;}});
  pending.resolve(); assert.equal(await run,false); assert.deepEqual(events,['a']);
});

test('asm.js requires no compiler and still preserves script order',async()=>{
  const events=[];assert.equal(await prepareEngine({compile:()=>{},supportScripts:['support'],dataScripts:['data'],engine:'engine',stopped:()=>false,loadScript:async name=>events.push(name)}),true);assert.deepEqual(events,['support','data','engine']);
});
