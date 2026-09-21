// Focused native policy/format checks. These do not simulate PhysX or replace a native build.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const moduleRoot = new URL('../../../../Plugins/TournamentBridge/Source/TournamentBridge/', import.meta.url);
const helper = await readFile(new URL('Private/TournamentHTML5PhysicsReport.h', moduleRoot), 'utf8');
const controls = await readFile(new URL('Private/TournamentHTML5Controls.cpp', moduleRoot), 'utf8');
const build = await readFile(new URL('TournamentBridge.Build.cs', moduleRoot), 'utf8');
const portable = helper.slice(helper.indexOf('struct Admission'), helper.indexOf('// End portable policy/output code.'));
async function compileRun(source) {
  const dir = await mkdtemp(join(tmpdir(), 'ut4-physics-report-'));
  try {
    const file = join(dir, 'check.cpp'), binary = join(dir, 'check');
    await writeFile(file, source);
    const compiled = spawnSync('clang++', ['-std=c++11', '-Wall', '-Wextra', '-Werror', file, '-o', binary], { encoding: 'utf8' });
    assert.equal(compiled.status, 0, compiled.stderr || String(compiled.error));
    const ran = spawnSync(binary, [], { encoding: 'utf8' });
    assert.equal(ran.status, 0, ran.stderr || String(ran.error));
  } finally { await rm(dir, { recursive: true, force: true }); }
}
const prefix = `
#include <cassert>
#include <cmath>
#include <limits>
#include <cstring>
#include <cstdio>
#include <cstdarg>
#include <string>
struct FMath { static bool IsFinite(double x) { return std::isfinite(x); } };
`;

test('actual native admission rejects each gate, invalid epochs and exhausted budgets', async () => {
  await compileRun(prefix + portable + `
int main() {
 Admission ok={true,true,true,true,true,true,true,7,7};
 assert(Check(ok)==1);
 auto bad=ok; bad.GameThread=false; assert(Check(bad)==-1);
 bad=ok; bad.OptIn=false; assert(Check(bad)==-2);
 bad=ok; bad.Ready=false; assert(Check(bad)==0);
 bad=ok; bad.Standalone=false; assert(Check(bad)==-4);
 bad=ok; bad.NoNetwork=false; assert(Check(bad)==-4);
 bad=ok; bad.Deck=false; assert(Check(bad)==-5);
 bad=ok; bad.Scene=false; assert(Check(bad)==-5);
 const double invalid[]={0,-1,6,7.5,4294967296.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()};
 for(double x:invalid) { bad=ok; bad.ExpectedEpoch=x; assert(Check(bad)==-3); }
 bad=ok; bad.ActualEpoch=8; assert(Check(bad)==-3);
 Budget calls;
 for(int i=0;i<4;++i) assert(calls.Take(7));
 assert(!calls.Take(7)); assert(!calls.Take(7)); assert(calls.Count==4);
 // Only admitted requests reach Take; refused requests cannot reset its epoch.
 bad=ok; bad.ExpectedEpoch=8; assert(Check(bad)==-3); assert(calls.Epoch==7);
 assert(calls.Take(8)); assert(calls.Count==1);
 Output use(7,1,1); use.Add("test"); use.Finish(); assert(use.Count==2);
}
`);
});

test('actual native output is bounded ASCII with explicit truncation and an end record', async () => {
  await compileRun(prefix + portable + `
int main() {
 Admission a={true,true,true,true,true,true,true,1,1}; assert(Check(a)==1);
 Budget b; assert(b.Take(1));
 Output o(4294967295.0,4294967295.0,4);
 std::string longText(3000,'x'); longText[0]='\\n'; longText[1]='\\r'; longText[2]=char(255);
 o.Add("value=%s",longText.c_str());
 for(int i=0;i<100;++i) o.Add("row=%d",i);
 o.Finish();
 assert(o.Count==64 && o.Truncated);
 for(unsigned i=0;i<o.Count;++i) {
   assert(strlen(o.Lines[i])+1<=512); // includes puts newline
   assert(strncmp(o.Lines[i],"UT4PHYS v1 ",11)==0);
   for(const unsigned char* p=(const unsigned char*)o.Lines[i];*p;++p) assert(*p>=32 && *p<=126);
 }
 assert(strstr(o.Lines[63],"end rows=64 truncated=1"));
 Output clean(1,2,1); clean.Add("present=0"); clean.Finish();
 assert(clean.Count==2 && !clean.Truncated);
 assert(strstr(clean.Lines[1],"end rows=2 truncated=0"));
}
`);
});

test('production preprocessing omits helper and export; opt-in build fails closed on unsupported targets', () => {
  const gate = controls.slice(controls.indexOf('#ifndef TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS'), controls.lastIndexOf('#endif'));
  for (const defines of [[], ['-DWITH_PHYSX=1'], ['-DTOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS=1', '-DWITH_PHYSX=0']]) {
    const p = spawnSync('clang++', ['-E', '-P', '-x', 'c++', ...defines, '-'], { input: gate, encoding: 'utf8' });
    assert.equal(p.status, 0, p.stderr);
    assert.equal(p.stdout.trim(), '');
  }
  assert.match(build, /GetEnvironmentVariable\("TOURNAMENT_UT4_PHYSICS_REPORT"\) == "1"/);
  assert.match(build, /Target.Platform != UnrealTargetPlatform.HTML5/);
  assert.match(build, /Target.Configuration == UnrealTargetConfiguration.Shipping/);
  assert.match(build, /!UEBuildConfiguration.bCompilePhysX/);
  assert.match(build, /throw new BuildException/);
  assert.match(build, /if \(PhysicsReport\) PrivateDependencyModuleNames.Add\("PhysX"\)/);
  assert.match(build, /PhysicsReport \? "1" : "0"/);
});

test('actual scene-access guard never queries a disabled UE4.15 async scene', async () => {
  // Compile the exact function prefix through its guarded scene lookup. A disabled
  // async lookup deliberately asserts, matching the pinned engine contract.
  const start=helper.indexOf('static void ActorShapes');
  const guardedLookup=helper.slice(start,helper.indexOf('// Each actor is read',start));
  await compileRun(prefix + portable + `
namespace physx { struct PxScene {}; }
const int PST_Sync=0, PST_Async=2;
struct FBodyInstance {}; struct UBodySetup {};
struct FPhysScene {
 bool Async=false; int Lookups=0, Passed=0; physx::PxScene Scene;
 bool HasAsyncScene() const { return Async; }
 physx::PxScene* GetPhysXScene(int type) {
   assert(type!=PST_Async || Async); ++Lookups; return &Scene;
 }
};
` + guardedLookup + `
 (void)B; ++Physics->Passed;
}
int main() {
 Admission a={true,true,true,true,true,true,true,1,1}; assert(Check(a)==1);
 Output o(1,2,1); FPhysScene scene; FBodyInstance body;
 ActorShapes(o,&body,nullptr,&scene,PST_Async);
 assert(scene.Lookups==0 && scene.Passed==0);
 assert(o.Count==1 && strstr(o.Lines[0],"asyncEnabled=0 inspected=0"));
 ActorShapes(o,&body,nullptr,&scene,PST_Sync);
 assert(scene.Lookups==1 && scene.Passed==1);
 scene.Async=true;
 ActorShapes(o,&body,nullptr,&scene,PST_Async);
 assert(scene.Lookups==2 && scene.Passed==2);
 ActorShapes(o,nullptr,nullptr,&scene,PST_Async);
 assert(scene.Lookups==3 && scene.Passed==2);
 o.Finish();
}
`);
});

test('export enforces early thread/launch/readiness gates before inspecting the world and consuming budget', () => {
  const body=helper.slice(helper.indexOf('extern "C" EMSCRIPTEN_KEEPALIVE'));
  const order=['if (!IsInGameThread())','FParse::Param','if (!TournamentBrowserReady())','UWorld* World=BrowserWorld()',
    'GetWorldContextFromWorld','TournamentBrowserSessionEpoch()','const int Status=Check(A)','if (Status!=1) return Status',
    'Calls.Take(ActualEpoch)','Snapshot(O,World,BrowserPlayer())','O.Finish()','puts(O.Lines[I])'];
  let previous=-1;
  for(const text of order) { const offset=body.indexOf(text); assert.ok(offset>previous,text); previous=offset; }
  for(const condition of ['World->GetNetMode()==NM_Standalone','!Context->PendingNetGame','Context->ActiveNetDrivers.Num()==0',
    '!World->GetNetDriver()','World->PersistentLevel','/Game/RestrictedAssets/Maps/WIP/DM-DeckTest','World->GetPhysicsScene()!=nullptr']) assert.ok(body.includes(condition),condition);
});

test('report uses existing bodies, explicit per-scene read locks and bounded shape reads', () => {
  assert.doesNotMatch(helper, /(?:->|\.)\s*(?:GetBodySetup|CreatePhysicsMeshes|GetCookedData|UpdateBodySetup|CreateShapeBodySetupIfNeeded|RecreatePhysicsState|EnsureCollisionTreeIsBuilt|Set\w*|Invalidate\w*)\s*\(/);
  assert.doesNotMatch(helper, /\b(?:LoadObject|LoadPackage|NewObject|ExecuteOnPhysicsReadWrite|SCOPED_SCENE_WRITE_LOCK)\s*\(/);
  assert.match(helper, /Model \? Model->ModelBodySetup : nullptr/);
  const actors=helper.slice(helper.indexOf('static void ActorShapes'),helper.indexOf('static void Hit'));
  assert.ok(actors.indexOf('SCOPED_SCENE_READ_LOCK(Scene)')<actors.indexOf('GetPxRigidActor_AssumesLocked(SceneType)'));
  assert.match(actors, /getShapes\(Shapes, 8\)/);
  assert.match(helper, /ActorShapes\(O,BI,B,World->GetPhysicsScene\(\),PST_Sync\)/);
  assert.match(helper, /ActorShapes\(O,BI,B,World->GetPhysicsScene\(\),PST_Async\)/);
  assert.match(helper, /B->bCreatedPhysicsMeshes[\s\S]*B->TriMeshes.Num\(\)/);
});

test('exactly four native-matched floor queries ignore only the local pawn and player starts', () => {
  assert.match(helper, /const FVector Anchor\(4600.f,4670.f,633.2301025390625f\)/);
  assert.match(helper, /Top = Anchor\+FVector\(0,0,256\), Bottom = Anchor-FVector\(0,0,2048\)/);
  assert.match(helper, /for \(int Complex=0; Complex<2; \+\+Complex\)/);
  assert.equal((helper.match(/World->LineTraceMultiByChannel\(/g)||[]).length,1);
  assert.equal((helper.match(/World->SweepSingleByChannel\(/g)||[]).length,1);
  assert.match(helper, /LineTraceMultiByChannel\(Hits,Top,Bottom,ECC_Pawn,Q\)/);
  assert.match(helper, /SweepSingleByChannel\(Down,Anchor,Bottom,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule\(40.f,108.f\),Q\)/);
  assert.match(helper, /Q.bReturnFaceIndex=true/);
  assert.match(helper, /if \(Pawn\) Q.AddIgnoredActor\(Pawn\)/);
  assert.match(helper, /for \(APlayerStart\* Start : Starts\) Q.AddIgnoredActor\(Start\)/);
  assert.equal((helper.match(/Q.AddIgnoredActor\(/g)||[]).length,2);
  assert.match(helper, /ignorePawn=%d ignoreStarts=%d/);
});
