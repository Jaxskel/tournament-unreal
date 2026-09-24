// Original bounded read-only asset probe. Include after WeaponTessellationUpgrade.h.
// Uses public Engine/MaterialShared exports; no private cooking-map access.
class FWeaponShaderResource final : public FMaterialResource
{
public:
    // WSP_CF_OVERRIDES_BEGIN
    // Owned diagnostic only: no UMaterial flags or global settings change.
    bool NoStaticLighting = false;
    virtual bool IsUsedWithStaticLighting() const override
    {
        return NoStaticLighting ? false : FMaterialResource::IsUsedWithStaticLighting();
    }
    virtual bool IsPersistent() const override
    {
        // Nonpersistent maps are not saved to DDC. Engine also treats this as
        // preview priority / no component-recreate-on-completion; not runtime evidence.
        return NoStaticLighting ? false : FMaterialResource::IsPersistent();
    }
    // WSP_CF_OVERRIDES_END
    mutable int32 TranslationRequests = 0;
    virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty Property, FMaterialCompiler* Compiler,
        EShaderFrequency OverrideShaderFrequency, bool bUsePreviousFrameTime) const override
    {
        ++TranslationRequests;
        return FMaterialResource::CompilePropertyAndSetMaterialProperty(Property, Compiler, OverrideShaderFrequency, bUsePreviousFrameTime);
    }
};
struct FWeaponShaderOwner
{
    FWeaponShaderResource* Resource = new FWeaponShaderResource;
    ~FWeaponShaderOwner()
    {
        // Finish on every ordinary return, including CacheShaders failure. Never
        // destroy a resource still referenced by outstanding shader jobs.
        Resource->FinishCompilation();
        if (Resource->IsCompilationFinished()) delete Resource;
        else UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_SHADER undrained resource retained until process exit"));
    }
};
static const TCHAR* WSPOrigin(int32 TranslationRequests, bool Pending)
{
    if (TranslationRequests > 0) return TEXT("translation-observed");
    return Pending ? TEXT("no-local-translation-pending-or-shared") : TEXT("no-local-translation-complete-at-return");
}
// Checks the material/instance identity subset only. This deliberately does not
// compare ShaderTypeDependencies, ShaderPipelineTypeDependencies, or
// VertexFactoryTypeDependencies, nor call unexported shader-map-ID equality.
// CacheShaders receives the FULL Requested ID and performs its engine-owned
// lookup/compilation; this additional diagnostic check is not full-ID equality.
static bool WSPMaterialInstanceIdentitySubset(const FMaterialShaderMapId& Expected, const FMaterialShaderMapId& Actual)
{
    FWeaponRepair Compare;
    return Expected.BaseMaterialId == Actual.BaseMaterialId && Expected.QualityLevel == Actual.QualityLevel &&
        Expected.FeatureLevel == Actual.FeatureLevel && Expected.Usage == Actual.Usage &&
        Expected.ReferencedFunctions == Actual.ReferencedFunctions && Expected.ReferencedParameterCollections == Actual.ReferencedParameterCollections &&
        FMemory::Memcmp(Expected.BasePropertyOverridesHash.Hash, Actual.BasePropertyOverridesHash.Hash, sizeof(Expected.BasePropertyOverridesHash.Hash)) == 0 &&
        FMemory::Memcmp(Expected.TextureReferencesHash.Hash, Actual.TextureReferencesHash.Hash, sizeof(Expected.TextureReferencesHash.Hash)) == 0 &&
        Compare.Same(MRValue(MRStatic(Expected.ParameterSet)), MRValue(MRStatic(Actual.ParameterSet)));
}
static bool WSPQualityBranches()
{
    // Exact graph already checked by fresh eight-node Verify. These three
    // connected quality pins make native GetQualityLevelNodeUsage true for ALL
    // qualities, before optional platform overrides OR in further true values.
    auto* Oil = FindObject<UMaterialFunction>(nullptr, TEXT("/Game/HTML5Compat/Weapons/V1/MF_Oilness.MF_Oilness"));
    if (!Oil) return false;
    FWeaponRepair Inspector;
    auto* Switch = Inspector.Node(Oil, TEXT("MaterialExpressionQualitySwitch_0"), TEXT("MaterialExpressionQualitySwitch"));
    if (!Switch || EMaterialQualityLevel::Num != 3) return false;
    const auto Inputs = Switch->GetInputs();
    if (Inputs.Num() != 4 || !Inputs[0] || !Inputs[0]->IsConnected()) return false;
    const TCHAR* Names[] = {TEXT("Low"), TEXT("High"), TEXT("Medium")};
    for (int32 I = 0; I < 3; ++I)
        if (!Inputs[I + 1] || !Inputs[I + 1]->IsConnected() || Switch->GetInputName(I + 1) != Names[I]) return false;
    return true;
}
static int32 WeaponShaderProbe(const FString& Params)
{
    // WSP_CF_FLAG_BEGIN
    const bool Counterfactual = FParse::Param(*Params, TEXT("WeaponShaderNoStaticLighting"));
    // WSP_CF_FLAG_END
    // WSP_ONE_FLAG_BEGIN
    const bool DiagnosticOne = Counterfactual || FParse::Param(*Params, TEXT("WeaponShaderEnforcer1PHigh"));
    // WSP_ONE_FLAG_END
    // Requires the same independently pinned aftermath and generation as fresh
    // Verify. This mode cannot Apply and cannot operate on a guessed/current root.
    if (!GIsEditor || !IsInGameThread() || !FApp::CanEverRender() || WeaponTessellationUpgrade(Params, true) != 0)
        return WFRStop(TEXT("shader-verified-generation"));
    FString ProofPath;
    if (!FParse::Value(*Params, TEXT("WeaponCurrentProof="), ProofPath)) return WFRStop(TEXT("shader-proof-path"));
    FWeaponTessProof Proof;
    if (!Proof.Read(ProofPath) || !WSPQualityBranches()) return WFRStop(TEXT("shader-quality-proof"));
    const FString MasterHash = HashFile(Proof.CurrentFiles.FindChecked(WTUMaster()));
    if (!Proof.Check(MasterHash)) return WFRStop(TEXT("shader-before-bytes"));
    auto* Master = FindObject<UMaterial>(nullptr, *ObjectPath(WTUMaster()));
    if (!Master) return WFRStop(TEXT("shader-master"));
    const TCHAR* Targets[] = {
        TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/M_Enforcer_Gun"),
        TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/Materials_thirdPerson/M_Enforcer_Gun_3rdPerson_Inst")
    };
    bool Success = true; int32 Resources = 0;
    for (const TCHAR* Target : Targets)
    {
        // WSP_ONE_TARGET_BEGIN
        if (DiagnosticOne && Target != Targets[0]) continue;
        // WSP_ONE_TARGET_END
        auto* MI = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(Target));
        if (!MI || MI->GetMaterial() != Master) return WFRStop(TEXT("shader-instance"), Target);
        FStaticParameterSet Effective; MI->GetStaticParameterValues(Effective);
        for (int32 Q = 0; Q < EMaterialQualityLevel::Num; ++Q)
        {
            // WSP_ONE_QUALITY_BEGIN
            if (DiagnosticOne && Q != EMaterialQualityLevel::High) continue;
            // WSP_ONE_QUALITY_END
            FWeaponShaderOwner Owner;
            auto* Resource = Owner.Resource;
            const auto Quality = static_cast<EMaterialQualityLevel::Type>(Q);
            Resource->SetMaterial(Master, Quality, true, ERHIFeatureLevel::ES2, MI);
            // WSP_CF_ADMISSION_BEGIN
            if (Counterfactual && (!Master->bUsedWithStaticLighting || Resource->IsSpecialEngineMaterial()))
                return WFRStop(TEXT("shader-counterfactual-admission"), Target);
            FMaterialShaderMapId OrdinaryRequested;
            if (Counterfactual) Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, OrdinaryRequested);
            Resource->NoStaticLighting = Counterfactual;
            // Set BEFORE virtual GetShaderMapId: dependencies are re-enumerated
            // through this resource's ShouldCache policy, never copied from a normal ID.
            // WSP_CF_ADMISSION_END
            FMaterialShaderMapId Requested;
            // Virtual dispatch includes MI composited static parameters and base
            // property overrides (pinned Material.cpp FMaterialResource override).
            Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
            // WSP_CF_ID_CHECK_BEGIN
            // A strict type-count reduction proves the counterfactual identity
            // differs: dependency array lengths participate in the engine key.
            if (Counterfactual &&
                (Requested.ShaderTypeDependencies.Num() >= OrdinaryRequested.ShaderTypeDependencies.Num() ||
                 Requested.ShaderPipelineTypeDependencies.Num() > OrdinaryRequested.ShaderPipelineTypeDependencies.Num() ||
                 Requested.VertexFactoryTypeDependencies.Num() > OrdinaryRequested.VertexFactoryTypeDependencies.Num()))
                return WFRStop(TEXT("shader-counterfactual-no-dependency-reduction"), Target);
            // WSP_CF_ID_CHECK_END
            FWeaponRepair Compare;
            if (Requested.BaseMaterialId != Master->StateId || Requested.QualityLevel != Quality || Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
                !Compare.Same(MRValue(MRStatic(Requested.ParameterSet)), MRValue(MRStatic(Effective)))) return WFRStop(TEXT("shader-requested-identity"), Target);
            // WSP_CF_BEGIN_LOG_BEGIN
            if (Counterfactual)
            {
                UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SHADER_COUNTERFACTUAL begin selector=enforcer1p-high material=%s quality=%d platform=%d master=%s staticLighting=0 persistent=0 previewPriorityPolicy=1 componentRecreatePolicy=0"),
                    Target, Q, static_cast<int32>(SP_OPENGL_ES2_WEBGL), *MasterHash);
            }
            else
            {
            // WSP_CF_BEGIN_LOG_END
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SHADER begin material=%s quality=%d platform=%d master=%s"),
                Target, Q, static_cast<int32>(SP_OPENGL_ES2_WEBGL), *MasterHash);
            // WSP_CF_BEGIN_LOG_CLOSE_BEGIN
            }
            // WSP_CF_BEGIN_LOG_CLOSE_END
            const bool Cached = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
            const bool Pending = !Resource->IsCompilationFinished();
            const int32 TranslationRequests = Resource->TranslationRequests;
            Resource->FinishCompilation();
            if (!Resource->IsCompilationFinished()) return WFRStop(TEXT("shader-undrained"), Target);
            auto* Map = Resource->GetGameThreadShaderMap();
            const auto& Errors = Resource->GetCompileErrors();
            const bool ValidMap = Cached && Resource->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() &&
                Map->CompiledSuccessfully() && Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL && WSPMaterialInstanceIdentitySubset(Requested, Map->GetShaderMapId()) &&
                Resource->GetFeatureLevel() == ERHIFeatureLevel::ES2 && Resource->GetQualityLevel() == Quality && Errors.Num() == 0;
            const int32 Samplers = ValidMap ? Resource->GetSamplerUsage() : -1;
            const bool Valid = ValidMap && Samplers >= 0 && Samplers <= 16;
            Success = Valid && Success; ++Resources;
            // WSP_CF_RESULT_LOG_BEGIN
            if (Counterfactual)
            {
                UE_LOG(LogUT4Html5Compat, Display,
                    TEXT("COMPAT_WEAPON_SHADER_COUNTERFACTUAL result material=%s quality=%d valid=%d samplers=%d translationRequests=%d pendingAfterCache=%d origin=%s identityCheck=material-instance-subset newShaderJobs=unknown errors=%d"),
                    Target, Q, Valid ? 1 : 0, Samplers, TranslationRequests, Pending ? 1 : 0, WSPOrigin(TranslationRequests, Pending), Errors.Num());
            }
            else
            {
            // WSP_CF_RESULT_LOG_END
            UE_LOG(LogUT4Html5Compat, Display,
                TEXT("COMPAT_WEAPON_SHADER result material=%s quality=%d valid=%d samplers=%d translationRequests=%d pendingAfterCache=%d origin=%s identityCheck=material-instance-subset newShaderJobs=unknown errors=%d"),
                Target, Q, Valid ? 1 : 0, Samplers, TranslationRequests, Pending ? 1 : 0, WSPOrigin(TranslationRequests, Pending), Errors.Num());
            // WSP_CF_RESULT_LOG_CLOSE_BEGIN
            }
            // WSP_CF_RESULT_LOG_CLOSE_END
            for (int32 I = 0; I < FMath::Min(Errors.Num(), 8); ++I)
                // WSP_CF_ERROR_LOG_BEGIN
                if (Counterfactual)
                {
                    UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_WEAPON_SHADER_COUNTERFACTUAL error quality=%d index=%d text=%s"), Q, I, *WFRContext(Errors[I]));
                }
                else
                {
                // WSP_CF_ERROR_LOG_END
                UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_WEAPON_SHADER error quality=%d index=%d text=%s"), Q, I, *WFRContext(Errors[I]));
                // WSP_CF_ERROR_LOG_CLOSE_BEGIN
                }
                // WSP_CF_ERROR_LOG_CLOSE_END
            // A complete-at-return success with zero local translation reused an
            // available map; this does not identify DDC versus in-memory origin.
        }
    }
    if (!Proof.Check(MasterHash)) return WFRStop(TEXT("shader-after-bytes"));
    // WSP_CF_COMPLETION_BEGIN
    if (Counterfactual)
    {
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SHADER_COUNTERFACTUAL complete selector=enforcer1p-high staticLighting=0 persistent=0 resources=%d valid=%d assetsSaved=0 ordinaryAcceptance=0"), Resources, Success ? 1 : 0);
        return Success && Resources == 1 ? 0 : 1;
    }
    // WSP_CF_COMPLETION_END
    // WSP_ONE_COMPLETION_BEGIN
    if (DiagnosticOne)
    {
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SHADER_DIAGNOSTIC complete selector=enforcer1p-high resources=%d valid=%d assetsSaved=0"), Resources, Success ? 1 : 0);
        return Success && Resources == 1 ? 0 : 1;
    }
    // WSP_ONE_COMPLETION_END
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SHADER complete resources=%d valid=%d assetsSaved=0"), Resources, Success ? 1 : 0);
    return Success && Resources == 6 ? 0 : 1;
}
