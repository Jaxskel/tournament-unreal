[CmdletBinding()]
param([string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master', [int]$Minutes=10, [int]$Frags=30)
# Keep this supervisor alive. For unattended hosting, invoke it in a Windows
# Scheduled Task (S4U, current local user) after preparing the offscreen build.
$ErrorActionPreference='Stop'
. "$PSScriptRoot\runtime-common.ps1"
# Connection timeouts are host-owned; browser packets cannot change them.
# The native bridge retries the configured server if first-run preparation times out.
$layout=Get-TournamentLayout $SourceRoot
$engineIni=Join-Path $layout.Saved 'Config\Windows\Engine.ini'
Set-TournamentIniValue $engineIni '/Script/OnlineSubsystemUtils.IpNetDriver' 'InitialConnectTimeout' '120.0'
Set-TournamentIniValue $engineIni '/Script/OnlineSubsystemUtils.IpNetDriver' 'ConnectionTimeout' '30.0'
$owned=New-Object 'System.Collections.Generic.List[int]'
try {
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
        $client
    }
    $server
    while($true) {
        foreach($processId in $owned) {
            if(!(Get-Process -Id $processId -ErrorAction SilentlyContinue)) { throw "Game process $processId exited. Inspect its native log." }
        }
        Start-Sleep -Seconds 5
    }
} finally {
    foreach($processId in $owned) { Stop-Process -Id $processId -ErrorAction SilentlyContinue }
}
