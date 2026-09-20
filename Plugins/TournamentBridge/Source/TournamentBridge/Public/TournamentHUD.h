// Original Tournament overlay; the stock DM HUD retains combat information.
#pragma once
#include "Core.h"
#include "Engine.h"
#include "UnrealTournament.h"
#include "UTHUD_DM.h"
#include "TournamentHUD.generated.h"

UCLASS()
class TOURNAMENTBRIDGE_API ATournamentHUD : public AUTHUD_DM
{
    GENERATED_BODY()
public:
    ATournamentHUD(const FObjectInitializer& ObjectInitializer);
    virtual void DrawHUD() override;
    void ClickTournamentMenu(float X, float Y);

private:
    TArray<FVector4> TournamentButtons;
    int32 LastMenuPage;
    void Label(const FString& Text, float X, float Y, float Scale, const FLinearColor& Color);
    void Panel(float X, float Y, float W, float H);
    void DrawTournamentMenu(class ATournamentPlayerController* PC, float Scale);
    void DrawTournamentDiagnostics(class ATournamentPlayerController* PC, float X, float Y, float W, float Scale);
    void DrawTournamentStandings(float X, float Y, float W, float Scale, int32 MaxRows);
};
