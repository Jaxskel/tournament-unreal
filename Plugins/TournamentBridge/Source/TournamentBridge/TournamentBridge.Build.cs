// Original TournamentBridge code. No Epic implementation is included.
using UnrealBuildTool;

public class TournamentBridge : ModuleRules
{
    public TournamentBridge(TargetInfo Target)
    {
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "UnrealTournament"
        });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "Sockets", "ImageWrapper", "RHI", "RenderCore" });
    }
}
