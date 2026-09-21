[CmdletBinding()]
param(
    [string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master',
    [ValidatePattern('^[A-Za-z0-9.-]+:[0-9]{1,5}$')][string]$Server='127.0.0.1:7787',
    [ValidatePattern('^[A-Za-z0-9_-]{1,20}$')][string]$Name='Player',
    [switch]$HardwareVideo,
    [switch]$GpuVideo,
    [ValidateSet(60,120)][int]$StreamFPS=120,
    [ValidateSet('540p','720p','1080p','1440p')][string]$StreamResolution='720p',
    [switch]$Headless,
    [ValidateRange(-1,1)][int]$StreamSeat=-1,
    [switch]$AcceptLicense,
    [switch]$ValidateOnly
)
. "$PSScriptRoot\runtime-common.ps1"
if ($GpuVideo) { $HardwareVideo = $true }
if ([int]($Server.Split(':')[-1]) -lt 1 -or [int]($Server.Split(':')[-1]) -gt 65535) { throw 'Invalid server port.' }
$layout=Get-TournamentLayout $SourceRoot
if ($ValidateOnly) { $layout; return }
Confirm-TournamentLicense $layout $AcceptLicense.IsPresent
$destination=$Server+'?Name='+$Name+'?VersionCheck=1'
$arguments=@($destination,'-game','-LAN','-windowed')
# Capture needs headroom so a slightly late render tick does not miss its deadline.
$renderFPS=if($HardwareVideo -and $StreamFPS -eq 120){240}else{60}
if ($Headless) { $arguments+=@('-nullrhi','-nosound','-unattended') }
if ($StreamSeat -ge 0) {
    if ($Headless) { throw 'A browser stream needs a rendered viewport; do not combine StreamSeat and Headless.' }
    $streamSize=if(!$HardwareVideo){@(960,540)}elseif($StreamResolution -eq '1440p'){@(2560,1440)}elseif($StreamResolution -eq '1080p'){@(1920,1080)}elseif($StreamResolution -eq '720p'){@(1280,720)}else{@(960,540)}
    # UE4 fixes the window's maximum dimensions at creation in session zero.
    # Reserve the largest supported bounds once, then select the actual stream size.
    $windowSize=if($HardwareVideo){@(2560,1440)}else{$streamSize}
    $initialResolution='r.SetRes '+$streamSize[0]+'x'+$streamSize[1]+'w,'
    $arguments+=@(("-TournamentFramePort="+(9001+$StreamSeat)),("-TournamentInputPort="+(9101+$StreamSeat)),("-TournamentServer="+$Server),
        '-LogCmds="LogD3D11RHI Log"',('-ResX='+$windowSize[0]),('-ResY='+$windowSize[1]),'-ForceRes','-TournamentOffscreen','-nosound','-unattended',('-TournamentStreamFPS='+$StreamFPS),('-ExecCmds="'+$initialResolution+'t.MaxFPS '+$renderFPS+',r.VSync 0,t.IdleWhenNotForeground 0,r.OneFrameThreadLag 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.DepthOfFieldQuality 0,r.DefaultFeature.AntiAliasing 1,r.MaxAnisotropy 16"'))
    if ($HardwareVideo) { $arguments+='-TournamentRawFrames' }
    if ($GpuVideo) { $arguments+='-TournamentGpuVideo' }
} else { $arguments+=@('-ResX=1280','-ResY=720') }
Start-TournamentNative $layout $arguments ('client-'+$Name)
