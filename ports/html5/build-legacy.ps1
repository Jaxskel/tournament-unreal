param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [ValidateSet('Development','Shipping')][string]$Configuration='Development',
    [ValidateRange(1,8)][int]$Workers=2
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=(Resolve-Path -LiteralPath $SourceRoot).Path
if(!(Test-Path "$root\.tournament-browser-port")){throw 'Use an isolated checkout marked .tournament-browser-port'}
& py -3 "$PSScriptRoot\configure-legacy.py" $root
if($LASTEXITCODE){throw 'Legacy toolchain configuration failed'}
& "$PSScriptRoot\..\..\scripts\install-plugin.ps1" -SourceRoot $root
& py -3 "$PSScriptRoot\configure-browser-config.py" $root
if($LASTEXITCODE){throw 'Browser platform configuration failed'}
& py -3 "$PSScriptRoot\patch-networking.py" $root
if($LASTEXITCODE){throw 'Browser network patch failed'}
& py -3 "$PSScriptRoot\patch-browser-pacing.py" $root
if($LASTEXITCODE){throw 'Browser pacing patch failed'}
& py -3 "$PSScriptRoot\patch-browser-glue.py" $root
if($LASTEXITCODE){throw 'Browser glue patch failed'}
& py -3 "$PSScriptRoot\patch-browser-logging.py" $root
if($LASTEXITCODE){throw 'Browser logging patch failed'}
& py -3 "$PSScriptRoot\patch-browser-party.py" $root --apply
if($LASTEXITCODE){throw 'Browser failed-map callback patch failed'}
& py -3 "$PSScriptRoot\patch-browser-window.py" $root --apply
if($LASTEXITCODE){throw 'Browser fixed-resolution window patch failed'}
& py -3 "$PSScriptRoot\patch-browser-outline.py" $root --apply
if($LASTEXITCODE){throw 'Browser Outline postprocess patch failed'}
& py -3 "$PSScriptRoot\patch-browser-asyncio.py" $root --apply
if($LASTEXITCODE){throw 'Browser redundant AsyncIO hint patch failed'}
$logDir="$root\UnrealTournament\Saved\Logs\BrowserPort"
New-Item -ItemType Directory -Force $logDir | Out-Null
$configDir="$root\Engine\Saved\UnrealBuildTool"
New-Item -ItemType Directory -Force $configDir | Out-Null
[IO.File]::WriteAllText("$configDir\BuildConfiguration.xml", @"
<Configuration xmlns="https://www.unrealengine.com/BuildConfiguration">
  <BuildConfiguration><MaxProcessorCount>$Workers</MaxProcessorCount><bAllowXGE>false</bAllowXGE></BuildConfiguration>
</Configuration>
"@)
& "$PSScriptRoot\..\..\scripts\pin-ucrt.ps1" -SourceRoot $root > "$logDir\build-tool.log"
if($LASTEXITCODE){throw "Build-tool compilation failed; see $logDir\build-tool.log"}
$previousUcrt=$env:TOURNAMENT_UT4_UCRT_VERSION
$previousEmccCores=$env:EMCC_CORES
try {
    $env:TOURNAMENT_UT4_UCRT_VERSION='10.0.10240.0'
    $env:EMCC_CORES=[string]$Workers
    Push-Location "$root\Engine\Source"
    try {
        # PowerShell 5.1 otherwise treats a compiler's stderr warning as a
        # terminating NativeCommandError. Preserve output and use its exit code.
        $previousErrors=$ErrorActionPreference
        try {
            $ErrorActionPreference='Continue'
            & "$root\Engine\Binaries\DotNET\UnrealBuildTool.exe" TournamentBrowser HTML5 $Configuration "-Project=$root\UnrealTournament\UnrealTournament.uproject" -NoUBTMakefiles -NoHotReload -2015 > "$logDir\compile.log" 2>&1
            $result=$LASTEXITCODE
        } finally { $ErrorActionPreference=$previousErrors }
    } finally { Pop-Location }
} finally {
    $env:TOURNAMENT_UT4_UCRT_VERSION=$previousUcrt
    $env:EMCC_CORES=$previousEmccCores
}
Get-Content "$logDir\compile.log" -Tail 30
if (Select-String -Path "$logDir\compile.log" -Pattern 'unresolved symbol:|undefined symbol:') {
    throw 'Unresolved browser symbols remain; do not deploy this build'
}
if ($result -eq 0) {
    $binaryName=if($Configuration -eq 'Shipping'){'TournamentBrowser-HTML5-Shipping.js'}else{'TournamentBrowser.js'}
    $javascript=Join-Path "$root\UnrealTournament\Binaries\HTML5" $binaryName
    foreach ($name in @('Ready','SessionEpoch','Width','Height','Frame','SetResolution','SetSensitivity','SetVolume','ReleaseInput')) {
        if (!(Select-String -LiteralPath $javascript -SimpleMatch -Quiet -Pattern ('Module["_TournamentBrowser'+$name+'"]'))) {
            throw "Missing browser control export: TournamentBrowser$name"
        }
    }
}
exit $result
