// Separate original read-only report; include inside UT4Compat AFTER WeaponGrenadeAssignmentReport.h.
// No engine includes here. Requires existing MRDescribe/WTU/WFR/WGA helpers.
// Dispatch: if (Mode.Equals(TEXT("SniperConsumerReport"), ESearchCase::IgnoreCase)) return SniperConsumerReport(Params);
// Args: -Mode=SniperConsumerReport -SniperSpec=<fixed spec> -SniperSpecSHA1=<40hex>
//       -SniperInputs=<operator pin manifest> -SniperInputsSHA1=<40hex>
// Manifest schema ut4-sniper-consumer-inputs-v1: read_only=true, project,
// original_project, packages in exact root order. Each row: package, file,
// original_file, sha1, original_sha1, sha256, original_sha256, bytes,
// original_bytes, selected_exists=true, original_exists=true.
// Native verifies SHA1; SHA256 fields are provenance syntax only and must be
// independently checked by the launcher. Selected/source bytes may differ.
// Only seven root files are checked, not all dependencies. Launcher owns physical
// separation/junction audit and immutable dependency pins. Normal PostLoad may
// dirty memory; report it without clearing, normalizing or authorizing repair.
// Existing CDO/SCS/asset slots are NOT live instances or executed Blueprint proof.
// MRDescribe expands full effective MIC facts, not the shared base graph again.
// Fixed read-only observer. Include after WeaponGrenadeAssignmentReport.h.
// Registry results are package metadata, never proof of live or global closure.
static const TCHAR* SCSniperRoots[] = {
    TEXT("/Game/RestrictedAssets/Weapons/Sniper/BP_Sniper"),
    TEXT("/Game/RestrictedAssets/Weapons/Sniper/BP_Sniper_Attach"),
    TEXT("/Game/RestrictedAssets/Weapons/Sniper/Meshes/Sniper_Rifle_1p"),
    TEXT("/Game/RestrictedAssets/Weapons/Sniper/Meshes/Sniper_Rifle_3p"),
    TEXT("/Game/RestrictedAssets/Proto/UT3_Weapons/WP_SniperRifle/Meshes/SK_WP_SniperRifle_1P"),
    TEXT("/Game/RestrictedAssets/Weapons/Sniper/Materials/M_Sniper_Rifle_Inst"),
    TEXT("/Game/RestrictedAssets/Weapons/Sniper/Materials/Materials_thridperson/M_Sniper_Rifle_3P_Inst")
};
static int32 SCSniperRootCount() { return ARRAY_COUNT(SCSniperRoots); }
static int32 SCSniperRootIndex(const FString& P)
{ for (int32 I = 0; I < SCSniperRootCount(); ++I) if (P == SCSniperRoots[I]) return I; return -1; }
static bool SCSniperMIC(int32 I) { return I == 5 || I == 6; }
static bool SCSniperBlueprint(int32 I) { return I == 0 || I == 1; }
static bool SCSniperRegistryRoot(int32 I)
{ return I >= 0 && I < SCSniperRootCount(); }
static bool SCSniperSHA256Format(const FString& H)
{
    if (H.Len() != 64) return false;
    for (TCHAR C : H) if (!((C >= '0' && C <= '9') || (C >= 'a' && C <= 'f') || (C >= 'A' && C <= 'F'))) return false;
    return true;
}
static bool SCSniperPinMatches(const FString& ExpectedPath, const FString& ActualPath,
    const FString& ExpectedSHA1, const FString& ActualSHA1, int64 ExpectedBytes, int64 ActualBytes)
{
    return ExpectedPath == ActualPath && ExpectedSHA1.Len() == 40 && ActualSHA1.Len() == 40 &&
        ExpectedSHA1.Equals(ActualSHA1, ESearchCase::IgnoreCase) && ExpectedBytes > 0 &&
        ExpectedBytes <= 64 * 1024 * 1024 && ActualBytes == ExpectedBytes;
}

struct FSNCRRootPin { FString Package, Selected, Original, SHA1, OriginalSHA1, SHA256, OriginalSHA256; int64 Bytes = -1, OriginalBytes = -1; };
struct FSNCRInputs
{
    FString Path, Hash, OriginalProject, SpecPath, SpecHash;
    TArray<FSNCRRootPin> Rows;
    bool SpecCheck() const
    {
        if (!WTUSHA1(SpecHash) || IFileManager::Get().FileSize(*SpecPath) <= 0 ||
            IFileManager::Get().FileSize(*SpecPath) > 65536 || !HashFile(SpecPath).Equals(SpecHash, ESearchCase::IgnoreCase)) return false;
        TSharedPtr<FJsonObject> J; bool ReadOnly = false, Repair = true;
        TArray<FString> Roots; for (const TCHAR* P : SCSniperRoots) Roots.Add(P);
        Roots.Sort();
        return ReadJson(SpecPath, J) && Str(J, TEXT("schema")) == TEXT("ut4-sniper-consumer-spec-v1") &&
            J->TryGetBoolField(TEXT("read_only"), ReadOnly) && ReadOnly &&
            J->TryGetBoolField(TEXT("repair_authority"), Repair) && !Repair && WRExactPaths(J, TEXT("roots"), Roots);
    }
    bool Check() const
    {
        if (!SpecCheck() || !WTUSHA1(Hash) || IFileManager::Get().FileSize(*Path) <= 0 ||
            IFileManager::Get().FileSize(*Path) > 2 * 1024 * 1024 ||
            !HashFile(Path).Equals(Hash, ESearchCase::IgnoreCase) || Rows.Num() != SCSniperRootCount()) return false;
        for (int32 I = 0; I < Rows.Num(); ++I)
        {
            const FSNCRRootPin& X = Rows[I]; FString Resolved;
            const FString SelectedExpected = Full(FPaths::GameDir() / TEXT("Content") / X.Package.Mid(6) + TEXT(".uasset"));
            const FString OriginalExpected = Full(OriginalProject / TEXT("Content") / X.Package.Mid(6) + TEXT(".uasset"));
            const int64 SelectedBytes = IFileManager::Get().FileSize(*X.Selected);
            const int64 OriginalBytes = IFileManager::Get().FileSize(*X.Original);
            if (X.Package != SCSniperRoots[I] || !WTUSHA1(X.SHA1) || !WTUSHA1(X.OriginalSHA1) ||
                !FPackageName::DoesPackageExist(X.Package, nullptr, &Resolved) ||
                X.Selected != SelectedExpected || X.Original != OriginalExpected ||
                !SCSniperPinMatches(SelectedExpected, Full(Resolved), X.SHA1, HashFile(X.Selected), X.Bytes, SelectedBytes) ||
                !SCSniperPinMatches(OriginalExpected, X.Original, X.OriginalSHA1, HashFile(X.Original), X.OriginalBytes, OriginalBytes)) return false;
        }
        return true;
    }
    bool Read()
    {
        if (!SpecCheck() || !WTUSHA1(Hash) || IFileManager::Get().FileSize(*Path) <= 0 ||
            IFileManager::Get().FileSize(*Path) > 2 * 1024 * 1024 ||
            !HashFile(Path).Equals(Hash, ESearchCase::IgnoreCase)) return false;
        TSharedPtr<FJsonObject> J; const TArray<TSharedPtr<FJsonValue>>* Values = nullptr; bool ReadOnly = false;
        if (!ReadJson(Path, J) || Str(J, TEXT("schema")) != TEXT("ut4-sniper-consumer-inputs-v1") ||
            !J->TryGetBoolField(TEXT("read_only"), ReadOnly) || !ReadOnly ||
            !Full(Str(J, TEXT("project"))).Equals(Full(FPaths::GameDir()), ESearchCase::IgnoreCase) ||
            !J->TryGetArrayField(TEXT("packages"), Values) || Values->Num() != SCSniperRootCount()) return false;
        OriginalProject = Full(Str(J, TEXT("original_project")));
        if (OriginalProject.IsEmpty() || OriginalProject.Equals(Full(FPaths::GameDir()), ESearchCase::IgnoreCase) || !Physical(OriginalProject, false) ||
            !IFileManager::Get().DirectoryExists(*OriginalProject)) return false;
        for (int32 I = 0; I < Values->Num(); ++I)
        {
            if ((*Values)[I]->Type != EJson::Object) return false;
            const auto Row = (*Values)[I]->AsObject(); FSNCRRootPin X; double B = -1, OB = -1;
            bool SE = false, OE = false;
            X.Package = Str(Row, TEXT("package")); X.Selected = Full(Str(Row, TEXT("file")));
            X.Original = Full(Str(Row, TEXT("original_file"))); X.SHA1 = Str(Row, TEXT("sha1"));
            X.OriginalSHA1 = Str(Row, TEXT("original_sha1")); X.SHA256 = Str(Row, TEXT("sha256"));
            X.OriginalSHA256 = Str(Row, TEXT("original_sha256"));
            if (X.Package != SCSniperRoots[I] || !Row->TryGetNumberField(TEXT("bytes"), B) ||
                !Row->TryGetNumberField(TEXT("original_bytes"), OB) || !FMath::IsFinite(B) || !FMath::IsFinite(OB) || B <= 0 || B > 64 * 1024 * 1024 ||
                B != double(int64(B)) || OB <= 0 || OB > 64 * 1024 * 1024 || OB != double(int64(OB)) ||
                !SCSniperSHA256Format(X.SHA256) || !SCSniperSHA256Format(X.OriginalSHA256) ||
                !Row->TryGetBoolField(TEXT("selected_exists"), SE) || !SE ||
                !Row->TryGetBoolField(TEXT("original_exists"), OE) || !OE) return false;
            X.Bytes = int64(B); X.OriginalBytes = int64(OB); Rows.Add(X);
        }
        return Check();
    }
};

static bool SCSniperBlueprint(UBlueprint* B, FWGAReport& R)
{
    auto* G = B ? Cast<UBlueprintGeneratedClass>(B->GeneratedClass) : nullptr;
    if (!WGAReady(B) || !WGAReady(B->ParentClass) || !WGAReady(G) || G->ClassGeneratedBy != B ||
        G->GetSuperClass() != B->ParentClass || WURPath(G) != WURPath(B) + TEXT("_C")) return false;
    auto J = WURObject(); J->SetStringField(TEXT("blueprint"), WURPath(B));
    J->SetStringField(TEXT("generated_class"), WURPath(G)); J->SetStringField(TEXT("actual_parent_class"), WURPath(B->ParentClass));
    J->SetBoolField(TEXT("generated_class_owned_by_blueprint"), G->ClassGeneratedBy == B);
    J->SetBoolField(TEXT("generated_super_matches_blueprint_parent"), G->GetSuperClass() == B->ParentClass);
    return R.Emit(TEXT("blueprint_identity"), J) && R.Templates(G);
}
static bool SCSniperRegistry(IAssetRegistry& Registry, FWGAReport& R, int32& Count)
{
    for (int32 I = 0; I < SCSniperRootCount(); ++I)
    {
        if (!SCSniperRegistryRoot(I)) continue;
        TArray<FName> Refs; const bool QueryOK = Registry.GetReferencers(FName(SCSniperRoots[I]), Refs, EAssetRegistryDependencyType::Packages);
        Refs.Sort([](const FName& A, const FName& B) { return A.ToString() < B.ToString(); });
        if (!QueryOK) { auto J = WURObject(); J->SetStringField(TEXT("source_package"), SCSniperRoots[I]); J->SetBoolField(TEXT("query_succeeded"), false); if (!R.Emit(TEXT("registry_query"), J)) return false; continue; }
        for (FName Ref : Refs)
        {
            if (++Count > 4096) return false;
            TArray<FAssetData> Assets; Registry.GetAssetsByPackageName(Ref, Assets, true); if (Assets.Num() > 64) return false;
            auto J = WURObject(); J->SetStringField(TEXT("source_package"), SCSniperRoots[I]);
            J->SetStringField(TEXT("referencer_package"), Ref.ToString()); J->SetBoolField(TEXT("query_succeeded"), true);
            J->SetBoolField(TEXT("metadata_known"), Assets.Num() > 0);
            TArray<TSharedPtr<FJsonValue>> Rows;
            for (const FAssetData& A : Assets)
            { auto V = WURObject(); V->SetStringField(TEXT("object"), A.ObjectPath.ToString()); V->SetStringField(TEXT("class"), A.AssetClass.ToString()); Rows.Add(MRValue(V)); }
            J->SetArrayField(TEXT("registered_assets"), Rows); if (!R.Emit(TEXT("registry_direct_referencer"), J)) return false;
        }
    }
    return true;
}
static int32 SniperConsumerReport(const FString& Params)
{
    FString Mode, Forbidden; FSNCRInputs Inputs;
    FParse::Value(*Params, TEXT("Mode="), Mode);
    if (!GIsEditor || !IsInGameThread() || !Mode.Equals(TEXT("SniperConsumerReport"), ESearchCase::IgnoreCase) ||
        !FParse::Value(*Params, TEXT("SniperSpec="), Inputs.SpecPath) || !FParse::Value(*Params, TEXT("SniperSpecSHA1="), Inputs.SpecHash) ||
        !FParse::Value(*Params, TEXT("SniperInputs="), Inputs.Path) || !FParse::Value(*Params, TEXT("SniperInputsSHA1="), Inputs.Hash) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")) || !Inputs.Read()) return WFRStop(TEXT("sniper-consumer-admission"));
    FWGAReport R; R.Schema = TEXT("ut4-sniper-consumer-v1"); R.Prefix = TEXT("COMPAT_SNIPER_CONSUMER"); R.Run = Inputs.Hash.ToLower();
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    Registry.SearchAllAssets(true); if (Registry.IsLoadingAssets()) return WFRStop(TEXT("sniper-registry-loading"));
    TArray<UPackage*> DirtyBefore; for (TObjectIterator<UPackage> It; It; ++It) if ((*It)->IsDirty()) DirtyBefore.Add(*It);
    auto Begin = WURObject(); Begin->SetNumberField(TEXT("root_packages"), 7); Begin->SetBoolField(TEXT("repair_authority"), false);
    Begin->SetStringField(TEXT("spec_sha1"), Inputs.SpecHash);
    Begin->SetBoolField(TEXT("dependency_immutability_proven"), false);
    Begin->SetBoolField(TEXT("runtime_behavior_verified"), false); Begin->SetBoolField(TEXT("global_usage_complete"), false);
    if (!R.Emit(TEXT("begin"), Begin)) return 1;
    for (int32 I = 0; I < SCSniperRootCount(); ++I)
    {
        if (!Inputs.Check()) return WFRStop(TEXT("sniper-consumer-before-load"), SCSniperRoots[I]);
        UObject* O = LoadObject<UObject>(nullptr, *ObjectPath(SCSniperRoots[I]), nullptr, LOAD_NoRedirects);
        if (!WGAReady(O) || WURPath(O) != ObjectPath(SCSniperRoots[I]) || !Inputs.Check())
            return WFRStop(TEXT("sniper-consumer-load-or-pins"), SCSniperRoots[I]);
        const bool Candidate = SCSniperMIC(I), BPIndex = SCSniperBlueprint(I);
        if ((Candidate && O->GetClass() != UMaterialInstanceConstant::StaticClass()) || (BPIndex && !O->IsA(UBlueprint::StaticClass())) ||
            (!Candidate && !BPIndex && !O->IsA(USkeletalMesh::StaticClass())))
            return WFRStop(TEXT("sniper-known-root-class"), SCSniperRoots[I]);
        auto Root = WURObject(); Root->SetNumberField(TEXT("root_index"), I); Root->SetStringField(TEXT("package"), SCSniperRoots[I]);
        Root->SetStringField(TEXT("object"), WURPath(O)); Root->SetStringField(TEXT("class"), WURPath(O->GetClass()));
        Root->SetBoolField(TEXT("known_candidate_mic"), Candidate); Root->SetBoolField(TEXT("dirty_at_observation"), O->GetOutermost()->IsDirty());
        Root->SetStringField(TEXT("selected_file"), Inputs.Rows[I].Selected); Root->SetStringField(TEXT("original_file"), Inputs.Rows[I].Original);
        Root->SetStringField(TEXT("selected_sha1"), Inputs.Rows[I].SHA1); Root->SetStringField(TEXT("original_sha1"), Inputs.Rows[I].OriginalSHA1);
        Root->SetNumberField(TEXT("selected_bytes"), double(Inputs.Rows[I].Bytes)); Root->SetNumberField(TEXT("original_bytes"), double(Inputs.Rows[I].OriginalBytes));
        const bool IsBP = O->IsA(UBlueprint::StaticClass()), IsMaterial = O->IsA(UMaterialInterface::StaticClass());
        const bool IsMesh = O->IsA(USkeletalMesh::StaticClass()) || O->IsA(UStaticMesh::StaticClass());
        Root->SetStringField(TEXT("observed_kind"), IsBP ? TEXT("blueprint") : IsMaterial ? TEXT("material") : IsMesh ? TEXT("mesh") : TEXT("class_only"));
        if (!R.Emit(TEXT("root"), Root)) return 1;
        if (auto* B = Cast<UBlueprint>(O)) { if (!SCSniperBlueprint(B, R)) return WFRStop(TEXT("sniper-blueprint"), R.Context); }
        else if (auto* M = Cast<UMaterialInterface>(O))
        {
            if (!R.Material(M, SCSniperRoots[I], -1)) return WFRStop(TEXT("sniper-material"), R.Context);
            const bool Dirty = M->GetOutermost()->IsDirty(); TSharedPtr<FJsonObject> Facts;
            if (!MRDescribe(M, Registry, Facts)) return WFRStop(TEXT("sniper-material-facts"), R.Context);
            Facts->SetBoolField(TEXT("package_dirty_before_description"), Dirty);
            Facts->SetBoolField(TEXT("live_assignment_proven"), false);
            if (!R.Emit(TEXT("material_facts"), Facts)) return 1;
        }
        else if (IsMesh) { if (!R.AssetSlots(O)) return WFRStop(TEXT("sniper-mesh"), R.Context); }
        else { auto U = WURObject(); U->SetStringField(TEXT("package"), SCSniperRoots[I]); U->SetStringField(TEXT("class"), WURPath(O->GetClass())); U->SetBoolField(TEXT("class_only_observation"), true); if (!R.Emit(TEXT("unknown_root_class"), U)) return 1; }
    }
    int32 DirectRows = 0;
    if (Registry.IsLoadingAssets() || !SCSniperRegistry(Registry, R, DirectRows)) return WFRStop(TEXT("sniper-registry"));
    int32 NewDirty = 0;
    for (TObjectIterator<UPackage> It; It; ++It)
    {
        UPackage* P = *It; if (!P->IsDirty() || DirtyBefore.Contains(P)) continue;
        if (++NewDirty > 256) return WFRStop(TEXT("sniper-dirty-observation-budget"));
        auto J = WURObject(); J->SetStringField(TEXT("package"), P->GetName()); J->SetBoolField(TEXT("normalization_attributed"), false);
        if (!R.Emit(TEXT("new_dirty_observation"), J)) return 1;
    }
    if (!Inputs.Check()) return WFRStop(TEXT("sniper-consumer-final-pins"));
    auto Done = WURObject(); Done->SetNumberField(TEXT("root_packages"), 7); Done->SetNumberField(TEXT("direct_referencer_rows"), DirectRows);
    Done->SetNumberField(TEXT("new_dirty_packages"), NewDirty); Done->SetNumberField(TEXT("assets_saved"), 0);
    Done->SetBoolField(TEXT("selected_bytes_unchanged"), true); Done->SetBoolField(TEXT("original_bytes_unchanged"), true);
    Done->SetBoolField(TEXT("dependency_immutability_proven"), false);
    Done->SetBoolField(TEXT("selected_original_equality_required"), false);
    Done->SetBoolField(TEXT("repair_authority"), false); Done->SetBoolField(TEXT("runtime_behavior_verified"), false);
    Done->SetBoolField(TEXT("global_usage_complete"), false); Done->SetBoolField(TEXT("live_closure_proven"), false);
    Done->SetStringField(TEXT("scope"), TEXT("Fixed 7 package observation; existing CDO/templates/material chains/mesh slots and direct registry metadata only; no world, dispatch, save or live behavior proof."));
    return R.Emit(TEXT("complete"), Done) ? 0 : 1;
}
