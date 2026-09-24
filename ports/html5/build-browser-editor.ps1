param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [ValidateRange(1,8)][int]$Workers=2,
    [switch]$ExperimentalGpuSkin8
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=(Resolve-Path -LiteralPath $SourceRoot).Path
$gpuArgs=@($root,'--phase','native-editor','--editor-plan')
if($ExperimentalGpuSkin8){$gpuArgs+='--experimental-gpu-skin8'}
$preflight=& py -3 "$PSScriptRoot\configure-browser-gpu-skin.py" @gpuArgs
if($LASTEXITCODE){throw 'GPU skin experiment preflight failed'}
# Global compiler guard; editor executable/project ownership is scoped to this physical root.
$admission=& py -3 "$PSScriptRoot\browser-build-admission.py" $root
if($LASTEXITCODE){throw 'Editor/compiler admission failed; coordinate the selected source freeze first'}
Write-Output $admission
$inputs=& py -3 "$PSScriptRoot\configure-browser-gpu-skin.py" @gpuArgs --apply
if($LASTEXITCODE){throw 'GPU skin experiment source configuration failed'}
$plan=($inputs -join "`n") | ConvertFrom-Json
if($ExperimentalGpuSkin8){Write-Warning $plan.notice}
$logDir="$root\UnrealTournament\Saved\Logs\BrowserPort"
New-Item -ItemType Directory -Force $logDir | Out-Null
$inputs | Set-Content -LiteralPath "$logDir\gpu-skin-editor-inputs.json" -Encoding UTF8
$configDir="$root\Engine\Saved\UnrealBuildTool"
New-Item -ItemType Directory -Force $configDir | Out-Null
[IO.File]::WriteAllText("$configDir\BuildConfiguration.xml", @"
<Configuration xmlns="https://www.unrealengine.com/BuildConfiguration">
  <BuildConfiguration><MaxProcessorCount>$Workers</MaxProcessorCount><bAllowXGE>false</bAllowXGE></BuildConfiguration>
</Configuration>
"@)
# Preserve caller environment even when a native command fails.
$priorUcrt=[Environment]::GetEnvironmentVariable('TOURNAMENT_UT4_UCRT_VERSION','Process')
try {
    $env:TOURNAMENT_UT4_UCRT_VERSION='10.0.10240.0'
    Push-Location "$root\Engine\Source"
    try {
        $index=0
        foreach($command in $plan.commands){
            $index++
            $exe=[string]$command[0]
            $arguments=@($command | Select-Object -Skip 1)
            $previousErrors=$ErrorActionPreference
            try {
                $ErrorActionPreference='Continue'
                & $exe @arguments 2>&1 | Tee-Object -FilePath "$logDir\gpu-skin-editor-$index.log"
                $code=$LASTEXITCODE
            } finally {$ErrorActionPreference=$previousErrors}
            if($code -ne 0){throw "Native build failed ($code); see gpu-skin-editor-$index.log"}
        }
    } finally {Pop-Location}
} finally {[Environment]::SetEnvironmentVariable('TOURNAMENT_UT4_UCRT_VERSION',$priorUcrt,'Process')}
Write-Output 'Native build commands completed. Shader cook, package coherence and private runtime validation remain separate gates.'
