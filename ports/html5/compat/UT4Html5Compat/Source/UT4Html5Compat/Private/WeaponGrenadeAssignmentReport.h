// Read-only fixed observation. Include inside UT4Compat after WeaponUsageReport.h.
// Uses its declared public engine APIs and held-handle FWURLedger file admission.
// Normal PostLoad is allowed; new dirty packages are reported, then fail closed.
static const TCHAR* WGASpecSHA1 = TEXT("652095894517da9d8c6d63ca18f49a5c7da2e44a");
static const TCHAR* WGARegistryAuditSHA1 = TEXT("01acccb110ac896f4abfb6ad6eddfc44e4745b07");
static TArray<FString> WGARoots()
{
    TArray<FString> R;
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/BP_GrenadeLauncher"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/BP_GrenadeLauncher_Attach"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_Launcher_3P"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher_1p"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher_3p"));
    return R;
}
static bool WGAParentChain(UMaterialInterface* M, TArray<UMaterialInterface*>& Chain)
{
    Chain.Empty();
    while (M)
    {
        if (Chain.Num() >= 64 || Chain.Contains(M) || M->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
        Chain.Add(M);
        if (Cast<UMaterial>(M)) return true;
        UMaterialInstance* I = Cast<UMaterialInstance>(M);
        if (!I || !I->Parent) return false;
        M = I->Parent;
    }
    return false;
}
static bool WGABudget(int32 Packages, int32 Files, int64 Bytes)
{ return Packages <= 2048 && Files <= 8192 && Bytes >= 0 && Bytes <= 8589934592LL; }
static bool WGARootAllowed(const FWURRoot& Root, const FString& Original)
{
    const FString SourceProject = Full(FPaths::GetPath(Original));
    const FString SourceEngine = Full(FPaths::GetPath(SourceProject) / TEXT("Engine"));
    const FString Project = Full(FPaths::GameDir()), Engine = Full(FPaths::EngineDir());
    const bool SourceLogical = Within(Root.Logical, SourceProject) || Within(Root.Logical, SourceEngine);
    const bool SelectedLogical = Within(Root.Logical, Project) || Within(Root.Logical, Engine);
    const bool SourceTarget = Within(Root.Target, SourceProject) || Within(Root.Target, SourceEngine);
    const bool SelectedTarget = Within(Root.Target, Project) || Within(Root.Target, Engine);
    return Root.Role == TEXT("source") ? SourceLogical && SourceTarget :
        Root.Role == TEXT("selected") && SelectedLogical && (SourceTarget || SelectedTarget);
}
struct FWGAReport
{
    FWURLedger Ledger;
    FString Run, Context;
    int32 Rows = 0, Characters = 0, Components = 0;
    bool BaselineReady = false;
    TSet<UPackage*> ObservedPackages;
    TSet<UObject*> Meshes;
    bool Emit(const TCHAR* Kind, TSharedPtr<FJsonObject> J)
    {
        J->SetStringField(TEXT("schema"), TEXT("ut4-grenade-assignment-v1")); J->SetStringField(TEXT("kind"), Kind);
        J->SetStringField(TEXT("run"), Run); J->SetNumberField(TEXT("sequence"), Rows);
        J->SetBoolField(TEXT("read_only"), true); J->SetBoolField(TEXT("global_usage_complete"), false);
        J->SetBoolField(TEXT("exclusive_runtime_consumption_proven"), false);
        FString Line;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Line)) ||
            Rows >= 8192 || Line.Len() > 65536 || Characters > 8 * 1024 * 1024 - Line.Len()) return false;
        ++Rows; Characters += Line.Len(); UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_GRENADE_ASSIGNMENT %s"), *Line); return true;
    }
    int32 Stop(const TCHAR* Reason)
    {
        if (BaselineReady) Loaded(TEXT("failure_observation"));
        auto J = WURObject(); J->SetStringField(TEXT("reason"), Reason); J->SetStringField(TEXT("context"), Context.Left(2048));
        J->SetStringField(TEXT("phase"), Ledger.Phase.Left(2048)); Emit(TEXT("error"), J);
        return WFRStop(Reason, Context);
    }
    bool Package(const FString& P)
    {
        Context = P;
        if (P.StartsWith(TEXT("/Script/"))) return true;
        FString File;
        if (!FPackageName::DoesPackageExist(P, nullptr, &File) || !File.EndsWith(TEXT(".uasset"))) return false;
        for (const FString& F : {File, FPaths::ChangeExtension(File, TEXT("uexp")), FPaths::ChangeExtension(File, TEXT("ubulk"))})
            if (IFileManager::Get().FileSize(*F) > 268435456) return false;
        if (Ledger.Packages.Num() >= 2048 && !Ledger.Packages.Contains(P)) return false;
        return Ledger.Package(P) && WGABudget(Ledger.Packages.Num(), Ledger.Files.Num(), Ledger.Bytes);
    }
    bool Loaded(const TCHAR* When)
    {
        bool OK = true; int32 Count = 0;
        for (TObjectIterator<UPackage> It; It; ++It)
        {
            UPackage* P = *It; if (++Count > 8192) return false;
            const bool Dirty = P->IsDirty(), NewDirty = Dirty && !Ledger.InitiallyDirty.Contains(P);
            const bool Exempt = P == GetTransientPackage() || P->HasAnyFlags(RF_Transient) || P->GetName().StartsWith(TEXT("/Script/"));
            const bool Unexpected = !Exempt && !Ledger.Packages.Contains(P->GetName()) && !Ledger.InitiallyMemoryOnly.Contains(P);
            if (!ObservedPackages.Contains(P) || NewDirty || Unexpected)
            {
                auto J = WURObject(); J->SetStringField(TEXT("package"), P->GetName()); J->SetStringField(TEXT("phase"), When);
                J->SetBoolField(TEXT("dirty"), Dirty); J->SetBoolField(TEXT("new_dirty"), NewDirty);
                J->SetBoolField(TEXT("unexpected_package"), Unexpected); J->SetBoolField(TEXT("normalization_attribution_claimed"), false);
                if (!Emit(TEXT("load_observation"), J)) return false;
                ObservedPackages.Add(P);
            }
            if (NewDirty || Unexpected) { OK = false; Context = P->GetName(); }
        }
        return OK;
    }
    bool Material(UMaterialInterface* M, const FString& Where, int32 Slot)
    {
        auto J = WURObject(); J->SetStringField(TEXT("context"), Where); J->SetNumberField(TEXT("slot"), Slot);
        J->SetStringField(TEXT("material"), WURPath(M)); J->SetBoolField(TEXT("null_material"), M == nullptr);
        if (!M) return Emit(TEXT("material_chain"), J);
        Context = WURPath(M); TArray<UMaterialInterface*> Chain;
        if (!WGAParentChain(M, Chain)) return false;
        TArray<TSharedPtr<FJsonValue>> Parents;
        for (UMaterialInterface* X : Chain)
        { auto V = WURObject(); V->SetStringField(TEXT("object"), WURPath(X)); V->SetStringField(TEXT("class"), WURPath(X->GetClass())); Parents.Add(MRValue(V)); }
        UMaterial* Base = Cast<UMaterial>(Chain.Last());
        J->SetArrayField(TEXT("chain"), Parents); J->SetStringField(TEXT("base_material"), WURPath(Base));
        J->SetBoolField(TEXT("used_with_static_lighting"), Base->bUsedWithStaticLighting != 0);
        J->SetBoolField(TEXT("special_engine_material"), Base->bUsedAsSpecialEngineMaterial != 0);
        return Emit(TEXT("material_chain"), J);
    }
    bool AssetSlots(UObject* Mesh)
    {
        Context = WURPath(Mesh);
        if (!Mesh || Mesh->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
        if (Meshes.Contains(Mesh)) return true;
        const bool Static = Mesh->IsA(UStaticMesh::StaticClass());
        if (!Static && !Mesh->IsA(USkeletalMesh::StaticClass())) return false;
        auto* A = FindField<UArrayProperty>(Mesh->GetClass(), Static ? TEXT("StaticMaterials") : TEXT("Materials"));
        auto* S = A ? Cast<UStructProperty>(A->Inner) : nullptr;
        auto* P = S ? FindField<UObjectPropertyBase>(S->Struct, TEXT("MaterialInterface")) : nullptr;
        if (!P) return false;
        FScriptArrayHelper Values(A, A->ContainerPtrToValuePtr<void>(Mesh)); if (Values.Num() > 256) return false;
        auto J = WURObject(); J->SetStringField(TEXT("mesh"), WURPath(Mesh)); J->SetStringField(TEXT("class"), WURPath(Mesh->GetClass()));
        J->SetNumberField(TEXT("slot_count"), Values.Num()); J->SetBoolField(TEXT("skeletal"), !Static);
        if (!Emit(TEXT("mesh"), J)) return false; Meshes.Add(Mesh);
        for (int32 I = 0; I < Values.Num(); ++I)
        {
            UObject* Value = P->GetObjectPropertyValue_InContainer(Values.GetRawPtr(I)); auto* M = Cast<UMaterialInterface>(Value);
            if ((Value && !M) || !Material(M, WURPath(Mesh) + TEXT(":asset_slot"), I)) return false;
        }
        return true;
    }
    bool Component(UActorComponent* C, const FString& Where)
    {
        Context = WURPath(C);
        if (!C || C->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad) || ++Components > 1024) return false;
        auto* M = Cast<UMeshComponent>(C); auto J = WURObject();
        J->SetStringField(TEXT("component"), WURPath(C)); J->SetStringField(TEXT("class"), WURPath(C->GetClass()));
        J->SetStringField(TEXT("context"), Where); J->SetBoolField(TEXT("mesh_component"), M != nullptr);
        if (!M) return Emit(TEXT("component"), J);
        UObject* Mesh = nullptr;
        if (auto* S = Cast<USkinnedMeshComponent>(M)) Mesh = S->SkeletalMesh;
        else if (auto* S = Cast<UStaticMeshComponent>(M)) Mesh = S->GetStaticMesh();
        else return false;
        const int32 N = M->GetNumMaterials(); if (N < 0 || N > 256 || M->OverrideMaterials.Num() > 256) return false;
        J->SetStringField(TEXT("mesh"), WURPath(Mesh)); J->SetStringField(TEXT("mesh_class"), Mesh ? WURPath(Mesh->GetClass()) : FString());
        J->SetNumberField(TEXT("resolved_slots"), N); J->SetNumberField(TEXT("override_slots"), M->OverrideMaterials.Num());
        J->SetNumberField(TEXT("mobility"), int32(M->Mobility)); J->SetStringField(TEXT("attach_parent"), WURPath(M->GetAttachParent()));
        J->SetStringField(TEXT("attach_socket"), M->GetAttachSocketName().ToString());
        if (!Emit(TEXT("component"), J)) return false;
        for (int32 I = 0; I < FMath::Max(N, M->OverrideMaterials.Num()); ++I)
        {
            auto* Resolved = I < N ? M->GetMaterial(I) : nullptr;
            auto* Override = M->OverrideMaterials.IsValidIndex(I) ? M->OverrideMaterials[I] : nullptr;
            auto Row = WURObject(); Row->SetStringField(TEXT("component"), WURPath(C)); Row->SetNumberField(TEXT("slot"), I);
            Row->SetStringField(TEXT("resolved"), WURPath(Resolved)); Row->SetStringField(TEXT("override"), WURPath(Override));
            if (!Emit(TEXT("slot"), Row) || !Material(Resolved, Where + TEXT(":resolved"), I) || !Material(Override, Where + TEXT(":override"), I)) return false;
        }
        return !Mesh || AssetSlots(Mesh);
    }
    bool Defaults(UObject* O, const FString& Where)
    {
        if (!O || O->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
        Context = WURPath(O); auto J = WURObject(); J->SetStringField(TEXT("object"), Context);
        J->SetStringField(TEXT("class"), WURPath(O->GetClass())); J->SetStringField(TEXT("context"), Where);
        for (const TCHAR* Name : {TEXT("Mesh1P"), TEXT("Mesh"), TEXT("PickupMesh"), TEXT("AttachmentType"), TEXT("DroppedPickupClass"), TEXT("InventoryType"), TEXT("WeaponType")})
        {
            auto* P = FindField<UObjectPropertyBase>(O->GetClass(), Name); UObject* V = P ? P->GetObjectPropertyValue_InContainer(O) : nullptr;
            auto Row = WURObject(); Row->SetBoolField(TEXT("declared"), P != nullptr); Row->SetStringField(TEXT("value"), WURPath(V));
            Row->SetStringField(TEXT("value_class"), V ? WURPath(V->GetClass()) : FString()); J->SetObjectField(Name, Row);
            if (auto* C = Cast<UActorComponent>(V)) if (!Component(C, Where + TEXT(":") + Name)) return false;
        }
        UFunction* F = O->FindFunction(FName(TEXT("GetPickupMeshTemplate")));
        if (F && F->Script.Num() > 1024 * 1024) return false;
        J->SetStringField(TEXT("pickup_function"), WURPath(F)); J->SetStringField(TEXT("pickup_function_owner"), F ? WURPath(F->GetOuter()) : FString());
        J->SetBoolField(TEXT("pickup_function_native"), F && F->HasAnyFunctionFlags(FUNC_Native));
        J->SetBoolField(TEXT("pickup_script_present"), F && F->Script.Num() > 0);
        J->SetNumberField(TEXT("pickup_script_bytes"), F ? F->Script.Num() : 0); J->SetBoolField(TEXT("pickup_function_executed"), false);
        if (F && F->Script.Num()) { FSHAHash H; FSHA1::HashBuffer(F->Script.GetData(), F->Script.Num(), H.Hash); J->SetStringField(TEXT("pickup_script_sha1"), H.ToString()); }
        return Emit(TEXT("defaults"), J);
    }
    bool Templates(UBlueprintGeneratedClass* Actual)
    {
        TSet<UClass*> Seen; TArray<UClass*> Classes;
        for (UClass* C = Actual; C; C = C->GetSuperClass())
        {
            Context = WURPath(C); if (Seen.Num() >= 64 || Seen.Contains(C)) return false; Seen.Add(C);
            Classes.Add(C);
        }
        for (UClass* C : Classes)
        {
            Context = WURPath(C);
            UObject* CDO = C->GetDefaultObject(false); if (!CDO || !Defaults(CDO, Context + TEXT(":cdo"))) return false;
            auto J = WURObject(); J->SetStringField(TEXT("root_class"), WURPath(Actual)); J->SetStringField(TEXT("class"), WURPath(C));
            J->SetStringField(TEXT("super"), WURPath(C->GetSuperClass())); J->SetStringField(TEXT("cdo"), WURPath(CDO));
            J->SetBoolField(TEXT("native"), C->HasAnyClassFlags(CLASS_Native)); if (!Emit(TEXT("class"), J)) return false;
            if (AActor* Actor = Cast<AActor>(CDO))
            { TArray<UActorComponent*> NativeComponents; Actor->GetComponents(NativeComponents); if (NativeComponents.Num() > 256) return false;
              for (UActorComponent* T : NativeComponents) if (!Component(T, WURPath(C) + TEXT(":cdo_components"))) return false; }
        }
        TArray<const UBlueprintGeneratedClass*> Hierarchy;
        if (!UBlueprintGeneratedClass::GetGeneratedClassesHierarchy(Actual, Hierarchy) || Hierarchy.Num() < 1 || Hierarchy.Num() > 64) return false;
        for (const UBlueprintGeneratedClass* B : Hierarchy)
        {
            if (!B || B->ComponentTemplates.Num() > 256) return false;
            for (UActorComponent* T : B->ComponentTemplates) if (!Component(T, WURPath(B) + TEXT(":add_component"))) return false;
            if (B->SimpleConstructionScript)
            {
                const auto& Nodes = B->SimpleConstructionScript->GetAllNodes(); if (Nodes.Num() > 256) return false;
                for (USCS_Node* N : Nodes)
                {
                    if (!N) return false;
                    UActorComponent* T = N->GetActualComponentTemplate(Actual);
                    auto Row = WURObject(); Row->SetStringField(TEXT("owner_class"), WURPath(B)); Row->SetStringField(TEXT("root_class"), WURPath(Actual));
                    Row->SetStringField(TEXT("node"), WURPath(N)); Row->SetStringField(TEXT("variable"), N->GetVariableName().ToString());
                    Row->SetStringField(TEXT("declared_template"), WURPath(N->ComponentTemplate)); Row->SetStringField(TEXT("actual_template"), WURPath(T));
                    if (!Emit(TEXT("scs"), Row) || !Component(T, WURPath(Actual) + TEXT(":scs:") + WURPath(N))) return false;
                }
            }
            // Stored overrides are observed independently of the engine's config-gated lookup.
            UInheritableComponentHandler* H = B->InheritableComponentHandler; if (!H) continue;
            if (H->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false; int32 Records = 0;
            for (auto It = H->CreateRecordIterator(); It; ++It)
            {
                const FComponentOverrideRecord& R = *It;
                if (++Records > 256 || !R.ComponentKey.IsValid() || !R.ComponentTemplate || !R.ComponentClass || !R.ComponentTemplate->IsA(R.ComponentClass)) return false;
                auto Row = WURObject(); Row->SetStringField(TEXT("root_class"), WURPath(Actual)); Row->SetStringField(TEXT("owner_class"), WURPath(B));
                Row->SetStringField(TEXT("key_owner"), WURPath(R.ComponentKey.GetComponentOwner())); Row->SetStringField(TEXT("key_variable"), R.ComponentKey.GetSCSVariableName().ToString());
                Row->SetStringField(TEXT("key_guid"), R.ComponentKey.GetAssociatedGuid().ToString()); Row->SetStringField(TEXT("template"), WURPath(R.ComponentTemplate));
                if (!Emit(TEXT("inherited"), Row) || !Component(R.ComponentTemplate, WURPath(Actual) + TEXT(":inherited:") + WURPath(H))) return false;
            }
        }
        return true;
    }
};
static bool WGAInputs(FWGAReport& R, const FString& Path, const FString& Hash, const FString& Original, TSharedPtr<FJsonObject> Spec)
{
    R.Context = Path;
    if (!WTUSHA1(Hash) || IFileManager::Get().FileSize(*Path) <= 0 || IFileManager::Get().FileSize(*Path) > 1024 * 1024 || !R.Ledger.Add(Path, false, Hash)) return false;
    TSharedPtr<FJsonObject> J; const TArray<TSharedPtr<FJsonValue>> *Roots = nullptr, *Files = nullptr, *Packages = nullptr;
    if (!ReadJson(Path, J) || Str(J, TEXT("schema")) != TEXT("ut4-grenade-assignment-inputs-v1") ||
        !J->TryGetArrayField(TEXT("read_only_roots"), Roots) || Roots->Num() < 1 || Roots->Num() > 1024 ||
        !J->TryGetArrayField(TEXT("files"), Files) || Files->Num() < 8 || Files->Num() > 256 ||
        !J->TryGetArrayField(TEXT("packages"), Packages) || Packages->Num() != 647) return false;
    TSet<FString> RootNames, Roles, FileNames, PackageNames; const auto Fixed = WGARoots();
    for (const auto& V : *Roots)
    {
        if (V->Type != EJson::Object) return false; auto Row = V->AsObject(); FWURRoot Root;
        Root.Logical = Str(Row, TEXT("logical_root")); Root.Target = Str(Row, TEXT("physical_root")); Root.Role = Str(Row, TEXT("role"));
        if (!WURLocalPath(Root.Logical) || !WURLocalPath(Root.Target) || Root.Logical != Full(Root.Logical) || Root.Target != Full(Root.Target) ||
            !WGARootAllowed(Root, Original) || RootNames.Contains(Root.Logical.ToLower())) return false;
#if PLATFORM_WINDOWS
        HANDLE H; FString Target; if (!WURMappedOpen(Root.Logical, Root, true, H, Target)) return false; CloseHandle(H);
#else
        return false;
#endif
        RootNames.Add(Root.Logical.ToLower()); R.Ledger.ReadRoots.Add(Root);
        if (!R.Emit(TEXT("read_root"), Row)) return false;
    }
    for (const auto& V : *Files)
    {
        if (V->Type != EJson::Object) return false; auto Row = V->AsObject();
        const FString P = Str(Row, TEXT("path")), H = Str(Row, TEXT("sha1")), Role = Str(Row, TEXT("role")); R.Context = P;
        if (!WURLocalPath(P) || P != Full(P) || Role.IsEmpty() || Role.Len() > 128 || Roles.Contains(Role) || FileNames.Contains(P.ToLower()) ||
            !WTUSHA1(H) || IFileManager::Get().FileSize(*P) > 268435456 || !R.Ledger.Add(P, false, H)) return false;
        if (Role == TEXT("registry-audit") && !H.Equals(WGARegistryAuditSHA1, ESearchCase::IgnoreCase)) return false;
        for (int32 I = 0; I < Fixed.Num(); ++I)
            if (Role == FString::Printf(TEXT("original-root-%d"), I) && P != Full(Original / Fixed[I].Mid(6) + TEXT(".uasset"))) return false;
        Roles.Add(Role); FileNames.Add(P.ToLower()); if (!R.Emit(TEXT("input"), Row)) return false;
    }
    if (!Roles.Contains(TEXT("registry-audit")) || !Roles.Contains(TEXT("engine-api-manifest"))) return false;
    for (int32 I = 0; I < Fixed.Num(); ++I) if (!Roles.Contains(FString::Printf(TEXT("original-root-%d"), I))) return false;
    TSet<FString> Allowed;
    for (const auto& V : Spec->GetArrayField(TEXT("hard_forward_packages"))) Allowed.Add(V->AsString());
    if (Allowed.Num() != 647) return false;
    for (const auto& V : *Packages)
    {
        if (V->Type != EJson::Object) return false; auto Row = V->AsObject(); const FString P = Str(Row, TEXT("package")), H = Str(Row, TEXT("sha1"));
        if (!Allowed.Contains(P) || PackageNames.Contains(P) || !WTUSHA1(H) || !R.Package(P)) return false;
        const FString Key = R.Ledger.Packages.FindChecked(P).ToLower();
        if (!R.Ledger.Files.FindChecked(Key).SHA1.Equals(H, ESearchCase::IgnoreCase)) return false;
        PackageNames.Add(P);
    }
    return WGABudget(R.Ledger.Packages.Num(), R.Ledger.Files.Num(), R.Ledger.Bytes);
}
static int32 WeaponGrenadeAssignmentReport(const FString& Params)
{
    FString Mode, SpecPath, Inputs, InputsHash, Original, Forbidden;
    if (!GIsEditor || !IsRunningCommandlet() || !IsInGameThread() ||
        !FParse::Value(*Params, TEXT("Mode="), Mode) || !Mode.Equals(TEXT("WeaponGrenadeAssignmentReport"), ESearchCase::IgnoreCase) ||
        !FParse::Value(*Params, TEXT("GrenadeAssignmentSpec="), SpecPath) || !FParse::Value(*Params, TEXT("GrenadeAssignmentInputs="), Inputs) ||
        !FParse::Value(*Params, TEXT("GrenadeAssignmentInputsSHA1="), InputsHash) || !FParse::Value(*Params, TEXT("GrenadeOriginalContent="), Original) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden)) return WFRStop(TEXT("grenade-assignment-admission"));
    if (!WURLocalPath(Original) || Original != Full(Original) || !Physical(Original, false) || !IFileManager::Get().DirectoryExists(*Original) ||
        !WURLocalPath(SpecPath) || SpecPath != Full(SpecPath) || !WURLocalPath(Inputs) || Inputs != Full(Inputs)) return WFRStop(TEXT("grenade-assignment-path"));
    FWGAReport R; R.Run = InputsHash.ToLower(); TSharedPtr<FJsonObject> Spec;
    if (IFileManager::Get().FileSize(*SpecPath) > 1024 * 1024 || !R.Ledger.Add(SpecPath, false, WGASpecSHA1) || !ReadJson(SpecPath, Spec) ||
        Str(Spec, TEXT("schema")) != TEXT("ut4-grenade-assignment-spec-v1")) return R.Stop(TEXT("grenade-assignment-spec"));
    const auto Fixed = WGARoots();
    for (const FString& P : Fixed) if (FindPackage(nullptr, *P)) { R.Context = P; return R.Stop(TEXT("grenade-root-preloaded")); }
    if (!WGAInputs(R, Inputs, InputsHash, Original, Spec)) return R.Stop(TEXT("grenade-assignment-inputs"));
    int32 Preloaded = 0;
    for (TObjectIterator<UPackage> It; It; ++It)
    {
        UPackage* P = *It; if (++Preloaded > 8192) return R.Stop(TEXT("grenade-baseline-budget"));
        if (P->IsDirty()) R.Ledger.InitiallyDirty.Add(P); R.ObservedPackages.Add(P);
        auto J = WURObject(); J->SetStringField(TEXT("package"), P->GetName()); J->SetBoolField(TEXT("dirty"), P->IsDirty());
        if (!R.Emit(TEXT("initial_package"), J)) return R.Stop(TEXT("grenade-output-budget"));
        FString File;
        if (FPackageName::DoesPackageExist(P->GetName(), nullptr, &File)) { if (!R.Package(P->GetName())) return R.Stop(TEXT("grenade-baseline-pins")); }
        else R.Ledger.InitiallyMemoryOnly.Add(P);
    }
    R.BaselineReady = true;
    auto Begin = WURObject(); Begin->SetStringField(TEXT("spec_sha1"), WGASpecSHA1); Begin->SetStringField(TEXT("registry_audit_sha1"), WGARegistryAuditSHA1);
    Begin->SetStringField(TEXT("scope"), TEXT("fixed_defaults_templates")); Begin->SetNumberField(TEXT("explicit_roots"), 6);
    Begin->SetNumberField(TEXT("hard_forward_admitted_packages"), 647); Begin->SetBoolField(TEXT("compile_on_load_disabled"), false);
    Begin->SetStringField(TEXT("limitations"), TEXT("PostLoad CDO/templates only; no Blueprint dispatch, actors/worlds, live renderer LCI, maps, soft-reference completeness or dynamic-consumer proof."));
    if (!R.Emit(TEXT("begin"), Begin) || !R.Loaded(TEXT("before_first_load")) || !R.Ledger.Check()) return R.Stop(TEXT("grenade-before-fingerprints"));
    TArray<UObject*> Objects;
    for (int32 I = 0; I < Fixed.Num(); ++I)
    {
        const FString P = Fixed[I]; R.Context = P; R.Ledger.Phase = TEXT("load:") + P;
        const bool DependencyLoaded = FindPackage(nullptr, *P) != nullptr;
        if (!R.Loaded(TEXT("before_load")) || !R.Ledger.LoadPins(P)) return R.Stop(TEXT("grenade-before-load"));
        UObject* O = LoadObject<UObject>(nullptr, *ObjectPath(P), nullptr, LOAD_NoRedirects);
        auto J = WURObject(); J->SetStringField(TEXT("package"), P); J->SetStringField(TEXT("object"), WURPath(O));
        J->SetStringField(TEXT("class"), O ? WURPath(O->GetClass()) : FString()); J->SetBoolField(TEXT("dependency_loaded_before_request"), DependencyLoaded);
        J->SetBoolField(TEXT("dirty_after_load"), O && O->GetOutermost()->IsDirty());
        const bool Emitted = R.Emit(TEXT("root"), J), LoadedOK = R.Loaded(TEXT("after_load"));
        if (!Emitted || !LoadedOK || !R.Ledger.LoadPins(P) || !O || WURPath(O) != ObjectPath(P) || O->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return R.Stop(TEXT("grenade-root-load"));
        const bool Exact = I < 2 ? O->GetClass() == UBlueprint::StaticClass() : (I < 4 ? O->GetClass() == UMaterialInstanceConstant::StaticClass() : O->GetClass() == USkeletalMesh::StaticClass());
        if (!Exact) return R.Stop(TEXT("grenade-root-type")); Objects.Add(O);
    }
    for (int32 I = 0; I < 2; ++I)
    {
        UBlueprint* B = Cast<UBlueprint>(Objects[I]); auto* C = Cast<UBlueprintGeneratedClass>(B->GeneratedClass);
        const FString Expected = Str(Spec->GetArrayField(TEXT("roots"))[I]->AsObject(), TEXT("expected_native_parent"));
        if (!C || !B->ParentClass || WURPath(B->ParentClass) != Expected || !B->ParentClass->HasAnyClassFlags(CLASS_Native) ||
            C->ClassGeneratedBy != B || C->GetSuperClass() != B->ParentClass || WURPath(C) != ObjectPath(Fixed[I]) + TEXT("_C") || !R.Templates(C)) return R.Stop(TEXT("grenade-templates"));
    }
    auto* One = Cast<UMaterialInstance>(Objects[2]); auto* Three = Cast<UMaterialInstance>(Objects[3]);
    if (Three->Parent != One || !R.Material(One, TEXT("fixed_1p"), -1) || !R.Material(Three, TEXT("fixed_3p"), -1) ||
        !R.AssetSlots(Objects[4]) || !R.AssetSlots(Objects[5])) return R.Stop(TEXT("grenade-material-mesh"));
    R.Ledger.Phase = TEXT("final_fingerprints");
    if (!R.Loaded(TEXT("after_observation")) || !R.Ledger.Check()) return R.Stop(TEXT("grenade-after-fingerprints"));
    for (const auto& KV : R.Ledger.Files)
    {
        const FWURFile& F = KV.Value; auto J = WURObject(); J->SetStringField(TEXT("path"), F.Path); J->SetStringField(TEXT("target"), F.Target);
        J->SetBoolField(TEXT("missing"), F.Missing); J->SetNumberField(TEXT("bytes"), double(F.Size));
        J->SetStringField(TEXT("sha1_before"), F.SHA1); J->SetStringField(TEXT("sha1_after"), F.SHA1); J->SetStringField(TEXT("identity"), F.Identity);
        if (!R.Emit(TEXT("file"), J)) return R.Stop(TEXT("grenade-output-budget"));
    }
    auto Done = WURObject(); Done->SetStringField(TEXT("scope"), TEXT("fixed_defaults_templates"));
    Done->SetNumberField(TEXT("fixed_roots"), 6); Done->SetNumberField(TEXT("blueprint_roots"), 2); Done->SetNumberField(TEXT("rows_before_complete"), R.Rows);
    Done->SetNumberField(TEXT("components"), R.Components); Done->SetNumberField(TEXT("files"), R.Ledger.Files.Num());
    Done->SetBoolField(TEXT("all_fingerprints_unchanged"), true); Done->SetBoolField(TEXT("new_dirty_packages"), false);
    Done->SetBoolField(TEXT("pickup_function_executed"), false); Done->SetBoolField(TEXT("live_renderer_lci_observed"), false); Done->SetNumberField(TEXT("assetsSaved"), 0);
    return R.Emit(TEXT("complete"), Done) ? 0 : R.Stop(TEXT("grenade-output-budget"));
}
