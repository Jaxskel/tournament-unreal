[CmdletBinding()]
param([string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master')
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $SourceRoot).Path
$project=Join-Path $root 'UnrealTournament\UnrealTournament.uproject'
if (!(Test-Path -LiteralPath $project)) { throw 'Choose the extracted clean-master source root containing UnrealTournament/UnrealTournament.uproject.' }
$target=Join-Path $root 'UnrealTournament\Plugins\TournamentBridge'
$source=Join-Path (Split-Path -Parent $PSScriptRoot) 'Plugins\TournamentBridge'
if ([IO.Path]::GetFullPath($source) -eq [IO.Path]::GetFullPath($target)) { throw 'Run this script from a separate checkout of the Tournament integration repository.' }
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'TournamentBridge.uplugin') -Destination $target -Force
Copy-Item -LiteralPath (Join-Path $source 'Source') -Destination $target -Recurse -Force
$data=Get-Content -Raw -LiteralPath $project | ConvertFrom-Json
if (!$data.PSObject.Properties['Plugins']) { $data | Add-Member -MemberType NoteProperty -Name Plugins -Value @() }
$found=@($data.Plugins | Where-Object Name -eq 'TournamentBridge')
if ($found.Count) { $found | ForEach-Object { $_.Enabled=$true } }
else { $data.Plugins+=@([PSCustomObject]@{Name='TournamentBridge';Enabled=$true}) }
if (!(Test-Path -LiteralPath ($project+'.before-tournament'))) { Copy-Item -LiteralPath $project -Destination ($project+'.before-tournament') }
$data | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $project -Encoding UTF8
Write-Output "Installed original Tournament source in $target. Build before launching."
