$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
foreach($script in Get-ChildItem "$root\scripts" -Filter *.ps1) {
    $tokens=$null; $errors=$null
    $null=[Management.Automation.Language.Parser]::ParseFile($script.FullName,[ref]$tokens,[ref]$errors)
    if($errors.Count -gt 0) { throw ($errors | Out-String) }
}
. "$root\scripts\runtime-common.ps1"
$temp=Join-Path ([IO.Path]::GetTempPath()) ('TournamentTest-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $temp | Out-Null
try {
    $ini=Join-Path $temp 'Engine.ini'
    Set-Content $ini "[Other]`nValue=keep`n[Target]`nbFirstRun=True`nOtherSetting=keep"
    Set-TournamentIniValue $ini 'Target' 'bFirstRun' 'False'
    Set-TournamentIniValue $ini 'Target' 'bFirstRun' 'False'
    $text=Get-Content -Raw $ini
    if(([regex]::Matches($text,'bFirstRun=False')).Count -ne 1 -or !$text.Contains('Value=keep') -or !$text.Contains('OtherSetting=keep')) { throw 'INI update was not idempotent or changed unrelated keys.' }
    $layout=[PSCustomObject]@{Saved=$temp}
    $rejected=$false
    try { Confirm-TournamentLicense $layout $false } catch { $rejected=$true }
    if(!$rejected) { throw 'License gate permitted an unaccepted first launch.' }
    if(Test-Path (Join-Path $temp 'Tournament\license-accepted.local.json')) { throw 'License gate wrote acceptance without consent.' }
    Write-Output 'Launcher syntax, INI preservation, and consent gate passed.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
