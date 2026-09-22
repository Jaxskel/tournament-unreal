// Original fixed-scope, read-only report. Include inside UT4Compat after WeaponPreflightReport.h.
// Six native targets: five MICs and their one selected glass parent material.
// No graph mutation, new asset, Apply, save or dirty-state clearing.
static FString WSRGlass() { return TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/Bio_HazyGlass"); }
static TArray<FString> WSRScope()
{
    TArray<FString> Paths;
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_HazyGlass_1p"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon3p"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon_1p_Inst"));
    Paths.Add(WSRGlass());
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Grenade/MIC_Grenade"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_3P"));
    Paths.Sort(); return Paths;
}
struct FWSROutput
{
    int32 Characters = 0;
    bool Emit(TSharedPtr<FJsonObject> J, const TCHAR* Kind)
    {
        J->SetStringField(TEXT("schema"), TEXT("ut4-weapon-supplement-v1"));
        J->SetStringField(TEXT("kind"), Kind);
        J->SetBoolField(TEXT("read_only"), true);
        J->SetBoolField(TEXT("apply_ready"), false);
        FString Text;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text))) return false;
        if (Text.Len() > 8 * 1024 * 1024 || Characters > 16 * 1024 * 1024 - Text.Len())
            return Fail(TEXT("WeaponSupplementReport output budget exceeded; incomplete report."));
        Characters += Text.Len();
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SUPPLEMENT %s"), *Text);
        return true;
    }
};
static bool WSRUnchanged(const TMap<FString, FString>& Files, const TMap<FString, FString>& Hashes)
{
    for (const auto& KV : Files)
        if (HashFile(KV.Value) != Hashes.FindChecked(KV.Key))
            return Fail(TEXT("WeaponSupplementReport file bytes changed: ") + KV.Value);
    return true;
}
static int32 WeaponSupplementReport(const FString& Params)
{
    FString SpecPath, OriginalContent, Forbidden;
    if (!GIsEditor || !IsInGameThread() ||
        !FParse::Value(*Params, TEXT("SupplementReportSpec="), SpecPath) ||
        !FParse::Value(*Params, TEXT("SupplementOriginalContent="), OriginalContent) || OriginalContent.IsEmpty() ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering"))) return 1;
    TSharedPtr<FJsonObject> Spec; bool ReadOnly = false, OriginalRequired = false;
    TArray<FString> Graphs; Graphs.Add(WSRGlass());
    const TArray<FString> Paths = WSRScope();
    if (!ReadJson(SpecPath, Spec) || Str(Spec, TEXT("schema")) != TEXT("ut4-weapon-supplement-v1") ||
        !Spec->TryGetBoolField(TEXT("read_only"), ReadOnly) || !ReadOnly ||
        !Spec->TryGetBoolField(TEXT("original_project_view_required"), OriginalRequired) || !OriginalRequired ||
        !WRExactPaths(Spec, TEXT("targets"), Paths) || !WRExactPaths(Spec, TEXT("graph_materials"), Graphs)) return 1;
    OriginalContent = Full(OriginalContent);
    if (!Physical(OriginalContent, false) || !IFileManager::Get().DirectoryExists(*OriginalContent)) return 1;
    TMap<FString, FString> ProjectFiles, OriginalFiles, BeforeHashes;
    // Compare every selected file before any explicit material load. The original
    // root is operator-supplied and recorded, never inferred from a package name.
    for (const FString& P : Paths)
    {
        if (FindPackage(nullptr, *P))
        { Fail(TEXT("WeaponSupplementReport requires fresh unloaded targets: ") + P); return 1; }
        FString File;
        const FString Original = Full(OriginalContent / P.Mid(6) + TEXT(".uasset"));
        if (!Within(Original, OriginalContent) || !Physical(Original, false) ||
            !FPackageName::DoesPackageExist(P, nullptr, &File)) return 1;
        const FString A = HashFile(Original), B = HashFile(File);
        if (A.IsEmpty() || A.Len() != 40 || !A.Equals(B, ESearchCase::IgnoreCase))
        { Fail(TEXT("WeaponSupplementReport selected view differs from original: ") + P); return 1; }
        ProjectFiles.Add(P, Full(File)); OriginalFiles.Add(P, Original); BeforeHashes.Add(P, B);
    }
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true); if (Registry.IsLoadingAssets()) return 1;
    FWSROutput Output; int32 MaterialRows = 0, GraphRows = 0;
    for (const FString& P : Paths)
    {
        TArray<FAssetData> Registered; Registry.GetAssetsByPackageName(FName(*P), Registered, true);
        if (!Registered.Num()) return 1;
        UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, *ObjectPath(P));
        const bool IsGlassParent = P == WSRGlass();
        if (!M || M->GetClass() != (IsGlassParent ? UMaterial::StaticClass() : UMaterialInstanceConstant::StaticClass())) return 1;
        UMaterial* Base = M->GetMaterial();
        const bool GlassFamily = IsGlassParent || P == TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_HazyGlass_1p");
        if (!Base || Base->GetPathName() != ObjectPath(GlassFamily ? WSRGlass() : WRMaster())) return 1;
        const bool Dirty = M->GetOutermost()->IsDirty();
        TSharedPtr<FJsonObject> J; if (!MRDescribe(M, Registry, J)) return 1;
        // MRDescribe expands graph nodes only when M == Base. Only the one
        // selected glass parent satisfies that condition: no weapons-master redo.
        if (IsGlassParent)
        {
            ++GraphRows;
            auto Roots = J->GetObjectField(TEXT("roots"));
            Roots->SetObjectField(TEXT("Metallic"), MRPin(Base->GetExpressionInputForProperty(MP_Metallic)));
            Roots->SetObjectField(TEXT("Roughness"), MRPin(Base->GetExpressionInputForProperty(MP_Roughness)));
            Roots->SetObjectField(TEXT("Specular"), MRPin(Base->GetExpressionInputForProperty(MP_Specular)));
            if (J->GetArrayField(TEXT("nodes")).Num() == 0) return 1;
        }
        else if (J->GetArrayField(TEXT("nodes")).Num() != 0 || J->GetObjectField(TEXT("roots"))->Values.Num() != 0) return 1;
        J->SetBoolField(TEXT("package_dirty_before_description"), Dirty);
        J->SetStringField(TEXT("view"), TEXT("selected original-file bytes; editor load may normalize in memory; not HTML5 runtime proof"));
        J->SetStringField(TEXT("original_content_root"), OriginalContent);
        J->SetStringField(TEXT("original_file"), OriginalFiles.FindChecked(P));
        J->SetStringField(TEXT("project_file"), ProjectFiles.FindChecked(P));
        J->SetStringField(TEXT("original_sha1_before"), BeforeHashes.FindChecked(P));
        J->SetBoolField(TEXT("selected_original_bytes_match"), true);
        if (!Output.Emit(J, TEXT("material"))) return 1;
        ++MaterialRows;
    }
    if (MaterialRows != 6 || GraphRows != 1 || !WSRUnchanged(ProjectFiles, BeforeHashes) || !WSRUnchanged(OriginalFiles, BeforeHashes)) return 1;
    TSharedPtr<FJsonObject> Done = MakeShareable(new FJsonObject);
    Done->SetNumberField(TEXT("materials"), MaterialRows); Done->SetNumberField(TEXT("glass_graphs"), GraphRows);
    Done->SetBoolField(TEXT("selected_original_bytes_unchanged"), true);
    Done->SetStringField(TEXT("original_content_root"), OriginalContent);
    return Output.Emit(Done, TEXT("complete")) ? 0 : 1;
}
