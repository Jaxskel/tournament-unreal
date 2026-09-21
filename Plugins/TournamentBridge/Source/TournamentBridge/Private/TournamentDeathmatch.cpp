#include "TournamentBridgeMutator.h"
#include "TournamentDeathmatch.h"
#include "TournamentHUD.h"
#include "TournamentGameState.h"
#include "TournamentPlayerController.h"
#include "Misc/PackageName.h"
#include "UTRecastNavMesh.h"

ATournamentDeathmatch::ATournamentDeathmatch(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    bDisableMapVote = true;
    HUDClass = ATournamentHUD::StaticClass();
    GameStateClass = ATournamentGameState::StaticClass();
    PlayerControllerClass = ATournamentPlayerController::StaticClass();
    BotFillCount = 7;
    ArenaRotation.Add(TEXT("/Game/RestrictedAssets/Maps/WIP/DM-DeckTest"));
    ArenaRotation.Add(TEXT("/Game/RestrictedAssets/Maps/DM-Outpost23"));
}

void ATournamentDeathmatch::TravelToNextMap_Implementation()
{
    if (!HasAuthority() || !GetWorld())
    {
        return;
    }

    TArray<FString> ValidMaps;
    for (const FString& Map : ArenaRotation)
    {
        if (Map.StartsWith(TEXT("/Game/")) && FPackageName::IsValidLongPackageName(Map)
            && FPackageName::DoesPackageExist(Map))
        {
            ValidMaps.AddUnique(Map);
        }
        else
        {
            UE_LOG(LogTemp, Error, TEXT("Tournament: invalid or missing rotation map: %s"), *Map);
        }
    }

    if (ValidMaps.Num() == 0)
    {
        UE_LOG(LogTemp, Error, TEXT("Tournament: no valid rotation maps; staying on the result screen."));
        return;
    }

    const FString CurrentMap = GetWorld()->GetOutermost()->GetName();
    const int32 CurrentIndex = ValidMaps.IndexOfByKey(CurrentMap);
    const FString& NextMap = ValidMaps[(CurrentIndex + 1) % ValidMaps.Num()];
    UE_LOG(LogTemp, Log, TEXT("Tournament: rotating from %s to %s"), *CurrentMap, *NextMap);
    // Relative travel keeps this game's options, including the telemetry mutator.
    if (!GetWorld()->ServerTravel(NextMap, false))
    {
        UE_LOG(LogTemp, Error, TEXT("Tournament: travel request failed for %s"), *NextMap);
    }
}

void ATournamentDeathmatch::HandleMatchHasEnded()
{
    // Use a short scoreboard interval instead of the stock character ceremony.
    // Keep the engine session lifecycle and bot learning, and use Tournament's
    // scoreboard during the result interval instead of spawning that ceremony.
    AGameMode::HandleMatchHasEnded();
    AUTRecastNavMesh* NavData = GetUTNavData(GetWorld());
    if (NavData)
    {
        NavData->SaveMapLearningData();
    }
    UE_LOG(LogTemp, Log, TEXT("Tournament: round complete; scoreboard then automatic rotation."));
}

float ATournamentDeathmatch::GetTravelDelay()
{
    return 12.0f;
}
