param([string]$SourceRoot='F:\TournamentUT4\source\UnrealTournament-clean-master')
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root=(Resolve-Path -LiteralPath $SourceRoot).Path
$file="$root\Engine\Source\Programs\UnrealBuildTool\Windows\VCEnvironment.cs"
$text=[IO.File]::ReadAllText($file)
$needle=[regex]::Match($text,"static string FindUniversalCRTVersion\(string UniversalCRTDir\)\s*\{").Value
if(!$text.Contains('TOURNAMENT_UT4_UCRT_VERSION')) {
 if([string]::IsNullOrEmpty($needle)){throw 'Expected UCRT selection function not found'}
 Copy-Item $file "$file.original"
 $replacement=$needle+@'

            string PinnedVersion = Environment.GetEnvironmentVariable("TOURNAMENT_UT4_UCRT_VERSION");
            if (!String.IsNullOrEmpty(PinnedVersion))
            {
                if (String.IsNullOrEmpty(UniversalCRTDir) || !Directory.Exists(Path.Combine(UniversalCRTDir, "include", PinnedVersion, "ucrt")))
                {
                    throw new BuildException("Tournament UCRT version not installed: " + PinnedVersion);
                }
                return PinnedVersion;
            }
'@
 [IO.File]::WriteAllText($file,$text.Replace($needle,$replacement))
}
& 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe' "$root\Engine\Source\Programs\UnrealBuildTool\UnrealBuildTool.csproj" /nologo /verbosity:minimal /p:Configuration=Development /p:Platform=AnyCPU
exit $LASTEXITCODE
