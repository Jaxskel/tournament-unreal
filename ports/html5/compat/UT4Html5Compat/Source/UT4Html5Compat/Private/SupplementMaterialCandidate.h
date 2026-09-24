// Fixed, transient-only Bio body and grenade-ammo parent-to-V1 shader candidate.
// Include after WeaponGrenadeRepair.h and EnforcerMaterialCandidate.h.
// No aliases, source setters, mesh edits, save policy, or package writes.
static const TCHAR* SMC_AftermathSHA1 = TEXT("632833e9512e68db02899077e06f5024555776ee");
static FString SMC_V1Master() { return WTUMaster(); }
static const TCHAR* SMC_OldMaster = TEXT("/Game/RestrictedAssets/Weapons/Global/Material/M_WeaponsBase");
static const TCHAR* SMC_Packages[5] = {
    TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon_1p_Inst"),
    TEXT("/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon3p"),
    TEXT("/Game/RestrictedAssets/Weapons/Global/Material/M_WeaponsBase"),
    TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Grenade/MIC_Grenade"),
    TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_3P")
};
static const TCHAR* SMC_SHA1[5] = {
    TEXT("98cd7456492bb522726946e963b18c4eebb075bc"),
    TEXT("affc9650c6a6799313af639491529b074700cd75"),
    TEXT("d3da11ac075007c5978a881ac8971f6df74c1de1"),
    TEXT("b1ac8f1d13406a0eba56312f03d5b75e8637c7d3"),
    TEXT("2c68ebcd0e2f971e055a5c2488c3dee93d8c029e")
};

struct FSupplementCandidatePins
{
    FString AfterPath;
    TSharedPtr<FJsonObject> Files;
    bool Check() const
    {
        if (!Physical(AfterPath, false) || !HashFile(AfterPath).Equals(SMC_AftermathSHA1, ESearchCase::IgnoreCase) ||
            !Files.IsValid() || Files->Values.Num() != 33) return false;
        for (const auto& KV : Files->Values)
        {
            FString H, File;
            if (!KV.Value->TryGetString(H) || !WTUSHA1(H) ||
                !FPackageName::DoesPackageExist(KV.Key, nullptr, &File) ||
                !HashFile(File).Equals(H, ESearchCase::IgnoreCase)) return false;
        }
        for (int32 I = 0; I < 5; ++I)
        {
            FString File;
            if (!FPackageName::DoesPackageExist(SMC_Packages[I], nullptr, &File) ||
                !HashFile(File).Equals(SMC_SHA1[I], ESearchCase::IgnoreCase)) return false;
        }
        return true;
    }
    bool Read(const FString& Params)
    {
        FString Hash; TSharedPtr<FJsonObject> J; const TSharedPtr<FJsonObject>* Table = nullptr;
        if (!FParse::Value(*Params, TEXT("SupplementAftermath="), AfterPath) ||
            !FParse::Value(*Params, TEXT("SupplementAftermathSHA1="), Hash) ||
            Hash != SMC_AftermathSHA1 || !Physical(AfterPath, false) ||
            !HashFile(AfterPath).Equals(SMC_AftermathSHA1, ESearchCase::IgnoreCase) ||
            !ReadJson(AfterPath, J) || Str(J, TEXT("schema")) != TEXT("ut4-enforcer-repair-aftermath-v1") ||
            !WGRBool(J, TEXT("complete"), true) || !WGRNumber(J, TEXT("saved"), 5) ||
            !J->TryGetObjectField(TEXT("files"), Table)) return false;
        Files = *Table;
        return Check();
    }
};

struct FSupplementMaterialCandidate
{
    FSupplementCandidatePins& Pins;
    UMaterial* V1 = nullptr; UMaterial* CloneV1 = nullptr; UMaterial* OldMaster = nullptr;
    // Bio parent, Bio child, grenade parent, grenade child.
    UMaterialInstanceConstant* Original[4] = {nullptr, nullptr, nullptr, nullptr};
    UMaterialInstanceConstant* Copies[4] = {nullptr, nullptr, nullptr, nullptr};
    TMap<FString, UObject*> Sources; TMap<FString, FString> DependencyFiles;
    TArray<UObject*> Roots; FWSALightingPolicy Lighting[5]; FGuid MasterId;
    TSharedPtr<FJsonObject> Before; FWSAOrdinaryResource* Resource = nullptr;
    bool Closed = false, CloseOK = false;
    explicit FSupplementMaterialCandidate(FSupplementCandidatePins& P) : Pins(P) {}
    ~FSupplementMaterialCandidate() { Close(); }
    bool Close()
    {
        if (Closed) return CloseOK;
        if (Resource) Resource->FinishCompilation();
        const bool Drained = WSADrain(); Closed = true;
        if (!Drained || (Resource && !Resource->IsCompilationFinished()))
        { UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_SUPPLEMENT_CANDIDATE undrained roots retained until process exit")); return false; }
        if (Resource) { delete Resource; Resource = nullptr; }
        for (auto* O : Roots) O->RemoveFromRoot();
        CloseOK = true; return true;
    }
    bool PinFiles() const
    {
        if (!Pins.Check()) return false;
        for (const auto& KV : DependencyFiles) if (!HashFile(KV.Key).Equals(KV.Value, ESearchCase::IgnoreCase)) return false;
        return true;
    }
    template<typename T> T* Copy(T* Source, const TCHAR* Name)
    {
        if (!Source || FindObject<UObject>(GetTransientPackage(), Name)) return nullptr;
        auto* O = DuplicateObject<T>(Source, GetTransientPackage(), FName(Name));
        if (!O) return nullptr;
        O->AddToRoot(); Roots.Add(O); O->SetFlags(RF_Transient);
        return O != Source && O->GetOuter() == GetTransientPackage() && O->GetClass() == Source->GetClass() ? O : nullptr;
    }
    bool Gather()
    {
        if (!Pins.Check()) return false;
        TArray<FString> Packages; for (const auto& KV : Pins.Files->Values) Packages.Add(KV.Key);
        for (int32 I = 0; I < 5; ++I) Packages.Add(SMC_Packages[I]);
        for (const FString& Package : Packages)
        {
            UObject* O = LoadObject<UObject>(nullptr, *ObjectPath(Package));
            if (!WGRReady(O) || !Pins.Check()) return false;
            FString File; if (!FPackageName::DoesPackageExist(Package, nullptr, &File)) return false;
            Sources.Add(O->GetPathName(), O); DependencyFiles.Add(File, HashFile(File));
        }
        V1 = FindObject<UMaterial>(nullptr, *ObjectPath(SMC_V1Master()));
        OldMaster = FindObject<UMaterial>(nullptr, *ObjectPath(SMC_OldMaster));
        // Fixed target order: Bio parent/child, then grenade parent/child.
        Original[0] = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(SMC_Packages[1]));
        Original[1] = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(SMC_Packages[0]));
        Original[2] = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(SMC_Packages[3]));
        Original[3] = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(SMC_Packages[4]));
        if (!WGRReady(V1) || !WGRReady(OldMaster) || V1->GetClass() != UMaterial::StaticClass() ||
            OldMaster->GetClass() != UMaterial::StaticClass() || !V1->bUsedWithStaticLighting ||
            V1->bUsedAsSpecialEngineMaterial || !WSPQualityBranches()) return false;
        for (int32 I = 0; I < 4; ++I)
        {
            if (!WGRReady(Original[I]) || Original[I]->GetClass() != UMaterialInstanceConstant::StaticClass()) return false;
            UMaterialInterface* Expected = (I == 0 || I == 2) ? static_cast<UMaterialInterface*>(OldMaster) : static_cast<UMaterialInterface*>(Original[I - 1]);
            if (Original[I]->Parent != Expected) return false;
        }
        FWeaponRepair Inspect;
        TArray<UObject*> Queue; for (const auto& KV : Sources) Queue.Add(KV.Value);
        for (int32 N = 0; N < Queue.Num(); ++N)
        {
            UObject* O = Queue[N]; if (!WGRReady(O) || Queue.Num() > 8192) return false;
            if (auto* Es = Inspect.Expressions(O)) for (auto* E : *Es)
            {
                if (!WGRReady(E) || E->GetOuter() != O) return false;
                if (!Sources.Contains(E->GetPathName())) Sources.Add(E->GetPathName(), E);
                if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                {
                    if (!WGRReady(C->MaterialFunction)) return false;
                    Sources.Add(C->MaterialFunction->GetPathName(), C->MaterialFunction);
                    Queue.AddUnique(C->MaterialFunction);
                }
            }
        }
        for (const auto& KV : Sources)
        {
            FString File; UObject* O = KV.Value;
            if (!FPackageName::DoesPackageExist(O->GetOutermost()->GetName(), nullptr, &File)) return false;
            const FString H = HashFile(File); if (!WTUSHA1(H)) return false;
            if (DependencyFiles.Contains(File) && !DependencyFiles.FindChecked(File).Equals(H, ESearchCase::IgnoreCase)) return false;
            DependencyFiles.Add(File, H);
        }
        if (!WSADrain() || !PinFiles()) return false;
        Before = Snapshot(); return Before.IsValid() && Unchanged();
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
        auto Instances = WGRObject();
        for (int32 I = 0; I < 4; ++I)
        {
            auto Facts = WGRInstance(Original[I], V1, nullptr);
            if (!Facts.IsValid()) return nullptr;
            Instances->SetObjectField(FString::FromInt(I), Facts);
        }
        J->SetObjectField(TEXT("original_instances"), Instances);
        return J;
    }
    bool Unchanged() const
    {
        if (!PinFiles()) return false;
        auto Now = Snapshot(); return Before.IsValid() && Now.IsValid() && FWeaponRepair().Same(MRValue(Before), MRValue(Now));
    }
    bool Prepare()
    {
        for (const TCHAR* N : {TEXT("UT4SupplementCandidateMaster"), TEXT("UT4SupplementBioParent"), TEXT("UT4SupplementBioChild"), TEXT("UT4SupplementGrenadeParent"), TEXT("UT4SupplementGrenadeChild")})
            if (FindObject<UObject>(GetTransientPackage(), N)) return false;
        if (!Unchanged()) return false;
        CloneV1 = Copy(V1, TEXT("UT4SupplementCandidateMaster"));
        if (!CloneV1 || !Lighting[0].Capture(V1, CloneV1) || !WSAOwnedGraph(V1, CloneV1)) return false;
        for (auto* E : CloneV1->Expressions)
        {
            E->SetFlags(RF_Transient);
            if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
            {
                auto Previous = MRProperties(C, true); C->UpdateFromFunctionResource(false);
                if (!FWeaponRepair().Same(MRValue(Previous), MRValue(MRProperties(C, true))) || !WSAInterfaces(C)) return false;
            }
        }
        MasterId = FGuid::NewGuid(); CloneV1->StateId = MasterId; CloneV1->bUsedWithStaticLighting = false;
        const TCHAR* Names[4] = {TEXT("UT4SupplementBioParent"), TEXT("UT4SupplementBioChild"), TEXT("UT4SupplementGrenadeParent"), TEXT("UT4SupplementGrenadeChild")};
        for (int32 I = 0; I < 4; ++I)
        {
            Copies[I] = Copy(Original[I], Names[I]);
            if (!Copies[I] || !Lighting[I + 1].Capture(Original[I], Copies[I]) || !Unchanged()) return false;
        }
        // Only transient copies are reparented; child-to-parent hierarchy is preserved.
        Copies[0]->SetParentEditorOnly(CloneV1); Copies[2]->SetParentEditorOnly(CloneV1);
        Copies[1]->SetParentEditorOnly(Copies[0]); Copies[3]->SetParentEditorOnly(Copies[2]);
        return WSADrain() && Equivalent() && Unchanged();
    }
    bool InstanceFacts(UMaterialInstanceConstant* M, TSharedPtr<FJsonObject>& Out) const
    {
        // nullptr is deliberate: raw parent facts and parameter names, no legacy alias path.
        Out = WGRInstance(M, V1, nullptr); return Out.IsValid();
    }
    bool Equivalent() const
    {
        if (!CloneV1 || !MasterId.IsValid() || MasterId == V1->StateId || CloneV1->StateId != MasterId ||
            CloneV1->GetOuter() != GetTransientPackage() ||
            !CloneV1->HasAnyFlags(RF_Transient) || CloneV1->bUsedWithStaticLighting || !WSAOwnedGraph(V1, CloneV1)) return false;
        for (int32 I = 0; I < 4; ++I)
        {
            UMaterialInterface* Expected = (I == 0 || I == 2) ? static_cast<UMaterialInterface*>(CloneV1) : static_cast<UMaterialInterface*>(Copies[I - 1]);
            if (!Copies[I] || Copies[I]->GetClass() != Original[I]->GetClass() || Copies[I]->GetOuter() != GetTransientPackage() ||
                !Copies[I]->HasAnyFlags(RF_Transient) || Copies[I]->Parent != Expected || Copies[I]->GetMaterial() != CloneV1) return false;
        }
        FWeaponRepair Compare; Compare.Canonical.Add(CloneV1->GetPathName(), V1->GetPathName());
        auto X = WSAObject(V1), Y = WSAObject(CloneV1);
        auto XP = X->GetObjectField(TEXT("properties")), YP = Y->GetObjectField(TEXT("properties"));
        if (!Lighting[0].Normalize(XP, YP) || !WGRLightingFields(XP, YP, V1->bUsedWithStaticLighting, CloneV1->bUsedWithStaticLighting)) return false;
        FString SourceState, CloneState;
        if (!XP->TryGetStringField(TEXT("StateId"), SourceState) || SourceState.IsEmpty() ||
            !YP->TryGetStringField(TEXT("StateId"), CloneState) || CloneState != MasterId.ToString()) return false;
        YP->SetStringField(TEXT("StateId"), SourceState);
        YP->SetStringField(TEXT("bUsedWithStaticLighting"), Str(XP, TEXT("bUsedWithStaticLighting")));
        if (!Compare.Same(MRValue(X), MRValue(Y)) || V1->Expressions.Num() != CloneV1->Expressions.Num()) return false;
        for (int32 I = 0; I < V1->Expressions.Num(); ++I)
            if (!Compare.Same(MRValue(WSAObject(V1->Expressions[I])), MRValue(WSAObject(CloneV1->Expressions[I])))) return false;
        for (int32 I = 0; I < 4; ++I)
        {
            TSharedPtr<FJsonObject> OriginalFacts, CopyFacts;
            if (!InstanceFacts(Original[I], OriginalFacts) || !InstanceFacts(Copies[I], CopyFacts) ||
                !RawFactsEqual(OriginalFacts, CopyFacts, I)) return false;
        }
        return true;
    }
    bool RawFactsEqual(const TSharedPtr<FJsonObject>& A, const TSharedPtr<FJsonObject>& B, int32 Member) const
    {
        if (Member < 0 || Member >= 4 || !A.IsValid() || !B.IsValid()) return false;
        auto AP = A->GetObjectField(TEXT("properties")), BP = B->GetObjectField(TEXT("properties"));
        if (!Lighting[Member + 1].Normalize(AP, BP)) return false;
        FWeaponRepair Compare;
        Compare.Canonical.Add(CloneV1->GetPathName(), V1->GetPathName());
        Compare.Canonical.Add(OldMaster->GetPathName(), V1->GetPathName());
        for (int32 I = 0; I < 4; ++I) Compare.Canonical.Add(Copies[I]->GetPathName(), Original[I]->GetPathName());
        return Compare.Same(MRValue(A), MRValue(B));
    }
    bool Compile()
    {
        int32 Count = 0;
        for (int32 I = 0; I < 4; ++I) for (auto Q : {EMaterialQualityLevel::Low, EMaterialQualityLevel::Medium, EMaterialQualityLevel::High})
        {
            if (!Equivalent() || !Unchanged() || Resource) return false;
            TSharedPtr<FJsonObject> SourceFacts, CandidateFacts;
            if (!InstanceFacts(Original[I], SourceFacts) || !InstanceFacts(Copies[I], CandidateFacts)) return false;
            FWeaponRepair Canonical;
            Canonical.Canonical.Add(CloneV1->GetPathName(), V1->GetPathName());
            Canonical.Canonical.Add(OldMaster->GetPathName(), V1->GetPathName()); // instance facts only
            for (int32 J = 0; J < 4; ++J) Canonical.Canonical.Add(Copies[J]->GetPathName(), Original[J]->GetPathName());
            const bool RawEqual = RawFactsEqual(SourceFacts, CandidateFacts, I);
            const bool EffectiveEqual = Canonical.Same(MRValue(SourceFacts->GetObjectField(TEXT("scalars"))), MRValue(CandidateFacts->GetObjectField(TEXT("scalars")))) &&
                Canonical.Same(MRValue(SourceFacts->GetObjectField(TEXT("vectors"))), MRValue(CandidateFacts->GetObjectField(TEXT("vectors")))) &&
                Canonical.Same(MRValue(SourceFacts->GetObjectField(TEXT("textures"))), MRValue(CandidateFacts->GetObjectField(TEXT("textures")))) &&
                Canonical.Same(MRValue(SourceFacts->GetObjectField(TEXT("static_effective"))), MRValue(CandidateFacts->GetObjectField(TEXT("static_effective"))));
            if (!RawEqual || !EffectiveEqual)
            {
                FString SourceDump, CandidateDump;
                const bool SourceSerialized = FJsonSerializer::Serialize(SourceFacts.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&SourceDump));
                const bool CandidateSerialized = FJsonSerializer::Serialize(CandidateFacts.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&CandidateDump));
                if (!SourceSerialized || !CandidateSerialized || SourceDump.Len() > 131072 || CandidateDump.Len() > 131072)
                {
                    UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_SUPPLEMENT_CANDIDATE mismatch facts serialization/size gate member=%d"), I);
                }
                else
                {
                    UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_SUPPLEMENT_CANDIDATE mismatch member=%d source=%s candidate=%s"), I, *SourceDump, *CandidateDump);
                }
                return false;
            }
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_SUPPLEMENT_CANDIDATE facts member=%d raw_equal=1 effective_equal=1 parent=%s"), I, *Copies[I]->Parent->GetPathName());
            Resource = new FWSAOrdinaryResource;
            Resource->SetMaterial(CloneV1, Q, true, ERHIFeatureLevel::ES2, Copies[I]);
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
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_SUPPLEMENT_CANDIDATE resource member=%d quality=%d valid=%d samplers=%d staticLighting=0 getterOverride=0 persistent=0"),
                I, int32(Q), Valid ? 1 : 0, Samplers);
            for (const auto& Error : Resource->GetCompileErrors()) UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_SUPPLEMENT_CANDIDATE compiler_error %s"), *WFRContext(Error));
            delete Resource; Resource = nullptr;
            if (!Valid || !Equivalent() || !Unchanged()) return false;
            ++Count;
        }
        return Count == 12;
    }
};

static int32 SupplementMaterialCandidate(const FString& Params)
{
    FString Mode, Forbidden; FParse::Value(*Params, TEXT("Mode="), Mode);
    FSupplementCandidatePins Pins;
    if (!GIsEditor || !IsInGameThread() || !FApp::CanEverRender() || Mode != TEXT("SupplementMaterialCandidate") ||
        FParse::Value(*Params, TEXT("Receipt="), Forbidden) || FParse::Value(*Params, TEXT("Manifest="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")) || !Pins.Read(Params)) return WFRStop(TEXT("supplement-candidate-admission"));
    FSupplementMaterialCandidate State(Pins);
    if (!State.Gather()) return WFRStop(TEXT("supplement-candidate-source"));
    if (!State.Prepare()) return WFRStop(TEXT("supplement-candidate-prepare"));
    if (!State.Compile()) return WFRStop(TEXT("supplement-candidate-shaders"));
    if (!State.Unchanged() || !State.Close() || !State.Unchanged()) return WFRStop(TEXT("supplement-candidate-finish"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_SUPPLEMENT_CANDIDATE complete resources=12 valid=12 assetsSaved=0 sourceUnchanged=1 runtimeAcceptance=0"));
    return 0;
}
