// Original TournamentBridge code. No Epic implementation is included.
#include "TournamentBridgeMutator.h"
#include "Modules/ModuleManager.h"
#include "TournamentBrowserStream.h"

class FTournamentBridgeModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        int32 Frames = 0, Input = 0;
        if (FParse::Value(FCommandLine::Get(), TEXT("TournamentFramePort="), Frames)
            && FParse::Value(FCommandLine::Get(), TEXT("TournamentInputPort="), Input)
            && Frames >= 1024 && Frames <= 65535 && Input >= 1024 && Input <= 65535)
            Browser.Reset(new FTournamentBrowserStream(Frames, Input));
    }
    virtual void ShutdownModule() override { Browser.Reset(); }
private:
    TUniquePtr<FTournamentBrowserStream> Browser;
};

IMPLEMENT_MODULE(FTournamentBridgeModule, TournamentBridge)
