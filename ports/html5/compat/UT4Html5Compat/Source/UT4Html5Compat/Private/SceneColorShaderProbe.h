// Fixed, read-only SceneColor shader diagnostic. Include after WeaponShaderProbe.h.
// Compiles only the original Bio glass material and its pinned 1P instance; this
// is shader-cache evidence, not browser render or cook acceptance.
static const TCHAR* SCSHMaterialPackages[] = {
    TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/Bio_HazyGlass"),
    TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_HazyGlass_1p")
};
static const TCHAR* SCSHMaterialSHA1[] = {
    TEXT("FE39078269E9520697493A421D90BC9999FCB8BC"),
    TEXT("1E4A99654A0694F3755F7937DA5175FDE28BCF87")
};
static const TCHAR* SCSHQualityNames[] = { TEXT("Low"), TEXT("High"), TEXT("Medium") };

static bool SCSHMapAccepted(bool CacheReturned, bool CompilationFinished, bool HasValidMap,
    bool MapFinalized, bool CompiledSuccessfully, bool PlatformMatches, bool QualityMatches,
    bool FeatureLevelMatches, bool IdentitySubsetMatches, int32 ErrorCount, int32 Samplers)
{
    return CacheReturned && CompilationFinished && HasValidMap && MapFinalized && CompiledSuccessfully &&
        PlatformMatches && QualityMatches && FeatureLevelMatches && IdentitySubsetMatches &&
        ErrorCount == 0 && Samplers >= 0 && Samplers <= 16;
}

// The selected package may be a junction to this one exact original-content
// file. Admission still requires handle-resolved mapping, physical original,
// and both byte pins; this does not authorize arbitrary redirected content.
static bool SCSHSelectedAccepted(bool Inspected, bool ExactOriginalTarget,
    bool OriginalPhysical, bool OriginalHashMatches, bool SelectedHashMatches)
{
    return Inspected && ExactOriginalTarget && OriginalPhysical && OriginalHashMatches && SelectedHashMatches;
}

struct FSCSHFilePin
{
    FString Package, Selected, Original, SHA1;
};

struct FSCSHFilePins
{
    FString OriginalContent;
    FSCSHFilePin Rows[2];

    bool CheckSelected(const FSCSHFilePin& Row) const
    {
        FWURRoot Mapping;
        Mapping.Logical = Full(FPaths::GameContentDir());
        Mapping.Target = OriginalContent;
        Mapping.Role = TEXT("scene-color-exact-original-content");
        FWURFile Selected;
        const bool Inspected = FWURFile::Inspect(Row.Selected, false, Selected, &Mapping);
        const bool OriginalPhysical = Physical(Row.Original, false);
        const bool OriginalHashMatches = HashFile(Row.Original).Equals(Row.SHA1, ESearchCase::IgnoreCase);
        const bool ExactOriginalTarget = Inspected && Selected.Target.Equals(Row.Original, ESearchCase::IgnoreCase);
        const bool SelectedHashMatches = Inspected && Selected.SHA1.Equals(Row.SHA1, ESearchCase::IgnoreCase);
        return SCSHSelectedAccepted(Inspected, ExactOriginalTarget, OriginalPhysical,
            OriginalHashMatches, SelectedHashMatches);
    }

    bool Read(const FString& OriginalContentPath)
    {
        OriginalContent = Full(OriginalContentPath);
        if (OriginalContent.IsEmpty() || !Physical(OriginalContent, false) ||
            Within(OriginalContent, Full(FPaths::GameDir()))) return false;
        for (int32 I = 0; I < 2; ++I)
        {
            FSCSHFilePin& Row = Rows[I];
            Row.Package = SCSHMaterialPackages[I];
            Row.SHA1 = SCSHMaterialSHA1[I];
            const FString Relative = FString(Row.Package).Mid(6) + TEXT(".uasset");
            Row.Selected = Full(FPackageName::LongPackageNameToFilename(Row.Package, TEXT(".uasset")));
            const FString ExpectedSelected = Full(FPaths::GameContentDir() / Relative);
            Row.Original = Full(FPaths::Combine(OriginalContent, Relative));
            if (!Row.Selected.Equals(ExpectedSelected, ESearchCase::IgnoreCase) ||
                !Physical(Row.Original, false) || !CheckSelected(Row)) return false;
        }
        return true;
    }

    bool Check() const
    {
        for (const FSCSHFilePin& Row : Rows)
            if (!Physical(Row.Original, false) || !CheckSelected(Row)) return false;
        return true;
    }
};

static int32 SceneColorShaderProbe(const FString& Params)
{
    FString Forbidden;
    if (!GIsEditor || !IsInGameThread() || !FApp::CanEverRender() ||
        FParse::Param(*Params, TEXT("NoDependsGathering")) ||
        FParse::Param(*Params, TEXT("Apply")) || FParse::Param(*Params, TEXT("Write")) ||
        FParse::Param(*Params, TEXT("Save")) || FParse::Param(*Params, TEXT("SceneColorShaderApply")) ||
        FParse::Param(*Params, TEXT("Manifest")) || FParse::Param(*Params, TEXT("Receipt")) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden))
        return WFRStop(TEXT("scene-color-shader-readonly-admission"));

    FString OriginalContent;
    if (!FParse::Value(*Params, TEXT("SceneColorOriginalContent="), OriginalContent))
        return WFRStop(TEXT("scene-color-shader-original-content-required"));
    FSCSHFilePins Pins;
    if (!Pins.Read(OriginalContent) || !Pins.Check()) return WFRStop(TEXT("scene-color-shader-before-pins"));

    // Load only the two fixed selected packages. OriginalContent is used solely
    // for byte comparison; original packages are never mounted or loaded.
    UPackage* BasePackage = FindPackage(nullptr, SCSHMaterialPackages[0]);
    if (!BasePackage) BasePackage = LoadPackage(nullptr, SCSHMaterialPackages[0], LOAD_None);
    UPackage* InstancePackage = FindPackage(nullptr, SCSHMaterialPackages[1]);
    if (!InstancePackage) InstancePackage = LoadPackage(nullptr, SCSHMaterialPackages[1], LOAD_None);
    UObject* BaseObject = BasePackage ? FindObject<UObject>(BasePackage, TEXT("Bio_HazyGlass")) : nullptr;
    UObject* InstanceObject = InstancePackage ? FindObject<UObject>(InstancePackage, TEXT("BIO_HazyGlass_1p")) : nullptr;
    UMaterial* Base = Cast<UMaterial>(BaseObject);
    UMaterialInstanceConstant* Instance = Cast<UMaterialInstanceConstant>(InstanceObject);
    if (!Base || Base->GetClass() != UMaterial::StaticClass() || !Instance ||
        Instance->GetClass() != UMaterialInstanceConstant::StaticClass() || Instance->Parent != Base ||
        Instance->GetMaterial() != Base || Base->MaterialDomain != MD_Surface ||
        Base->GetBlendMode() != BLEND_Translucent || !Pins.Check())
        return WFRStop(TEXT("scene-color-shader-material-identity-or-pins"));

    const bool StaticLightingBefore = Base->bUsedWithStaticLighting;
    const bool BaseDirtyBefore = Base->GetOutermost()->IsDirty();
    const bool InstanceDirtyBefore = Instance->GetOutermost()->IsDirty();
    bool AllValid = true;
    int32 Resources = 0, ValidResources = 0;
    UE_LOG(LogUT4Html5Compat, Display,
        TEXT("COMPAT_SCENE_COLOR_SHADER begin base=%s instance=%s platform=%d featureLevel=%d qualities=3 originalContent=%s baseSha1=%s instanceSha1=%s staticLighting=%d diagnosticOnly=1"),
        SCSHMaterialPackages[0], SCSHMaterialPackages[1], static_cast<int32>(SP_OPENGL_ES2_WEBGL),
        static_cast<int32>(ERHIFeatureLevel::ES2), *Pins.OriginalContent, SCSHMaterialSHA1[0],
        SCSHMaterialSHA1[1], StaticLightingBefore ? 1 : 0);

    for (int32 AssetIndex = 0; AssetIndex < 2; ++AssetIndex)
    {
        UMaterialInterface* Material = AssetIndex == 0 ? static_cast<UMaterialInterface*>(Base) : static_cast<UMaterialInterface*>(Instance);
        UMaterialInstance* ShaderInstance = AssetIndex == 0 ? nullptr : static_cast<UMaterialInstance*>(Instance);
        for (int32 Q = 0; Q < EMaterialQualityLevel::Num; ++Q)
        {
            const auto Quality = static_cast<EMaterialQualityLevel::Type>(Q);
            FWeaponShaderOwner Owner;
            FWeaponShaderResource* Resource = Owner.Resource;
            if (!Resource || Resource->NoStaticLighting) return WFRStop(TEXT("scene-color-shader-resource-policy"));
            Resource->SetMaterial(Base, Quality, true, ERHIFeatureLevel::ES2, ShaderInstance);

            FMaterialShaderMapId Requested;
            Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
            FWeaponRepair Compare;
            FStaticParameterSet EffectiveStatic;
            if (AssetIndex == 1) Instance->GetStaticParameterValues(EffectiveStatic);
            if (Requested.BaseMaterialId != Base->StateId || Requested.QualityLevel != Quality ||
                Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
                !Compare.Same(MRValue(MRStatic(Requested.ParameterSet)), MRValue(MRStatic(EffectiveStatic))))
                return WFRStop(TEXT("scene-color-shader-requested-identity"));

            const bool CacheReturned = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
            const bool PendingAfterCache = !Resource->IsCompilationFinished();
            const int32 TranslationRequests = Resource->TranslationRequests;
            Resource->FinishCompilation();
            const bool CompilationFinished = Resource->IsCompilationFinished();
            const bool PinsStable = Pins.Check();
            FMaterialShaderMap* Map = CompilationFinished ? Resource->GetGameThreadShaderMap() : nullptr;
            const TArray<FString>& Errors = Resource->GetCompileErrors();
            const bool HasValidMap = CompilationFinished && Resource->HasValidGameThreadShaderMap() && Map;
            const bool MapFinalized = HasValidMap && Map->IsCompilationFinalized();
            const bool CompiledSuccessfully = MapFinalized && Map->CompiledSuccessfully();
            const bool PlatformMatches = CompiledSuccessfully && Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL;
            const bool QualityMatches = Resource->GetQualityLevel() == Quality;
            const bool FeatureLevelMatches = Resource->GetFeatureLevel() == ERHIFeatureLevel::ES2;
            const bool IdentitySubsetMatches = CompiledSuccessfully &&
                WSPMaterialInstanceIdentitySubset(Requested, Map->GetShaderMapId());
            const int32 Samplers = HasValidMap ? Resource->GetSamplerUsage() : -1;
            const bool Valid = SCSHMapAccepted(CacheReturned, CompilationFinished, HasValidMap,
                MapFinalized, CompiledSuccessfully, PlatformMatches, QualityMatches, FeatureLevelMatches,
                IdentitySubsetMatches, Errors.Num(), Samplers);
            AllValid = AllValid && Valid && PinsStable;
            if (Valid) ++ValidResources;
            ++Resources;

            UE_LOG(LogUT4Html5Compat, Display,
                TEXT("COMPAT_SCENE_COLOR_SHADER result asset=%s quality=%s qualityIndex=%d platform=%d cacheReturned=%d pendingAfterCache=%d finished=%d validMap=%d finalized=%d compiled=%d platformMatches=%d qualityMatches=%d featureLevelMatches=%d identityCheck=material-instance-subset identitySubsetMatches=%d translationRequests=%d origin=%s samplers=%d errors=%d pinsStable=%d newShaderJobs=unknown"),
                SCSHMaterialPackages[AssetIndex], SCSHQualityNames[Q], Q, static_cast<int32>(SP_OPENGL_ES2_WEBGL),
                CacheReturned ? 1 : 0, PendingAfterCache ? 1 : 0, CompilationFinished ? 1 : 0,
                HasValidMap ? 1 : 0, MapFinalized ? 1 : 0, CompiledSuccessfully ? 1 : 0,
                PlatformMatches ? 1 : 0, QualityMatches ? 1 : 0, FeatureLevelMatches ? 1 : 0,
                IdentitySubsetMatches ? 1 : 0, TranslationRequests, WSPOrigin(TranslationRequests, PendingAfterCache),
                Samplers, Errors.Num(), PinsStable ? 1 : 0);
            for (int32 I = 0; I < FMath::Min(Errors.Num(), 8); ++I)
                UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_SCENE_COLOR_SHADER error asset=%s quality=%s index=%d text=%s"),
                    SCSHMaterialPackages[AssetIndex], SCSHQualityNames[Q], I, *WFRContext(Errors[I]));
            if (!PinsStable) return WFRStop(TEXT("scene-color-shader-after-resource-pins"));
        }
    }

    const bool FlagsUnchanged = Base->bUsedWithStaticLighting == StaticLightingBefore &&
        Base->GetOutermost()->IsDirty() == BaseDirtyBefore && Instance->GetOutermost()->IsDirty() == InstanceDirtyBefore &&
        Instance->Parent == Base && Base->MaterialDomain == MD_Surface && Base->GetBlendMode() == BLEND_Translucent;
    if (!Pins.Check()) return WFRStop(TEXT("scene-color-shader-final-pins"));
    UE_LOG(LogUT4Html5Compat, Display,
        TEXT("COMPAT_SCENE_COLOR_SHADER complete resources=%d valid=%d allValid=%d materialFlagsAndDirtyStateUnchanged=%d assetsSaved=0 materialSettingsChanged=0 diagnosticOnly=1 browserRenderVerified=0 cookParityVerified=0"),
        Resources, ValidResources, AllValid && Resources == 6 && ValidResources == 6 ? 1 : 0,
        FlagsUnchanged ? 1 : 0);
    return AllValid && Resources == 6 && ValidResources == 6 && FlagsUnchanged ? 0 : 1;
}
