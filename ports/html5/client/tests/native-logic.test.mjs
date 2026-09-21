// Compiles the actual changed function bodies for both platform branches with
// small UE API test doubles. This is not a full UE build or gameplay validation.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const plugin = new URL('../../../../Plugins/TournamentBridge/Source/TournamentBridge/Private/', import.meta.url);
function body(source, signature) {
  const start=source.indexOf(signature);
  assert.ok(start>=0, 'Missing native function: '+signature);
  const opening=source.indexOf('{',start);
  let depth=0;
  for (let i=opening;i<source.length;i++) {
    if (source[i]==='{') depth++;
    if (source[i]==='}' && --depth===0) return source.slice(start,i+1);
  }
  throw new Error('Unterminated function: '+signature);
}

const stubs = String.raw`
#include <cassert>
#include <cmath>
#include <string>
#include <vector>
#include <algorithm>
#define TEXT(x) L##x
#define UE_SERVER 0
using int32=int;
struct FString {
  std::wstring Value;
  FString() {} FString(const wchar_t* v):Value(v) {} FString(std::wstring v):Value(v) {}
  int Len() const { return int(Value.size()); }
  FString Left(int n) const { return Value.substr(0,n); }
  void Empty() { Value.clear(); }
  void ReplaceInline(const wchar_t* from,const wchar_t* to) {
    size_t pos=0; while ((pos=Value.find(from,pos))!=std::wstring::npos) { Value.replace(pos,std::wstring(from).size(),to); pos+=std::wstring(to).size(); }
  }
  template<class... Args> static FString Printf(const wchar_t*,Args...) { return L"formatted"; }
};
FString operator+(const FString& a,const FString& b) { return a.Value+b.Value; }
template<class T> struct TArray:std::vector<T> { int Num() const { return int(this->size()); } };
struct FMath {
  template<class T> static T Clamp(T x,T lo,T hi) { return std::max(lo,std::min(hi,x)); }
  static int RoundToInt(float x) { return int(std::lround(x)); }
};
enum NetMode { NM_Standalone,NM_Client,NM_DedicatedServer };
struct World { bool HasGameMode=true; void* GetAuthGameMode() { return HasGameMode?this:nullptr; } };
struct ATournamentBridgeMutator {
  World* W=nullptr; bool Authority=true; NetMode Mode=NM_Standalone;
  World* GetWorld() const { return W; } bool HasAuthority() const { return Authority; }
  NetMode GetNetMode() const { return Mode; } bool CanObserve() const;
};
namespace EUTSoundClass { enum Type { Master }; }
namespace EWindowMode { enum Type { Windowed,WindowedFullscreen }; }
struct UUTGameUserSettings {
  int Applies=0,Saves=0,Confirms=0; float Volume=.5f; EWindowMode::Type Mode=EWindowMode::Windowed;
  float GetSoundClassVolume(EUTSoundClass::Type) { return Volume; }
  void SetSoundClassVolume(EUTSoundClass::Type,float v) { Volume=v; }
  EWindowMode::Type GetFullscreenMode() { return Mode; }
  void SetFullscreenMode(EWindowMode::Type m) { Mode=m; }
  void ApplyResolutionSettings(bool) { Applies++; } void ConfirmVideoMode() { Confirms++; }
  void SaveSettings() { Saves++; }
} UserSettings;
struct UFont {} Font;
struct Engine { UUTGameUserSettings* GetGameUserSettings() { return &UserSettings; } UFont* GetSmallFont() { return &Font; } } EngineInstance;
Engine* GEngine=&EngineInstance;
template<class T> T* Cast(T* v) { return v; }
bool Offscreen=false;
struct FParse { static bool Param(const wchar_t*,const wchar_t*) { return Offscreen; } };
struct FCommandLine { static const wchar_t* Get() { return L""; } };
struct Input { float Sensitivity=.05f; float GetMouseSensitivity() { return Sensitivity; } void SetMouseSensitivity(float v) { Sensitivity=v; } } PlayerInputInstance;
struct Profile { float MouseSensitivity=.05f; };
struct UUTLocalPlayer { Profile P; int Saves=0; Profile* GetProfileSettings() { return &P; } void SaveProfileSettings() { Saves++; } } LocalPlayer;
struct ATournamentPlayerController {
  int MenuPage=1; Input* PlayerInput=&PlayerInputInstance; TArray<FString> Diagnostics;
  int GetTournamentItemCount() const { return MenuPage==1?6:4; }
  bool CanTournamentReconnect() const { return false; } void* GetPawn() const { return nullptr; }
  UUTLocalPlayer* GetUTLocalPlayer() { return &LocalPlayer; }
  void GetTournamentDiagnostics(TArray<FString>& lines) { lines=Diagnostics; }
  FString GetTournamentItemLabel(int Index) const;
  bool IsTournamentItemEnabled(int Index) const;
  void AdjustSetting(int Index,int Direction);
};
struct FLinearColor {};
namespace TournamentPalette { const FLinearColor Text; }
float WidthOf(const FString& text,float scale) {
  float w=0; for (wchar_t c:text.Value) w+=c==L'W'?2.f:c==L'.'?.5f:1.f; return w*scale;
}
struct ATournamentHUD {
  int Measurements=0; TArray<FString> Drawn;
  void GetTextSize(const FString& text,float& w,float& h,UFont*,float scale) { Measurements++; w=WidthOf(text,scale); h=1; }
  void Label(const FString& text,float,float,float,const FLinearColor&) { Drawn.push_back(text); }
  void DrawTournamentDiagnostics(ATournamentPlayerController*,float,float,float,float);
};
`;

const checks = String.raw`
int main() {
  World world; ATournamentBridgeMutator mutator; mutator.W=&world;
  assert(mutator.CanObserve()==!PLATFORM_HTML5);
  mutator.Mode=NM_DedicatedServer; assert(mutator.CanObserve()==!PLATFORM_HTML5);
  mutator.Mode=NM_Client; assert(!mutator.CanObserve());
  mutator.Mode=NM_Standalone; mutator.Authority=false; assert(!mutator.CanObserve());
  mutator.Authority=true; world.HasGameMode=false; assert(!mutator.CanObserve());
  world.HasGameMode=true; mutator.W=nullptr; assert(!mutator.CanObserve());

  ATournamentPlayerController pc;
  assert(pc.IsTournamentItemEnabled(4)==!PLATFORM_HTML5);
  assert(pc.IsTournamentItemEnabled(3)); assert(!pc.IsTournamentItemEnabled(-1));
  assert(pc.GetTournamentItemLabel(4).Value==(PLATFORM_HTML5?L"FULLSCREEN: USE BROWSER TOOLBAR":L"TOGGLE WINDOW / FULLSCREEN"));
  pc.AdjustSetting(4,1);
  assert(UserSettings.Applies==!PLATFORM_HTML5);
  assert(UserSettings.Confirms==!PLATFORM_HTML5); assert(UserSettings.Saves==!PLATFORM_HTML5);
  Offscreen=true;
  assert(pc.GetTournamentItemLabel(4).Value==L"FULLSCREEN: USE BROWSER TOOLBAR");
  pc.AdjustSetting(4,1); assert(UserSettings.Applies==!PLATFORM_HTML5);
  int oldSaves=UserSettings.Saves;
  pc.AdjustSetting(3,1); assert(std::abs(UserSettings.Volume-.55f)<.0001f); assert(UserSettings.Saves==oldSaves+1);
  pc.AdjustSetting(1,1); assert(std::abs(PlayerInputInstance.Sensitivity-.055f)<.0001f);
  assert(LocalPlayer.Saves==1); assert(LocalPlayer.P.MouseSensitivity==PlayerInputInstance.Sensitivity);

  for (const std::wstring& input:std::vector<std::wstring>{L"short",L"line\nwith\rcontrols",std::wstring(256,L'W'),std::wstring(400,L'a'),L""}) {
    for (float scale: { .25f,1.f,2.f }) for (float width: { 0.f,.2f,1.f,3.f,10.f,80.f,300.f,2000.f }) {
      ATournamentHUD hud; pc.Diagnostics.clear(); pc.Diagnostics.push_back(FString(input));
      hud.DrawTournamentDiagnostics(&pc,0,0,width,scale);
      assert(hud.Drawn.Num()==1); assert(hud.Measurements<=10);
      FString text(input.substr(0,256)); text.ReplaceInline(L"\n",L" "); text.ReplaceInline(L"\r",L" ");
      const float fontScale=.95f*scale;
      FString expected=text;
      if (WidthOf(text,fontScale)>width) {
        expected.Empty();
        // Independent exhaustive reference: longest fitting prefix plus suffix.
        for (int n=0;n<text.Len();n++) {
          const FString candidate=text.Left(n)+FString(L"...");
          if (WidthOf(candidate,fontScale)<=width) expected=candidate;
        }
      }
      assert(hud.Drawn[0].Value==expected.Value);
      assert(WidthOf(hud.Drawn[0],fontScale)<=width);
    }
  }
}
`;

test('native and HTML5 guards plus bounded HUD truncation execute from actual C++ bodies', async t => {
  const compiler=process.env.CXX || 'c++';
  if (spawnSync(compiler,['--version']).error) { t.skip('C++ compiler unavailable; native branch harness not run'); return; }
  const [mutator,controller,hud]=await Promise.all(['TournamentBridgeMutator.cpp','TournamentPlayerController.cpp','TournamentHUD.cpp'].map(name=>readFile(new URL(name,plugin),'utf8')));
  const source=stubs+'\n'+[
    body(mutator,'bool ATournamentBridgeMutator::CanObserve() const'),
    body(controller,'FString ATournamentPlayerController::GetTournamentItemLabel(int32 Index) const'),
    body(controller,'bool ATournamentPlayerController::IsTournamentItemEnabled(int32 Index) const'),
    body(controller,'void ATournamentPlayerController::AdjustSetting(int32 Index, int32 Direction)'),
    body(hud,'void ATournamentHUD::DrawTournamentDiagnostics(')
  ].join('\n')+'\n'+checks;
  const results=fileURLToPath(new URL('../test-results/',import.meta.url));
  await mkdir(results,{ recursive:true });
  const directory=await mkdtemp(join(results,'native-logic-'));
  t.after(()=>rm(directory,{ recursive:true,force:true }));
  for (const platform of [0,1]) {
    const executable=join(directory,'check-'+platform+(process.platform==='win32'?'.exe':''));
    const compile=spawnSync(compiler,['-std=c++11','-x','c++','-DPLATFORM_HTML5='+platform,'-o',executable,'-'],{ input:source,encoding:'utf8' });
    assert.equal(compile.status,0,compile.stderr);
    const run=spawnSync(executable,[],{ encoding:'utf8' });
    assert.equal(run.status,0,run.stderr);
  }
});

test('actual BrowserReady rejects generic entry controllers and requires a begun Tournament world with viewport', async t => {
  const compiler=process.env.CXX || 'c++';
  if (spawnSync(compiler,['--version']).error) { t.skip('C++ compiler unavailable; readiness body not run'); return; }
  const controls=await readFile(new URL('TournamentHTML5Controls.cpp',plugin),'utf8');
  // Use actual production helper/Ready bodies. Doubles model only object state
  // and polymorphic cast behavior, not the readiness predicate. This is not UE gameplay.
  const source=String.raw`
#include <cassert>
struct APlayerController { virtual ~APlayerController() {} };
struct ATournamentPlayerController : APlayerController {};
struct DerivedTournamentController : ATournamentPlayerController {};
struct GenericEntryController : APlayerController {};
template<class T> T* Cast(APlayerController* player) { return dynamic_cast<T*>(player); }
struct UWorld {
  bool Begun=false;
  APlayerController* Player=nullptr;
  bool HasBegunPlay() const { return Begun; }
  APlayerController* GetFirstPlayerController() { return Player; }
};
struct FViewport {};
struct UGameViewportClient {
  UWorld* World=nullptr;
  FViewport* Viewport=nullptr;
  UWorld* GetWorld() { return World; }
};
struct UEngine { UGameViewportClient* GameViewport=nullptr; };
UEngine* GEngine=nullptr;
`+[
    body(controls,'UWorld* BrowserWorld()'),
    body(controls,'APlayerController* BrowserPlayer()'),
    body(controls,'int TournamentBrowserReady()')
  ].join('\n')+String.raw`
int main() {
  assert(TournamentBrowserReady()==0); // No engine.
  UEngine engine; GEngine=&engine;
  assert(TournamentBrowserReady()==0); // No viewport client.
  UGameViewportClient client; engine.GameViewport=&client;
  FViewport viewport; client.Viewport=&viewport;
  assert(TournamentBrowserReady()==0); // No world, despite a viewport.
  UWorld world; client.World=&world;
  ATournamentPlayerController matchPlayer; world.Player=&matchPlayer;
  assert(TournamentBrowserReady()==0); // Match controller before BeginPlay.
  world.Begun=true;
  assert(TournamentBrowserReady()==1); // Tournament match controller.
  APlayerController genericPlayer; world.Player=&genericPlayer;
  assert(TournamentBrowserReady()==0); // Ticking entry/pending connection must not pass.
  GenericEntryController entryPlayer; world.Player=&entryPlayer;
  assert(TournamentBrowserReady()==0); // Unrelated controller subclass also rejected.
  world.Player=nullptr;
  assert(TournamentBrowserReady()==0);
  DerivedTournamentController derivedPlayer; world.Player=&derivedPlayer;
  assert(TournamentBrowserReady()==1); // Preserve legitimate Tournament subclasses.
  client.Viewport=nullptr;
  assert(TournamentBrowserReady()==0); // Correct world/controller without render viewport.
  client.Viewport=&viewport;
  assert(TournamentBrowserReady()==1);
  client.World=nullptr;
  assert(TournamentBrowserReady()==0); // World teardown after a previously ready state.
}
`;
  const results=fileURLToPath(new URL('../test-results/',import.meta.url));
  await mkdir(results,{ recursive:true });
  const directory=await mkdtemp(join(results,'native-ready-'));
  t.after(()=>rm(directory,{ recursive:true,force:true }));
  const executable=join(directory,'check-ready'+(process.platform==='win32'?'.exe':''));
  const compile=spawnSync(compiler,['-std=c++11','-x','c++','-o',executable,'-'],{ input:source,encoding:'utf8',timeout:30000 });
  assert.equal(compile.status,0,compile.stderr || compile.error?.message);
  const run=spawnSync(executable,[],{ encoding:'utf8',timeout:5000 });
  assert.equal(run.status,0,run.stderr || run.error?.message);
});
