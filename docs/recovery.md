# Tournament — UT4 development recovery

## What works

On 20 September 2026, the preserved Windows UT4 client ran on this Mac through CrossOver. A local deathmatch on DM-DeckTest had one human and six bots, visible characters, working bot combat, scoring, deaths, and respawning. See [game screenshot](../ut4-running.png) and [live bot scoreboard](../evidence/bots-scoreboard.png). Audio was disabled during verification. The approximately 120 FPS shown in the captured scoreboard is one native-client sample, not a browser or sustained performance benchmark.

On the Windows PC, the recovered UE4.15 source successfully compiled and linked the `UnrealTournament` editor game module and the original `TournamentBridge` plugin. Local build evidence (`evidence/build-artifacts.json`, excluded from Git) records artifact sizes and SHA-256 hashes; the full game/plugin logs are retained locally and excluded from the public repository. This was an incremental build using the recovered engine/editor and its build libraries, not a full engine rebuild or a newly packaged shipping game.

The plugin is a foundation for authoritative match telemetry: server-side kill/weapon records, bot flags, match IDs, event IDs, and final rankings. Its `TournamentDeathmatch` subclass replaces map selection with a configured arena rotation. Compilation and runtime event checks passed, including a 35-record completed match and observed Deck → Outpost rotation. It does not authenticate Tournament accounts or award money. See [plugin contract and limitations](../Plugins/TournamentBridge/README.md).

## Play on this Mac

Double-click **Play UT4.command** in this folder. It requires the recovered client under this workspace's `work/ut4-recovery/client` and the existing CrossOver `TournamentUT4` bottle; it is not a portable installer.

1. Choose **Play Offline** if the Epic sign-in screen appears.
2. Open the console with **~**, enter the following, and press Return:

   ```text
   open DM-DeckTest?Game=DM?Bots=6?Difficulty=3?TimeLimit=15?GoalScore=30
   ```

3. Click **START MATCH**. Use WASD, mouse aim, left-click fire, and Escape for the menu. Click to respawn when prompted.

**The stock Mac client still shows its map chooser after a match.** A one-minute test reached the winner screen and then the chooser despite a disable-vote configuration. Manually choosing Outpost 23 successfully loaded that second arena with six bots. Evidence includes [completed match](../evidence/completed-match.png), [stock chooser](../evidence/stock-map-chooser.png), and [second arena](../evidence/outpost23.png).

`config/Game.ini` now provides rotation settings for the **new source-built `TournamentDeathmatch` class**, which is not installed in the stock Mac client. Bot fill is seven total players, yielding six bots with one human. The initial Mac profile is backed up under `work/ut4-recovery/mac-Game.ini.before-tournament`.

The launcher stores startup output under `logs/client-launch.log`. The game's own detailed log is `~/Documents/UnrealTournament/Saved/Logs/UnrealTournament.log`. The launcher enables normal audio, which remains unverified.

## Rebuild on the configured Windows PC

The recovered source is at `F:\TournamentUT4\source\UnrealTournament-clean-master`. The original downloaded archive is at `F:\TournamentUT4\work\UnrealTournament-clean-master.zip`. The build scripts default to these paths and accept `-SourceRoot` overrides.

Installed prerequisites:

- Visual Studio 2022 Community, with the optional **MSVC v140 / Visual Studio 2015** toolset.
- **Windows SDK 8.1** and **Universal CRT 10.0.10240.0**.
- The Windows .NET Framework MSBuild executable used by `pin-ucrt.ps1`.

Modern UCRT 10.0.26100.0 did not compile with this old toolchain. `pin-ucrt.ps1` adds a project-local build-tool override controlled by `TOURNAMENT_UT4_UCRT_VERSION`, verifies the requested version exists, and rebuilds UnrealBuildTool. No system SDK selection or registry override is required. This machine's MSBuild used installed framework assemblies with reference-assembly warnings; a pristine machine still needs validation.

With the recovered archive extracted and the prerequisites installed:

1. Copy `Plugins/TournamentBridge` into the source project's `UnrealTournament/Plugins/TournamentBridge` directory.
2. Run `scripts/pin-ucrt.ps1` with PowerShell.
3. Run `scripts/build-windows.ps1`.
4. Run `scripts/build-plugin.ps1`.

The build scripts select `UnrealTournamentEditor Win64 Development`, `-2015`, and UCRT `10.0.10240.0`. The plugin script also enables the plugin in the project's `.uproject`. The current scripts write logs under `UnrealTournament/Saved/Logs/Tournament` and preserve the native build exit code. Re-running these commands does not package a distributable game.

## Recovered material and versions

| Material | Version / size | Source |
| --- | --- | --- |
| Full source, content, Windows editor and build libraries | UE4.15, CL3228288; 41,601,952,464-byte ZIP; 77,733,605,444 bytes extracted | [UT4ever clean-master archive](https://downloads.ut4ever.box.ca/source/UnrealTournament-clean-master.zip) |
| Preserved Windows client/server archive | Shipping CL3525360; 10,321,694,322-byte ZIP | [UT4ever game archive](https://downloads.ut4ever.box.ca/game%20files/UT4.zip) |
| Preserved Linux dedicated server | Shipping CL3525360; 871,496,252-byte ZIP | [Epic's server archive](https://s3.amazonaws.com/unrealtournament/ShippedBuilds/%2B%2BUT%2BRelease-Next-CL-3525360/UnrealTournament-Server-XAN-3525360-Linux.zip) |

`scripts/remote_zip.py` inspects remote ZIP directories with bounded HTTP range requests, avoiding a full download for discovery. `scripts/extract_windows.py` performs path-checked, CRC-verified extraction on Windows. Extraction validates ZIP integrity; it is not independent publisher authentication.

The running Mac client and rebuilt source are different UT revisions. The new plugin is **not loaded into the Mac shipping client**. Do not assume that source-built clients and the preserved shipping server are network compatible, or copy DLLs between those versions.

## Remaining gates and limitations

- The preserved Linux dedicated-server experiment stopped at its first-run agreement. That Docker container remains stopped. The subsequent Windows source-development setup has an explicit local acceptance record and ran the server plus two clients.
- Verify the plugin in an authoritative match after that decision, including winning-kill ordering, one final ranking event, reconnects, duplicate notifications, and file-write failure handling.
- Verify two independent network clients, server rotation, and delayed spectating. Local bot combat does not establish multiplayer readiness.
- The preserved shipping client uses stock menus. The source build now includes the original Tournament HUD/menu, viewport streaming, settings, and diagnostics. Ticket validation, identity binding, rewards, anti-cheat ingestion, and settlement remain unavailable; no live money or account integration is enabled.
- UT4 now has a GPU-hosted browser streaming route with two exclusive game-control seats. It remains UE4.15, not a WebAssembly port or UE5 conversion. The ioquake3/OpenArena demo remains separate. See [browser hosting](browser-hosting.md) for architecture and the mixed asset-version caveat.
- The UT source and restricted assets have a dedicated Epic license. Finding a downloadable archive does not make them freely redistributable or authorize a separate commercial game. No recovered Epic engine/content was added to the public GitHub repository. Production distribution requires a suitable rights basis.

## Engine choice

This recovered Unreal Tournament project is UE4.15. Epic's [Unreal Engine 5.8 release](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available) is a separate engine release; the UT archive cannot simply be relabeled or opened as a verified UE5 game. The inspected [Open Tournament project](https://github.com/OpenTournament/OpenTournament) targets UE5.7 but its own license also restricts use to that project. A UE5 migration or independently licensed UE5 replacement remains a separate implementation decision.
