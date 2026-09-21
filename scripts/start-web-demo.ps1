[CmdletBinding()]
param(
    [string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master',
    [Parameter(Mandatory=$true)][string]$Cloudflared,
    [string]$Node='C:\Program Files\nodejs\node.exe',
    [int]$Minutes=10,
    [int]$Frags=30,
    [ValidateRange(-1,15)][int]$GraphicsAdapter=-1,
    [ValidateSet(60,120)][int]$StreamFPS=120,
    [ValidateSet('540p','720p','1080p')][string]$StreamResolution='720p',
    [string]$FFmpeg
)
# Run from a persistent Windows Scheduled Task, not a short-lived SSH child.
# Install browser npm dependencies and build the native offscreen plugin first.
$ErrorActionPreference='Stop'
if($FFmpeg -and !(Test-Path $FFmpeg -PathType Leaf)) { throw 'FFmpeg executable not found.' }
$env:FFMPEG_PATH=$FFmpeg
$env:STREAM_FPS=[string]$StreamFPS
$env:STREAM_RESOLUTION=$StreamResolution
$repo=Split-Path $PSScriptRoot -Parent
$state=Join-Path $SourceRoot 'UnrealTournament\Saved\Tournament\Web'
New-Item -ItemType Directory -Force $state | Out-Null
if(!(Test-Path "$repo\browser\node_modules\ws")) { throw 'Run npm ci in browser first.' }
if(Get-NetTCPConnection -LocalPort 8890 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8890 is in use; stop the existing demo first.' }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$tunnelLog=Join-Path $state "tunnel-$stamp.log"
$tunnel=$null; $gateway=$null
try {
    $tunnel=Start-Process -FilePath $Cloudflared -ArgumentList @('tunnel','--url','http://127.0.0.1:8890','--no-autoupdate','--logfile',('"'+$tunnelLog+'"')) -PassThru
    $origin=$null
    for($i=0;$i -lt 60;$i++) {
        if($tunnel.HasExited) { throw 'Public tunnel exited before becoming ready.' }
        if(Test-Path $tunnelLog) {
            $match=[regex]::Match((Get-Content -Raw $tunnelLog),'https://[a-z0-9-]+\.trycloudflare\.com')
            if($match.Success) { $origin=$match.Value; break }
        }
        Start-Sleep -Seconds 1
    }
    if(!$origin) { throw 'No public URL after 60 seconds; inspect tunnel log.' }
    $env:PUBLIC_ORIGIN=$origin
    $gateway=Start-Process -FilePath $Node -ArgumentList 'server.js' -WorkingDirectory "$repo\browser" -RedirectStandardOutput "$state\gateway.log" -RedirectStandardError "$state\gateway-error.log" -PassThru
    @{url=$origin;startedAtUtc=[DateTime]::UtcNow.ToString('o');rewards=$false;audio=$false;capacity=2} | ConvertTo-Json | Set-Content "$state\current-demo.local.json"
    Write-Output "Browser demo URL: $origin"
    Write-Output 'Game content may need several minutes to build its initial cache.'
    & "$PSScriptRoot\start-web-game.ps1" -SourceRoot $SourceRoot -Minutes $Minutes -Frags $Frags -GraphicsAdapter $GraphicsAdapter -HardwareVideo:([bool]$FFmpeg) -StreamFPS $StreamFPS -StreamResolution $StreamResolution
} finally {
    if($gateway -and !$gateway.HasExited) { Stop-Process -Id $gateway.Id -ErrorAction SilentlyContinue }
    if($tunnel -and !$tunnel.HasExited) { Stop-Process -Id $tunnel.Id -ErrorAction SilentlyContinue }
}
