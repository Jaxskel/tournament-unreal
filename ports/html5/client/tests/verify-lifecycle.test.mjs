// Harness scheduling/cleanup tests. One real owned browser tests delayed profile
// cleanup; no engine/game assets are used.
import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import { remainingStartupMs, startupOperation, cleanupVerification, trackBrowserServer } from '../verify-runtime.mjs';

const never=new Promise(()=>{});

test('startup budget is remaining time, not a fresh timeout or a 15-second cap',async()=>{
  let now=1000;
  const deadline=now+300000, budgets=[];
  for (const label of ['Launch','Launcher status read','postRun readiness','World/control read']) {
    const result=await startupOperation(remaining=>{
      budgets.push(remaining); now+=20000; return Promise.resolve(label);
    },label,deadline,never,()=>now);
    assert.equal(result,label);
  }
  assert.deepEqual(budgets,[300000,280000,260000,240000]);
  assert.equal(remainingStartupMs(deadline,now),220000);
});

test('an exhausted deadline never starts another UI operation or grants a minimum timeout',async()=>{
  for (const now of [1000,1001]) {
    assert.throws(()=>remainingStartupMs(1000,now),/deadline exhausted/);
    let called=false;
    await assert.rejects(startupOperation(()=>{called=true;},'UI',1000,never,()=>now),/deadline exhausted/);
    assert.equal(called,false);
  }
  assert.throws(()=>remainingStartupMs(Infinity,0),/deadline exhausted/);
});

test('a read that finishes after the global deadline cannot report successful readiness',async()=>{
  let now=0;
  await assert.rejects(startupOperation(()=>{now=301000;return Promise.resolve({ready:true});},
    'World/control read',300000,never,()=>now),/deadline exhausted/);
});

test('fatal diagnostics still win over a pending startup read',async()=>{
  let rejectFatal;
  const failed=new Promise((_,reject)=>{rejectFatal=reject;});
  const fatal=Error('LogEngine:Error: Failed to load special material');
  const pending=startupOperation(()=>never,'postRun readiness',Date.now()+300000,failed);
  const check=assert.rejects(pending,error=>error===fatal);
  rejectFatal(fatal);
  await check;
});

test('a blocked UI read is bounded by the remaining startup deadline',async()=>{
  await assert.rejects(startupOperation(()=>never,'postRun readiness',Date.now()+20,never),
    /postRun readiness timed out at the global startup deadline/);
});

function serverDouble({close=()=>Promise.resolve(),kill=()=>Promise.resolve(),forceThrow=false,exited=false}={}) {
  const calls=[];
  const process={exitCode:exited?0:null,signalCode:null,kill(signal){
    calls.push(['owned-process',signal]);
    if (forceThrow) throw Error('fixture force kill failure');
    return true;
  }};
  const server=Object.assign(new EventEmitter(),{calls,close(){calls.push('close');return close();},kill(){calls.push('kill');return kill();},
    process(){calls.push('process');return process;},
    finishClose(){process.exitCode=0;server.emit('close',0,null);}});
  return server;
}

test('successful close and successful kill fallback do not fail verification',async()=>{
  for (const failClose of [false,true]) {
    const server=serverDouble({close:()=>failClose?Promise.reject(Error('close failed')):Promise.resolve()});
    const result={status:'passed'};
    await cleanupVerification(server,result);
    assert.deepEqual(server.calls,failClose?['process','close','kill']:['process','close']);
    assert.deepEqual(result,{status:'passed'});
  }
  await cleanupVerification(undefined,{status:'failed'},Error('launch failed'));
});

test('close/kill timeout preserves the primary failure and records cleanup separately',async()=>{
  const server=serverDouble({close:()=>never,kill:()=>never});
  const primary=Error('actual missing Deck / engine fatal');
  const result={status:'failed',error:primary.message};
  const operation=async()=>{
    try { throw primary; }
    finally { await cleanupVerification(server,result,primary,{closeMs:5,killMs:5}); }
  };
  await assert.rejects(operation(),error=>error===primary);
  assert.equal(result.error,primary.message);
  assert.match(result.cleanupError,/Browser close timed out; Browser kill timed out/);
  assert.match(result.cleanupError,/SIGKILL requested for owned browser/);
  assert.deepEqual(server.calls,['process','close','kill',['owned-process','SIGKILL']]);
});

test('cleanup failure alone fails an otherwise passed run',async()=>{
  const server=serverDouble({close(){throw Error('close failure');},kill(){return Promise.reject(Error('kill failure'));}});
  const result={status:'passed'};
  await assert.rejects(cleanupVerification(server,result),/close failure; kill failure/);
  assert.equal(result.status,'failed');
  assert.equal(result.error,result.cleanupError);
});

test('a force-kill exception also cannot replace the primary engine error',async()=>{
  const server=serverDouble({close(){throw Error('close failure');},kill(){throw Error('kill failure');},forceThrow:true});
  const primary=Error('engine assertion'), result={status:'failed',error:primary.message};
  await cleanupVerification(server,result,primary);
  assert.equal(result.error,'engine assertion');
  assert.match(result.cleanupError,/force kill: fixture force kill failure/);
});

test('cleanup never signals an already exited browser process',async()=>{
  const server=serverDouble({close(){throw Error('close failure');},kill(){throw Error('kill failure');},exited:true});
  const result={status:'failed',error:'engine failure'};
  await cleanupVerification(server,result,Error(result.error));
  assert.deepEqual(server.calls,['process','close','kill']);
  assert.equal(result.status,'failed');
  assert.match(result.cleanupError,/kill failure/);
});

test('confirmed server/process close with pending profile cleanup preserves success and disconnects owned client',async()=>{
  const server=serverDouble({close(){server.finishClose();return never;}});
  let disconnected=false;
  const result={status:'passed'};
  await cleanupVerification(server,result,undefined,{closeMs:5,killMs:5,browser:{async close(){disconnected=true;}}});
  assert.equal(disconnected,true);
  assert.equal(result.status,'passed');assert.equal(result.cleanupError,undefined);
  assert.match(result.cleanupWarning,/Owned browser closed.*temporary-directory cleanup remains pending/);
  assert.deepEqual(server.calls,['process','close']);
});

test('server close observed before cleanup is retained; primary engine failure remains unchanged',async()=>{
  const server=trackBrowserServer(serverDouble({close:()=>never}));
  server.finishClose();
  const primary=Error('real engine fatal'),result={status:'failed',error:primary.message};
  await cleanupVerification(server,result,primary,{closeMs:5,killMs:5});
  assert.equal(result.error,primary.message);assert.equal(result.status,'failed');
  assert.equal(result.cleanupError,undefined);assert.ok(result.cleanupWarning);
});

test('kill can close the owned browser while its profile deletion promise remains pending',async()=>{
  const server=serverDouble({close:()=>never,kill(){server.finishClose();return never;}});
  const result={status:'passed'};
  await cleanupVerification(server,result,undefined,{closeMs:5,killMs:5});
  assert.equal(result.status,'passed');assert.match(result.cleanupWarning,/Browser kill timed out/);
  assert.deepEqual(server.calls,['process','close','kill']);
});

test('exitCode alone is not proof of server close; genuine cleanup errors stay fatal',async()=>{
  const server=serverDouble({exited:true,close:()=>never,kill:()=>never});
  const result={status:'passed'};
  await assert.rejects(cleanupVerification(server,result,undefined,{closeMs:5,killMs:5}),/Browser cleanup failed/);
  assert.equal(result.cleanupWarning,undefined);
  assert.deepEqual(server.calls,['process','close','kill']);
});

test('a disconnected-client failure is not mislabeled as delayed directory cleanup',async()=>{
  const server=serverDouble({close(){server.finishClose();return never;},kill:()=>never});
  const result={status:'passed'};
  await assert.rejects(cleanupVerification(server,result,undefined,{closeMs:5,killMs:5,
    browser:{close:()=>Promise.reject(Error('client disconnect failed'))}}),/client disconnect failed/);
  assert.equal(result.cleanupWarning,undefined);assert.equal(result.status,'failed');
});

test('real launchServer closure completes before delayed profile deletion; no browser or websocket orphan',async()=>{
  const {chromium}=await import('playwright');
  const server=trackBrowserServer(await chromium.launchServer({headless:true,
    ...(process.env.CHROME_CHANNEL?{channel:process.env.CHROME_CHANNEL}:{})}));
  let browser,release;
  const original=fs.promises.rm;
  const directory=server._userDataDirForTest; // Pinned Playwright test hook only.
  const gate=new Promise(resolve=>{release=resolve;});
  let held=false;
  try {
    assert.equal(typeof directory,'string');
    browser=await chromium.connect(server.wsEndpoint());
    const page=await browser.newPage();await page.setContent('<p>Cleanup fixture, no engine</p>');
    fs.promises.rm=async function(path,...args){
      if(path===directory){held=true;await gate;}
      return original.call(this,path,...args);
    };
    const result={status:'passed'};
    await cleanupVerification(server,result,undefined,{closeMs:1000,killMs:1000,browser});
    assert.equal(held,true);assert.equal(result.status,'passed');assert.ok(result.cleanupWarning);
    assert.equal(browser.isConnected(),false);assert.notEqual(server.process().exitCode,null);
    // Server's public /json endpoint must no longer accept connections.
    const url=new URL(server.wsEndpoint());url.protocol='http:';url.pathname='/json';
    await assert.rejects(fetch(url,{signal:AbortSignal.timeout(1000)}),/fetch failed/);
  } finally {
    fs.promises.rm=original;release();
    await server.close();await browser?.close();
  }
});
