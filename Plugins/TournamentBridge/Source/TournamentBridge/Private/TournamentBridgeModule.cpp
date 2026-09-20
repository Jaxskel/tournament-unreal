// Original TournamentBridge code. No Epic implementation is included.
#include "TournamentBridgeMutator.h"
#include "Modules/ModuleManager.h"

class FTournamentBridgeModule : public IModuleInterface
{
public:
    virtual void StartupModule() override {}
    virtual void ShutdownModule() override {}
};

IMPLEMENT_MODULE(FTournamentBridgeModule, TournamentBridge)
