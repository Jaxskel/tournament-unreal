// In-memory candidate only. No save policy, mesh setter, source reparenting or aliases.
// Include after WeaponGrenadeRepair.h and EnforcerConsumerReport.h.
struct FEnforcerCandidatePins
{
    FEnforcerConsumerInputs Consumers;
    FString AfterPath;
    TSharedPtr<FJsonObject> Files;
    bool Check() const
    {
        if (!Consumers.Check() || !Physical(AfterPath, false) ||
            !HashFile(AfterPath).Equals(TEXT("f276720c105f3d754a53ff7cf38bff24b514fceb"), ESearchCase::IgnoreCase) || !Files.IsValid() || Files->Values.Num() != 25) return false;
        for (const auto& KV : Files->Values)
        {
            FString H, File;
            if (!KV.Value->TryGetString(H) || !WTUSHA1(H) || !FPackageName::DoesPackageExist(KV.Key, nullptr, &File) ||
                !HashFile(File).Equals(H, ESearchCase::IgnoreCase)) return false;
        }
        return true;
    }
    bool Read(const FString& Params)
    {
        FString Forbidden;
        if (!FParse::Value(*Params, TEXT("EnforcerInputs="), Consumers.Path) ||
            !FParse::Value(*Params, TEXT("EnforcerInputsSHA1="), Consumers.Hash) ||
            Consumers.Hash != TEXT("81a52a86f48c7d58c812870c4fbd515b95cbfa51") || !Consumers.Read() ||
            !FParse::Value(*Params, TEXT("GrenadeAftermath="), AfterPath) || !Physical(AfterPath, false) ||
            !HashFile(AfterPath).Equals(TEXT("f276720c105f3d754a53ff7cf38bff24b514fceb"), ESearchCase::IgnoreCase) ||
            FParse::Value(*Params, TEXT("Receipt="), Forbidden) || FParse::Value(*Params, TEXT("Manifest="), Forbidden)) return false;
        TSharedPtr<FJsonObject> J; const TSharedPtr<FJsonObject>* Table = nullptr;
        if (!ReadJson(AfterPath, J) || Str(J, TEXT("schema")) != TEXT("ut4-grenade-repair-aftermath-v1") ||
            !WGRBool(J, TEXT("complete"), true) || !J->TryGetObjectField(TEXT("package_sha1"), Table)) return false;
        Files = *Table;
        return Check();
    }
};

struct FEnforcerCandidate
{
    FEnforcerCandidatePins& Pins;
    UMaterial* Master = nullptr; UMaterial* CloneMaster = nullptr;
    UMaterialInstanceConstant* Original[2] = {nullptr, nullptr};
    UMaterialInstanceConstant* Copies[2] = {nullptr, nullptr};
    TMap<FString, UObject*> Sources;
    TMap<FString, FString> DependencyFiles;
    TArray<UObject*> Roots;
    FWSALightingPolicy Lighting[3];
    FGuid MasterId;
    TSharedPtr<FJsonObject> Before;
    FWSAOrdinaryResource* Resource = nullptr;
    bool Closed = false, CloseOK = false;
    explicit FEnforcerCandidate(FEnforcerCandidatePins& P) : Pins(P) {}
    ~FEnforcerCandidate() { Close(); }
    bool Close()
    {
        if (Closed) return CloseOK;
        if (Resource) Resource->FinishCompilation();
        const bool Drained = WSADrain();
        Closed = true;
        if (!Drained || (Resource && !Resource->IsCompilationFinished()))
        {
            UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_ENFORCER_CANDIDATE undrained roots retained until process exit"));
            return false;
        }
        if (Resource) { delete Resource; Resource = nullptr; }
        for (auto* O : Roots) O->RemoveFromRoot();
        CloseOK = true; return true;
    }
    bool Gather()
    {
        if (!Pins.Check()) return false;
        TArray<UObject*> Queue;
        for (const auto& KV : Pins.Files->Values)
        {
            auto* O = LoadObject<UObject>(nullptr, *ObjectPath(KV.Key));
            if (!WGRReady(O) || !Pins.Check()) return false;
            Queue.Add(O);
        }
        Master = FindObject<UMaterial>(nullptr, *ObjectPath(WTUMaster()));
        const auto Targets = ECRRoots();
        for (int32 I = 0; I < 2; ++I) Original[I] = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(Targets[I + 5]));
        if (!WGRReady(Master) || Master->GetClass() != UMaterial::StaticClass() || !Master->bUsedWithStaticLighting ||
            Master->bUsedAsSpecialEngineMaterial || !WSPQualityBranches()) return false;
        for (auto* M : Original) if (!WGRReady(M) || M->GetClass() != UMaterialInstanceConstant::StaticClass() || M->Parent != Master) return false;
        FWeaponRepair Inspect;
        for (int32 I = 0; I < Queue.Num(); ++I)
        {
            auto* O = Queue[I]; if (!WGRReady(O) || Queue.Num() > 8192) return false;
            if (Sources.Contains(O->GetPathName())) continue;
            Sources.Add(O->GetPathName(), O);
            FString File;
            if (!FPackageName::DoesPackageExist(O->GetOutermost()->GetName(), nullptr, &File)) return false;
            const FString H = HashFile(File); if (!WTUSHA1(H)) return false;
            if (DependencyFiles.Contains(File) && DependencyFiles.FindChecked(File) != H) return false;
            DependencyFiles.Add(File, H);
            if (auto* Es = Inspect.Expressions(O)) for (auto* E : *Es)
            {
                if (!WGRReady(E) || E->GetOuter() != O) return false;
                Queue.Add(E);
                if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                { if (!WGRReady(C->MaterialFunction)) return false; Queue.AddUnique(C->MaterialFunction); }
            }
        }
        if (!WSADrain()) return false;
        Before = Snapshot();
        return Before.IsValid() && Unchanged();
    }
    TSharedPtr<FJsonObject> Snapshot() const
    {
        auto J = WGRObject(), Objects = WGRObject(), Dirty = WGRObject();
        for (const auto& KV : Sources)
        {
            if (!WGRReady(KV.Value)) return nullptr;
            Objects->SetObjectField(KV.Key, WSAObject(KV.Value));
            Dirty->SetBoolField(KV.Value->GetOutermost()->GetName(), KV.Value->GetOutermost()->IsDirty());
        }
        J->SetObjectField(TEXT("objects"), Objects); J->SetObjectField(TEXT("dirty"), Dirty);
        for (int32 I = 0; I < 2; ++I)
        {
            auto Facts = WGRInstance(Original[I], Master, nullptr); if (!Facts.IsValid()) return nullptr;
            J->SetObjectField(I == 0 ? TEXT("one") : TEXT("three"), Facts);
        }
        return J;
    }
    bool Unchanged() const
    {
        if (!Pins.Check()) return false;
        for (const auto& KV : DependencyFiles) if (HashFile(KV.Key) != KV.Value) return false;
        auto Now = Snapshot();
        return Before.IsValid() && Now.IsValid() && FWeaponRepair().Same(MRValue(Before), MRValue(Now));
    }
    template<typename T> T* Copy(T* Source, const TCHAR* Name)
    {
        if (FindObject<UObject>(GetTransientPackage(), Name)) return nullptr;
        auto* O = DuplicateObject<T>(Source, GetTransientPackage(), FName(Name));
        if (!O) return nullptr;
        O->AddToRoot(); Roots.Add(O); O->SetFlags(RF_Transient);
        return O != Source && O->GetOuter() == GetTransientPackage() && O->GetClass() == Source->GetClass() ? O : nullptr;
    }
    bool Prepare()
    {
        for (const TCHAR* N : {TEXT("UT4EnforcerCandidateMaster"), TEXT("UT4EnforcerCandidate1P"), TEXT("UT4EnforcerCandidate3P")})
            if (FindObject<UObject>(GetTransientPackage(), N)) return false;
        if (!Unchanged()) return false;
        CloneMaster = Copy(Master, TEXT("UT4EnforcerCandidateMaster"));
        if (!CloneMaster || !Lighting[0].Capture(Master, CloneMaster) || !WSAOwnedGraph(Master, CloneMaster)) return false;
        for (auto* E : CloneMaster->Expressions)
        {
            E->SetFlags(RF_Transient);
            if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
            {
                const auto Previous = MRProperties(C, true); C->UpdateFromFunctionResource(false);
                if (!FWeaponRepair().Same(MRValue(Previous), MRValue(MRProperties(C, true))) || !WSAInterfaces(C)) return false;
            }
        }
        MasterId = FGuid::NewGuid(); CloneMaster->StateId = MasterId;
        CloneMaster->bUsedWithStaticLighting = false;
        Copies[0] = Copy(Original[0], TEXT("UT4EnforcerCandidate1P"));
        Copies[1] = Copy(Original[1], TEXT("UT4EnforcerCandidate3P"));
        for (int32 I = 0; I < 2; ++I)
        {
            if (!Copies[I] || !Lighting[I + 1].Capture(Original[I], Copies[I]) || !Unchanged()) return false;
            // Only a rooted, owned transient copy receives this setter.
            Copies[I]->SetParentEditorOnly(CloneMaster);
        }
        return WSADrain() && Equivalent() && Unchanged();
    }
    bool Equivalent() const
    {
        if (!CloneMaster || !MasterId.IsValid() || MasterId == Master->StateId || CloneMaster->StateId != MasterId ||
            CloneMaster->GetOuter() != GetTransientPackage() || !CloneMaster->HasAnyFlags(RF_Transient) ||
            CloneMaster->bUsedWithStaticLighting || !WSAOwnedGraph(Master, CloneMaster)) return false;
        FWeaponRepair Compare; Compare.Canonical.Add(CloneMaster->GetPathName(), Master->GetPathName());
        for (int32 I = 0; I < 2; ++I)
        {
            if (!Copies[I] || Copies[I]->GetOuter() != GetTransientPackage() || !Copies[I]->HasAnyFlags(RF_Transient) || Copies[I]->Parent != CloneMaster || Copies[I]->GetMaterial() != CloneMaster) return false;
            Compare.Canonical.Add(Copies[I]->GetPathName(), Original[I]->GetPathName());
        }
        auto X = WSAObject(Master), Y = WSAObject(CloneMaster);
        auto XP = X->GetObjectField(TEXT("properties")), YP = Y->GetObjectField(TEXT("properties"));
        if (!XP->HasField(TEXT("StateId")) || !YP->HasField(TEXT("StateId")) || !Lighting[0].Normalize(XP, YP) ||
            !WGRLightingFields(XP, YP, Master->bUsedWithStaticLighting, CloneMaster->bUsedWithStaticLighting)) return false;
        YP->SetStringField(TEXT("StateId"), Str(XP, TEXT("StateId")));
        YP->SetStringField(TEXT("bUsedWithStaticLighting"), Str(XP, TEXT("bUsedWithStaticLighting")));
        if (!Compare.Same(MRValue(X), MRValue(Y))) return false;
        for (int32 I = 0; I < Master->Expressions.Num(); ++I)
            if (!Compare.Same(MRValue(WSAObject(Master->Expressions[I])), MRValue(WSAObject(CloneMaster->Expressions[I])))) return false;
        for (int32 I = 0; I < 2; ++I)
        {
            auto A = WGRInstance(Original[I], Master, nullptr), B = WGRInstance(Copies[I], Master, nullptr);
            if (!A.IsValid() || !B.IsValid() || !Lighting[I + 1].Normalize(A->GetObjectField(TEXT("properties")), B->GetObjectField(TEXT("properties"))) ||
                !Compare.Same(MRValue(A), MRValue(B))) return false;
        }
        return true;
    }
    bool Compile()
    {
        int32 Count = 0;
        for (int32 I = 0; I < 2; ++I) for (auto Q : {EMaterialQualityLevel::Low, EMaterialQualityLevel::Medium, EMaterialQualityLevel::High})
        {
            if (!Equivalent() || !Unchanged() || Resource) return false;
            Resource = new FWSAOrdinaryResource;
            Resource->SetMaterial(CloneMaster, Q, true, ERHIFeatureLevel::ES2, Copies[I]);
            FMaterialShaderMapId Requested; Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
            FStaticParameterSet Static; Copies[I]->GetStaticParameterValues(Static);
            if (Resource->IsUsedWithStaticLighting() || Resource->IsPersistent() || Resource->IsSpecialEngineMaterial() ||
                Requested.BaseMaterialId != MasterId || Requested.QualityLevel != Q || Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
                !FWeaponRepair().Same(MRValue(MRStatic(Static)), MRValue(MRStatic(Requested.ParameterSet)))) return false;
            const bool Cached = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
            Resource->FinishCompilation();
            if (!WSADrain() || !Resource->IsCompilationFinished()) return false;
            auto* Map = Resource->GetGameThreadShaderMap();
            const bool MapOK = Cached && Resource->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() &&
                Map->CompiledSuccessfully() && Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL &&
                WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId()) && Resource->GetCompileErrors().Num() == 0;
            const int32 Samplers = MapOK ? Resource->GetSamplerUsage() : -1;
            const bool Valid = MapOK && Samplers >= 0 && Samplers <= 16;
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_ENFORCER_CANDIDATE resource member=%d quality=%d valid=%d samplers=%d translations=%d assetStaticLighting=0 getterOverride=0 persistent=0"),
                I, int32(Q), Valid ? 1 : 0, Samplers, Resource->TranslationRequests);
            for (const auto& Error : Resource->GetCompileErrors())
                UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_ENFORCER_CANDIDATE compiler_error %s"), *WFRContext(Error));
            delete Resource; Resource = nullptr;
            if (!Valid || !Equivalent() || !Unchanged()) return false;
            ++Count;
        }
        return Count == 6;
    }
};
static int32 EnforcerMaterialCandidate(const FString& Params)
{
    FString Mode; FParse::Value(*Params, TEXT("Mode="), Mode);
    FEnforcerCandidatePins Pins;
    if (!GIsEditor || !IsInGameThread() || !FApp::CanEverRender() || Mode != TEXT("EnforcerMaterialCandidate") ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")) || !Pins.Read(Params)) return WFRStop(TEXT("enforcer-candidate-admission"));
    FEnforcerCandidate State(Pins);
    if (!State.Gather()) return WFRStop(TEXT("enforcer-candidate-source"));
    if (!State.Prepare()) return WFRStop(TEXT("enforcer-candidate-prepare"));
    if (!State.Compile()) return WFRStop(TEXT("enforcer-candidate-shaders"));
    if (!State.Unchanged() || !State.Close() || !State.Unchanged()) return WFRStop(TEXT("enforcer-candidate-finish"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_ENFORCER_CANDIDATE complete resources=6 valid=6 assetsSaved=0 meshChanges=0 sourceUnchanged=1 runtimeAcceptance=0"));
    return 0;
}
