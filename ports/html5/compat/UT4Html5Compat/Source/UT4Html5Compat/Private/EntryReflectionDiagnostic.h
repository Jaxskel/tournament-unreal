// Fixed, normal-editor-only UT-Entry reflection-capture diagnostic.
// This records an in-memory recapture and UObject::PreSave readback; it never saves a package.
static const TCHAR* ERDPackage = TEXT("/Game/RestrictedAssets/Maps/UT-Entry");
static const TCHAR* ERDMapSHA1 = TEXT("653a6eb7a37f00c5238d210e5f45d7729117a246");
static const double ERDDeadlineSeconds = 180.0;
static bool ERDAllowed(bool Editor, bool Commandlet, bool GameThread, bool Renderable,
    bool ExactWorld, bool Registered, bool Unique, bool ShaderIdle, bool FeatureLevel,
    bool MapPins, bool OutputExternal, bool SettingsDisabled)
{
    return Editor && !Commandlet && GameThread && Renderable && ExactWorld && Registered && Unique &&
        ShaderIdle && FeatureLevel && MapPins && OutputExternal && SettingsDisabled;
}

static bool ERDMapPinAccepted(bool SelectedPhysical, bool OriginalPhysical, bool SameBytes,
    bool DistinctFiles, bool ExactPackage)
{
    return SelectedPhysical && OriginalPhysical && SameBytes && DistinctFiles && ExactPackage;
}

struct FERDState : TSharedFromThis<FERDState>
{
    FString Output, OriginalContent, SelectedMap, OriginalMap;
    FString SelectedIdentity, OriginalIdentity;
    int64 SelectedSize = -1, OriginalSize = -1;
    double Started = 0.0;
    HANDLE EvidenceHandle = INVALID_HANDLE_VALUE;
    FString TargetPath;
    int32 Phase = 0;
    bool OldMonitor = false, OldAutoSave = false, OldAutoCreate = false, OldAutoDelete = false;
    bool SettingsSaved = false, Finished = false;
    bool PackageDirtyBefore = false;
    FDelegateHandle Ticker;
    UEditorLoadingSavingSettings* Settings = nullptr;
    TWeakObjectPtr<UEditorLoadingSavingSettings> SettingsOwner;
    TWeakObjectPtr<UWorld> WorldOwner;
    TWeakObjectPtr<UReflectionCaptureComponent> TargetOwner;
    UWorld* World = nullptr;
    UReflectionCaptureComponent* Target = nullptr;
    TMap<FString, FString> BeforeObjects;
    FString BeforeDigest, BeforeStateId;

    bool Emit(const TCHAR* Kind, const FString& Detail, bool Complete = false, bool Success = false)
    {
        TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
        J->SetStringField(TEXT("schema"), TEXT("ut4-entry-reflection-diagnostic-v1"));
        J->SetStringField(TEXT("kind"), Kind);
        J->SetStringField(TEXT("status"), Complete ? (Success ? TEXT("diagnostic_completed") : TEXT("failed")) : TEXT("running"));
        J->SetStringField(TEXT("package"), ERDPackage);
        J->SetStringField(TEXT("selected_map"), SelectedMap);
        J->SetStringField(TEXT("original_map"), OriginalMap);
        J->SetStringField(TEXT("target"), TargetPath);
        J->SetStringField(TEXT("detail"), Detail.Left(4096));
        J->SetBoolField(TEXT("diagnostic_only"), true);
        J->SetBoolField(TEXT("package_saved"), false);
        J->SetBoolField(TEXT("native_save_authorized"), false);
        J->SetBoolField(TEXT("complete"), Complete);
        FString Line;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Line)) ||
            Line.Len() > 8192 || EvidenceHandle == INVALID_HANDLE_VALUE) return false;
        const FString Record = Line + TEXT("\n");
        FTCHARToUTF8 Encoded(*Record);
        DWORD Written = 0;
        if (!WriteFile(EvidenceHandle, Encoded.Get(), DWORD(Encoded.Length()), &Written, nullptr) ||
            Written != DWORD(Encoded.Length()) || !FlushFileBuffers(EvidenceHandle)) return false;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_ENTRY_REFLECTION %s"), *Line);
        return true;
    }

    bool CheckMapPins() const
    {
        FWURFile A, B;
        const bool AOK = FWURFile::Inspect(SelectedMap, false, A);
        const bool BOK = FWURFile::Inspect(OriginalMap, false, B);
        return ERDMapPinAccepted(AOK, BOK,
            AOK && A.SHA1.Equals(ERDMapSHA1, ESearchCase::IgnoreCase) && BOK && B.SHA1.Equals(ERDMapSHA1, ESearchCase::IgnoreCase),
            AOK && BOK && A.Identity == SelectedIdentity && B.Identity == OriginalIdentity &&
                A.Size == SelectedSize && B.Size == OriginalSize && A.Identity != B.Identity,
            AOK && BOK && A.Target.EndsWith(TEXT("UT-Entry.umap")) && B.Target.EndsWith(TEXT("UT-Entry.umap")));
    }

    static bool Snapshot(UWorld* InWorld, UReflectionCaptureComponent* InTarget,
        TMap<FString, FString>& Out, FString& Digest)
    {
        if (!InWorld || !InWorld->GetOutermost() || !InTarget) return false;
        int32 Count = 0;
        int64 Bytes = 0;
        for (TObjectIterator<UObject> It; It; ++It)
        {
            UObject* O = *It;
            if (!IsValid(O) || O->GetOutermost() != InWorld->GetOutermost() || O->HasAnyFlags(RF_ClassDefaultObject | RF_Transient)) continue;
            if (++Count > 150000) return false;
            FString Row = O->GetClass()->GetPathName() + TEXT("\n");
            for (TFieldIterator<UProperty> PIt(O->GetClass()); PIt; ++PIt)
            {
                UProperty* P = *PIt;
                if (P->HasAnyPropertyFlags(CPF_Transient | CPF_DuplicateTransient | CPF_NonPIEDuplicateTransient)) continue;
                const FString Name = P->GetName();
                // These are the expected in-memory capture-cache state changes; all authored fields remain compared.
                if (O == InTarget && (Name == TEXT("StateId"))) continue;
                if (Row.Len() > 1048576) return false;
                for (int32 I = 0; I < P->ArrayDim; ++I)
                {
                    FString Value;
                    P->ExportText_InContainer(I, Value, O, nullptr, O, 0);
                    Row += Name + TEXT("[") + FString::FromInt(I) + TEXT("]=") + Value + TEXT("\n");
                    if (Row.Len() > 1048576) return false;
                }
            }
            if (AActor* A = Cast<AActor>(O)) Row += TEXT("actor_transform=") + A->GetActorTransform().ToHumanReadableString() + TEXT("\n");
            if (USceneComponent* C = Cast<USceneComponent>(O)) Row += TEXT("component_transform=") + C->GetComponentTransform().ToHumanReadableString() + TEXT("\n");
            const FString Key = O->GetPathName();
            if (Out.Contains(Key)) return false;
            Bytes += Row.Len() * sizeof(TCHAR);
            if (Bytes > 100663296) return false;
            Out.Add(Key, MoveTemp(Row));
        }
        TArray<FString> Keys;
        Out.GetKeys(Keys);
        Keys.Sort();
        FSHA1 Hash;
        for (const FString& Key : Keys)
        {
            const FString& Row = Out.FindChecked(Key);
            Hash.Update(reinterpret_cast<const uint8*>(*Key), Key.Len() * sizeof(TCHAR));
            const uint8 Separator = 0xff; Hash.Update(&Separator, 1);
            Hash.Update(reinterpret_cast<const uint8*>(*Row), Row.Len() * sizeof(TCHAR));
            Hash.Update(&Separator, 1);
        }
        uint8 BytesOut[20]; Hash.Final(); Hash.GetHash(BytesOut);
        Digest = BytesToHex(BytesOut, 20).ToLower();
        return true;
    }

    FString StateIdText() const
    {
        UProperty* P = FindField<UProperty>(Target->GetClass(), TEXT("StateId"));
        FString S;
        if (P) P->ExportText_InContainer(0, S, Target, nullptr, Target, 0);
        return S;
    }

    bool ValidatePayload(FString& HashOut, int32& Dimension, int64& ZeroChannels) const
    {
        const FReflectionCaptureFullHDR* HDR = Target ? Target->GetFullHDRData() : nullptr;
        if (!HDR || !HDR->HasValidData() || HDR->CubemapSize < 16 || HDR->CubemapSize > 512 || (HDR->CubemapSize & (HDR->CubemapSize - 1)) != 0 ||
            HDR->CubemapSize != UReflectionCaptureComponent::GetReflectionCaptureSize_GameThread()) return false;
        const TRefCountPtr<FReflectionCaptureUncompressedData> Raw = HDR->GetUncompressedData();
        if (!Raw.IsValid()) return false;
        const TArray<uint8>& Data = Raw->GetArray();
        int64 Pixels = 0;
        for (int32 N = HDR->CubemapSize; N > 0; N >>= 1) Pixels += int64(N) * N * 6;
        const int64 Expected = Pixels * sizeof(FFloat16Color);
        if (Expected <= 0 || Expected > 64 * 1024 * 1024 || Data.Num() != Expected) return false;
        FSHA1 Hash; Hash.Update(Data.GetData(), Data.Num()); uint8 BytesOut[20]; Hash.Final(); Hash.GetHash(BytesOut);
        HashOut = BytesToHex(BytesOut, 20).ToLower(); Dimension = HDR->CubemapSize; ZeroChannels = 0;
        for (int64 Offset = 0; Offset < Expected; Offset += sizeof(FFloat16Color))
        {
            FFloat16Color C; FMemory::Memcpy(&C, Data.GetData() + Offset, sizeof(C));
            const float V[4] = { C.R.GetFloat(), C.G.GetFloat(), C.B.GetFloat(), C.A.GetFloat() };
            for (int32 I = 0; I < 4; ++I)
            {
                if (!FMath::IsFinite(V[I])) return false;
                if (V[I] == 0.0f) ++ZeroChannels;
            }
        }
        return true;
    }

    void RestoreSettings()
    {
        Settings = SettingsOwner.Get();
        if (!SettingsSaved || !Settings) return;
        Settings->bMonitorContentDirectories = OldMonitor;
        Settings->bAutoSaveEnable = OldAutoSave;
        Settings->bAutoCreateAssets = OldAutoCreate;
        Settings->bAutoDeleteAssets = OldAutoDelete;
        SettingsSaved = false;
    }

    void Finish(const TCHAR* Status, const FString& Why)
    {
        if (Finished) return;
        Finished = true;
        const bool Pins = CheckMapPins();
        // Remain fenced against autosave until module shutdown.
        const bool Good = Pins && FString(Status) == TEXT("diagnostic_completed");
        const bool Wrote = Emit(TEXT("complete"), FString(Status) + TEXT(":") + Why + TEXT("; map_pins_unchanged=") +
            (Pins ? TEXT("true") : TEXT("false")), true, Good);
        if (!Wrote || !Good) UE_LOG(LogUT4Html5Compat, Error, TEXT("Entry reflection diagnostic evidence/invariant failure"));
        FPlatformMisc::RequestExit(false);
    }

    bool Tick(float)
    {
        if (Finished) return false;
        const double Now = FPlatformTime::Seconds();
        if (Now - Started > ERDDeadlineSeconds) { Finish(TEXT("failed"), TEXT("deadline")); return false; }
        if (Phase == 0)
        {
            if (!CheckMapPins()) { Finish(TEXT("failed"), TEXT("map pins changed before recapture")); return false; }
            if (!GEditor || !IsInGameThread() || !FApp::CanEverRender() || !GShaderCompilingManager ||
                GShaderCompilingManager->IsCompiling() || GShaderCompilingManager->HasShaderJobs()) return true;
            World = GEditor->GetEditorWorldContext().World();
            if (!World || World->GetOutermost()->GetName() != ERDPackage || World->WorldType != EWorldType::Editor || !World->PersistentLevel || !World->Scene || World->FeatureLevel < ERHIFeatureLevel::SM4) return true;
            int32 Matches = 0, WorldCaptures = 0;
            const FString ExpectedTarget = World->PersistentLevel->GetPathName() + TEXT(".SphereReflectionCapture_1.NewReflectionComponent");
            for (TObjectIterator<UReflectionCaptureComponent> It; It; ++It)
            {
                UReflectionCaptureComponent* C = *It;
                if (IsValid(C) && C->GetWorld() == World) ++WorldCaptures;
                if (!IsValid(C) || C->GetWorld() != World || !C->GetOwner() || C->GetOwner()->GetName() != TEXT("SphereReflectionCapture_1") ||
                    C->GetName() != TEXT("NewReflectionComponent")) continue;
                ++Matches; Target = C;
                if (C->GetPathName() != ExpectedTarget || C->GetOwner()->GetLevel() != World->PersistentLevel ||
                    C->GetClass()->GetPathName() != TEXT("/Script/Engine.SphereReflectionCaptureComponent") || !C->IsRegistered())
                { Finish(TEXT("failed"), TEXT("target path/class/registration mismatch")); return false; }
            }
            if (Matches != 1 || WorldCaptures != 1 || !Target) { Finish(TEXT("failed"), TEXT("expected one exact capture component")); return false; }
            Settings = SettingsOwner.Get();
            const bool SettingsDisabled = Settings && !Settings->bAutoSaveEnable && !Settings->bMonitorContentDirectories &&
                !Settings->bAutoCreateAssets && !Settings->bAutoDeleteAssets;
            if (!ERDAllowed(GIsEditor, IsRunningCommandlet(), IsInGameThread(), FApp::CanEverRender(),
                World->WorldType == EWorldType::Editor && World->GetOutermost()->GetName() == ERDPackage,
                Target->IsRegistered() && Target->IsVisible(), Matches == 1,
                !GShaderCompilingManager->IsCompiling() && !GShaderCompilingManager->HasShaderJobs(),
                World->FeatureLevel >= ERHIFeatureLevel::SM4, CheckMapPins(), EvidenceHandle != INVALID_HANDLE_VALUE, SettingsDisabled))
            { Finish(TEXT("failed"), TEXT("recapture admission changed")); return false; }
            WorldOwner = World; TargetOwner = Target; TargetPath = Target->GetPathName();
            BeforeObjects.Reset();
            if (!Snapshot(World, Target, BeforeObjects, BeforeDigest)) { Finish(TEXT("failed"), TEXT("before snapshot rejected or over budget")); return false; }
            BeforeStateId = StateIdText();
            if (BeforeStateId.IsEmpty()) { Finish(TEXT("failed"), TEXT("missing reflected state ID")); return false; }
            PackageDirtyBefore = World->GetOutermost()->IsDirty();
            if (!Emit(TEXT("before"), FString::Printf(TEXT("objects=%d;digest=%s;state_id=%s;feature_level=%d;full_hdr_present=%d;full_hdr_compressed_bytes=%d"), BeforeObjects.Num(), *BeforeDigest, *BeforeStateId, int32(World->FeatureLevel), Target->GetFullHDRData() != nullptr, Target->GetFullHDRData() ? Target->GetFullHDRData()->CompressedCapturedData.Num() : 0)))
            { Finish(TEXT("failed"), TEXT("before evidence write failed")); return false; }
            Target->SetCaptureIsDirty();
            UReflectionCaptureComponent::UpdateReflectionCaptureContents(World);
            UObject* VirtualTarget = Target;
            VirtualTarget->PreSave(nullptr); // invokes the component override; it reads back but does not save the package.
            Phase = 1;
            return true;
        }
        if (!WorldOwner.IsValid() || !TargetOwner.IsValid() || WorldOwner.Get() != World || TargetOwner.Get() != Target ||
            !GEditor || GEditor->GetEditorWorldContext().World() != World)
        { Finish(TEXT("failed"), TEXT("captured world/component changed")); return false; }
        TMap<FString, FString> AfterObjects; FString AfterDigest;
        FString PayloadSHA1; int32 Dimension = 0; int64 ZeroChannels = 0;
        const bool SnapshotOK = Snapshot(World, Target, AfterObjects, AfterDigest);
        const bool PayloadOK = ValidatePayload(PayloadSHA1, Dimension, ZeroChannels);
        const bool StateAdvanced = StateIdText() != BeforeStateId;
        const bool Pins = CheckMapPins();
        bool ObjectsEqual = SnapshotOK && AfterObjects.Num() == BeforeObjects.Num();
        if (ObjectsEqual)
            for (const auto& KV : BeforeObjects)
            { const FString* V = AfterObjects.Find(KV.Key); if (!V || *V != KV.Value) { ObjectsEqual = false; break; } }
        const bool PackageDirtySame = World->GetOutermost()->IsDirty() == PackageDirtyBefore;
        if (!Emit(TEXT("after"), FString::Printf(TEXT("snapshot_ok=%d;objects_equal=%d;before_digest=%s;after_digest=%s;state_id_advanced=%d;payload_valid=%d;dimension=%d;payload_sha1=%s;zero_channels=%lld;package_dirty_unchanged=%d;map_pins_unchanged=%d"),
            SnapshotOK, ObjectsEqual, *BeforeDigest, *AfterDigest, StateAdvanced, PayloadOK, Dimension, *PayloadSHA1, ZeroChannels, PackageDirtySame, Pins)) ||
            !SnapshotOK || !ObjectsEqual || !StateAdvanced || !PayloadOK || !PackageDirtySame || !Pins)
        { Finish(TEXT("failed"), TEXT("capture readback, map snapshot, state, or pin validation failed")); return false; }
        Finish(TEXT("diagnostic_completed"), TEXT("in-memory capture/readback recorded; zero-channel count is descriptive only"));
        return false;
    }
};

static TSharedPtr<FERDState> GEntryReflectionDiagnostic;

static int32 EntryReflectionDiagnostic(const FString& Params)
{
    FString Output, OriginalContent;
    if (!GIsEditor || IsRunningCommandlet() || !IsInGameThread() || !FApp::CanEverRender() ||
        !FApp::IsUnattended() || GEngine || GEditor || GEntryReflectionDiagnostic.IsValid() ||
        !FParse::Param(*Params, TEXT("EntryReflectionDiagnostic")) ||
        !FParse::Value(*Params, TEXT("EntryReflectionOutput="), Output) ||
        !FParse::Value(*Params, TEXT("EntryReflectionOriginalContent="), OriginalContent) ||
        FParse::Param(*Params, TEXT("NoDependsGathering")) || FParse::Param(*Params, TEXT("Save")) ||
        FParse::Param(*Params, TEXT("Apply")) || FParse::Param(*Params, TEXT("Write")) ||
        FParse::Param(*Params, TEXT("Manifest")) || FParse::Param(*Params, TEXT("Receipt")))
        return WFRStop(TEXT("entry-reflection-diagnostic-admission"));
    Output = Full(Output); OriginalContent = Full(OriginalContent);
    const FString GameRoot = Full(FPaths::GameDir());
    const FString Relative = TEXT("RestrictedAssets/Maps/UT-Entry.umap");
    const FString Selected = Full(FPackageName::LongPackageNameToFilename(ERDPackage, TEXT(".umap")));
    const FString Original = Full(FPaths::Combine(OriginalContent, Relative));
    const FString OriginalProject = Full(FPaths::GetPath(OriginalContent));
    const FString EngineRoot = Full(FPaths::GetPath(Full(FPaths::EngineDir())));
    const FString OriginalEngineRoot = Full(FPaths::GetPath(OriginalProject));
    if (Output.IsEmpty() || OriginalContent.IsEmpty() || Within(Output, GameRoot) || Within(Output, OriginalProject) ||
        Within(Output, EngineRoot) || Within(Output, OriginalEngineRoot) || Output.ToLower().Contains(TEXT("/content/")) ||
        !FPaths::GetCleanFilename(OriginalContent).Equals(TEXT("Content"), ESearchCase::IgnoreCase) ||
        !Physical(FPaths::GetPath(Output), false) ||
        !IFileManager::Get().DirectoryExists(*FPaths::GetPath(Output)) || IFileManager::Get().FileExists(*Output) ||
        !Physical(OriginalContent, false) || Within(OriginalContent, GameRoot) ||
        !Selected.Equals(Full(FPaths::GameContentDir() / Relative), ESearchCase::IgnoreCase))
        return WFRStop(TEXT("entry-reflection-diagnostic-path-admission"));
    FWURFile A, B;
    if (!FWURFile::Inspect(Selected, false, A) || !FWURFile::Inspect(Original, false, B) ||
        !ERDMapPinAccepted(true, true, A.SHA1.Equals(ERDMapSHA1, ESearchCase::IgnoreCase) && B.SHA1.Equals(ERDMapSHA1, ESearchCase::IgnoreCase),
            A.Identity != B.Identity, A.Target.EndsWith(TEXT("UT-Entry.umap")) && B.Target.EndsWith(TEXT("UT-Entry.umap"))))
        return WFRStop(TEXT("entry-reflection-diagnostic-map-pins"));
    UEditorLoadingSavingSettings* Settings = GetMutableDefault<UEditorLoadingSavingSettings>();
    if (!Settings) return WFRStop(TEXT("entry-reflection-diagnostic-editor-unavailable"));
    TSharedPtr<FERDState> S = MakeShareable(new FERDState);
    S->Output = Output; S->OriginalContent = OriginalContent; S->SelectedMap = Selected; S->OriginalMap = Original;
    S->SelectedIdentity = A.Identity; S->OriginalIdentity = B.Identity; S->SelectedSize = A.Size; S->OriginalSize = B.Size;
    S->Started = FPlatformTime::Seconds(); S->Settings = Settings; S->SettingsOwner = Settings;
    S->EvidenceHandle = CreateFileW(*Output, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (S->EvidenceHandle == INVALID_HANDLE_VALUE) return WFRStop(TEXT("entry-reflection-exclusive-output"));
    S->OldMonitor = Settings->bMonitorContentDirectories; S->OldAutoSave = Settings->bAutoSaveEnable;
    S->OldAutoCreate = Settings->bAutoCreateAssets; S->OldAutoDelete = Settings->bAutoDeleteAssets;
    Settings->bMonitorContentDirectories = false; Settings->bAutoSaveEnable = false;
    Settings->bAutoCreateAssets = false; Settings->bAutoDeleteAssets = false;
    S->SettingsSaved = true;
    if (!S->Emit(TEXT("begin"), TEXT("process-local autosave/autoimport suppression; no package save")))
    { S->RestoreSettings(); CloseHandle(S->EvidenceHandle); S->EvidenceHandle = INVALID_HANDLE_VALUE; return WFRStop(TEXT("entry-reflection-diagnostic-output")); }
    GEntryReflectionDiagnostic = S;
    S->Ticker = FTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([S](float Delta) { return S->Tick(Delta); }), 0.1f);
    return 0;
}

// Called only by the owning module, after editor ticking has ended.
static void ShutdownEntryReflectionDiagnostic()
{
    TSharedPtr<FERDState> S = GEntryReflectionDiagnostic;
    if (!S.IsValid()) return;
    FTicker::GetCoreTicker().RemoveTicker(S->Ticker);
    if (!S->Finished) S->Emit(TEXT("complete"), TEXT("module shutdown before diagnostic completed"), true, false);
    S->RestoreSettings();
    if (S->EvidenceHandle != INVALID_HANDLE_VALUE) { CloseHandle(S->EvidenceHandle); S->EvidenceHandle = INVALID_HANDLE_VALUE; }
    GEntryReflectionDiagnostic.Reset();
}
