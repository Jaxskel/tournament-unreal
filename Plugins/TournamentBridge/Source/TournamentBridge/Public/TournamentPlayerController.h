// Original Tournament UI. No platform identity, score or reward authority lives here.
#pragma once
#include "Core.h"
#include "Engine.h"
#include "UnrealTournament.h"
#include "UTPlayerController.h"
#include "TournamentPlayerController.generated.h"

UCLASS()
class TOURNAMENTBRIDGE_API ATournamentPlayerController : public AUTPlayerController
{
    GENERATED_BODY()
public:
    ATournamentPlayerController(const FObjectInitializer& ObjectInitializer);
    virtual void ShowMenu(const FString& Parameters) override;
    virtual void HideMenu() override;
    virtual bool InputKey(FKey Key, EInputEvent EventType, float AmountDepressed, bool bGamepad) override;
    virtual bool InputAxis(FKey Key, float Delta, float DeltaTime, int32 NumSamples, bool bGamepad) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    void ReleaseBrowserInput();

    bool IsTournamentMenuOpen() const { return bTournamentMenuOpen; }
    int32 GetTournamentPage() const { return MenuPage; }
    int32 GetTournamentSelection() const { return MenuSelection; }
    void SelectTournamentItem(int32 Index);
    void ActivateTournamentItem(int32 Index);
    FString GetTournamentItemLabel(int32 Index) const;
    int32 GetTournamentItemCount() const;
    bool CanTournamentReconnect() const;
    bool IsTournamentItemEnabled(int32 Index) const;
    void GetTournamentDiagnostics(TArray<FString>& Lines) const;

private:
    bool bTournamentMenuOpen;
    bool bPreviousCursor;
    int32 MenuPage; // 0: pause/play, 1: local settings, 2: authoritative rules, 3: diagnostics.
    int32 MenuSelection;
    void AdjustSetting(int32 Index, int32 Direction);
};
