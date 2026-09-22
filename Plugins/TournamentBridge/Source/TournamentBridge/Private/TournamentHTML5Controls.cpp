// Original bounded controls for the local-rendering browser client.
// No arbitrary console command, identity, score, or reward entry point.
#include "TournamentBridgeMutator.h"
#include "TournamentPlayerController.h"

#if PLATFORM_HTML5
#include "GameFramework/PlayerInput.h"
#include "UTGameUserSettings.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/WorldSettings.h"
#include "UnrealClient.h"
#include <emscripten/emscripten.h>

namespace {
UWorld* BrowserWorld()
{
    return GEngine && GEngine->GameViewport ? GEngine->GameViewport->GetWorld() : nullptr;
}
APlayerController* BrowserPlayer()
{
    UWorld* World = BrowserWorld();
    return World ? World->GetFirstPlayerController() : nullptr;
}
}

extern "C" {
EMSCRIPTEN_KEEPALIVE int TournamentBrowserReady()
{
    UWorld* World = BrowserWorld();
    // UT-Entry can tick while a multiplayer connection is pending. Only the
    // Tournament match controller establishes playable-world readiness.
    return World && World->HasBegunPlay() && Cast<ATournamentPlayerController>(BrowserPlayer())
        && GEngine->GameViewport->Viewport ? 1 : 0;
}

// A weak reference distinguishes replacement controllers even when allocator
// addresses are reused. The launcher can miss a short not-ready travel interval.
EMSCRIPTEN_KEEPALIVE double TournamentBrowserSessionEpoch()
{
    static TWeakObjectPtr<APlayerController> LastPlayer;
    static TWeakObjectPtr<UWorld> LastWorld;
    static uint32 Epoch = 0;
    if (!TournamentBrowserReady()) return 0;
    APlayerController* Player = BrowserPlayer();
    if (LastPlayer.Get() != Player || LastWorld.Get() != BrowserWorld())
    {
        LastPlayer = Player;
        LastWorld = BrowserWorld();
        ++Epoch;
        if (Epoch == 0) ++Epoch;
    }
    return static_cast<double>(Epoch);
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserSetResolution(int Width, int Height)
{
    if (!((Width == 1920 && Height == 1080) || (Width == 2560 && Height == 1440))) return 0;
    UWorld* World = BrowserWorld();
    if (!World) return 0;
    return GEngine->Exec(World, *FString::Printf(TEXT("r.SetRes %dx%dw"), Width, Height)) ? 1 : 0;
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserWidth()
{
    return GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport
        ? GEngine->GameViewport->Viewport->GetSizeXY().X : 0;
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserHeight()
{
    return GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport
        ? GEngine->GameViewport->Viewport->GetSizeXY().Y : 0;
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserSetSensitivity(double Value)
{
    if (!FMath::IsFinite(Value)) return 0;
    APlayerController* Player = BrowserPlayer();
    if (!Player || !Player->PlayerInput) return 0;
    Player->PlayerInput->SetMouseSensitivity(FMath::Clamp(static_cast<float>(Value), 0.005f, 0.5f));
    return 1;
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserSetVolume(double Value)
{
    if (!FMath::IsFinite(Value)) return 0;
    UUTGameUserSettings* Settings = GEngine ? Cast<UUTGameUserSettings>(GEngine->GetGameUserSettings()) : nullptr;
    if (!Settings) return 0;
    Settings->SetSoundClassVolume(EUTSoundClass::Master, FMath::Clamp(static_cast<float>(Value), 0.f, 1.f));
    return 1;
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserReleaseInput()
{
    APlayerController* Player = BrowserPlayer();
    if (!Player) return 0;
    ATournamentPlayerController* TournamentPlayer = Cast<ATournamentPlayerController>(Player);
    if (TournamentPlayer) TournamentPlayer->ReleaseBrowserInput();
    else
    {
        Player->InputKey(EKeys::LeftMouseButton, IE_Released, 0.f, false);
        Player->InputKey(EKeys::RightMouseButton, IE_Released, 0.f, false);
    }
    if (Player->PlayerInput) Player->PlayerInput->FlushPressedKeys();
    return 1;
}

EMSCRIPTEN_KEEPALIVE double TournamentBrowserFrame()
{
    return static_cast<double>(GFrameCounter);
}
}

namespace {
struct FBrowserMenuPause
{
    TWeakObjectPtr<UWorld> World;
    TWeakObjectPtr<APlayerController> Player;
    double Epoch = 0;
    bool Owns(APlayerController* PC, double E) const
    {
        return PC && World.Get() == PC->GetWorld() && Player.Get() == PC && Epoch == E;
    }
    void Clear() { World.Reset(); Player.Reset(); Epoch = 0; }
};
FBrowserMenuPause BrowserMenuPause;

APlayerController* MenuPausePlayer(double ExpectedEpoch)
{
    if (!IsInGameThread() || !FMath::IsFinite(ExpectedEpoch) || ExpectedEpoch <= 0 ||
        ExpectedEpoch > 4294967295.0 || !TournamentBrowserReady() ||
        ExpectedEpoch != TournamentBrowserSessionEpoch()) return nullptr;
    UWorld* World = BrowserWorld();
    APlayerController* PC = BrowserPlayer();
    const FWorldContext* Context = GEngine->GetWorldContextFromWorld(World);
    // UT also permits pausing an empty listen server. The browser control must
    // never inherit that permission or pause an in-progress network connection.
    if (!PC || !PC->IsLocalController() || !PC->PlayerState || PC->GetWorld() != World ||
        !World->GetWorldSettings() || !World->GetAuthGameMode() ||
        World->GetNetMode() != NM_Standalone || World->GetNetDriver() ||
        !Context || Context->PendingNetGame) return nullptr;
    return PC;
}
}

extern "C" {
// -1 unavailable/stale; 0 running; 1 menu-owned effective pause;
// 2 foreign/engine pause; 3 menu-owned pause awaiting UWorld's PauseDelay.
EMSCRIPTEN_KEEPALIVE int TournamentBrowserMenuPauseStatus(double ExpectedEpoch)
{
    APlayerController* PC = MenuPausePlayer(ExpectedEpoch);
    if (!PC) return -1;
    if (!PC->IsPaused()) return PC->GetWorld()->IsPaused() ? 2 : 0;
    if (!BrowserMenuPause.Owns(PC, ExpectedEpoch) ||
        PC->GetWorld()->GetWorldSettings()->Pauser != PC->PlayerState) return 2;
    return PC->GetWorld()->IsPaused() ? 1 : 3;
}

EMSCRIPTEN_KEEPALIVE int TournamentBrowserSetMenuPaused(int Paused, double ExpectedEpoch)
{
    if (Paused != 0 && Paused != 1) return 0;
    APlayerController* PC = MenuPausePlayer(ExpectedEpoch);
    if (!PC) return 0;
    const int Status = TournamentBrowserMenuPauseStatus(ExpectedEpoch);
    if (Paused)
    {
        // SetPause appends a delegate on every accepted call. Observe an owned
        // pending pause instead of adding duplicates, and never adopt a foreign one.
        if (Status == 1 || Status == 3) return Status == 1 ? 1 : 0;
        if (Status != 0) return 0;
        BrowserMenuPause.Clear();
        TournamentBrowserReleaseInput();
        if (!PC->SetPause(true)) return 0;
        BrowserMenuPause.World = PC->GetWorld();
        BrowserMenuPause.Player = PC;
        BrowserMenuPause.Epoch = ExpectedEpoch;
        return TournamentBrowserMenuPauseStatus(ExpectedEpoch) == 1 ? 1 : 0;
    }
    if (Status == 0)
    {
        BrowserMenuPause.Clear();
        return 1;
    }
    if (Status != 1 && Status != 3) return 0;
    TournamentBrowserReleaseInput();
    PC->SetPause(false);
    // ClearPause may report success after removing only one pause delegate.
    // The actual state, not its return value, confirms that gameplay can resume.
    if (PC->IsPaused() || PC->GetWorld()->IsPaused()) return 0;
    BrowserMenuPause.Clear();
    return 1;
}
}

#ifndef TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS
#define TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS 0
#endif
#if TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS && WITH_PHYSX
#include "TournamentHTML5PhysicsReport.h"
#endif
#endif
