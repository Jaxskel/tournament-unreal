// Original diagnostic implementation. Include inside UT4Compat after the reports.
// Top-level includes: MaterialExpressionCustom, SceneDepth, CameraVectorWS, FeatureLevelSwitch.
// Exactly one physical COW material save; no original-source save or dirty-flag clearing.
static bool RejectConfiguredRobotRedirects();
static const TCHAR* BSXSpecSHA1 = TEXT("0e861c09fbaae4b1e596130b8dcade399ca9f7f5");
static FString BSXPackage() { return BSRNick() + TEXT("M_Robust_BlobShadow"); }
static FString BSXInverse() { return BSRNick() + TEXT("M_Robust_BlobShadowInverse"); }
static const TCHAR* BSXNames[] = {TEXT("TournamentBlobES2Switch"), TEXT("TournamentBlobES2Normal"),
    TEXT("TournamentBlobSceneDepth"), TEXT("TournamentBlobCameraVector")};
static const TCHAR* BSXCode = TEXT(R"SHADER(float4 receiverSv = Parameters.SvPosition;
receiverSv.z = ConvertToDeviceZ(ReceiverDepth);
float3 receiverPosition = SvPositionToResolvedTranslatedWorld(receiverSv);
float3 horizontal = ddx(receiverPosition);
float3 vertical = ddy(receiverPosition);
float3 receiverNormal = cross(horizontal, vertical);
float lengthSquared = dot(receiverNormal, receiverNormal);
if (!(ReceiverDepth > 0.0 && ReceiverDepth < 65504.0 &&
      lengthSquared > 1e-12 && lengthSquared < 1e30))
{
    return float4(0.0, 0.0, 0.0, 0.0);
}
receiverNormal *= rsqrt(lengthSquared);
receiverNormal = dot(receiverNormal, CameraDirection) < 0.0 ? -receiverNormal : receiverNormal;
return float4(receiverNormal, 0.0);
)SHADER");

// BSX_DIAGNOSTICS_BEGIN: bounded logging only; no validation or mutation policy.
static int32 BSXDiagnosticLines = 0;
static bool BSXBad(bool Failed, const TCHAR* Gate, const TCHAR* Context = TEXT(""))
{
    if (Failed && BSXDiagnosticLines < 64)
    {
        ++BSXDiagnosticLines;
        UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_BLOB_GATE_FAIL gate=%s context=%s"), Gate, Context);
    }
    return Failed;
}
template<typename T> static bool BSXBad(T* Value, const TCHAR* Gate, const TCHAR* Context = TEXT(""))
{
    return BSXBad(Value != nullptr, Gate, Context);
}
static bool BSXGood(bool Passed, const TCHAR* Gate, const TCHAR* Context = TEXT(""))
{
    BSXBad(!Passed, Gate, Context);
    return Passed;
}
static void BSXStage(const TCHAR* Stage)
{
    if (BSXDiagnosticLines < 64)
    {
        ++BSXDiagnosticLines;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_BLOB_STAGE %s"), Stage);
    }
}
// BSX_DIAGNOSTICS_END

// Only the known expression-reference substitution is normalized, never values,
// masks, defaults, parameter GUIDs, root wiring, or unrelated graph properties.
static FString BSXNormal(FString S, bool Delta)
{
    if (!Delta) return S;
    const FString Prefix = ObjectPath(BSXPackage()) + TEXT(":");
    const FString A = Prefix + BSXNames[0], B = Prefix + TEXT("MaterialExpressionSceneTexture_3");
    S.ReplaceInline(*(TEXT("MaterialExpressionFeatureLevelSwitch'") + A + TEXT("'")),
        *(TEXT("MaterialExpressionSceneTexture'") + B + TEXT("'")), ESearchCase::CaseSensitive);
    S.ReplaceInline(*A, *B, ESearchCase::CaseSensitive);
    return S;
}
static bool BSXSame(const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B, bool Delta, int32 Depth = 0)
{
    if (!A.IsValid() || !B.IsValid() || A->Type != B->Type || Depth > 64) return false;
    if (A->Type == EJson::String) return A->AsString() == BSXNormal(B->AsString(), Delta);
    if (A->Type == EJson::Number) return A->AsNumber() == B->AsNumber();
    if (A->Type == EJson::Boolean) return A->AsBool() == B->AsBool();
    if (A->Type == EJson::Null) return true;
    if (A->Type == EJson::Array)
    {
        const auto& X = A->AsArray(); const auto& Y = B->AsArray();
        if (X.Num() != Y.Num()) return false;
        for (int32 I = 0; I < X.Num(); ++I) if (!BSXSame(X[I], Y[I], Delta, Depth + 1)) return false;
        return true;
    }
    if (A->Type == EJson::Object)
    {
        const auto& X = A->AsObject()->Values; const auto& Y = B->AsObject()->Values;
        if (X.Num() != Y.Num()) return false;
        for (const auto& KV : X)
        { const auto* V = Y.Find(KV.Key); if (!V || !BSXSame(KV.Value, *V, Delta, Depth + 1)) return false; }
        return true;
    }
    return false;
}
static bool BSXField(const TSharedPtr<FJsonObject>& A, const TSharedPtr<FJsonObject>& B, const TCHAR* K, bool Delta = false)
{
    const auto* X = A->Values.Find(K); const auto* Y = B->Values.Find(K);
    return BSXGood(X && Y && BSXSame(*X, *Y, Delta), TEXT("BSXField"), K);
}
static UMaterialExpression* BSXNode(UMaterial* M, const TCHAR* Name, const TCHAR* Class)
{
    UClass* ExactClass = FindObject<UClass>(nullptr, *(FString(TEXT("/Script/Engine.")) + Class));
    if (BSXBad((!ExactClass), TEXT("BSXNode:L71.1")) || BSXBad((!ExactClass->IsChildOf(UMaterialExpression::StaticClass())), TEXT("BSXNode:L71.2"))) return nullptr;
    UMaterialExpression* Found = nullptr;
    for (auto* E : M->Expressions) if (E && E->GetName() == Name)
    { if (BSXBad((Found), TEXT("BSXNode:L74.1")) || BSXBad((E->GetOuter() != M), TEXT("BSXNode:L74.2")) || BSXBad((E->GetClass() != ExactClass), TEXT("BSXNode:L74.3"))) return nullptr; Found = E; }
    return Found;
}
static bool BSXPin(const FExpressionInput& P, UMaterialExpression* E, bool RGBA = false)
{
    const int32 V = RGBA ? 1 : 0;
    return P.Expression == E && P.OutputIndex == 0 && P.Mask == V && P.MaskR == V &&
        P.MaskG == V && P.MaskB == V && P.MaskA == V;
}
template<typename T> static T* BSXAdd(UMaterial* M, const TCHAR* Name)
{
    if (BSXBad((FindObject<UObject>(M, Name)), TEXT("BSXAdd:L85.1"))) return nullptr;
    T* E = NewObject<T>(M, FName(Name));
    E->Material = M; E->MaterialExpressionGuid = FGuid::NewGuid(); M->Expressions.Add(E); return E;
}
// These two native classes declare NO_API StaticClass/constructors in this
// editor. Instantiate through the exported base and an exact loaded Engine
// UClass; never call their typed NewObject/Cast/StaticClass entry points.
static UMaterialExpression* BSXAddReflected(UMaterial* M, const TCHAR* Name, const TCHAR* ClassName)
{
    if (BSXBad((FindObject<UObject>(M, Name)), TEXT("BSXAddReflected:L94.1"))) return nullptr;
    UClass* ExactClass = FindObject<UClass>(nullptr, *(FString(TEXT("/Script/Engine.")) + ClassName));
    if (BSXBad((!ExactClass), TEXT("BSXAddReflected:L96.1")) || BSXBad((!ExactClass->IsChildOf(UMaterialExpression::StaticClass())), TEXT("BSXAddReflected:L96.2"))) return nullptr;
    UMaterialExpression* E = NewObject<UMaterialExpression>(M, ExactClass, FName(Name));
    if (BSXBad((!E), TEXT("BSXAddReflected:L98.1")) || BSXBad((E->GetClass() != ExactClass), TEXT("BSXAddReflected:L98.2"))) return nullptr;
    E->Material = M; E->MaterialExpressionGuid = FGuid::NewGuid(); M->Expressions.Add(E); return E;
}
static bool BSXShape(UMaterial* M, bool Delta)
{
    auto* Old = BSXNode(M, TEXT("MaterialExpressionSceneTexture_3"), TEXT("MaterialExpressionSceneTexture"));
    auto* Mask = BSXNode(M, TEXT("MaterialExpressionComponentMask_4"), TEXT("MaterialExpressionComponentMask"));
    if (BSXBad((!Old), TEXT("BSXShape:L105.1")) || BSXBad((!Mask), TEXT("BSXShape:L105.2")) || BSXBad((!Mask->GetInput(0)), TEXT("BSXShape:L105.3")) || BSXBad((Str(MRProperties(Old, true), TEXT("SceneTextureId")) != TEXT("PPI_WorldNormal")), TEXT("BSXShape:L105.4"))) return false;
    if (!Delta) return BSXGood(BSXPin(*Mask->GetInput(0), Old, true), TEXT("BSXShape.original_mask"));
    auto* Switch = Cast<UMaterialExpressionFeatureLevelSwitch>(BSXNode(M, BSXNames[0], TEXT("MaterialExpressionFeatureLevelSwitch")));
    auto* Custom = Cast<UMaterialExpressionCustom>(BSXNode(M, BSXNames[1], TEXT("MaterialExpressionCustom")));
    auto* Depth = static_cast<UMaterialExpressionSceneDepth*>(BSXNode(M, BSXNames[2], TEXT("MaterialExpressionSceneDepth")));
    auto* Camera = BSXNode(M, BSXNames[3], TEXT("MaterialExpressionCameraVectorWS"));
    if (BSXBad((!Switch), TEXT("BSXShape:L111.1")) || BSXBad((!Custom), TEXT("BSXShape:L111.2")) || BSXBad((!Depth), TEXT("BSXShape:L111.3")) || BSXBad((!Camera), TEXT("BSXShape:L111.4")) || BSXBad((!M->bUseFullPrecision), TEXT("BSXShape:L111.5")) ||
        BSXBad((!BSXPin(*Mask->GetInput(0), Switch, true)), TEXT("BSXShape:L111.6")) || BSXBad((!BSXPin(Switch->Default, Old, true)), TEXT("BSXShape:L111.7")) ||
        BSXBad((!BSXPin(Switch->Inputs[ERHIFeatureLevel::ES2], Custom)), TEXT("BSXShape:L111.8")) || BSXBad((Custom->Code != BSXCode), TEXT("BSXShape:L111.9")) ||
        BSXBad((Custom->OutputType != CMOT_Float4), TEXT("BSXShape:L111.10")) || BSXBad((Custom->Inputs.Num() != 2), TEXT("BSXShape:L111.11")) ||
        BSXBad((Custom->Inputs[0].InputName != TEXT("ReceiverDepth")), TEXT("BSXShape:L111.12")) || BSXBad((!BSXPin(Custom->Inputs[0].Input, Depth)), TEXT("BSXShape:L111.13")) ||
        BSXBad((Custom->Inputs[1].InputName != TEXT("CameraDirection")), TEXT("BSXShape:L111.14")) || BSXBad((!BSXPin(Custom->Inputs[1].Input, Camera)), TEXT("BSXShape:L111.15")) ||
        BSXBad((Depth->InputMode != EMaterialSceneAttributeInputMode::Coordinates), TEXT("BSXShape:L111.16")) || BSXBad((Depth->Input.Expression), TEXT("BSXShape:L111.17")) ||
        BSXBad((Depth->Coordinates_DEPRECATED.Expression), TEXT("BSXShape:L111.18")) || BSXBad((Depth->ConstInput != FVector2D::ZeroVector), TEXT("BSXShape:L111.19"))) return false;
    for (int32 I = 1; I < ERHIFeatureLevel::Num; ++I) if (BSXBad((Switch->Inputs[I].Expression), TEXT("BSXShape:L119.1"))) return false;
    TSet<FGuid> IDs;
    UMaterialExpression* NewNodes[] = {Switch, Custom, Depth, Camera};
    for (auto* E : NewNodes)
    { if (BSXBad((!E->MaterialExpressionGuid.IsValid()), TEXT("BSXShape:L123.1")) || BSXBad((IDs.Contains(E->MaterialExpressionGuid)), TEXT("BSXShape:L123.2"))) return false; IDs.Add(E->MaterialExpressionGuid); }
    for (auto* E : M->Expressions)
        if (BSXBad((E != Switch && E != Custom && E != Depth && E != Camera && IDs.Contains(E->MaterialExpressionGuid)), TEXT("BSXShape:L125.1"))) return false;
    return true;
}
static bool BSXEdit(UMaterial* M)
{
    if (BSXBad((!BSXShape(M, false)), TEXT("BSXEdit:L130.1"))) return false;
    for (const TCHAR* N : BSXNames) if (BSXBad((FindObject<UObject>(M, N)), TEXT("BSXEdit:L131.1"))) return false;
    auto* Mask = BSXNode(M, TEXT("MaterialExpressionComponentMask_4"), TEXT("MaterialExpressionComponentMask"));
    const FExpressionInput Original = *Mask->GetInput(0);
    auto* Switch = BSXAdd<UMaterialExpressionFeatureLevelSwitch>(M, BSXNames[0]);
    auto* Custom = BSXAdd<UMaterialExpressionCustom>(M, BSXNames[1]);
    auto* Depth = static_cast<UMaterialExpressionSceneDepth*>(BSXAddReflected(M, BSXNames[2], TEXT("MaterialExpressionSceneDepth")));
    auto* Camera = BSXAddReflected(M, BSXNames[3], TEXT("MaterialExpressionCameraVectorWS"));
    if (BSXBad((!Switch), TEXT("BSXEdit:L138.1")) || BSXBad((!Custom), TEXT("BSXEdit:L138.2")) || BSXBad((!Depth), TEXT("BSXEdit:L138.3")) || BSXBad((!Camera), TEXT("BSXEdit:L138.4"))) return false;
    Switch->Default = Original; Switch->Inputs[ERHIFeatureLevel::ES2].Expression = Custom;
    Custom->OutputType = CMOT_Float4; Custom->Code = BSXCode;
    Custom->Description = TEXT("EXPERIMENT: approximate receiver normal from alpha-copy depth; not GBuffer parity");
    Custom->Inputs.SetNum(2);
    Custom->Inputs[0].InputName = TEXT("ReceiverDepth"); Custom->Inputs[0].Input.Expression = Depth;
    Custom->Inputs[1].InputName = TEXT("CameraDirection"); Custom->Inputs[1].Input.Expression = Camera;
    Depth->InputMode = EMaterialSceneAttributeInputMode::Coordinates;
    Depth->ConstInput = FVector2D::ZeroVector;
    // Keep the original all-RGBA input mask; float4 Custom output makes it valid.
    Mask->GetInput(0)->Expression = Switch;
    M->bUseFullPrecision = true;
    return BSXGood(BSXShape(M, true), TEXT("BSXEdit.final_shape"));
}
static bool BSXFacts(UMaterialInterface* Asset, const TSharedPtr<FJsonObject>& Expected, IAssetRegistry& Registry, bool Delta,
    TSharedPtr<FJsonObject>& Actual)
{
    if (BSXBad((!MRDescribe(Asset, Registry, Actual)), TEXT("BSXFacts:L155.1"))) return false;
    for (const TCHAR* K : {TEXT("material"), TEXT("class"), TEXT("base_material"), TEXT("blend"), TEXT("shading"),
        TEXT("two_sided"), TEXT("opacity_mask_clip"), TEXT("parent_chain"), TEXT("texture_parameters"),
        TEXT("scalar_parameters"), TEXT("vector_parameters"), TEXT("base_graph_textures_including_functions"),
        TEXT("has_null_texture_expression"), TEXT("roots")})
        if (BSXBad((!BSXField(Expected, Actual, K)), TEXT("BSXFacts:L160.1"))) return Fail(FString(TEXT("Blob experiment baseline mismatch: ")) + K);
    for (const TCHAR* K : {TEXT("static_overrides"), TEXT("static_effective")})
        if (BSXBad((Expected->HasField(K) && !BSXField(Expected, Actual, K)), TEXT("BSXFacts:L162.1"))) return false;
    TSharedPtr<FJsonObject> X = MakeShareable(new FJsonObject); X->Values = Expected->GetObjectField(TEXT("properties"))->Values;
    TSharedPtr<FJsonObject> Y = MakeShareable(new FJsonObject); Y->Values = Actual->GetObjectField(TEXT("properties"))->Values;
    if (Delta)
    {
        for (const TCHAR* K : {TEXT("StateId"), TEXT("LightingGuid"), TEXT("Expressions"), TEXT("bUseFullPrecision")}) { X->RemoveField(K); Y->RemoveField(K); }
        const auto& A = Expected->GetArrayField(TEXT("nodes")); const auto& B = Actual->GetArrayField(TEXT("nodes"));
        int32 OldIndex = 0, Added = 0;
        for (const auto& V : B)
        {
            auto N = V->AsObject(); bool New = false;
            if (Str(N, TEXT("owner")) == ObjectPath(BSXPackage()))
                for (const TCHAR* Name : BSXNames) New |= Str(N, TEXT("name")) == Name;
            if (New) { ++Added; continue; }
            if (BSXBad((!A.IsValidIndex(OldIndex)), TEXT("BSXFacts:L176.1")) || BSXBad((!BSXSame(A[OldIndex++], V, true)), TEXT("BSXFacts:L176.2"))) return Fail(TEXT("Blob experiment original graph drift."));
        }
        if (BSXBad((Added != 4), TEXT("BSXFacts:L178.1")) || BSXBad((OldIndex != A.Num()), TEXT("BSXFacts:L178.2"))) return false;
        if (BSXBad((Str(Expected->GetObjectField(TEXT("properties")), TEXT("StateId")) ==
            Str(Actual->GetObjectField(TEXT("properties")), TEXT("StateId"))), TEXT("BSXFacts:L179.1"))) return Fail(TEXT("Blob experiment StateId did not change."));
    }
    else if (BSXBad((!BSXField(Expected, Actual, TEXT("nodes"))), TEXT("BSXFacts:L182.1"))) return false;
    return BSXGood(BSXSame(MRValue(X), MRValue(Y), false), TEXT("BSXFacts.properties"), *Asset->GetPathName());
}
static bool BSXDisk(const TSharedPtr<FJsonObject>& Pins, bool SkipTarget)
{
    TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
    for (const auto& KV : Pins->Values)
    {
        if (SkipTarget && KV.Key == BSXPackage()) continue;
        if (BSXBad((!MRHashPackage(KV.Key, Hashes)), TEXT("BSXDisk:L191.1")) || BSXBad((!Str(Hashes, *KV.Key).Equals(KV.Value->AsString(), ESearchCase::IgnoreCase)), TEXT("BSXDisk:L191.2")))
            return Fail(TEXT("Blob experiment package bytes changed: ") + KV.Key);
    }
    return true;
}
static int32 BlobShadowExperiment(const FString& Params)
{
    BSXDiagnosticLines = 0; // diagnostic-only per invocation
    BSXStage(TEXT("entered"));
    FString Action, SpecPath, BaselinePath, Receipt, SourceFile, Aftermath, Forbidden;
    if (BSXBad((!GIsEditor), TEXT("BlobShadowExperiment:L199.1")) || BSXBad((!IsInGameThread()), TEXT("BlobShadowExperiment:L199.2")) ||
        BSXBad((!FParse::Value(*Params, TEXT("BlobAction="), Action)), TEXT("BlobShadowExperiment:L199.3")) ||
        BSXBad((!FParse::Value(*Params, TEXT("BlobExperimentSpec="), SpecPath)), TEXT("BlobShadowExperiment:L199.4")) ||
        BSXBad((!FParse::Value(*Params, TEXT("BlobBaseline="), BaselinePath)), TEXT("BlobShadowExperiment:L199.5")) ||
        BSXBad((!FParse::Value(*Params, TEXT("Receipt="), Receipt)), TEXT("BlobShadowExperiment:L199.6")) ||
        BSXBad((!FParse::Value(*Params, TEXT("BlobOriginalFile="), SourceFile)), TEXT("BlobShadowExperiment:L199.7")) ||
        BSXBad((FParse::Value(*Params, TEXT("Manifest="), Forbidden)), TEXT("BlobShadowExperiment:L199.8")) ||
        BSXBad((FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering"))), TEXT("BlobShadowExperiment:L199.9"))) return 1;
    const bool Apply = Action == TEXT("Apply"), Verify = Action == TEXT("Verify"), Report = Action == TEXT("Report");
    if (BSXBad(((!Apply && !Verify && !Report)), TEXT("BlobShadowExperiment:L208.1")) || BSXBad(((Apply && (!FApp::CanEverRender() ||
        !FParse::Param(*Params, TEXT("AcknowledgeApproximateBlobNormal"))))), TEXT("BlobShadowExperiment:L208.2")))
    { Fail(TEXT("Explicit diagnostic action required; Apply needs rendering and AcknowledgeApproximateBlobNormal.")); return 1; }
    if (BSXBad(((Apply || Verify) && !FParse::Value(*Params, TEXT("BlobAftermath="), Aftermath)), TEXT("BlobShadowExperiment:L211.1"))) return 1;
    BSXStage(TEXT("arguments_accepted"));
    TSharedPtr<FJsonObject> Spec, Baseline;
    if (BSXBad((!Physical(SpecPath, false)), TEXT("BlobShadowExperiment:L213.1")) || BSXBad((!Physical(BaselinePath, false)), TEXT("BlobShadowExperiment:L213.2")) ||
        BSXBad((!HashFile(SpecPath).Equals(BSXSpecSHA1, ESearchCase::IgnoreCase)), TEXT("BlobShadowExperiment:L213.3")) || BSXBad((!ReadJson(SpecPath, Spec)), TEXT("BlobShadowExperiment:L213.4")) ||
        BSXBad((!HashFile(BaselinePath).Equals(Str(Spec, TEXT("baseline_sha1")), ESearchCase::IgnoreCase)), TEXT("BlobShadowExperiment:L213.5")) ||
        BSXBad((!ReadJson(BaselinePath, Baseline)), TEXT("BlobShadowExperiment:L213.6")) || BSXBad((Str(Baseline, TEXT("schema")) != TEXT("ut4-blob-experiment-baseline-v1")), TEXT("BlobShadowExperiment:L213.7"))) return 1;
    BSXStage(TEXT("spec_and_baseline_pins_accepted"));
    TSet<FString> Saves; Saves.Add(BSXPackage().ToLower()); FSavePolicy Policy;
    if (BSXBad((!Policy.Read(Receipt, SpecPath, Saves)), TEXT("BlobShadowExperiment:L218.1")) || BSXBad((!RejectConfiguredRobotRedirects()), TEXT("BlobShadowExperiment:L218.2"))) return 1;
    BSXStage(TEXT("receipt_and_redirects_accepted"));
    const FString Target = Policy.Files.FindChecked(BSXPackage().ToLower()); SourceFile = Full(SourceFile);
    const auto Pins = Spec->GetObjectField(TEXT("original_sha1"));
    const FString PristineHash = Str(Pins, *BSXPackage());
    if (BSXBad((!Within(SourceFile, Policy.OriginalRoot)), TEXT("BlobShadowExperiment:L222.1")) || BSXBad((Within(SourceFile, Policy.ContentRoot)), TEXT("BlobShadowExperiment:L222.2")) ||
        BSXBad((!SourceFile.EndsWith(TEXT("/Content/") + BSXPackage().Mid(6) + TEXT(".uasset"), ESearchCase::IgnoreCase)), TEXT("BlobShadowExperiment:L222.3")) ||
        BSXBad((!Physical(SourceFile, false)), TEXT("BlobShadowExperiment:L222.4")) || BSXBad((!HashFile(SourceFile).Equals(PristineHash, ESearchCase::IgnoreCase)), TEXT("BlobShadowExperiment:L222.5"))) return 1;
    if (Apply || Verify)
    {
        Aftermath = Full(Aftermath);
        if (BSXBad((Within(Aftermath, Policy.ContentRoot)), TEXT("BlobShadowExperiment:L228.1")) || BSXBad((Within(Aftermath, Policy.OriginalRoot)), TEXT("BlobShadowExperiment:L228.2")) ||
            BSXBad((!Physical(Aftermath, Apply)), TEXT("BlobShadowExperiment:L228.3")) || BSXBad(((Apply && FPaths::FileExists(Aftermath))), TEXT("BlobShadowExperiment:L228.4"))) return 1;
    }
    BSXStage(TEXT("original_and_aftermath_paths_accepted"));
    TSharedPtr<FJsonObject> Previous;
    if (BSXBad((Verify && (!ReadJson(Aftermath, Previous) || Str(Previous, TEXT("schema")) != TEXT("ut4-blob-experiment-aftermath-v1") ||
        Str(Previous, TEXT("spec_sha1")) != HashFile(SpecPath) || Str(Previous, TEXT("baseline_sha1")) != HashFile(BaselinePath) ||
        Str(Previous, TEXT("target_sha1")) != HashFile(Target) || Str(Previous, TEXT("target_file")) != Target)), TEXT("BlobShadowExperiment:L232.1"))) return 1;
    if (BSXBad((!BSXDisk(Pins, Verify)), TEXT("BlobShadowExperiment:L235.1"))) return 1;
    for (const FString& P : {BSXPackage(), BSXInverse()})
        if (BSXBad((FindPackage(nullptr, *P)), TEXT("BlobShadowExperiment:L237.1"))) { Fail(TEXT("Blob experiment requires a fresh process: ") + P); return 1; }
    BSXStage(TEXT("disk_pins_and_fresh_packages_accepted"));
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true); if (BSXBad((Registry.IsLoadingAssets()), TEXT("BlobShadowExperiment:L239.1"))) return 1;
    BSXStage(TEXT("registry_ready"));
    auto* M = LoadObject<UMaterial>(nullptr, *ObjectPath(BSXPackage()));
    auto* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(BSXInverse()));
    const auto& Materials = Baseline->GetArrayField(TEXT("materials"));
    if (BSXBad((!M), TEXT("BlobShadowExperiment:L243.1")) || BSXBad((!MI), TEXT("BlobShadowExperiment:L243.2")) || BSXBad((Materials.Num() != 2), TEXT("BlobShadowExperiment:L243.3")) || BSXBad((MI->Parent != M), TEXT("BlobShadowExperiment:L243.4"))) return 1;
    TSharedPtr<FJsonObject> MasterBase, InverseBase;
    for (const auto& V : Materials)
    {
        auto J = V->AsObject();
        if (Str(J, TEXT("material")) == ObjectPath(BSXPackage())) MasterBase = J;
        if (Str(J, TEXT("material")) == ObjectPath(BSXInverse())) InverseBase = J;
    }
    BSXStage(TEXT("primary_and_inverse_loaded"));
    const bool DirtyAfterLoad = M->GetOutermost()->IsDirty();
    TSharedPtr<FJsonObject> Facts, InverseFacts;
    if (BSXBad((!MasterBase.IsValid()), TEXT("BlobShadowExperiment:L253.1")) || BSXBad((!InverseBase.IsValid()), TEXT("BlobShadowExperiment:L253.2")) || BSXBad((!BSXShape(M, Verify)), TEXT("BlobShadowExperiment:L253.3")) ||
        BSXBad((!BSXFacts(M, MasterBase, Registry, Verify, Facts)), TEXT("BlobShadowExperiment:L253.4")) || BSXBad((!BSXFacts(MI, InverseBase, Registry, false, InverseFacts)), TEXT("BlobShadowExperiment:L253.5"))) return 1;
    BSXStage(TEXT("baseline_shape_and_facts_accepted"));
    // Known load-dirty is accepted ONLY in this new operation after exact native
    // graph/properties/parameter and pristine source+target byte comparisons.
    // Existing report/repair policy is untouched; no dirty flag is ever cleared.
    const FString BeforeState = Str(MasterBase->GetObjectField(TEXT("properties")), TEXT("StateId"));
    if (Apply)
    {
        {
            BSXStage(TEXT("apply_edit_begin"));
            FMaterialUpdateContext Update; Update.AddMaterial(M); M->PreEditChange(nullptr);
            if (BSXBad((!BSXEdit(M)), TEXT("BlobShadowExperiment:L263.1"))) return 1;
            BSXStage(TEXT("apply_edit_shape_accepted"));
            M->PostEditChange();
        }
        if (BSXBad((!BSXShape(M, true)), TEXT("BlobShadowExperiment:L266.1")) || BSXBad((!BSXFacts(M, MasterBase, Registry, true, Facts)), TEXT("BlobShadowExperiment:L266.2")) ||
            BSXBad((!BSXFacts(MI, InverseBase, Registry, false, InverseFacts)), TEXT("BlobShadowExperiment:L266.3")) || BSXBad((!BSXDisk(Pins, false)), TEXT("BlobShadowExperiment:L266.4")) ||
            BSXBad((!HashFile(SourceFile).Equals(PristineHash, ESearchCase::IgnoreCase)), TEXT("BlobShadowExperiment:L266.5")) || BSXBad((!Policy.Check(BSXPackage())), TEXT("BlobShadowExperiment:L266.6"))) return 1;
        BSXStage(TEXT("presave_gates_accepted"));
        if (BSXBad((!Policy.Save(M)), TEXT("BlobShadowExperiment:L269.1"))) return 1;
        BSXStage(TEXT("save_succeeded"));
    }
    if (BSXBad((!BSXDisk(Pins, Apply || Verify)), TEXT("BlobShadowExperiment:L271.1")) || BSXBad((!HashFile(SourceFile).Equals(PristineHash, ESearchCase::IgnoreCase)), TEXT("BlobShadowExperiment:L271.2"))) return 1;
    BSXStage(TEXT("final_disk_pins_accepted"));
    TSharedPtr<FJsonObject> Out = MakeShareable(new FJsonObject);
    Out->SetStringField(TEXT("schema"), TEXT("ut4-blob-experiment-aftermath-v1"));
    Out->SetStringField(TEXT("action"), Action); Out->SetStringField(TEXT("spec_sha1"), HashFile(SpecPath));
    Out->SetStringField(TEXT("baseline_sha1"), HashFile(BaselinePath)); Out->SetStringField(TEXT("target_file"), Target);
    Out->SetStringField(TEXT("source_file"), SourceFile); Out->SetStringField(TEXT("source_sha1"), HashFile(SourceFile));
    Out->SetStringField(TEXT("target_sha1"), HashFile(Target)); Out->SetBoolField(TEXT("observed_load_dirty"), DirtyAfterLoad);
    Out->SetStringField(TEXT("before_state_id"), BeforeState);
    Out->SetStringField(TEXT("after_state_id"), Str(MRProperties(M, true), TEXT("StateId")));
    Out->SetStringField(TEXT("before_lighting_guid"), Str(MasterBase->GetObjectField(TEXT("properties")), TEXT("LightingGuid")));
    Out->SetStringField(TEXT("after_lighting_guid"), Str(MRProperties(M, true), TEXT("LightingGuid")));
    Out->SetBoolField(TEXT("full_precision_after"), M->bUseFullPrecision);
    Out->SetStringField(TEXT("full_precision_before_native_text"), Str(MasterBase->GetObjectField(TEXT("properties")), TEXT("bUseFullPrecision")));
    Out->SetBoolField(TEXT("promotion_allowed"), false); Out->SetBoolField(TEXT("shader_compile_verified"), false);
    Out->SetBoolField(TEXT("browser_render_verified"), false); Out->SetBoolField(TEXT("native_gbuffer_parity"), false);
    Out->SetBoolField(TEXT("requires_fresh_paired_cook"), true); Out->SetNumberField(TEXT("saved_packages"), Apply ? 1 : 0);
    Out->SetStringField(TEXT("limitation"), TEXT("Approximate geometric receiver normal from quantized alpha-copy depth; edge/precision artifacts remain possible. Shader link alone is not visual acceptance."));
    Out->SetObjectField(TEXT("original_roots"), MasterBase->GetObjectField(TEXT("roots")));
    for (const auto& V : MasterBase->GetArrayField(TEXT("nodes")))
        if (Str(V->AsObject(), TEXT("path")) == ObjectPath(BSXPackage()) + TEXT(":MaterialExpressionComponentMask_4"))
            Out->SetObjectField(TEXT("input_before"), V->AsObject()->GetArrayField(TEXT("inputs"))[0]->AsObject());
    TSharedPtr<FJsonObject> Added = MakeShareable(new FJsonObject);
    if (Apply || Verify)
    {
        for (const TCHAR* N : BSXNames)
        { auto* E = FindObject<UMaterialExpression>(M, N); if (BSXBad((!E), TEXT("BlobShadowExperiment:L296.1"))) return 1; Added->SetObjectField(N, MRProperties(E, true)); }
        auto* Mask = BSXNode(M, TEXT("MaterialExpressionComponentMask_4"), TEXT("MaterialExpressionComponentMask"));
        Out->SetObjectField(TEXT("input_after"), MRPin(Mask->GetInput(0)));
    }
    Out->SetObjectField(TEXT("added_expressions"), Added);
    if (BSXBad((Verify && (!BSXField(Previous, Out, TEXT("added_expressions")) || !BSXField(Previous, Out, TEXT("input_after")) ||
        !BSXField(Previous, Out, TEXT("after_state_id")) || !BSXField(Previous, Out, TEXT("after_lighting_guid")))), TEXT("BlobShadowExperiment:L301.1"))) return 1;
    BSXStage(TEXT("aftermath_facts_accepted"));
    FString Text;
    if (BSXBad((!FJsonSerializer::Serialize(Out.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text))), TEXT("BlobShadowExperiment:L304.1")) || BSXBad((Text.Len() > 128 * 1024), TEXT("BlobShadowExperiment:L304.2"))) return 1;
    if (BSXBad((Apply && (!Physical(Aftermath, true) || FPaths::FileExists(Aftermath) || !FFileHelper::SaveStringToFile(Text, *Aftermath))), TEXT("BlobShadowExperiment:L305.1")))
    { Fail(TEXT("Material saved but aftermath write failed: preserve logs and do not promote.")); return 1; }
    BSXStage(TEXT("complete"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_BLOB_EXPERIMENT %s"), *Text);
    return 0;
}
