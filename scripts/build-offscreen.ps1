param([string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master')
$ErrorActionPreference='Stop'
$env:TOURNAMENT_UT4_UCRT_VERSION='10.0.10240.0'
$r=(Resolve-Path $SourceRoot).Path
if(Get-CimInstance Win32_Process -Filter "name='UE4Editor.exe'" | Where-Object { $_.ExecutablePath -like "$r\*" }) {
    throw 'Stop game processes in this installation before rebuilding its graphics module.'
}
$viewport=Join-Path $r 'Engine\Source\Runtime\Windows\D3D11RHI\Private\Windows\WindowsD3D11Viewport.cpp'
if(!(Select-String -Path $viewport -SimpleMatch 'TournamentOffscreen' -Quiet)) {
    throw 'Run python scripts/enable-offscreen.py SOURCE_ROOT first.'
}
Push-Location "$r\Engine\Source"
try {
    & "$r\Engine\Binaries\DotNET\UnrealBuildTool.exe" UnrealTournamentEditor Win64 Development "-project=$r\UnrealTournament\UnrealTournament.uproject" -Module D3D11RHI -NoHotReloadFromIDE -2015
    if($LASTEXITCODE -ne 0) { throw 'D3D11RHI build failed.' }
} finally { Pop-Location }
