param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [ValidateSet('Development','Shipping')][string]$Configuration='Development',
    [ValidateRange(1,8)][int]$Workers=2
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=(Resolve-Path -LiteralPath $SourceRoot).Path
if(!(Test-Path "$root\.tournament-browser-port")){throw 'Use an isolated checkout marked .tournament-browser-port'}
# Prepare validates the isolated SDK, both source guards and the cached native
# optimizer before any other build setup. Child environments never change ours.
$previousErrors=$ErrorActionPreference
try {
    $ErrorActionPreference='Continue'
    $prepared=& py -3 "$PSScriptRoot\prepare-browser-optimizer.py" $root prepare
    $prepareResult=$LASTEXITCODE
} finally { $ErrorActionPreference=$previousErrors }
if($prepareResult -ne 0){throw 'Guarded optimizer preparation failed'}
$optimizer=($prepared -join "`n") | ConvertFrom-Json
if(!$optimizer.selection){throw 'Guarded optimizer selection receipt missing'}
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
& py -3 "$PSScriptRoot\patch-browser-tile-light.py" $root --apply
if($LASTEXITCODE){throw 'Browser canvas tile lighting patch failed'}
& py -3 "$PSScriptRoot\patch-browser-lineup.py" $root --apply
if($LASTEXITCODE){throw 'Browser intro schedule bounds patch failed'}
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
# Always invalidate the previous JS/BC/memory/symbol generation together. This
# intentionally pays a full HTML5 link per call: UBT does not track optimizer
# tools/environment as prerequisites. Prior outputs stay in a hashed backup.
# On failure partial outputs are quarantined; the prior generation is NOT
# restored automatically. Inspect its receipt before deliberate recovery.
# Timeout/interrupt drains the owned process tree before quarantine/unlock. If
# drain cannot be confirmed, the lock and live output paths remain for recovery.
$previousErrors=$ErrorActionPreference
try {
    $ErrorActionPreference='Continue'
    & py -3 "$PSScriptRoot\prepare-browser-optimizer.py" $root link --selection $optimizer.selection --configuration $Configuration --workers $Workers
    $result=$LASTEXITCODE
} finally { $ErrorActionPreference=$previousErrors }
if(Test-Path "$logDir\compile.log"){Get-Content "$logDir\compile.log" -Tail 30}
exit $result
