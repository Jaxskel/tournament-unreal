# Multiplayer verification

A compile is not a multiplayer pass. Update this record only from actual runtime evidence.

## Required session

Use one authoritative `UnrealTournamentEditor -server` process and two independent `-game` client processes built against UE4.15 CL3228288 with the same TournamentBridge plugin. A headless client verifies transport/state only. At least one rendered client is required to verify visibility, controls, combat, and the native menu.

1. Start the server with `scripts/start-server.ps1`. Require explicit license acceptance on first launch. Verify the log identifies `TournamentDeathmatch` and binds the intended UDP address/port.
2. Join Alpha and Bravo with `scripts/join-game.ps1`. Record both server connection/player names; confirm both replicated players appear on both clients.
3. Start/fight/kill/respawn. Confirm bots are present and gameplay changes originate on the server. Save event JSONL and compare scores with both clients.
4. Use a short round (`-Minutes 1 -Frags 3`) to verify one final ranking, Deck → Outpost 23, and then Outpost 23 → Deck. Confirm no chooser, preserved server rules, and new unique match IDs.
5. Disconnect Bravo, reconnect, and verify a new live connection without duplicate final events. Player names are display names; demo participant IDs are match-local and reconnects may receive a new ID.
6. On the rendered client, open and close Escape/settings repeatedly, adjust volume and sensitivity, resume mouse capture, and test fullscreen. No held movement or firing should continue while interacting with the menu.
7. Verify wrong protocol versions reject cleanly. Check a missing map produces a clear server error. Do not claim platform anti-cheat or ticket validation from those checks.
8. Run `verify-events.py` on every completed JSONL file. Keep original logs locally; redact machine paths, addresses, tokens, and player identifiers before sharing diagnostics.

## Current record

- Preserved shipping client: local bot match, scoring, deaths, respawn, completion, and both maps observed on Mac.
- Recovered source: base game module and event/rotation plugin compiled on Windows.
- Native Tournament HUD, settings/menu controller, reconnect, and diagnostics compiled and linked against the recovered Windows UE4.15 project. Launcher tests and eight event-contract tests passed.
- Native multiplayer runtime: pending the first-run license decision.
- New Tournament UI input/focus, source-built rotation, event output, and two-client reconnect: pending runtime verification.
- Spectator delay, internet hosting, packaged clients, Tournament tickets, rewards, and anti-cheat: not implemented/verified in this Unreal integration.

The stock shipping client used for the Mac visual checks is CL3525360. It does not contain this repository's new UI and is not the client for a CL3228288 source-built server test.
