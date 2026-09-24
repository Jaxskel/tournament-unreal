// Classifier tests only: no browser, game, network, or generated source needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import { isFailureDiagnostic, startupOperation } from '../verify-runtime.mjs';
const ids = new Set(['fp /game.pak', 'datafile_F:/private/game.data']);
const context = {initializing:true, knownDependencyIds:ids};
const notices = ['[UT4] still waiting on run dependencies:', '[UT4] (end of list)', ...[...ids].map(id=>'[UT4] dependency: '+id)];

test('exact pinned inventory notices are opt-in and end at postRun',()=>{
  for(const text of notices){
    assert.equal(isFailureDiagnostic('error',text),true);
    assert.equal(isFailureDiagnostic('error',text,context),false);
    assert.equal(isFailureDiagnostic('error',text,{...context,initializing:false}),true);
  }
});
test('unknown IDs, whitespace, multiline, generic stderr and fatal diagnostics stay fatal',()=>{
  for(const text of [...notices.flatMap(t=>[t+'\n',t+' extra',t+'\r\n']), '[UT4] dependency: fp /unknown', '[UT4] warning: run dependency added without ID', '[UT4] Error loading package', 'LogEngine:Error: failed', 'RuntimeError: unreachable'])
    assert.equal(isFailureDiagnostic('error',text,context),true,text);
  for(const type of ['log','error']) assert.equal(isFailureDiagnostic(type,'[UT4] dependency: abort(',{...context,knownDependencyIds:new Set(['abort('])}),true);
});
test('missing/invalid inventory or nonboolean phase cannot authorize notices',()=>{
  for(const knownDependencyIds of [undefined,[],new Set(),new Set(['']),new Set(['x\ny']),new Set([3]),new Set(['x'.repeat(4097)]),new Set(Array.from({length:129},(_,i)=>String(i)))])
    assert.equal(isFailureDiagnostic('error',notices[0],{initializing:true,knownDependencyIds}),true);
  for(const initializing of [undefined,0,1,'true',false]) assert.equal(isFailureDiagnostic('error',notices[0],{...context,initializing}),true);
});
test('accepted progress does not make a non-ready operation succeed or extend its deadline',async()=>{
  const deadline=Date.now()+25;
  const timer=setInterval(()=>assert.equal(isFailureDiagnostic('error',notices[0],context),false),2);
  try { await assert.rejects(startupOperation(()=>new Promise(()=>{}),'postRun readiness',deadline,new Promise(()=>{})),/global startup deadline/); }
  finally {clearInterval(timer);}
});
