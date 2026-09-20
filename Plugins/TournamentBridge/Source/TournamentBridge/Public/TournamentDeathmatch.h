// Original Tournament code. Uses the UT game mode API without copying its implementation.
#pragma once

#include "TournamentBridgeMutator.h"
#include "UnrealTournament.h"
#include "UTDMGameMode.h"
#include "TournamentDeathmatch.generated.h"

UCLASS(Config=Game)
class TOURNAMENTBRIDGE_API ATournamentDeathmatch : public AUTDMGameMode
{
    GENERATED_BODY()

public:
    ATournamentDeathmatch(const FObjectInitializer& ObjectInitializer);
    virtual void TravelToNextMap_Implementation() override;

    // Server configuration only; full /Game package names, never URL options.
    UPROPERTY(Config)
    TArray<FString> ArenaRotation;
};
