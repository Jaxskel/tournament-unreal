// Read-only counterfactual: exact repaired 18 MICs x three qualities.
// Include after WeaponShaderProbe.h. No asset flags, global settings or saves.
static int32 WeaponShaderBatchProbe(const FString& Params)
{
    if (!GIsEditor || !IsInGameThread() || !FApp::CanEverRender() || WeaponTessellationUpgrade(Params, true) != 0)
        return WFRStop(TEXT("shader-batch-verified-generation"));
    FString ProofPath;
    if (!FParse::Value(*Params, TEXT("WeaponCurrentProof="), ProofPath)) return WFRStop(TEXT("shader-batch-proof-path"));
    FWeaponTessProof Proof;
    if (!Proof.Read(ProofPath) || !WSPQualityBranches()) return WFRStop(TEXT("shader-batch-quality-proof"));
    const FString MasterHash = HashFile(Proof.CurrentFiles.FindChecked(WTUMaster()));
    if (!Proof.Check(MasterHash)) return WFRStop(TEXT("shader-batch-before-bytes"));
    auto* Master = FindObject<UMaterial>(nullptr, *ObjectPath(WTUMaster()));
    if (!Master || !Master->bUsedWithStaticLighting) return WFRStop(TEXT("shader-batch-master"));
    TArray<FString> Targets = WRScope();
    if (Targets.Remove(WRMaster()) != 1 || Targets.Num() != 18 || EMaterialQualityLevel::Num != 3)
        return WFRStop(TEXT("shader-batch-fixed-scope"));
    TSet<FString> Seen;
    for (const FString& Target : Targets)
    {
        auto* MI = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(Target));
        if (Seen.Contains(Target) || !MI || MI->GetMaterial() != Master) return WFRStop(TEXT("shader-batch-instance"), Target);
        Seen.Add(Target);
    }
    bool Success = true; int32 Resources = 0;
    for (const FString& Target : Targets)
    {
        auto* MI = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(Target));
        if (!MI || MI->GetMaterial() != Master) return WFRStop(TEXT("shader-batch-instance-recheck"), Target);
        FStaticParameterSet Effective; MI->GetStaticParameterValues(Effective);
        for (int32 Q = 0; Q < EMaterialQualityLevel::Num; ++Q)
        {
            FWeaponShaderOwner Owner;
            auto* Resource = Owner.Resource;
            const auto Quality = static_cast<EMaterialQualityLevel::Type>(Q);
            Resource->SetMaterial(Master, Quality, true, ERHIFeatureLevel::ES2, MI);
            if (Resource->IsSpecialEngineMaterial()) return WFRStop(TEXT("shader-batch-special-material"), Target);
            FMaterialShaderMapId OrdinaryRequested;
            Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, OrdinaryRequested);
            Resource->NoStaticLighting = true;
            // Regenerate dependencies through the owned override. Never reuse or
            // edit an ordinary ID; persistence=false also changes preview priority.
            FMaterialShaderMapId Requested;
            Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
            if (Requested.ShaderTypeDependencies.Num() >= OrdinaryRequested.ShaderTypeDependencies.Num() ||
                Requested.ShaderPipelineTypeDependencies.Num() > OrdinaryRequested.ShaderPipelineTypeDependencies.Num() ||
                Requested.VertexFactoryTypeDependencies.Num() > OrdinaryRequested.VertexFactoryTypeDependencies.Num())
                return WFRStop(TEXT("shader-batch-no-dependency-reduction"), Target);
            FWeaponRepair Compare;
            if (Requested.BaseMaterialId != Master->StateId || Requested.QualityLevel != Quality || Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
                !Compare.Same(MRValue(MRStatic(Requested.ParameterSet)), MRValue(MRStatic(Effective))))
                return WFRStop(TEXT("shader-batch-requested-identity"), Target);
            UE_LOG(LogUT4Html5Compat, Display,
                TEXT("COMPAT_WEAPON_SHADER_BATCH begin material=%s quality=%d platform=%d master=%s staticLighting=0 persistent=0 previewPriorityPolicy=1 componentRecreatePolicy=0"),
                *Target, Q, static_cast<int32>(SP_OPENGL_ES2_WEBGL), *MasterHash);
            const bool Cached = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
            const bool Pending = !Resource->IsCompilationFinished();
            const int32 TranslationRequests = Resource->TranslationRequests;
            Resource->FinishCompilation();
            if (!Resource->IsCompilationFinished()) return WFRStop(TEXT("shader-batch-undrained"), Target);
            auto* Map = Resource->GetGameThreadShaderMap();
            const auto& Errors = Resource->GetCompileErrors();
            const bool ValidMap = Cached && Resource->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() &&
                Map->CompiledSuccessfully() && Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL &&
                WSPMaterialInstanceIdentitySubset(Requested, Map->GetShaderMapId()) &&
                Resource->GetFeatureLevel() == ERHIFeatureLevel::ES2 && Resource->GetQualityLevel() == Quality && Errors.Num() == 0;
            const int32 Samplers = ValidMap ? Resource->GetSamplerUsage() : -1;
            const bool Valid = ValidMap && Samplers >= 0 && Samplers <= 16;
            Success = Valid && Success; ++Resources;
            UE_LOG(LogUT4Html5Compat, Display,
                TEXT("COMPAT_WEAPON_SHADER_BATCH result material=%s quality=%d valid=%d samplers=%d translationRequests=%d pendingAfterCache=%d origin=%s identityCheck=material-instance-subset newShaderJobs=unknown errors=%d"),
                *Target, Q, Valid ? 1 : 0, Samplers, TranslationRequests, Pending ? 1 : 0, WSPOrigin(TranslationRequests, Pending), Errors.Num());
            for (int32 I = 0; I < FMath::Min(Errors.Num(), 8); ++I)
            {
                UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_WEAPON_SHADER_BATCH error material=%s quality=%d index=%d text=%s"),
                    *Target, Q, I, *WFRContext(Errors[I]));
            }
        }
    }
    if (!Proof.Check(MasterHash)) return WFRStop(TEXT("shader-batch-after-bytes"));
    UE_LOG(LogUT4Html5Compat, Display,
        TEXT("COMPAT_WEAPON_SHADER_BATCH complete materials=18 qualities=3 resources=%d valid=%d staticLighting=0 persistent=0 assetsSaved=0 ordinaryAcceptance=0"),
        Resources, Success ? 1 : 0);
    return Success && Resources == 54 ? 0 : 1;
}
