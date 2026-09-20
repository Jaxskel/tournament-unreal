[CmdletBinding()]
param(
    [string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master',
    [ValidatePattern('^[A-Za-z0-9.-]+:[0-9]{1,5}$')][string]$Server='127.0.0.1:7787',
    [ValidatePattern('^[A-Za-z0-9_-]{1,20}$')][string]$Name='Player',
    [switch]$Headless,
    [switch]$AcceptLicense,
    [switch]$ValidateOnly
)
. "$PSScriptRoot\runtime-common.ps1"
if ([int]($Server.Split(':')[-1]) -lt 1 -or [int]($Server.Split(':')[-1]) -gt 65535) { throw 'Invalid server port.' }
$layout=Get-TournamentLayout $SourceRoot
if ($ValidateOnly) { $layout; return }
Confirm-TournamentLicense $layout $AcceptLicense.IsPresent
$destination=$Server+'?Name='+$Name+'?VersionCheck=1'
$arguments=@($destination,'-game','-LAN','-windowed','-ResX=1280','-ResY=720')
if ($Headless) { $arguments+=@('-nullrhi','-nosound','-unattended') }
Start-TournamentNative $layout $arguments ('client-'+$Name)
