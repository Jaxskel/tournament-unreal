[CmdletBinding()]
param(
    [string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master',
    [ValidateRange(1,60)][int]$Minutes=10,
    [ValidateRange(1,500)][int]$Frags=30,
    [ValidateRange(1,60)][int]$RestartDelaySeconds=3,
    [ValidateRange(30,600)][int]$FrameTimeoutSeconds=120,
    [switch]$Once
)
# Run under a Scheduled Task. The supervisor owns retries, rather than relying
# on Task Scheduler's finite restart counter. Stop the task to stop hosting.
$ErrorActionPreference='Stop'
. "$PSScriptRoot\runtime-common.ps1"
$layout=Get-TournamentLayout $SourceRoot
$logs=Join-Path $layout.Saved 'Logs\Tournament'
New-Item -ItemType Directory -Force $logs | Out-Null
$supervisorLog=Join-Path $logs 'supervisor.log'
function Write-SupervisorLog([string]$Message) {
    $line=([DateTime]::UtcNow.ToString('o')+' '+$Message)
    Add-Content -LiteralPath $supervisorLog -Value $line -Encoding UTF8
    Write-Host $line
}
$engineIni=Join-Path $layout.Saved 'Config\Windows\Engine.ini'
Set-TournamentIniValue $engineIni '/Script/OnlineSubsystemUtils.IpNetDriver' 'InitialConnectTimeout' '120.0'
Set-TournamentIniValue $engineIni '/Script/OnlineSubsystemUtils.IpNetDriver' 'ConnectionTimeout' '30.0'
while($true) {
    $owned=New-Object 'System.Collections.Generic.List[int]'
    try {
        Write-SupervisorLog 'Starting arena and preloading both browser seats.'
        $server=& "$PSScriptRoot\start-server.ps1" -SourceRoot $SourceRoot -Minutes $Minutes -Frags $Frags
        $owned.Add($server.pid)
        $ready=$false
        for($attempt=0;$attempt -lt 120;$attempt++) {
            if(!(Get-Process -Id $server.pid -ErrorAction SilentlyContinue)) { throw 'Native server exited; inspect server.log.' }
            if(Get-NetUDPEndpoint -LocalPort 7787 -ErrorAction SilentlyContinue | Where-Object OwningProcess -eq $server.pid) { $ready=$true; break }
            Start-Sleep -Seconds 1
        }
        if(!$ready) { throw 'Server did not bind its game port within two minutes.' }
        foreach($seat in 0,1) {
            $name=if($seat -eq 0){'BrowserOne'}else{'BrowserTwo'}
            $client=& "$PSScriptRoot\join-game.ps1" -SourceRoot $SourceRoot -Name $name -StreamSeat $seat
            $owned.Add($client.pid)
        }
        Write-SupervisorLog ("Native processes: "+($owned -join ', '))
        $lastFresh=@([DateTime]::UtcNow,[DateTime]::UtcNow)
        $announced=$false
        while($true) {
            foreach($processId in $owned) {
                if(!(Get-Process -Id $processId -ErrorAction SilentlyContinue)) { throw "Game process $processId exited." }
            }
            $health=$null
            try { $health=Invoke-RestMethod 'http://127.0.0.1:8890/api/health' -TimeoutSec 3 } catch {
                # A gateway outage does not prove that a native process is stuck.
                Write-SupervisorLog 'Gateway unavailable; retaining native processes.'
            }
            if($null -ne $health) {
                $fresh=0
                for($seat=0;$seat -lt 2;$seat++) {
                    $state=$health.seats[$seat]
                    if($state.nativeConnected -and $null -ne $state.frameAgeMs -and $state.frameAgeMs -lt 5000) {
                        $lastFresh[$seat]=[DateTime]::UtcNow; $fresh++
                    }
                    if(([DateTime]::UtcNow-$lastFresh[$seat]).TotalSeconds -gt $FrameTimeoutSeconds) { throw "Seat $($seat+1) stopped supplying frames." }
                }
                if($fresh -eq 2 -and !$announced) { Write-SupervisorLog 'READY: both browser seats have fresh game frames.'; $announced=$true }
            }
            Start-Sleep -Seconds 2
        }
    } catch {
        Write-SupervisorLog ("Recovering: "+$_.Exception.Message)
        # Keep the failed run before native launchers overwrite their logs.
        $archive=Join-Path $logs ('recovery-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Force $archive | Out-Null
        Get-ChildItem $logs -Filter '*.log' -File | Where-Object Name -ne 'supervisor.log' | Copy-Item -Destination $archive
        Get-ChildItem $logs -Directory -Filter 'recovery-*' | Sort-Object Name -Descending | Select-Object -Skip 10 | Remove-Item -Recurse -Force
        if($Once) { throw }
    } finally {
        foreach($processId in $owned) { Stop-Process -Id $processId -ErrorAction SilentlyContinue }
    }
    Write-SupervisorLog "Restarting in $RestartDelaySeconds seconds."
    Start-Sleep -Seconds $RestartDelaySeconds
}
