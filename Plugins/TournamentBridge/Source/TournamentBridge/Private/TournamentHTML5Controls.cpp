// Original bounded controls for the local-rendering browser client.
// No arbitrary console command, identity, score, or reward entry point.
#include "TournamentBridgeMutator.h"
#include "TournamentPlayerController.h"

#if PLATFORM_HTML5
#include "GameFramework/PlayerInput.h"
#include "UTGameUserSettings.h"
#include "Engine/GameViewportClient.h"
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
    static uint32 Epoch = 0;
    if (!TournamentBrowserReady()) return 0;
    APlayerController* Player = BrowserPlayer();
    if (LastPlayer.Get() != Player)
    {
        LastPlayer = Player;
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

#ifndef TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS
#define TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS 0
#endif
#if TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS && WITH_PHYSX
#include "TournamentHTML5PhysicsReport.h"
#endif
#endif
