# Reproduce the local UT4 HTML5 build

This is an ordered operator recipe for the **licensed, locally recovered UT4 beta / UE4.15.0 CL3228288**. It uses only the original integration code in this repository; obtain the matching engine, source assets, SDKs and binaries from the user's authorized local installation. Do not add those files or generated game packages to this repository. Keep the public Vercel streaming demo and its running Windows installation unchanged.

**Playable practice is demonstrated; the finished beta is not yet verified.** See the [current recorded status](CURRENT-STATUS.md) for the corrected floor regression, bounded gameplay/network results, actual 1080p/1440p measurements and remaining material/performance gates. The September 21 snapshot below is historical. Commands form a reproduction recipe; the complete sequence has not yet been replayed from a clean checkout.

## 1. Know which results exist

Historical snapshot recorded on 2026-09-21, retained for provenance. Later results in [CURRENT-STATUS.md](CURRENT-STATUS.md) supersede its unresolved-floor and no-performance-result statements. Related records: [verification.json](verification.json), [port notes](README.md), [compatibility instructions](compat/README.md) and [launcher instructions](client/README.md).

| Area | Recorded result and remaining gate |
| --- | --- |
| Matching legacy build | The latest intro schedule bounds wrapper build passed in **353.56 seconds** with all nine exports and no unresolved symbols. It includes configuration, logging, Party, pacing and browser window fixes. A fresh clean-checkout replay remains required. |
| Shader profile | Original patch changes only WebGL fragment samplers to 16 and shader version 61 → 62. Both editor and ShaderCompileWorker shader-format DLL rebuilds are required; patch application alone is insufficient. |
| Private compatibility assets | Copy-on-write preparation, Apply with rendering, fresh-process Verify, and original/sibling hash audit passed for **18 textured weapon surfaces plus 3 Robot repairs**. This supersedes older untested wording in the compatibility README. Browser appearance is unverified. |
| Current cook | Operator reports the explicit **Deck + UT-Entry + Outpost23** iterative cook finished **2026-09-21 20:48:25 UTC**, exit **0**, **885.79 seconds**, **0 errors / 1,904 warnings**. Required map/registry/cache presence passed; **7,793 nonempty files / 4,496,716,095 bytes**. Material/shader fallback warnings still block clean readiness. The expanded v3 package is now served privately; browser rotation remains unverified. |
| Packaging | Operator reports rotation-v3 packaging exit **0**, **9,178 files**, pak **1,820,658,276 bytes** (<2 GiB), `.data` **1,826,054,717 bytes**. The data pair was atomically installed on private localhost:8077 at **21:15:07 UTC**, with v2 preserved; full data SHA-256 `4036c83a38330f3a71b9f10bb874a81e5d3b7de6aa8dffb62b276bb1aca57b00` and loader-declared size matched. The matching UnrealPak verified all 9,178 files healthy; full data slices match the staged files, and the transferred archive hash matches. Required Deck, Entry, Outpost, registry, cache and configuration are listed. Browser rotation remains unverified. See [package verification](PACKAGE-VERIFICATION.md). |
| Converted WASM | Matching-runtime conversion validates and has initialized in Chrome with 1.5 GiB, including allocator smoke. **Firefox 146 and Playwright WebKit 26** also passed actual runtime initialization, allocator and matching file-packager preloader smoke. The preloader used fixture data; these results prove neither gameplay nor actual Safari behavior. The allocator probe used `noInitialRun=true`; it proves neither a world nor FPS. |
| Actual launcher probe | Chrome runs the actual WASM world and six-bot match locally, with native window/canvas/backing buffer at 1920×1080. Removed Web Audio velocity calls and cubemap mip activation have been corrected. The redundant startup I/O cleanup burst is fixed in the new build. **The Outline fix restores visible 3D rendering, and the Canvas tile-light fix removed the observed uniform-buffer assertion in a 30-second run. Controlled idle testing at PlayerStart_3 then proved the pawn falls through a BSP floor. The native read-only report hits that floor correctly; browser collision remains unresolved. No valid gameplay FPS result.** |
| Latest readiness correction | The **540.22-second** build includes the `ATournamentPlayerController` requirement in `TournamentBrowserReady()` and TournamentDeathmatch's explicit controller class. The reconverted Chrome runtime exposes all nine controls and returns not-ready before main. A ticking UT-Entry world with a generic controller must not pass readiness. Subsequent actual practice and two-client multiplayer probes reached Tournament match readiness; this does not validate rendering or completed gameplay. |
| Final rotation / networking | Two independent Chrome contexts joined the isolated native 7797 server with distinct identities and simultaneous bidirectional traffic. Direct package loading fixed the observed Blob-storage failure and passed a real single-client reconnect. A stable two-client run reached readiness, then hit a native Array.h bounds assertion before Reconnect. The assertion is mapped to intro-timer rescheduling against the wrong array after a late join. The bounded patch passes 17 actual-source checks and its HTML5 build. Both clients remained Ready through a 40-second late-join observation, then A reconnected while B remained connected without a native assertion or page error. This menu-open lifecycle probe does not verify interactive combat. V3 contains the rotation maps; sustained multiplayer, travel and performance remain unverified. |

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

Stop editors, cookers and compilers using this isolated checkout before applying source/configuration patches, installing plugins or changing the Content overlay. Coordinate the next clean run; do not interrupt another operator's active work merely to replay this document. Keep `.before-*` backups. Patchers intentionally reject unexpected source/backup combinations; do not bypass those guards or silently overwrite another agent's changes.

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

Exit zero is necessary, never sufficient for these build/cook/package commands: review diagnostics and the artifact gates below. The sole exit-code exception in this recipe is the pinned UnrealPak `-List` branch in step 8; do not use `Invoke-Checked` for that branch. Preserve the source revision, tool versions, configuration, command lines, logs and hashes in scratch storage for the replay record.

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

The wrapper also applies `patch-browser-analytics.py` before the fresh HTML5 build. It disables the legacy engine and UT analytics provider initialization only under `PLATFORM_HTML5_BROWSER`. UT's local event-name initialization remains active; native/editor behavior is preserved. This addresses observed requests to Epic's analytics endpoint that produce browser CORS errors. It does not change Tournament platform integration or claim to disable every independent telemetry subsystem. Browser verification must still fail on unexpected console/network errors.

The analytics patcher defaults to read-only preflight, pins both complete original source files, requires the isolated checkout marker and engine version, and retains exact original backups. Both sources and backups are checked before either source is replaced. Backups are flushed, verified, and published exclusively; interrupted source replacement can resume from the exact original/patched pair. Coordinate source ownership before `--apply`: admission snapshots are not locks, and this is not a power-loss transaction. A new coherent HTML5 runtime generation is required to activate the source change; local host tests alone do not prove the browser result.

If interruption or an unlink failure leaves a `.analytics-backup-*` temporary name sharing the final backup's file identity, preflight deliberately refuses the resulting multiple-link file. Both source replacements are still gated on completed backups. Preserve the files for inspection: verify the temporary and final names refer to the same file, their bytes match the pinned original, and no other links exist before removing only the owned temporary name and rerunning read-only preflight. Never replace or delete an unrecognized backup to bypass this refusal.
5. Worker limits, disabled XGE, pinned-UCRT UBT compilation, then `TournamentBrowser HTML5 Development` through the legacy toolchain.
6. Fails on unresolved/undefined symbols even if the old linker only warns; after a zero exit, checks all nine `Module["_TournamentBrowser..."]` exports.

The isolated desktop Game target is backed up as `.cs.before-tournament-browser` so UE4.15 UAT discovers only one Game target. Do not re-enable a competing Game target for packaging.

Retain `UnrealTournament/Saved/Logs/BrowserPort/build-tool.log` and `compile.log`, original `UnrealTournament/Binaries/HTML5/TournamentBrowser.js`, and its matching `TournamentBrowser.js.mem`. Required exports are Ready, SessionEpoch, Width, Height, Frame, SetResolution, SetSensitivity, SetVolume and ReleaseInput, each prefixed `TournamentBrowser`. Export strings/link success are not runtime readiness.

The legacy default heap is 256 MiB. A larger initial heap is an explicit experiment, not an automatically selected fix for missing assets. Keep the JS, `.js.mem`, later WASM conversion and manifest from one consistent build.

The latest readiness/controller build passed in 540.22 seconds and its reconverted runtime initialized in Chrome with all nine exports. For subsequent reproductions, include both the cast in Ready and the game mode's controller-class assignment; nine export names alone cannot detect an older implementation. Use the conversion from that same build for readiness verification. This milestone does not establish a fresh replay of the consolidated wrapper or complete recipe.

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

### Native editor prerequisite: Swarm's NETFX SDK headers

A full editor build can fail in `SwarmInterface.cpp:21` with missing `metahost.h`, followed by a missing `SwarmInterface.exp`. The verified recovery used the **official Microsoft-signed .NET Framework 4.8 Developer Pack**, with its SDK and targeting pack installed successfully (exit 0, no restart). This was an installation, not an archive extraction. Verify the installed header and x64 import library before retrying; a .NET runtime alone is not the required SDK evidence.

The pinned engine's `Windows/VCEnvironment.cs:216–237` searches only `NETFXSDK\4.6` registry entries for `KitsInstallationFolder`, even with VS2015/2017. It does not automatically discover 4.8. Lines 682–685 and 787–797 select the SDK's `Include/um` and `Lib/um/x64`; lines 117–130, 706–710 and 824–828 preserve caller `INCLUDE`/`LIB` paths. `SwarmInterface.cpp:30` requests `mscoree.lib`. These references describe the privately inspected matching source; no engine source or SDK payload is distributed here.

Use the actual installed SDK path and process-only environment values around the unchanged [native editor wrapper](build-browser-editor.ps1). Preserve the experiment selection already chosen for the coordinated build; [GPU8](GPU-SKIN-EXPERIMENT.md) remains explicitly opt-in and requires a matching fresh shader cook.

```powershell
$netfxSdk = 'C:\Program Files (x86)\Windows Kits\NETFXSDK\4.8' # Adjust to verified installation.
$netfxInclude = Join-Path $netfxSdk 'Include\um'
$netfxLib = Join-Path $netfxSdk 'Lib\um\x64'
foreach ($required in @((Join-Path $netfxInclude 'metahost.h'), (Join-Path $netfxLib 'mscoree.lib'))) {
    if (!(Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing NETFX SDK file: $required" }
}
$nativeBuildArgs = @{ SourceRoot = $port; Workers = 2 }
# Only for the already coordinated GPU8 experiment:
# $nativeBuildArgs.ExperimentalGpuSkin8 = $true
$previousInclude = [Environment]::GetEnvironmentVariable('INCLUDE', 'Process')
$previousLib = [Environment]::GetEnvironmentVariable('LIB', 'Process')
try {
    [Environment]::SetEnvironmentVariable('INCLUDE', (@($previousInclude, $netfxInclude) | Where-Object { $_ }) -join ';', 'Process')
    [Environment]::SetEnvironmentVariable('LIB', (@($previousLib, $netfxLib) | Where-Object { $_ }) -join ';', 'Process')
    & "$repo\ports\html5\build-browser-editor.ps1" @nativeBuildArgs
} finally {
    [Environment]::SetEnvironmentVariable('INCLUDE', $previousInclude, 'Process')
    [Environment]::SetEnvironmentVariable('LIB', $previousLib, 'Process')
}
```

The observed unchanged-wrapper retry reused compiled outputs: **four editor actions in 9.12 seconds**, then **ShaderCompileWorker in 0.70 seconds**, **10.728 seconds total**. Its makefile was regenerated because `BuildConfiguration.xml` was newer; this does not prove cached makefiles always consume a changed environment. No `-NoUBTMakefiles` addition, clean, global environment change, fabricated registry entry or source bypass was needed. Retain the official installation receipt and actual build logs. This result establishes the native prerequisite recovery, not a fresh end-to-end build/cook replay or browser shader validation.

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

## 6. Cook with normal shader workers and verify required maps

The completed **Deck** cook used this normal-worker command, not `-NoShaderWorker`; it reported 0 errors and 2,710 warnings in 4,107.55 seconds:

```powershell
Invoke-Checked $editor @(
    $project, '-run=Cook', '-TargetPlatform=HTML5', '-Map=DM-DeckTest',
    '-CookCultures=en', '-unversioned', '-compressed', '-SkipEditorContent',
    '-unattended', '-nop4', '-stdout'
) "$scratch\cook-deck.log"
```

This command documents the initial non-iterative Deck cook; the later expanded iterative result is recorded below. Do not start a competing process. After shader version/compiler changes, **omit `-iterate`** so stale cooked shaders cannot survive. Keep normal shader workers enabled. A shader compile still running is not success; `-NoShaderWorker` is not the normal recipe. Do not stage/package while cooking is active.

Before a **final rotation-capable** package, explicitly cook all three maps. Normal cooking also gathers the configured default map, but listing all roots makes startup and subsequent server travel coverage explicit:

```powershell
$finalMaps = '/Game/RestrictedAssets/Maps/WIP/DM-DeckTest+/Game/RestrictedAssets/Maps/UT-Entry+/Game/RestrictedAssets/Maps/DM-Outpost23'
Invoke-Checked $editor @(
    $project, '-run=Cook', '-TargetPlatform=HTML5', "-Map=$finalMaps",
    '-CookCultures=en', '-unversioned', '-compressed', '-SkipEditorContent',
    '-unattended', '-nop4', '-stdout'
) "$scratch\cook-final.log"
```

The operator subsequently ran those explicit three roots with **`-iterate`** against the existing cook, finishing at **20:48:25 UTC on 2026-09-21**: exit 0, 885.79 seconds, 0 errors and 1,904 warnings. No cooker or ShaderCompileWorker remained afterward. This cached follow-up is not evidence of a new clean cook after a compiler/shader change. Reported required output sizes were:

| Cooked output | Bytes |
| --- | ---: |
| DM-DeckTest | 11,939,768 |
| UT-Entry | 24,983 |
| DM-Outpost23 | 47,322,296 |
| AssetRegistry.bin | 4,912,182 |
| WebGL global shader cache | 325,705 |

Total: **7,793 nonempty cooked files, 4,496,716,095 bytes**. Operator evidence is in `F:\TournamentUT4\work\html5-cook-rotation-iterate-1.log` and `F:\TournamentUT4\work\html5-cook-rotation-iterate-1-result.json`. Required-presence checks passed; material/shader fallback warnings still block clean readiness. **No packaging had followed at that cook checkpoint**. Rotation-v3 was packaged and installed later (see the status table); existing Deck v2 package results and byte counts must not be attributed to the expanded outputs.

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

The optional [startup compression experiment](STARTUP-COMPRESSION.md) prepares a separate response that leaves twelve texture packages uncompressed. One six-run private headless comparison measured an 8.58% lower median launch-to-Ready time at a 57.43 MiB package-size cost. It is opt-in, requires independent archive equivalence checks, and does not change the packaging command above or establish gameplay performance.

Test and list **every final staged pak**, using matching UnrealPak. The usual stage root is shown below; verify it against this UAT log rather than accidentally listing a previous archive:

**Pinned UE4.15 CL3228288 quirk:** `Engine/Source/Programs/UnrealPak/Private/UnrealPak.cpp:1166–1210` defines `ListFilesInPak` to return `true` after emitting the summary for a valid pak, and `false` for an invalid pak. Line 1727 assigns that bool directly to `Result`, so **`-List` success is exactly 1; zero is failure**. The `-Test` branch at line 1719 instead uses `TestPakFile(...) ? 0 : 1`. This exception applies only to this matching executable's `-List`; never accept arbitrary nonzero codes or change the general command helper. Require a single positive summary, matching entry count and byte totals, no error/fatal diagnostics, and the required nonempty content paths below. The latest 8,328-file count is recorded evidence, not a hardcoded count for future cooks.

```powershell
function Read-PinnedPakListing {
    param([string]$Text, [int]$ExitCode)
    if ($ExitCode -ne 1) { throw "Pinned UnrealPak -List failed (expected 1, got $ExitCode)" }
    if ($Text -match '(?im)^.*\bLog\w+:\s*(?:Error|Fatal):|Fatal error:|Assertion failed:|Ensure condition failed:') {
        throw 'Pak listing contains error/fatal diagnostics'
    }
    $summary = [regex]::Matches($Text, '(?m)^.*\bLogPakFile:\s*Display:\s*(\d+) files \((\d+) bytes\), \((\d+) filtered bytes\)\.\s*$')
    $records = [regex]::Matches($Text, '(?m)^.*\bLogPakFile:\s*Display:\s*"([^"]+)" offset: \d+, size: (\d+) bytes, sha1: [0-9A-Fa-f]{40}\.\s*$')
    if ($summary.Count -ne 1 -or $records.Count -eq 0) { throw 'Missing/ambiguous pak summary or empty listing' }
    $count = [int64]$summary[0].Groups[1].Value
    $bytes = [int64]$summary[0].Groups[2].Value
    $filteredBytes = [int64]$summary[0].Groups[3].Value
    [int64]$listedBytes = 0
    foreach ($record in $records) { $listedBytes += [int64]$record.Groups[2].Value }
    # No SizeFilter is passed: all records and their bytes must be present.
    if ($count -ne $records.Count -or $bytes -le 0 -or $bytes -ne $listedBytes -or $filteredBytes -ne $bytes) {
        throw 'Pak listing count/byte totals do not match its complete summary'
    }
    foreach ($record in $records) {
        if ([int64]$record.Groups[2].Value -gt 0) { $record.Groups[1].Value.Replace('\', '/') }
    }
}
$staged = "$port\UnrealTournament\Saved\StagedBuilds\HTML5"
$paks = @(Get-ChildItem $staged -Recurse -Filter '*.pak')
if (!$paks.Count) { throw 'No staged pak; inspect UAT stage path' }
$listedPaths = @()
for ($i = 0; $i -lt $paks.Count; $i++) {
    Invoke-Checked $unrealPak @($paks[$i].FullName, '-Test') "$scratch\pak-$i-test.log"
    $listLog = "$scratch\pak-$i-list.log"
    $savedErrors = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $unrealPak $paks[$i].FullName '-List' > $listLog 2>&1
        $listCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedErrors }
    Get-Content -LiteralPath $listLog -Tail 5
    $listedPaths += @(Read-PinnedPakListing (Get-Content -Raw -LiteralPath $listLog) $listCode)
    Get-FileHash -Algorithm SHA256 -LiteralPath $paks[$i].FullName
}
$required = @(
    '/Content/RestrictedAssets/Maps/WIP/DM-DeckTest.umap',
    '/Content/RestrictedAssets/Maps/UT-Entry.umap',
    '/Content/RestrictedAssets/Maps/DM-Outpost23.umap',
    '/AssetRegistry.bin',
    '/GlobalShaderCache-GLSL_ES2_WEBGL.bin'
)
foreach ($entry in $required) {
    if (!($listedPaths | Where-Object { $_.EndsWith($entry, [StringComparison]::Ordinal) })) {
        throw "Required final pak entry missing or empty: $entry"
    }
}
```

This is a minimum presence gate, not a substitute for inspection. The current Deck package intentionally does **not** pass this final rotation gate because Outpost23 is absent; preserve that failure until the final cook/package includes it. Check the actual listed entry sizes/paths, the configured `/Game/RestrictedAssets/Maps/UT-Entry` package's cooked `/Content/RestrictedAssets/Maps/UT-Entry.umap` path, expected engine/default material dependencies, compatibility packages/parents and errors in each `-Test`/`-List` log. `DevelopmentAssetRegistry.bin` is not a substitute for runtime `AssetRegistry.bin`. If this matching staging implementation deliberately stages a required shader cache loose, stop and account explicitly for that file in both stage and `.data.js` preload metadata; do not silently waive the gate.

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
  "packageFiles": ["UnrealTournament.data"],
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

Require the actual nine exports, native world readiness and a positive session epoch, successful control calls, and agreement between native viewport, canvas and real WebGL drawing buffer before measuring. Ready must require the Tournament controller, not merely `HasBegunPlay`: UT-Entry can tick while a multiplayer connection is pending. UT-Entry activity is not proof of joining a match or gameplay. FPS/p95 come from native frame advances observed in engine main-loop callbacks, not a synthetic animation loop. The harness narrowly records/exempts three known legacy startup notices; missing material/map errors, Party failures, DebugBreak, aborts, context loss and readiness timeouts remain failures. A zero engine exit after DebugBreak cannot count as a pass.

Archive the report with package/build hashes and all cook/pak/conversion logs. Even a future passing harness run still needs visible Deck/characters/weapons/material review, real input/audio checks, six-bot practice, completed rounds and **Deck → Outpost23 → Deck** travel with UT-Entry available, followed by authoritative multiplayer join/replication/reconnect testing. Do not claim gameplay readiness or replace the public streaming demo on the strength of this recipe, link success, allocator smoke or partial-package startup.

## 11. Native editor-server prerequisite and isolated packet gateway

The separate native test uses `UnrealTournamentEditor Win64 Development` with `-server`; it does not require a new Server target. Refresh TournamentBridge **after** the HTML5 build and before starting a cooker/editor using this tree. Do not run either build concurrently with a cook. For a module-only refresh, use this fork's `-NoHotReload`, not just `-NoHotReloadFromIDE`:

```powershell
# $port/$project/$ubt/$scratch refer to the isolated paths in step 2.
$env:TOURNAMENT_UT4_UCRT_VERSION = '10.0.10240.0'
Push-Location "$port\Engine\Source"
try {
    Invoke-Checked $ubt @(
        'UnrealTournamentEditor', 'Win64', 'Development', "-Project=$project",
        '-Module', 'TournamentBridge', '-NoHotReload', '-NoUBTMakefiles', '-2015'
    ) "$scratch\native-tournamentbridge-build.log"
} finally { Pop-Location }
```

In this UBT revision, a nonempty module selection can independently request hot reload; `-NoHotReloadFromIDE` only disables the IDE detection route. Module filtering also does not build a missing game-module import library. The observed LNK1181 required `UnrealTournament/Intermediate/Build/Win64/UE4Editor/Development/UE4Editor-UnrealTournament.lib`.

The operator's subsequent native build passed in **3.94 seconds** with `-NoHotReload` after restoring that single audited import library. The original and isolated `UE4Editor-UnrealTournament.dll` were byte-identical (SHA-256 `B606926A26ADFBBACCCC80B33B839DB74003DB3B7033A9B491953DD1E5692DBF`); the matching x64 import library (8,875,938 bytes, SHA-256 `B575C0FBE0F0CD3A4C9E477CA21370008853C5BC5EB5834E9DDC6238C6009E11`) referenced the expected DLL, and all 20,198 imported symbols matched its exports. This evidence applies to that exact pair. If the game DLL/source changes or the pair cannot be established, build the matching game module instead of borrowing another library. Existing launcher defaults select the original installation; always pass the isolated `-SourceRoot` explicitly.

The local diagnostic topology is Mac `127.0.0.1:9080` → SSH → Windows `127.0.0.1:9080` → fixed UDP `127.0.0.1:7797`, with native beacon `7798`. The original `7787/7788` server and rendering clients remain separate. Run the native process and gateway in foreground persistent sessions; quote PowerShell's `'-MULTIHOME=127.0.0.1'` argument to prevent numeric argument splitting. Verify both UDP bindings actually say `127.0.0.1`.

For a scratch copy of `gateway.mjs`, `package.json` and its lockfile, install with `npm.cmd ci --ignore-scripts --no-audit --no-fund`, then run with `GAME_HOST=127.0.0.1`, `GAME_PORT=7797`, `PORT=9080`, and exact `BROWSER_ORIGINS=http://127.0.0.1:8077`. On Mac keep this SSH command foreground:

```sh
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -o BatchMode=yes \
  -L 127.0.0.1:9080:127.0.0.1:9080 jacks@192.168.7.209
```

The WebSocket endpoint is `ws://127.0.0.1:9080/game`, subprotocol `binary`. `/health`, accepted-origin upgrade, wrong-origin rejection and released connection slots verify gateway admission and the tunnel only. A bound native socket and completed Deck load do not establish a browser gameplay handshake, replication, or six-player operation. Preserve native/gateway logs separately from cook logs and complete those gameplay checks before enabling Multiplayer for users.


Actual two-client checkpoint, 2026-09-21 20:41–20:43 UTC: independent Chrome contexts loaded sequentially using the unchanged localhost:8077 multiplayer manifest. Both reached native Tournament match readiness, while the server logged distinct identities `emscripten-00024` and `emscripten-00029` and different full stats IDs. Gateway health observed two simultaneous connections. A sent/received 1,163/1,872 WebSocket frames; B sent/received 323/641. Both directions carried framed game traffic; these counts are not necessarily UDP-packet counts.

Clicking the launcher's **Reconnect** closed A's original socket, then failed downloading `UnrealTournament.data` with `net::ERR_FAILED`; no replacement socket opened. The endpoint returned HTTP 200 afterward, but the failure cause remains unresolved. Both owned test contexts/browser were closed and gateway admission returned to zero. This is a handshake pass and a reconnect failure, with no rendering/FPS claim. Retained diagnostics include the initial UT-Entry travel error followed by successful map load, invalid reflection-capture data, async I/O queue overflow, and a native legacy replay-service failure. Private evidence remains under the workspace's `work/ut4-html5/mp-handshake-C9AkO6/` (`report.json`, `summary.md`, `native-join-evidence.log`, screenshots); the original bounded probe is `work/ut4-html5/probe-multiplayer.cjs`.


Reconnect investigation follow-up: the old eager-Blob path failed even for one real client. CDP observed HTTP 200 followed by `net::ERR_FAILED`, zero response-body bytes and no retrievable response body. Collecting the old realm reduced backing storage from roughly 1.59 GB to 27 KB but did not make Retry succeed. A byte-to-Blob experiment then exposed browser `BlobStatus::ERR_OUT_OF_MEMORY` and `ERR_REFERENCED_BLOB_BROKEN`; that unsuccessful candidate was removed. Blob resource exhaustion is observed; an exact effective quota and the contribution of inspector-retained response handles are not independently measured.

The loader now supports explicit `"packageFiles": ["UnrealTournament.data"]` (included in the example above). It lets the unmodified 1.36 packager's ArrayBuffer XHR load the declared package URL directly, without a package Blob. A real single-client direct-package reconnect reached native readiness again without forced GC. The subsequent two-client run does **not** establish reconnect success: A asserted in native `Array.h:633` before the reconnect click, and the engine pair changed during the run. Keep complete two-client reconnect status unverified until retested against stable matching artifacts. Fixture/validation checks passed: 80 tests, no failures, one headed-only check skipped. The owned 7797 server now runs with `-NoReplays`; the matching engine logged its explicit rejection of replay recording. No live-server settings were changed.


A further two-client run used stable new Outline/IO engine artifacts (WASM SHA-256 `2c5d5e1fc58c27639c223bec1a883710f3583724aef3df1322f55b0a814445f3`) and unchanged v2 Deck data, with the explicit package field confined to the probe's own manifest responses. Fingerprints before/after matched. Both clients initially reached native readiness; A then hit the same native `Array.h:633` bounds assertion as B joined and disappeared before Reconnect. No package download failed. This is **not** a two-client reconnect pass. Evidence: private `work/ut4-html5/mp-reconnect-KkaaFw/`; current implementation/test/report hashes are in `work/ut4-html5/reconnect-checkpoint.json`. All owned probe browsers were closed and gateway health returned zero connections before the operator's v3 data swap.


V3 installation receipt: private `work/ut4-html5/rotation-v3-swap-receipt.json`. The macOS `renamex_np(RENAME_SWAP)` directory exchange preserved the full former directory as `work/ut4-html5/converted-game.before-rotation-v3-20260921T211505Z/`; all engine/bootstrap file hashes were unchanged. HTTP Content-Length and served data-script metadata both report 1,826,054,717 bytes. The canonical private operator manifest now enables `packageFiles: ["UnrealTournament.data"]`, as does the example manifest.

Runtime diagnostic capture now retains the actual `Expression 'UniformBuffer' failed in ...OpenGLShaders.cpp:2858!` shape, bounded to 1,800 characters, before a bare Error. It supersedes stale initial-travel text for this assertion shape. Three focused diagnostic fixtures passed; canonical verifier severity/skip rules and practice-menu pause behavior were not changed.

The later HUD draw crash is traced to the temporary Canvas tile view missing its default mobile directional-light buffer. `patch-browser-tile-light.py` pins the inspected method and initializes slot zero only for the browser below SM4 when it is absent. Native behavior and valid copied buffers remain unchanged. Six local checks, including the private actual method and compiled insert semantics, pass; the patch was independently reviewed. The subsequent HTML5 build passed in 340.15 seconds with all nine exports. The matching runtime completed a 30-second fixed-1080p observation without that assertion. Its first screenshot shows the arena and a bot, but the final screenshot shows sky and weapon; scene correctness is under investigation, so this is not a gameplay or performance acceptance result. The headless diagnostic recorded 1,800 native ticks in 30 seconds and 18.4 ms p95 callback intervals; these are not presented FPS or a representative gameplay benchmark.
