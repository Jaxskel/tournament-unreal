using UnrealBuildTool;

public class UT4Html5Compat : ModuleRules
{
    public UT4Html5Compat(TargetInfo Target)
    {
        PrivateDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "UnrealEd", "Json", "RHI"
        });
    }
}
