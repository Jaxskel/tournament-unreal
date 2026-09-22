// Original read-only report. Include after MaterialPreflightReport.h inside UT4Compat.
// Fixed asset scope; no saves, redirects, actor creation, world loads or graph setters.
static FString BSRNick() { return TEXT("/Game/RestrictedAssets/Effects/Nick/"); }
static FString BSRCharacter() { return TEXT("/Game/RestrictedAssets/Blueprints/BaseUTCharacter"); }
static bool BSRSpec(const TSharedPtr<FJsonObject>& Spec, bool& LoadedComponents)
{
    bool ReadOnly = false;
    const TArray<TSharedPtr<FJsonValue>>* Materials = nullptr;
    if (Str(Spec, TEXT("schema")) != TEXT("ut4-blob-shadow-report-v1") ||
        !Spec->TryGetBoolField(TEXT("read_only"), ReadOnly) || !ReadOnly ||
        !Spec->TryGetBoolField(TEXT("include_loaded_world_components"), LoadedComponents) ||
        Str(Spec, TEXT("mesh")) != BSRNick() + TEXT("miniCylinder") ||
        Str(Spec, TEXT("character")) != BSRCharacter() ||
        !Spec->TryGetArrayField(TEXT("materials"), Materials) || Materials->Num() != 2) return false;
    TArray<FString> Paths;
    for (const auto& V : *Materials)
    {
        if (V->Type != EJson::String) return false;
        Paths.Add(V->AsString());
    }
    Paths.Sort();
    return Paths[0] == BSRNick() + TEXT("M_Robust_BlobShadow") &&
        Paths[1] == BSRNick() + TEXT("M_Robust_BlobShadowInverse");
}
struct FBSROutput
{
    int32 Characters = 0;
    bool Emit(TSharedPtr<FJsonObject> J, const TCHAR* Kind)
    {
        J->SetStringField(TEXT("blob_schema"), TEXT("ut4-blob-shadow-report-v1"));
        J->SetStringField(TEXT("blob_kind"), Kind);
        FString Text;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text))) return false;
        if (Text.Len() > 8 * 1024 * 1024 || Characters > 32 * 1024 * 1024 - Text.Len())
            return Fail(TEXT("BlobShadowReport output budget exceeded; incomplete report."));
        Characters += Text.Len();
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_BLOB_REPORT %s"), *Text);
        return true;
    }
};
static bool BSRParameters(UMaterialInterface* M, TSharedPtr<FJsonObject> J)
{
    UMaterial* Base = M ? M->GetMaterial() : nullptr;
    if (!Base) return false;
    if (auto* MI = Cast<UMaterialInstance>(M))
        J->SetStringField(TEXT("parent"), MI->Parent ? MI->Parent->GetPathName() : TEXT(""));
    TArray<FName> Names; TArray<FGuid> IDs;
    TArray<TSharedPtr<FJsonValue>> Scalars, Vectors;
    Base->GetAllScalarParameterNames(Names, IDs);
    if (Names.Num() > 128) return false;
    for (FName N : Names)
    {
        float V = 0; if (!M->GetScalarParameterValue(N, V)) return false;
        TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject);
        P->SetStringField(TEXT("name"), N.ToString()); P->SetNumberField(TEXT("value"), V);
        Scalars.Add(MRValue(P));
    }
    Names.Empty(); IDs.Empty(); Base->GetAllVectorParameterNames(Names, IDs);
    if (Names.Num() > 128) return false;
    for (FName N : Names)
    {
        FLinearColor V; if (!M->GetVectorParameterValue(N, V)) return false;
        TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject);
        P->SetStringField(TEXT("name"), N.ToString());
        TArray<TSharedPtr<FJsonValue>> Values;
        for (float C : {V.R, V.G, V.B, V.A}) Values.Add(MakeShareable(new FJsonValueNumber(C)));
        P->SetArrayField(TEXT("value"), Values); Vectors.Add(MRValue(P));
    }
    J->SetArrayField(TEXT("scalar_parameters"), Scalars); J->SetArrayField(TEXT("vector_parameters"), Vectors);
    return true;
}
static bool BSRComponent(UStaticMeshComponent* C, bool Template, FBSROutput& Output)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetStringField(TEXT("component"), C->GetPathName());
    J->SetBoolField(TEXT("template"), Template);
    J->SetStringField(TEXT("mesh"), C->GetStaticMesh() ? C->GetStaticMesh()->GetPathName() : TEXT(""));
    J->SetStringField(TEXT("owner"), C->GetOwner() ? C->GetOwner()->GetPathName() : TEXT(""));
    J->SetStringField(TEXT("attach_parent"), C->GetAttachParent() ? C->GetAttachParent()->GetPathName() : TEXT(""));
    J->SetStringField(TEXT("attach_socket"), C->GetAttachSocketName().ToString());
    J->SetStringField(TEXT("component_to_world"), C->GetComponentTransform().ToString());
    // Native properties retain relative transforms, visibility, owner-only flags,
    // collision profile and material overrides without guessing inherited defaults.
    J->SetObjectField(TEXT("properties"), MRProperties(C, true));
    UWorld* World = C->GetWorld();
    J->SetStringField(TEXT("world"), World ? World->GetPathName() : TEXT(""));
    J->SetBoolField(TEXT("world_begun_play"), World && World->HasBegunPlay());
    TArray<TSharedPtr<FJsonValue>> Materials;
    if (C->GetNumMaterials() > 16) return Fail(TEXT("BlobShadowReport component material budget."));
    for (int32 I = 0; I < C->GetNumMaterials(); ++I)
    {
        UMaterialInterface* M = C->GetMaterial(I);
        auto P = Describe(M); P->SetNumberField(TEXT("slot"), I);
        if (M && !BSRParameters(M, P)) return Fail(TEXT("BlobShadowReport unresolved component parameters."));
        Materials.Add(MRValue(P));
    }
    J->SetArrayField(TEXT("materials"), Materials);
    return Output.Emit(J, Template ? TEXT("component_template") : TEXT("loaded_component"));
}
static int32 BlobShadowPreflightReport(const FString& Params)
{
    FString Path, Forbidden;
    if (!GIsEditor || !IsInGameThread() ||
        !FParse::Value(*Params, TEXT("BlobReportSpec="), Path) || Path.IsEmpty() ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")))
    { Fail(TEXT("BlobShadowReport requires editor, dependency gathering and BlobReportSpec; no Manifest/Receipt.")); return 1; }
    TSharedPtr<FJsonObject> Spec; bool LoadedComponents = false;
    if (!ReadJson(Path, Spec) || !BSRSpec(Spec, LoadedComponents))
    { Fail(TEXT("BlobShadowReport fixed read-only scope rejected.")); return 1; }
    FBSROutput Output;
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true);
    if (Registry.IsLoadingAssets()) return 1;
    TArray<FString> Paths;
    Paths.Add(BSRNick() + TEXT("M_Robust_BlobShadow")); Paths.Add(BSRNick() + TEXT("M_Robust_BlobShadowInverse"));
    FMRDirtyObserver Observer(Paths, FParse::Param(*Params, TEXT("TraceDirty")));
    for (const FString& P : Paths)
    {
        Observer.Phase = TEXT("blob_load:") + P;
        auto* M = LoadObject<UMaterialInterface>(nullptr, *ObjectPath(P));
        if (!M || (P == Paths[0] ? !Cast<UMaterial>(M) : !Cast<UMaterialInstanceConstant>(M))) return 1;
        const bool Dirty = M && M->GetOutermost()->IsDirty();
        Observer.Phase = TEXT("blob_describe:") + P;
        TSharedPtr<FJsonObject> J;
        if (!M || !MRDescribe(M, Registry, J)) return 1;
        J->SetBoolField(TEXT("package_dirty_before_description"), Dirty);
        if (!Output.Emit(J, TEXT("material"))) return 1;
    }
    auto* Mesh = LoadObject<UStaticMesh>(nullptr, *ObjectPath(BSRNick() + TEXT("miniCylinder")));
    auto* Class = LoadObject<UClass>(nullptr, *(BSRCharacter() + TEXT(".BaseUTCharacter_C")));
    UObject* CDO = Class ? Class->GetDefaultObject() : nullptr;
    if (!Mesh || !CDO) { Fail(TEXT("BlobShadowReport mesh/generated CDO unavailable.")); return 1; }
    TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
    if (!MRHashPackage(BSRNick() + TEXT("miniCylinder"), Hashes) || !MRHashPackage(BSRCharacter(), Hashes)) return 1;
    TSharedPtr<FJsonObject> MeshRecord = MakeShareable(new FJsonObject);
    MeshRecord->SetStringField(TEXT("mesh"), Mesh->GetPathName());
    MeshRecord->SetObjectField(TEXT("package_sha1"), Hashes);
    MeshRecord->SetObjectField(TEXT("properties"), MRProperties(Mesh, true));
    if (!Output.Emit(MeshRecord, TEXT("mesh"))) return 1;
    TSharedPtr<FJsonObject> Defaults = MakeShareable(new FJsonObject);
    Defaults->SetStringField(TEXT("cdo"), CDO->GetPathName());
    TSharedPtr<FJsonObject> Properties = MakeShareable(new FJsonObject);
    // Report exact inherited shadow settings/references, not the entire character.
    for (TFieldIterator<UProperty> It(CDO->GetClass()); It; ++It)
    {
        UProperty* P = *It; const FString N = P->GetName();
        if (!N.Contains(TEXT("Shadow")) && !N.Contains(TEXT("Foot")) && !N.Contains(TEXT("Cylinder"))) continue;
        for (int32 I = 0; I < P->ArrayDim; ++I)
        {
            FString Text; P->ExportText_InContainer(I, Text, CDO, nullptr, CDO, 0);
            Properties->SetStringField(FString::Printf(TEXT("%s[%d]"), *N, I), Text);
        }
    }
    Defaults->SetObjectField(TEXT("properties"), Properties);
    Defaults->SetBoolField(TEXT("package_dirty_after_load"), CDO->GetOutermost()->IsDirty());
    if (!Output.Emit(Defaults, TEXT("character_defaults"))) return 1;
    int32 Templates = 0, Live = 0;
    for (TObjectIterator<UStaticMeshComponent> It; It; ++It)
    {
        UStaticMeshComponent* C = *It;
        const bool Template = C->GetOutermost() == Class->GetOutermost();
        const bool InWorld = LoadedComponents && !C->IsTemplate() && C->GetWorld() && C->GetStaticMesh() == Mesh;
        if (!Template && !InWorld) continue;
        if (Templates + Live >= 128) { Fail(TEXT("BlobShadowReport component budget exceeded.")); return 1; }
        if (!BSRComponent(C, Template, Output)) return 1;
        if (Template) ++Templates; else ++Live;
    }
    TSharedPtr<FJsonObject> Done = MakeShareable(new FJsonObject);
    Done->SetNumberField(TEXT("materials"), 2); Done->SetNumberField(TEXT("templates"), Templates);
    Done->SetNumberField(TEXT("loaded_components"), Live); Done->SetBoolField(TEXT("read_only"), true);
    Done->SetBoolField(TEXT("apply_ready"), false);
    Done->SetBoolField(TEXT("loaded_world_scan_requested"), LoadedComponents);
    Done->SetStringField(TEXT("scope"), TEXT("CDO/templates plus optional already-loaded components; no world load or actor spawn. Zero live components is not runtime evidence."));
    return Output.Emit(Done, TEXT("complete")) ? 0 : 1;
}
