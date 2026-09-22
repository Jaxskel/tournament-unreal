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
    return X && Y && BSXSame(*X, *Y, Delta);
}
static UMaterialExpression* BSXNode(UMaterial* M, const TCHAR* Name, const TCHAR* Class)
{
    UClass* ExactClass = FindObject<UClass>(nullptr, *(FString(TEXT("/Script/Engine.")) + Class));
    if (!ExactClass || !ExactClass->IsChildOf(UMaterialExpression::StaticClass())) return nullptr;
    UMaterialExpression* Found = nullptr;
    for (auto* E : M->Expressions) if (E && E->GetName() == Name)
    { if (Found || E->GetOuter() != M || E->GetClass() != ExactClass) return nullptr; Found = E; }
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
    if (FindObject<UObject>(M, Name)) return nullptr;
    T* E = NewObject<T>(M, FName(Name));
    E->Material = M; E->MaterialExpressionGuid = FGuid::NewGuid(); M->Expressions.Add(E); return E;
}
// These two native classes declare NO_API StaticClass/constructors in this
// editor. Instantiate through the exported base and an exact loaded Engine
// UClass; never call their typed NewObject/Cast/StaticClass entry points.
static UMaterialExpression* BSXAddReflected(UMaterial* M, const TCHAR* Name, const TCHAR* ClassName)
{
    if (FindObject<UObject>(M, Name)) return nullptr;
    UClass* ExactClass = FindObject<UClass>(nullptr, *(FString(TEXT("/Script/Engine.")) + ClassName));
    if (!ExactClass || !ExactClass->IsChildOf(UMaterialExpression::StaticClass())) return nullptr;
    UMaterialExpression* E = NewObject<UMaterialExpression>(M, ExactClass, FName(Name));
    if (!E || E->GetClass() != ExactClass) return nullptr;
    E->Material = M; E->MaterialExpressionGuid = FGuid::NewGuid(); M->Expressions.Add(E); return E;
}
static bool BSXShape(UMaterial* M, bool Delta)
{
    auto* Old = BSXNode(M, TEXT("MaterialExpressionSceneTexture_3"), TEXT("MaterialExpressionSceneTexture"));
    auto* Mask = BSXNode(M, TEXT("MaterialExpressionComponentMask_4"), TEXT("MaterialExpressionComponentMask"));
    if (!Old || !Mask || !Mask->GetInput(0) || Str(MRProperties(Old, true), TEXT("SceneTextureId")) != TEXT("PPI_WorldNormal")) return false;
    if (!Delta) return BSXPin(*Mask->GetInput(0), Old, true);
    auto* Switch = Cast<UMaterialExpressionFeatureLevelSwitch>(BSXNode(M, BSXNames[0], TEXT("MaterialExpressionFeatureLevelSwitch")));
    auto* Custom = Cast<UMaterialExpressionCustom>(BSXNode(M, BSXNames[1], TEXT("MaterialExpressionCustom")));
    auto* Depth = static_cast<UMaterialExpressionSceneDepth*>(BSXNode(M, BSXNames[2], TEXT("MaterialExpressionSceneDepth")));
    auto* Camera = BSXNode(M, BSXNames[3], TEXT("MaterialExpressionCameraVectorWS"));
    if (!Switch || !Custom || !Depth || !Camera || !M->bUseFullPrecision ||
        !BSXPin(*Mask->GetInput(0), Switch, true) || !BSXPin(Switch->Default, Old, true) ||
        !BSXPin(Switch->Inputs[ERHIFeatureLevel::ES2], Custom) || Custom->Code != BSXCode ||
        Custom->OutputType != CMOT_Float4 || Custom->Inputs.Num() != 2 ||
        Custom->Inputs[0].InputName != TEXT("ReceiverDepth") || !BSXPin(Custom->Inputs[0].Input, Depth) ||
        Custom->Inputs[1].InputName != TEXT("CameraDirection") || !BSXPin(Custom->Inputs[1].Input, Camera) ||
        Depth->InputMode != EMaterialSceneAttributeInputMode::Coordinates || Depth->Input.Expression ||
        Depth->Coordinates_DEPRECATED.Expression || Depth->ConstInput != FVector2D::ZeroVector) return false;
    for (int32 I = 1; I < ERHIFeatureLevel::Num; ++I) if (Switch->Inputs[I].Expression) return false;
    TSet<FGuid> IDs;
    UMaterialExpression* NewNodes[] = {Switch, Custom, Depth, Camera};
    for (auto* E : NewNodes)
    { if (!E->MaterialExpressionGuid.IsValid() || IDs.Contains(E->MaterialExpressionGuid)) return false; IDs.Add(E->MaterialExpressionGuid); }
    for (auto* E : M->Expressions)
        if (E != Switch && E != Custom && E != Depth && E != Camera && IDs.Contains(E->MaterialExpressionGuid)) return false;
    return true;
}
static bool BSXEdit(UMaterial* M)
{
    if (!BSXShape(M, false)) return false;
    for (const TCHAR* N : BSXNames) if (FindObject<UObject>(M, N)) return false;
    auto* Mask = BSXNode(M, TEXT("MaterialExpressionComponentMask_4"), TEXT("MaterialExpressionComponentMask"));
    const FExpressionInput Original = *Mask->GetInput(0);
    auto* Switch = BSXAdd<UMaterialExpressionFeatureLevelSwitch>(M, BSXNames[0]);
    auto* Custom = BSXAdd<UMaterialExpressionCustom>(M, BSXNames[1]);
    auto* Depth = static_cast<UMaterialExpressionSceneDepth*>(BSXAddReflected(M, BSXNames[2], TEXT("MaterialExpressionSceneDepth")));
    auto* Camera = BSXAddReflected(M, BSXNames[3], TEXT("MaterialExpressionCameraVectorWS"));
    if (!Switch || !Custom || !Depth || !Camera) return false;
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
    return BSXShape(M, true);
}
static bool BSXFacts(UMaterialInterface* Asset, const TSharedPtr<FJsonObject>& Expected, IAssetRegistry& Registry, bool Delta,
    TSharedPtr<FJsonObject>& Actual)
{
    if (!MRDescribe(Asset, Registry, Actual)) return false;
    for (const TCHAR* K : {TEXT("material"), TEXT("class"), TEXT("base_material"), TEXT("blend"), TEXT("shading"),
        TEXT("two_sided"), TEXT("opacity_mask_clip"), TEXT("parent_chain"), TEXT("texture_parameters"),
        TEXT("scalar_parameters"), TEXT("vector_parameters"), TEXT("base_graph_textures_including_functions"),
        TEXT("has_null_texture_expression"), TEXT("roots")})
        if (!BSXField(Expected, Actual, K)) return Fail(TEXT("Blob experiment baseline mismatch: ") + K);
    for (const TCHAR* K : {TEXT("static_overrides"), TEXT("static_effective")})
        if (Expected->HasField(K) && !BSXField(Expected, Actual, K)) return false;
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
            if (!A.IsValidIndex(OldIndex) || !BSXSame(A[OldIndex++], V, true)) return Fail(TEXT("Blob experiment original graph drift."));
        }
        if (Added != 4 || OldIndex != A.Num()) return false;
        if (Str(Expected->GetObjectField(TEXT("properties")), TEXT("StateId")) ==
            Str(Actual->GetObjectField(TEXT("properties")), TEXT("StateId"))) return Fail(TEXT("Blob experiment StateId did not change."));
    }
    else if (!BSXField(Expected, Actual, TEXT("nodes"))) return false;
    return BSXSame(MRValue(X), MRValue(Y), false);
}
static bool BSXDisk(const TSharedPtr<FJsonObject>& Pins, bool SkipTarget)
{
    TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
    for (const auto& KV : Pins->Values)
    {
        if (SkipTarget && KV.Key == BSXPackage()) continue;
        if (!MRHashPackage(KV.Key, Hashes) || !Str(Hashes, *KV.Key).Equals(KV.Value->AsString(), ESearchCase::IgnoreCase))
            return Fail(TEXT("Blob experiment package bytes changed: ") + KV.Key);
    }
    return true;
}
static int32 BlobShadowExperiment(const FString& Params)
{
    FString Action, SpecPath, BaselinePath, Receipt, SourceFile, Aftermath, Forbidden;
    if (!GIsEditor || !IsInGameThread() ||
        !FParse::Value(*Params, TEXT("BlobAction="), Action) ||
        !FParse::Value(*Params, TEXT("BlobExperimentSpec="), SpecPath) ||
        !FParse::Value(*Params, TEXT("BlobBaseline="), BaselinePath) ||
        !FParse::Value(*Params, TEXT("Receipt="), Receipt) ||
        !FParse::Value(*Params, TEXT("BlobOriginalFile="), SourceFile) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering"))) return 1;
    const bool Apply = Action == TEXT("Apply"), Verify = Action == TEXT("Verify"), Report = Action == TEXT("Report");
    if ((!Apply && !Verify && !Report) || (Apply && (!FApp::CanEverRender() ||
        !FParse::Param(*Params, TEXT("AcknowledgeApproximateBlobNormal")))))
    { Fail(TEXT("Explicit diagnostic action required; Apply needs rendering and AcknowledgeApproximateBlobNormal.")); return 1; }
    if ((Apply || Verify) && !FParse::Value(*Params, TEXT("BlobAftermath="), Aftermath)) return 1;
    TSharedPtr<FJsonObject> Spec, Baseline;
    if (!Physical(SpecPath, false) || !Physical(BaselinePath, false) ||
        !HashFile(SpecPath).Equals(BSXSpecSHA1, ESearchCase::IgnoreCase) || !ReadJson(SpecPath, Spec) ||
        !HashFile(BaselinePath).Equals(Str(Spec, TEXT("baseline_sha1")), ESearchCase::IgnoreCase) ||
        !ReadJson(BaselinePath, Baseline) || Str(Baseline, TEXT("schema")) != TEXT("ut4-blob-experiment-baseline-v1")) return 1;
    TSet<FString> Saves; Saves.Add(BSXPackage().ToLower()); FSavePolicy Policy;
    if (!Policy.Read(Receipt, SpecPath, Saves) || !RejectConfiguredRobotRedirects()) return 1;
    const FString Target = Policy.Files.FindChecked(BSXPackage().ToLower()); SourceFile = Full(SourceFile);
    const auto Pins = Spec->GetObjectField(TEXT("original_sha1"));
    const FString PristineHash = Str(Pins, *BSXPackage());
    if (!Within(SourceFile, Policy.OriginalRoot) || Within(SourceFile, Policy.ContentRoot) ||
        !SourceFile.EndsWith(TEXT("/Content/") + BSXPackage().Mid(6) + TEXT(".uasset"), ESearchCase::IgnoreCase) ||
        !Physical(SourceFile, false) || !HashFile(SourceFile).Equals(PristineHash, ESearchCase::IgnoreCase)) return 1;
    if (Apply || Verify)
    {
        Aftermath = Full(Aftermath);
        if (Within(Aftermath, Policy.ContentRoot) || Within(Aftermath, Policy.OriginalRoot) ||
            !Physical(Aftermath, Apply) || (Apply && FPaths::FileExists(Aftermath))) return 1;
    }
    TSharedPtr<FJsonObject> Previous;
    if (Verify && (!ReadJson(Aftermath, Previous) || Str(Previous, TEXT("schema")) != TEXT("ut4-blob-experiment-aftermath-v1") ||
        Str(Previous, TEXT("spec_sha1")) != HashFile(SpecPath) || Str(Previous, TEXT("baseline_sha1")) != HashFile(BaselinePath) ||
        Str(Previous, TEXT("target_sha1")) != HashFile(Target) || Str(Previous, TEXT("target_file")) != Target)) return 1;
    if (!BSXDisk(Pins, Verify)) return 1;
    for (const FString& P : {BSXPackage(), BSXInverse()})
        if (FindPackage(nullptr, *P)) { Fail(TEXT("Blob experiment requires a fresh process: ") + P); return 1; }
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true); if (Registry.IsLoadingAssets()) return 1;
    auto* M = LoadObject<UMaterial>(nullptr, *ObjectPath(BSXPackage()));
    auto* MI = LoadObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(BSXInverse()));
    const auto& Materials = Baseline->GetArrayField(TEXT("materials"));
    if (!M || !MI || Materials.Num() != 2 || MI->Parent != M) return 1;
    TSharedPtr<FJsonObject> MasterBase, InverseBase;
    for (const auto& V : Materials)
    {
        auto J = V->AsObject();
        if (Str(J, TEXT("material")) == ObjectPath(BSXPackage())) MasterBase = J;
        if (Str(J, TEXT("material")) == ObjectPath(BSXInverse())) InverseBase = J;
    }
    const bool DirtyAfterLoad = M->GetOutermost()->IsDirty();
    TSharedPtr<FJsonObject> Facts, InverseFacts;
    if (!MasterBase.IsValid() || !InverseBase.IsValid() || !BSXShape(M, Verify) ||
        !BSXFacts(M, MasterBase, Registry, Verify, Facts) || !BSXFacts(MI, InverseBase, Registry, false, InverseFacts)) return 1;
    // Known load-dirty is accepted ONLY in this new operation after exact native
    // graph/properties/parameter and pristine source+target byte comparisons.
    // Existing report/repair policy is untouched; no dirty flag is ever cleared.
    const FString BeforeState = Str(MasterBase->GetObjectField(TEXT("properties")), TEXT("StateId"));
    if (Apply)
    {
        {
            FMaterialUpdateContext Update; Update.AddMaterial(M); M->PreEditChange(nullptr);
            if (!BSXEdit(M)) return 1;
            M->PostEditChange();
        }
        if (!BSXShape(M, true) || !BSXFacts(M, MasterBase, Registry, true, Facts) ||
            !BSXFacts(MI, InverseBase, Registry, false, InverseFacts) || !BSXDisk(Pins, false) ||
            !HashFile(SourceFile).Equals(PristineHash, ESearchCase::IgnoreCase) || !Policy.Check(BSXPackage())) return 1;
        if (!Policy.Save(M)) return 1;
    }
    if (!BSXDisk(Pins, Apply || Verify) || !HashFile(SourceFile).Equals(PristineHash, ESearchCase::IgnoreCase)) return 1;
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
        { auto* E = FindObject<UMaterialExpression>(M, N); if (!E) return 1; Added->SetObjectField(N, MRProperties(E, true)); }
        auto* Mask = BSXNode(M, TEXT("MaterialExpressionComponentMask_4"), TEXT("MaterialExpressionComponentMask"));
        Out->SetObjectField(TEXT("input_after"), MRPin(Mask->GetInput(0)));
    }
    Out->SetObjectField(TEXT("added_expressions"), Added);
    if (Verify && (!BSXField(Previous, Out, TEXT("added_expressions")) || !BSXField(Previous, Out, TEXT("input_after")) ||
        !BSXField(Previous, Out, TEXT("after_state_id")) || !BSXField(Previous, Out, TEXT("after_lighting_guid")))) return 1;
    FString Text;
    if (!FJsonSerializer::Serialize(Out.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text)) || Text.Len() > 128 * 1024) return 1;
    if (Apply && (!Physical(Aftermath, true) || FPaths::FileExists(Aftermath) || !FFileHelper::SaveStringToFile(Text, *Aftermath)))
    { Fail(TEXT("Material saved but aftermath write failed: preserve logs and do not promote.")); return 1; }
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_BLOB_EXPERIMENT %s"), *Text);
    return 0;
}
