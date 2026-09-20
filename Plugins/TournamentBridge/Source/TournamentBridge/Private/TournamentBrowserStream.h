#pragma once
#include "Core.h"
#include "Containers/Ticker.h"

class FSocket;
class ATournamentPlayerController;

// Captures this Unreal viewport only. Never captures or controls the desktop.
class FTournamentBrowserStream : public FTickerObjectBase
{
public:
    FTournamentBrowserStream(int32 InFramePort, int32 InInputPort);
    virtual ~FTournamentBrowserStream();
    virtual bool Tick(float DeltaTime) override;
private:
    FSocket* Frames;
    FSocket* Input;
    int32 FramePort;
    int32 InputPort;
    int32 Sent;
    double LastConnect;
    double LastCapture;
    double LastInput;
    double LastReconnect;
    FString ServerDestination;
    TArray<uint8> Pending;
    TSet<FName> Held;
    TWeakObjectPtr<ATournamentPlayerController> LastController;
    TWeakObjectPtr<ATournamentPlayerController> NamedController;
    void Release(ATournamentPlayerController* PC);
    void ReadInput(ATournamentPlayerController* PC, float DeltaTime);
    void PumpFrames();
    void CloseFrames();
};
