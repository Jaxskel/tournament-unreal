// Observation only: fixed seven packages, existing native CDO/component readers.
// Normal asset PostLoad is allowed and dirty state is reported, never cleared.
// No saves, world loading, actor spawning, pickup execution or material setters.
static TArray<FString> ECRRoots()
{
    TArray<FString> R;
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Enforcer"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Enforcer_Attach"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Dual_Enforcer_Attach"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_1p"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_3p"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/M_Enforcer_Gun"));
    R.Add(TEXT("/Game/RestrictedAssets/Weapons/Enforcer/Materials/Materials_thirdPerson/M_Enforcer_Gun_3rdPerson_Inst"));
    return R;
}
static const TCHAR* ECRParent(int32 I)
{
    return I == 0 ? TEXT("/Script/UnrealTournament.UTWeap_Enforcer") :
        I == 1 ? TEXT("/Script/UnrealTournament.UTWeaponAttachment") :
        I == 2 ? TEXT("/Script/UnrealTournament.UTWeapAttachment_Enforcer") : TEXT("");
}
struct FEnforcerConsumerInputs
{
    FString Path, Hash;
    TArray<TSharedPtr<FJsonObject>> Rows;
    bool Check() const
    {
        if (!WTUSHA1(Hash) || IFileManager::Get().FileSize(*Path) <= 0 ||
            IFileManager::Get().FileSize(*Path) > 65536 || !HashFile(Path).Equals(Hash, ESearchCase::IgnoreCase) || Rows.Num() != 7) return false;
        const TArray<FString> Roots = ECRRoots();
        for (int32 I = 0; I < Roots.Num(); ++I)
        {
            const auto& Row = Rows[I]; FString File; double Bytes = 0;
            if (Str(Row, TEXT("package")) != Roots[I] || !WTUSHA1(Str(Row, TEXT("sha1"))) ||
                !Row->TryGetNumberField(TEXT("bytes"), Bytes) || Bytes <= 0 || Bytes > 64 * 1024 * 1024 ||
                !FPackageName::DoesPackageExist(Roots[I], nullptr, &File) || !File.EndsWith(TEXT(".uasset")) ||
                !Full(File).Equals(Full(Str(Row, TEXT("file"))), ESearchCase::IgnoreCase) ||
                IFileManager::Get().FileSize(*File) != Bytes || !HashFile(File).Equals(Str(Row, TEXT("sha1")), ESearchCase::IgnoreCase)) return false;
        }
        return true;
    }
    bool Read()
    {
        if (!WTUSHA1(Hash) || IFileManager::Get().FileSize(*Path) <= 0 || IFileManager::Get().FileSize(*Path) > 65536 ||
            !HashFile(Path).Equals(Hash, ESearchCase::IgnoreCase)) return false;
        TSharedPtr<FJsonObject> J; const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (!ReadJson(Path, J) || Str(J, TEXT("schema")) != TEXT("ut4-enforcer-consumer-inputs-v1") ||
            !Full(Str(J, TEXT("project"))).Equals(Full(FPaths::GameDir()), ESearchCase::IgnoreCase) ||
            !J->TryGetArrayField(TEXT("packages"), Values) || Values->Num() != 7) return false;
        for (const auto& V : *Values) { if (V->Type != EJson::Object) return false; Rows.Add(V->AsObject()); }
        return Check();
    }
};
static bool ECRExtraDefaults(UBlueprintGeneratedClass* Class, FWGAReport& R)
{
    UObject* CDO = Class ? Class->GetDefaultObject(false) : nullptr;
    if (!WGAReady(CDO)) return false;
    auto J = WURObject(); J->SetStringField(TEXT("cdo"), WURPath(CDO));
    for (const TCHAR* Name : {TEXT("LeftMesh"), TEXT("DualWieldAttachmentType"), TEXT("LeftOverlayMesh"), TEXT("OverlayMesh")})
    {
        auto* P = FindField<UObjectPropertyBase>(CDO->GetClass(), Name);
        UObject* V = P ? P->GetObjectPropertyValue_InContainer(CDO) : nullptr;
        auto Item = WURObject(); Item->SetBoolField(TEXT("declared"), P != nullptr); Item->SetStringField(TEXT("value"), WURPath(V));
        J->SetObjectField(Name, Item);
        if (auto* C = Cast<UActorComponent>(V)) if (!R.Component(C, WURPath(CDO) + TEXT(":") + Name)) return false;
    }
    return R.Emit(TEXT("dual_defaults"), J);
}
static int32 EnforcerConsumerReport(const FString& Params)
{
    FString Mode, Forbidden; FEnforcerConsumerInputs Inputs;
    FParse::Value(*Params, TEXT("Mode="), Mode);
    if (!GIsEditor || !IsInGameThread() || !Mode.Equals(TEXT("EnforcerConsumerReport"), ESearchCase::IgnoreCase) ||
        !FParse::Value(*Params, TEXT("EnforcerInputs="), Inputs.Path) || !FParse::Value(*Params, TEXT("EnforcerInputsSHA1="), Inputs.Hash) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")) || !Inputs.Read()) return WFRStop(TEXT("enforcer-consumer-admission"));
    FWGAReport R; R.Schema = TEXT("ut4-enforcer-consumer-v1"); R.Prefix = TEXT("COMPAT_WEAPON_ENFORCER"); R.Run = Inputs.Hash.ToLower();
    auto Begin = WURObject(); Begin->SetStringField(TEXT("inputs_sha1"), R.Run);
    Begin->SetBoolField(TEXT("asset_save_authority"), false); Begin->SetBoolField(TEXT("dependency_immutability_proven"), false);
    if (!R.Emit(TEXT("begin"), Begin)) return 1;
    TArray<UPackage*> DirtyBefore;
    for (TObjectIterator<UPackage> It; It; ++It) if ((*It)->IsDirty()) DirtyBefore.Add(*It);
    TArray<UObject*> Objects; const TArray<FString> Roots = ECRRoots();
    // All seven file pins are checked before the first explicit load and after every load.
    for (int32 I = 0; I < Roots.Num(); ++I)
    {
        if (!Inputs.Check()) return WFRStop(TEXT("enforcer-consumer-before-load"), Roots[I]);
        UObject* O = LoadObject<UObject>(nullptr, *ObjectPath(Roots[I]));
        if (!WGAReady(O) || WURPath(O) != ObjectPath(Roots[I]) || !Inputs.Check()) return WFRStop(TEXT("enforcer-consumer-load"), Roots[I]);
        if ((I < 3 && !Cast<UBlueprint>(O)) || (I >= 3 && I < 5 && !Cast<USkeletalMesh>(O)) ||
            (I >= 5 && !Cast<UMaterialInstanceConstant>(O))) return WFRStop(TEXT("enforcer-consumer-class"), Roots[I]);
        Objects.Add(O);
    }
    for (int32 I = 0; I < Objects.Num(); ++I)
    {
        auto Row = WURObject(); Row->SetStringField(TEXT("object"), WURPath(Objects[I]));
        Row->SetStringField(TEXT("class"), WURPath(Objects[I]->GetClass())); Row->SetObjectField(TEXT("file_pin"), Inputs.Rows[I]);
        Row->SetBoolField(TEXT("package_dirty"), Objects[I]->GetOutermost()->IsDirty());
        if (!R.Emit(TEXT("root"), Row)) return 1;
        if (I < 3)
        {
            auto* B = Cast<UBlueprint>(Objects[I]); auto* C = Cast<UBlueprintGeneratedClass>(B->GeneratedClass);
            if (!WGAReady(C) || C->ClassGeneratedBy != B || C->GetSuperClass() != B->ParentClass ||
                WURPath(B->ParentClass) != ECRParent(I) || WURPath(C) != ObjectPath(Roots[I]) + TEXT("_C") ||
                !R.Templates(C) || !ECRExtraDefaults(C, R)) return WFRStop(TEXT("enforcer-consumer-templates"), R.Context);
        }
        else if (I < 5) { if (!R.AssetSlots(Objects[I])) return WFRStop(TEXT("enforcer-consumer-mesh"), Roots[I]); }
        else if (!R.Material(Cast<UMaterialInterface>(Objects[I]), Roots[I], -1)) return 1;
    }
    int32 DirtyCount = 0;
    for (TObjectIterator<UPackage> It; It; ++It)
    {
        if (!(*It)->IsDirty() || DirtyBefore.Contains(*It)) continue;
        if (++DirtyCount > 256) return WFRStop(TEXT("enforcer-consumer-dirty-budget"));
        auto J = WURObject(); J->SetStringField(TEXT("package"), (*It)->GetName());
        J->SetBoolField(TEXT("normalization_attributed"), false); if (!R.Emit(TEXT("new_dirty_observation"), J)) return 1;
    }
    if (!Inputs.Check()) return WFRStop(TEXT("enforcer-consumer-final-pins"));
    auto Done = WURObject(); Done->SetNumberField(TEXT("root_packages"), 7); Done->SetNumberField(TEXT("blueprints"), 3);
    Done->SetNumberField(TEXT("components"), R.Components); Done->SetNumberField(TEXT("new_dirty_packages"), DirtyCount);
    Done->SetBoolField(TEXT("selected_bytes_unchanged"), true); Done->SetNumberField(TEXT("assets_saved"), 0);
    Done->SetBoolField(TEXT("runtime_behavior_verified"), false); Done->SetBoolField(TEXT("repair_authority"), false);
    Done->SetStringField(TEXT("scope"), TEXT("Fixed CDO/template/slot observation after normal PostLoad; no live world, graph-execution, dependency-immutability or exclusive-consumer proof."));
    return R.Emit(TEXT("complete"), Done) ? 0 : 1;
}
