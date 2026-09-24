// Original build target for the experimental local-rendering browser port.
using UnrealBuildTool;
using System.Collections.Generic;

public class TournamentBrowserTarget : TargetRules
{
    public TournamentBrowserTarget(TargetInfo Target)
    {
        Type = TargetType.Game;
        bUsesCEF3 = false;
        UEBuildConfiguration.bUseLoggingInShipping = true;
        UEBuildConfiguration.bUseChecksInShipping = true;
        UEBuildConfiguration.bCompileBox2D = false;
    }

    public override bool ShouldCompileMonolithic(UnrealTargetPlatform Platform, UnrealTargetConfiguration Configuration)
    {
        return true;
    }

    public override void SetupBinaries(TargetInfo Target,
        ref List<UEBuildBinaryConfiguration> Binaries, ref List<string> Modules)
    {
        Modules.Add("UnrealTournament");
        Modules.Add("UnrealTournamentFullScreenMovie");
        // OnlineSubsystemNull is supplied by its enabled plugin. Listing it as
        // a game module too creates an empty extra library in this legacy UBT.
    }

    public override void SetupGlobalEnvironment(TargetInfo Target,
        ref LinkEnvironmentConfiguration LinkEnvironment,
        ref CPPEnvironmentConfiguration CompileEnvironment)
    {
        UEBuildConfiguration.bWithPerfCounters = false;
    }
}
