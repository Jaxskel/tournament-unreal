[CmdletBinding()]
param(
    [string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master',
    [ValidatePattern('^[A-Za-z0-9.-]+:[0-9]{1,5}$')][string]$Server='127.0.0.1:7787',
    [ValidatePattern('^[A-Za-z0-9_-]{1,20}$')][string]$Name='Player',
    [switch]$Headless,
    [ValidateRange(-1,1)][int]$StreamSeat=-1,
    [switch]$AcceptLicense,
    [switch]$ValidateOnly
)
. "$PSScriptRoot\runtime-common.ps1"
if ([int]($Server.Split(':')[-1]) -lt 1 -or [int]($Server.Split(':')[-1]) -gt 65535) { throw 'Invalid server port.' }
$layout=Get-TournamentLayout $SourceRoot
if ($ValidateOnly) { $layout; return }
Confirm-TournamentLicense $layout $AcceptLicense.IsPresent
$destination=$Server+'?Name='+$Name+'?VersionCheck=1'
$arguments=@($destination,'-game','-LAN','-windowed')
if ($Headless) { $arguments+=@('-nullrhi','-nosound','-unattended') }
if ($StreamSeat -ge 0) {
    if ($Headless) { throw 'A browser stream needs a rendered viewport; do not combine StreamSeat and Headless.' }
    $arguments+=@(("-TournamentFramePort="+(9001+$StreamSeat)),("-TournamentInputPort="+(9101+$StreamSeat)),("-TournamentServer="+$Server),
        '-ResX=960','-ResY=540','-ForceRes','-TournamentOffscreen','-nosound','-unattended','-ExecCmds="t.MaxFPS 30,r.VSync 0,t.IdleWhenNotForeground 0"')
} else { $arguments+=@('-ResX=1280','-ResY=720') }
Start-TournamentNative $layout $arguments ('client-'+$Name)
