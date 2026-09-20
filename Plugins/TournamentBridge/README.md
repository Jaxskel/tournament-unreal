# TournamentBridge

Original practice/demo observability plugin for the supplied UT4 UE4.15 source.
**Windows UE4.15 compilation and linking passed; runtime event verification remains pending.**
Epic files were read selectively as API references; none are included here.

Enable the plugin in the restored UT project and add the native mutator using
`?mutator=TournamentBridge.TournamentBridgeMutator` on the server's map URL.
The reflected class is `/Script/TournamentBridge.TournamentBridgeMutator`.
This uses the source's `ModuleRules(TargetInfo)` convention.

Only an authoritative world with an active GameMode writes files (dedicated,
listen, or standalone practice host). Clients never write; the actor does not
replicate. Each observed match gets a fresh GUID and
`Saved/Tournament/events-<GUID>.jsonl`: compact UTF-8 without BOM, one JSON object
per line. `match_start`, `kill`, optional `frag_race_target_reached`, and one
`match_end` with the ranked scoreboard all carry `practice_demo: true` and
`real_money: false`. Event IDs are monotonic decimal strings starting at `1`
within a match. Participant IDs are match-local PlayerState identities, **not
accounts or authenticated users**; reconnects get new identities. Bot flags,
team number (`255` means none), suicide, teamkill, and world-death flags are
explicit. A null killer is a world/unattributed death; only a self-killer is
labeled a suicide. No HTTP, authentication, payouts, or gameplay mutations.

Optional server `Game.ini` settings (apply outside this plugin during setup):

```ini
[/Script/TournamentBridge.TournamentBridgeMutator]
DefaultKillPoints=0
FragRaceTarget=0
; Replace this placeholder with an exact class name/path from a kill event:
; +DamageTypePoints=(DamageTypeClass="YourObservedDamageClass",Points=3)
```

The default rule list is empty and default points are zero: no weapon assumptions.
Exact full class paths take precedence over short names; the first matching rule
wins within each category, without inheritance matching. Only observed enemy
frags award these separate practice points; suicides, world deaths, teamkills,
and spectators award none. Bots participate and are labeled. Points never alter
`PlayerState.Score`. A positive `FragRaceTarget` reports the first participant to
reach that many observed enemy frags, once, **without ending the UT match**.

The final individual scoreboard sorts native scores descending, with shared
competition ranks for ties (1, 1, 3); it is not a team-game winner declaration.
Observed frag/death counts are bridge counters, not UT's lifetime/native totals.
Disconnected participants retain their last observed score. Warmup is excluded;
mid-match activation cannot reconstruct earlier kills. Intermission/overtime do
not create new match IDs. A later WaitingToStart -> InProgress cycle does.

Finalization waits until the next server tick because UT can signal match end
before invoking the mutator for the winning kill. Repeated end notifications
are ignored. Teardown only flushes an already pending end; process crashes or
forced shutdown may leave an incomplete log. File errors disable writes for
that match and log an error; there are no retries or durability guarantees.

Parent checks: build/UHT; dedicated + listen/remote-client matches; empty roster;
normal kill, suicide, world death, teamkill and bot; class-rule precedence;
winning kill before final event; repeated end notifications; time-limit finish,
overtime/intermission, aborted match and travel; disconnected players and ties;
unwritable Saved directory. Compare vanilla scores and match length with/without
the plugin, parse every JSONL line, and verify no remote-client event file.

## Build verification (20 September 2026)

Compiled successfully as `UE4Editor-TournamentBridge.dll` on the Windows PC with the recovered UE4.15 changelist 3228288 project, MSVC v140, Windows SDK 8.1 and UCRT 10.0.10240.0. This verifies compilation and linking. Runtime JSONL event validation is still pending; the dedicated-server run requires the user’s first-run license decision.

## Automatic arena rotation

The plugin also includes `TournamentDeathmatch`, an `AUTDMGameMode` subclass. Select it with `?Game=/Script/TournamentBridge.TournamentDeathmatch` and include `?mutator=TournamentBridge.TournamentBridgeMutator` to collect telemetry. The original mutator remains observational; map travel is the separate game mode's responsibility.

The default rotation is `/Game/RestrictedAssets/Maps/WIP/DM-DeckTest`, then `/Game/RestrictedAssets/Maps/DM-Outpost23`. Configure `ArenaRotation` under `[/Script/TournamentBridge.TournamentDeathmatch]` in Game.ini. The game mode requests the next map directly at the normal end-of-match travel callback, preserving existing game URL options. It accepts only existing `/Game/` packages, skips invalid entries with errors, removes duplicates, and leaves the result screen with an error if no valid entry exists. It does not accept client-selected travel destinations. If the current map is outside the list, it chooses the first configured map.

This class passed UHT, compilation, and linking on Windows. Runtime rotation is still unverified. The preserved shipping Mac client does not contain this class and still presents its stock map chooser; configuration alone did not change that behavior. Before shipping, verify both travel directions, reconnects, option preservation, missing maps, and the telemetry file ending before travel.

## Native Tournament UI

`TournamentDeathmatch` assigns `TournamentHUD` and `TournamentPlayerController`. The HUD retains the stock DM combat widgets and overlays gold/brown Tournament branding, a no-rewards label, and replicated top-three standings with shared ranks for tied scores. Escape toggles the Canvas menu; settings use UT's volume, fullscreen, and profile sensitivity APIs. Stock profile synchronization may also occur if the user is already logged into Epic; no login is initiated.

The Diagnostics page shows map/match, network role, connection state, endpoint (never URL credentials/options), and the replicated ping estimate. Reconnect is enabled only for an active remote client and preserves the engine's last remote URL. It is not a recovery frontend after UT destroys the controller and returns to its entry menu.

These UI classes passed Windows UE4.15 compilation/linking. Rendering, menu input/focus, settings persistence, and reconnect runtime checks remain pending. UT's entry/login frontend remains stock; these classes replace the in-match presentation.
