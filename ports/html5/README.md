# Local-rendering UT4 browser port — experimental

This work targets the recovered **UT4 beta, UE4.15 CL3228288**. It does not substitute another game. It is not a production release and is not the client currently served by the public Vercel demo. That demo still streams from Windows.

The engine and game compile and link successfully with their bundled Emscripten 1.36.13 toolchain. Its output is asm.js/WebGL, not WebAssembly. A newer-linker experiment passed the standalone packet tests but exposed C library ABI differences in the full game. The current converter instead translates optimized asm.js using Binaryen while preserving the matching legacy JS runtime. The full engine now initializes as WebAssembly in Chrome and passes an allocator smoke test with 1.5 GiB memory. The corrected compiler build now loads Deck and Outpost. Bounded checks verify floor collision, real keyboard walking/jumping/landing, six-bot match activity, shortened-round automatic rotation, and two-context multiplayer input/reconnect. Outpost is overexposed; aiming, longer sessions and browser-specific frame pacing remain release gates. See [verification status](verification.json).

## Original changes in this directory

- A monolithic browser target without CEF or desktop performance counters; the online plugin is registered once.
- Explicit build-local Emscripten configuration, a missing replay header include, and browser definitions of byte-order helpers omitted by the original platform guards.
- A browser-only frame-pacing fix: the existing requestAnimationFrame loop schedules ticks without the desktop limiter busy-waiting on HTML5’s no-op sleep. Native client/server pacing is preserved; FPS benefit remains to be measured. The browser cap no longer derives from negotiated network speed, so high-refresh multiplayer packet rates and background-tab resume must also be measured before release.
- Narrow legacy glue fixes bound culture-string writes, allocate the URL terminator, and cast the frame log argument to the integer width required by its format. Each has regression checks; diagnostic fixes do not imply gameplay validation.
- Bounded packet parsing retaining split headers and payloads; partial send retention; deferred disconnect notification; removal of the old `select` descriptor limit.
- A loopback WebSocket-to-UDP gateway with a fixed operator-configured destination, separate UDP sockets per player, exact origins, size/rate/queue limits, heartbeat cleanup, and six-player admission. It transports game packets; it neither renders nor streams video.

Epic's engine, game code, content, SDK binaries, and generated game outputs are not included. Apply these original scripts only to a licensed, isolated local copy. They do not modify the running installation.

## Windows build

Use the [ordered build recipe](BUILD.md) for shader, private material, cook, packaging and conversion prerequisites. The commands below describe individual stages.

Requires the recovered matching source/content/editor, bundled emsdk, Python 3 via `py -3`, MSVC v140, Windows SDK 8.1, and UCRT 10.0.10240.0. Copy the installation to a separate directory, preserving `Engine/Source/Developer/DerivedDataCache`. Exclude build/cache output, **not all folders named DerivedDataCache**. Content may be junctioned to the licensed source only when the cook treats it as input. Never put the marker on the live installation.

```powershell
$port = 'F:\TournamentUT4\browser-port'
New-Item -ItemType File "$port\.tournament-browser-port"
./ports/html5/build-legacy.ps1 -SourceRoot $port -Workers 4
```

The marker and exact engine version are checked. The standalone browser target replaces discovery of the desktop Game target in this isolated checkout, preserving it as `.cs.before-tournament-browser`; UE4.15 AutomationTool cannot package a project with two Game targets. Patches preserve `.before-tournament-html5` originals. Reapplication regenerates patched files from those originals; keep unrelated edits elsewhere. Do not run the scripts while another compiler is reading the checkout. Build logs go to `UnrealTournament/Saved/Logs/BrowserPort`. The wrapper fails if unresolved symbols remain even if the old linker only warns.

The engine's hard-coded asm.js heap is 256 MiB. A successful link alone does **not** establish enough memory for Deck or a suitable runtime configuration. The current WebAssembly adapter uses a fixed configurable memory allocation (1.5 GiB in the tested full-game build). Current validation and remaining limits are recorded in verification.json.

For the first asset conversion after shader/compiler changes, omit `-iterate` so stale cooked shaders cannot survive. The engine's normal shader workers are substantially faster than `-NoShaderWorker`:

```powershell
& "$port\Engine\Binaries\Win64\UE4Editor-Cmd.exe" `
  "$port\UnrealTournament\UnrealTournament.uproject" `
  -run=Cook -TargetPlatform=HTML5 -Map=DM-DeckTest -CookCultures=en `
  -unversioned -compressed -SkipEditorContent -unattended -nop4
```

`patch-browser-packaging.py` excludes desktop tutorial/menu movies from HTML5 staging and enables the matching packager’s `--no-heap-copy` option. Recompile AutomationTool scripts, then restage; the first partial-package probe shrank from 1,737,687,846 bytes to 185 MB. UnrealPak and HTML5LaunchHelper must be built from the matching checkout. This probe is incomplete cooked content, not a playable release.

An editor-only BoneWeightMaterial was removed from the browser startup packages in the development checkout and its debug reference redirected to WorldGridMaterial. This does not replace player materials. Some recovered character materials reference moved textures. `patch-webgl-shaders.py` raises only the WebGL fragment compiler limit to 16 samplers, matching the runtime fragment binding capacity, and bumps its shader-cache version. Vertex shaders retain their eight-sampler limit. Rebuild both the editor and ShaderCompileWorker ShaderFormatOpenGL modules and recook affected assets after applying it. The launcher requires 16 fragment, 8 vertex, and 24 combined texture slots. Other unsupported material features still require compatibility work. The [compatibility commandlet](compat/README.md) reports actual mesh slots and texture parameters, prepares independent private material copies, and repairs selected assets. Its editor module compiles, Report runs, and Apply plus a fresh-process Verify passed for three Robot material repairs and 18 textured weapon surfaces. The source and untouched-sibling hash audit also passed; all saved materials are private copies. Browser appearance and shader completion remain verification gates; do not count a replacement graph as fixed graphics without viewing it.

## Browser launcher

The original [local launcher](client/README.md) provides fixed 1080p/1440p, centered aspect ratio, real engine callback metrics, input release, settings and clean retry. Its fixture tests pass, including pointer capture in headed Chrome. The C control exports are present in the full engine. Actual checks retained1080p/1440p through short matches; full mouse/settings behavior remains under verification. Use a complete matching asset package; the current private rotation package is about1.8GB.

## Packet gateway

```sh
cd ports/html5
npm ci
npm test
BROWSER_ORIGINS=http://127.0.0.1:8000 GAME_HOST=127.0.0.1 GAME_PORT=7787 npm start
```

It listens only on `127.0.0.1:9080`. `/health` reports admission count, not game readiness. `/game` requires the `binary` WebSocket subprotocol. Emscripten's TCP-over-WebSocket stream uses a four-byte little-endian length before each game datagram; the gateway accepts fragmented/coalesced writes and sends one framed UDP reply per binary message. Browser-supplied destinations and query parameters are rejected.

Set the browser runtime's `Module.websocket.url` to the game gateway URL before loading the engine. The legacy runtime expects a string. Bounded real UE handshake, two-context input and reconnect checks against the native server pass. Complete multiplayer combat/travel acceptance remains open. Do not expose the stock experimental UE HTML5 WebSocket server: this patch does not fix its server-side listener/disconnect and unbounded-buffer bugs.

This local gateway has no Tournament identity/rewards contract. Public production admission requires Tournament-issued tickets and staging verification; no packets or browser UI messages award money.

## Tests and release gates

```sh
c++ -std=c++11 -O2 -DNDEBUG -Wall -Wextra -Werror -fsanitize=undefined \
  ports/html5/packet-buffer.test.cpp -o /tmp/packet-test
/tmp/packet-test
cd ports/html5 && npm ci && npm test
```

Tests cover every split point, repeated fragments, coalescing, maximum-size payloads, malformed lengths, two isolated gateway peers, disconnect isolation, origin/destination rejection, admission limits and floods. Checks remain active with `NDEBUG`. CI also runs the parser with AddressSanitizer on Linux. The current Mac's AddressSanitizer runtime hung before `main`; native undefined-behavior checks and Chrome execution passed.

Before replacing the streaming demo, complete these gates:

1. Produce a strict successful engine link and a complete reproducible asset package.
2. Load Deck locally in the browser; verify visible characters, weapons, lighting and input with no video stream.
3. Verify two independent browsers join one authoritative match, fight, respawn, finish, rotate and reconnect. Verify six-bot practice separately.
4. Preserve the selected 1920×1080 or 2560×1440 drawing-buffer size, centered aspect ratio, and working Escape/settings/fullscreen behavior.
5. Measure real presented frames, CPU/GPU frame time, frame-time percentiles, memory and loading on Chrome, Firefox and Safari. Targets are 120 FPS at 1080p and 60 FPS at 1440p; they are not achieved measurements.
6. Verify authentication, event deduplication, authoritative reward configuration, restrictions, delayed spectating and anti-cheat against Tournament staging before enabling any rewards.

## Matching-runtime WebAssembly conversion

`convert-asm-to-wasm.py` preserves the legacy C/C++ and JavaScript ABI. It replaces only the asm.js module with a WebAssembly instance and wraps startup asynchronously. The launcher must compile the `.wasm` asynchronously into `Module.wasmModule` before loading the adapter. `Module.gameRuntimeReady` reports asynchronous startup; normal Emscripten initialization hooks remain in use. The matching `.js.mem` file is loaded once by the unchanged legacy runtime.

The development toolchain is the official Emscripten 1.38.48 Windows archive, release hash `1290d9deb93d67c4649999a8f2c8d9167d38dc04`, SHA256 `0d11d58986a4047990d615466be673d5fbf32f80f382376f3cdd727cc03b7311`. Only its `asm2wasm` converter is used on this route; do not mix its C libraries with the older engine objects.

```powershell
py -3 ports/html5/convert-asm-to-wasm.py `
  F:\TournamentUT4\browser-port\UnrealTournament\Binaries\HTML5\TournamentBrowser.js `
  F:\TournamentUT4\work\converted-game\TournamentBrowser.js `
  --binaryen F:\TournamentUT4\toolchains\fastcomp-1.38.48\install --memory-mib 1536
```

Binaryen optimization passes are intentionally omitted: this old converter's `-O2` generated invalid i64 code in the regression probe. The incoming asm.js is already optimized. Full-game Chrome startup found and fixed both the 8 MiB synchronous-instantiation limit and duplicate memory initialization; browser gameplay testing remains required.
