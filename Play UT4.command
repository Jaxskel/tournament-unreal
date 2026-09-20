#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
WORKSPACE="$(cd -- "$HERE/../.." && pwd)"
CLIENT="$WORKSPACE/work/ut4-recovery/client/Engine/Binaries/Win64/UE4-Win64-Shipping.exe"
WINE='/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine'
if [[ ! -f "$CLIENT" || ! -x "$WINE" ]]; then
  echo 'The recovered UT4 client and CrossOver are required on this Mac.'
  read -r -p 'Press Enter to close.'
  exit 1
fi
mkdir -p "$HERE/logs"
echo 'Starting Unreal Tournament. Choose Play Offline if prompted.'
echo 'For the verified six-bot setup, open the console with ~ and enter:'
echo 'open DM-DeckTest?Game=DM?Bots=6?Difficulty=3?TimeLimit=15?GoalScore=30'
echo 'Then click START MATCH. WASD to move, mouse to aim, click to shoot.'
exec "$WINE" --bottle TournamentUT4 "$CLIENT" UnrealTournament -windowed -ResX=1280 -ResY=720 -NoSplash -log > "$HERE/logs/client-launch.log" 2>&1
