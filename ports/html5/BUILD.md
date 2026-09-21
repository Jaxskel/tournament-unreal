# Reproduce the local UT4 HTML5 build

This is an ordered operator recipe for the **licensed, locally recovered UT4 beta / UE4.15.0 CL3228288**. It uses only the original integration code in this repository; obtain the matching engine, source assets, SDKs and binaries from the user's authorized local installation. Do not add those files or generated game packages to this repository. Keep the public Vercel streaming demo and its running Windows installation unchanged.

**The local browser game is not ready.** This document assembles previously separate steps; the latest wrapper and this complete sequence have **not** been freshly replayed from a clean isolated checkout. Commands below are reproduction instructions, not evidence that they were executed while writing this document. No Windows changes were made for this documentation task.

## 1. Know which results exist

Status recorded on 2026-09-21, using [verification.json](verification.json), the [port notes](README.md), [compatibility instructions](compat/README.md), [launcher instructions](client/README.md), and the latest operator update:

| Area | Recorded result and remaining gate |
| --- | --- |
| Matching legacy build | Full engine compile/link exited zero; nine browser exports, including SessionEpoch, are recorded as present. The latest wrapper also installs configuration, logging and Party fixes. Its newly consolidated whole flow still needs a fresh replay. |
| Shader profile | Original patch changes only WebGL fragment samplers to 16 and shader version 61 → 62. Both editor and ShaderCompileWorker shader-format DLL rebuilds are required; patch application alone is insufficient. |
| Private compatibility assets | Copy-on-write preparation, Apply with rendering, fresh-process Verify, and original/sibling hash audit passed for **18 textured weapon surfaces plus 3 Robot repairs**. This supersedes older untested wording in the compatibility README. Browser appearance is unverified. |
| Current cook | Full non-iterative **Deck** cook is still processing through normal shader workers. Do not interpret progress, an existing cooked directory, or a partial package as cook success. |
| Packaging | UAT previously produced an approximately 185 MB **partial** package after packaging fixes. That establishes the packaging mechanism, not complete assets. |
| Converted WASM | Matching-runtime conversion validates and has initialized in Chrome with 1.5 GiB, including allocator smoke. The allocator probe used `noInitialRun=true`; it proves neither a world nor FPS. |
| Actual launcher probe | The incomplete package initializes WebGL but fails on real missing assets: the latest harness first reported missing `RemoveSurfaceMaterial`, then captured missing Deck, the Party World ensure and DebugBreak. World/tick metrics remained uninitialized. This probe predates validation of the newest Party/control build. |
| Latest readiness correction | Source now requires an `ATournamentPlayerController` in `TournamentBrowserReady()`, and TournamentDeathmatch explicitly sets that controller class. The current Party/logging link is finishing; this newer controls change still needs the next Windows incremental build and conversion. A ticking UTEntry world with a generic controller must not pass readiness. |
| Final rotation / networking | Explicit Deck, UTEntry and Outpost23 cook/package coverage, complete browser gameplay, actual multiplayer handshake, rotation, reconnect and performance remain unverified. Native/streaming success does not validate this port. |

## 2. Prepare an isolated checkout and tools

Use an isolated physical engine/source tree. A read-only Content junction to the licensed original is allowed initially; selected compatibility assets must become private physical copies before Apply. Never mark or patch the live installation. Preserve `Engine/Source/Developer/DerivedDataCache` when copying: exclude generated cache output, **not every directory named DerivedDataCache**.

Required tools: matching bundled Emscripten **1.36.13**, its bundled Python 2/runtime tools, Python 3 via `py -3` for the original patch scripts, MSVC **v140 / VS2015**, Windows SDK **8.1**, UCRT **10.0.10240.0**, matching editor/program source, .NET MSBuild, and Node/Playwright for later launcher verification. The converter uses the separately pinned Binaryen tool below; do not replace the legacy compiler/C libraries with that newer SDK.

In one PowerShell session, adjust the integration-repository path and select a fresh scratch directory outside that repository:

```powershell
$repo = 'F:\path\to\tournament-ut4' # This original integration repository; adjust.
$port = 'F:\TournamentUT4\browser-port'
$original = 'F:\TournamentUT4\source\UnrealTournament-clean-master'
$scratch = 'F:\TournamentUT4\work\html5-repro-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$project = "$port\UnrealTournament\UnrealTournament.uproject"
$editor = "$port\Engine\Binaries\Win64\UE4Editor-Cmd.exe"
$ubt = "$port\Engine\Binaries\DotNET\UnrealBuildTool.exe"
$msbuild = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe'
$ErrorActionPreference = 'Stop'

if (!(Test-Path -LiteralPath $project)) { throw 'Matching isolated project missing' }
if ([IO.Path]::GetFullPath($port) -eq [IO.Path]::GetFullPath($original)) {
    throw 'The port must be separate from the licensed original'
}
$version = Get-Content -Raw "$port\Engine\Build\Build.version" | ConvertFrom-Json
if ($version.MajorVersion -ne 4 -or $version.MinorVersion -ne 15 -or
    $version.PatchVersion -ne 0 -or $version.Changelist -ne 3228288) {
    throw 'Requires UE4.15.0 CL3228288'
}
New-Item -ItemType Directory -Path $scratch | Out-Null
# Only after inspecting that this is the isolated copy, never the live installation:
if (!(Test-Path "$port\.tournament-browser-port")) {
    New-Item -ItemType File "$port\.tournament-browser-port" | Out-Null
}
Set-Location $repo
```

Stop editors, cookers and compilers using this isolated checkout before applying source/configuration patches, installing plugins or changing the Content overlay. Do not stop the currently active cook merely to replay this document: coordinate the next clean run. Keep `.before-*` backups. Patchers intentionally reject unexpected source/backup combinations; do not bypass those guards or silently overwrite another agent's changes.

For native commands in the examples, this helper preserves logs and checks the actual exit code without PowerShell 5.1 turning routine native stderr into a terminating `NativeCommandError`:

```powershell
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments, [string]$Log)
    $null = Get-Command -Name $Program -ErrorAction Stop
    $savedErrors = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Program @Arguments > $Log 2>&1
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedErrors }
    Get-Content -LiteralPath $Log -Tail 25
    if ($code -ne 0) { throw "Command failed ($code): $Program; inspect $Log" }
}
```

Exit zero is necessary, never sufficient: review compiler/cook/package diagnostics and the artifact gates below. Preserve the source revision, tool versions, configuration, command lines, logs and hashes in scratch storage for the replay record.

## 3. Build the matching legacy browser target

```powershell
& "$repo\ports\html5\build-legacy.ps1" -SourceRoot $port -Configuration Development -Workers 4
if ($LASTEXITCODE) { throw 'Legacy HTML5 build failed' }
```

Read the current [wrapper](build-legacy.ps1), rather than manually reproducing an older subset. Its order is:

1. `configure-legacy.py`: explicit build-local Emscripten paths, browser target, byte-order helper and replay include.
2. `scripts/install-plugin.ps1`: installs/enables current **TournamentBridge** source in the isolated project.
3. `configure-browser-config.py`: installs the HTML5 game-engine subclass's WebSocket net-driver configuration; redirects the editor-only BoneWeight debug material to WorldGrid and removes its startup package. These settings must later be restaged.
4. Network, pacing, glue and logging patchers, followed by `patch-browser-party.py --apply`. The Party guard prevents the failed-map callback from assuming a world exists; it does **not** supply missing maps or make failed startup playable.
5. Worker limits, disabled XGE, pinned-UCRT UBT compilation, then `TournamentBrowser HTML5 Development` through the legacy toolchain.
6. Fails on unresolved/undefined symbols even if the old linker only warns; after a zero exit, checks all nine `Module["_TournamentBrowser..."]` exports.

The isolated desktop Game target is backed up as `.cs.before-tournament-browser` so UE4.15 UAT discovers only one Game target. Do not re-enable a competing Game target for packaging.

Retain `UnrealTournament/Saved/Logs/BrowserPort/build-tool.log` and `compile.log`, original `UnrealTournament/Binaries/HTML5/TournamentBrowser.js`, and its matching `TournamentBrowser.js.mem`. Required exports are Ready, SessionEpoch, Width, Height, Frame, SetResolution, SetSensitivity, SetVolume and ReleaseInput, each prefixed `TournamentBrowser`. Export strings/link success are not runtime readiness.

The legacy default heap is 256 MiB. A larger initial heap is an explicit experiment, not an automatically selected fix for missing assets. Keep the JS, `.js.mem`, later WASM conversion and manifest from one consistent build.

When continuing the current work, wait for the active Party/logging link to finish before installing/rebuilding the newer readiness/controller sources. The next incremental build must include both the cast in Ready and the game mode's controller-class assignment; nine export names alone cannot detect an older implementation. Reconvert that output before using it for readiness verification.

## 4. Install compatibility tools and rebuild both shader consumers

`build-legacy.ps1` does **not** apply the WebGL compiler patch or build editor/cooker dependencies. With no cook/editor using the tree:

```powershell
py -3 "$repo\ports\html5\patch-webgl-shaders.py" $port
if ($LASTEXITCODE) { throw 'WebGL shader patch failed' }

$compat = "$repo\ports\html5\compat"
$compatDestination = "$port\UnrealTournament\Plugins\UT4Html5Compat"
# New installation only. If present, compare/coordinate its version; do not blind-overwrite.
if (!(Test-Path -LiteralPath $compatDestination)) {
    Copy-Item -LiteralPath "$compat\UT4Html5Compat" -Destination $compatDestination -Recurse
}

$previousUcrt = $env:TOURNAMENT_UT4_UCRT_VERSION
$env:TOURNAMENT_UT4_UCRT_VERSION = '10.0.10240.0'
Invoke-Checked "$port\Engine\Build\BatchFiles\Build.bat" @(
    'UnrealTournamentEditor', 'Win64', 'Development', $project,
    '-WaitMutex', '-NoHotReloadFromIDE', '-2015'
) "$scratch\editor-build.log"
Invoke-Checked "$port\Engine\Build\BatchFiles\Build.bat" @(
    'ShaderCompileWorker', 'Win64', 'Development', '-WaitMutex', '-2015'
) "$scratch\shader-worker-build.log"
```

Explicitly rebuild **each consumer's ShaderFormatOpenGL DLL**, including the worker variant. A rebuilt editor alone can leave shader workers loading the old compiler module:

```powershell
Push-Location "$port\Engine\Source"
try {
    Invoke-Checked $ubt @(
        'UnrealTournamentEditor', 'Win64', 'Development', "-Project=$project",
        '-Module', 'ShaderFormatOpenGL', '-NoUBTMakefiles', '-NoHotReload', '-2015'
    ) "$scratch\editor-shaderformat.log"
    Invoke-Checked $ubt @(
        'ShaderCompileWorker', 'Win64', 'Development',
        '-Module', 'ShaderFormatOpenGL', '-NoUBTMakefiles', '-NoHotReload', '-2015'
    ) "$scratch\worker-shaderformat.log"
} finally { Pop-Location }
Get-ChildItem "$port\Engine\Binaries\Win64" -Filter '*ShaderFormatOpenGL*.dll' |
    Select-Object Name, Length, LastWriteTime
```

Review both build logs and the `UE4Editor-ShaderFormatOpenGL.dll` and `ShaderCompileWorker-ShaderFormatOpenGL.dll` outputs. They must correspond to the patched source and this build; an old DLL's existence is not verification. The patch sets only `GLSL_ES2_WEBGL` pixel shaders to 16 samplers, leaves vertex shaders at 8, and bumps the WebGL shader version to **62**. Actual browser contexts must expose fragment ≥16, vertex ≥8 and combined ≥24 slots. No other ES3 feature support is implied.

## 5. Prepare private materials, Apply with rendering, then fresh Verify

Use the finalized [browser-surfaces manifest](compat/manifest.browser-surfaces.json) for the recorded **18 weapon + 3 Robot** scope. Do not modify its texture choices or broaden its package list without a new reviewed preparation/receipt. This is a bounded private compatibility conversion, not an original-content resave.

```powershell
$manifest = "$compat\manifest.browser-surfaces.json"
$receipt = "$port\UnrealTournament\html5-compat-cow.json"
Invoke-Checked $editor @(
    $project, '-run=UT4Html5Compat', '-Mode=Report', "-Manifest=$manifest",
    '-NullRHI', '-unattended', '-nop4', '-stdout'
) "$scratch\compat-report.log"
```

For a **new overlay only**, with editors/cookers stopped and the Content junction still pointing to the declared original:

```powershell
if (Test-Path -LiteralPath $receipt) { throw 'Existing receipt: use Verify/audit below, not a repeated Apply' }
$cowArgs = @('--project', $project, '--isolated-root', $port,
    '--original-root', $original, '--manifest', $manifest, '--mode', 'inplace')
py -3 "$compat\prepare_cow.py" @cowArgs
if ($LASTEXITCODE) { throw 'COW planning failed' }
# Inspect the plan; execution creates private copies and swaps only the junction entry.
py -3 "$compat\prepare_cow.py" @cowArgs --execute
if ($LASTEXITCODE) { throw 'COW preparation failed' }
Invoke-Checked $editor @(
    $project, '-run=UT4Html5Compat', '-Mode=Apply', "-Manifest=$manifest",
    "-Receipt=$receipt", '-AllowCommandletRendering', '-unattended', '-nop4', '-stdout'
) "$scratch\compat-apply.log"
```

**Never use `-NullRHI` for Apply.** This engine can leave new material render resources null and crash during material edits. Apply requires `-AllowCommandletRendering`. Report and Verify may use NullRHI.

Whether continuing the already verified private overlay or creating a new one, invoke Verify in a **new editor process**, without persistent Robot redirects, and audit the original/sibling hashes:

```powershell
Invoke-Checked $editor @(
    $project, '-run=UT4Html5Compat', '-Mode=Verify', "-Manifest=$manifest",
    "-Receipt=$receipt", '-NullRHI', '-unattended', '-nop4', '-stdout'
) "$scratch\compat-verify.log"
py -3 "$compat\prepare_cow.py" --audit $receipt
if ($LASTEXITCODE) { throw 'Original/sibling hash audit failed' }
```

Existing fallback parents/receipts are not a reason to rerun Apply. The helper intentionally refuses conflicting or reused preparation; use the explicit recovery/shadow-project procedure in [compat/README.md](compat/README.md), preserving the old private outputs. Require successful saves, fresh Verify and hash audit before cooking. These prove package structure and isolation, not final shader appearance or gameplay material overrides.

## 6. Complete a normal-worker, non-iterative cook

The **currently running** cook uses this Deck command, not `-NoShaderWorker`:

```powershell
Invoke-Checked $editor @(
    $project, '-run=Cook', '-TargetPlatform=HTML5', '-Map=DM-DeckTest',
    '-CookCultures=en', '-unversioned', '-compressed', '-SkipEditorContent',
    '-unattended', '-nop4', '-stdout'
) "$scratch\cook-deck.log"
```

This documents the current scope; do not start a competing process. After shader version/compiler changes, **omit `-iterate`** so stale cooked shaders cannot survive. Keep normal shader workers enabled. A shader compile still running is not success; `-NoShaderWorker` is not the normal recipe. Do not stage/package while cooking is active.

Before a **final rotation-capable** package, explicitly cook all three maps. Normal cooking also gathers the configured default map, but listing all roots makes startup and subsequent server travel coverage explicit:

```powershell
$finalMaps = '/Game/RestrictedAssets/Maps/WIP/DM-DeckTest+/Game/RestrictedAssets/Maps/UT-Entry+/Game/RestrictedAssets/Maps/DM-Outpost23'
Invoke-Checked $editor @(
    $project, '-run=Cook', '-TargetPlatform=HTML5', "-Map=$finalMaps",
    '-CookCultures=en', '-unversioned', '-compressed', '-SkipEditorContent',
    '-unattended', '-nop4', '-stdout'
) "$scratch\cook-final.log"
```

Require unambiguous resolution of those exact package paths in the matching source Content. The configured entry package is `/Game/RestrictedAssets/Maps/UT-Entry` (with a hyphen). Preserve the resolved paths in the artifact inventory; do not substitute a different entry map just to pass a name check.

Require the cooker to exit zero **and** its final summary to report successful completion. Treat failed material/shader compilation, missing required packages, invalid default materials, shader-map failures and cook errors as blockers; inspect warnings relevant to reachable game assets rather than accepting fallback/default-material substitution as verified graphics. Confirm new nonempty cooked map files, `AssetRegistry.bin`, the WebGL global shader cache, and dependencies including repaired materials/generated parents. Inline material shader maps live with their cooked packages; a global-cache filename alone does not prove their validity. Preserve the complete log and shader-version/build provenance.

## 7. Build packaging prerequisites and force UAT script recompilation

These steps are not performed by the legacy wrapper. Build matching **UnrealPak Win64 Development** and the **HTML5LaunchHelper .NET project**, not a guessed native HTML5LaunchHelper target:

```powershell
Invoke-Checked "$port\Engine\Build\BatchFiles\Build.bat" @(
    'UnrealPak', 'Win64', 'Development', '-WaitMutex', '-2015'
) "$scratch\unrealpak-build.log"
$helperProjects = @(Get-ChildItem "$port\Engine\Source\Programs" -Recurse -Filter HTML5LaunchHelper.csproj)
if ($helperProjects.Count -ne 1) { throw 'Locate the single matching HTML5LaunchHelper.csproj' }
# Use the configuration/output path declared by this matching .NET project.
# Omitting /p:Configuration uses its own declared default, not a guessed native target.
Invoke-Checked $msbuild @(
    $helperProjects[0].FullName, '/t:Build', '/nologo', '/verbosity:minimal', '/p:Platform=AnyCPU'
) "$scratch\html5-launch-helper-build.log"
$unrealPak = "$port\Engine\Binaries\Win64\UnrealPak.exe"
if (!(Test-Path -LiteralPath $unrealPak)) { throw 'UnrealPak output missing' }
# Verify HTML5LaunchHelper.exe at the .csproj OutputPath expected by matching UAT.
Select-String -LiteralPath $helperProjects[0].FullName -Pattern 'Configuration|OutputPath'

py -3 "$repo\ports\html5\patch-browser-packaging.py" $port
if ($LASTEXITCODE) { throw 'Browser packaging patch failed' }
```

The packaging patch changes `HTML5Platform.Automation.cs`: desktop movies are excluded and the matching file packager receives `--no-heap-copy`. It keeps the FS archive outside the fixed WASM heap. **Recompile the AutomationTool scripts after this source change.** The next invocation uses `-compile`; inspect its log for actual script recompilation and the patched packager command. Do not use `-nocompile`/`-nocompileuat` to reuse an older HTML5 automation assembly. Restage after configuration or packaging changes; merely rebuilding the game executable does not refresh packaged data.

## 8. Stage, pak and package only the successful completed cook

Proceed only after step 6's final cook succeeds and steps 4–7 pass. `-skipcook` deliberately packages existing cook output; it does **not** validate or complete that output. Use a fresh archive directory and do not use `-skipstage`, `-skippak` or `-skippackage` to reuse the earlier partial probe.

```powershell
$archive = "$scratch\package"
Invoke-Checked "$port\Engine\Build\BatchFiles\RunUAT.bat" @(
    '-compile', 'BuildCookRun', "-project=$project", '-nop4', '-unattended',
    '-platform=HTML5', '-clientconfig=Development', "-map=$finalMaps",
    '-skipcook', '-stage', '-pak', '-package', '-archive', "-archivedirectory=$archive"
) "$scratch\uat-package.log"
$env:TOURNAMENT_UT4_UCRT_VERSION = $previousUcrt
```

Require UAT success, fresh stage/package timestamps, recompiled script evidence, and `--no-heap-copy` in the packaging invocation. The precise target/platform/program paths are from the matching engine; if UAT reports missing UnrealPak/HTML5LaunchHelper or a second Game target, fix the prerequisite rather than accepting partial output. The combined `-compile BuildCookRun` recipe remains part of the **not-yet-freshly-replayed** sequence; inspect its actual output before promoting artifacts.

Test and list **every final staged pak**, using matching UnrealPak. The usual stage root is shown below; verify it against this UAT log rather than accidentally listing a previous archive:

```powershell
$staged = "$port\UnrealTournament\Saved\StagedBuilds\HTML5"
$paks = @(Get-ChildItem $staged -Recurse -Filter '*.pak')
if (!$paks.Count) { throw 'No staged pak; inspect UAT stage path' }
$listing = ''
for ($i = 0; $i -lt $paks.Count; $i++) {
    Invoke-Checked $unrealPak @($paks[$i].FullName, '-Test') "$scratch\pak-$i-test.log"
    Invoke-Checked $unrealPak @($paks[$i].FullName, '-List') "$scratch\pak-$i-list.log"
    $listing += (Get-Content -Raw "$scratch\pak-$i-list.log").Replace('\', '/')
    Get-FileHash -Algorithm SHA256 -LiteralPath $paks[$i].FullName
}
$required = @(
    '/Content/RestrictedAssets/Maps/WIP/DM-DeckTest.umap',
    '/UTEntry.umap',
    '/Content/RestrictedAssets/Maps/DM-Outpost23.umap',
    '/AssetRegistry.bin',
    '/GlobalShaderCache-GLSL_ES2_WEBGL.bin'
)
foreach ($entry in $required) {
    if (!$listing.Contains($entry)) { throw "Required final pak entry missing: $entry" }
}
```

This is a minimum presence gate, not a substitute for inspection. Check the actual listed entry sizes/paths, the UTEntry source-to-cooked path, expected engine/default material dependencies, compatibility packages/parents and errors in each `-Test`/`-List` log. `DevelopmentAssetRegistry.bin` is not a substitute for runtime `AssetRegistry.bin`. If this matching staging implementation deliberately stages a required shader cache loose, stop and account explicitly for that file in both stage and `.data.js` preload metadata; do not silently waive the gate.

Inspect the emitted `.data.js` package metadata: it must load the **same tested pak(s)**, with matching entry names/lengths and byte contents in the corresponding `.data` slices. Record hashes of those slices and compare with the listed pak files when accepting the package. Verify any deliberately loose runtime files likewise. Never infer completeness from a `.data` file's size, an existing AssetRegistry, UAT exit zero, or a previous approximately 185 MB package. A listed map alone also does not prove all its dependencies or material shader maps are usable.

## 9. Convert the matching asm.js; assemble one coherent private runtime

Use only the converter from the official Emscripten 1.38.48 Windows archive, release hash `1290d9deb93d67c4649999a8f2c8d9167d38dc04`, archive SHA256 `0d11d58986a4047990d615466be673d5fbf32f80f382376f3cdd727cc03b7311`. The Binaryen root below contains `bin/asm2wasm.exe`. Its **C/C++ libraries/linker are not used**: the full newer-linker experiment exposed 32/64-bit `off_t` ABI mismatches.

```powershell
$binaryen = 'F:\TournamentUT4\toolchains\fastcomp-1.38.48\install'
$converted = "$scratch\converted-game"
py -3 "$repo\ports\html5\convert-asm-to-wasm.py" `
    "$port\UnrealTournament\Binaries\HTML5\TournamentBrowser.js" `
    "$converted\TournamentBrowser.js" --binaryen $binaryen --memory-mib 1536
if ($LASTEXITCODE) { throw 'Matching-runtime conversion failed' }
```

Preserve the original asm.js; output to a different path. Do not add Binaryen `-O2`: the pinned converter generated invalid i64 code with those optimization passes in a probe. The input asm.js is already optimized. Retain converter metadata `TournamentBrowser.wasm-imports.json`, inspect its memory/table limits, and record hashes of the resulting JS/WASM and memory initializer.

The adapter preserves the old JS runtime, asynchronously instantiates the compiled WASM, and exposes `Module.gameRuntimeReady`. The launcher must asynchronously compile `Module.wasmModule` **before** loading the adapter. Do not use a newer `instantiateWasm` hook. Normal `onRuntimeInitialized`/postRun and actual world readiness remain required; script.onload or promise fulfillment alone is insufficient.

**Keep the external matching `.js.mem` exactly once. Never embed it into WASM as well.** The converter copies it with its original basename because the legacy runtime references that name. Its fixed 1536 MiB memory is an experiment and must agree with the manifest and WASM import limits; no automatic memory/resolution adaptation occurs.

Into a fresh **private** serving tree outside this repository, assemble:

- A copy of the original `ports/html5/client/` launcher UI (omit `node_modules`, test fixtures and private `runtime.json` from any public distribution).
- Under `engine/`, converted `TournamentBrowser.js`, `TournamentBrowser.wasm`, and matching `TournamentBrowser.js.mem` from this conversion.
- `Utility.js`, the actual emitted `.data.js`, `.data`, and any required sidecars from the **verified current package**, using their emitted names.

Do not overwrite the converted adapter with UAT's original asm.js while copying packaged files. Do not combine the new engine with the old partial `.data`. The examples use `UnrealTournament.data.js/.data`; rename manifest keys/URLs to match actual emission, including any configuration suffixes. Do not rename only one member of a loader/asset pair.

## 10. Write the private manifest and verify the actual iframe

Create `runtime.json` in the private serving tree, not as a checked-in game deliverable. This is a contract example, not a package included here:

```json
{
  "version": 1,
  "format": "wasm",
  "engine": "TournamentBrowser.js",
  "supportScripts": ["Utility.js"],
  "dataScripts": ["UnrealTournament.data.js"],
  "files": {
    "Utility.js": "./engine/Utility.js",
    "UnrealTournament.data.js": "./engine/UnrealTournament.data.js",
    "UnrealTournament.data": "./engine/UnrealTournament.data",
    "TournamentBrowser.js.mem": "./engine/TournamentBrowser.js.mem",
    "TournamentBrowser.js": "./engine/TournamentBrowser.js",
    "TournamentBrowser.wasm": "./engine/TournamentBrowser.wasm"
  },
  "wasmModule": "TournamentBrowser.wasm",
  "memoryInitializer": "TournamentBrowser.js.mem",
  "totalMemory": 1610612736,
  "arguments": ["/Game/RestrictedAssets/Maps/WIP/DM-DeckTest?Game=/Script/TournamentBridge.TournamentDeathmatch?Mutator=TournamentBridge.TournamentBridgeMutator?BotFill=7?MaxPlayers=7?LAN=1?RequireReady=0?MaxPlayerWait=3?Difficulty=3", "-NoSplash", "-NoMCP", "-unattended"],
  "multiplayerArguments": [],
  "bindings": [
    "TournamentBrowserReady", "TournamentBrowserSessionEpoch",
    "TournamentBrowserWidth", "TournamentBrowserHeight", "TournamentBrowserFrame",
    "TournamentBrowserSetResolution", "TournamentBrowserSetSensitivity",
    "TournamentBrowserSetVolume", "TournamentBrowserReleaseInput"
  ],
  "websocketUrl": "ws://127.0.0.1:9080/game",
  "initializationTimeoutMs": 180000
}
```

Use the exact case `wasmModule`. Declare every asset requested by the emitted packager. Serve UI/manifest/assets on the same loopback HTTP origin with correct JavaScript/WASM MIME types and real 404s; verify `.mjs` handling. No deployment is part of this recipe. `multiplayerArguments: []` intentionally disables Multiplayer. A separately prepared authoritative test may use `["127.0.0.1:7787"]` with the fixed operator gateway, but it does not replace Practice arguments or establish a handshake.

Run fixture/unit checks separately if desired; they do not validate the package. Once the complete package passes the preceding gates, use the **existing private operator URL** with the real-runtime harness. The example uses the scratch server port 8077, an explicitly existing directory outside the repo, and the 1080p five-second bounded probe:

```powershell
Set-Location "$repo\ports\html5\client"
npm ci
if ($LASTEXITCODE) { throw 'Launcher dependency installation failed' }
npm run verify:runtime -- --self-test-args
if ($LASTEXITCODE) { throw 'Harness CLI regression failed' }
npm run verify:runtime -- --self-test-diagnostics
if ($LASTEXITCODE) { throw 'Harness diagnostic regression failed' }
npm run verify:runtime -- --url http://127.0.0.1:8077/index.html `
    --manifest-url http://127.0.0.1:8077/runtime.json --out-dir $scratch `
    --resolution 1080p --seconds 5 --ready-timeout-seconds 30
if ($LASTEXITCODE) { throw 'Actual runtime verification failed; inspect scratch report' }
```

This command starts neither server nor gateway. Use installed Chrome, or install Playwright Chromium separately and specify `--channel chromium`. The harness writes a unique `ut4-runtime-*` report/screenshot directory under scratch. The 30-second world deadline is a deliberately bounded diagnostic; a full load may require a larger explicitly chosen limit. A later `--resolution both --seconds 30 --ready-timeout-seconds 300` run checks fresh 1080p/1440p instances, but no speed or successful-load guarantee is implied.

Require the actual nine exports, native world readiness and a positive session epoch, successful control calls, and agreement between native viewport, canvas and real WebGL drawing buffer before measuring. Ready must require the Tournament controller, not merely `HasBegunPlay`: UTEntry can tick while a multiplayer connection is pending. UTEntry activity is not proof of joining a match or gameplay. FPS/p95 come from native frame advances observed in engine main-loop callbacks, not a synthetic animation loop. The harness narrowly records/exempts three known legacy startup notices; missing material/map errors, Party failures, DebugBreak, aborts, context loss and readiness timeouts remain failures. A zero engine exit after DebugBreak cannot count as a pass.

Archive the report with package/build hashes and all cook/pak/conversion logs. Even a future passing harness run still needs visible Deck/characters/weapons/material review, real input/audio checks, six-bot practice, completed rounds and **Deck → Outpost23 → Deck** travel with UTEntry available, followed by authoritative multiplayer join/replication/reconnect testing. Do not claim gameplay readiness or replace the public streaming demo on the strength of this recipe, link success, allocator smoke or partial-package startup.
