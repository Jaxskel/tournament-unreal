// Original Tournament integration code.
#pragma once
#include "UnrealTournament.h"
#include "UTGameState.h"
#include "TournamentGameState.generated.h"

UCLASS()
class TOURNAMENTBRIDGE_API ATournamentGameState : public AUTGameState
{
    GENERATED_BODY()
public:
    virtual void UpdateHighlights_Implementation() override;
};
