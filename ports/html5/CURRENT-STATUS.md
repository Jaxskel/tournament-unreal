# Local browser beta: recorded status

Updated 2026-09-23. **Playable practice is demonstrated; the requested finished
beta is not yet verified.** The game executes locally as WASM/WebGL, not video
streamed from the Windows GPU. Licensed game payloads and raw operator evidence
remain private. Repository tests and shader compilation alone do not establish
gameplay or native visual parity.

## What has been observed

| Requirement | Evidence and remaining limit |
| --- | --- |
| Floor collision and movement | A matching corrected-optimizer build passed the exact Deck floor regression, horizontal movement, jumping and landing. This fixes the previously reported reproduction; it is not a claim about every surface or map. |
| Bots, combat and respawn | An earlier six-bot practice capture shows bot scores and two recorded player deaths, alongside a live first-person view at 100 health. This supports a bounded respawn observation, not a captured death-to-respawn timeline, player-shot kills or every weapon. |
| Menu and resolution | Native standalone pause/resume was observed twice, including a paused 1080p→1440p change. The latest headed practice capture separately confirmed native window, canvas and drawing-buffer dimensions at both resolutions. Audio behavior and direct world-clock freeze were not measured by the pause probe. |
| Rotation | An earlier accelerated `GoalScore=1 / TimeLimit=1` practice fixture logged five completed alternating Deck/Outpost loads, continuing Ready samples and clean owned-browser exit. Its old boolean checker missed the logs. This does not establish default-duration or multiplayer rotation, or recertify newer generations. |
| Current rotation retry | The [browser NoMCP writer guard](CLOUD-STATS.md) passed native build/conversion and a separate accelerated headless Deck → Outpost → Deck check: advancing Ready epochs, no HTTP/page errors, unchanged inputs and owned-browser exit 0. This resolves the recorded legacy stats-404 reproduction. The private port-8078 practice preview now serves that runtime with the previous content package; all fifteen served file hashes match the passing capture. Default-duration and multiplayer rotation remain open. Earlier failed runs remain failed. |
| Multiplayer | Two browser clients joined, sustained simultaneous traffic and native frames for about 27 seconds, then one reconnected while the other remained connected. Network combat, complete matches and multiplayer travel remain open. |
| Character skinning | Captured browser programs and bound draw streams demonstrate an eight-influence GPU skinning path. This is not per-mesh identity, morph activation, pixel correctness or a measured FPS improvement. |
| Weapons and other assets | Wrong/gray weapon materials remain visible in the playable generation. The scoped Grenade repair saved exactly two new material/function packages and one parent change, preserving 22 other packages. A fresh process verified all 18 selected instances and six Grenade shader resources with zero saves. Its fresh cook and packaged archive passed their scoped checks, and that package passed a new accelerated browser roundtrip. The current port-8079 preview contains the repaired content; actual Grenade appearance is not yet verified. The Enforcer remains visibly gray. The dedicated Enforcer repair has now saved exactly three new materials and the two gun meshes. A fresh Unreal process verified the saved material semantics, geometry and all slot metadata, with all six ordinary shader resources passing (15/16/16 samplers for each view), zero additional saves and unchanged identities/hashes for the other 28 tracked packages. Its cook, package and browser appearance are still pending. Other weapon, foot-shadow, lighting, effects, animation and placement fidelity remain open. |

The latest private playable preview is **http://127.0.0.1:8079/index.html**. Its
Grenade content cook finished in 2,266 seconds with zero selected-family failures
and zero engine errors; 388 unrelated material-failure lines remain recorded.
Packaging matched all six staged data slices, and the archive integrity test
passed for 9,175 files. The separate legacy list command returned 1; its output
was checked independently for all nine required map, registry, shader and repaired
asset entries. A 68.818-second accelerated headless Deck → Outpost → Deck run
then passed with advancing epochs, 1920×1080 native/canvas dimensions, no
HTTP/page errors, unchanged assets and owned-browser exit 0. This is not a new
FPS, weapon-appearance or default-duration-match result. Port 8078 retains the
previous content for comparison.

The old unresolved-floor wording in the September 21 build snapshot is
superseded by the bounded movement result above. Other historical failures remain
part of the record; they are not silently converted into successful runs.

## Performance and loading

Latest valid headed practice evidence is one continuous six-bot session, with
1080p measured before 1440p. Each phase below lasted 30 seconds. These rates are
native ticks and requestAnimationFrame callbacks, **not directly measured
presented FPS or GPU execution time**.

| Internal resolution / workload | Native ticks/s | rAF callbacks/s | Engine-callback interval p95 / worst |
| --- | ---: | ---: | ---: |
| 1920×1080 stationary | 91.10 | 91.12 | 13.1 / 72.1 ms |
| 1920×1080 movement/fire | 97.97 | 97.96 | 12.8 / 205.9 ms |
| 2560×1440 stationary | 119.10 | 119.10 | 10.4 / 34.3 ms |
| 2560×1440 movement/fire | 106.63 | 106.66 | 11.6 / 247.7 ms |

Native Ready arrived after 15.7752 seconds. Capture, focus, visibility, native
pause status and matching dimensions passed; served inputs remained unchanged
and the owned browser exited 0. Presentation was a 921×518 CSS canvas inside a
1280×800 window, not a full-screen display benchmark. Scenes were not replayed
deterministically, so the higher 1440p rate is not a controlled resolution result.
The 120-at-1080p / 60-at-1440p targets remain unverified; the observed long stalls
also leave the smooth-pacing requirement unresolved.

A separate [startup packaging experiment](STARTUP-COMPRESSION.md) reduced median
headless launch-to-Ready from 13.1367 to 12.0100 seconds across six runs (8.58%),
at the cost of 60,223,598 bytes. The [archive verifier](STARTUP-PACKAGING.md)
confirmed all 9,173 entries: the twelve selected decoded payloads and all
unselected stored payloads were preserved. The candidate is not promoted. This
is neither cold-network timing nor a gameplay-performance result.

## Remaining acceptance

Finish material repair, fresh cook and visual comparison; rerun collision and
gameplay on the resulting coherent generation; verify player damage/kills, all
supported weapons, audio, default-duration rotation and sustained multiplayer
combat/travel; measure frame pacing at the intended display sizes. Actual Safari
and broader browser gameplay remain unverified. The complete build recipe still
needs a fresh clean-checkout replay. Real rewards and Tournament production
identity/anti-cheat integrations remain disabled pending staging contracts.

Raw evidence identifiers and SHA256 digests (private artifacts, not bundled):

- Movement: `scene-motion-1790035587316/report.json`, `92a0390d18b6a5a085e12f4db5afcde0a2b921913d6a873b74d96b3f1a5e15fc`.
- Bot combat/respawn observation: `scene-motion-1790035783599/report.json`, `09cbbb80c919800ffd75bc1178a9f72f4d14228a9848db81bcb93bd4922e857b`.
- Associated death-count screenshot: `scene-motion-1790035783599/scoreboard.png`, `6b196c1e97206292268dd560e634ce0583486219f0c1620282afb474bab2da9b`; live-view screenshot: `scene-motion-1790035783599/end.png`, `8317cd545d2131d88eee19848de2872cbb8e949cc5fd8f48c8148f8157c79158`.
- Pause: `scene-motion-1790039549298/report.json`, `bf18693609bf7346a5d161d579b9c5d6baf11d30ca2f03cf3d21b2af9b926cba`.
- Historical rotation: `scene-motion-1790036016516/report.json`, `cf8fb4b5fb1ec42d2347da01297b529c613f03a66f674570d51aff2cdcc589a5`.
- Cloud-stats guard rotation: `rotation-current-review/run-1790197355494/report.json`, `de58175b7a784a875f31e9c79e4a767f73b91c474247efcb383125e18111005e`.
- Grenade packaged browser rotation: `rotation-current-review/run-1790200036022/report.json`, `1b1b3a81f5597c7a2b7089b1e533ffd8844fcadda9fbaf4f4f4f6bec822fd1d8`.
- Grenade cook: `grenade-cook-1/result.raw.json`, `1f54d7c27bef7ecb878acdaeba71bb22b87a68ca0e0dc18f703f0d3a30b90443`; packaging: `grenade-package-1/result.json`, `35f59fa7eacebdb95edc3088a2ec98302183fc047cdc464ecc00da43ba9c0dca`.
- Grenade fresh native verification: `weapon-grenade-repair-build/verify1/report.log`, `190092c8c853e2e7bf30b15d5e9363321e55d3a49c498b05b11d56f82b8b8ddf` (shader/serialization evidence, not browser appearance).
- Multiplayer lifecycle: `mp-gameplay-3D9viO/report.json`, `e0ea1e36aef1a0b4a8e8448da43d02358ad6036ee3cbe477fbe1efcf8eaaeb4b`.
- Headed performance: `comparable-perf-1790130131271/report.json`, `eda525798efda50bb20897da65df70b01959ef9c009bab311ef2b63a8560aefd`.
- Six-run startup comparison: `startup-file-read-review/comparison-run-1/report.json`, `9bcdd6d36b3cf24f3572477e0336c63a3b25fb548cc9c654e28c282725be5f85`.
- GPU draw source qualification: `gpu8-r001-diagnostic/observation-1/offline-source-qualification.json`, `2956d8bfcb049145b92af09012ff853e6c968e28f4646b3d25cce9808d6a6e6d`.

- Enforcer pre-repair geometry and explicit four-slot baseline: native module 32 compiled; a fresh read-only report completed with both meshes, zero saves and unchanged selected bytes. Raw report `enforcer-mesh-native-2/report.log`, `1d65aec50a437c983da956a9524b38a2ba80a88daf71d9916009f9a08aa6a8ed`. Geometry matched the preceding process exactly. See [coverage and limitations](compat/ENFORCER-MESH-INVARIANT.md); material-slot changes, save-roundtrip verification and browser appearance remain pending.
- Enforcer persistent repair tool: native module 33 built successfully in 14.594 seconds; raw result `enforcer-repair-native-1/build-result.json`, SHA-256 `711d6f8b449c3f600d16cf35f6c888939adadfad18f82e7d76cfda4095437eef`. The [fixed five-asset operation](compat/ENFORCER-MATERIAL-REPAIR.md) creates dedicated materials and changes only the two gun-body slots. Seven extracted-body host tests cover the bounded save/failure paths and mesh comparisons. This build-only checkpoint was followed by the native Apply/fresh Verify recorded below. Cook and browser visual acceptance remain pending; the current playable package is unchanged.

- Enforcer native Apply/fresh Verify: Apply saved five assets in 123.052 seconds; fresh Verify saved zero in 114.564 seconds. Apply result `enforcer-repair-native-1/apply/result.json`, SHA-256 `2ae00aad8b9506dad8836ca81dfe91fcfdf88e12ea02a0629e6bff84486b5edd`; Verify result `enforcer-repair-native-1/verify/result.json`, `73abffe87cb3eca25bb66b8f0e4227cae11c5c7663ff1f4c5a4118e467f3ba0b`. Both views passed all three shader qualities; geometry, other material slots and 28 protected packages remained unchanged. This is serialization/shader evidence only. Port 8079 still serves the previous package with the visibly gray Enforcer.
