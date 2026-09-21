#include "TournamentBridgeMutator.h"
#include "TournamentGameState.h"
#include "UTPlayerState.h"

void ATournamentGameState::UpdateHighlights_Implementation()
{
    // The recovered content can produce an invalid FavoriteWeapon class during
    // stock match highlights (confirmed in the server replication crash dump).
    // This demo uses authoritative frag standings, not cosmetic weapon awards.
    // Avoid generating the unsafe reference; never mask invalid objects in the
    // engine serializer or accept browser-supplied scores.
    ClearHighlights();
    for (APlayerState* State : PlayerArray)
    {
        AUTPlayerState* Player = Cast<AUTPlayerState>(State);
        if (Player)
        {
            Player->FavoriteWeapon = nullptr;
            Player->ForceNetUpdate();
        }
    }
    UE_LOG(LogTemp, Log, TEXT("Tournament: finalized frag standings without cosmetic weapon highlights."));
}
