#include "TournamentBridgeMutator.h"
#include "TournamentPlayerController.h"
#include "TournamentHUD.h"
#include "GameFramework/PlayerInput.h"
#include "Engine/NetDriver.h"
#include "Engine/NetConnection.h"

ATournamentPlayerController::ATournamentPlayerController(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer), bTournamentMenuOpen(false), bPreviousCursor(false), MenuPage(0), MenuSelection(0)
{
}

void ATournamentPlayerController::ShowMenu(const FString& Parameters)
{
    if (!IsLocalController() || bTournamentMenuOpen) return;
    // Leave stock dialogs alone. They manage their own focus and close behavior.
    UUTLocalPlayer* LP = GetUTLocalPlayer();
    if (LP && LP->AreMenusOpen())
    {
        if (FParse::Param(FCommandLine::Get(), TEXT("TournamentOffscreen"))) LP->CloseAllUI();
        else { Super::ShowMenu(Parameters); return; }
    }
    ToggleScoreboard(false);
    OnStopFire();
    OnStopAltFire();
    if (PlayerInput) PlayerInput->FlushPressedKeys();
    bPreviousCursor = bShowMouseCursor;
    bTournamentMenuOpen = true;
    MenuPage = MenuSelection = 0;
    SetIgnoreMoveInput(true);
    SetIgnoreLookInput(true);
    bShowMouseCursor = true;
    FInputModeGameAndUI Mode;
    Mode.SetHideCursorDuringCapture(false);
    SetInputMode(Mode);
}

void ATournamentPlayerController::HideMenu()
{
    if (!bTournamentMenuOpen) { Super::HideMenu(); return; }
    bTournamentMenuOpen = false;
    MenuPage = MenuSelection = 0;
    if (PlayerInput) PlayerInput->FlushPressedKeys();
    SetIgnoreMoveInput(false);
    SetIgnoreLookInput(false);
    bShowMouseCursor = bPreviousCursor;
    SetInputMode(FInputModeGameOnly());
}

void ATournamentPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (bTournamentMenuOpen) HideMenu();
    Super::EndPlay(EndPlayReason);
}

void ATournamentPlayerController::ReleaseBrowserInput()
{
    OnStopFire();
    OnStopAltFire();
    if (PlayerInput) PlayerInput->FlushPressedKeys();
}

bool ATournamentPlayerController::InputKey(FKey Key, EInputEvent EventType, float AmountDepressed, bool bGamepad)
{
    const FName Name = Key.GetFName();
    if (Name == FName(TEXT("Escape")))
    {
        if (EventType == IE_Pressed)
        {
            UUTLocalPlayer* LP = GetUTLocalPlayer();
            if (!bTournamentMenuOpen && LP && LP->AreMenusOpen())
                return Super::InputKey(Key, EventType, AmountDepressed, bGamepad);
            if (bTournamentMenuOpen) HideMenu(); else ShowMenu(TEXT(""));
        }
        return true;
    }
    if (!bTournamentMenuOpen) return Super::InputKey(Key, EventType, AmountDepressed, bGamepad);
    if (EventType == IE_Pressed)
    {
        if (Name == FName(TEXT("Up"))) SelectTournamentItem(MenuSelection - 1);
        else if (Name == FName(TEXT("Down")) || Name == FName(TEXT("Tab"))) SelectTournamentItem(MenuSelection + 1);
        else if (Name == FName(TEXT("Enter")) || Name == FName(TEXT("SpaceBar"))) ActivateTournamentItem(MenuSelection);
        else if (Name == FName(TEXT("Left")) && MenuPage == 1) AdjustSetting(MenuSelection, -1);
        else if (Name == FName(TEXT("Right")) && MenuPage == 1) AdjustSetting(MenuSelection, 1);
        else if (Name == FName(TEXT("LeftMouseButton")))
        {
            float X, Y;
            ATournamentHUD* HUD = Cast<ATournamentHUD>(GetHUD());
            if (HUD && GetMousePosition(X, Y)) HUD->ClickTournamentMenu(X, Y);
        }
    }
    // Consume releases as well: closing a menu must never discharge a weapon.
    return true;
}

bool ATournamentPlayerController::InputAxis(FKey Key, float Delta, float DeltaTime, int32 NumSamples, bool bGamepad)
{
    return bTournamentMenuOpen ? true : Super::InputAxis(Key, Delta, DeltaTime, NumSamples, bGamepad);
}

int32 ATournamentPlayerController::GetTournamentItemCount() const { return MenuPage == 0 ? 4 : MenuPage == 1 ? 6 : MenuPage == 3 ? 2 : 1; }
void ATournamentPlayerController::SelectTournamentItem(int32 Index)
{
    const int32 Count = GetTournamentItemCount();
    const int32 Direction = Index < MenuSelection ? -1 : 1;
    MenuSelection = (Index % Count + Count) % Count;
    for (int32 Attempt = 0; Attempt < Count && !IsTournamentItemEnabled(MenuSelection); ++Attempt)
        MenuSelection = (MenuSelection + Direction + Count) % Count;
}

FString ATournamentPlayerController::GetTournamentItemLabel(int32 Index) const
{
    if (MenuPage == 0)
    {
        if (Index == 0) return GetPawn() ? TEXT("RESUME GAME") : TEXT("PLAY / RESPAWN");
        return Index == 1 ? TEXT("SETTINGS") : Index == 2 ? TEXT("GAME MODE") : TEXT("DIAGNOSTICS");
    }
    if (MenuPage == 2) return TEXT("BACK");
    if (MenuPage == 3) return Index == 0
        ? (CanTournamentReconnect() ? TEXT("RECONNECT TO THIS SERVER") : TEXT("RECONNECT UNAVAILABLE - REMOTE CLIENTS ONLY"))
        : TEXT("BACK");
    if (Index < 2)
        return FString::Printf(TEXT("MOUSE SENSITIVITY  %.3f   %s"), PlayerInput ? PlayerInput->GetMouseSensitivity() : 0.05f, Index == 0 ? TEXT("[-]") : TEXT("[+]"));
    UUTGameUserSettings* Settings = GEngine ? Cast<UUTGameUserSettings>(GEngine->GetGameUserSettings()) : nullptr;
    if (Index < 4)
        return FString::Printf(TEXT("MASTER VOLUME  %d%%   %s"), Settings ? FMath::RoundToInt(100.f * Settings->GetSoundClassVolume(EUTSoundClass::Master)) : 0, Index == 2 ? TEXT("[-]") : TEXT("[+]"));
    if (Index == 4)
    {
#if PLATFORM_HTML5
        return TEXT("FULLSCREEN: USE BROWSER TOOLBAR");
#else
        return FParse::Param(FCommandLine::Get(), TEXT("TournamentOffscreen"))
            ? TEXT("FULLSCREEN: USE BROWSER TOOLBAR") : TEXT("TOGGLE WINDOW / FULLSCREEN");
#endif
    }
    return TEXT("BACK");
}

void ATournamentPlayerController::ActivateTournamentItem(int32 Index)
{
    if (!bTournamentMenuOpen || !IsTournamentItemEnabled(Index)) return;
    if (MenuPage == 0)
    {
        if (Index == 0)
        {
            HideMenu();
            // A normal restart request; the server decides whether spawning is allowed.
            if (!GetPawn() && PlayerState && !PlayerState->bOnlySpectator) ServerRestartPlayer();
        }
        else
        {
            MenuPage = Index;
            MenuSelection = 0;
            if (!IsTournamentItemEnabled(MenuSelection)) SelectTournamentItem(1);
        }
    }
    else if (MenuPage == 3)
    {
        if (Index == 0)
        {
            // UE4.15 UnrealEngine.cpp::HandleReconnectCommand uses LastRemoteURL
            // verbatim. URL.cpp::FURL::ToString serializes Host, Port and every Op
            // (including Name). Never rebuild it from the display-only endpoint.
            const FWorldContext* Context = GEngine->GetWorldContextFromWorld(GetWorld());
            const FString Destination = Context->LastRemoteURL.ToString();
            HideMenu();
            // PlayerController.cpp::ClientTravelInternal_Implementation invokes
            // PreClientTravel, then SetClientTravel for non-seamless absolute travel.
            ClientTravel(Destination, TRAVEL_Absolute, false);
        }
        else { MenuPage = MenuSelection = 0; }
    }
    else if (MenuPage == 2 || Index == 5) { MenuPage = MenuSelection = 0; }
    else AdjustSetting(Index, Index == 0 || Index == 2 ? -1 : 1);
}

bool ATournamentPlayerController::CanTournamentReconnect() const
{
    // A previous remote URL can survive a return to local practice. Net mode must
    // still be client, or reconnect could unexpectedly leave a standalone match.
    const UWorld* World = GetWorld();
    if (!IsLocalController() || !World || World->GetNetMode() != NM_Client || !GEngine) return false;
    const UNetDriver* Driver = World->GetNetDriver();
    const FWorldContext* Context = GEngine->GetWorldContextFromWorld(World);
    return Driver && Driver->ServerConnection && Context
        && Context->LastRemoteURL.Valid && !Context->LastRemoteURL.Host.IsEmpty()
        && Context->LastRemoteURL.IsInternal();
}

bool ATournamentPlayerController::IsTournamentItemEnabled(int32 Index) const
{
#if PLATFORM_HTML5
    if (MenuPage == 1 && Index == 4) return false;
#endif
    return Index >= 0 && Index < GetTournamentItemCount()
        && (MenuPage != 3 || Index != 0 || CanTournamentReconnect());
}

void ATournamentPlayerController::GetTournamentDiagnostics(TArray<FString>& Lines) const
{
    Lines.Reset();
    const UWorld* World = GetWorld();
    if (!World) { Lines.Add(TEXT("World: unavailable")); return; }
    const AUTGameState* GS = World->GetGameState<AUTGameState>();
    Lines.Add(FString(TEXT("Map: ")) + World->GetMapName());
    Lines.Add(FString(TEXT("Match: ")) + (GS ? GS->GetMatchState().ToString() : TEXT("awaiting game state")));
    const ENetMode Mode = World->GetNetMode();
    const TCHAR* RoleLabel = Mode == NM_Client ? TEXT("remote client") : Mode == NM_ListenServer ? TEXT("listen server / host")
        : Mode == NM_DedicatedServer ? TEXT("dedicated server") : TEXT("local practice / standalone");
    Lines.Add(FString(TEXT("Role: ")) + RoleLabel + (PlayerState && PlayerState->bOnlySpectator ? TEXT(" / spectator") : TEXT("")));
    const UNetDriver* Driver = World->GetNetDriver();
    const UNetConnection* Connection = Driver ? Driver->ServerConnection : nullptr;
    if (Mode == NM_Client && Connection)
    {
        const TCHAR* State = Connection->State == USOCK_Open ? TEXT("open") : Connection->State == USOCK_Pending ? TEXT("pending")
            : Connection->State == USOCK_Closed ? TEXT("closed") : TEXT("invalid");
        Lines.Add(FString(TEXT("Connection: ")) + State);
        // Show the endpoint only. Never display credentials or other URL options.
        const FWorldContext* Context = GEngine ? GEngine->GetWorldContextFromWorld(World) : nullptr;
        Lines.Add(Context && Context->LastRemoteURL.Valid
            ? FString::Printf(TEXT("Server: %s:%d"), *Context->LastRemoteURL.Host, Context->LastRemoteURL.Port)
            : TEXT("Server: unavailable"));
        // PlayerState.h documents replicated Ping as milliseconds divided by four.
        Lines.Add(PlayerState && PlayerState->Ping > 0
            ? FString::Printf(TEXT("Ping: ~%d ms (replicated estimate)"), int32(PlayerState->Ping) * 4)
            : TEXT("Ping: not yet available"));
    }
    else
    {
        Lines.Add(Mode == NM_Client ? TEXT("Connection: unavailable") : Mode == NM_Standalone
            ? TEXT("Connection: offline - no remote server") : TEXT("Connection: hosting - no upstream server"));
        Lines.Add(TEXT("Ping: not applicable / unavailable"));
    }
    Lines.Add(TEXT("Platform rewards: DISABLED (demo)"));
}

void ATournamentPlayerController::AdjustSetting(int32 Index, int32 Direction)
{
    if (Index < 2 && PlayerInput)
    {
        const float Sensitivity = FMath::Clamp(PlayerInput->GetMouseSensitivity() + Direction * 0.005f, 0.005f, 0.5f);
        PlayerInput->SetMouseSensitivity(Sensitivity);
#if !UE_SERVER
        UUTLocalPlayer* LP = GetUTLocalPlayer();
        if (LP && LP->GetProfileSettings())
        {
            LP->GetProfileSettings()->MouseSensitivity = Sensitivity;
            // Public UE4.15 API: always saves the local profile; stock UT also
            // syncs it to Epic when already logged in. No sign-in is initiated.
            LP->SaveProfileSettings();
        }
#endif
        return;
    }
    UUTGameUserSettings* Settings = GEngine ? Cast<UUTGameUserSettings>(GEngine->GetGameUserSettings()) : nullptr;
    if (!Settings) return;
    if (Index == 2 || Index == 3)
    {
        Settings->SetSoundClassVolume(EUTSoundClass::Master, FMath::Clamp(Settings->GetSoundClassVolume(EUTSoundClass::Master) + Direction * 0.05f, 0.f, 1.f));
        Settings->SaveSettings();
    }
    else if (Index == 4)
    {
#if PLATFORM_HTML5
        // Browser fullscreen and fixed render resolution belong to the launcher.
        // Guard the action too: settings arrows can call it without activation.
        return;
#else
        // Browser fullscreen belongs to the web player; keep the native stream size fixed.
        if (FParse::Param(FCommandLine::Get(), TEXT("TournamentOffscreen"))) return;
        Settings->SetFullscreenMode(Settings->GetFullscreenMode() == EWindowMode::Windowed ? EWindowMode::WindowedFullscreen : EWindowMode::Windowed);
        Settings->ApplyResolutionSettings(false);
        Settings->ConfirmVideoMode();
        Settings->SaveSettings();
#endif
    }
}
