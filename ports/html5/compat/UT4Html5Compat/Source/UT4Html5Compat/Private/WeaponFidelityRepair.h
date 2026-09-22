// Original bounded repair implementation; include inside UT4Compat after WeaponPreflightReport.h.
// Required top-level includes: MaterialExpressionConstant, FeatureLevelSwitch, SetMaterialAttributes.
// This separate operation requires pristine MIC copies and a 23-destination physical COW receipt.
static const TCHAR* WFRRecipeHash = TEXT("11115c4f91274c90437aac5a1f783a16f3b14279");
// WFR_DIAGNOSTICS_BEGIN
// Diagnostic-only: no loading, hashing, saving, or predicate re-evaluation.
// A short one-line context identifies the package/field without dumping baseline data.
static FString WFRContext(FString Context)
{
    Context = Context.Left(320);
    Context.ReplaceInline(TEXT("\r"), TEXT(" "));
    Context.ReplaceInline(TEXT("\n"), TEXT(" "));
    Context.ReplaceInline(TEXT("\t"), TEXT(" "));
    return Context;
}
static bool WFRGate(bool Passed, const TCHAR* Gate, const FString& Context = FString())
{
    if (!Passed) UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_REPAIR_DIAG gate=%s context=%s"), Gate, *WFRContext(Context));
    return Passed;
}
static int32 WFRStop(const TCHAR* Gate, const FString& Context = FString())
{
    WFRGate(false, Gate, Context);
    return 1;
}
static void WFRStage(const TCHAR* Stage)
{
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_REPAIR_DIAG stage=%s"), Stage);
}
// WFR_DIAGNOSTICS_END
struct FWeaponRepair
{
    TMap<FString, FString> Clones, Canonical;
    TMap<FString, UObject*> Objects;
    TMap<FString, TSharedPtr<FJsonObject>> Baseline;
    TArray<FString> Instances, Direct;
    TSharedPtr<FJsonObject> Pins;
    FSavePolicy Policy;
    bool Verify = false;

    FString Normal(FString Text) const
    {
        TArray<FString> Keys; Canonical.GetKeys(Keys);
        Keys.Sort([](const FString& A, const FString& B) { return A.Len() > B.Len(); });
        for (const FString& K : Keys) Text.ReplaceInline(*K, *Canonical.FindChecked(K), ESearchCase::CaseSensitive);
        return Text;
    }
    bool Same(const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B, int32 Depth = 0) const
    {
        if (!A.IsValid() || !B.IsValid() || A->Type != B->Type || Depth > 64) return false;
        if (A->Type == EJson::String) return Normal(A->AsString()) == Normal(B->AsString());
        if (A->Type == EJson::Number) return A->AsNumber() == B->AsNumber();
        if (A->Type == EJson::Boolean) return A->AsBool() == B->AsBool();
        if (A->Type == EJson::Null) return true;
        if (A->Type == EJson::Array)
        {
            const auto& X = A->AsArray(); const auto& Y = B->AsArray();
            if (X.Num() != Y.Num()) return false;
            for (int32 I = 0; I < X.Num(); ++I) if (!Same(X[I], Y[I], Depth + 1)) return false;
            return true;
        }
        if (A->Type == EJson::Object)
        {
            const auto& X = A->AsObject()->Values; const auto& Y = B->AsObject()->Values;
            if (X.Num() != Y.Num()) return false;
            for (const auto& KV : X)
            { const auto* V = Y.Find(KV.Key); if (!V || !Same(KV.Value, *V, Depth + 1)) return false; }
            return true;
        }
        return false;
    }
    bool Field(const TSharedPtr<FJsonObject>& A, const TSharedPtr<FJsonObject>& B, const TCHAR* Key) const
    {
        const auto* X = A->Values.Find(Key); const auto* Y = B->Values.Find(Key);
        return WFRGate(X && Y && Same(*X, *Y), TEXT("field-mismatch"), Key);
    }
    bool Properties(UObject* A, UObject* B, const TSet<FString>& Skip) const
    {
        auto X = MRProperties(A, true); auto Y = MRProperties(B, true);
        for (const FString& K : Skip) { X->RemoveField(K); Y->RemoveField(K); }
        return Same(MRValue(X), MRValue(Y));
    }
    bool DiskPins() const
    {
        TSharedPtr<FJsonObject> Actual = MakeShareable(new FJsonObject);
        for (const auto& KV : Pins->Values)
        {
            if (Verify && Direct.Contains(KV.Key)) continue;
            if (!MRHashPackage(KV.Key, Actual) || !Str(Actual, *KV.Key).Equals(KV.Value->AsString(), ESearchCase::IgnoreCase))
                return Fail(TEXT("WeaponRepair original bytes differ: ") + KV.Key);
        }
        return true;
    }
    TArray<UMaterialExpression*>* Expressions(UObject* O) const
    {
        if (auto* M = Cast<UMaterial>(O)) return &M->Expressions;
        if (auto* F = Cast<UMaterialFunction>(O)) return &F->FunctionExpressions;
        return nullptr;
    }
    UMaterialExpression* Node(UObject* O, const TCHAR* Name, const TCHAR* Class) const
    {
        UMaterialExpression* Found = nullptr;
        auto* Es = Expressions(O); if (!Es) return nullptr;
        for (auto* E : *Es) if (E && E->GetName() == Name)
        { if (Found || E->GetClass()->GetName() != Class || E->GetOuter() != O) return nullptr; Found = E; }
        return Found;
    }
    template<typename T> T* Add(UObject* O, const TCHAR* Name)
    {
        if (FindObject<UObject>(O, Name)) return nullptr;
        T* E = NewObject<T>(O, FName(Name));
        E->Material = Cast<UMaterial>(O); E->Function = Cast<UMaterialFunction>(O);
        Expressions(O)->Add(E); return E;
    }
    void AOAliases(const FString& Source, const TCHAR* OldName)
    {
        const FString NewPath = ObjectPath(Clones.FindChecked(Source)) + TEXT(":TournamentES2AOMask");
        const FString OldPath = ObjectPath(Source) + TEXT(":") + OldName;
        Canonical.Add(TEXT("MaterialExpressionFeatureLevelSwitch'") + NewPath + TEXT("'"),
            TEXT("MaterialExpressionPrecomputedAOMask'") + OldPath + TEXT("'"));
        Canonical.Add(NewPath, OldPath);
    }
    bool Pin(const FExpressionInput& P, UMaterialExpression* E, int32 Output = 0) const
    {
        return P.Expression == E && P.OutputIndex == Output && P.Mask == 0 && P.MaskR == 0 &&
            P.MaskG == 0 && P.MaskB == 0 && P.MaskA == 0;
    }
    bool AO(UObject* O, const TCHAR* OldName)
    {
        auto* Old = Node(O, OldName, TEXT("MaterialExpressionPrecomputedAOMask"));
        if (!Old) return false;
        auto* Switch = Cast<UMaterialExpressionFeatureLevelSwitch>(Node(O, TEXT("TournamentES2AOMask"), TEXT("MaterialExpressionFeatureLevelSwitch")));
        auto* Zero = Cast<UMaterialExpressionConstant>(Node(O, TEXT("TournamentES2AOZero"), TEXT("MaterialExpressionConstant")));
        if (!Verify)
        {
            Switch = Add<UMaterialExpressionFeatureLevelSwitch>(O, TEXT("TournamentES2AOMask"));
            Zero = Add<UMaterialExpressionConstant>(O, TEXT("TournamentES2AOZero"));
            if (!Switch || !Zero) return false;
            Zero->R = 0; Switch->Default.Expression = Old;
            Switch->Inputs[ERHIFeatureLevel::ES2].Expression = Zero;
            int32 Replaced = 0;
            for (auto* E : *Expressions(O)) if (E != Switch && E != Zero)
                for (auto* Input : E->GetInputs()) if (Input && Input->Expression == Old)
                { if (Input->OutputIndex != 0) return false; Input->Expression = Switch; ++Replaced; }
            if (Replaced != 1) return false;
        }
        if (!Switch || !Zero || Zero->R != 0 || !Pin(Switch->Default, Old) || !Pin(Switch->Inputs[ERHIFeatureLevel::ES2], Zero)) return false;
        for (int32 I = 1; I < ERHIFeatureLevel::Num; ++I) if (Switch->Inputs[I].Expression) return false;
        return true;
    }
    bool WPO(UMaterial* M)
    {
        auto* Old = Node(M, TEXT("MaterialExpressionSetMaterialAttributes_0"), TEXT("MaterialExpressionSetMaterialAttributes"));
        auto* Call = Cast<UMaterialExpressionMaterialFunctionCall>(Node(M, TEXT("MaterialExpressionMaterialFunctionCall_1"), TEXT("MaterialExpressionMaterialFunctionCall")));
        auto* Root = M->GetExpressionInputForProperty(MP_MaterialAttributes);
        if (!Old || !Call || !Root || !M->bUseMaterialAttributes || Call->FunctionOutputs.Num() != 2 ||
            Call->FunctionOutputs[1].Output.OutputName != TEXT("WPO Only")) return false;
        auto* Set = Cast<UMaterialExpressionSetMaterialAttributes>(Node(M, TEXT("TournamentES2WPO"), TEXT("MaterialExpressionSetMaterialAttributes")));
        auto* Switch = Cast<UMaterialExpressionFeatureLevelSwitch>(Node(M, TEXT("TournamentES2Attributes"), TEXT("MaterialExpressionFeatureLevelSwitch")));
        if (!Verify)
        {
            if (Root->Expression != Old || Root->OutputIndex != 0) return false;
            Set = Add<UMaterialExpressionSetMaterialAttributes>(M, TEXT("TournamentES2WPO"));
            Switch = Add<UMaterialExpressionFeatureLevelSwitch>(M, TEXT("TournamentES2Attributes"));
            if (!Set || !Switch) return false;
            Set->Inputs.SetNum(2); Set->Inputs[0] = *Root;
            Set->Inputs[1].Expression = Call; Set->Inputs[1].OutputIndex = 1;
            Set->AttributeSetTypes.Add(FMaterialAttributeDefinitionMap::GetID(MP_WorldPositionOffset));
            Switch->Default = *Root; Switch->Inputs[ERHIFeatureLevel::ES2].Expression = Set;
            Root->Expression = Switch; Root->OutputIndex = 0;
        }
        if (!Set || !Switch || !Pin(*Root, Switch) || !Pin(Switch->Default, Old) ||
            !Pin(Switch->Inputs[ERHIFeatureLevel::ES2], Set) || Set->Inputs.Num() != 2 ||
            !Pin(Set->Inputs[0], Old) || !Pin(Set->Inputs[1], Call, 1) ||
            Set->AttributeSetTypes.Num() != 1 || Set->AttributeSetTypes[0] != FMaterialAttributeDefinitionMap::GetID(MP_WorldPositionOffset)) return false;
        for (int32 I = 1; I < ERHIFeatureLevel::Num; ++I) if (Switch->Inputs[I].Expression) return false;
        return true;
    }
    bool Graph(UMaterial* Master, const TSharedPtr<FJsonObject>& Expected)
    {
        TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
        TSet<UMaterialFunction*> Seen; TArray<TSharedPtr<FJsonValue>> Nodes;
        // New clone packages have no on-disk hash before saving. Seed only their
        // identities for this structural walk; DiskPins checks original provenance.
        for (const auto& KV : Clones) Hashes->SetStringField(KV.Value, TEXT("unsaved-structural-inspection"));
        if (!MRGraph(Master->Expressions, Nodes, Seen, Hashes)) return false;
        TMap<FString, TSharedPtr<FJsonObject>> ByPath;
        int32 Added = 0;
        for (const auto& V : Nodes)
        {
            auto N = V->AsObject();
            if (Str(N, TEXT("name")).StartsWith(TEXT("TournamentES2"))) { ++Added; continue; }
            const FString Path = Normal(Str(N, TEXT("path")));
            if (ByPath.Contains(Path)) return false;
            ByPath.Add(Path, N);
        }
        const auto& OldNodes = Expected->GetArrayField(TEXT("nodes"));
        if (Added != 6 || ByPath.Num() != OldNodes.Num()) return false;
        for (const auto& V : OldNodes)
        {
            auto N = V->AsObject(); auto* Actual = ByPath.Find(Str(N, TEXT("path")));
            if (!Actual || !Same(MRValue(N), MRValue(*Actual))) return Fail(TEXT("WeaponRepair graph drift: ") + Str(N, TEXT("path")));
        }
        return true;
    }
    bool Instance(UMaterialInstanceConstant* M)
    {
        auto* B = Baseline.Find(M->GetOutermost()->GetName()); if (!B) return false;
        // A semantic snapshot must also work before the new parent has a file.
        // DiskPins handles original bytes independently; never save just to describe.
        TSharedPtr<FJsonObject> J = Describe(M);
        J->SetObjectField(TEXT("properties"), MRProperties(M, true));
        J->SetNumberField(TEXT("blend"), M->GetBlendMode());
        J->SetNumberField(TEXT("shading"), M->GetShadingModel());
        J->SetBoolField(TEXT("two_sided"), M->IsTwoSided());
        J->SetNumberField(TEXT("opacity_mask_clip"), M->GetOpacityMaskClipValue());
        TArray<TSharedPtr<FJsonValue>> Chain;
        TSet<UMaterialInterface*> Seen;
        for (UMaterialInterface* P = M; P; )
        {
            if (Seen.Contains(P) || Seen.Num() >= 32) return false;
            Seen.Add(P); Chain.Add(MakeShareable(new FJsonValueString(P->GetPathName())));
            auto* MI = Cast<UMaterialInstance>(P); P = MI ? MI->Parent : nullptr;
        }
        J->SetArrayField(TEXT("parent_chain"), Chain);
        J->SetObjectField(TEXT("static_overrides"), MRStatic(M->GetStaticParameters()));
        FStaticParameterSet Effective; M->GetStaticParameterValues(Effective);
        J->SetObjectField(TEXT("static_effective"), MRStatic(Effective));
        UMaterial* Base = M->GetMaterial(); if (!Base) return false;
        TArray<FName> Names; TArray<FGuid> IDs;
        TArray<TSharedPtr<FJsonValue>> Scalars, Vectors;
        Base->GetAllScalarParameterNames(Names, IDs);
        for (FName Name : Names)
        {
            float Value = 0; if (!M->GetScalarParameterValue(Name, Value)) return false;
            TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject);
            P->SetStringField(TEXT("name"), Name.ToString()); P->SetNumberField(TEXT("value"), Value);
            Scalars.Add(MRValue(P));
        }
        Names.Empty(); IDs.Empty(); Base->GetAllVectorParameterNames(Names, IDs);
        for (FName Name : Names)
        {
            FLinearColor Value; if (!M->GetVectorParameterValue(Name, Value)) return false;
            TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject);
            P->SetStringField(TEXT("name"), Name.ToString());
            TArray<TSharedPtr<FJsonValue>> Channels;
            for (float V : {Value.R, Value.G, Value.B, Value.A}) Channels.Add(MakeShareable(new FJsonValueNumber(V)));
            P->SetArrayField(TEXT("value"), Channels); Vectors.Add(MRValue(P));
        }
        J->SetArrayField(TEXT("scalar_parameters"), Scalars); J->SetArrayField(TEXT("vector_parameters"), Vectors);
        for (const TCHAR* K : {TEXT("parent_chain"), TEXT("static_overrides"), TEXT("static_effective"), TEXT("scalar_parameters"),
            TEXT("vector_parameters"), TEXT("texture_parameters"), TEXT("blend"), TEXT("shading"), TEXT("two_sided"), TEXT("opacity_mask_clip")})
            if (!Field(*B, J, K)) return Fail(TEXT("WeaponRepair instance drift: ") + M->GetName() + TEXT("/") + K);
        auto X = (*B)->GetObjectField(TEXT("properties")); auto Y = J->GetObjectField(TEXT("properties"));
        for (const TCHAR* K : {TEXT("ScalarParameterValues"), TEXT("VectorParameterValues"), TEXT("TextureParameterValues"), TEXT("FontParameterValues"), TEXT("BasePropertyOverrides")})
            if (!Field(X, Y, K)) return Fail(TEXT("WeaponRepair override bag drift: ") + M->GetName() + TEXT("/") + K);
        return true;
    }
};

static int32 WeaponFidelityRepair(const FString& Params, bool Verify)
{
    WFRStage(TEXT("entry")); // WFR_DIAGNOSTIC_STAGE
    FString SpecPath, BaselinePath, Receipt, Forbidden;
    if (!GIsEditor || !IsInGameThread() || (!Verify && !FApp::CanEverRender()) ||
        !FParse::Value(*Params, TEXT("WeaponRepairSpec="), SpecPath) ||
        !FParse::Value(*Params, TEXT("WeaponBaseline="), BaselinePath) || !FParse::Value(*Params, TEXT("Receipt="), Receipt) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")))
    { Fail(TEXT("WeaponRepair requires fixed spec, reviewed baseline, separate COW receipt and fresh editor; Apply requires rendering.")); return WFRStop(TEXT("admission")); }
    TSharedPtr<FJsonObject> Spec, Base;
    if (!WFRGate(HashFile(SpecPath).Equals(WFRRecipeHash, ESearchCase::IgnoreCase), TEXT("recipe-hash"), SpecPath) || !WFRGate(ReadJson(SpecPath, Spec), TEXT("recipe-json"), SpecPath) ||
        !WFRGate(HashFile(BaselinePath).Equals(Str(Spec, TEXT("baseline_sha1")), ESearchCase::IgnoreCase), TEXT("baseline-hash"), BaselinePath) || !WFRGate(ReadJson(BaselinePath, Base), TEXT("baseline-json"), BaselinePath) || Str(Base, TEXT("schema")) != TEXT("ut4-weapon-fidelity-baseline-v1") ||
        Str(Base, TEXT("report_sha256")) != Str(Spec, TEXT("report_sha256"))) return WFRStop(TEXT("recipe-baseline"));
    WFRStage(TEXT("recipe-baseline-passed")); // WFR_DIAGNOSTIC_STAGE
    FWeaponRepair R; R.Verify = Verify; R.Pins = Spec->GetObjectField(TEXT("original_sha1"));
    TSet<FString> Destinations;
    for (const auto& KV : Spec->GetObjectField(TEXT("clones"))->Values)
    { R.Clones.Add(KV.Key, KV.Value->AsString()); R.Canonical.Add(ObjectPath(KV.Value->AsString()), ObjectPath(KV.Key)); Destinations.Add(KV.Value->AsString().ToLower()); }
    for (const auto& V : Spec->GetArrayField(TEXT("instances"))) { R.Instances.Add(V->AsString()); Destinations.Add(V->AsString().ToLower()); }
    for (const auto& V : Spec->GetArrayField(TEXT("direct_parents"))) R.Direct.Add(V->AsString());
    if (R.Clones.Num() != 5 || R.Instances.Num() != 18 || R.Direct.Num() != 4 || Destinations.Num() != 23 || R.Pins->Values.Num() != 23 ||
        !R.Policy.Read(Receipt, SpecPath, Destinations) || !R.DiskPins()) return WFRStop(TEXT("scope-receipt-original-pins"));
    WFRStage(TEXT("scope-receipt-pins-passed")); // WFR_DIAGNOSTIC_STAGE
    for (const auto& V : Base->GetArrayField(TEXT("materials")))
    {
        auto B = V->AsObject(); const FString P = FPackageName::ObjectPathToPackageName(Str(B, TEXT("material")));
        if (R.Baseline.Contains(P)) return WFRStop(TEXT("baseline-duplicate"), P);
        R.Baseline.Add(P, B);
    }
    if (R.Baseline.Num() != 19) return WFRStop(TEXT("baseline-count"), FString::FromInt(R.Baseline.Num()));
    WFRStage(TEXT("baseline-index-passed")); // WFR_DIAGNOSTIC_STAGE
    // This operation must be the first loader of originals and destination clones.
    for (const auto& KV : R.Pins->Values) if (FindPackage(nullptr, *KV.Key)) return WFRStop(TEXT("original-already-loaded"), KV.Key);
    for (const auto& KV : R.Clones)
        if (FindPackage(nullptr, *KV.Value) || (!Verify && FPackageName::DoesPackageExist(KV.Value))) return WFRStop(TEXT("clone-loaded-or-existing"), KV.Value);
    WFRStage(TEXT("unloaded-gates-passed")); // WFR_DIAGNOSTIC_STAGE
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true); if (Registry.IsLoadingAssets()) return WFRStop(TEXT("registry-still-loading"));
    WFRStage(TEXT("load-originals")); // WFR_DIAGNOSTIC_STAGE
    for (const auto& KV : R.Pins->Values)
    {
        UObject* O = LoadObject<UObject>(nullptr, *ObjectPath(KV.Key));
        if (!O || (R.Instances.Contains(KV.Key) ? !Cast<UMaterialInstanceConstant>(O) : !R.Expressions(O))) return WFRStop(TEXT("original-load-or-type"), KV.Key);
        R.Objects.Add(KV.Key, O);
    }
    WFRStage(TEXT("check-original-instances")); // WFR_DIAGNOSTIC_STAGE
    for (const FString& P : R.Instances) if (!R.Instance(CastChecked<UMaterialInstanceConstant>(R.Objects.FindChecked(P)))) return WFRStop(TEXT("original-instance"), P);
    WFRStage(TEXT("describe-original-master")); // WFR_DIAGNOSTIC_STAGE
    auto* OriginalMaster = Cast<UMaterial>(R.Objects.FindChecked(WRMaster()));
    auto* Expected = R.Baseline.Find(WRMaster()); if (!OriginalMaster || !Expected) return WFRStop(TEXT("original-master-or-baseline"), WRMaster());
    TSharedPtr<FJsonObject> OriginalFacts;
    if (!MRDescribe(OriginalMaster, Registry, OriginalFacts)) return WFRStop(TEXT("original-master-describe"), WRMaster());
    auto Roots = OriginalFacts->GetObjectField(TEXT("roots"));
    Roots->SetObjectField(TEXT("Metallic"), MRPin(OriginalMaster->GetExpressionInputForProperty(MP_Metallic)));
    Roots->SetObjectField(TEXT("Roughness"), MRPin(OriginalMaster->GetExpressionInputForProperty(MP_Roughness)));
    Roots->SetObjectField(TEXT("Specular"), MRPin(OriginalMaster->GetExpressionInputForProperty(MP_Specular)));
    if (!R.Field(*Expected, OriginalFacts, TEXT("nodes")) ||
        !R.Field(*Expected, OriginalFacts, TEXT("roots")) || !R.Field(*Expected, OriginalFacts, TEXT("package_sha1"))) return WFRStop(TEXT("original-master-snapshot"), WRMaster());
    for (const auto& KV : (*Expected)->GetObjectField(TEXT("package_sha1"))->Values) R.Pins->SetField(KV.Key, KV.Value);
    WFRStage(TEXT("prepare-clones")); // WFR_DIAGNOSTIC_STAGE
    for (const auto& KV : R.Clones)
    {
        UObject* O = Verify ? LoadObject<UObject>(nullptr, *ObjectPath(KV.Value)) :
            DuplicateObject<UObject>(R.Objects.FindChecked(KV.Key), CreatePackage(nullptr, *KV.Value), FName(*FPackageName::GetShortName(KV.Value)));
        if (!O || O->GetClass() != R.Objects.FindChecked(KV.Key)->GetClass() || !R.Expressions(O)) return WFRStop(TEXT("clone-load-or-type"), KV.Value);
        for (auto* E : *R.Expressions(O)) if (!E || E->GetOuter() != O) return WFRStop(TEXT("clone-expression-owner"), KV.Value);
        R.Objects.Add(KV.Value, O);
    }
    if (!Verify)
    {
        for (const auto& KV : R.Clones)
        {
            UObject* O = R.Objects.FindChecked(KV.Value);
            for (auto* E : *R.Expressions(O)) if (auto* Call = Cast<UMaterialExpressionMaterialFunctionCall>(E))
            {
                if (!Call->MaterialFunction) return WFRStop(TEXT("function-call-null"), E->GetPathName());
                const FString* Dest = R.Clones.Find(Call->MaterialFunction->GetOutermost()->GetName());
                if (Dest && !Call->SetMaterialFunction(Cast<UMaterialFunction>(O), Call->MaterialFunction,
                    CastChecked<UMaterialFunction>(R.Objects.FindChecked(*Dest)))) return WFRStop(TEXT("function-remap"), E->GetPathName());
            }
        }
    }
    WFRStage(TEXT("check-ao-wpo")); // WFR_DIAGNOSTIC_STAGE
    const FString MF = TEXT("/Game/RestrictedAssets/Weapons/Global/Material/MF/");
    const FString Texture = MF + TEXT("MF_BaseShader_Textures"), Dirt = MF + TEXT("MF_Dirt");
    R.AOAliases(Texture, TEXT("MaterialExpressionPrecomputedAOMask_0")); R.AOAliases(Dirt, TEXT("MaterialExpressionPrecomputedAOMask_4"));
    if (!R.AO(R.Objects.FindChecked(R.Clones.FindChecked(Texture)), TEXT("MaterialExpressionPrecomputedAOMask_0")) ||
        !R.AO(R.Objects.FindChecked(R.Clones.FindChecked(Dirt)), TEXT("MaterialExpressionPrecomputedAOMask_4"))) return WFRStop(TEXT("ao-branches"));
    auto* Master = CastChecked<UMaterial>(R.Objects.FindChecked(R.Clones.FindChecked(WRMaster())));
    if (!R.WPO(Master)) return WFRStop(TEXT("wpo-branch"));
    if (!Verify)
    {
        for (const auto& KV : R.Clones) R.Objects.FindChecked(KV.Value)->PostEditChange();
        FMaterialUpdateContext Update; Update.AddMaterial(Master);
        for (const FString& P : R.Direct)
        {
            auto* MI = CastChecked<UMaterialInstanceConstant>(R.Objects.FindChecked(P));
            if (MI->Parent != OriginalMaster) return WFRStop(TEXT("direct-parent"), P);
            Update.AddMaterialInstance(MI); MI->SetParentEditorOnly(Master);
        }
    }
    WFRStage(TEXT("check-clone-graph")); // WFR_DIAGNOSTIC_STAGE
    if (!R.Graph(Master, *Expected)) return WFRStop(TEXT("clone-graph"));
    for (const auto& KV : R.Clones)
    {
        TSet<FString> Skip; Skip.Add(TEXT("StateId")); Skip.Add(TEXT("Expressions"));
        Skip.Add(TEXT("FunctionExpressions")); Skip.Add(TEXT("MaterialAttributes"));
        // Derived compile dependency IDs change when cloned functions receive new StateIds.
        // MRGraph above checks the complete normalized dependency graph independently.
        Skip.Add(TEXT("MaterialFunctionInfos"));
        // Pinned UMaterialInterface PostDuplicate/PostEditChangeProperty regenerate this cache identity.
        Skip.Add(TEXT("LightingGuid"));
        if (!R.Properties(R.Objects.FindChecked(KV.Key), R.Objects.FindChecked(KV.Value), Skip))
        { Fail(TEXT("WeaponRepair cloned object properties drift: ") + KV.Key); return WFRStop(TEXT("clone-properties"), KV.Key); }
    }
    for (const FString& P : R.Instances) if (!R.Instance(CastChecked<UMaterialInstanceConstant>(R.Objects.FindChecked(P)))) return WFRStop(TEXT("reparented-instance"), P);
    if (!R.DiskPins()) return WFRStop(TEXT("pre-save-disk-pins"));
    TArray<FString> Saves; for (const auto& KV : R.Clones) Saves.Add(KV.Value);
    Saves.Append(R.Direct); Saves.Sort(); if (Saves.Num() != 9) return WFRStop(TEXT("save-count"), FString::FromInt(Saves.Num()));
    WFRStage(TEXT("all-semantic-checks-passed")); // WFR_DIAGNOSTIC_STAGE
    // No disk mutation until every structural, override, provenance and destination check passes.
    for (const FString& P : Saves) if (!R.Policy.Check(P)) return WFRStop(TEXT("save-policy"), P);
    WFRStage(TEXT("save-policy-passed")); // WFR_DIAGNOSTIC_STAGE
    for (const FString& P : Saves)
    {
        UObject* O = R.Objects.FindChecked(P);
        if (!Verify)
        {
            O->MarkPackageDirty();
            if (!UPackage::SavePackage(O->GetOutermost(), O, RF_Public | RF_Standalone, *R.Policy.Files.FindChecked(P.ToLower()))) return WFRStop(TEXT("save-package"), P);
        }
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_REPAIR package=%s sha1=%s saved=%d"), *P,
            *HashFile(R.Policy.Files.FindChecked(P.ToLower())), Verify ? 0 : 1);
    }
    R.Verify = true; if (!R.DiskPins()) return WFRStop(TEXT("post-save-disk-pins"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_REPAIR complete mode=%s destinations=23 saves=%d untouchedMICs=14; shader/runtime validation still required"), Verify ? TEXT("verify") : TEXT("apply"), Verify ? 0 : 9);
    return 0;
}
