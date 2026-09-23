// Fixed three-package transition. Include inside UT4Compat after WeaponSamplerAliasProbe.h.
// Existing helpers are read/compare primitives only; the old write allowlist is never adopted.
static const TCHAR* WGRSpecSHA1 = TEXT("2cc1070e4cda8af887c5eeefcf957abf1de6ff71");
static const TCHAR* WGRTessSHA1 = TEXT("eb4a1f14ee13bd988fe5915802adfbac50ec5db6");
static FString WGRMaster() { return TEXT("/Game/HTML5Compat/Weapons/V1/Grenade/M_WeaponsBase_Grenade"); }
static FString WGRLayer() { return TEXT("/Game/HTML5Compat/Weapons/V1/Grenade/MF_LayerSet_Grenade"); }
static FString WGRChild() { return TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_Launcher_3P"); }
static TSharedPtr<FJsonObject> WGRObject() { return MakeShareable(new FJsonObject); }
static bool WGRBool(const TSharedPtr<FJsonObject>& J, const TCHAR* Key, bool Expected)
{ bool Value = !Expected; return J.IsValid() && J->TryGetBoolField(Key, Value) && Value == Expected; }
static bool WGRNumber(const TSharedPtr<FJsonObject>& J, const TCHAR* Key, double Expected)
{ double Value = -1; return J.IsValid() && J->TryGetNumberField(Key, Value) && Value == Expected; }
static bool WGRLightingFields(const TSharedPtr<FJsonObject>& Source, const TSharedPtr<FJsonObject>& Candidate, bool SourceFlag, bool CandidateFlag)
{
    FString Before, After;
    // This UE's bool ExportText can emit a PRESENT empty string for false.
    // Missing/wrong-type fields are never equivalent to that representation.
    return Source.IsValid() && Candidate.IsValid() && SourceFlag && !CandidateFlag &&
        Source->TryGetStringField(TEXT("bUsedWithStaticLighting"), Before) && Before == TEXT("True") &&
        Candidate->TryGetStringField(TEXT("bUsedWithStaticLighting"), After) && After.IsEmpty();
}
static bool WGRReady(UObject* O)
{ return O && !O->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad | RF_NeedPostLoadSubobjects); }
static int32 WGRStop(const TCHAR* Gate, const FString& Context = FString())
{
    UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_GRENADE_REPAIR failure gate=%s context=%s"), Gate, *WFRContext(Context));
    return 1;
}
// Exclusive external evidence only. A partial/empty file prevents silent retry adoption.
struct FWGREvidence
{
#if PLATFORM_WINDOWS
    HANDLE Handle = INVALID_HANDLE_VALUE;
#endif
    bool Open(const FString& Path)
    {
#if PLATFORM_WINDOWS
        Handle = CreateFileW(*Full(Path), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        return Handle != INVALID_HANDLE_VALUE;
#else
        return false;
#endif
    }
    bool Write(const TSharedPtr<FJsonObject>& J)
    {
        FString Text;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<>::Create(&Text)) || Text.Len() > 16 * 1024 * 1024) return false;
#if PLATFORM_WINDOWS
        FTCHARToUTF8 Bytes(*Text); DWORD Written = 0;
        return Handle != INVALID_HANDLE_VALUE && Bytes.Length() <= 32 * 1024 * 1024 &&
            WriteFile(Handle, Bytes.Get(), Bytes.Length(), &Written, nullptr) && Written == static_cast<DWORD>(Bytes.Length()) && FlushFileBuffers(Handle);
#else
        return false;
#endif
    }
    bool Close()
    {
#if PLATFORM_WINDOWS
        if (Handle != INVALID_HANDLE_VALUE)
        { const bool OK = CloseHandle(Handle) != 0; Handle = INVALID_HANDLE_VALUE; return OK; }
#endif
        return true;
    }
    ~FWGREvidence() { Close(); }
};

struct FWGRProof
{
    FWeaponTessProof Old;
    FSavePolicy Policy;
    FString Preparation, PreparationHash, Receipt, ReceiptHash, SpecPath, BeforePath, AfterPath;
    TSharedPtr<FJsonObject> Prep, Spec, Expected, Refs;
    TArray<FString> Instances, Saves;
    bool ReadJsonBounded(const FString& Path, TSharedPtr<FJsonObject>& J) const
    {
        const int64 Size = IFileManager::Get().FileSize(*Path);
        return Size > 0 && Size <= 32 * 1024 * 1024 && Physical(Path, false) && ReadJson(Path, J);
    }
    bool Ref(const TCHAR* Name, FString& Path, FString& Hash) const
    {
        const TSharedPtr<FJsonObject>* J = nullptr;
        if (!Prep->TryGetObjectField(Name, J)) return false;
        Path = Full(Str(*J, TEXT("path"))); Hash = Str(*J, TEXT("sha1")).ToLower();
        return WTUSHA1(Hash) && Old.External(Path, false) && HashFile(Path).Equals(Hash, ESearchCase::IgnoreCase);
    }
    bool Read(const FString& Params, bool Verify)
    {
        FString ProofPath, ProofHash, TessPath, TessHash, Hash;
        if (!FParse::Value(*Params, TEXT("GrenadePreparation="), Preparation) ||
            !FParse::Value(*Params, TEXT("GrenadePreparationSHA1="), PreparationHash) || !WTUSHA1(PreparationHash) ||
            !FParse::Value(*Params, TEXT("GrenadeReceipt="), Receipt) ||
            !FParse::Value(*Params, TEXT("GrenadeReceiptSHA1="), ReceiptHash) || !WTUSHA1(ReceiptHash) ||
            !Physical(Preparation, false) || !HashFile(Preparation).Equals(PreparationHash, ESearchCase::IgnoreCase) ||
            !ReadJsonBounded(Preparation, Prep) || Str(Prep, TEXT("schema")) != TEXT("ut4-grenade-repair-preparation-v1")) return false;
        const TSharedPtr<FJsonObject>* P = nullptr;
        if (!Prep->TryGetObjectField(TEXT("current_proof"), P) || Str(*P, TEXT("sha1")) != WTUProofSHA1 || !Old.Read(Str(*P, TEXT("path")))) return false;
        if (!Old.External(Preparation, false) || !Ref(TEXT("current_proof"), ProofPath, ProofHash) ||
            !Ref(TEXT("spec"), SpecPath, Hash) || Hash != WGRSpecSHA1 || !ReadJsonBounded(SpecPath, Spec) ||
            !Ref(TEXT("tess_aftermath"), TessPath, TessHash) || TessHash != WGRTessSHA1) return false;
        // Spec is immutable repository-authored scope; preparation may add Python identity metadata.
        if (Str(Spec, TEXT("schema")) != TEXT("ut4-grenade-repair-spec-v1")) return false;
        Expected = Spec->GetObjectField(TEXT("before_sha1"));
        for (const auto& V : Spec->GetArrayField(TEXT("instances"))) Instances.Add(V->AsString());
        for (const auto& V : Spec->GetArrayField(TEXT("save_packages"))) Saves.Add(V->AsString());
        if (Expected->Values.Num() != 23 || Instances.Num() != 18 || Saves.Num() != 3 ||
            Saves[0] != WGRLayer() || Saves[1] != WGRMaster() || Saves[2] != WSATarget()) return false;
        TSharedPtr<FJsonObject> Tess;
        if (!ReadJsonBounded(TessPath, Tess) || !WGRBool(Tess, TEXT("complete"), true) || !WGRNumber(Tess, TEXT("saved"), 1) ||
            !FWeaponRepair().Same(MRValue(Expected), MRValue(Tess->GetObjectField(TEXT("package_sha1"))))) return false;
        const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
        if (!Prep->TryGetArrayField(TEXT("rows"), Rows) || Rows->Num() != 23) return false;
        TSet<FString> Seen;
        for (const auto& V : *Rows)
        {
            if (V->Type != EJson::Object) return false;
            auto J = V->AsObject(); const FString Package = Str(J, TEXT("package"));
            const FString* File = Old.CurrentFiles.Find(Package);
            if (!File || Seen.Contains(Package) || !Full(Str(J, TEXT("path"))).Equals(*File, ESearchCase::IgnoreCase) ||
                !Str(J, TEXT("sha1")).Equals(Str(Expected, *Package), ESearchCase::IgnoreCase)) return false;
            Seen.Add(Package);
        }
        if (!Prep->TryGetArrayField(TEXT("new_destinations"), Rows) || Rows->Num() != 2) return false;
        Seen.Empty();
        for (const auto& V : *Rows)
        {
            if (V->Type != EJson::Object) return false;
            auto J = V->AsObject(); const FString Package = Str(J, TEXT("package"));
            if ((Package != WGRMaster() && Package != WGRLayer()) || Seen.Contains(Package) ||
                !Full(Str(J, TEXT("path"))).Equals(Full(FPackageName::LongPackageNameToFilename(Package, TEXT(".uasset"))), ESearchCase::IgnoreCase)) return false;
            Seen.Add(Package);
        }
        TSet<FString> Allowed; for (const auto& S : Saves) Allowed.Add(S.ToLower());
        TSharedPtr<FJsonObject> COW;
        if (!Old.External(Receipt, false) || !HashFile(Receipt).Equals(ReceiptHash, ESearchCase::IgnoreCase) ||
            !ReadJsonBounded(Receipt, COW) || Str(COW, TEXT("operation")) != TEXT("grenade-defaults-v1") ||
            !Policy.Read(Receipt, Preparation, Allowed) || !Policy.OriginalRoot.Equals(Full(Str(Old.Json, TEXT("original"))), ESearchCase::IgnoreCase)) return false;
        FString Backup, BackupHash, Approval, ApprovalHash;
        if (!Ref(TEXT("one_p_beforeimage"), Backup, BackupHash) || BackupHash != Str(Expected, *WSATarget()) ||
            !Ref(TEXT("candidate_approval"), Approval, ApprovalHash)) return false;
        TSharedPtr<FJsonObject> A;
        if (!ReadJsonBounded(Approval, A) || Str(A, TEXT("schema")) != TEXT("ut4-grenade-candidate-approval-v1") ||
            !WGRBool(A, TEXT("reviewed"), true) || !WGRNumber(A, TEXT("resources"), 6) || !WGRNumber(A, TEXT("valid"), 6) ||
            !WGRNumber(A, TEXT("native_exit"), 0) || !WGRBool(A, TEXT("asset_flag_false"), true) ||
            !WGRBool(A, TEXT("resource_lighting_override"), false) || !WGRBool(A, TEXT("reference_ids_equal"), true)) return false;
        for (const TCHAR* Key : {TEXT("pair_log"), TEXT("asset_flag_log")})
        {
            if (!A->TryGetObjectField(Key, P) || !WTUSHA1(Str(*P, TEXT("sha1"))) || !Old.External(Str(*P, TEXT("path")), false) ||
                !HashFile(Str(*P, TEXT("path"))).Equals(Str(*P, TEXT("sha1")), ESearchCase::IgnoreCase)) return false;
        }
        Refs = A;
        if (!FParse::Value(*Params, TEXT("GrenadeBefore="), BeforePath) || !FParse::Value(*Params, TEXT("GrenadeAftermath="), AfterPath) ||
            !Old.External(BeforePath, !Verify) || !Old.External(AfterPath, !Verify) || Full(BeforePath).Equals(Full(AfterPath), ESearchCase::IgnoreCase)) return false;
        if (!Verify)
        {
            FString LegacyProof, LegacyTess;
            if (!FParse::Value(*Params, TEXT("WeaponCurrentProof="), LegacyProof) || !Full(LegacyProof).Equals(ProofPath, ESearchCase::IgnoreCase) ||
                !FParse::Value(*Params, TEXT("WeaponTessAftermath="), LegacyTess) || !Full(LegacyTess).Equals(TessPath, ESearchCase::IgnoreCase) ||
                FPaths::FileExists(BeforePath) || FPaths::FileExists(AfterPath)) return false;
        }
        return true;
    }
    bool Evidence() const
    {
        if (!Old.External(Preparation, false) || !HashFile(Preparation).Equals(PreparationHash, ESearchCase::IgnoreCase) ||
            !Old.External(Receipt, false) || !HashFile(Receipt).Equals(ReceiptHash, ESearchCase::IgnoreCase) ||
            !Physical(Old.File, false) || !HashFile(Old.File).Equals(WTUProofSHA1, ESearchCase::IgnoreCase)) return false;
        for (const TCHAR* Key : {TEXT("spec"), TEXT("current_proof"), TEXT("tess_aftermath"), TEXT("one_p_beforeimage"), TEXT("candidate_approval")})
        { FString P, H; if (!Ref(Key, P, H)) return false; }
        for (const TCHAR* Key : {TEXT("pair_log"), TEXT("asset_flag_log")})
        { auto J = Refs->GetObjectField(Key); if (!Old.External(Str(J, TEXT("path")), false) || !HashFile(Str(J, TEXT("path"))).Equals(Str(J, TEXT("sha1")), ESearchCase::IgnoreCase)) return false; }
        for (const TCHAR* Key : {TEXT("original_dependencies"), TEXT("artifacts")})
            for (const auto& V : Old.Json->GetArrayField(Key)) if (!Old.Snapshot(V->AsObject())) return false;
        return Old.Snapshot(Old.Json->GetObjectField(TEXT("recipe"))) && Old.Snapshot(Old.Json->GetObjectField(TEXT("baseline")));
    }
    // Empty hashes mean the two fixed new destinations must still be absent.
    bool Files(const TSharedPtr<FJsonObject>& Hashes) const
    {
        if (!Evidence() || Hashes->Values.Num() != 25) return false;
        for (const auto& KV : Hashes->Values)
        {
            const FString* OldFile = Old.CurrentFiles.Find(KV.Key);
            if (!OldFile && KV.Key != WGRMaster() && KV.Key != WGRLayer()) return false;
            const FString File = OldFile ? *OldFile : Full(FPackageName::LongPackageNameToFilename(KV.Key, TEXT(".uasset")));
            const FString H = KV.Value->AsString();
            if (!Physical(File, H.IsEmpty())) return false;
            if (H.IsEmpty()) { if (OldFile || FPaths::FileExists(File)) return false; }
            else if (!WTUSHA1(H) || !HashFile(File).Equals(H, ESearchCase::IgnoreCase)) return false;
        }
        return true;
    }
    TSharedPtr<FJsonObject> InitialFiles() const
    {
        auto J = WGRObject(); for (const auto& KV : Expected->Values) J->SetField(KV.Key, KV.Value);
        J->SetStringField(WGRMaster(), TEXT("")); J->SetStringField(WGRLayer(), TEXT("")); return J;
    }
    bool FinalTable(const TSharedPtr<FJsonObject>& Table) const
    {
        if (!Table.IsValid() || Table->Values.Num() != 25) return false;
        for (const auto& KV : Expected->Values)
        {
            const FString H = Str(Table, *KV.Key);
            if (!WTUSHA1(H)) return false;
            if (KV.Key == WSATarget()) { if (H.Equals(KV.Value->AsString(), ESearchCase::IgnoreCase)) return false; }
            else if (!H.Equals(KV.Value->AsString(), ESearchCase::IgnoreCase)) return false;
        }
        return WTUSHA1(Str(Table, *WGRMaster())) && WTUSHA1(Str(Table, *WGRLayer()));
    }
};

// No registry queries. Parameter reads are over the unchanged shared master names.
// After aliasing, exactly the six old texture keys use their canonical binding;
// raw per-instance override arrays remain separately byte-for-byte textual facts.
static TSharedPtr<FJsonObject> WGRInstance(UMaterialInstanceConstant* M, UMaterial* SourceMaster, UMaterial* NewMaster)
{
    if (!WGRReady(M) || !WGRReady(SourceMaster)) return nullptr;
    const FString Package = M->GetOutermost()->GetName();
    const bool Pair = Package == WSATarget() || Package == WGRChild();
    auto J = WGRObject(); auto Properties = MRProperties(M, true);
    if (NewMaster && Package == WSATarget())
    {
        if (M->Parent != NewMaster) return nullptr;
        Properties->SetStringField(TEXT("Parent"), FString(TEXT("Material'")) + SourceMaster->GetPathName() + TEXT("'"));
    }
    J->SetObjectField(TEXT("properties"), Properties);
    TArray<TSharedPtr<FJsonValue>> Chain; TSet<UMaterialInterface*> Seen;
    for (UMaterialInterface* P = M; P; )
    {
        if (!WGRReady(P) || Seen.Contains(P) || Seen.Num() >= 32) return nullptr;
        Seen.Add(P); Chain.Add(MakeShareable(new FJsonValueString(P == NewMaster ? SourceMaster->GetPathName() : P->GetPathName())));
        auto* Instance = Cast<UMaterialInstance>(P); P = Instance ? Instance->Parent : nullptr;
    }
    J->SetArrayField(TEXT("parents"), Chain); J->SetObjectField(TEXT("static_overrides"), MRStatic(M->GetStaticParameters()));
    FStaticParameterSet Effective; M->GetStaticParameterValues(Effective); J->SetObjectField(TEXT("static_effective"), MRStatic(Effective));
    J->SetNumberField(TEXT("blend"), M->GetBlendMode()); J->SetNumberField(TEXT("shading"), M->GetShadingModel());
    J->SetBoolField(TEXT("two_sided"), M->IsTwoSided()); J->SetNumberField(TEXT("opacity_mask_clip"), M->GetOpacityMaskClipValue());
    for (int32 Kind = 0; Kind < 3; ++Kind)
    {
        TArray<FName> Names; TArray<FGuid> Ids; auto Values = WGRObject();
        if (Kind == 0) SourceMaster->GetAllScalarParameterNames(Names, Ids);
        if (Kind == 1) SourceMaster->GetAllVectorParameterNames(Names, Ids);
        if (Kind == 2) SourceMaster->GetAllTextureParameterNames(Names, Ids);
        if (Names.Num() != Ids.Num() || Names.Num() > 2048) return nullptr;
        for (FName Name : Names)
        {
            const FString Key = Name.ToString(); if (Values->HasField(Key)) return nullptr;
            if (Kind == 0) { float V = 0; if (!M->GetScalarParameterValue(Name, V)) return nullptr; Values->SetNumberField(Key, V); }
            if (Kind == 1)
            {
                FLinearColor V; if (!M->GetVectorParameterValue(Name, V)) return nullptr;
                TArray<TSharedPtr<FJsonValue>> C; for (float X : {V.R, V.G, V.B, V.A}) C.Add(MakeShareable(new FJsonValueNumber(X)));
                Values->SetArrayField(Key, C);
            }
            if (Kind == 2)
            {
                FName Lookup = Name;
                if (Pair && NewMaster) for (const auto& A : WSAliases) if (Key == A.OldName) Lookup = FName(A.NewName);
                UTexture* V = nullptr; if (!M->GetTextureParameterValue(Lookup, V) || !V) return nullptr;
                Values->SetStringField(Key, V->GetPathName());
            }
        }
        J->SetObjectField(Kind == 0 ? TEXT("scalars") : (Kind == 1 ? TEXT("vectors") : TEXT("textures")), Values);
    }
    return J;
}

struct FWGRState
{
    FWGRProof& Proof;
    UMaterial* Master = nullptr; UMaterialFunction* Layer = nullptr;
    UMaterial* NewMaster = nullptr; UMaterialFunction* NewLayer = nullptr;
    UMaterialInstanceConstant* One = nullptr; UMaterialInstanceConstant* Three = nullptr;
    TMap<FString, UObject*> Sources;
    TArray<UObject*> Roots;
    FMaterialResource* Resource = nullptr;
    TSharedPtr<FJsonObject> Before, Ids, Files, DirtyBaseline;
    bool Closed = false, CloseOK = false;
    explicit FWGRState(FWGRProof& P) : Proof(P), Files(P.InitialFiles()) {}
    ~FWGRState() { Close(); }
    void Hold(UObject* O)
    {
        if (O && !O->IsRooted()) { O->AddToRoot(); Roots.Add(O); }
    }
    bool Close()
    {
        if (Closed) return CloseOK;
        const bool Drained = WSADrain(); if (Resource) Resource->FinishCompilation();
        if (!Drained || (Resource && !Resource->IsCompilationFinished()))
        {
            Closed = true;
            UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_GRENADE_REPAIR undrained owned roots retained until process exit"));
            return false;
        }
        if (Resource) { delete Resource; Resource = nullptr; }
        for (auto* O : Roots) O->RemoveFromRoot(); Closed = true; CloseOK = true; return true;
    }
    bool Gather()
    {
        Master = FindObject<UMaterial>(nullptr, *ObjectPath(WTUMaster()));
        Layer = FindObject<UMaterialFunction>(nullptr, *ObjectPath(WSALayer()));
        One = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(WSATarget()));
        Three = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(WGRChild()));
        if (!WGRReady(Master) || !WGRReady(Layer) || !WGRReady(One) || !WGRReady(Three) || Three->Parent != One || !Master->bUsedWithStaticLighting) return false;
        TArray<UObject*> Queue; Queue.Add(Master); Queue.Add(Layer);
        for (const FString& P : Proof.Instances)
        {
            auto* M = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(P));
            if (!WGRReady(M) || M->GetClass() != UMaterialInstanceConstant::StaticClass()) return false;
            Queue.Add(M);
        }
        FWeaponRepair Inspect;
        for (int32 I = 0; I < Queue.Num(); ++I)
        {
            UObject* O = Queue[I]; if (!WGRReady(O) || Queue.Num() > 8192) return false;
            if (Sources.Contains(O->GetPathName())) continue;
            Sources.Add(O->GetPathName(), O);
            if (auto* Es = Inspect.Expressions(O)) for (auto* E : *Es)
            {
                if (!WGRReady(E) || E->GetOuter() != O || Sources.Contains(E->GetPathName())) return false;
                Queue.Add(E);
                if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                { if (!WGRReady(C->MaterialFunction)) return false; Queue.AddUnique(C->MaterialFunction); }
            }
        }
        return true;
    }
    TSharedPtr<FJsonObject> Snapshot(bool Changed) const
    {
        auto J = WGRObject(), Objects = WGRObject(), Materials = WGRObject(), Dirty = WGRObject();
        for (const auto& KV : Sources)
        {
            auto O = WSAObject(KV.Value);
            if (Changed && KV.Value == One)
            {
                if (!NewMaster || One->Parent != NewMaster) return nullptr;
                O->GetObjectField(TEXT("properties"))->SetStringField(TEXT("Parent"), FString(TEXT("Material'")) + Master->GetPathName() + TEXT("'"));
            }
            Objects->SetObjectField(KV.Key, O);
            const FString P = KV.Value->GetOutermost()->GetName();
            // Only the one explicitly saved original package may become dirty.
            if (P != WSATarget()) Dirty->SetBoolField(P, KV.Value->GetOutermost()->IsDirty());
        }
        for (const FString& P : Proof.Instances)
        {
            auto* M = Cast<UMaterialInstanceConstant>(Sources.FindRef(ObjectPath(P)));
            auto Facts = WGRInstance(M, Master, Changed ? NewMaster : nullptr);
            if (!Facts.IsValid()) return nullptr;
            Materials->SetObjectField(P, Facts);
        }
        J->SetObjectField(TEXT("objects"), Objects); J->SetObjectField(TEXT("instances"), Materials); J->SetObjectField(TEXT("protected_dirty"), Dirty);
        return J;
    }
    bool Unchanged(bool Changed) const
    {
        auto Now = Snapshot(Changed);
        if (!Before.IsValid() || !Now.IsValid() || !DirtyBaseline.IsValid()) return false;
        FWeaponRepair Compare;
        // Serialized semantics cross process boundaries; dirty observations do not.
        // Every process retains its own exact protected-package dirty baseline.
        return Compare.Field(Before, Now, TEXT("objects")) && Compare.Field(Before, Now, TEXT("instances")) &&
            Compare.Same(MRValue(DirtyBaseline), MRValue(Now->GetObjectField(TEXT("protected_dirty"))));
    }
    bool TextureContracts() const
    {
        // Reuse the exact source parameter/sampler contract, not the transient probe's write/lifetime state.
        FWSAliasState ReadOnlyContract(Proof.Old, Str(Proof.Expected, *WTUMaster()));
        ReadOnlyContract.Closed = true; // No owned resources; destructor must not perform work.
        return ReadOnlyContract.Contracts(One, Layer) && ReadOnlyContract.Contracts(Three, Layer);
    }
    bool CloneAbsent() const
    {
        for (const FString& P : {WGRMaster(), WGRLayer()})
            if (FindPackage(nullptr, *P) || FPackageName::DoesPackageExist(P) || !Proof.Policy.Check(P)) return false;
        return true;
    }
    bool SetAlias(UMaterialExpression* E, const FWSAlias& A)
    {
        if (!E || E->GetOuter() != NewLayer || NewLayer->GetPathName() != ObjectPath(WGRLayer()) ||
            E->GetName() != A.Node || E->GetClass()->GetPathName() != TEXT("/Script/Engine.MaterialExpressionTextureObjectParameter")) return false;
        auto BeforeFields = MRProperties(E, true);
        if (!WSAField(BeforeFields, TEXT("ParameterName"), A.OldName) || !WSAField(BeforeFields, TEXT("ExpressionGUID"), A.Guid)) return false;
        auto* P = FindField<UProperty>(E->GetClass(), TEXT("ParameterName"));
        if (!P || P->ArrayDim != 1 || P->HasAnyPropertyFlags(CPF_Transient) || P->GetClass()->GetPathName() != TEXT("/Script/CoreUObject.NameProperty")) return false;
        FName* Name = static_cast<FName*>(P->ContainerPtrToValuePtr<void>(E));
        if (!Name || *Name != FName(A.OldName)) return false;
        *Name = FName(A.NewName);
        auto AfterFields = MRProperties(E, true);
        if (!WSAField(AfterFields, TEXT("ParameterName"), A.NewName)) return false;
        AfterFields->SetStringField(TEXT("ParameterName"), A.OldName);
        return FWeaponRepair().Same(MRValue(BeforeFields), MRValue(AfterFields));
    }
    bool Prepare()
    {
        if (!CloneAbsent() || One->Parent != Master || !Unchanged(false) || !TextureContracts() || !Proof.Files(Files)) return false;
        Hold(One); Hold(Three);
        // Check exact absence before CreatePackage. No existing package or asset is adopted.
        NewLayer = DuplicateObject<UMaterialFunction>(Layer, CreatePackage(nullptr, *WGRLayer()), FName(*FPackageName::GetShortName(WGRLayer())));
        if (!NewLayer) return false; Hold(NewLayer);
        NewMaster = DuplicateObject<UMaterial>(Master, CreatePackage(nullptr, *WGRMaster()), FName(*FPackageName::GetShortName(WGRMaster())));
        if (!NewMaster) return false; Hold(NewMaster);
        if (NewLayer == Layer || NewMaster == Master || NewLayer->GetPathName() != ObjectPath(WGRLayer()) ||
            NewMaster->GetPathName() != ObjectPath(WGRMaster()) || NewLayer->HasAnyFlags(RF_Transient) || NewMaster->HasAnyFlags(RF_Transient) ||
            !WSAOwnedGraph(Master, NewMaster) || !WSAOwnedGraph(Layer, NewLayer)) return false;
        NewLayer->SetFlags(RF_Public | RF_Standalone); NewMaster->SetFlags(RF_Public | RF_Standalone);
        NewMaster->StateId = FGuid::NewGuid(); NewLayer->StateId = FGuid::NewGuid();
        Ids = WGRObject(); Ids->SetStringField(TEXT("master"), NewMaster->StateId.ToString());
        Ids->SetStringField(TEXT("layer"), NewLayer->StateId.ToString()); Ids->SetStringField(TEXT("lighting"), NewMaster->GetLightingGuid().ToString());
        if (!Identity()) return false;
        FWeaponRepair Inspect;
        // All owners/input pointers were proved above, before any updater/setter.
        for (UObject* O : {static_cast<UObject*>(NewMaster), static_cast<UObject*>(NewLayer)})
            for (auto* E : *Inspect.Expressions(O)) if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
            {
                auto B = MRProperties(C, true); C->UpdateFromFunctionResource(false);
                if (!Inspect.Same(MRValue(B), MRValue(MRProperties(C, true))) || !WSAInterfaces(C)) return false;
            }
        if (!WSAOwnedGraph(Master, NewMaster) || !WSAOwnedGraph(Layer, NewLayer)) return false;
        for (const auto& A : WSAliases) if (!SetAlias(Inspect.Node(NewLayer, A.Node, TEXT("MaterialExpressionTextureObjectParameter")), A)) return false;
        auto* Call = Cast<UMaterialExpressionMaterialFunctionCall>(Inspect.Node(NewMaster, TEXT("MaterialExpressionMaterialFunctionCall_0"), TEXT("MaterialExpressionMaterialFunctionCall")));
        if (!Call || Call->MaterialFunction != Layer || !Call->SetMaterialFunction(nullptr, Layer, NewLayer) || !WSAInterfaces(Call)) return false;
        int32 Replaced = 0;
        for (auto& Info : NewMaster->MaterialFunctionInfos) if (Info.Function == Layer)
        { if (Info.StateId != Layer->StateId) return false; Info.Function = NewLayer; Info.StateId = NewLayer->StateId; ++Replaced; }
        if (Replaced != 1 || !NewMaster->bUsedWithStaticLighting) return false;
        NewMaster->bUsedWithStaticLighting = false;
        if (!Equivalent() || !Unchanged(false) || !Proof.Files(Files)) return false;
        {
            FMaterialUpdateContext Update;
            Update.AddMaterial(NewMaster); Update.AddMaterialInstance(One); Update.AddMaterialInstance(Three);
            One->SetParentEditorOnly(NewMaster);
        }
        return WSADrain() && Equivalent() && Unchanged(true) && Proof.Files(Files);
    }
    bool Identity() const
    {
        return NewMaster && NewLayer && Ids.IsValid() && Ids->Values.Num() == 3 &&
            NewMaster->StateId.IsValid() && NewLayer->StateId.IsValid() && NewMaster->GetLightingGuid().IsValid() &&
            NewMaster->StateId != Master->StateId && NewLayer->StateId != Layer->StateId && NewMaster->StateId != NewLayer->StateId &&
            NewMaster->GetLightingGuid() != Master->GetLightingGuid() &&
            Str(Ids, TEXT("master")) == NewMaster->StateId.ToString() && Str(Ids, TEXT("layer")) == NewLayer->StateId.ToString() &&
            Str(Ids, TEXT("lighting")) == NewMaster->GetLightingGuid().ToString();
    }
    bool Equivalent() const
    {
        if (!Identity() || NewMaster->bUsedWithStaticLighting || NewMaster->GetPathName() != ObjectPath(WGRMaster()) ||
            NewLayer->GetPathName() != ObjectPath(WGRLayer()) || !WSAOwnedGraph(Master, NewMaster, Layer, NewLayer) || !WSAOwnedGraph(Layer, NewLayer)) return false;
        FWeaponRepair Compare;
        Compare.Canonical.Add(NewMaster->GetPathName(), Master->GetPathName()); Compare.Canonical.Add(NewLayer->GetPathName(), Layer->GetPathName());
        const auto& A = Master->MaterialFunctionInfos; const auto& B = NewMaster->MaterialFunctionInfos;
        if (A.Num() != B.Num()) return false;
        int32 Replaced = 0, Aliased = 0;
        for (int32 I = 0; I < A.Num(); ++I)
        {
            const bool Target = A[I].Function == Layer;
            if (B[I].Function != (Target ? NewLayer : A[I].Function) || B[I].StateId != (Target ? NewLayer->StateId : A[I].StateId)) return false;
            if (Target) ++Replaced;
        }
        if (Replaced != 1) return false;
        UObject* Old[] = {Master, Layer}; UObject* New[] = {NewMaster, NewLayer};
        for (int32 K = 0; K < 2; ++K)
        {
            auto X = WSAObject(Old[K]), Y = WSAObject(New[K]);
            auto XP = X->GetObjectField(TEXT("properties")), YP = Y->GetObjectField(TEXT("properties"));
            if (!XP->HasField(TEXT("StateId")) || !YP->HasField(TEXT("StateId"))) return false;
            YP->SetStringField(TEXT("StateId"), Str(XP, TEXT("StateId")));
            if (K == 0)
            {
                if (!WGRLightingFields(XP, YP, Master->bUsedWithStaticLighting, NewMaster->bUsedWithStaticLighting) ||
                    !XP->HasField(TEXT("LightingGuid")) || !YP->HasField(TEXT("LightingGuid")) ||
                    !XP->HasField(TEXT("MaterialFunctionInfos")) || !YP->HasField(TEXT("MaterialFunctionInfos"))) return false;
                YP->SetStringField(TEXT("bUsedWithStaticLighting"), Str(XP, TEXT("bUsedWithStaticLighting")));
                YP->SetStringField(TEXT("LightingGuid"), Str(XP, TEXT("LightingGuid")));
                // Typed dependency identities above validate every element before normalizing its export text.
                YP->SetStringField(TEXT("MaterialFunctionInfos"), Str(XP, TEXT("MaterialFunctionInfos")));
            }
            if (!Compare.Same(MRValue(X), MRValue(Y))) return false;
            auto* OE = Compare.Expressions(Old[K]); auto* NE = Compare.Expressions(New[K]);
            if (!OE || !NE || OE->Num() != NE->Num()) return false;
            for (int32 I = 0; I < OE->Num(); ++I)
            {
                auto* O = (*OE)[I]; auto* N = (*NE)[I]; auto L = WSAObject(O), R = WSAObject(N);
                if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(N)) if (!WSAInterfaces(C)) return false;
                if (K == 1) for (const auto& Alias : WSAliases) if (N->GetName() == Alias.Node)
                {
                    auto LP = L->GetObjectField(TEXT("properties")), RP = R->GetObjectField(TEXT("properties"));
                    if (!WSAField(LP, TEXT("ParameterName"), Alias.OldName) || !WSAField(RP, TEXT("ParameterName"), Alias.NewName) ||
                        !WSAField(LP, TEXT("ExpressionGUID"), Alias.Guid) || !WSAField(RP, TEXT("ExpressionGUID"), Alias.Guid)) return false;
                    RP->SetStringField(TEXT("ParameterName"), Alias.OldName); ++Aliased;
                }
                if (!Compare.Same(MRValue(L), MRValue(R))) return false;
            }
        }
        return Aliased == 6;
    }
    bool Compile()
    {
        if (!Equivalent() || !Unchanged(true) || !Proof.Files(Files)) return false;
        int32 Count = 0;
        for (auto* Instance : {One, Three}) for (auto Q : {EMaterialQualityLevel::Low, EMaterialQualityLevel::Medium, EMaterialQualityLevel::High})
        {
            if (Resource) return false;
            Resource = new FWSAOrdinaryResource;
            Resource->SetMaterial(NewMaster, Q, true, ERHIFeatureLevel::ES2, Instance);
            FMaterialShaderMapId Requested;
            Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
            FStaticParameterSet Effective; Instance->GetStaticParameterValues(Effective);
            if (Resource->IsPersistent() || Resource->IsUsedWithStaticLighting() || Resource->IsSpecialEngineMaterial() ||
                Requested.BaseMaterialId != NewMaster->StateId || Requested.QualityLevel != Q || Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
                !FWeaponRepair().Same(MRValue(MRStatic(Effective)), MRValue(MRStatic(Requested.ParameterSet))) ||
                !Requested.ReferencedFunctions.Contains(NewLayer->StateId) || Requested.ReferencedFunctions.Contains(Layer->StateId)) return false;
            const bool Cached = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
            Resource->FinishCompilation();
            if (!WSADrain() || !Resource->IsCompilationFinished()) return false;
            auto* Map = Resource->GetGameThreadShaderMap();
            const bool MapOK = Cached && Resource->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() && Map->CompiledSuccessfully() &&
                Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL && WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId()) && Resource->GetCompileErrors().Num() == 0;
            // A failed map must not be used as a uniform-array or sampler observation.
            const bool Valid = MapOK && Resource->GetSamplerUsage() >= 0 && Resource->GetSamplerUsage() <= 16 &&
                Resource->GetUniform2DTextureExpressions().Num() == 14 && Resource->GetUniformCubeTextureExpressions().Num() == 0;
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_GRENADE_REPAIR shader material=%s quality=%d valid=%d ordinaryLightingPolicy=1 staticLighting=0 persistent=0"),
                *Instance->GetOutermost()->GetName(), int32(Q), Valid ? 1 : 0);
            delete Resource; Resource = nullptr;
            if (!Valid || !Equivalent() || !Unchanged(true) || !Proof.Files(Files)) return false;
            ++Count;
        }
        return Count == 6;
    }
    bool SaveAll(const FString& BeforeHash)
    {
        UObject* Assets[] = {NewLayer, NewMaster, One};
        for (int32 I = 0; I < 3; ++I)
        {
            UObject* Asset = Assets[I]; const FString Package = Proof.Saves[I];
            if (!Asset || Asset->GetOutermost()->GetName() != Package || !Equivalent() || !Unchanged(true) ||
                !Proof.Files(Files) || !Proof.Old.External(Proof.BeforePath, false) ||
                !HashFile(Proof.BeforePath).Equals(BeforeHash, ESearchCase::IgnoreCase) || !Proof.Policy.Check(Package)) return false;
            Asset->MarkPackageDirty();
            if (!UPackage::SavePackage(Asset->GetOutermost(), Asset, RF_Public | RF_Standalone, *Proof.Policy.Files.FindChecked(Package.ToLower()))) return false;
            const FString H = HashFile(Proof.Policy.Files.FindChecked(Package.ToLower()));
            if (!WTUSHA1(H) || (I == 2 && H.Equals(Str(Proof.Expected, *Package), ESearchCase::IgnoreCase))) return false;
            Files->SetStringField(Package, H.ToLower());
            UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_GRENADE_REPAIR saved package=%s ordinal=%d"), *Package, I + 1);
            if (!Proof.Files(Files) || !Equivalent() || !Unchanged(true)) return false;
        }
        return Proof.FinalTable(Files);
    }
};

static bool WGRBeforeShape(const TSharedPtr<FJsonObject>& J)
{
    const TSharedPtr<FJsonObject>* Objects = nullptr; const TSharedPtr<FJsonObject>* Instances = nullptr;
    const TSharedPtr<FJsonObject>* Dirty = nullptr;
    return J.IsValid() && J->TryGetObjectField(TEXT("objects"), Objects) && (*Objects)->Values.Num() > 18 && (*Objects)->Values.Num() <= 8192 &&
        J->TryGetObjectField(TEXT("instances"), Instances) && (*Instances)->Values.Num() == 18 &&
        J->TryGetObjectField(TEXT("protected_dirty"), Dirty) && (*Dirty)->Values.Num() > 0;
}

// New generation admission only. Do not call the old parent/hash verifier here.
static int32 WGRFreshVerify(FWGRProof& Proof, const FString& Params)
{
    FString AfterHash;
    TSharedPtr<FJsonObject> A, B;
    const TSharedPtr<FJsonObject>* Table = nullptr; const TSharedPtr<FJsonObject>* BeforeRef = nullptr;
    const TSharedPtr<FJsonObject>* Snapshot = nullptr; const TSharedPtr<FJsonObject>* Ids = nullptr;
    if (!FParse::Value(*Params, TEXT("GrenadeAftermathSHA1="), AfterHash) || !WTUSHA1(AfterHash) ||
        !HashFile(Proof.AfterPath).Equals(AfterHash, ESearchCase::IgnoreCase) || !Proof.ReadJsonBounded(Proof.AfterPath, A) ||
        Str(A, TEXT("schema")) != TEXT("ut4-grenade-repair-aftermath-v1") || Str(A, TEXT("spec_sha1")) != WGRSpecSHA1 ||
        !Str(A, TEXT("preparation_sha1")).Equals(Proof.PreparationHash, ESearchCase::IgnoreCase) ||
        !Str(A, TEXT("receipt_sha1")).Equals(Proof.ReceiptHash, ESearchCase::IgnoreCase) ||
        !WGRBool(A, TEXT("complete"), true) || !WGRNumber(A, TEXT("saved"), 3) || !WGRNumber(A, TEXT("semantic_instances"), 18) ||
        !WGRNumber(A, TEXT("shader_resources"), 6) || !WGRBool(A, TEXT("static_lighting"), false) || !WGRBool(A, TEXT("runtime_acceptance"), false) ||
        !A->TryGetObjectField(TEXT("package_sha1"), Table) || !Proof.FinalTable(*Table) || !Proof.Files(*Table) ||
        !A->TryGetObjectField(TEXT("before"), BeforeRef) || !A->TryGetObjectField(TEXT("clone_ids"), Ids) ||
        !Full(Str(*BeforeRef, TEXT("path"))).Equals(Full(Proof.BeforePath), ESearchCase::IgnoreCase) || !WTUSHA1(Str(*BeforeRef, TEXT("sha1"))) ||
        !HashFile(Proof.BeforePath).Equals(Str(*BeforeRef, TEXT("sha1")), ESearchCase::IgnoreCase) || !Proof.ReadJsonBounded(Proof.BeforePath, B) ||
        Str(B, TEXT("schema")) != TEXT("ut4-grenade-repair-before-v1") || Str(B, TEXT("spec_sha1")) != WGRSpecSHA1 ||
        !Str(B, TEXT("preparation_sha1")).Equals(Proof.PreparationHash, ESearchCase::IgnoreCase) ||
        !B->TryGetObjectField(TEXT("snapshot"), Snapshot) || !WGRBeforeShape(*Snapshot)) return WGRStop(TEXT("fresh-aftermath"));
    // Check the entire selected set before the first load; dependency loads are normal UE loads.
    for (const auto& KV : (*Table)->Values) if (FindPackage(nullptr, *KV.Key)) return WGRStop(TEXT("fresh-already-loaded"), KV.Key);
    for (const auto& KV : (*Table)->Values)
    {
        UClass* Class = Proof.Instances.Contains(KV.Key) ? UMaterialInstanceConstant::StaticClass() :
            (KV.Key == WGRMaster() || KV.Key == WTUMaster() ? UMaterial::StaticClass() : UMaterialFunction::StaticClass());
        UObject* O = StaticLoadObject(Class, nullptr, *ObjectPath(KV.Key));
        if (!WGRReady(O) || O->GetClass() != Class || O->GetPathName() != ObjectPath(KV.Key)) return WGRStop(TEXT("fresh-load"), KV.Key);
    }
    FWGRState State(Proof);
    if (!State.Gather()) return WGRStop(TEXT("fresh-sources"));
    State.NewMaster = FindObject<UMaterial>(nullptr, *ObjectPath(WGRMaster()));
    State.NewLayer = FindObject<UMaterialFunction>(nullptr, *ObjectPath(WGRLayer()));
    State.Hold(State.One); State.Hold(State.Three); State.Hold(State.NewMaster); State.Hold(State.NewLayer);
    State.Before = *Snapshot; State.Ids = *Ids; State.Files = *Table;
    auto Initial = State.Snapshot(true);
    if (!Initial.IsValid()) return WGRStop(TEXT("fresh-snapshot"));
    State.DirtyBaseline = Initial->GetObjectField(TEXT("protected_dirty"));
    if (!State.Equivalent() || !State.Unchanged(true) || !Proof.Files(State.Files) || !State.Compile() || !State.Close() ||
        !State.Equivalent() || !State.Unchanged(true) || !Proof.Files(State.Files) ||
        !Proof.Old.External(Proof.BeforePath, false) || !Proof.Old.External(Proof.AfterPath, false) ||
        !HashFile(Proof.BeforePath).Equals(Str(*BeforeRef, TEXT("sha1")), ESearchCase::IgnoreCase) ||
        !HashFile(Proof.AfterPath).Equals(AfterHash, ESearchCase::IgnoreCase)) return WGRStop(TEXT("fresh-final"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_GRENADE_REPAIR complete mode=verify saved=0 packages=25 semanticInstances=18 shaderResources=6 runtimeAcceptance=0"));
    return 0;
}

static int32 WeaponGrenadeRepair(const FString& Params, bool Verify)
{
    const bool Apply = FParse::Param(*Params, TEXT("GrenadeApply"));
    if (!GIsEditor || !IsRunningCommandlet() || !IsInGameThread() || !FApp::CanEverRender() || !GShaderCompilingManager ||
        FParse::Param(*Params, TEXT("NoDependsGathering")) || (Verify && Apply)) return WGRStop(TEXT("admission"));
    FWGRProof Proof;
    if (!Proof.Read(Params, Verify)) return WGRStop(TEXT("preparation"));
    if (Verify) return WGRFreshVerify(Proof, Params);
    if (!Proof.Files(Proof.InitialFiles()) || WeaponTessellationUpgrade(Params, true) != 0) return WGRStop(TEXT("old-full-verifier"));
    FWGRState State(Proof);
    if (!State.Gather() || !State.CloneAbsent()) return WGRStop(TEXT("source-set"));
    State.Before = State.Snapshot(false);
    if (!WGRBeforeShape(State.Before)) return WGRStop(TEXT("before-snapshot"));
    State.DirtyBaseline = State.Before->GetObjectField(TEXT("protected_dirty"));
    if (!State.TextureContracts() || !State.Unchanged(false) || !Proof.Files(State.Files)) return WGRStop(TEXT("source-contract"));
    if (!Apply)
    {
        if (!State.Close() || !State.Unchanged(false) || !Proof.Files(State.Files)) return WGRStop(TEXT("preflight-final"));
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_GRENADE_REPAIR preflight saved=0 packages=23 newDestinationsAbsent=2 semanticInstances=18 runtimeAcceptance=0"));
        return 0;
    }
    FWGREvidence BeforeEvidence, AfterEvidence;
    // Reserve BOTH files before any graph mutation. No retry adopts either file.
    if (!Proof.Old.External(Proof.BeforePath, true) || !Proof.Old.External(Proof.AfterPath, true) ||
        !BeforeEvidence.Open(Proof.BeforePath) || !AfterEvidence.Open(Proof.AfterPath)) return WGRStop(TEXT("reserve-evidence"));
    auto B = WGRObject();
    B->SetStringField(TEXT("schema"), TEXT("ut4-grenade-repair-before-v1")); B->SetStringField(TEXT("spec_sha1"), WGRSpecSHA1);
    B->SetStringField(TEXT("preparation_sha1"), Proof.PreparationHash.ToLower()); B->SetObjectField(TEXT("snapshot"), State.Before);
    B->SetBoolField(TEXT("one_p_dirty_before"), State.One->GetOutermost()->IsDirty());
    if (!BeforeEvidence.Write(B) || !BeforeEvidence.Close()) return WGRStop(TEXT("before-write"));
    const FString BeforeHash = HashFile(Proof.BeforePath);
    if (!WTUSHA1(BeforeHash) || !State.Prepare()) return WGRStop(TEXT("prepare-graphs"));
    if (!State.Compile()) return WGRStop(TEXT("compile-six"));
    if (!State.SaveAll(BeforeHash)) return WGRStop(TEXT("save-three"));
    if (!State.Close() || !State.Equivalent() || !State.Unchanged(true) || !Proof.Files(State.Files) ||
        !Proof.Old.External(Proof.BeforePath, false) || !HashFile(Proof.BeforePath).Equals(BeforeHash, ESearchCase::IgnoreCase)) return WGRStop(TEXT("after-save"));
    auto A = WGRObject(), Ref = WGRObject();
    Ref->SetStringField(TEXT("path"), Full(Proof.BeforePath)); Ref->SetStringField(TEXT("sha1"), BeforeHash.ToLower());
    A->SetStringField(TEXT("schema"), TEXT("ut4-grenade-repair-aftermath-v1")); A->SetStringField(TEXT("spec_sha1"), WGRSpecSHA1);
    A->SetStringField(TEXT("preparation_sha1"), Proof.PreparationHash.ToLower()); A->SetStringField(TEXT("receipt_sha1"), Proof.ReceiptHash.ToLower());
    A->SetObjectField(TEXT("before"), Ref); A->SetObjectField(TEXT("package_sha1"), State.Files); A->SetObjectField(TEXT("clone_ids"), State.Ids);
    A->SetBoolField(TEXT("complete"), true); A->SetNumberField(TEXT("saved"), 3); A->SetNumberField(TEXT("semantic_instances"), 18);
    A->SetNumberField(TEXT("shader_resources"), 6); A->SetBoolField(TEXT("static_lighting"), false); A->SetBoolField(TEXT("runtime_acceptance"), false);
    A->SetBoolField(TEXT("one_p_dirty_after"), State.One->GetOutermost()->IsDirty());
    if (!AfterEvidence.Write(A) || !AfterEvidence.Close()) return WGRStop(TEXT("aftermath-write"));
    const FString AfterHash = HashFile(Proof.AfterPath);
    if (!WTUSHA1(AfterHash) || !Proof.Old.External(Proof.AfterPath, false) || !Proof.Files(State.Files)) return WGRStop(TEXT("aftermath-check"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_GRENADE_REPAIR complete mode=apply saved=3 packages=25 semanticInstances=18 shaderResources=6 runtimeAcceptance=0 aftermath_sha1=%s"), *AfterHash);
    return 0;
}
