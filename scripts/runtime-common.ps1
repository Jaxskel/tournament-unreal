Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-TournamentLayout([string]$SourceRoot) {
    $root = (Resolve-Path -LiteralPath $SourceRoot).Path
    $project = Join-Path $root 'UnrealTournament\UnrealTournament.uproject'
    $engine = Join-Path $root 'Engine\Binaries\Win64\UE4Editor.exe'
    $plugin = Join-Path $root 'UnrealTournament\Plugins\TournamentBridge\Binaries\Win64\UE4Editor-TournamentBridge.dll'
    foreach ($file in @($project, $engine, $plugin)) {
        if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing required file: $file. Install and build the plugin first." }
    }
    $builtAt = (Get-Item -LiteralPath $plugin).LastWriteTimeUtc
    $pluginSource = Join-Path $root 'UnrealTournament\Plugins\TournamentBridge\Source'
    $newer = @(Get-ChildItem -LiteralPath $pluginSource -Recurse -File | Where-Object { $_.LastWriteTimeUtc -gt $builtAt.AddSeconds(2) })
    if ($newer.Count) { throw 'TournamentBridge source is newer than its DLL. Run build-plugin.ps1 successfully before launching.' }
    $version = Get-Content -Raw (Join-Path $root 'Engine\Build\Build.version') | ConvertFrom-Json
    if ($version.MajorVersion -ne 4 -or $version.MinorVersion -ne 15 -or $version.Changelist -ne 3228288) {
        throw 'These development launchers require the recovered UE4.15 CL3228288 source/editor. Do not mix shipping-client revisions.'
    }
    return [PSCustomObject]@{ Root=$root; Project=$project; Engine=$engine; Plugin=$plugin; Saved=(Join-Path $root 'UnrealTournament\Saved') }
}

function Set-TournamentIniValue([string]$Path, [string]$Section, [string]$Key, [string]$Value) {
    $lines = if (Test-Path -LiteralPath $Path) { @(Get-Content -LiteralPath $Path) } else { @() }
    $result = New-Object 'System.Collections.Generic.List[string]'
    $inside = $false; $foundSection = $false; $written = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*\[.+\]\s*$') {
            if ($inside -and !$written) { $result.Add("$Key=$Value"); $written=$true }
            $inside = $line.Trim() -eq "[$Section]"
            if ($inside) { $foundSection=$true }
        }
        if ($inside -and $line -match ('^\s*' + [regex]::Escape($Key) + '\s*=')) {
            if (!$written) { $result.Add("$Key=$Value"); $written=$true }
        } else { $result.Add($line) }
    }
    if (!$foundSection) { $result.Add(''); $result.Add("[$Section]") }
    if (!$written) { $result.Add("$Key=$Value") }
    New-Item -ItemType Directory -Force (Split-Path -Parent $Path) | Out-Null
    [IO.File]::WriteAllLines($Path, $result, (New-Object Text.UTF8Encoding($false)))
}

function Confirm-TournamentLicense($Layout, [bool]$AcceptLicense) {
    $record = Join-Path $Layout.Saved 'Tournament\license-accepted.local.json'
    if (!$AcceptLicense -and !(Test-Path -LiteralPath $record)) {
        throw 'Read the Epic/UT license supplied with your installation. If you accept it for this local setup, rerun with -AcceptLicense. No license acceptance is automatic.'
    }
    if ($AcceptLicense) {
        New-Item -ItemType Directory -Force (Split-Path -Parent $record) | Out-Null
        @{acceptedAtUtc=[DateTime]::UtcNow.ToString('o');scope='local-development';source='explicit-launcher-flag'} | ConvertTo-Json | Set-Content -LiteralPath $record
    }
    # Epic's dedicated server cannot display the first-run agreement dialog.
    Set-TournamentIniValue (Join-Path $Layout.Saved 'Config\Windows\Engine.ini') '/Script/UnrealTournament.UTGameEngine' 'bFirstRun' 'False'
}

function Start-TournamentNative($Layout, [string[]]$Arguments, [string]$LogName) {
    $logs = Join-Path $Layout.Saved 'Logs\Tournament'
    New-Item -ItemType Directory -Force $logs | Out-Null
    $log = Join-Path $logs ($LogName + '.log')
    $argsList = @('"' + $Layout.Project + '"') + $Arguments + @('-NoSplash', '-NoMCP', '-log', ('-abslog="' + $log + '"'))
    $process = Start-Process -FilePath $Layout.Engine -ArgumentList $argsList -WorkingDirectory $Layout.Root -PassThru
    $result = [PSCustomObject]@{ pid=$process.Id; log=$log; startedAtUtc=[DateTime]::UtcNow.ToString('o') }
    $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logs ($LogName + '.local.json'))
    return $result
}
