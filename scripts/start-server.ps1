[CmdletBinding()]
param(
    [string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master',
    [ValidateRange(1024,65535)][int]$Port=7787,
    [ValidateSet('127.0.0.1','0.0.0.0')][string]$ListenAddress='127.0.0.1',
    [ValidateRange(1,60)][int]$Minutes=15,
    [ValidateRange(1,500)][int]$Frags=30,
    [switch]$AcceptLicense,
    [switch]$ValidateOnly
)
. "$PSScriptRoot\runtime-common.ps1"
$layout=Get-TournamentLayout $SourceRoot
if ($ValidateOnly) { $layout; return }
Confirm-TournamentLicense $layout $AcceptLicense.IsPresent
$map='/Game/RestrictedAssets/Maps/WIP/DM-DeckTest?Game=/Script/TournamentBridge.TournamentDeathmatch?Mutator=TournamentBridge.TournamentBridgeMutator?BotFill=7?MaxPlayers=7?LAN=1?RequireReady=0?MaxPlayerWait=3?Difficulty=3?TimeLimit='+$Minutes+'?GoalScore='+$Frags
Start-TournamentNative $layout @($map,'-server','-nullrhi','-nosound','-unattended','-LAN',"-port=$Port","-MULTIHOME=$ListenAddress") 'server'
