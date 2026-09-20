// Original TournamentBridge code. No Epic implementation is included.
#pragma once

#include "Core.h"
#include "Engine.h"

class AUTPlayerController;
class AUTInventory;
class AUTWeapon;
class AUTCharacter;
class AUTPlayerState;
class AUTCarriedObject;
class FJsonObject;

#include "UTMutator.h"
#include "TournamentBridgeMutator.generated.h"

USTRUCT()
struct FTournamentDamagePoints
{
    GENERATED_USTRUCT_BODY()

    UPROPERTY()
    FString DamageTypeClass;

    UPROPERTY()
    int32 Points;

    FTournamentDamagePoints() : Points(0) {}
};

// Ephemeral identities refer only to PlayerState instances in this match.
struct FTournamentParticipant
{
    TWeakObjectPtr<APlayerState> State;
    FString Id;
    FString Name;
    float VanillaScore = 0.0f;
    int64 PracticePoints = 0;
    int32 ObservedFrags = 0;
    int32 ObservedDeaths = 0;
    int32 Team = 255;
    bool bBot = false;
    bool bConnected = true;
    bool bSpectator = false;
};

UCLASS(Config = Game, NotBlueprintable)
class TOURNAMENTBRIDGE_API ATournamentBridgeMutator : public AUTMutator
{
    GENERATED_UCLASS_BODY()

public:
    // Exact full class path takes precedence over an exact short class name.
    UPROPERTY(Config)
    TArray<FTournamentDamagePoints> DamageTypePoints;

    UPROPERTY(Config)
    int32 DefaultKillPoints;

    // Zero disables this observational race; never changes the UT score limit.
    UPROPERTY(Config)
    int32 FragRaceTarget;

    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void ScoreKill_Implementation(AController* Killer, AController* Other,
        TSubclassOf<UDamageType> DamageType) override;
    virtual void NotifyMatchStateChange_Implementation(FName NewState) override;
    virtual void NotifyLogout_Implementation(AController* C) override;

private:
    bool CanObserve() const;
    void ObserveState(FName State);
    void StartObservedMatch();
    void FinishObservedMatch();
    int32 TouchParticipant(APlayerState* State);
    void RefreshRoster();
    TSharedRef<FJsonObject> ParticipantJson(int32 Index) const;
    int32 PointsFor(UClass* DamageClass) const;
    void Emit(const TCHAR* Type, TSharedRef<FJsonObject> Event);

    TArray<FTournamentParticipant> Participants;
    FString MatchId;
    FString EventPath;
    FString RaceLeaderId;
    FName EndState;
    uint64 NextEventId = 0;
    bool bStarted = false;
    bool bEndPending = false;
    bool bFinalized = false;
    bool bWriteFailed = false;
};
