param([string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$env:TOURNAMENT_UT4_UCRT_VERSION='10.0.10240.0'
$root=(Resolve-Path -LiteralPath $SourceRoot).Path
$logs=Join-Path $root 'UnrealTournament\Saved\Logs\Tournament'
New-Item -ItemType Directory -Force $logs | Out-Null
Set-Location "$root\Engine\Source"
& "$root\Engine\Binaries\DotNET\UnrealBuildTool.exe" UnrealTournamentEditor Win64 Development "-project=$root\UnrealTournament\UnrealTournament.uproject" -Module UnrealTournament -NoHotReloadFromIDE -2015 2>&1 | Tee-Object -FilePath (Join-Path $logs 'build-base.log')
exit $LASTEXITCODE
