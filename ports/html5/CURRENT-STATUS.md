# Local browser beta: recorded status

Updated 2026-09-24. **Playable practice is demonstrated; the requested finished
beta is not yet verified.** The game executes locally as WASM/WebGL, not video
streamed from the Windows GPU. Licensed game payloads and raw operator evidence
remain private. Repository tests and shader compilation alone do not establish
gameplay or native visual parity.

## What has been observed

| Requirement | Evidence and remaining limit |
| --- | --- |
| Floor collision and movement | A matching corrected-optimizer build passed the exact Deck floor regression, horizontal movement, jumping and landing. This fixes the previously reported reproduction; it is not a claim about every surface or map. |
| Bots, combat and respawn | An earlier six-bot practice capture shows bot scores and two recorded player deaths, alongside a live first-person view at 100 health. This supports a bounded respawn observation, not a captured death-to-respawn timeline, player-shot kills or every weapon. |
| Menu and resolution | The current Supplement generation passed 1080p → 1440p → 1080p with matching native/canvas sizes, centered 16:9 layout, confirmed pause/resume and owned-browser exit 0. Its CSS presentation is scaled, not a full-screen performance measurement. Earlier cleanup-failed runs remain failed. Audio and direct world-clock freeze remain unmeasured. |
| Rotation | An earlier accelerated `GoalScore=1 / TimeLimit=1` practice fixture logged five completed alternating Deck/Outpost loads, continuing Ready samples and clean owned-browser exit. Its old boolean checker missed the logs. This does not establish default-duration or multiplayer rotation, or recertify newer generations. |
| Current rotation | The current Supplement package passed accelerated headless Deck → Outpost → Deck in 68.133 seconds: Ready epochs 1 → 2 → 3, matching 1080p dimensions, no HTTP/page errors, fifteen unchanged served pins and owned-browser exit 0. The browser NoMCP writer guard remains included. Default-duration and multiplayer rotation remain open. |
| Multiplayer | Historical two-client traffic and reconnect passed. Current-generation strict tests stopped on startup engine errors, despite observed network traffic and subsequent Deck loading. The matching source logs an error for a pending initial network connection; the entry map also reports missing reflection-capture data. These strict runs remain failed. A separate diagnostic retained only those exact startup errors, observed 30 seconds of two-client traffic and native-frame advancement, and reconnected one client through a new iframe while the other stayed Ready. It exited cleanly but explicitly did not claim clean engine acceptance. Combat and multiplayer travel remain open. |
| Character skinning | Captured browser programs and bound draw streams demonstrate an eight-influence GPU skinning path. This is not per-mesh identity, morph activation, pixel correctness or a measured FPS improvement. |
| Weapons and other assets | The dedicated Enforcer repair passed native Apply/fresh Verify, a new cook and package, and a browser roundtrip. The starting first-person gun now visibly has blue/metallic material detail in the captured scene instead of the earlier gray fallback. This is a bounded visual improvement, not a native-reference match. All six ordinary shader resources passed (15/16/16 samplers for each view); geometry and other slots were preserved. The preceding Grenade repair remains included, but its browser appearance is not yet verified. Other weapons, foot shadows, lighting, effects, animation and placement fidelity remain open. |

The [Bio Rifle body and grenade-ammunition repair](compat/SUPPLEMENT-MATERIAL-REPAIR.md) now passed native Apply/fresh Verify, fresh cook, packaging and browser observation. Twelve shader resources passed at 15–16 samplers. Nine scoped assets were saved; protected source packages, mesh geometry and vertex colors were preserved. The first-person Bio body now visibly has dark metallic surface detail instead of the prior white-gray fallback. The grenade view also shows detailed exposed rounds. Different spawn positions and lighting prevent a pixel-equivalent comparison; native parity, third-person fidelity and normal pickup/combat remain unverified. Bio glass was excluded from that asset repair; the separate engine-path milestone below does not yet establish native visual parity.

A newer, separate **scene-color diagnostic generation** completed its native/browser
builds, three-map cook and packaging. The cook recorded zero selected-family
failures and zero engine errors; **286 other material-failure lines remain**.
All 25 required cooked payloads matched their decoded archive entries, the
9,179-file archive integrity test passed, and the downloaded package hashes
matched. Original Bio glass materials were retained.

Its browser capture at 1080p → 1440p → 1080p recorded eighteen paired draws:
a scene-color encoder writes a separate texture, then a shader with the native
decode expression samples that texture while writing to a different color
attachment. Independent offline review confirmed the source and observed
bindings, complete framebuffers and correct dimensions. Shader compile/link
succeeded with extension-order warnings retained. All fifteen served pins
remained unchanged and the owned browser exited 0. This establishes the recorded
copy/decode draw path, **not Bio mesh identity, pixel correctness, native visual
parity, normal pickups/combat or FPS**. The private diagnostic is on port 8082;
it has not replaced the practice preview below.

The latest private playable preview is **http://127.0.0.1:8081/index.html**.
Its cook finished in 2,307.428 seconds with zero selected-family failures and zero
engine errors; **291 unrelated material-failure lines remain**. Packaging passed
the 9,179-file archive integrity test, exact staged-data-slice comparison and
decoded-byte comparison for all 23 required cooked entries. All three downloaded
package files matched their full hashes. The new 1,872,697,632-byte data file has
SHA-256 `fb28c01286a7e72472529d531d9b13b82f8b457cea0961aeb7d7a4089d3ee837`.
Runtime JS/WASM/memory are unchanged. Port 8080 retains the previous content for
comparison.

The current settings check passed in 47.243 seconds, and the weapon-view
collection finished in 47.671 seconds. Both retained all fifteen served-file
hashes and exited the owned browser cleanly. Weapon collection used a private
one-player fixture and the standard `Loaded` console command; it is not evidence
of normal pickups, player kills, sustained performance or every weapon.

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

- Enforcer pre-repair geometry and explicit four-slot baseline: native module 32 compiled; a fresh read-only report completed with both meshes, zero saves and unchanged selected bytes. Raw report `enforcer-mesh-native-2/report.log`, `1d65aec50a437c983da956a9524b38a2ba80a88daf71d9916009f9a08aa6a8ed`. Geometry matched the preceding process exactly. See [coverage and limitations](compat/ENFORCER-MESH-INVARIANT.md). This pre-repair checkpoint was followed by the scoped repair and browser observation below.
- Enforcer persistent repair tool: native module 33 built successfully in 14.594 seconds; raw result `enforcer-repair-native-1/build-result.json`, SHA-256 `711d6f8b449c3f600d16cf35f6c888939adadfad18f82e7d76cfda4095437eef`. The [fixed five-asset operation](compat/ENFORCER-MATERIAL-REPAIR.md) creates dedicated materials and changes only the two gun-body slots. Seven extracted-body host tests cover the bounded save/failure paths and mesh comparisons. This build-only checkpoint was followed by the native Apply/fresh Verify recorded below. The later cook/package and bounded first-person browser observation are recorded below; broader visual acceptance remains open.

- Enforcer native Apply/fresh Verify: Apply saved five assets in 123.052 seconds; fresh Verify saved zero in 114.564 seconds. Apply result `enforcer-repair-native-1/apply/result.json`, SHA-256 `2ae00aad8b9506dad8836ca81dfe91fcfdf88e12ea02a0629e6bff84486b5edd`; Verify result `enforcer-repair-native-1/verify/result.json`, `73abffe87cb3eca25bb66b8f0e4227cae11c5c7663ff1f4c5a4118e467f3ba0b`. Both views passed all three shader qualities; geometry, other material slots and 28 protected packages remained unchanged. This is serialization/shader evidence only. Port 8079 still serves the previous package with the visibly gray Enforcer.

- Enforcer cook: `enforcer-cook-1/result.raw.json`, `dd1834c7a16a9d9ef544de874a098a2265cd21acc9e16bd21e0667c731fc06ed`; package: `enforcer-package-1/result.json`, `c00bf5051523bb32e4287430191e43cbe4a03343db7bd0676efb40e1785bce41`. All fourteen required archive entries were decoded and matched to the fresh cooked bytes.
- Enforcer packaged browser rotation: `enforcer-rotation-review/run-1790212162998/report.json`, `9d2f248241896c229e821ed6f429a1b5821fd00576990f7ebdbc8bc7b3e1128d`. Starting screenshot: `33e0ad2bd38dfcef6331e978a12e50401958cd3bbb36dbc29f0bde3a0812624a`; ending screenshot: `3105a4fc15aa6ae0b58d7f596091bc9d4f85cc9ba0e7b6db808f467430c1f4e7`. Headless only; these images are not a new FPS benchmark or native-parity proof.

- Enforcer settings observation: `enforcer-settings-review/run-1790212598560/report.json`, `a952c172718c2527f6a88d890538d5852760a21e75d8299682c8acc5185002dd`. Both UI resolution/pause cycles and fifteen served-file comparisons completed; browser close/kill timed out, so the run is **failed**, not acceptance. A separate OS snapshot found its owned browser PID/process group absent; only its remaining Node runner was terminated. No FPS, pointer-lock, player-shot or jump-outcome claim.


Latest Supplement generation private evidence (raw reports retained):

- Cook: `supplement-cook-1/result.raw.json`, `5bd2861742e049618ab5f4c56155daa54492df6bf41c99fef4e2b06b3036e81e`.
- Package: `supplement-package-1/result.raw.json`, `5b4a2ab4922715e1d398797a8877c26831f7a50a65628f50f74f75625aac5751`.
- Downloaded-package review: `supplement-package-1/independent-download-review.json`, `f293a5e228a4391e09f067b95511a9ddfcdcd072760d4a08da2fb9d6b42b79f4`.
- Weapon views: `supplement-weapon-views/run-1790223271824/report.json`, `231b5494f8c0fca5ab862467e771ad283a338d4ffa2595bf46e2e565bc2e6ff3`.
- Settings: `supplement-settings-review/run-1790223354308/report.json`, `32991f54742fd0f8d33e730cb0544485f5d83d501cde31e821f7345dca2f15d1`.
- Rotation: `supplement-rotation-review/run-1790223635305/report.json`, `95ec177e40d08e158a38ffd999e4110173f9ce91cd2e3873bc2c9f859e32fa1c`.
- Failed strict multiplayer diagnostic: `probe-supplement-multiplayer-diagnostic/run-1790223552912/report.json`, `177a498f8064e8ad50ca30ec1f232d1baadfe1265737eb26c81913202dc097ce`.
- Multiplayer observation with retained startup errors: `probe-supplement-multiplayer-observation/run-1790223839337/report.json`, `1d6691c945f5eecc30bca425dd9992394f0618a83c2548a34bae49e7d202689b`. Status is `diagnostic-connectivity-observed`, **not** clean engine acceptance; 30.075-second input-dispatch interval and 73.459-second total, new iframe/postRun/socket for reconnect, other client remains Ready, owned-browser exit 0, gateway returns to zero clients. No player-input consumption, kills, respawn or travel claim.

Scene-color diagnostic generation evidence (private):

- Cook: `scene-color-cook-1/final/result.json`, `3617306c2e656e0cde2b28c88d877ea4a2689d30edd58c2bf5b1fe6b2a8229f6`.
- Package: `scene-color-package-1/final/result.json`, `276cb18a1b37adc63fc1bfeef37b9c703dadf8a40d1bacb0d00b379e482fe100`.
- Browser generation: `scene-color-browser-review/generation-receipt-1.json`, `55974abae80a6d898a47ca990f2be803e797057e8607d92948b499feae71074b`.
- Raw draw capture: `scene-color-browser-review/runs/run-1790239141816/report.json`, `5eea39c8f03d13ff84524a9e26926e939ed0785e367c8ee0e1761d2cb51b4205`.
- Separate source/state qualification: `scene-color-browser-review/runs/run-1790239141816/offline-qualification-main.json`, `2bc12e0fae8978cc7b3770800eb0b1ffa950b66c2a32f40db1792c6bf58df8e5`.
