// Original read-only weapon report. Include after MaterialPreflightReport.h inside UT4Compat.
// Fixed original-package scope. No asset writes, graph edits, redirects or mesh transforms.
static FString WRMaster() { return TEXT("/Game/RestrictedAssets/Weapons/Global/Material/M_WeaponsBase"); }
static TArray<FString> WRScope()
{
    TArray<FString> Paths;
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/M_Enforcer_Gun"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/Material_Custom/M_Enforcer_Gun_Pattern_test_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/Materials_thirdPerson/M_Enforcer_Gun_3rdPerson_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Flak/Materials/M_Flak_Gun_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Flak/Materials/Materials_thirdPerson/M_Flak_Gun_3P_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Global/Material/M_WeaponsBase"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_Launcher_3P"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/LightningRifle/Material/MIC_Lighting_Gun_Partone"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/LightningRifle/Material/MIC_Lighting_Gun_Parttwo_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/LightningRifle/Material/Material_ThirdPerson/MIC_Lighting_Gun_Partone_3P_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/LightningRifle/Material/Material_ThirdPerson/MIC_Lighting_Gun_Parttwo_3P_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/LinkGun/Materials/MIC_LinkGun_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/LinkGun/Materials/Material_ThirdPerson/MIC_LinkGun_3P_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/RocketLauncher/Materials/MIC_Rocket_Launcher_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/RocketLauncher/Materials/Material_ThirdPerson/MIC_Rocket_Launcher_3P_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/RocketLauncher/Materials/Material_ThirdPerson/MIC_Rocket_Launcher_3P_Inst2"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Sniper/Materials/M_Sniper_Rifle_Inst"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Sniper/Materials/Materials_thridperson/M_Sniper_Rifle_3P_Inst"));
    Paths.Sort(); return Paths;
}
static TArray<FString> WRMeshes()
{
    TArray<FString> Paths;
    Paths.Add(TEXT("/Game/RestrictedAssets/Character/Malcom_New/Meshes/malcolm_1p"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Character/Malcom_New/Meshes/malcolm_3p"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_1p"));
    Paths.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_3p"));
    Paths.Sort(); return Paths;
}
static bool WRExactPaths(const TSharedPtr<FJsonObject>& Spec, const TCHAR* Key, const TArray<FString>& Expected)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Spec->TryGetArrayField(Key, Values) || Values->Num() != Expected.Num()) return false;
    TArray<FString> Paths;
    for (const auto& V : *Values)
    {
        if (V->Type != EJson::String) return false;
        Paths.Add(V->AsString());
    }
    Paths.Sort(); return Paths == Expected;
}
struct FWROutput
{
    int32 Characters = 0;
    bool Emit(TSharedPtr<FJsonObject> J, const TCHAR* Kind)
    {
        J->SetStringField(TEXT("schema"), TEXT("ut4-weapon-report-v1"));
        J->SetStringField(TEXT("kind"), Kind);
        FString Text;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text))) return false;
        if (Text.Len() > 8 * 1024 * 1024 || Characters > 32 * 1024 * 1024 - Text.Len())
            return Fail(TEXT("WeaponReport output budget exceeded; incomplete report."));
        Characters += Text.Len();
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_REPORT %s"), *Text);
        return true;
    }
};
// Reads the existing imported rendering resource only. Aggregate CPU-skin eligibility
// is derived by the evidence reader: the pinned resource methods are not DLL-exported.
static bool WRSkin(USkeletalMesh* Mesh, TSharedPtr<FJsonObject> J, int32& TotalLODs, int32& TotalSections)
{
    const FSkeletalMeshResource* Resource = Mesh->GetResourceForRendering();
    if (!Resource || Resource->LODModels.Num() == 0 || Resource->LODModels.Num() > 16 - TotalLODs)
        return Fail(TEXT("WeaponReport missing skin resource or total LOD budget exceeded."));
    TotalLODs += Resource->LODModels.Num();
    int32 Sections = 0;
    for (int32 I = 0; I < Resource->LODModels.Num(); ++I)
    {
        const int32 Count = Resource->LODModels[I].Sections.Num();
        if (Count > 256 - TotalSections - Sections) return Fail(TEXT("WeaponReport total section budget exceeded."));
        Sections += Count;
    }
    TotalSections += Sections;
    TSharedPtr<FJsonObject> Skin = MakeShareable(new FJsonObject);
    Skin->SetStringField(TEXT("resource"), TEXT("GetResourceForRendering: existing ImportedResource"));
    Skin->SetStringField(TEXT("view"), TEXT("editor original-package view; not live HTML5 component evidence"));
    Skin->SetBoolField(TEXT("is_editor"), GIsEditor);
    Skin->SetBoolField(TEXT("runtime_component_observed"), false);
    Skin->SetNumberField(TEXT("es2_bone_limit"), GetFeatureLevelMaxNumberOfBones(ERHIFeatureLevel::ES2));
    Skin->SetNumberField(TEXT("sm5_bone_limit"), GetFeatureLevelMaxNumberOfBones(ERHIFeatureLevel::SM5));
    TArray<TSharedPtr<FJsonValue>> LODs;
    for (int32 I = 0; I < Resource->LODModels.Num(); ++I)
    {
        const FStaticLODModel& LOD = Resource->LODModels[I];
        TSharedPtr<FJsonObject> L = MakeShareable(new FJsonObject);
        L->SetNumberField(TEXT("lod"), I);
        L->SetNumberField(TEXT("num_vertices"), LOD.NumVertices);
        L->SetNumberField(TEXT("num_tex_coords"), LOD.NumTexCoords);
        L->SetNumberField(TEXT("vertex_buffer_vertices"), LOD.VertexBufferGPUSkin.GetNumVertices());
        L->SetNumberField(TEXT("vertex_buffer_tex_coords"), LOD.VertexBufferGPUSkin.GetNumTexCoords());
        L->SetBoolField(TEXT("vertex_buffer_extra_influences"), LOD.VertexBufferGPUSkin.HasExtraBoneInfluences());
        TArray<TSharedPtr<FJsonValue>> SectionRows;
        for (int32 K = 0; K < LOD.Sections.Num(); ++K)
        {
            const FSkelMeshSection& Section = LOD.Sections[K];
            TSharedPtr<FJsonObject> S = MakeShareable(new FJsonObject);
            S->SetNumberField(TEXT("section"), K);
            S->SetNumberField(TEXT("bone_map_count"), Section.BoneMap.Num());
            S->SetNumberField(TEXT("max_bone_influences"), Section.MaxBoneInfluences);
            S->SetBoolField(TEXT("extra_influences"), Section.HasExtraBoneInfluences());
            // Read the public count directly; GetNumVertices contains an editor consistency assertion.
            S->SetNumberField(TEXT("num_vertices"), Section.NumVertices);
            S->SetNumberField(TEXT("num_triangles"), Section.NumTriangles);
            S->SetBoolField(TEXT("disabled"), Section.bDisabled);
            SectionRows.Add(MRValue(S));
        }
        L->SetArrayField(TEXT("sections"), SectionRows); LODs.Add(MRValue(L));
    }
    Skin->SetArrayField(TEXT("lods"), LODs); J->SetObjectField(TEXT("skin"), Skin);
    return true;
}
static int32 WeaponPreflightReport(const FString& Params)
{
    FString SpecPath, Forbidden;
    if (!GIsEditor || !IsInGameThread() ||
        !FParse::Value(*Params, TEXT("WeaponReportSpec="), SpecPath) || SpecPath.IsEmpty() ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")))
    { Fail(TEXT("WeaponReport requires editor dependency gathering and WeaponReportSpec; no Manifest/Receipt.")); return 1; }
    TSharedPtr<FJsonObject> Spec; bool ReadOnly = false;
    if (!ReadJson(SpecPath, Spec) || Str(Spec, TEXT("schema")) != TEXT("ut4-weapon-report-v1") ||
        !Spec->TryGetBoolField(TEXT("read_only"), ReadOnly) || !ReadOnly ||
        !WRExactPaths(Spec, TEXT("targets"), WRScope()) || !WRExactPaths(Spec, TEXT("meshes"), WRMeshes()))
    { Fail(TEXT("WeaponReport scope must be exactly the original master, eighteen instances and four Enforcer/Malcolm meshes.")); return 1; }
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true);
    if (Registry.IsLoadingAssets()) return 1;
    FWROutput Output;
    const TArray<FString> Paths = WRScope();
    FMRDirtyObserver Observer(Paths, FParse::Param(*Params, TEXT("TraceDirty")));
    for (const FString& P : Paths)
    {
        TArray<FAssetData> Registered;
        Registry.GetAssetsByPackageName(FName(*P), Registered, true);
        if (Registered.Num() == 0) return 1;
        Observer.Phase = TEXT("weapon_load:") + P;
        UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, *ObjectPath(P));
        if (!M || (P == WRMaster() ? !Cast<UMaterial>(M) : !Cast<UMaterialInstanceConstant>(M))) return 1;
        const bool DirtyBefore = M->GetOutermost()->IsDirty();
        Observer.Phase = TEXT("weapon_describe:") + P;
        TSharedPtr<FJsonObject> J;
        if (!MRDescribe(M, Registry, J)) return 1;
        J->SetBoolField(TEXT("package_dirty_before_description"), DirtyBefore);
        // MRDescribe includes raw override bags, effective parameters, ordered parent chain,
        // static GUIDs and all recursively called function expressions/properties once for master.
        // ExportText preserves FunctionInputs/Outputs and SetMaterialAttributes arrays.
        if (P == WRMaster())
        {
            UMaterial* Master = Cast<UMaterial>(M);
            TSharedPtr<FJsonObject> Roots = J->GetObjectField(TEXT("roots"));
            Roots->SetObjectField(TEXT("Metallic"), MRPin(Master->GetExpressionInputForProperty(MP_Metallic)));
            Roots->SetObjectField(TEXT("Roughness"), MRPin(Master->GetExpressionInputForProperty(MP_Roughness)));
            Roots->SetObjectField(TEXT("Specular"), MRPin(Master->GetExpressionInputForProperty(MP_Specular)));
        }
        if (!Output.Emit(J, TEXT("material"))) return 1;
    }
    int32 TotalLODs = 0, TotalSections = 0;
    for (const FString& P : WRMeshes())
    {
        USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *ObjectPath(P));
        if (!Mesh || Mesh->Materials.Num() == 0 || Mesh->Materials.Num() > 16) return 1;
        TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
        TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
        if (!MRHashPackage(P, Hashes)) return 1;
        J->SetStringField(TEXT("mesh"), Mesh->GetPathName());
        if (!WRSkin(Mesh, J, TotalLODs, TotalSections)) return 1;
        J->SetBoolField(TEXT("package_dirty_after_load"), Mesh->GetOutermost()->IsDirty());
        TArray<TSharedPtr<FJsonValue>> Slots;
        for (int32 I = 0; I < Mesh->Materials.Num(); ++I)
        {
            UMaterialInterface* M = Mesh->Materials[I].MaterialInterface;
            if (!M || !MRHashPackage(M->GetOutermost()->GetName(), Hashes)) return 1;
            TSharedPtr<FJsonObject> Slot = MakeShareable(new FJsonObject);
            if (P.Contains(TEXT("/Weapons/Enforcer/"))) Slot = Describe(M);
            else
            {
                Slot->SetStringField(TEXT("material"), M->GetPathName());
                Slot->SetStringField(TEXT("class"), M->GetClass()->GetName());
            }
            Slot->SetNumberField(TEXT("slot"), I);
            Slot->SetStringField(TEXT("slot_name"), Mesh->Materials[I].MaterialSlotName.ToString());
            Slots.Add(MRValue(Slot));
        }
        J->SetArrayField(TEXT("slots"), Slots); J->SetObjectField(TEXT("package_sha1"), Hashes);
        if (!Output.Emit(J, TEXT("mesh"))) return 1;
    }
    TSharedPtr<FJsonObject> Done = MakeShareable(new FJsonObject);
    Done->SetNumberField(TEXT("materials"), Paths.Num()); Done->SetNumberField(TEXT("meshes"), WRMeshes().Num());
    Done->SetBoolField(TEXT("read_only"), true); Done->SetBoolField(TEXT("apply_ready"), false);
    return Output.Emit(Done, TEXT("complete")) ? 0 : 1;
}
