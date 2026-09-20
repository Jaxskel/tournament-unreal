// Original TournamentBridge code. No Epic implementation is included.
#include "TournamentBridgeMutator.h"
#include "UObject/Interface.h"
#include "UTTeamInterface.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"
#include "GameFramework/GameMode.h"
#include "GameFramework/GameState.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

DEFINE_LOG_CATEGORY_STATIC(LogTournamentBridge, Log, All);

ATournamentBridgeMutator::ATournamentBridgeMutator(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer), DefaultKillPoints(0), FragRaceTarget(0)
{
    bReplicates = false;
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.bStartWithTickEnabled = true;
    PrimaryActorTick.bAllowTickOnDedicatedServer = true;
    GroupNames.Add(FName(TEXT("TournamentBridge")));
    DisplayName = FText::FromString(TEXT("Tournament Bridge (practice/demo)"));
}

bool ATournamentBridgeMutator::CanObserve() const
{
    return GetWorld() && HasAuthority() && GetNetMode() != NM_Client
        && GetWorld()->GetAuthGameMode() != nullptr;
}

void ATournamentBridgeMutator::BeginPlay()
{
    Super::BeginPlay();
    SetActorTickEnabled(CanObserve());
    if (CanObserve())
    {
        AGameState* State = GetWorld()->GetGameState<AGameState>();
        if (State) ObserveState(State->GetMatchState());
    }
}

void ATournamentBridgeMutator::NotifyMatchStateChange_Implementation(FName NewState)
{
    if (CanObserve()) ObserveState(NewState);
    Super::NotifyMatchStateChange_Implementation(NewState);
}

void ATournamentBridgeMutator::ObserveState(FName State)
{
    if (!CanObserve()) return;
    if (State == MatchState::WaitingToStart && bFinalized) bStarted = false;
    if (!bStarted && State == MatchState::InProgress) StartObservedMatch();

    AGameState* GameState = GetWorld()->GetGameState<AGameState>();
    // Virtual dispatch includes UT's MapVoteHappening / WaitingTravel states.
    if (bStarted && !bFinalized && !bEndPending &&
        (State == MatchState::WaitingPostMatch || State == MatchState::LeavingMap ||
         State == MatchState::Aborted || (GameState && GameState->HasMatchEnded())))
    {
        EndState = State;
        bEndPending = true;
    }
}

void ATournamentBridgeMutator::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!CanObserve()) return;
    AGameState* State = GetWorld()->GetGameState<AGameState>();
    if (State)
    {
        // Also supports enabling the mutator during an already active match.
        if (!bStarted && State->IsMatchInProgress()) StartObservedMatch();
        ObserveState(State->GetMatchState());
    }
    // Score processing (including its last ScoreKill callback) has unwound.
    if (bEndPending) FinishObservedMatch();
}

void ATournamentBridgeMutator::EndPlay(const EEndPlayReason::Type Reason)
{
    // Never manufacture a completed match for an unrelated world teardown.
    if (CanObserve() && bEndPending) FinishObservedMatch();
    Super::EndPlay(Reason);
}

void ATournamentBridgeMutator::StartObservedMatch()
{
    if (!CanObserve() || bStarted) return;
    Participants.Empty();
    RaceLeaderId.Empty();
    NextEventId = 0;
    bStarted = true;
    bFinalized = bEndPending = bWriteFailed = false;
    EndState = NAME_None;
    const FString Directory = FPaths::Combine(FPaths::GameSavedDir(), TEXT("Tournament"));
    do
    {
        MatchId = FGuid::NewGuid().ToString();
        EventPath = FPaths::Combine(Directory, TEXT("events-") + MatchId + TEXT(".jsonl"));
    } while (IFileManager::Get().FileExists(*EventPath));
    if (!IFileManager::Get().MakeDirectory(*Directory, true))
    {
        bWriteFailed = true;
        UE_LOG(LogTournamentBridge, Error, TEXT("Cannot create event directory: %s"), *Directory);
    }
    RefreshRoster();
    TSharedRef<FJsonObject> Event = MakeShareable(new FJsonObject());
    Event->SetStringField(TEXT("map"), GetWorld()->GetMapName());
    Event->SetStringField(TEXT("game_mode"), GetWorld()->GetAuthGameMode()->GetClass()->GetPathName());
    Event->SetNumberField(TEXT("default_kill_points"), DefaultKillPoints);
    Event->SetNumberField(TEXT("frag_race_target"), FMath::Max(0, FragRaceTarget));
    Event->SetStringField(TEXT("frag_race_policy"), TEXT("observe_only"));
    TArray<TSharedPtr<FJsonValue>> Rules;
    for (const FTournamentDamagePoints& Rule : DamageTypePoints)
    {
        TSharedRef<FJsonObject> Item = MakeShareable(new FJsonObject());
        Item->SetStringField(TEXT("damage_type_class"), Rule.DamageTypeClass);
        Item->SetNumberField(TEXT("points"), Rule.Points);
        Rules.Add(MakeShareable(new FJsonValueObject(Item)));
    }
    Event->SetArrayField(TEXT("damage_type_points"), Rules);
    Emit(TEXT("match_start"), Event);
}

int32 ATournamentBridgeMutator::TouchParticipant(APlayerState* State)
{
    if (!State) return INDEX_NONE;
    int32 Index = Participants.IndexOfByPredicate([State](const FTournamentParticipant& P)
    {
        return P.State.Get() == State;
    });
    if (Index == INDEX_NONE)
    {
        Index = Participants.AddDefaulted();
        Participants[Index].State = State;
        Participants[Index].Id = FString::Printf(TEXT("p%d"), Index + 1);
    }
    FTournamentParticipant& P = Participants[Index];
    P.Name = State->PlayerName;
    P.VanillaScore = State->Score;
    P.bBot = State->bIsABot;
    P.bSpectator = State->bOnlySpectator;
    IUTTeamInterface* Team = Cast<IUTTeamInterface>(State);
    P.Team = Team ? Team->GetTeamNum() : 255;
    return Index;
}

void ATournamentBridgeMutator::RefreshRoster()
{
    // Retain disconnected participants' last observed native score.
    for (FTournamentParticipant& P : Participants) P.bConnected = false;
    AGameState* State = GetWorld()->GetGameState<AGameState>();
    if (!State) return;
    for (APlayerState* Player : State->PlayerArray)
    {
        if (Player)
        {
            const int32 Index = TouchParticipant(Player);
            Participants[Index].bConnected = true;
        }
    }
}

TSharedRef<FJsonObject> ATournamentBridgeMutator::ParticipantJson(int32 Index) const
{
    TSharedRef<FJsonObject> Result = MakeShareable(new FJsonObject());
    const FTournamentParticipant& P = Participants[Index];
    Result->SetStringField(TEXT("participant_id"), P.Id);
    Result->SetStringField(TEXT("display_name"), P.Name);
    Result->SetBoolField(TEXT("bot"), P.bBot);
    Result->SetBoolField(TEXT("connected"), P.bConnected);
    Result->SetBoolField(TEXT("spectator"), P.bSpectator);
    Result->SetNumberField(TEXT("team"), P.Team);
    Result->SetNumberField(TEXT("vanilla_score"), P.VanillaScore);
    Result->SetStringField(TEXT("practice_points"), FString::Printf(TEXT("%lld"), P.PracticePoints));
    Result->SetNumberField(TEXT("observed_enemy_frags"), P.ObservedFrags);
    Result->SetNumberField(TEXT("observed_deaths"), P.ObservedDeaths);
    return Result;
}

int32 ATournamentBridgeMutator::PointsFor(UClass* DamageClass) const
{
    if (DamageClass)
    {
        for (const FTournamentDamagePoints& Rule : DamageTypePoints)
            if (Rule.DamageTypeClass == DamageClass->GetPathName()) return Rule.Points;
        for (const FTournamentDamagePoints& Rule : DamageTypePoints)
            if (Rule.DamageTypeClass == DamageClass->GetName()) return Rule.Points;
    }
    return DefaultKillPoints;
}

void ATournamentBridgeMutator::ScoreKill_Implementation(AController* Killer, AController* Other,
    TSubclassOf<UDamageType> DamageType)
{
    if (CanObserve())
    {
        AGameState* State = GetWorld()->GetGameState<AGameState>();
        if (!bStarted && State && State->IsMatchInProgress()) StartObservedMatch();
        // Pending finalization deliberately accepts the match-winning callback.
        if (bStarted && !bFinalized && State && (State->IsMatchInProgress() || bEndPending))
        {
            const int32 K = TouchParticipant(Killer ? Killer->PlayerState : nullptr);
            const int32 V = TouchParticipant(Other ? Other->PlayerState : nullptr);
            const bool bSuicide = Other && Killer == Other;
            const bool bWorldDeath = Killer == nullptr;
            IUTTeamInterface* KT = Killer ? Cast<IUTTeamInterface>(Killer->PlayerState) : nullptr;
            IUTTeamInterface* VT = Other ? Cast<IUTTeamInterface>(Other->PlayerState) : nullptr;
            const bool bTeamKill = K != INDEX_NONE && V != INDEX_NONE && !bSuicide && KT && VT &&
                (KT->IsFriendlyToAll() || VT->IsFriendlyToAll() ||
                 (KT->GetTeamNum() != 255 && KT->GetTeamNum() == VT->GetTeamNum()));
            const bool bEligible = K != INDEX_NONE && V != INDEX_NONE && !bSuicide && !bTeamKill &&
                !Participants[K].bSpectator && !Participants[V].bSpectator;
            const int32 Points = bEligible ? PointsFor(DamageType.Get()) : 0;
            if (V != INDEX_NONE) ++Participants[V].ObservedDeaths;
            if (bEligible)
            {
                Participants[K].PracticePoints += Points;
                ++Participants[K].ObservedFrags;
            }
            TSharedRef<FJsonObject> Event = MakeShareable(new FJsonObject());
            if (K != INDEX_NONE) Event->SetObjectField(TEXT("killer"), ParticipantJson(K));
            else Event->SetField(TEXT("killer"), MakeShareable(new FJsonValueNull()));
            if (V != INDEX_NONE) Event->SetObjectField(TEXT("victim"), ParticipantJson(V));
            else Event->SetField(TEXT("victim"), MakeShareable(new FJsonValueNull()));
            Event->SetStringField(TEXT("damage_type_class"), DamageType.Get() ? DamageType->GetName() : TEXT(""));
            Event->SetStringField(TEXT("damage_type_path"), DamageType.Get() ? DamageType->GetPathName() : TEXT(""));
            Event->SetBoolField(TEXT("suicide"), bSuicide);
            Event->SetBoolField(TEXT("world_death"), bWorldDeath);
            Event->SetBoolField(TEXT("teamkill"), bTeamKill);
            Event->SetBoolField(TEXT("eligible_enemy_frag"), bEligible);
            Event->SetNumberField(TEXT("practice_points_awarded"), Points);
            Emit(TEXT("kill"), Event);
            if (bEligible && FragRaceTarget > 0 && RaceLeaderId.IsEmpty() &&
                Participants[K].ObservedFrags >= FragRaceTarget)
            {
                RaceLeaderId = Participants[K].Id;
                TSharedRef<FJsonObject> Race = MakeShareable(new FJsonObject());
                Race->SetObjectField(TEXT("participant"), ParticipantJson(K));
                Race->SetNumberField(TEXT("target"), FragRaceTarget);
                Race->SetBoolField(TEXT("ends_game"), false);
                Emit(TEXT("frag_race_target_reached"), Race);
            }
        }
    }
    // Preserve the existing mutator chain exactly once, regardless of file errors.
    Super::ScoreKill_Implementation(Killer, Other, DamageType);
}

void ATournamentBridgeMutator::NotifyLogout_Implementation(AController* C)
{
    if (CanObserve() && bStarted && !bFinalized && C && C->PlayerState)
    {
        const int32 Index = TouchParticipant(C->PlayerState);
        Participants[Index].bConnected = false;
    }
    Super::NotifyLogout_Implementation(C);
}

void ATournamentBridgeMutator::FinishObservedMatch()
{
    if (!CanObserve() || !bStarted || bFinalized || !bEndPending) return;
    bFinalized = true;
    bEndPending = false;
    RefreshRoster();
    TArray<int32> Order;
    for (int32 I = 0; I < Participants.Num(); ++I)
        if (!Participants[I].bSpectator) Order.Add(I);
    Order.Sort([this](int32 A, int32 B)
    {
        const float AS = Participants[A].VanillaScore, BS = Participants[B].VanillaScore;
        return AS == BS ? A < B : AS > BS;
    });
    TArray<TSharedPtr<FJsonValue>> Rows;
    int32 Rank = 0;
    for (int32 I = 0; I < Order.Num(); ++I)
    {
        if (I == 0 || Participants[Order[I]].VanillaScore != Participants[Order[I - 1]].VanillaScore)
            Rank = I + 1;
        TSharedRef<FJsonObject> Row = ParticipantJson(Order[I]);
        Row->SetNumberField(TEXT("rank"), Rank);
        Rows.Add(MakeShareable(new FJsonValueObject(Row)));
    }
    TSharedRef<FJsonObject> Event = MakeShareable(new FJsonObject());
    Event->SetStringField(TEXT("end_state"), EndState.ToString());
    Event->SetBoolField(TEXT("aborted"), EndState == MatchState::Aborted);
    Event->SetStringField(TEXT("ranking"), TEXT("individual_vanilla_score_desc_competition_ties"));
    Event->SetStringField(TEXT("frag_race_first_participant_id"), RaceLeaderId);
    Event->SetArrayField(TEXT("scoreboard"), Rows);
    Emit(TEXT("match_end"), Event);
}

void ATournamentBridgeMutator::Emit(const TCHAR* Type, TSharedRef<FJsonObject> Event)
{
    if (!CanObserve() || !bStarted || bWriteFailed) return;
    Event->SetNumberField(TEXT("schema_version"), 1);
    Event->SetStringField(TEXT("mode"), TEXT("practice_demo"));
    Event->SetBoolField(TEXT("practice_demo"), true);
    Event->SetBoolField(TEXT("real_money"), false);
    Event->SetStringField(TEXT("identity_scope"), TEXT("match_local_playerstate"));
    Event->SetStringField(TEXT("match_id"), MatchId);
    Event->SetStringField(TEXT("event_id"), FString::Printf(TEXT("%llu"), ++NextEventId));
    Event->SetStringField(TEXT("type"), Type);
    Event->SetStringField(TEXT("utc"), FDateTime::UtcNow().ToIso8601());
    FString Line;
    const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
        TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Line);
    const bool bSerialized = FJsonSerializer::Serialize(Event, Writer);
    Line += TEXT("\n");
    const uint32 Flags = NextEventId == 1 ? FILEWRITE_NoReplaceExisting : FILEWRITE_Append;
    if (!bSerialized || !FFileHelper::SaveStringToFile(Line, *EventPath,
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), Flags))
    {
        // No retries after a potentially partial append: avoid duplicate JSON/events.
        bWriteFailed = true;
        UE_LOG(LogTournamentBridge, Error, TEXT("Event write failed; logging disabled for match %s (%s)"),
            *MatchId, *EventPath);
    }
}
