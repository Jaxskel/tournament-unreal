// Original, generation-pinned one-master operation. Include after WeaponFidelityRepair.h.
// Does not refresh functions, reparent instances, or change the legacy save allowlist.
static const TCHAR* WTUProofSHA1 = TEXT("f86076971bcdd3f4adee45ca27d1ec22da9f5f9b");
static const TCHAR* WTUOldMasterSHA1 = TEXT("5d82999ff94ee56567fdcab1bd7918c5f533a7b2");
static FString WTUMaster() { return TEXT("/Game/HTML5Compat/Weapons/V1/M_WeaponsBase"); }
static bool WTUSHA1(const FString& S)
{
    if (S.Len() != 40) return false;
    for (int32 I = 0; I < S.Len(); ++I)
    { const TCHAR C = S[I]; if (!((C >= '0' && C <= '9') || (C >= 'a' && C <= 'f') || (C >= 'A' && C <= 'F'))) return false; }
    return true;
}
struct FWeaponTessProof
{
    FString File;
    TSharedPtr<FJsonObject> Json;
    TMap<FString, FString> CurrentFiles, CurrentHashes;
    bool Snapshot(const TSharedPtr<FJsonObject>& J) const
    {
        const FString Path = Str(J, TEXT("path")), Hash = Str(J, TEXT("sha1"));
        return WTUSHA1(Hash) && Physical(Path, false) && HashFile(Path).Equals(Hash, ESearchCase::IgnoreCase);
    }
    bool Read(const FString& Path)
    {
        File = Path;
        if (!Physical(File, false) || !HashFile(File).Equals(WTUProofSHA1, ESearchCase::IgnoreCase) || !ReadJson(File, Json) ||
            Str(Json, TEXT("schema")) != TEXT("weapon-uv0-current23-capture-v1") ||
            !Full(Str(Json, TEXT("project"))).Equals(Full(FPaths::GameDir()), ESearchCase::IgnoreCase) ||
            !Full(Str(Json, TEXT("content"))).Equals(Full(FPaths::GameContentDir()), ESearchCase::IgnoreCase)) return false;
        // The entire immutable capture is pinned, including roles, original paths,
        // all four raw success artifacts, 9 matching Apply/Verify hashes, and identities.
        // Native admission rechecks physical files+bytes; captured inode/time metadata
        // is evidence, not a claim that this C++ reader implements Python's stat API.
        const auto& Rows = Json->GetArrayField(TEXT("rows"));
        if (Rows.Num() != 23 || Json->GetArrayField(TEXT("original_dependencies")).Num() != 48 ||
            Json->GetArrayField(TEXT("artifacts")).Num() != 4) return false;
        for (const auto& V : Rows)
        {
            auto J = V->AsObject(); const FString P = Str(J, TEXT("package"));
            const FString F = Full(Str(J, TEXT("path"))), H = Str(J, TEXT("sha1"));
            if (!GamePackage(P) || CurrentFiles.Contains(P) || !WTUSHA1(H) ||
                !F.Equals(Full(FPackageName::LongPackageNameToFilename(P, TEXT(".uasset"))), ESearchCase::IgnoreCase)) return false;
            CurrentFiles.Add(P, F); CurrentHashes.Add(P, H);
        }
        const FString* Old = CurrentHashes.Find(WTUMaster());
        return Old && Old->Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase);
    }
    bool Check(const FString& MasterHash) const
    {
        if (!WTUSHA1(MasterHash) || !Physical(File, false) || !HashFile(File).Equals(WTUProofSHA1, ESearchCase::IgnoreCase)) return false;
        for (const auto& KV : CurrentFiles)
        {
            const FString H = KV.Key == WTUMaster() ? MasterHash : CurrentHashes.FindChecked(KV.Key);
            if (!Physical(KV.Value, false) || !HashFile(KV.Value).Equals(H, ESearchCase::IgnoreCase))
                return Fail(TEXT("WeaponTess current generation drift: ") + KV.Key);
        }
        for (const TCHAR* Key : {TEXT("original_dependencies"), TEXT("artifacts")})
            for (const auto& V : Json->GetArrayField(Key)) if (!Snapshot(V->AsObject())) return Fail(FString(TEXT("WeaponTess proof input drift: ")) + Key);
        return Snapshot(Json->GetObjectField(TEXT("recipe"))) && Snapshot(Json->GetObjectField(TEXT("baseline")));
    }
    bool External(const FString& Path, bool Missing) const
    {
        const FString P = Full(Path);
        // All evidence is outside BOTH engine trees and every Content directory.
        const FString OriginalEngine = FPaths::GetPath(Full(Str(Json, TEXT("original"))));
        return !Within(P, Full(Str(Json, TEXT("root")))) && !Within(P, OriginalEngine) &&
            !P.ToLower().Contains(TEXT("/content/")) && !P.ToLower().EndsWith(TEXT("/content")) && Physical(P, Missing);
    }
};

// Reserve evidence BEFORE graph mutation. CREATE_NEW is exclusive; a failure or
// crash leaves the reserved/partial file and any saved asset for explicit review.
// No overwrite, rollback, retry adoption, or claim of atomic asset+receipt commit.
struct FWeaponTessEvidence
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
    bool Write(const FString& Text)
    {
#if PLATFORM_WINDOWS
        FTCHARToUTF8 Bytes(*Text);
        if (Handle == INVALID_HANDLE_VALUE || Bytes.Length() > 65536) return false;
        DWORD Written = 0;
        return WriteFile(Handle, Bytes.Get(), Bytes.Length(), &Written, nullptr) &&
            Written == static_cast<DWORD>(Bytes.Length()) && FlushFileBuffers(Handle);
#else
        return false;
#endif
    }
    ~FWeaponTessEvidence()
    {
#if PLATFORM_WINDOWS
        if (Handle != INVALID_HANDLE_VALUE) CloseHandle(Handle);
#endif
    }
};

static int32 WeaponTessellationUpgrade(const FString& Params, bool Verify)
{
    FString ProofPath, ReceiptPath, Backup, Aftermath, AftermathHash;
    if (!GIsEditor || !IsInGameThread() || (!Verify && !FApp::CanEverRender()) ||
        !FParse::Param(*Params, TEXT("WeaponUV0")) || !FParse::Param(*Params, TEXT("WeaponTess1")) ||
        !FParse::Value(*Params, TEXT("WeaponCurrentProof="), ProofPath) ||
        !FParse::Value(*Params, TEXT("WeaponTessReceipt="), ReceiptPath) ||
        !FParse::Value(*Params, TEXT("WeaponMasterBackup="), Backup) ||
        !FParse::Value(*Params, TEXT("WeaponTessAftermath="), Aftermath) ||
        (Verify && !FParse::Value(*Params, TEXT("WeaponTessAftermathSHA1="), AftermathHash))) return WFRStop(TEXT("tess-admission"));
    FWeaponTessProof Proof;
    if (!Proof.Read(ProofPath)) return WFRStop(TEXT("tess-proof"));
    FString MasterHash = WTUOldMasterSHA1;
    if (!Proof.External(Backup, false) || !HashFile(Backup).Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase) ||
        !Proof.External(Aftermath, !Verify) || Full(Aftermath).Equals(Full(Backup), ESearchCase::IgnoreCase)) return WFRStop(TEXT("tess-evidence-paths"));
    if (Verify)
    {
        TSharedPtr<FJsonObject> A;
        const TSharedPtr<FJsonObject>* Rows = nullptr; bool Complete = false; double Saved = 0;
        if (!WTUSHA1(AftermathHash) || !HashFile(Aftermath).Equals(AftermathHash, ESearchCase::IgnoreCase) || !ReadJson(Aftermath, A) ||
            Str(A, TEXT("schema")) != TEXT("weapon-tess-one-master-aftermath-v1") || Str(A, TEXT("proof_sha1")) != WTUProofSHA1 ||
            Str(A, TEXT("master")) != WTUMaster() || Str(A, TEXT("before_sha1")) != WTUOldMasterSHA1 ||
            Str(A, TEXT("variant")) != TEXT("es2-uv0-tess1") || !A->TryGetBoolField(TEXT("complete"), Complete) || !Complete ||
            !A->TryGetNumberField(TEXT("saved"), Saved) || Saved != 1 || !A->TryGetObjectField(TEXT("package_sha1"), Rows))
            return WFRStop(TEXT("tess-aftermath"));
        MasterHash = Str(A, TEXT("after_sha1"));
        if (!WTUSHA1(MasterHash) || MasterHash.Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase) || (*Rows)->Values.Num() != 23) return WFRStop(TEXT("tess-aftermath-scope"));
        for (const auto& KV : Proof.CurrentHashes)
            if (!Str(*Rows, *KV.Key).Equals(KV.Key == WTUMaster() ? MasterHash : KV.Value, ESearchCase::IgnoreCase)) return WFRStop(TEXT("tess-aftermath-row"), KV.Key);
    }
    else if (FPaths::FileExists(Aftermath)) return WFRStop(TEXT("tess-aftermath-exists"));
    if (!Proof.Check(MasterHash)) return WFRStop(TEXT("tess-generation-before"));
    FSavePolicy Policy; TSet<FString> OnlyMaster; OnlyMaster.Add(WTUMaster().ToLower());
    if (!Policy.Read(ReceiptPath, ProofPath, OnlyMaster) ||
        !Policy.OriginalRoot.Equals(Full(Str(Proof.Json, TEXT("original"))), ESearchCase::IgnoreCase)) return WFRStop(TEXT("tess-one-save-policy"));
    const FString ReceiptHash = HashFile(ReceiptPath);
    // Full existing seven-node Verify is mandatory before an upgrade. A fresh
    // eight-node Verify is reachable only through this proof/aftermath admission.
    FWeaponRepair R;
    if (WeaponFidelityRepair(Params, true, &R, Verify) != 0) return WFRStop(TEXT("tess-existing-state"));
    auto* Master = CastChecked<UMaterial>(R.Objects.FindChecked(WTUMaster()));
    auto* Original = CastChecked<UMaterial>(R.Objects.FindChecked(WRMaster()));
    if (Original->D3D11TessellationMode != MTM_NoTessellation || Master->D3D11TessellationMode != MTM_NoTessellation ||
        !Proof.Check(MasterHash)) return WFRStop(TEXT("tess-no-tessellation-or-drift"));
    if (Verify)
    {
        if (!HashFile(Aftermath).Equals(AftermathHash, ESearchCase::IgnoreCase) ||
            !HashFile(ReceiptPath).Equals(ReceiptHash, ESearchCase::IgnoreCase) ||
            !HashFile(Backup).Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase)) return WFRStop(TEXT("tess-verify-evidence-drift"));
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_TESS complete mode=verify variant=es2-uv0-tess1 saved=0 packages=23"));
        return 0;
    }
    FWeaponTessEvidence Evidence;
    if (!Proof.External(Aftermath, true) || !Evidence.Open(Aftermath)) return WFRStop(TEXT("tess-reserve-evidence"));
    auto* Set = CastChecked<UMaterialExpressionSetMaterialAttributes>(R.Node(Master, TEXT("TournamentES2WPO"), TEXT("MaterialExpressionSetMaterialAttributes")));
    auto* One = R.Add<UMaterialExpressionConstant>(Master, TEXT("TournamentES2TessellationOne"));
    if (!One) return WFRStop(TEXT("tess-add-one"));
    One->R = 1.0f;
    Set->Inputs.SetNum(4); Set->Inputs[3].Expression = One;
    Set->AttributeSetTypes.Add(FMaterialAttributeDefinitionMap::GetID(MP_TessellationMultiplier));
    Master->PostEditChange();
    R.Tess1 = true; // R.Verify stays true: all reused validators are get-only.
    auto* Expected = R.Baseline.Find(WRMaster());
    const FString MF = TEXT("/Game/RestrictedAssets/Weapons/Global/Material/MF/");
    if (!Expected || !R.WPO(Master) ||
        !R.AO(R.Objects.FindChecked(R.Clones.FindChecked(MF + TEXT("MF_BaseShader_Textures"))), TEXT("MaterialExpressionPrecomputedAOMask_0")) ||
        !R.AO(R.Objects.FindChecked(R.Clones.FindChecked(MF + TEXT("MF_Dirt"))), TEXT("MaterialExpressionPrecomputedAOMask_4")) ||
        WFRFinalChecks(R, Master, Expected) != 0 ||
        !Proof.Check(WTUOldMasterSHA1) || !Proof.External(Backup, false) || !HashFile(Backup).Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase) ||
        !Physical(ReceiptPath, false) || !HashFile(ReceiptPath).Equals(ReceiptHash, ESearchCase::IgnoreCase) || !Policy.Check(WTUMaster())) return WFRStop(TEXT("tess-final-before-save"));
    // The only save in this operation. No function refresh and no MIC writes.
    if (!Policy.Save(Master)) return WFRStop(TEXT("tess-save"));
    MasterHash = HashFile(Policy.Files.FindChecked(WTUMaster().ToLower()));
    if (MasterHash.Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase) || !Proof.Check(MasterHash) ||
        !Proof.External(Backup, false) || !HashFile(Backup).Equals(WTUOldMasterSHA1, ESearchCase::IgnoreCase) ||
        !Physical(ReceiptPath, false) || !HashFile(ReceiptPath).Equals(ReceiptHash, ESearchCase::IgnoreCase)) return WFRStop(TEXT("tess-post-save-drift"));
    TSharedPtr<FJsonObject> A = MakeShareable(new FJsonObject), Rows = MakeShareable(new FJsonObject);
    A->SetStringField(TEXT("schema"), TEXT("weapon-tess-one-master-aftermath-v1"));
    A->SetStringField(TEXT("proof_sha1"), WTUProofSHA1); A->SetStringField(TEXT("master"), WTUMaster());
    A->SetStringField(TEXT("before_sha1"), WTUOldMasterSHA1); A->SetStringField(TEXT("after_sha1"), MasterHash.ToLower());
    A->SetStringField(TEXT("variant"), TEXT("es2-uv0-tess1")); A->SetBoolField(TEXT("complete"), true); A->SetNumberField(TEXT("saved"), 1);
    for (const auto& KV : Proof.CurrentHashes) Rows->SetStringField(KV.Key, KV.Key == WTUMaster() ? MasterHash.ToLower() : KV.Value);
    A->SetObjectField(TEXT("package_sha1"), Rows);
    FString Text;
    if (!FJsonSerializer::Serialize(A.ToSharedRef(), TJsonWriterFactory<>::Create(&Text)) || !Evidence.Write(Text)) return WFRStop(TEXT("tess-aftermath-write"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_TESS complete mode=apply variant=es2-uv0-tess1 saved=1 packages=23 master_sha1=%s"), *MasterHash);
    return 0;
}
