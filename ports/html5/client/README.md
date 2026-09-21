# Local UT4 browser launcher — experimental

Original launcher UI for the locally compiled UT4 beta, UE4.15 CL3228288. This directory is independent of `browser/public` and the public streaming demo. There is no identity, wallet, reward, map-selection or official-site navigation. **A successful compile, initialized runtime or nonzero main-loop rate does not establish working gameplay.** No engine or packaged game assets are included.

## Integrate locally

1. Serve this directory with an HTTP static server, including `.mjs` as JavaScript (for example `python3 -m http.server 8000 --bind 127.0.0.1` from this directory). Do not open `index.html` as `file://`.
2. Copy `runtime.example.json` to `runtime.json`. Change its file names/URLs to match the actual emitted build and completed asset package. The example names are placeholders. Host those files on the **same origin**; subdirectories are supported. No final game availability is required to develop/test the UI.
3. Set the heap explicitly if needed: `1610612736` bytes is **1536 MiB, an experiment**, not an established requirement. Legacy asm.js receives `Module.TOTAL_MEMORY`; `INITIAL_MEMORY` is also supplied for compatible future outputs. Omit `totalMemory` to retain the generated runtime's default. No automatic heap/resolution adjustment is performed.
4. Set `websocketUrl` to the operator's packet gateway (e.g. `ws://127.0.0.1:9080/game`). The launcher sets `Module.websocket = {url, subprotocol: 'binary'}`. This carries game packets, not video. It neither starts the gateway nor proves a network handshake. Allow the static-server origin in the gateway's existing configuration. HTTPS requires `wss://`.
5. Optionally set `multiplayerArguments` to `["127.0.0.1:7787"]` for the local authoritative server experiment; keep `websocketUrl` at `ws://127.0.0.1:9080/game`. The server address goes into engine arguments, while the WebSocket URL is the packet transport. Neither is editable in the menu. Omitted or empty multiplayer arguments leave Multiplayer disabled.
6. Open the local page, choose Practice or configured Multiplayer, select 1080p or 1440p in Settings, and launch. Stop/Retry tears down the entire engine frame. The public demo is unchanged.

The static server must serve actual asset bytes and 404 missing files, not an HTML fallback. HTTP compression is supported; correct `Content-Encoding` and `Content-Length` produce meaningful browser transfer progress. Unknown totals remain indeterminate with a received-byte count. Progress is per file, then separate indeterminate compilation/dependency stages. Loading is sequential and never fabricates an overall percentage. Use CSP that permits same-origin scripts, `blob:` scripts/data fetches, and the configured game WebSocket; Emscripten/WASM may also need eval/WASM compilation permissions. No CSP policy is changed by the launcher.

## `runtime.json` version 1

| Field | Contract |
| --- | --- |
| `version` | Required integer `1`. |
| `format` | Required `asmjs` or `wasm`; both remain experimental. |
| `files` | Required object: exact name requested by generated runtime → same-origin URL relative to `runtime.json`. Include **all** `.js`, `.data.js`, `.data`, `.js.mem`, optional `.wasm`, metadata or other runtime sidecars. No cross-origin URLs/redirects. |
| `engine` | Required key in `files`; classic, non-modularized engine script. |
| `supportScripts` | Optional ordered `files` keys, e.g. `Utility.js`. Loaded first. |
| `dataScripts` | Optional ordered `files` keys for Emscripten packagers. Loaded after support scripts, before engine. |
| `memoryInitializer` | Optional `files` key for the original `.js.mem`; preloaded via `Module.memoryInitializerRequest`. Retain this for converted legacy WASM when the old runtime still requires it. |
| `wasmModule` | For converted legacy WASM: `files` key, downloaded with byte progress and asynchronously compiled using `WebAssembly.compile`. Sets `Module.wasmModule` **before** loading the engine wrapper. |
| `wasmBinary` | Alternative future conventional Emscripten WASM `files` key; passed as a `Uint8Array` to `Module.wasmBinary`. Mutually exclusive with `wasmModule`. This path is adapter coverage only, not a validated newer-linker engine. |
| `packageFiles` | Optional explicit array of unique keys in `files`, consumed by `dataScripts`. These archives bypass eager Blob downloads: the emitted packager requests their declared same-origin URLs directly as ArrayBuffers. Cannot name or alias scripts, memory initializers or WASM; requires a data script. For the legacy UT4 package use `["UnrealTournament.data"]`. |
| `totalMemory` | Optional byte count, ≥16 MiB, multiple of 65536. Must match converted WASM's exact memory import limits. The converter owns `wasmMemory`, `buffer`, and effective `TOTAL_MEMORY`; the launcher does not allocate or override its imported memory. |
| `arguments` | Optional array of Practice engine argument strings. Defaults to the TournamentBridge Deck practice URL below. Existing resolution/window flags are replaced with selected `-ResX`, `-ResY`, `-ForceRes`, `-Windowed`. No UI map selection. |
| `multiplayerArguments` | Optional operator-configured array of engine argument strings, validated like `arguments` (strings without NUL characters). Omitted or empty disables Multiplayer; malformed values fail manifest validation. Used instead of Practice arguments; receives the same fixed resolution/window flags. |
| `bindings` | Optional allowlisted array of the exact C export names below. Empty by default. Controls require both `Module.cwrap` and the corresponding `Module._Name` exports; settings wait for `TournamentBrowserReady() === 1` and a positive `TournamentBrowserSessionEpoch()`. |
| `websocketUrl` | Required absolute `ws://` or `wss://` game-packet endpoint without credentials, query or fragment. May use another port/host. |
| `initializationTimeoutMs` | Optional 1000–900000; default 180000. Covers compilation/startup until `postRun`; failure offers manual clean retry. Downloads separately fail after 60 seconds without progress. |

For `convert-asm-to-wasm.py` output, change the example's `format` to `wasm`, point `engine` at its converted JS, add `"wasmModule": "TournamentBrowser.wasm"` and the corresponding `files` entry. Keep `memoryInitializer` pointing to the original `.js.mem`. **Do not add an `instantiateWasm` hook.** The wrapper asynchronously instantiates the compiled module and exposes `Module.gameRuntimeReady`. Rejection is reported; fulfillment and `script.onload` are not readiness signals. The launcher waits for normal `postRun`. A wrapper that omits those normal lifecycle hooks must be adapted before use here.

The practice default retains the Tournament HUD, game mode, mutator and one human plus six bots:

```text
/Game/RestrictedAssets/Maps/WIP/DM-DeckTest?Game=/Script/TournamentBridge.TournamentDeathmatch?Mutator=TournamentBridge.TournamentBridgeMutator?BotFill=7?MaxPlayers=7?LAN=1?RequireReady=0?MaxPlayerWait=3?Difficulty=3
```

The initial package may contain only Deck. Tournament rotation can require Outpost in a later completed cook; this launcher does not claim rotation assets are present and does not provide map selection. There are no rewards.

### Practice and bounded multiplayer

Practice retains `arguments` unchanged, defaulting to the Deck URL above for one human and six bots. Multiplayer exclusively uses `multiplayerArguments`; it does not inherit the Practice URL or bot options. The native authoritative server owns multiplayer rules. The sample manifest leaves Multiplayer disabled. To opt into the local connection experiment, merge these fields into your actual manifest:

```json
{
  "multiplayerArguments": ["127.0.0.1:7787"],
  "websocketUrl": "ws://127.0.0.1:9080/game"
}
```

The menu checks the same-origin manifest for availability without loading engine assets. Each launch, Retry and Reconnect reads and validates the manifest again. Selection is stored in `tournament.local-ut4.mode` (page memory if storage is unavailable), retained through reload/clean Retry/Reconnect, and locked until Stop. Reconnect creates a fresh iframe/runtime and uses the same mode and selected resolution; it is a manual connection attempt, not a connection-status detector. Removing configuration causes a clear error without falling back to Practice or downloading game assets. Stop permits choosing Practice again.

Multiplayer keeps its engine loop running while the menu is open, including when native bindings are absent, so the launcher does not pause client networking. Input capture/release and optional native ReleaseInput still apply. No host input, accounts, rewards, automatic reconnect, server startup or gateway changes are provided. **Argument delivery and fixture lifecycle tests do not prove a handshake, replication, server travel, reconnect success or gameplay.**

### Optional TournamentBridge C ABI

Add only exports that the build actually provides to `bindings` (include `TournamentBrowserReady` and `TournamentBrowserSessionEpoch` for settings). Every cwrap return/argument type is `number`; integer vs double follows the C export. Unknown names are rejected; no arbitrary commands execute.

| Export | Arguments | Result/use |
| --- | --- | --- |
| `TournamentBrowserReady` | none | int, `1` means world + viewport exists |
| `TournamentBrowserSessionEpoch` | none | double, positive controller generation when ready; `0` unavailable. Native implementation uses weak object identity to detect controller replacement even with address reuse. |
| `TournamentBrowserSetResolution` | width, height | int, `1` accepts 1920×1080 or 2560×1440 |
| `TournamentBrowserWidth`, `TournamentBrowserHeight` | none | int, actual viewport size |
| `TournamentBrowserSetSensitivity` | double | int, `1` accepts sensitivity, clamped to 0.005–0.5 |
| `TournamentBrowserSetVolume` | double | int, `1` accepts volume, clamped to 0–1 |
| `TournamentBrowserReleaseInput` | none | int, `1` releases input |
| `TournamentBrowserFrame` | none | double, native `GFrameCounter` (displayed as a count, not fabricated FPS) |

Exports are discovered after runtime initialization and polled for readiness. Saved settings apply only after Ready returns 1 with a positive session epoch; a setter returning 0 is retried. Successful unchanged values are not reapplied within an epoch. An epoch change clears the applied cache and reapplies saved settings, even if readiness never went false between polls. A new epoch also queues ReleaseInput when the menu is open. Missing exports are never passed speculatively to old `cwrap` because that can abort. Unavailable controls stay disabled. No saved audio/sensitivity value means the launcher preserves the native value until the user chooses one; slider placeholders are labeled as unset. Native resolution changes update the drawing buffer only after the actual Width/Height getters agree. If the setters/getters are absent, resolution remains a next-launch request. Menu entry also calls the optional ReleaseInput binding; release is queued if the world is not ready yet.

Each launch defines `Module.canvas`, `arguments`, `preInit`, `preRun`, `postRun`, `onRuntimeInitialized`, `onAbort`, `onExit`, `monitorRunDependencies`, `setStatus`, `noImageDecoding: true` and `noAudioDecoding: true` before loading scripts. Bootstrap assets are fetched once and exposed through frame-owned Blob URLs. Explicit `packageFiles` bypass that Blob stage: `locateFile` returns only their declared same-origin URL, and the legacy packager downloads each archive once as an ArrayBuffer for its normal filesystem mount. Package requests retain byte progress, a 60-second inactivity watchdog, HTTP/HTML/empty-response errors, and cancellation on Stop. Undeclared requests still fail explicitly. This requires no `getPreloadedPackage` hook or generated-engine edit. Bootstrap Blob URLs are revoked after `postRun`, once startup dependencies have consumed them. Stop/Retry/Reconnect synchronously pauses the old loop, aborts tracked requests, releases URLs and bindings, then removes the frame; actual realm/heap collection remains browser-controlled. Large mounted buffers, WASM compilation and heap allocation still require substantial memory.

## Resolution, input and measurement

- A separate WebGL 1 probe requires at least **16 fragment, 8 vertex and 24 combined texture slots** before downloading assets. Unsupported limits or unavailable WebGL produce an actionable error and Retry. Passing this preflight is not validation of the actual game context or cooked shaders.
- The selected drawing buffer is **1920×1080 or 2560×1440**, stored under `tournament.local-ut4.resolution`. Resizing or fullscreen changes only CSS dimensions: viewport and canvas stay centered at 16:9. The launcher never uses device pixel ratio or automatic resolution reduction. A selection changed during a launch applies through the optional ready native binding, otherwise on the next launch.
- `-ResX/-ResY` request the engine resolution. When global `UE_JSlib.UE_GSystemResolution_ResX/Y` getters exist, their actual values are shown alongside the drawing buffer. A mismatch is reported, not hidden by resizing over the renderer. The async converter can make `UE_JSlib` closure-local; getters then report unavailable. Actual renderer agreement still needs full-game validation.
- Return to engine restores keyboard focus; Capture mouse or clicking the canvas requests pointer lock on a user gesture. Escape, native pointer release, app focus loss and Menu release the pointer and expose controls. Capture denial leaves Menu accessible. Settings is inline and dismissible; no focus trap. Held keys are released when opening the menu. In Practice without configured native bindings, a matched pair of exported pause/resume functions pauses the local loop. With native bindings, the loop keeps ticking so world readiness and live settings can complete while input is released. A menu never claims to pause a multiplayer server. Stop always disposes of the frame.
- Audio/sensitivity sliders appear only when their allowlisted exports exist and enable only when Ready is true with a valid session epoch. These are direct native settings, with no arbitrary console commands. `noAudioDecoding` disables Emscripten's preload decoder, not UE audio itself. Actual full-engine audio and sensitivity still need validation.
- `Module.preMainLoop/postMainLoop` measure **completed engine main-loop callbacks**. The HUD shows callback cadence, mean interval, p95 interval and mean CPU callback duration over a rolling two-second window. No standalone animation loop feeds this counter. A timer only publishes accumulated samples. Uninitialized, warming, paused/stalled and unresponsive states have no numerical FPS. This is not presented-frame/GPU timing or proof of gameplay. Future builds must retain these incoming Module hooks. Legacy behavior is documented in [Emscripten 1.36.13's browser library](https://github.com/emscripten-core/emscripten/blob/1.36.13/src/library_browser.js).

## Tests (no final engine required)

```sh
cd ports/html5/client
npm ci
npx playwright install chromium
npm test
# Or use installed Google Chrome:
CHROME_CHANNEL=chrome npm test
# Include native pointer lock capture/release (skipped in headless mode):
HEADED=1 CHROME_CHANNEL=chrome npm test
# Pure contract/metrics tests only:
npm run test:unit
```

The test server supplies its own `runtime.json` and clearly labeled fixtures. Tests exercise real HTTP/Blob downloads, `.data.js` ordering and file loading, `.mem` handoff, configurable memory, Practice/Multiplayer argument isolation, mode persistence through reload/retry/reconnect, configuration removal, pointer capture/release and denial, Escape/settings, fixed resolution through reload/window/fullscreen changes, explicit callback metrics, errors, timeouts, clean retry and asynchronous WASM adapter behavior. **Fixtures are not UT4 gameplay or game performance evidence.** No test invokes the final engine, build, cook, gateway or public demo.

Native pointer capture/release runs with `HEADED=1`; headless mode explicitly skips that one subtest. The test grants pointer-lock permission only in its isolated browser context and disables Playwright focus emulation for that check. Denial recovery and Escape/menu tests run in either mode. User browser permissions are not changed by the launcher.

Remaining integration gates: complete package, actual Deck rendering/materials/input/audio, memory sufficiency, engine resolution agreement, main-loop instrumentation in the full runtime, network travel/handshake and reconnect, and browser coverage beyond the tested desktop browser. A blocked synchronous engine can also block same-process UI/timers; frame isolation makes ordinary failures recoverable but is not a worker/process watchdog.

## Opt-in real-runtime verification (separate from fixtures)

`npm run verify:runtime` drives the existing launcher and its actual `runtime.html` iframe with Playwright. It does not serve, substitute, bundle or copy engine assets, edit the manifest, start a server/gateway, or use a fake engine. **Do not run against an incomplete package.** Supply the existing private operator launcher URL and its exact same-origin `runtime.json` explicitly. Use a trailing slash or `index.html` for the launcher URL. The manifest must list all nine current C exports, including `TournamentBrowserSessionEpoch`; newer builds must retain the actual Emscripten main-loop hooks. This is independent of `npm test` and requires the caller's installed Chrome (or Playwright Chromium via `--channel chromium`).

Create an output directory **outside the repository** yourself, then run when the engine and package are ready:

```sh
npm run verify:runtime -- \
  --url http://127.0.0.1:8000/index.html \
  --manifest-url http://127.0.0.1:8000/runtime.json \
  --out-dir /absolute/existing/private/verification-results \
  --resolution both --seconds 30 --warmup-seconds 5 \
  --ready-timeout-seconds 300 --stall-seconds 15
```

`--resolution both` runs independent fresh browsers at 1920×1080 and 2560×1440; either can be selected alone with `1080p` or `1440p`. Default is headless; `--headed` records a headed run. `--mode multiplayer` uses the operator's existing `multiplayerArguments` and gateway configuration, without claiming a handshake. No host input or connection override exists. `--seconds` accepts 5–600 measured seconds; warmup is 0–120 seconds; world-readiness timeout is 10–1800 seconds. Individual browser operations also have bounded deadlines so an unresponsive engine fails rather than hanging indefinitely. No minimum FPS target is imposed. The configurable 2–120 second stall limit is a liveness check, not a performance guarantee.

The verifier requires actual postRun followed by `TournamentBrowserReady() === 1`, a positive session epoch, and all nine exported functions with the current numeric ABI. It rejects `noInitialRun`, known fixture inputs, missing exports, unready worlds, invalid counters, and changing controller epochs during measurement. It calls the real resolution, sensitivity (`0.04`), volume (`0.4`) and ReleaseInput setters and requires return value `1`; setter acceptance alone does not establish audible output or input feel. A fresh browser profile contains these test settings. Native viewport dimensions, `Module.canvas` dimensions and the **actual engine WebGL drawing buffer** must agree with the selected resolution initially, after window resizes, and throughout measurement. The probe observes the engine's own `getContext` result; it does not create a substitute context. It does not exercise pointer lock or fullscreen in this harness.

Timing wraps the existing `Module.postMainLoop` callback and records native `TournamentBrowserFrame()` advances. Node/browser polling never manufactures frames. The JSON report includes native ticks per configured measured interval, p95 observed tick interval, completed callback count and raw tick intervals. The first tick supplies a timestamp, not an invented interval. Multiple native ticks between callbacks fail because exact per-tick p95 would be unresolved; overwritten hooks, insufficient samples, lost WebGL context and native tick stalls also fail. These are engine tick observations, **not presented/GPU FPS, server tick rate or a gameplay benchmark**. Headless mode, instrumentation and browser polling can affect measurements.

Except for the three narrowly matched legacy notices below, any console error, UE error/fatal diagnostic, DebugBreak, assertion/abort, uncaught page error, runtime error message, failed HTTP/network request, crash/disconnection or world-readiness timeout fails the run. An engine process exit of zero or a fulfilled initialization promise never overrides a recorded failure. The operator manifest is hashed and checked against the launcher's actual manifest responses to reject changes during a run.

The actual matching legacy adapter emits these normal startup notices via `Module.printErr`, so the harness records them without treating them as failures:

- Exactly `[UT4] run() called, but dependencies remain, so not running`.
- Exactly `[UT4] pre-main prep time: N ms`, where `N` is a nonnegative decimal integer with no leading zeros except `0`. The adapter computes this instrumentation from integer `Date.now()` values.
- Exactly `[UT4] Calling stub instead of sigaction()`. The adapter's compatibility stub prints this notice and returns `0`; this exemption does not establish native signal support.

Matches include the literal launcher prefix and consume the entire message. Different case, trailing whitespace/newlines, other stubs, malformed timing values and appended text are not exempted. Fatal matching takes precedence. Source-map diagnostics, missing assets/materials, Party World ensures and DebugBreak remain failures. No generic `printErr`, warning, dependency-list or stub exemption exists; inspect newly observed diagnostics before changing this list.

Each invocation creates a unique `ut4-runtime-*` directory under the caller's output directory, with `report.json` and best-effort world/measured/failure screenshots. Logs are capped at 5,000 events with a dropped-event count. No Playwright trace, video or asset archive is produced. Reports can contain private URLs and engine diagnostics; they remain local. Exit codes are `0` for all requested resolutions passing, `1` for runtime verification failure, and `2` for invalid arguments/setup errors before a runtime report can be written. A failed first resolution stops the run. A blocked renderer can prevent a failure screenshot; its timeout is recorded instead.

Safe preparation checks without contacting any runtime or creating artifacts:

```sh
npm run verify:runtime -- --self-test-args
npm run verify:runtime -- --self-test-diagnostics
npm run verify:runtime -- --help
# Add --validate-only to a complete command to check URL/path/options only.
```

CLI validation, syntax and diagnostic regression checks have been exercised. The diagnostic checks cover expected strings, numeric/whitespace/prefix/suffix near-misses, and retained fatal/UE error detection across console severities. A bounded real partial-runtime run at 1080p (five-second requested measurement, 30-second readiness deadline) exited `1` first on the missing `RemoveSurfaceMaterial` engine asset, and also captured missing `DM-DeckTest`, the `Party.cpp:162` World ensure and DebugBreak. The loader notices remained recorded without causing that failure. Metrics stayed uninitialized; the measured interval was never reached. **The full cooked game and successful readiness/measurement path remain unvalidated.** Passing a future run will still not establish match completion, bot behavior, shader correctness, multiplayer replication/handshake, server travel, audio quality or subjective playability.
