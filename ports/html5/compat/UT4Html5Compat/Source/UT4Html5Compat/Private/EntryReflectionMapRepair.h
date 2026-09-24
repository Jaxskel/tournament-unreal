// Original fixed-one-map integration. Include INSIDE UT4Compat after EntryReflectionDiagnostic.h.
// Launcher owns the 15 selected maps + 15 originals + 5 junctions audit and the flushed
// external backup. Native code checks only the selected map, its original/backup and proof.
// No rollback: a failed save may leave a partial/changed selected map. Never auto-retry.
// A zero-valued valid HDR payload is persistence evidence, not visual success.
// Receipt digest is diagnostic4 provenance ONLY, never cross-run admission.
static const TCHAR* ERMBaselineDigest = TEXT("72c5d75b7c786ec992026ef11eeb3a758431e01c");
static const TCHAR* ERMDiagnosticSHA1 = TEXT("916a90760ebbabc25d878a85ea46692c076495c4");
// SHA256 of the same raw diagnostic4 result: def14970c3b4ba71f4826ce856dcf6c833834f22175dbae531ed057e0969f687.

static bool ERMSaveAdmission(bool Editor, bool Commandlet, bool Thread, bool Render,
    bool Unattended, bool ExactWorld, bool TargetOK, bool ShaderIdle, bool Settings,
    bool Pins, bool Authored, bool Payload, bool StateAdvanced)
{
    return Editor && !Commandlet && Thread && Render && Unattended && ExactWorld &&
        TargetOK && ShaderIdle && Settings && Pins && Authored && Payload && StateAdvanced;
}
static bool ERMSHA1(const FString& S)
{
    if (S.Len() != 40) return false;
    for (int32 I = 0; I < S.Len(); ++I)
        if (!((S[I] >= TCHAR('0') && S[I] <= TCHAR('9')) || (S[I] >= TCHAR('a') && S[I] <= TCHAR('f')))) return false;
    return true;
}
// Cross-run proof: exact inspect1/2 raw JSONL, not diagnostic4's digest-only baseline.
// Canonicalization replaces only the exact level's GUID with 32 zeroes in a COPY.
static const TCHAR* ERMCanonicalDigest = TEXT("4fb768cf9ba362b390affa07c74d3237ab88ab85");
static const TCHAR* ERMInspect1SHA1 = TEXT("cf5e348674462e227410397e4333dec8503b457d");
static const TCHAR* ERMInspect2SHA1 = TEXT("201e78123abc635ed7d1114ab3d8317c0cebf151");
static const TCHAR* ERMLevelPath = TEXT("/Game/RestrictedAssets/Maps/UT-Entry.UT-Entry:PersistentLevel");
static const TCHAR* ERMRegistryPath = TEXT("/Game/RestrictedAssets/Maps/UT-Entry.MapBuildDataRegistry");
static bool ERMGuid(const FString& S)
{
    if (S.Len()!=32) return false;
    bool Nonzero=false;
    for (int32 I=0;I<S.Len();++I)
    {
        const TCHAR C=S[I];
        if (!((C>='0' && C<='9') || (C>='a' && C<='f') || (C>='A' && C<='F'))) return false;
        Nonzero=Nonzero || C!='0';
    }
    return Nonzero;
}
static bool ERMCanonicalLevelRow(const FString& Path,const FString& Row,FString& Copy,FString& Guid)
{
    if (Path!=ERMLevelPath || !Row.StartsWith(TEXT("/Script/Engine.Level\n"),ESearchCase::CaseSensitive)) return false;
    const FString Prefix=TEXT("\nLevelBuildDataId[0]=");
    const int32 At=Row.Find(Prefix,ESearchCase::CaseSensitive);
    const int32 Any=Row.Find(TEXT("\nLevelBuildDataId["),ESearchCase::CaseSensitive);
    if (At==INDEX_NONE || Any!=At || Row.Find(TEXT("\nLevelBuildDataId["),ESearchCase::CaseSensitive,ESearchDir::FromStart,At+1)!=INDEX_NONE) return false;
    const int32 Start=At+Prefix.Len();
    if (Start+32>=Row.Len() || Row[Start+32]!='\n') return false;
    Guid=Row.Mid(Start,32);
    if (!ERMGuid(Guid)) return false;
    Copy=Row.Left(Start)+TEXT("00000000000000000000000000000000")+Row.Mid(Start+32);
    return true;
}
static FString ERMRowsDigest(const TMap<FString,FString>& Rows)
{
    TArray<FString> Keys; Rows.GetKeys(Keys); Keys.Sort(); FSHA1 Hash;
    const uint8 Separator=0xff;
    for (const FString& Key : Keys)
    {
        const FString& Row=Rows.FindChecked(Key);
        Hash.Update(reinterpret_cast<const uint8*>(*Key),Key.Len()*sizeof(TCHAR)); Hash.Update(&Separator,1);
        Hash.Update(reinterpret_cast<const uint8*>(*Row),Row.Len()*sizeof(TCHAR)); Hash.Update(&Separator,1);
    }
    uint8 Bytes[20]; Hash.Final(); Hash.GetHash(Bytes); return BytesToHex(Bytes,20).ToLower();
}
static bool ERMCanonical(const TMap<FString,FString>& Rows,FString& Digest,FString& Guid)
{
    const FString* Level=Rows.Find(ERMLevelPath); FString Normalized;
    if (!Level || !ERMCanonicalLevelRow(ERMLevelPath,*Level,Normalized,Guid)) return false;
    TMap<FString,FString> Copy=Rows; Copy.FindChecked(ERMLevelPath)=Normalized;
    Digest=ERMRowsDigest(Copy); return true;
}
// Matched ORIGINAL synchronous-load snapshots: 60 objects, only generated GUID differs.
static const TCHAR* ERMLoadedDigest=TEXT("ac7d121f2682ce525598ec3f9e990ca4ea1c6337");
static const TCHAR* ERMLoaded1SHA1=TEXT("0113fb6a81bcf961d743db433c346a2fa0e046c1");
static const TCHAR* ERMLoaded2SHA1=TEXT("306cde051c6b1d7201aa387be6b619492d193900");
static const TCHAR* ERMPreservationContract=TEXT("ut4-entry-loaded60-registry-v1");
// Exact reflected registry row from BOTH original editor inspections; custom data is separate.
static const TCHAR* ERMRegistryRow=TEXT("/Script/Engine.MapBuildDataRegistry\nLevelLightingQuality[0]=(INVALID)\n");
static bool ERMLoadedRowsAccepted(const TMap<FString,FString>& Rows,const FString& SavedGuid,FString& Digest)
{
    if (Rows.Num()!=61 || !ERMGuid(SavedGuid)) return false;
    const FString* Registry=Rows.Find(ERMRegistryPath);
    const FString* Level=Rows.Find(ERMLevelPath);
    FString Normalized,Guid;
    if (!Registry || *Registry!=ERMRegistryRow || !Level || !ERMCanonicalLevelRow(ERMLevelPath,*Level,Normalized,Guid) || Guid!=SavedGuid) return false;
    const FString Expected=TEXT("\nMapBuildData[0]=MapBuildDataRegistry'/Game/RestrictedAssets/Maps/UT-Entry.MapBuildDataRegistry'\n");
    const int32 At=Normalized.Find(Expected,ESearchCase::CaseSensitive);
    if (At==INDEX_NONE || Normalized.Find(TEXT("\nMapBuildData["),ESearchCase::CaseSensitive)!=At ||
        Normalized.Find(TEXT("\nMapBuildData["),ESearchCase::CaseSensitive,ESearchDir::FromStart,At+1)!=INDEX_NONE) return false;
    // Only a COPY changes: remove the one new registry object/reference; GUID already canonical.
    Normalized=Normalized.Left(At)+TEXT("\nMapBuildData[0]=\n")+Normalized.Mid(At+Expected.Len());
    TMap<FString,FString> Copy=Rows; Copy.Remove(ERMRegistryPath); Copy.FindChecked(ERMLevelPath)=Normalized;
    Digest=ERMRowsDigest(Copy); return Digest==ERMLoadedDigest;
}

static bool ERMRegistryLinked(UWorld* World,const FString& Guid)
{
    if (!World || World->GetOutermost()->GetName()!=ERDPackage || !World->PersistentLevel || !ERMGuid(Guid)) return false;
    ULevel* Level=World->PersistentLevel;
    const UMapBuildDataRegistry* Registry=Level->MapBuildData;
    return Level->GetPathName()==ERMLevelPath && Level->GetClass()->GetPathName()==TEXT("/Script/Engine.Level") &&
        Level->LevelBuildDataId.IsValid() && Level->LevelBuildDataId.ToString()==Guid &&
        Registry && Registry->GetPathName()==ERMRegistryPath && Registry->GetOutermost()==World->GetOutermost() &&
        Registry->GetClass()->GetPathName()==TEXT("/Script/Engine.MapBuildDataRegistry") && Registry->GetLevelBuildData(Level->LevelBuildDataId)!=nullptr;
}
static bool ERMReloadIdentity(const FString& Raw,const FString& ExpectedRaw,const FString& Guid,const FString& SavedGuid)
{
    return ERMSHA1(Raw) && Raw==ExpectedRaw && ERMGuid(Guid) && Guid==SavedGuid;
}

static bool ERMSame(const FWURFile& A, const FWURFile& B)
{
    return A.Target == B.Target && A.Identity == B.Identity && A.Size == B.Size && A.SHA1 == B.SHA1;
}
static bool ERMUnchanged(const FWURFile& A)
{
    FWURFile B; return FWURFile::Inspect(A.Path, false, B) && ERMSame(A, B);
}
static bool ERMReadJSON(const FString& Path, const FString& SHA1, FWURFile& Pin, TSharedPtr<FJsonObject>& J)
{
    return ERMSHA1(SHA1) && FWURFile::Inspect(Path, false, Pin, nullptr, 65536) && Pin.SHA1 == SHA1 &&
        ReadJson(Path, J) && ERMUnchanged(Pin);
}
static FString ERMBrightness(UReflectionCaptureComponent* Target)
{
    const float Value = Target->GetAverageBrightness();
    if (!FMath::IsFinite(Value)) return FString();
    uint32 Bits = 0; FMemory::Memcpy(&Bits, &Value, sizeof(Bits));
    return FString::Printf(TEXT("%08x"), Bits);
}
static bool ERMObjectsEqual(const TMap<FString,FString>& A, const TMap<FString,FString>& B)
{
    if (A.Num() != B.Num()) return false;
    for (const auto& KV : A) { const FString* V = B.Find(KV.Key); if (!V || *V != KV.Value) return false; }
    return true;
}

// Original bounded archive, no proxy or FMemoryWriter. Encoding is fingerprint-only,
// not a package format: FNames are strings; UObject references are presence-byte + path.
// Referenced asset CONTENT is outside this hash (launcher pins protect external inputs).
// Exact traversal bytes are compared; no claim of canonical TMap/octree ordering.
// The cap bounds output storage, not serializer-owned temporary allocations.
// Equality starts at the migrated editor registry; it does not prove original legacy migration fidelity.
// Read-only probe: add -EntryMapRegistryProbe to the normal -EntryMapInspectOnly route.
static const TCHAR* ERMRegistrySchema=TEXT("ut4-entry-registry-bytes-v1");
class FERMRegistryWriter : public FArchive
{
public:
    TArray<uint8> Bytes;
    int64 Position=0, Limit;
    bool Failed=false;
    const UObject* Subject;
    UObject* Defaults;
    FERMRegistryWriter(const UObject* InSubject,UObject* InDefaults,int64 InLimit=16*1024*1024)
        : Limit(InLimit),Subject(InSubject),Defaults(InDefaults)
    {
        ArIsSaving=true; ArIsPersistent=true;
        if (Limit<=0 || Limit>16*1024*1024) { Reject(); return; }
        Bytes.Reserve(int32(Limit)); // bounded allocation; subsequent writes cannot exceed it
    }
    void Reject() { Failed=true; SetError(); }
    virtual void Serialize(void* Data,int64 Num) override
    {
        if (Failed) return;
        if (Num<0 || Position<0 || Position>Bytes.Num() || Position>Limit || Num>Limit-Position || (Num && !Data))
        { Reject(); return; }
        const int64 End=Position+Num;
        if (End>Bytes.Num()) Bytes.SetNumUninitialized(int32(End),false);
        if (Num) FMemory::Memcpy(Bytes.GetData()+Position,Data,SIZE_T(Num));
        Position=End;
    }
    virtual void Seek(int64 Offset) override
    {
        if (Failed) return;
        if (Offset<0 || Offset>Bytes.Num()) { Reject(); return; }
        Position=Offset;
    }
    virtual int64 Tell() override { return Position; }
    virtual int64 TotalSize() override { return Bytes.Num(); }
    virtual FString GetArchiveName() const override { return TEXT("EntryRegistryFingerprintV1"); }
    virtual void Preload(UObject*) override { Reject(); } // never load/create to satisfy serialization
    virtual UObject* GetArchetypeFromLoader(const UObject* Object) override
    {
        if (Object!=Subject || !Defaults) Reject();
        return Defaults; // prevalidated existing native CDO, avoiding GetArchetype fallback
    }
    using FArchive::operator<<;
    virtual FArchive& operator<<(FName& Name) override
    {
        if (Failed) return *this;
        FString Value=Name.ToString();
        if (Value.Len()>4096) { Reject(); return *this; }
        static_cast<FArchive&>(*this) << Value; return *this;
    }
    virtual FArchive& operator<<(UObject*& Object) override
    {
        if (Failed) return *this;
        uint8 Present=Object ? 1 : 0; Serialize(&Present,1);
        if (Failed) return *this;
        FString Value=Object ? Object->GetPathName() : FString();
        if (Value.Len()>4096) { Reject(); return *this; }
        static_cast<FArchive&>(*this) << Value; return *this;
    }
    bool FlagsOK() const
    {
        return ArIsSaving && ArIsPersistent && !ArIsLoading && !ArIsTransacting && !ArWantBinaryPropertySerialization &&
            !ArIsFilterEditorOnly && !ArIsSaveGame && !ArNoDelta && ArPortFlags==0 && !CookingTarget() &&
            !ArIsCountingMemory && !ArIsObjectReferenceCollector && !ArIsModifyingWeakAndStrongReferences &&
            !ArAllowLazyLoading && !ArShouldSkipBulkData && !ArUseCustomPropertyList && !ArCustomPropertyList &&
            !ArForceByteSwapping && !ArForceUnicode && !ArSerializingDefaults;
    }
    FString FlagsText() const
    {
        return FString::Printf(TEXT("saving=1;persistent=1;loading=0;transaction=0;binary=0;editor_filtered=0;savegame=0;nodelta=0;port=0;cooking=0;collector=0;counting=0;modifyrefs=0;lazy=0;skipbulk=0;customlist=0;swap=0;unicode=0;defaults=0;ue4=%d;licensee=%d;custom=current-registered"),UE4Ver(),LicenseeUE4Ver());
    }
};
static bool ERMRegistryFingerprint(UWorld* World,UReflectionCaptureComponent* Target,const FString& Guid,
    FString& Hash,int64& Size,FString& Flags)
{
    if (!ERMRegistryLinked(World,Guid) || !IsInGameThread()) return false;
    UMapBuildDataRegistry* Registry=World->PersistentLevel->MapBuildData;
    UClass* Class=Registry->GetClass(); UObject* Defaults=Class->GetDefaultObject(false);
    const EObjectFlags Pending=EObjectFlags(RF_NeedLoad | RF_NeedPostLoad | RF_NeedPostLoadSubobjects);
    if (!Defaults || Defaults->GetClass()!=Class || !Defaults->HasAnyFlags(RF_ClassDefaultObject) ||
        Registry->HasAnyFlags(Pending) || Class->HasAnyFlags(Pending) || Defaults->HasAnyFlags(Pending)) return false;
    TMap<FString,FString> Before,After; FString BeforeDigest,AfterDigest;
    if (!FERDState::Snapshot(World,Target,Before,BeforeDigest)) return false;
    const bool Dirty=World->GetOutermost()->IsDirty();
    FERMRegistryWriter Writer(Registry,Defaults);
    if (!Writer.FlagsOK() || Writer.Failed) return false;
    const FString InitialFlags=Writer.FlagsText();
    Registry->Serialize(Writer); // ENGINE_API entry: private sample serializers remain inside Engine
    if (Writer.Failed || Writer.IsError() || Writer.IsCriticalError() || !Writer.FlagsOK() || Writer.FlagsText()!=InitialFlags ||
        Writer.Tell()!=Writer.TotalSize() || Writer.TotalSize()<=0 || !ERMRegistryLinked(World,Guid) ||
        World->PersistentLevel->MapBuildData!=Registry || World->GetOutermost()->IsDirty()!=Dirty ||
        !FERDState::Snapshot(World,Target,After,AfterDigest) || BeforeDigest!=AfterDigest || !ERMObjectsEqual(Before,After)) return false;
    Size=Writer.Bytes.Num(); Flags=InitialFlags;
    FSHA1 SHA; SHA.Update(Writer.Bytes.GetData(),Writer.Bytes.Num()); SHA.Final(); uint8 Out[20]; SHA.GetHash(Out);
    Hash=BytesToHex(Out,20).ToLower(); return true;
}

static void ERMFingerprintFields(const TSharedPtr<FJsonObject>& J,const FString& Hash,int64 Size,const FString& Flags)
{
    J->SetStringField(TEXT("registry_schema"),ERMRegistrySchema);
    J->SetStringField(TEXT("registry_sha1"),Hash); J->SetNumberField(TEXT("registry_bytes"),double(Size));
    J->SetStringField(TEXT("registry_archive_flags"),Flags);
}

struct FERMReceipt
{
    FString ReceiptPath, ReceiptSHA1, OriginalContent, Selected, Original, Backup, Diagnostic;
    FWURFile ReceiptPin, OriginalPin, BackupPin, DiagnosticPin, SelectedPin;
    bool External(const FString& Path) const
    {
        const FString EngineRoot = Full(FPaths::GetPath(Full(FPaths::EngineDir())));
        const FString OriginalRoot = Full(FPaths::GetPath(Full(FPaths::GetPath(OriginalContent))));
        return !Path.IsEmpty() && !Within(Path, EngineRoot) && !Within(Path, OriginalRoot) &&
            !Path.ToLower().Contains(TEXT("/content/"));
    }
    bool Read(const FString& Params, bool ForSave)
    {
        FString Expected;
        if (!FParse::Value(*Params, TEXT("EntryMapReceipt="), ReceiptPath) ||
            !FParse::Value(*Params, TEXT("EntryMapReceiptSHA1="), ReceiptSHA1) ||
            !FParse::Value(*Params, TEXT("EntryMapExpectedSHA1="), Expected) || !ERMSHA1(Expected)) return false;
        ReceiptPath = Full(ReceiptPath);
        TSharedPtr<FJsonObject> J;
        if (!ERMReadJSON(ReceiptPath, ReceiptSHA1, ReceiptPin, J) ||
            Str(J,TEXT("schema")) != TEXT("ut4-entry-reflection-save-v1") ||
            Str(J,TEXT("operation")) != TEXT("save-entry-reflection") || Str(J,TEXT("package")) != ERDPackage ||
            Str(J,TEXT("original_sha1")) != ERDMapSHA1 || Str(J,TEXT("diagnostic_result_sha1")) != ERMDiagnosticSHA1 ||
            Str(J,TEXT("authored_digest")) != ERMBaselineDigest) return false;
        bool Authorized = false; double Objects = 0;
        if (!J->TryGetBoolField(TEXT("native_save_authorized"), Authorized) || !Authorized ||
            !J->TryGetNumberField(TEXT("authored_objects"), Objects) || Objects != 78) return false;
        const FString OriginalField = Str(J,TEXT("original_map"));
        if (OriginalField.IsEmpty()) return false;
        OriginalContent = Full(FPaths::GetPath(FPaths::GetPath(FPaths::GetPath(Full(OriginalField)))));
        if (!FPaths::GetCleanFilename(OriginalContent).Equals(TEXT("Content"), ESearchCase::IgnoreCase) ||
            Within(OriginalContent,Full(FPaths::GameDir()))) return false;
        Selected = Full(FPaths::GameContentDir() / TEXT("RestrictedAssets/Maps/UT-Entry.umap"));
        Original = Full(OriginalContent / TEXT("RestrictedAssets/Maps/UT-Entry.umap"));
        Backup = Full(Str(J,TEXT("backup"))); Diagnostic = Full(Str(J,TEXT("diagnostic_result")));
        if (Str(J,TEXT("backup")).IsEmpty() || Str(J,TEXT("diagnostic_result")).IsEmpty() ||
            Full(Str(J,TEXT("selected_map"))) != Selected || Full(OriginalField) != Original ||
            Full(FPackageName::LongPackageNameToFilename(ERDPackage,TEXT(".umap"))) != Selected ||
            !External(ReceiptPath) || !External(Backup) || !External(Diagnostic) ||
            !FWURFile::Inspect(Selected,false,SelectedPin) || !FWURFile::Inspect(Original,false,OriginalPin) ||
            !FWURFile::Inspect(Backup,false,BackupPin) || !FWURFile::Inspect(Diagnostic,false,DiagnosticPin,nullptr,65536)) return false;
        const TArray<TSharedPtr<FJsonValue>>* Allowlist = nullptr;
        if (!J->TryGetArrayField(TEXT("save_allowlist"), Allowlist) || Allowlist->Num() != 1 ||
            (*Allowlist)[0]->Type != EJson::String || Full((*Allowlist)[0]->AsString()) != Selected) return false;
        if (OriginalPin.SHA1 != ERDMapSHA1 || BackupPin.SHA1 != ERDMapSHA1 || DiagnosticPin.SHA1 != ERMDiagnosticSHA1 ||
            SelectedPin.Identity == OriginalPin.Identity || SelectedPin.Identity == BackupPin.Identity ||
            OriginalPin.Identity == BackupPin.Identity || SelectedPin.SHA1 != Expected) return false;
        return !ForSave || Expected == ERDMapSHA1;
    }
    bool Fixed() const
    {
        return ERMUnchanged(ReceiptPin) && ERMUnchanged(OriginalPin) && ERMUnchanged(BackupPin) && ERMUnchanged(DiagnosticPin);
    }
    bool Before() const { return Fixed() && ERMUnchanged(SelectedPin); }
};

// Exclusive append-only, bounded JSONL. Completion is authoritative only with a
// successful owned exit and launcher-wide after audit; partial files are evidence.
struct FERMEvidence
{
    HANDLE Handle = INVALID_HANDLE_VALUE;
    bool Open(const FString& Path, const FERMReceipt& R)
    {
        if (!R.External(Path) || !Physical(FPaths::GetPath(Path),false) || !Physical(Path,true) ||
            IFileManager::Get().FileExists(*Path)) return false;
        Handle = CreateFileW(*Path,FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        return Handle != INVALID_HANDLE_VALUE;
    }
    bool Emit(const TSharedPtr<FJsonObject>& J, int32 MaxChars = 16384)
    {
        FString Text;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(),TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text)) ||
            Text.Len() > MaxChars || Handle == INVALID_HANDLE_VALUE) return false;
        Text += TEXT("\n"); FTCHARToUTF8 Bytes(*Text); DWORD Written = 0;
        return WriteFile(Handle,Bytes.Get(),DWORD(Bytes.Length()),&Written,nullptr) && Written == DWORD(Bytes.Length()) && FlushFileBuffers(Handle);
    }
    void Close() { if (Handle != INVALID_HANDLE_VALUE) { CloseHandle(Handle); Handle = INVALID_HANDLE_VALUE; } }
    ~FERMEvidence() { Close(); }
};
static TSharedPtr<FJsonObject> ERMRecord(const TCHAR* Mode, const TCHAR* Kind, const FERMReceipt& R)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetStringField(TEXT("schema"),TEXT("ut4-entry-map-result-v1"));
    J->SetStringField(TEXT("mode"),Mode); J->SetStringField(TEXT("kind"),Kind);
    J->SetStringField(TEXT("package"),ERDPackage); J->SetStringField(TEXT("source_receipt_sha1"),R.ReceiptSHA1);
    J->SetStringField(TEXT("selected"),R.Selected);
    J->SetBoolField(TEXT("visual_success_claim"),false);
    J->SetStringField(TEXT("preservation_contract"),ERMPreservationContract);
    J->SetStringField(TEXT("loaded_baseline_digest"),ERMLoadedDigest);
    J->SetStringField(TEXT("loaded1_sha1"),ERMLoaded1SHA1); J->SetStringField(TEXT("loaded2_sha1"),ERMLoaded2SHA1);
    return J;
}
static bool ERMTarget(UWorld* World, bool Registered, UReflectionCaptureComponent*& Target)
{
    if (!World || !World->PersistentLevel || World->GetOutermost()->GetName() != ERDPackage) return false;
    const FString Exact = World->PersistentLevel->GetPathName() + TEXT(".SphereReflectionCapture_1.NewReflectionComponent");
    int32 Count = 0; Target = nullptr;
    for (TObjectIterator<UReflectionCaptureComponent> It; It; ++It)
    {
        UReflectionCaptureComponent* C = *It;
        if (!IsValid(C) || C->GetOutermost() != World->GetOutermost()) continue;
        ++Count;
        if (C->GetPathName() == Exact && C->GetClass()->GetPathName() == TEXT("/Script/Engine.SphereReflectionCaptureComponent") &&
            C->GetOwner() && C->GetOwner()->GetLevel() == World->PersistentLevel && C->IsRegistered() == Registered) Target = C;
    }
    return Count == 1 && Target;
}

struct FERMState : TSharedFromThis<FERMState>
{
    FERMReceipt Receipt;
    FERMEvidence Evidence;
    FERDState Capture; // Only the public snapshot/payload/pin/settings utilities are used.
    TMap<FString,FString> Authored;
    FString InitialState, InitialRawDigest, InitialLevelGuid, InitialRegistryHash, InitialRegistryFlags;
    int64 InitialRegistryBytes=0;
    FDelegateHandle Ticker;
    double Started = 0;
    bool Finished = false, SaveAttempted = false;
    bool InspectOnly = false, RegistryProbe = false;
    int32 Phase = 0;
    bool SettingsDisabled() const
    {
        const UEditorLoadingSavingSettings* S = Capture.SettingsOwner.Get();
        return S && !S->bMonitorContentDirectories && !S->bAutoSaveEnable && !S->bAutoCreateAssets &&
            !S->bAutoDeleteAssets && Capture.PerformanceMonitor.IsDisabled();
    }
    bool Payload(FString& Hash, FString& Brightness, int64& Zeros)
    {
        int32 Dimension = 0;
        Brightness = ERMBrightness(Capture.Target);
        return !Brightness.IsEmpty() && Capture.ValidatePayload(Hash,Dimension,Zeros) && Dimension == 128;
    }
    bool SameAuthored()
    {
        TMap<FString,FString> Now; FString Digest;
        return FERDState::Snapshot(Capture.World,Capture.Target,Now,Digest) && Now.Num() == 78 &&
            Digest == InitialRawDigest && ERMObjectsEqual(Authored,Now) && ERMRegistryLinked(Capture.World,InitialLevelGuid);
    }
    void Finish(bool OK, const FString& Detail, const TSharedPtr<FJsonObject>& Values = nullptr)
    {
        if (Finished) return;
        Finished = true;
        TSharedPtr<FJsonObject> J = Values.IsValid() ? Values : ERMRecord(InspectOnly ? TEXT("inspect") : TEXT("save"),TEXT("complete"),Receipt);
        J->SetStringField(TEXT("status"),OK ? (InspectOnly ? TEXT("inspected") : TEXT("saved")) : TEXT("failed"));
        J->SetStringField(TEXT("detail"),Detail); J->SetBoolField(TEXT("save_attempted"),SaveAttempted);
        if (!Evidence.Emit(J) || !OK) UE_LOG(LogUT4Html5Compat,Error,TEXT("Entry map save failed: %s"),*Detail);
        // Settings stay suppressed until owning module shutdown, after editor ticking.
        FPlatformMisc::RequestExit(false);
    }
    bool Tick(float)
    {
        if (Finished) return false;
        if (FPlatformTime::Seconds()-Started > 180) { Finish(false,TEXT("deadline")); return false; }
        if (!Receipt.Before() || !Capture.CheckMapPins() || !SettingsDisabled()) { Finish(false,TEXT("pre-save pins/settings")); return false; }
        if (!GIsEditor || IsRunningCommandlet() || !FApp::IsUnattended()) { Finish(false,TEXT("editor mode changed")); return false; }
        if (!GEditor || !IsInGameThread() || !FApp::CanEverRender() || !GShaderCompilingManager ||
            GShaderCompilingManager->IsCompiling() || GShaderCompilingManager->HasShaderJobs()) return true;
        if (Phase == 0)
        {
            Capture.World = GEditor->GetEditorWorldContext().World();
            if (!Capture.World || Capture.World->WorldType != EWorldType::Editor || !Capture.World->Scene ||
                Capture.World->FeatureLevel < ERHIFeatureLevel::SM4) return true;
            if (!ERMTarget(Capture.World,true,Capture.Target) || !Capture.Target->IsVisible()) { Finish(false,TEXT("target")); return false; }
            FString Digest;
            const bool SnapshotOK = FERDState::Snapshot(Capture.World,Capture.Target,Authored,Digest);
            // ENTRY_MAP_INSPECT_BEGIN
            FString CanonicalDigest,LevelGuid;
            const bool CanonicalOK=SnapshotOK && ERMCanonical(Authored,CanonicalDigest,LevelGuid);
            const bool RegistryOK=CanonicalOK && ERMRegistryLinked(Capture.World,LevelGuid);
            if (InspectOnly || !SnapshotOK || Authored.Num()!=78 || !CanonicalOK || CanonicalDigest!=ERMCanonicalDigest || !RegistryOK)
            {
                TSharedPtr<FJsonObject> Summary = ERMRecord(InspectOnly ? TEXT("inspect") : TEXT("save"),TEXT("complete"),Receipt);
                Summary->SetBoolField(TEXT("snapshot_ok"),SnapshotOK);
                Summary->SetNumberField(TEXT("objects"),Authored.Num());
                Summary->SetStringField(TEXT("authored_digest"),Digest);
                Summary->SetStringField(TEXT("canonical_digest"),CanonicalDigest);
                Summary->SetStringField(TEXT("expected_canonical_digest"),ERMCanonicalDigest);
                Summary->SetStringField(TEXT("level_build_data_id"),LevelGuid);
                Summary->SetBoolField(TEXT("registry_link_valid"),RegistryOK);
                Summary->SetStringField(TEXT("registry_path"),RegistryOK ? ERMRegistryPath : TEXT(""));
                Summary->SetStringField(TEXT("inspect1_sha1"),ERMInspect1SHA1);
                Summary->SetStringField(TEXT("inspect2_sha1"),ERMInspect2SHA1);
                Summary->SetBoolField(TEXT("baseline_matches"),SnapshotOK && Authored.Num()==78 && CanonicalOK && CanonicalDigest==ERMCanonicalDigest && RegistryOK);
                Summary->SetBoolField(TEXT("package_saved"),false);
                bool RowsOK = SnapshotOK;
                if (SnapshotOK)
                {
                    TArray<FString> Keys; Authored.GetKeys(Keys); Keys.Sort();
                    for (const FString& Key : Keys)
                    {
                        TSharedPtr<FJsonObject> Row = ERMRecord(InspectOnly ? TEXT("inspect") : TEXT("save"),TEXT("snapshot_row"),Receipt);
                        Row->SetStringField(TEXT("object_path"),Key);
                        Row->SetStringField(TEXT("snapshot_row"),Authored.FindChecked(Key));
                        // Existing Snapshot bounds retained; allow worst-case JSON escaping of a full row.
                        if (!Evidence.Emit(Row,8*1024*1024)) { RowsOK=false; break; }
                    }
                }
                Summary->SetBoolField(TEXT("snapshot_rows_complete"),RowsOK);
                FString ProbeHash,ProbeFlags; int64 ProbeBytes=0;
                const bool ProbeOK=!RegistryProbe || (InspectOnly && RegistryOK &&
                    ERMRegistryFingerprint(Capture.World,Capture.Target,LevelGuid,ProbeHash,ProbeBytes,ProbeFlags));
                Summary->SetBoolField(TEXT("registry_probe_requested"),RegistryProbe);
                if (RegistryProbe) ERMFingerprintFields(Summary,ProbeHash,ProbeBytes,ProbeFlags);
                const bool InspectionOK = ProbeOK && InspectOnly && RowsOK && Receipt.Before() && Capture.CheckMapPins() && SettingsDisabled();
                Finish(InspectionOK,InspectOnly ? TEXT("inspect only; no capture or save") : TEXT("authored baseline"),Summary);
                return false; // Unconditional: inspect never reaches capture, PreSave or SavePackage.
            }
            // ENTRY_MAP_INSPECT_END
            InitialRawDigest=Digest; InitialLevelGuid=LevelGuid;
            InitialState = Capture.StateIdText();
            if (InitialState.IsEmpty()) { Finish(false,TEXT("state ID")); return false; }
            Capture.WorldOwner = Capture.World; Capture.TargetOwner = Capture.Target;
            Capture.PackageDirtyBefore = Capture.World->GetOutermost()->IsDirty();
            if (!ERMRegistryFingerprint(Capture.World,Capture.Target,InitialLevelGuid,InitialRegistryHash,InitialRegistryBytes,InitialRegistryFlags) ||
                !SameAuthored() || !Receipt.Before() || !SettingsDisabled())
            { Finish(false,TEXT("registry before capture")); return false; }
            TSharedPtr<FJsonObject> RegistryBefore=ERMRecord(TEXT("save"),TEXT("registry_before_capture"),Receipt);
            ERMFingerprintFields(RegistryBefore,InitialRegistryHash,InitialRegistryBytes,InitialRegistryFlags);
            if (!Evidence.Emit(RegistryBefore)) { Finish(false,TEXT("registry evidence before capture")); return false; }
            Capture.Target->SetCaptureIsDirty();
            UReflectionCaptureComponent::UpdateReflectionCaptureContents(Capture.World);
            UObject* VirtualTarget = Capture.Target; VirtualTarget->PreSave(nullptr);
            Phase = 1; return true;
        }
        if (!Capture.WorldOwner.IsValid() || !Capture.TargetOwner.IsValid() || Capture.WorldOwner.Get()!=Capture.World ||
            Capture.TargetOwner.Get()!=Capture.Target || GEditor->GetEditorWorldContext().World()!=Capture.World)
        { Finish(false,TEXT("world lifetime")); return false; }
        FString PayloadHash,Brightness; int64 Zeros = 0;
        if (!ERMSaveAdmission(GIsEditor,IsRunningCommandlet(),IsInGameThread(),FApp::CanEverRender(),FApp::IsUnattended(),
            Capture.World->WorldType==EWorldType::Editor && Capture.World->FeatureLevel>=ERHIFeatureLevel::SM4 && Capture.World->Scene &&
                Capture.World->GetOutermost()->GetName()==ERDPackage,
            Capture.Target->IsRegistered() && Capture.Target->IsVisible(),true,SettingsDisabled(),Receipt.Before() && Capture.CheckMapPins(),
            SameAuthored(),Payload(PayloadHash,Brightness,Zeros),Capture.StateIdText()!=InitialState) ||
            Capture.World->GetOutermost()->IsDirty()!=Capture.PackageDirtyBefore)
        { Finish(false,TEXT("save admission")); return false; }
        FString BeforeRegistryHash,BeforeRegistryFlags; int64 BeforeRegistryBytes=0;
        if (!ERMRegistryFingerprint(Capture.World,Capture.Target,InitialLevelGuid,BeforeRegistryHash,BeforeRegistryBytes,BeforeRegistryFlags) ||
            BeforeRegistryHash!=InitialRegistryHash || BeforeRegistryBytes!=InitialRegistryBytes || BeforeRegistryFlags!=InitialRegistryFlags || !SameAuthored())
        { Finish(false,TEXT("registry drift before save")); return false; }
        const FString SavedState = Capture.StateIdText();
        TSharedPtr<FJsonObject> Before = ERMRecord(TEXT("save"),TEXT("before_save"),Receipt);
        ERMFingerprintFields(Before,BeforeRegistryHash,BeforeRegistryBytes,BeforeRegistryFlags);
        Before->SetStringField(TEXT("payload_sha1"),PayloadHash); Before->SetStringField(TEXT("state_id"),SavedState);
        if (!Evidence.Emit(Before) || !Receipt.Before() || !SettingsDisabled()) { Finish(false,TEXT("pre-save evidence/pins")); return false; }
        SaveAttempted = true;
        // Exported UEditorEngine wrapper; uncooked, synchronous, one .umap, no slow-task UI.
        const bool Saved = GEditor->SavePackage(Capture.World->GetOutermost(),Capture.World,RF_Standalone,*Receipt.Selected,
            GError,nullptr,false,false,SAVE_None,nullptr,FDateTime::MinValue(),false);
        FWURFile After;
        FString PostHash,PostBrightness,PostRegistryHash,PostRegistryFlags; int64 PostZeros = 0,PostRegistryBytes=0;
        const bool OK = Saved && Receipt.Fixed() && FWURFile::Inspect(Receipt.Selected,false,After) &&
            After.SHA1 != ERDMapSHA1 && After.Identity != Receipt.OriginalPin.Identity && After.Identity != Receipt.BackupPin.Identity &&
            SameAuthored() && Capture.StateIdText()==SavedState && Payload(PostHash,PostBrightness,PostZeros) &&
            PostHash==PayloadHash && PostBrightness==Brightness && PostZeros==Zeros && SettingsDisabled() &&
            ERMRegistryFingerprint(Capture.World,Capture.Target,InitialLevelGuid,PostRegistryHash,PostRegistryBytes,PostRegistryFlags) &&
            PostRegistryHash==InitialRegistryHash && PostRegistryBytes==InitialRegistryBytes && PostRegistryFlags==InitialRegistryFlags && SameAuthored();
        TSharedPtr<FJsonObject> J = ERMRecord(TEXT("save"),TEXT("complete"),Receipt);
        ERMFingerprintFields(J,PostRegistryHash,PostRegistryBytes,PostRegistryFlags);
        J->SetStringField(TEXT("saved_map_sha1"),After.SHA1); J->SetStringField(TEXT("saved_identity"),After.Identity);
        J->SetStringField(TEXT("authored_digest"),InitialRawDigest);
        J->SetStringField(TEXT("canonical_digest"),ERMCanonicalDigest);
        J->SetStringField(TEXT("initial_level_guid"),InitialLevelGuid);
        J->SetStringField(TEXT("saved_level_guid"),Capture.World->PersistentLevel->LevelBuildDataId.ToString());
        J->SetStringField(TEXT("registry_path"),ERMRegistryPath);
        J->SetBoolField(TEXT("registry_link_valid"),ERMRegistryLinked(Capture.World,InitialLevelGuid));
        J->SetStringField(TEXT("inspect1_sha1"),ERMInspect1SHA1); J->SetStringField(TEXT("inspect2_sha1"),ERMInspect2SHA1); J->SetNumberField(TEXT("objects"),Authored.Num());
        J->SetStringField(TEXT("state_id"),SavedState); J->SetStringField(TEXT("payload_sha1"),PayloadHash);
        J->SetStringField(TEXT("brightness_bits"),Brightness); J->SetNumberField(TEXT("dimension"),128);
        J->SetNumberField(TEXT("zero_channels"),double(Zeros));
        Finish(OK,OK ? TEXT("one uncooked map saved; fresh verification required") : TEXT("save/post-save invariant failed; no rollback"),J);
        return false;
    }
};
static TSharedPtr<FERMState> GEntryMapRepair;

// Call only in module startup before GEngine/GEditor creation; never from commandlet routing.
static int32 StartEntryReflectionMapSave(const FString& Params)
{
    // FAILED_SAVE2_SAVE_GUARD_BEGIN
    FString FailedOnly;
    if (FParse::Param(*Params,TEXT("EntryMapInspectFailedSave2")) ||
        FParse::Value(*Params,TEXT("FailedSaveProof="),FailedOnly) || FParse::Value(*Params,TEXT("FailedSaveProofSHA1="),FailedOnly))
        return WFRStop(TEXT("entry-map-failed-save2-commandlet-only"));
    // FAILED_SAVE2_SAVE_GUARD_END
    if (!GIsEditor || IsRunningCommandlet() || !IsInGameThread() || !FApp::CanEverRender() || !FApp::IsUnattended() ||
        GEngine || GEditor || GEntryMapRepair.IsValid() || GEntryReflectionDiagnostic.IsValid() ||
        !FParse::Param(*Params,TEXT("EntryReflectionMapSave")) || !FParse::Param(*Params,TEXT("EntryReflectionDiagnostic")) ||
        !FParse::Param(*Params,TEXT("TournamentEntryReflectionNoMainFrame"))) return WFRStop(TEXT("entry-map-save-mode"));
    for (const TCHAR* Flag : {TEXT("immersive"),TEXT("VREditor"),TEXT("ForceVREditor"),TEXT("AutomatedMapBuild"),TEXT("nullrhi"),TEXT("game"),TEXT("EntryReflectionMapVerify"),TEXT("EntryMapInspectLoaded")})
        if (FParse::Param(*Params,Flag)) return WFRStop(TEXT("entry-map-conflicting-mode"));
    TSharedPtr<FERMState> S = MakeShareable(new FERMState);
    S->InspectOnly=FParse::Param(*Params,TEXT("EntryMapInspectOnly"));
    S->RegistryProbe=FParse::Param(*Params,TEXT("EntryMapRegistryProbe"));
    if (S->RegistryProbe && !S->InspectOnly) return WFRStop(TEXT("entry-map-registry-probe-requires-inspect"));
    FString Output;
    if (!S->Receipt.Read(Params,true) || !FParse::Value(*Params,TEXT("EntryMapOutput="),Output) ||
        !S->Evidence.Open(Full(Output),S->Receipt)) return WFRStop(TEXT("entry-map-receipt/evidence"));
    S->Capture.SelectedMap=S->Receipt.Selected; S->Capture.OriginalMap=S->Receipt.Original;
    S->Capture.SelectedIdentity=S->Receipt.SelectedPin.Identity; S->Capture.OriginalIdentity=S->Receipt.OriginalPin.Identity;
    S->Capture.SelectedSize=S->Receipt.SelectedPin.Size; S->Capture.OriginalSize=S->Receipt.OriginalPin.Size;
    auto* Settings=GetMutableDefault<UEditorLoadingSavingSettings>();
    auto* Performance=GetMutableDefault<UEditorPerProjectUserSettings>();
    if (!Settings || !Performance) return WFRStop(TEXT("entry-map-settings"));
    S->Capture.Settings=Settings; S->Capture.SettingsOwner=Settings;
    S->Capture.OldMonitor=Settings->bMonitorContentDirectories; S->Capture.OldAutoSave=Settings->bAutoSaveEnable;
    S->Capture.OldAutoCreate=Settings->bAutoCreateAssets; S->Capture.OldAutoDelete=Settings->bAutoDeleteAssets;
    Settings->bMonitorContentDirectories=false; Settings->bAutoSaveEnable=false;
    Settings->bAutoCreateAssets=false; Settings->bAutoDeleteAssets=false; S->Capture.SettingsSaved=true;
    S->Capture.PerformanceMonitor.Disable(Performance);
    if (!S->Evidence.Emit(ERMRecord(S->InspectOnly ? TEXT("inspect") : TEXT("save"),TEXT("begin"),S->Receipt)))
    { S->Capture.RestoreSettings(); return WFRStop(TEXT("entry-map-begin-evidence")); }
    S->Started=FPlatformTime::Seconds(); GEntryMapRepair=S;
    S->Ticker=FTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([S](float Delta){return S->Tick(Delta);}),0.1f);
    return 0;
}
static void ShutdownEntryReflectionMapSave()
{
    auto S=GEntryMapRepair; if (!S.IsValid()) return;
    FTicker::GetCoreTicker().RemoveTicker(S->Ticker);
    if (!S->Finished) S->Finish(false,TEXT("shutdown before completion"));
    S->Capture.RestoreSettings(); S->Evidence.Close(); GEntryMapRepair.Reset();
}

// FAILED_SAVE2_INSPECTION_BEGIN
// Fixed failed afterimage only. This is observation, never successful-save adoption.
static bool ERMFailedSave2Row(const TSharedPtr<FJsonObject>& Row,int32 Index,const FERMReceipt& R)
{
    const TCHAR* Kinds[]={TEXT("begin"),TEXT("registry_before_capture"),TEXT("before_save"),TEXT("complete")};
    bool Visual=true,Attempted=false;
    if (Index<0 || Index>=4 || !Row.IsValid() ||
        Str(Row,TEXT("schema"))!=TEXT("ut4-entry-map-result-v1") || Str(Row,TEXT("mode"))!=TEXT("save") ||
        Str(Row,TEXT("kind"))!=Kinds[Index] || Str(Row,TEXT("package"))!=ERDPackage ||
        Str(Row,TEXT("source_receipt_sha1"))!=R.ReceiptSHA1 || Str(Row,TEXT("selected"))!=R.Selected ||
        !Row->TryGetBoolField(TEXT("visual_success_claim"),Visual) || Visual) return false;
    return Index!=3 || (Str(Row,TEXT("status"))==TEXT("failed") &&
        Row->TryGetBoolField(TEXT("save_attempted"),Attempted) && Attempted &&
        Str(Row,TEXT("saved_map_sha1"))==R.SelectedPin.SHA1 &&
        Str(Row,TEXT("saved_identity"))==R.SelectedPin.Identity);
}
static int32 ERMInspectFailedSave2(const FString& Params)
{
    FERMReceipt R; FString Output,Forbidden,ProofPath,ProofSHA;
    if (FParse::Param(*Params,TEXT("EntryMapInspectLoaded")) ||
        FParse::Value(*Params,TEXT("EntryMapSaveProof="),Forbidden) ||
        FParse::Value(*Params,TEXT("EntryMapSaveProofSHA1="),Forbidden) ||
        !R.Read(Params,false) || R.SelectedPin.SHA1!=TEXT("7797936e53bf4267307b0f461ea532632fb8c4a1") ||
        !FParse::Value(*Params,TEXT("FailedSaveProof="),ProofPath) ||
        !FParse::Value(*Params,TEXT("FailedSaveProofSHA1="),ProofSHA) ||
        ProofSHA!=TEXT("48e89afcf61055202073dc541de069ddbe0c0b68") ||
        !FParse::Value(*Params,TEXT("EntryMapOutput="),Output)) return WFRStop(TEXT("entry-map-failed-save2-input"));
    ProofPath=Full(ProofPath); FWURFile ProofPin;
    if (!R.External(ProofPath) || !FWURFile::Inspect(ProofPath,false,ProofPin,nullptr,65536) || ProofPin.SHA1!=ProofSHA)
        return WFRStop(TEXT("entry-map-failed-save2-pin"));
    FString Text; TArray<FString> Lines;
    if (!FFileHelper::LoadFileToString(Text,*ProofPath)) return WFRStop(TEXT("entry-map-failed-save2-read"));
    Text.ParseIntoArrayLines(Lines,true);
    if (Lines.Num()!=4) return WFRStop(TEXT("entry-map-failed-save2-sequence"));
    for (int32 I=0;I<4;++I)
    {
        TSharedPtr<FJsonObject> Row;
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Lines[I]),Row) || !ERMFailedSave2Row(Row,I,R))
            return WFRStop(TEXT("entry-map-failed-save2-proof"));
    }
    FERMEvidence Evidence;
    if (!Evidence.Open(Full(Output),R) || !Evidence.Emit(ERMRecord(TEXT("inspect_failed_save2"),TEXT("begin"),R)))
        return WFRStop(TEXT("entry-map-failed-save2-evidence"));
    if (FindPackage(nullptr,ERDPackage) || !R.Before() || !ERMUnchanged(ProofPin))
        return WFRStop(TEXT("entry-map-failed-save2-preload"));
    UPackage* Package=LoadPackage(nullptr,ERDPackage,LOAD_None);
    UWorld* World=Package ? UWorld::FindWorldInPackage(Package) : nullptr;
    FERDState Capture; Capture.World=World;
    const bool TargetOK=World && !World->Scene && ERMTarget(World,false,Capture.Target);
    TMap<FString,FString> Rows; FString Digest,CanonicalDigest,Guid,Payload,Brightness,State,RegistryHash,RegistryFlags;
    int32 Dimension=0; int64 Zeros=0,RegistryBytes=0;
    // FAILED_SAVE2_OBSERVATIONS_BEGIN
    const bool SnapshotAttempted=TargetOK;
    const bool SnapshotOK=SnapshotAttempted && FERDState::Snapshot(World,Capture.Target,Rows,Digest);
    const bool CanonicalOK=SnapshotOK && ERMCanonical(Rows,CanonicalDigest,Guid);
    // Read actual level GUID independently of snapshot/canonical success.
    const bool LevelPresent=World && World->PersistentLevel;
    const FString ActualGuid=LevelPresent ? World->PersistentLevel->LevelBuildDataId.ToString() : FString();
    const bool RegistryLinked=LevelPresent && ERMRegistryLinked(World,ActualGuid);
    const bool PayloadAttempted=TargetOK;
    const bool PayloadOK=PayloadAttempted && Capture.ValidatePayload(Payload,Dimension,Zeros);
    if (TargetOK) { Brightness=ERMBrightness(Capture.Target); State=Capture.StateIdText(); }
    const bool RegistryAttempted=TargetOK && RegistryLinked;
    const bool RegistryOK=RegistryAttempted && ERMRegistryFingerprint(World,Capture.Target,ActualGuid,RegistryHash,RegistryBytes,RegistryFlags);
    // FAILED_SAVE2_OBSERVATIONS_END
    bool RowsOK=SnapshotOK;
    if (SnapshotOK)
    {
        TArray<FString> Keys; Rows.GetKeys(Keys); Keys.Sort();
        for (const FString& Key : Keys)
        {
            TSharedPtr<FJsonObject> Row=ERMRecord(TEXT("inspect_failed_save2"),TEXT("snapshot_row"),R);
            Row->SetStringField(TEXT("object_path"),Key); Row->SetStringField(TEXT("snapshot_row"),Rows.FindChecked(Key));
            if (!Evidence.Emit(Row,8*1024*1024)) { RowsOK=false; break; }
        }
    }
    // No object-count/digest/payload/registry match is an acceptance gate here.
    // File immutability and complete snapshot evidence remain mandatory.
    const bool OK=RowsOK && R.Before() && ERMUnchanged(ProofPin);
    TSharedPtr<FJsonObject> J=ERMRecord(TEXT("inspect_failed_save2"),TEXT("complete"),R);
    J->SetStringField(TEXT("status"),OK ? TEXT("inspected") : TEXT("failed"));
    J->SetBoolField(TEXT("preservation_accepted"),false);
    J->SetBoolField(TEXT("save_attempted"),false); J->SetBoolField(TEXT("package_saved"),false);
    J->SetStringField(TEXT("failed_save_proof_sha1"),ProofSHA); J->SetStringField(TEXT("inspected_map_sha1"),R.SelectedPin.SHA1);
    J->SetBoolField(TEXT("target_present"),TargetOK);
    J->SetBoolField(TEXT("snapshot_attempted"),SnapshotAttempted); J->SetBoolField(TEXT("snapshot_ok"),SnapshotOK);
    J->SetBoolField(TEXT("snapshot_rows_complete"),RowsOK); J->SetNumberField(TEXT("objects"),Rows.Num());
    J->SetStringField(TEXT("authored_digest"),Digest); J->SetBoolField(TEXT("canonical_valid"),CanonicalOK);
    J->SetStringField(TEXT("canonical_digest"),CanonicalDigest); J->SetStringField(TEXT("level_build_data_id"),ActualGuid);
    J->SetStringField(TEXT("registry_path"),LevelPresent && World->PersistentLevel->MapBuildData ? World->PersistentLevel->MapBuildData->GetPathName() : FString());
    J->SetBoolField(TEXT("registry_link_valid"),RegistryLinked);
    J->SetBoolField(TEXT("payload_attempted"),PayloadAttempted); J->SetBoolField(TEXT("payload_succeeded"),PayloadOK);
    J->SetStringField(TEXT("payload_sha1"),Payload); J->SetNumberField(TEXT("dimension"),Dimension);
    J->SetNumberField(TEXT("zero_channels"),double(Zeros)); J->SetStringField(TEXT("brightness_bits"),Brightness);
    J->SetStringField(TEXT("state_id"),State);
    J->SetBoolField(TEXT("registry_attempted"),RegistryAttempted); J->SetBoolField(TEXT("registry_succeeded"),RegistryOK);
    ERMFingerprintFields(J,RegistryHash,RegistryBytes,RegistryFlags);
    if (!Evidence.Emit(J) || !OK) return WFRStop(TEXT("entry-map-failed-save2-observation"));
    return 0;
}
// FAILED_SAVE2_INSPECTION_END

// Routed only through VerifyEntryReflectionMap's commandlet/mode/absence guards.
// Add -EntryMapInspectLoaded with ORIGINAL EntryMapExpectedSHA1 and the current
// receipt; omit both SaveProof arguments. No startup map, ticker or world registration.
static int32 ERMInspectLoadedOriginal(const FString& Params)
{
    FERMReceipt R; FString Output,Forbidden;
    if (FParse::Value(*Params,TEXT("EntryMapSaveProof="),Forbidden) ||
        FParse::Value(*Params,TEXT("EntryMapSaveProofSHA1="),Forbidden) ||
        !R.Read(Params,true) || R.SelectedPin.SHA1!=ERDMapSHA1 ||
        !FParse::Value(*Params,TEXT("EntryMapOutput="),Output)) return WFRStop(TEXT("entry-map-loaded-inspect-input"));
    FERMEvidence Evidence;
    if (!Evidence.Open(Full(Output),R) || !Evidence.Emit(ERMRecord(TEXT("inspect_loaded"),TEXT("begin"),R)))
        return WFRStop(TEXT("entry-map-loaded-inspect-evidence"));
    if (FindPackage(nullptr,ERDPackage) || !R.Before()) return WFRStop(TEXT("entry-map-loaded-inspect-preload"));
    UPackage* Package=LoadPackage(nullptr,ERDPackage,LOAD_None);
    UWorld* World=Package ? UWorld::FindWorldInPackage(Package) : nullptr;
    UReflectionCaptureComponent* Target=nullptr;
    const bool TargetOK=World && !World->Scene && ERMTarget(World,false,Target);
    TMap<FString,FString> Rows; FString RawDigest,CanonicalDigest,Guid;
    const bool SnapshotOK=TargetOK && FERDState::Snapshot(World,Target,Rows,RawDigest);
    const bool CanonicalOK=SnapshotOK && ERMCanonical(Rows,CanonicalDigest,Guid);
    const bool RegistryOK=CanonicalOK && ERMRegistryLinked(World,Guid);
    bool RowsOK=SnapshotOK;
    if (SnapshotOK)
    {
        TArray<FString> Keys; Rows.GetKeys(Keys); Keys.Sort();
        for (const FString& Key : Keys)
        {
            TSharedPtr<FJsonObject> Row=ERMRecord(TEXT("inspect_loaded"),TEXT("snapshot_row"),R);
            Row->SetStringField(TEXT("object_path"),Key); Row->SetStringField(TEXT("snapshot_row"),Rows.FindChecked(Key));
            if (!Evidence.Emit(Row,8*1024*1024)) { RowsOK=false; break; }
        }
    }
    const bool Matches=SnapshotOK && Rows.Num()==78 && CanonicalOK && CanonicalDigest==ERMCanonicalDigest;
    // Read-only observation: original PostLoad need not have editor-created registry/population.
    const bool OK=RowsOK && R.Before();
    TSharedPtr<FJsonObject> J=ERMRecord(TEXT("inspect_loaded"),TEXT("complete"),R);
    J->SetStringField(TEXT("status"),OK ? TEXT("inspected") : TEXT("failed"));
    J->SetBoolField(TEXT("target_present"),TargetOK); J->SetBoolField(TEXT("canonical_valid"),CanonicalOK);
    J->SetBoolField(TEXT("snapshot_ok"),SnapshotOK); J->SetBoolField(TEXT("snapshot_rows_complete"),RowsOK);
    J->SetNumberField(TEXT("objects"),Rows.Num()); J->SetStringField(TEXT("authored_digest"),RawDigest);
    J->SetStringField(TEXT("canonical_digest"),CanonicalDigest); J->SetStringField(TEXT("expected_canonical_digest"),ERMCanonicalDigest);
    J->SetStringField(TEXT("level_build_data_id"),Guid); J->SetStringField(TEXT("registry_path"),World && World->PersistentLevel && World->PersistentLevel->MapBuildData ? World->PersistentLevel->MapBuildData->GetPathName() : FString());
    J->SetBoolField(TEXT("registry_link_valid"),RegistryOK); J->SetBoolField(TEXT("baseline_matches"),Matches);
    J->SetStringField(TEXT("inspect1_sha1"),ERMInspect1SHA1); J->SetStringField(TEXT("inspect2_sha1"),ERMInspect2SHA1);
    J->SetBoolField(TEXT("save_attempted"),false); J->SetBoolField(TEXT("package_saved"),false);
    if (!Evidence.Emit(J) || !OK) return WFRStop(TEXT("entry-map-loaded-inspect-mismatch"));
    return 0;
}

// Synchronous commandlet-only load. No ticker, world registration, capture or PreSave.
// PostLoad can derive encoded data; only retained full HDR is accepted. Missing data fails.
static int32 VerifyEntryReflectionMap(const FString& Params)
{
    if (!GIsEditor || !IsRunningCommandlet() || !IsInGameThread() || !FApp::IsUnattended() ||
        !FApp::CanEverRender() || GMaxRHIFeatureLevel < ERHIFeatureLevel::SM4 ||
        FParse::Param(*Params,TEXT("EntryMapInspectOnly")) || FParse::Param(*Params,TEXT("EntryMapRegistryProbe")) ||
        FParse::Param(*Params,TEXT("EntryReflectionMapSave")) || FParse::Param(*Params,TEXT("EntryReflectionDiagnostic")) ||
        !FParse::Param(*Params,TEXT("EntryReflectionMapVerify")) || FindPackage(nullptr,ERDPackage))
        return WFRStop(TEXT("entry-map-verify-mode/package-present"));
    // FAILED_SAVE2_ROUTE_BEGIN
    if (FParse::Param(*Params,TEXT("EntryMapInspectFailedSave2"))) return ERMInspectFailedSave2(Params);
    FString FailedOnly;
    if (FParse::Value(*Params,TEXT("FailedSaveProof="),FailedOnly) || FParse::Value(*Params,TEXT("FailedSaveProofSHA1="),FailedOnly))
        return WFRStop(TEXT("entry-map-failed-save2-flag-required"));
    // FAILED_SAVE2_ROUTE_END
    if (FParse::Param(*Params,TEXT("EntryMapInspectLoaded"))) return ERMInspectLoadedOriginal(Params);
    FERMReceipt R; FString ProofPath,ProofSHA,Output;
    if (!R.Read(Params,false) || R.SelectedPin.SHA1==ERDMapSHA1 ||
        !FParse::Value(*Params,TEXT("EntryMapSaveProof="),ProofPath) || !FParse::Value(*Params,TEXT("EntryMapSaveProofSHA1="),ProofSHA) ||
        !FParse::Value(*Params,TEXT("EntryMapOutput="),Output)) return WFRStop(TEXT("entry-map-verify-input"));
    ProofPath=Full(ProofPath); FWURFile ProofPin;
    if (!R.External(ProofPath) || !ERMSHA1(ProofSHA) || !FWURFile::Inspect(ProofPath,false,ProofPin,nullptr,65536) || ProofPin.SHA1!=ProofSHA)
        return WFRStop(TEXT("entry-map-proof-pin"));
    FString Text; TArray<FString> Lines;
    if (!FFileHelper::LoadFileToString(Text,*ProofPath)) return WFRStop(TEXT("entry-map-proof-read"));
    Text.ParseIntoArrayLines(Lines,true);
    if (Lines.Num()!=4) return WFRStop(TEXT("entry-map-proof-sequence"));
    TSharedPtr<FJsonObject> Proof;
    const TCHAR* Kinds[]={TEXT("begin"),TEXT("registry_before_capture"),TEXT("before_save"),TEXT("complete")};
    FString ExpectedRegistryHash,ExpectedRegistryFlags; double ExpectedRegistryBytes=0;
    for (int32 I=0;I<4;++I)
    {
        TSharedPtr<FJsonObject> Row;
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Lines[I]),Row) || !Row.IsValid() ||
            Str(Row,TEXT("schema"))!=TEXT("ut4-entry-map-result-v1") || Str(Row,TEXT("mode"))!=TEXT("save") ||
            Str(Row,TEXT("kind"))!=Kinds[I] || Str(Row,TEXT("package"))!=ERDPackage ||
            Str(Row,TEXT("source_receipt_sha1"))!=R.ReceiptSHA1 || Str(Row,TEXT("selected"))!=R.Selected ||
            Str(Row,TEXT("preservation_contract"))!=ERMPreservationContract || Str(Row,TEXT("loaded_baseline_digest"))!=ERMLoadedDigest ||
            Str(Row,TEXT("loaded1_sha1"))!=ERMLoaded1SHA1 || Str(Row,TEXT("loaded2_sha1"))!=ERMLoaded2SHA1)
            return WFRStop(TEXT("entry-map-proof-content"));
        if (I>0)
        {
            double Size=0;
            if (Str(Row,TEXT("registry_schema"))!=ERMRegistrySchema || !ERMSHA1(Str(Row,TEXT("registry_sha1"))) ||
                !Row->TryGetNumberField(TEXT("registry_bytes"),Size) || Size<=0 || Size>16*1024*1024 || Size!=double(int64(Size)) ||
                Str(Row,TEXT("registry_archive_flags")).IsEmpty()) return WFRStop(TEXT("entry-map-registry-proof"));
            if (I==1) { ExpectedRegistryHash=Str(Row,TEXT("registry_sha1")); ExpectedRegistryFlags=Str(Row,TEXT("registry_archive_flags")); ExpectedRegistryBytes=Size; }
            else if (Str(Row,TEXT("registry_sha1"))!=ExpectedRegistryHash || Str(Row,TEXT("registry_archive_flags"))!=ExpectedRegistryFlags || Size!=ExpectedRegistryBytes)
                return WFRStop(TEXT("entry-map-registry-proof-drift"));
        }
        Proof=Row;
    }
    double Objects=0,Dimension=0,Zeros=0; bool Attempted=false;
    if (Str(Proof,TEXT("status"))!=TEXT("saved") || !Proof->TryGetBoolField(TEXT("save_attempted"),Attempted) || !Attempted ||
        Str(Proof,TEXT("saved_map_sha1"))!=R.SelectedPin.SHA1 || Str(Proof,TEXT("saved_identity"))!=R.SelectedPin.Identity ||
        !ERMSHA1(Str(Proof,TEXT("authored_digest"))) ||
        Str(Proof,TEXT("canonical_digest"))!=ERMCanonicalDigest ||
        Str(Proof,TEXT("inspect1_sha1"))!=ERMInspect1SHA1 || Str(Proof,TEXT("inspect2_sha1"))!=ERMInspect2SHA1 ||
        !ERMGuid(Str(Proof,TEXT("saved_level_guid"))) || Str(Proof,TEXT("initial_level_guid"))!=Str(Proof,TEXT("saved_level_guid")) ||
        Str(Proof,TEXT("registry_path"))!=ERMRegistryPath || !Proof->TryGetNumberField(TEXT("objects"),Objects) || Objects!=78 ||
        !Proof->TryGetNumberField(TEXT("dimension"),Dimension) || Dimension!=128 || !Proof->TryGetNumberField(TEXT("zero_channels"),Zeros) ||
        !ERMSHA1(Str(Proof,TEXT("payload_sha1"))) || Str(Proof,TEXT("state_id")).IsEmpty() || !ERMUnchanged(ProofPin))
        return WFRStop(TEXT("entry-map-proof-values"));
    FERMEvidence Evidence;
    if (!Evidence.Open(Full(Output),R) || !Evidence.Emit(ERMRecord(TEXT("verify"),TEXT("begin"),R))) return WFRStop(TEXT("entry-map-verify-evidence"));
    // No commandlet startup map argument: package must first enter memory here.
    if (FindPackage(nullptr,ERDPackage) || !R.Before()) return WFRStop(TEXT("entry-map-preload-drift"));
    UPackage* Package=LoadPackage(nullptr,ERDPackage,LOAD_None);
    UWorld* World=Package ? UWorld::FindWorldInPackage(Package) : nullptr;
    FERDState Capture; Capture.World=World;
    bool OK=World && ERMTarget(World,false,Capture.Target);
    FString Digest,Payload,Brightness,CanonicalDigest,LevelGuid,RegistryHash,RegistryFlags; int32 ActualDimension=0; int64 ActualZeros=0,RegistryBytes=0; TMap<FString,FString> ObjectsNow;
    if (OK)
    {
        Brightness=ERMBrightness(Capture.Target);
        OK=FERDState::Snapshot(World,Capture.Target,ObjectsNow,Digest) && ObjectsNow.Num()==61 &&
            ERMCanonical(ObjectsNow,CanonicalDigest,LevelGuid) && LevelGuid==Str(Proof,TEXT("saved_level_guid")) &&
            ERMLoadedRowsAccepted(ObjectsNow,Str(Proof,TEXT("saved_level_guid")),CanonicalDigest) &&
            ERMRegistryLinked(World,LevelGuid) &&
            ERMRegistryFingerprint(World,Capture.Target,LevelGuid,RegistryHash,RegistryBytes,RegistryFlags) &&
            RegistryHash==ExpectedRegistryHash && double(RegistryBytes)==ExpectedRegistryBytes && RegistryFlags==ExpectedRegistryFlags &&
            Capture.ValidatePayload(Payload,ActualDimension,ActualZeros) && ActualDimension==128 &&
            Payload==Str(Proof,TEXT("payload_sha1")) && Capture.StateIdText()==Str(Proof,TEXT("state_id")) &&
            !Brightness.IsEmpty() && Brightness==Str(Proof,TEXT("brightness_bits")) && double(ActualZeros)==Zeros;
    }
    OK=OK && R.Before() && ERMUnchanged(ProofPin);
    TSharedPtr<FJsonObject> J=ERMRecord(TEXT("verify"),TEXT("complete"),R);
    J->SetStringField(TEXT("status"),OK ? TEXT("verified") : TEXT("failed"));
    ERMFingerprintFields(J,RegistryHash,RegistryBytes,RegistryFlags);
    J->SetStringField(TEXT("save_proof_sha1"),ProofSHA); J->SetStringField(TEXT("saved_map_sha1"),R.SelectedPin.SHA1);
    J->SetStringField(TEXT("authored_digest"),Digest); J->SetStringField(TEXT("payload_sha1"),Payload);
    J->SetStringField(TEXT("brightness_bits"),Brightness); J->SetNumberField(TEXT("dimension"),ActualDimension);
    J->SetStringField(TEXT("state_id"),OK ? Capture.StateIdText() : FString());
    J->SetNumberField(TEXT("objects"),ObjectsNow.Num()); J->SetNumberField(TEXT("zero_channels"),double(ActualZeros));
    J->SetBoolField(TEXT("package_saved"),false);
    J->SetStringField(TEXT("canonical_digest"),CanonicalDigest); J->SetStringField(TEXT("level_build_data_id"),LevelGuid);
    J->SetBoolField(TEXT("registry_link_valid"),World && ERMRegistryLinked(World,LevelGuid));
    if (!Evidence.Emit(J) || !OK) return WFRStop(TEXT("entry-map-reload-proof-failed"));
    return 0;
}
