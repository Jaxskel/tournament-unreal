#include "TournamentBridgeMutator.h"
#include "TournamentBrowserStream.h"
#include "TournamentPlayerController.h"
#include "TournamentHUD.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"
#include "RenderingThread.h"
#include "RHICommandList.h"
#include "Interfaces/IImageWrapper.h"
#include "Interfaces/IImageWrapperModule.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "GameFramework/PlayerInput.h"

FTournamentBrowserStream::FTournamentBrowserStream(int32 InFramePort, int32 InInputPort)
    : Frames(nullptr), Input(nullptr), FramePort(InFramePort), InputPort(InInputPort), Sent(0),
      LastConnect(-10), LastCapture(0), LastInput(0), LastReconnect(0)
{
    // This destination comes only from the host's validated launcher, never
    // from browser messages. The controller can be destroyed during travel.
    FParse::Value(FCommandLine::Get(), TEXT("TournamentServer="), ServerDestination);
    if (!ServerDestination.IsEmpty())
    {
        const FURL URL(nullptr, *ServerDestination, TRAVEL_Absolute);
        if (!URL.Valid || !URL.IsInternal() || URL.Host.IsEmpty() || ServerDestination.Contains(TEXT("?")) || ServerDestination.Contains(TEXT("/"))) ServerDestination.Empty();
    }
    LastReconnect = FPlatformTime::Seconds();
    ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
    Input = Sockets->CreateSocket(NAME_DGram, TEXT("Tournament browser game input"), true);
    TSharedRef<FInternetAddr> Address = Sockets->CreateInternetAddr();
    bool Valid = false;
    Address->SetIp(TEXT("127.0.0.1"), Valid);
    Address->SetPort(InputPort);
    if (!Input || !Input->Bind(*Address))
    {
        UE_LOG(LogTemp, Error, TEXT("Tournament browser: cannot bind local input port %d"), InputPort);
        if (Input) { Sockets->DestroySocket(Input); Input = nullptr; }
        return;
    }
    Input->SetNonBlocking(true);
    UE_LOG(LogTemp, Log, TEXT("Tournament browser enabled: frames %d / input %d (loopback only)"), FramePort, InputPort);
}

FTournamentBrowserStream::~FTournamentBrowserStream()
{
    Release(LastController.Get());
    CloseFrames();
    if (Input) { Input->Close(); ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Input); }
}

void FTournamentBrowserStream::CloseFrames()
{
    if (Frames) { Frames->Close(); ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Frames); Frames = nullptr; }
    Pending.Empty();
    Sent = 0;
}

void FTournamentBrowserStream::Release(ATournamentPlayerController* PC)
{
    if (PC)
    {
        for (const FName& Key : Held) PC->InputKey(FKey(Key), IE_Released, 0, false);
        PC->ReleaseBrowserInput();
    }
    Held.Empty();
}

void FTournamentBrowserStream::ReadInput(ATournamentPlayerController* PC, float DeltaTime)
{
    if (!Input) return;
    uint32 Available = 0;
    int32 Packets = 0;
    while (Packets++ < 128 && Input->HasPendingData(Available))
    {
        uint8 Bytes[4097];
        int32 Received = 0;
        if (!Input->Recv(Bytes, 4096, Received) || Received <= 0) break;
        if (Available > 4096) continue;
        Bytes[Received] = 0;
        const FString Text(UTF8_TO_TCHAR(reinterpret_cast<const char*>(Bytes)));
        TSharedPtr<FJsonObject> Object;
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Object) || !Object.IsValid()) continue;
        FString Type;
        if (!Object->TryGetStringField(TEXT("type"), Type)) continue;
        if (Type == TEXT("heartbeat")) { LastInput = FPlatformTime::Seconds(); continue; }
        if (!PC) continue;
        if (Type == TEXT("reset")) { Release(PC); LastInput = FPlatformTime::Seconds(); continue; }
        if (Type == TEXT("menu-state"))
        {
            bool Open = false;
            if (!Object->TryGetBoolField(TEXT("open"), Open)) continue;
            Release(PC);
            if (Open) PC->ShowMenu(TEXT("")); else PC->HideMenu();
        }
        else if (Type == TEXT("key"))
        {
            FString Key;
            bool Down = false;
            if (!Object->TryGetStringField(TEXT("key"), Key) || !Object->TryGetBoolField(TEXT("down"), Down)) continue;
            static const TSet<FString> Allowed = { TEXT("W"), TEXT("A"), TEXT("S"), TEXT("D"), TEXT("SpaceBar"),
                TEXT("LeftShift"), TEXT("LeftControl"), TEXT("One"), TEXT("Two"), TEXT("Three"), TEXT("Four"),
                TEXT("Five"), TEXT("Six"), TEXT("Seven"), TEXT("Eight"), TEXT("Nine"), TEXT("Escape"), TEXT("Tab"),
                TEXT("Enter"), TEXT("LeftMouseButton"), TEXT("RightMouseButton") };
            if (!Allowed.Contains(Key)) continue;
            const FName Name(*Key);
            if (Down && !Held.Contains(Name)) { Held.Add(Name); PC->InputKey(FKey(Name), IE_Pressed, 1, false); }
            if (!Down) { Held.Remove(Name); PC->InputKey(FKey(Name), IE_Released, 0, false); }
        }
        else if (Type == TEXT("mouse"))
        {
            double DX = 0, DY = 0;
            if (!Object->TryGetNumberField(TEXT("dx"), DX) || !Object->TryGetNumberField(TEXT("dy"), DY)
                || !FMath::IsFinite(DX) || !FMath::IsFinite(DY)) continue;
            PC->InputAxis(EKeys::MouseX, FMath::Clamp(float(DX), -300.f, 300.f), DeltaTime, 1, false);
            PC->InputAxis(EKeys::MouseY, -FMath::Clamp(float(DY), -300.f, 300.f), DeltaTime, 1, false);
        }
        else if (Type == TEXT("menu"))
        {
            double X = 0, Y = 0;
            if (!Object->TryGetNumberField(TEXT("x"), X) || !Object->TryGetNumberField(TEXT("y"), Y)
                || !FMath::IsFinite(X) || !FMath::IsFinite(Y)) continue;
            ATournamentHUD* HUD = Cast<ATournamentHUD>(PC->GetHUD());
            if (HUD && GEngine->GameViewport && GEngine->GameViewport->Viewport)
            {
                const FIntPoint Size = GEngine->GameViewport->Viewport->GetSizeXY();
                HUD->ClickTournamentMenu(FMath::Clamp(float(X), 0.f, 1.f) * Size.X, FMath::Clamp(float(Y), 0.f, 1.f) * Size.Y);
            }
        }
        else continue;
        LastInput = FPlatformTime::Seconds();
    }
    if (PC && Held.Num() && FPlatformTime::Seconds() - LastInput > 3.0) Release(PC);
}

void FTournamentBrowserStream::PumpFrames()
{
    const double Now = FPlatformTime::Seconds();
    if (!Frames && Now - LastConnect > 1.0)
    {
        LastConnect = Now;
        ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
        TSharedRef<FInternetAddr> Address = Sockets->CreateInternetAddr();
        bool Valid = false; Address->SetIp(TEXT("127.0.0.1"), Valid); Address->SetPort(FramePort);
        Frames = Sockets->CreateSocket(NAME_Stream, TEXT("Tournament viewport frames"), false);
        if (!Frames || !Frames->Connect(*Address)) { CloseFrames(); return; }
        Frames->SetNonBlocking(true);
        UE_LOG(LogTemp, Log, TEXT("Tournament browser: framebuffer gateway connected"));
    }
    if (!Frames) return;
    if (Frames->GetConnectionState() != SCS_Connected) { CloseFrames(); return; }
    if (Pending.Num())
    {
        int32 Wrote = 0;
        if (Frames->Send(Pending.GetData() + Sent, Pending.Num() - Sent, Wrote)) Sent += Wrote;
        else if (ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->GetLastErrorCode() != SE_EWOULDBLOCK)
        {
            CloseFrames();
            return;
        }
        if (Sent >= Pending.Num()) { Pending.Empty(); Sent = 0; }
        else return;
    }
    if (Now - LastCapture < 1.0 / 24.0 || !GEngine || !GEngine->GameViewport || !GEngine->GameViewport->Viewport) return;
    LastCapture = Now;
    FViewport* Viewport = GEngine->GameViewport->Viewport;
    const FIntPoint Size = Viewport->GetSizeXY();
    if (Size.X < 1 || Size.Y < 1 || Size.X > 1920 || Size.Y > 1080) return;
    TArray<FColor> Pixels;
    const FViewportRHIRef RHIViewport = Viewport->GetViewportRHI();
    if (!RHIViewport.IsValid()) return;
    // Slate releases its scene-target reference after every frame. Read the
    // persistent game backbuffer, on the render thread, after prior drawing.
    ENQUEUE_UNIQUE_RENDER_COMMAND_THREEPARAMETER(
        TournamentReadGameBackbuffer,
        FViewportRHIRef, Target, RHIViewport,
        TArray<FColor>*, Output, &Pixels,
        FIntPoint, Dimensions, Size,
        {
            FTexture2DRHIRef Texture = RHICmdList.GetViewportBackBuffer(Target);
            if (Texture.IsValid()) RHICmdList.ReadSurfaceData(Texture,
                FIntRect(0, 0, Dimensions.X, Dimensions.Y), *Output, FReadSurfaceDataFlags(RCM_UNorm));
        });
    FlushRenderingCommands();
    if (Pixels.Num() != Size.X * Size.Y) return;
    IImageWrapperModule& Module = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    IImageWrapperPtr JPEG = Module.CreateImageWrapper(EImageFormat::JPEG);
    if (!JPEG.IsValid() || !JPEG->SetRaw(Pixels.GetData(), Pixels.Num() * sizeof(FColor), Size.X, Size.Y, ERGBFormat::BGRA, 8)) return;
    const TArray<uint8>& Encoded = JPEG->GetCompressed(65);
    if (!Encoded.Num() || Encoded.Num() > 4 * 1024 * 1024) return;
    const uint32 Length = uint32(Encoded.Num());
    Pending.SetNumUninitialized(Length + 4);
    Pending[0] = uint8(Length >> 24); Pending[1] = uint8(Length >> 16);
    Pending[2] = uint8(Length >> 8); Pending[3] = uint8(Length);
    FMemory::Memcpy(Pending.GetData() + 4, Encoded.GetData(), Length);
    Sent = 0;
}

bool FTournamentBrowserStream::Tick(float DeltaTime)
{
    UWorld* World = GEngine && GEngine->GameViewport ? GEngine->GameViewport->GetWorld() : nullptr;
    APlayerController* AnyController = World ? GEngine->GetFirstLocalPlayerController(World) : nullptr;
    ATournamentPlayerController* PC = Cast<ATournamentPlayerController>(AnyController);
    if (LastController.Get() != PC) { Release(LastController.Get()); LastController = PC; }
    if (PC && PC->PlayerState && NamedController.Get() != PC)
    {
        PC->ServerChangeName(FramePort == 9001 ? TEXT("Player One") : TEXT("Player Two"));
        NamedController = PC;
    }
    const double Now = FPlatformTime::Seconds();
    if (World && AnyController && World->GetNetMode() == NM_Standalone && !ServerDestination.IsEmpty()
        && Now - LastReconnect > 15.0)
    {
        const FWorldContext* Context = GEngine->GetWorldContextFromWorld(World);
        if (Context && !Context->PendingNetGame)
        {
            LastReconnect = Now;
            Release(PC);
            UE_LOG(LogTemp, Log, TEXT("Tournament browser: reconnecting to configured game server"));
            AnyController->ClientTravel(ServerDestination, TRAVEL_Absolute, false);
        }
    }
    ReadInput(PC, DeltaTime);
    // An entry menu is not a playable seat. Suppress its frames while the
    // configured multiplayer connection is recovering.
    if (PC && World && World->GetNetMode() == NM_Client) PumpFrames();
    else if (Frames) CloseFrames();
    return true;
}
