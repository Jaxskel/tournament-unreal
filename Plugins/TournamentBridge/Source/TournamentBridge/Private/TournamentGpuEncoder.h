#pragma once
#include "Core.h"
#include "RHI.h"

// Game-backbuffer-only encoding. Access exclusively from the render thread;
// teardown occurs after its last completed capture, never while it is in use.
class FTournamentGpuEncoder
{
public:
    FTournamentGpuEncoder();
    ~FTournamentGpuEncoder();
    bool Encode(FTexture2DRHIRef Texture, int32 FPS, TArray<uint8>& Packet, FString& Error);
private:
    struct FImpl;
    FImpl* Impl;
};
