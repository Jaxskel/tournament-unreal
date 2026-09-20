#include "TournamentBridgeMutator.h"
#include "TournamentHUD.h"
#include "TournamentPlayerController.h"

namespace TournamentPalette
{
    const FLinearColor Gold(FColor(255, 215, 90));
    const FLinearColor Muted(FColor(168, 158, 138));
    const FLinearColor Text(FColor(232, 224, 208));
    const FLinearColor Brown(0.012f, 0.008f, 0.004f, 0.94f);
}

ATournamentHUD::ATournamentHUD(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer), LastMenuPage(-1)
{
}

void ATournamentHUD::Label(const FString& Text, float X, float Y, float Scale, const FLinearColor& Color)
{
    UFont* Font = GEngine ? GEngine->GetSmallFont() : nullptr;
    DrawText(Text, FLinearColor::Black, X + 1, Y + 1, Font, Scale);
    DrawText(Text, Color, X, Y, Font, Scale);
}

void ATournamentHUD::Panel(float X, float Y, float W, float H)
{
    DrawRect(TournamentPalette::Brown, X, Y, W, H);
    DrawRect(TournamentPalette::Gold, X, Y, W, 1);
    DrawRect(TournamentPalette::Gold, X, Y + H - 1, W, 1);
    DrawRect(TournamentPalette::Gold, X, Y, 1, H);
    DrawRect(TournamentPalette::Gold, X + W - 1, Y, 1, H);
}

void ATournamentHUD::DrawHUD()
{
    Super::DrawHUD(); // Keep native ammo, health, weapons, crosshair and hit feedback.
    TournamentButtons.Reset();
    LastMenuPage = -1;
    if (!Canvas || !PlayerOwner) return;
    ATournamentPlayerController* PC = Cast<ATournamentPlayerController>(PlayerOwner);
    const float Scale = FMath::Max(0.25f, FMath::Min(Canvas->ClipX / 1280.f, Canvas->ClipY / 720.f));
    if (PC && PC->IsTournamentMenuOpen()) { DrawTournamentMenu(PC, Scale); return; }
    // Do not cover the stock full scoreboard or the sight line through the arena.
    if (!bShowHUD || ScoreboardIsUp()) return;
    Panel(18 * Scale, 92 * Scale, 240 * Scale, 67 * Scale);
    Label(TEXT("TOURNAMENT"), 30 * Scale, 101 * Scale, 1.3f * Scale, TournamentPalette::Gold);
    Label(TEXT("DEMO \u2022 NO REWARDS"), 30 * Scale, 126 * Scale, 0.8f * Scale, TournamentPalette::Muted);
    DrawTournamentStandings(Canvas->ClipX - 258 * Scale, 170 * Scale, 240 * Scale, Scale, 3);
    Label(TEXT("ESC  MENU    TAB  SCOREBOARD"), 24 * Scale, Canvas->ClipY - 130 * Scale, 0.85f * Scale, TournamentPalette::Muted);
}

void ATournamentHUD::DrawTournamentStandings(float X, float Y, float W, float Scale, int32 MaxRows)
{
    AUTGameState* GS = GetWorld() ? GetWorld()->GetGameState<AUTGameState>() : nullptr;
    if (!GS) return;
    TArray<AUTPlayerState*> Players;
    for (APlayerState* State : GS->PlayerArray)
    {
        AUTPlayerState* PS = Cast<AUTPlayerState>(State);
        if (PS && !PS->bOnlySpectator && !PS->bIsInactive) Players.Add(PS);
    }
    Players.Sort([](const AUTPlayerState& A, const AUTPlayerState& B)
    {
        if (A.Score != B.Score) return A.Score > B.Score;
        if (A.Deaths != B.Deaths) return A.Deaths < B.Deaths;
        return A.PlayerId < B.PlayerId;
    });
    const int32 Count = FMath::Min(MaxRows, Players.Num());
    Panel(X, Y, W, (75 + 29 * Count) * Scale);
    Label(TEXT("FRAG RACE"), X + 12 * Scale, Y + 10 * Scale, Scale, TournamentPalette::Gold);
    const int32 Seconds = FMath::Max(0, GS->GetRemainingTime());
    const FString Rules = FString::Printf(TEXT("%d FRAGS  /  %02d:%02d"), GS->GoalScore, Seconds / 60, Seconds % 60);
    Label(Rules, X + 12 * Scale, Y + 33 * Scale, 0.8f * Scale, TournamentPalette::Muted);
    int32 Rank = 1;
    for (int32 I = 0; I < Count; ++I)
    {
        AUTPlayerState* PS = Players[I];
        // Competition ranks: deaths only order equal scores; they do not break ties.
        if (I > 0 && PS->Score != Players[I - 1]->Score) Rank = I + 1;
        const bool bYou = PS == PlayerOwner->PlayerState;
        const float RowY = Y + (58 + I * 29) * Scale;
        if (bYou) DrawRect(FLinearColor(0.12f, 0.085f, 0.012f, 0.65f), X + 5 * Scale, RowY - 2 * Scale, W - 10 * Scale, 27 * Scale);
        FString Name = PS->PlayerName;
        Name.ReplaceInline(TEXT("\n"), TEXT(" "));
        Name.ReplaceInline(TEXT("\r"), TEXT(" "));
        Name = Name.Left(MaxRows > 3 ? 23 : 14);
        const FString Tag = bYou ? TEXT(" YOU") : PS->bIsABot ? TEXT(" BOT") : TEXT("");
        Label(FString::Printf(TEXT("%d  %s%s"), Rank, *Name, *Tag), X + 12 * Scale, RowY, 0.8f * Scale, bYou ? TournamentPalette::Gold : TournamentPalette::Text);
        Label(FString::Printf(TEXT("%.0f"), PS->Score), X + W - 42 * Scale, RowY, Scale, TournamentPalette::Gold);
    }
    // This is a display of replicated native scores, not settlement or payout ranking.
}

void ATournamentHUD::DrawTournamentMenu(ATournamentPlayerController* PC, float Scale)
{
    DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.60f), 0, 0, Canvas->ClipX, Canvas->ClipY);
    const float W = 600 * Scale;
    const float H = 580 * Scale;
    const float X = (Canvas->ClipX - W) * 0.5f;
    const float Y = (Canvas->ClipY - H) * 0.5f;
    Panel(X, Y, W, H);
    Label(TEXT("TOURNAMENT"), X + 32 * Scale, Y + 23 * Scale, 2.1f * Scale, TournamentPalette::Gold);
    Label(TEXT("DEMO \u2022 NO REWARDS"), X + 34 * Scale, Y + 64 * Scale, Scale, TournamentPalette::Muted);
    DrawRect(TournamentPalette::Gold, X + 32 * Scale, Y + 94 * Scale, W - 64 * Scale, 1);
    const int32 Page = PC->GetTournamentPage();
    LastMenuPage = Page;
    Label(Page == 1 ? TEXT("SETTINGS") : Page == 2 ? TEXT("GAME MODE") : Page == 3 ? TEXT("DIAGNOSTICS") : TEXT("FRAG RACE"), X + 34 * Scale, Y + 110 * Scale, 1.25f * Scale, TournamentPalette::Text);
    float ButtonY = Y + 160 * Scale;
    if (Page == 2)
    {
        AUTGameState* GS = GetWorld()->GetGameState<AUTGameState>();
        Label(TEXT("FRAG RACE / DEATHMATCH"), X + 34 * Scale, ButtonY, Scale, TournamentPalette::Gold);
        Label(GS ? FString::Printf(TEXT("First to %d frags. Highest score wins."), GS->GoalScore) : TEXT("Waiting for server rules..."), X + 34 * Scale, ButtonY + 35 * Scale, Scale, TournamentPalette::Text);
        Label(TEXT("Arenas rotate automatically."), X + 34 * Scale, ButtonY + 70 * Scale, Scale, TournamentPalette::Text);
        Label(TEXT("Rules and standings are controlled by the server."), X + 34 * Scale, ButtonY + 105 * Scale, 0.9f * Scale, TournamentPalette::Muted);
        Label(TEXT("PPK and cash rewards are not enabled in this demo."), X + 34 * Scale, ButtonY + 140 * Scale, 0.9f * Scale, TournamentPalette::Muted);
        ButtonY += 198 * Scale;
    }
    if (Page == 3)
    {
        DrawTournamentDiagnostics(PC, X + 34 * Scale, ButtonY, W - 68 * Scale, Scale);
        ButtonY = Y + 415 * Scale;
    }
    float MouseX = -1, MouseY = -1;
    PC->GetMousePosition(MouseX, MouseY);
    for (int32 I = 0; I < PC->GetTournamentItemCount(); ++I)
    {
        const float BX = X + 32 * Scale, BY = ButtonY + I * 48 * Scale;
        const float BW = W - 64 * Scale, BH = 40 * Scale;
        TournamentButtons.Add(FVector4(BX, BY, BW, BH));
        const bool bHover = MouseX >= BX && MouseX <= BX + BW && MouseY >= BY && MouseY <= BY + BH;
        const bool bEnabled = PC->IsTournamentItemEnabled(I);
        const bool bSelected = bEnabled && (bHover || PC->GetTournamentSelection() == I);
        DrawRect(bSelected ? FLinearColor(0.18f, 0.12f, 0.025f, 1.f) : FLinearColor(0.025f, 0.018f, 0.01f, 1.f), BX, BY, BW, BH);
        if (bSelected) DrawRect(TournamentPalette::Gold, BX, BY, 3 * Scale, BH);
        Label(PC->GetTournamentItemLabel(I), BX + 14 * Scale, BY + 10 * Scale, Scale, bSelected ? TournamentPalette::Gold : bEnabled ? TournamentPalette::Text : TournamentPalette::Muted);
    }
    if (Page == 0)
    {
        Label(TEXT("WASD  MOVE     MOUSE  AIM / FIRE"), X + 34 * Scale, Y + 382 * Scale, Scale, TournamentPalette::Muted);
        Label(TEXT("TAB  SCORES    SPACE  JUMP"), X + 34 * Scale, Y + 411 * Scale, Scale, TournamentPalette::Muted);
        Label(TEXT("The match continues while this menu is open."), X + 34 * Scale, Y + 456 * Scale, 0.9f * Scale, TournamentPalette::Muted);
    }
    Label(TEXT("ESC  RESUME    ARROWS  NAVIGATE    ENTER  SELECT"), X + 34 * Scale, Y + H - 35 * Scale, 0.85f * Scale, TournamentPalette::Muted);
}

void ATournamentHUD::DrawTournamentDiagnostics(ATournamentPlayerController* PC, float X, float Y, float W, float Scale)
{
    TArray<FString> Lines;
    PC->GetTournamentDiagnostics(Lines);
    UFont* Font = GEngine ? GEngine->GetSmallFont() : nullptr;
    for (int32 I = 0; I < Lines.Num(); ++I)
    {
        FString Text = Lines[I].Left(256);
        Text.ReplaceInline(TEXT("\n"), TEXT(" "));
        Text.ReplaceInline(TEXT("\r"), TEXT(" "));
        // Bound long map names/hostnames to the panel, without displaying URL options.
        float TextW = 0, TextH = 0;
        GetTextSize(Text, TextW, TextH, Font, 0.95f * Scale);
        if (TextW > W)
        {
            do
            {
                Text = Text.Left(FMath::Max(0, Text.Len() - 1));
                GetTextSize(Text + TEXT("..."), TextW, TextH, Font, 0.95f * Scale);
            } while (Text.Len() > 0 && TextW > W);
            Text += TEXT("...");
        }
        Label(Text, X, Y + I * 30 * Scale, 0.95f * Scale, TournamentPalette::Text);
    }
}

void ATournamentHUD::ClickTournamentMenu(float X, float Y)
{
    ATournamentPlayerController* PC = Cast<ATournamentPlayerController>(PlayerOwner);
    if (!PC || !PC->IsTournamentMenuOpen() || LastMenuPage != PC->GetTournamentPage()) return;
    for (int32 I = 0; I < TournamentButtons.Num(); ++I)
    {
        const FVector4& B = TournamentButtons[I];
        if (PC->IsTournamentItemEnabled(I) && X >= B.X && X <= B.X + B.Z && Y >= B.Y && Y <= B.Y + B.W)
        {
            PC->SelectTournamentItem(I);
            PC->ActivateTournamentItem(I);
            TournamentButtons.Reset(); // Old-page coordinates cannot activate a new-page action.
            return;
        }
    }
}
