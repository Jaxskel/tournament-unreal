// Original TournamentBridge code. No Epic implementation is included.
using UnrealBuildTool;

public class TournamentBridge : ModuleRules
{
    public TournamentBridge(TargetInfo Target)
    {
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "UnrealTournament"
        });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "Sockets", "ImageWrapper", "RHI", "RenderCore", "SlateCore" });
        // Private, explicit diagnostic build only. Unsupported targets fail closed.
        bool PhysicsReport = System.Environment.GetEnvironmentVariable("TOURNAMENT_UT4_PHYSICS_REPORT") == "1";
        if (PhysicsReport && (Target.Platform != UnrealTargetPlatform.HTML5 ||
            Target.Configuration == UnrealTargetConfiguration.Shipping || !UEBuildConfiguration.bCompilePhysX))
        {
            throw new BuildException("TOURNAMENT_UT4_PHYSICS_REPORT requires a non-Shipping HTML5 PhysX build.");
        }
        Definitions.Add("TOURNAMENT_HTML5_PHYSICS_DIAGNOSTICS=" + (PhysicsReport ? "1" : "0"));
        if (PhysicsReport) PrivateDependencyModuleNames.Add("PhysX");
    }
}
