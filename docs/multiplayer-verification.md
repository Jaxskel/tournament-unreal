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

## Runtime record — 20 September 2026

The recovered Windows source build ran one authoritative TournamentDeathmatch server and two offscreen GPU clients, streamed to two independent browser sessions through the public HTTPS gateway.

- Both clients joined Deck, appeared as separate non-bot participants, and received independent frames. Normal streamed play on Deck was observed around 21–22 FPS at 960×540 before remaining cache work completed.
- Browser capture, movement, aiming, firing, deaths, respawning, Escape menu, settings sensitivity changes, and absolute menu close were exercised.
- A complete Deck round produced 35 ordered records: one match start, 33 kills, and one final ranking. `verify-events.py` accepted the completed log. Both human clients were present in the server scoreboard and recorded deaths.
- Deck → Outpost rotation was observed on the server. Both clients loaded Outpost and resumed frames after initial asset preparation. Source-built character models were visible; the recovered archive uses available fallback content where optional EpicInternal packages are absent.
- First-run texture/shader compilation initially produced placeholder materials and long map loads. The host caches were prepared before the final demo handoff. Cached map loads and public input must still be measured separately from cold-start asset preparation.
- Native modules and the offscreen D3D11RHI patch compiled and linked. PowerShell launcher/INI/consent tests, eight event-validator tests, and 24 browser/gateway tests passed.
- Live rejoin after leaving a menu open returned to game input with the menu closed. Two occupied seats rejected a third join with HTTP 409. Native Diagnostics → Reconnect reloaded Deck in 1.34 seconds; both streams were healthy afterward.
- Final screenshots show distinct PlayerOne and PlayerTwo viewpoints, both alive, with textured Deck and approximately 20–22 streamed FPS.
- Gateway tests include three-second liveness reset, absolute menu state, seat acquisition after a menu was left open, TCP reconnects, strict origin/input/token checks, and capped mouse transmission at 360/1000 Hz display loops.

Remaining production checks: independent Firefox/Safari performance, extended soak testing, a permanent host/domain, audio transport, delayed spectators, Tournament-issued tickets/identity, account restrictions, reward configuration/settlement, and anti-cheat ingestion. A successful demo is not production certification. Current demo seats are shared native players and award no platform money or points.

The preserved Mac shipping client (CL3525360) is separate. The browser demo streams the recovered source build and its Tournament plugin, not that preserved client.

## Recovery verification — 20 September 2026 (EDT)

The previously shared host had stopped after a native server crash, leaving HTTP available but both game sources absent. The old supervisor exited with the failed game. The first attempted mitigation (removing the character ceremony) was insufficient. Windows CDB analysis of the minidump identified the invalid replicated reference at the `AUTPlayerState::FavoriteWeapon` offset. The final build uses `TournamentGameState` to skip cosmetic weapon highlights and retains the frag standings.

Observed with the rebuilt plugin, not just socket fixtures:

- Two completed short rounds rotated Deck → Outpost → Deck without a native restart. Both event logs validated: Deck had 9 records (start, 7 kills, final ranking); Outpost had 6 (start, 4 kills, final ranking).
- Through the public HTTPS address, four warm Play-to-first-drawn-frame measurements were 296, 246, 138, and 137 ms. This measures initial video display, not input latency; first-ever native startup remains slower.
- An owned dedicated server was deliberately terminated at 03:15:03 UTC. The supervisor detected the exit and launched a replacement group without a manual task restart. The existing browser retained its seat and resumed frames. A second browser pressed Play during the outage, received the recovery status, and entered automatically without another click. Both then displayed live frames at approximately 19–22 FPS.
- Native plugin compilation, 27 Node tests, 8 event tests, and PowerShell launcher checks passed. Browser checks showed a rendered game and no reported page errors.

The demo remains dependent on the Windows GPU host staying awake and online. This verification covers short rounds and a forced crash, not an extended unattended uptime guarantee. Recovery takes native initialization time; keeping both seats preloaded enables fast normal joins.
