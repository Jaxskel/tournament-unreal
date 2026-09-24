// Original read-only UE4.15 report implementation. Included inside UT4Compat.
// No asset setters, graph updates, redirects, saves, or COW operations belong here.
static TSharedPtr<FJsonValue> MRValue(const TSharedPtr<FJsonObject>& J)
{
    return MakeShareable(new FJsonValueObject(J));
}
static void MREmit(const TSharedPtr<FJsonObject>& J)
{
    FString Text;
    FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_MATERIAL_REPORT %s"), *Text);
}
static TArray<FString> MRScope()
{
    TArray<FString> Paths;
    const FString U = TEXT("/Game/RestrictedAssets/Effects/Pickups/UDamage/Materials/");
    const FString O = TEXT("/Game/RestrictedAssets/Pickups/Powerups/Assets/");
    const FString L = TEXT("/Game/RestrictedAssets/Weapons/Weapon_Effects/Materials/Link/");
    for (const TCHAR* N : {TEXT("M_UDamageGlass"), TEXT("M_UDamageSkin"), TEXT("M_UDamageSkin_1P")}) Paths.Add(U + N);
    for (const TCHAR* N : {TEXT("M_UDamage_Overlay"), TEXT("M_UDamage_Overlay_1P")}) Paths.Add(O + N);
    for (const TCHAR* N : {TEXT("BeamMaterial"), TEXT("BeamMaterial_Inst2"), TEXT("BeamMaterial_Inst_Translucent"), TEXT("BeamMaterial_Slim_Inst"), TEXT("M_LinkProjectile_Core"), TEXT("M_LinkProjectile_Core_Inst")}) Paths.Add(L + N);
    Paths.Sort();
    return Paths;
}
// Optional observation only: one stack per selected package, no dirty-state changes.
struct FMRDirtyObserver
{
    TSet<FString> Selected, Recorded;
    FDelegateHandle Handle;
    FString Phase;
    FMRDirtyObserver(const TArray<FString>& Paths, bool Enabled) : Phase(TEXT("registry"))
    {
        if (!Enabled) return;
        for (const FString& P : Paths) Selected.Add(P);
        Handle = UPackage::PackageMarkedDirtyEvent.AddLambda([this](UPackage* Package, bool WasDirty)
        {
            const FString P = Package->GetName();
            if (!Selected.Contains(P) || Recorded.Contains(P)) return;
            Recorded.Add(P);
            ANSICHAR Stack[65536] = {};
            FPlatformStackWalk::StackWalkAndDump(Stack, sizeof(Stack), 2);
            TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
            J->SetStringField(TEXT("package"), P);
            J->SetStringField(TEXT("phase"), Phase);
            J->SetBoolField(TEXT("was_dirty"), WasDirty);
            J->SetStringField(TEXT("stack"), ANSI_TO_TCHAR(Stack));
            FString Text;
            FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_MATERIAL_DIRTY %s"), *Text);
        });
    }
    ~FMRDirtyObserver()
    {
        if (Handle.IsValid()) UPackage::PackageMarkedDirtyEvent.Remove(Handle);
    }
};
static TSharedPtr<FJsonObject> MRProperties(UObject* Object, bool AllProperties)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    for (TFieldIterator<UProperty> It(Object->GetClass()); It; ++It)
    {
        UProperty* P = *It;
        const FString N = P->GetName();
        const bool InstanceField = N == TEXT("ScalarParameterValues") || N == TEXT("VectorParameterValues") ||
            N == TEXT("TextureParameterValues") || N == TEXT("FontParameterValues") || N == TEXT("BasePropertyOverrides");
        if (!AllProperties && !InstanceField) continue;
        if (P->HasAnyPropertyFlags(CPF_Transient)) continue;
        // Native text includes inherited/default values, GUIDs, masks and function-call
        // input/output records. It is review evidence, not an importable edit script.
        for (int32 I = 0; I < P->ArrayDim; ++I)
        {
            FString Text;
            P->ExportText_InContainer(I, Text, Object, nullptr, Object, 0);
            J->SetStringField(P->ArrayDim == 1 ? N : FString::Printf(TEXT("%s[%d]"), *N, I), Text);
        }
    }
    return J;
}
static TSharedPtr<FJsonObject> MRPin(FExpressionInput* Input)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetStringField(TEXT("expression"), Input && Input->Expression ? Input->Expression->GetPathName() : TEXT(""));
    J->SetNumberField(TEXT("output_index"), Input ? Input->OutputIndex : 0);
    TArray<TSharedPtr<FJsonValue>> Mask;
    J->SetBoolField(TEXT("available"), Input != nullptr);
    const int32 Values[] = {Input ? Input->Mask : 0, Input ? Input->MaskR : 0, Input ? Input->MaskG : 0, Input ? Input->MaskB : 0, Input ? Input->MaskA : 0};
    for (int32 V : Values) Mask.Add(MakeShareable(new FJsonValueNumber(V)));
    J->SetArrayField(TEXT("mask"), Mask);
    return J;
}
static bool MRHashPackage(const FString& Package, TSharedPtr<FJsonObject> Hashes)
{
    if (Hashes->HasField(Package)) return true;
    FString Filename; TArray<uint8> Bytes;
    if (!FPackageName::DoesPackageExist(Package, nullptr, &Filename) || !FFileHelper::LoadFileToArray(Bytes, *Filename))
        return Fail(TEXT("MaterialReport cannot hash package: ") + Package);
    FSHAHash Hash;
    FSHA1::HashBuffer(Bytes.GetData(), Bytes.Num(), Hash.Hash);
    Hashes->SetStringField(Package, Hash.ToString());
    return true;
}
static bool MRGraph(const TArray<UMaterialExpression*>& Expressions, TArray<TSharedPtr<FJsonValue>>& Nodes,
    TSet<UMaterialFunction*>& Seen, TSharedPtr<FJsonObject> Hashes, int32 Depth = 0)
{
    if (Depth > 32 || Nodes.Num() + Expressions.Num() > 8192) return Fail(TEXT("MaterialReport graph budget exceeded; no truncated success."));
    for (UMaterialExpression* E : Expressions)
    {
        if (!E) return Fail(TEXT("MaterialReport null expression."));
        TSharedPtr<FJsonObject> N = MakeShareable(new FJsonObject);
        N->SetStringField(TEXT("path"), E->GetPathName());
        N->SetStringField(TEXT("name"), E->GetName());
        N->SetStringField(TEXT("owner"), E->GetOuter()->GetPathName());
        N->SetStringField(TEXT("class"), E->GetClass()->GetName());
        N->SetObjectField(TEXT("properties"), MRProperties(E, true));
        TArray<TSharedPtr<FJsonValue>> Inputs;
        const auto Pins = E->GetInputs();
        const auto* InputFunction = Cast<UMaterialExpressionMaterialFunctionCall>(E);
        for (int32 I = 0; I < Pins.Num(); ++I)
        {
            auto P = MRPin(Pins[I]);
            // Function-call GetInputs enumerates FunctionInputs in the same order.
            // GetInputName adds transient editor type suffixes; report the serialized name.
            P->SetNumberField(TEXT("index"), I); P->SetStringField(TEXT("name"), InputFunction ? InputFunction->FunctionInputs[I].Input.InputName : E->GetInputName(I));
            Inputs.Add(MRValue(P));
        }
        N->SetArrayField(TEXT("inputs"), Inputs);
        Nodes.Add(MRValue(N));
        if (auto* Call = Cast<UMaterialExpressionMaterialFunctionCall>(E))
        {
            UMaterialFunction* F = Call->MaterialFunction;
            N->SetStringField(TEXT("function"), F ? F->GetPathName() : TEXT(""));
            if (!F) return Fail(TEXT("MaterialReport null material function."));
            if (!Seen.Contains(F))
            {
                Seen.Add(F);
                if (!MRHashPackage(F->GetOutermost()->GetName(), Hashes) || !MRGraph(F->FunctionExpressions, Nodes, Seen, Hashes, Depth + 1)) return false;
            }
        }
    }
    return true;
}
static TSharedPtr<FJsonObject> MRStatic(const FStaticParameterSet& Set)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    TArray<TSharedPtr<FJsonValue>> Switches, Masks, Terrain;
    auto Item = [](FName Name, bool Override, const FGuid& Guid) {
        TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject);
        P->SetStringField(TEXT("name"), Name.ToString()); P->SetBoolField(TEXT("override"), Override);
        P->SetStringField(TEXT("guid"), Guid.ToString()); return P;
    };
    for (const auto& V : Set.StaticSwitchParameters)
    { auto P = Item(V.ParameterName, V.bOverride, V.ExpressionGUID); P->SetBoolField(TEXT("value"), V.Value); Switches.Add(MRValue(P)); }
    for (const auto& V : Set.StaticComponentMaskParameters)
    {
        auto P = Item(V.ParameterName, V.bOverride, V.ExpressionGUID);
        P->SetBoolField(TEXT("r"), V.R); P->SetBoolField(TEXT("g"), V.G); P->SetBoolField(TEXT("b"), V.B); P->SetBoolField(TEXT("a"), V.A);
        Masks.Add(MRValue(P));
    }
    for (const auto& V : Set.TerrainLayerWeightParameters)
    { auto P = Item(V.ParameterName, V.bOverride, V.ExpressionGUID); P->SetNumberField(TEXT("weightmap_index"), V.WeightmapIndex); Terrain.Add(MRValue(P)); }
    J->SetArrayField(TEXT("switches"), Switches); J->SetArrayField(TEXT("masks"), Masks); J->SetArrayField(TEXT("terrain"), Terrain);
    return J;
}
static bool MRDescribe(UMaterialInterface* M, IAssetRegistry& Registry, TSharedPtr<FJsonObject>& J)
{
    J = Describe(M);
    J->SetStringField(TEXT("kind"), TEXT("material"));
    J->SetStringField(TEXT("schema"), TEXT("ut4-material-report-v1"));
    J->SetNumberField(TEXT("blend"), M->GetBlendMode());
    J->SetNumberField(TEXT("shading"), M->GetShadingModel());
    J->SetBoolField(TEXT("two_sided"), M->IsTwoSided());
    J->SetNumberField(TEXT("opacity_mask_clip"), M->GetOpacityMaskClipValue());
    J->SetObjectField(TEXT("properties"), MRProperties(M, true));
    TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
    if (!MRHashPackage(M->GetOutermost()->GetName(), Hashes)) return false;
    TArray<TSharedPtr<FJsonValue>> Chain;
    TSet<UMaterialInterface*> SeenParents;
    for (UMaterialInterface* P = M; P; )
    {
        if (SeenParents.Contains(P) || SeenParents.Num() >= 32) return Fail(TEXT("MaterialReport cyclic/excessive parent chain."));
        SeenParents.Add(P);
        Chain.Add(MakeShareable(new FJsonValueString(P->GetPathName())));
        if (!MRHashPackage(P->GetOutermost()->GetName(), Hashes)) return false;
        auto* MI = Cast<UMaterialInstance>(P); P = MI ? MI->Parent : nullptr;
    }
    J->SetArrayField(TEXT("parent_chain"), Chain);
    if (auto* MI = Cast<UMaterialInstance>(M))
    {
        J->SetObjectField(TEXT("static_overrides"), MRStatic(MI->GetStaticParameters()));
        FStaticParameterSet Effective; MI->GetStaticParameterValues(Effective);
        J->SetObjectField(TEXT("static_effective"), MRStatic(Effective));
    }
    UMaterial* Base = M->GetMaterial();
    if (!Base) return Fail(TEXT("MaterialReport missing base material."));
    TArray<TSharedPtr<FJsonValue>> Scalars, Vectors;
    TArray<FName> Names; TArray<FGuid> IDs;
    Base->GetAllScalarParameterNames(Names, IDs);
    for (FName N : Names)
    {
        float V = 0; if (!M->GetScalarParameterValue(N, V)) return Fail(TEXT("MaterialReport unresolved scalar."));
        TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject); P->SetStringField(TEXT("name"), N.ToString()); P->SetNumberField(TEXT("value"), V); Scalars.Add(MRValue(P));
    }
    Names.Empty(); IDs.Empty(); Base->GetAllVectorParameterNames(Names, IDs);
    for (FName N : Names)
    {
        FLinearColor V; if (!M->GetVectorParameterValue(N, V)) return Fail(TEXT("MaterialReport unresolved vector."));
        TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject); P->SetStringField(TEXT("name"), N.ToString());
        TArray<TSharedPtr<FJsonValue>> C;
        for (float Value : {V.R, V.G, V.B, V.A}) C.Add(MakeShareable(new FJsonValueNumber(Value)));
        P->SetArrayField(TEXT("value"), C); Vectors.Add(MRValue(P));
    }
    J->SetArrayField(TEXT("scalar_parameters"), Scalars); J->SetArrayField(TEXT("vector_parameters"), Vectors);
    TSharedPtr<FJsonObject> Roots = MakeShareable(new FJsonObject);
    TArray<TSharedPtr<FJsonValue>> Nodes;
    if (M == Base)
    {
        const EMaterialProperty Props[] = {MP_BaseColor, MP_EmissiveColor, MP_Opacity, MP_OpacityMask, MP_Normal, MP_WorldPositionOffset, MP_WorldDisplacement, MP_Refraction, MP_MaterialAttributes};
        const TCHAR* Labels[] = {TEXT("BaseColor"), TEXT("EmissiveColor"), TEXT("Opacity"), TEXT("OpacityMask"), TEXT("Normal"), TEXT("WorldPositionOffset"), TEXT("WorldDisplacement"), TEXT("Refraction"), TEXT("MaterialAttributes")};
        for (int32 I = 0; I < ARRAY_COUNT(Props); ++I) Roots->SetObjectField(Labels[I], MRPin(Base->GetExpressionInputForProperty(Props[I])));
        TSet<UMaterialFunction*> Seen;
        if (!MRGraph(Base->Expressions, Nodes, Seen, Hashes)) return false;
    }
    J->SetObjectField(TEXT("roots"), Roots); J->SetArrayField(TEXT("nodes"), Nodes);
    J->SetObjectField(TEXT("package_sha1"), Hashes);
    // Package metadata only: never recursively load referencers or expand the save scope.
    TArray<FName> Queue; TSet<FName> Visited;
    Queue.Add(FName(*M->GetOutermost()->GetName())); Visited.Add(Queue[0]);
    TArray<TSharedPtr<FJsonValue>> Direct, Transitive;
    for (int32 I = 0; I < Queue.Num(); ++I)
    {
        TArray<FName> Refs;
        Registry.GetReferencers(Queue[I], Refs, EAssetRegistryDependencyType::Packages);
        Refs.Sort([](const FName& A, const FName& B) { return A.ToString() < B.ToString(); });
        for (FName R : Refs)
        {
            if (I == 0) Direct.Add(MakeShareable(new FJsonValueString(R.ToString())));
            if (Visited.Contains(R)) continue;
            if (Visited.Num() >= 16384) return Fail(TEXT("MaterialReport referencer budget exceeded; no truncated success."));
            Visited.Add(R); Queue.Add(R); Transitive.Add(MakeShareable(new FJsonValueString(R.ToString())));
        }
    }
    J->SetArrayField(TEXT("direct_referencers"), Direct); J->SetArrayField(TEXT("transitive_referencers"), Transitive);
    J->SetBoolField(TEXT("registry_scan_complete"), true);
    J->SetBoolField(TEXT("package_dirty_after_load"), M->GetOutermost()->IsDirty());
    return true;
}
static int32 MaterialPreflightReport(const FString& Params)
{
    FString SpecPath, Forbidden;
    if (!FParse::Value(*Params, TEXT("ReportSpec="), SpecPath) || SpecPath.IsEmpty() ||
        FParse::Value(*Params, TEXT("Receipt="), Forbidden) || FParse::Value(*Params, TEXT("Manifest="), Forbidden))
    { Fail(TEXT("MaterialReport requires -ReportSpec=<read-only spec>; no Manifest/Receipt.")); return 1; }
    TSharedPtr<FJsonObject> Spec;
    if (!ReadJson(SpecPath, Spec) || Str(Spec, TEXT("schema")) != TEXT("ut4-material-preflight-first5-v1"))
    { Fail(TEXT("Invalid material report spec.")); return 1; }
    bool ReadOnly = false;
    const TArray<TSharedPtr<FJsonValue>>* Targets = nullptr;
    if (!Spec->TryGetBoolField(TEXT("read_only"), ReadOnly) || !ReadOnly || !Spec->TryGetArrayField(TEXT("targets"), Targets)) return 1;
    TArray<FString> Paths;
    for (const auto& V : *Targets)
    {
        if (V->Type != EJson::Object) return 1;
        Paths.Add(Str(V->AsObject(), TEXT("package")));
    }
    Paths.Sort();
    if (Paths != MRScope()) { Fail(TEXT("MaterialReport scope must be exactly the five parents and six variants.")); return 1; }
    if (!GIsEditor || FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")))
    { Fail(TEXT("MaterialReport requires editor dependency gathering.")); return 1; }
    FMRDirtyObserver DirtyObserver(Paths, FParse::Param(*Params, TEXT("TraceDirty")));
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true);
    if (Registry.IsLoadingAssets()) { Fail(TEXT("MaterialReport registry scan incomplete.")); return 1; }
    for (const FString& P : Paths)
    {
        TArray<FAssetData> Registered;
        Registry.GetAssetsByPackageName(FName(*P), Registered, true);
        if (Registered.Num() == 0) { Fail(TEXT("MaterialReport package absent from on-disk registry: ") + P); return 1; }
        DirtyObserver.Phase = TEXT("load:") + P;
        auto* M = LoadObject<UMaterialInterface>(nullptr, *ObjectPath(P));
        const bool DirtyBeforeDescription = M && M->GetOutermost()->IsDirty();
        DirtyObserver.Phase = TEXT("describe:") + P;
        TSharedPtr<FJsonObject> J;
        if (!M || !MRDescribe(M, Registry, J)) { Fail(TEXT("MaterialReport failed: ") + P); return 1; }
        J->SetBoolField(TEXT("package_dirty_before_description"), DirtyBeforeDescription);
        MREmit(J);
    }
    TSharedPtr<FJsonObject> Done = MakeShareable(new FJsonObject);
    Done->SetStringField(TEXT("schema"), TEXT("ut4-material-report-v1"));
    Done->SetStringField(TEXT("kind"), TEXT("complete")); Done->SetNumberField(TEXT("count"), Paths.Num());
    Done->SetBoolField(TEXT("read_only"), true); MREmit(Done);
    return 0;
}
