// Fixed two-mesh, read-only baseline for the subsequent material-slot repair.
// Include after EnforcerMaterialCandidate.h and EnforcerMeshInvariant.h.
static int32 EnforcerMeshReport(const FString& Params)
{
    FString Mode, Preparation; FEnforcerCandidatePins Pins;
    FParse::Value(*Params, TEXT("Mode="), Mode);
    if (!GIsEditor || !IsInGameThread() || !Mode.Equals(TEXT("EnforcerMeshReport"), ESearchCase::IgnoreCase) ||
        FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")) || !Pins.Read(Params) ||
        !FParse::Value(*Params, TEXT("EnforcerMeshPreparation="), Preparation) || !Physical(Preparation, false) ||
        !HashFile(Preparation).Equals(TEXT("ac5742ef7b0e2666ecc8b55494a173fba3e5cd21"), ESearchCase::IgnoreCase))
        return WFRStop(TEXT("enforcer-mesh-admission"));
    FWGAReport Report; Report.Schema = TEXT("ut4-enforcer-mesh-baseline-v1");
    Report.Prefix = TEXT("COMPAT_ENFORCER_MESH"); Report.Run = Pins.Consumers.Hash;
    const auto Targets = ECRRoots(); int32 Count = 0;
    for (int32 I = 3; I < 5; ++I)
    {
        FString File;
        if (!Pins.Check() || !FPackageName::DoesPackageExist(Targets[I], nullptr, &File) || !Physical(File, false))
            return WFRStop(TEXT("enforcer-mesh-physical"), Targets[I]);
        auto* Mesh = LoadObject<USkeletalMesh>(nullptr, *ObjectPath(Targets[I]));
        if (!WGRReady(Mesh) || Mesh->GetClass() != USkeletalMesh::StaticClass() || !Pins.Check())
            return WFRStop(TEXT("enforcer-mesh-load"), Targets[I]);
        TSharedPtr<FJsonObject> First, Second; FString Error;
        const bool Dirty = Mesh->GetOutermost()->IsDirty();
        if (!FEnforcerMeshInvariant::Snapshot(Mesh, First, Error) ||
            !FEnforcerMeshInvariant::Snapshot(Mesh, Second, Error) ||
            !First.IsValid() || !Second.IsValid() || !FWeaponRepair().Same(MRValue(First), MRValue(Second)) ||
            Mesh->GetOutermost()->IsDirty() != Dirty || !Pins.Check())
            return WFRStop(TEXT("enforcer-mesh-snapshot"), Targets[I] + TEXT(": ") + Error);
        auto Row = WGRObject(); Row->SetStringField(TEXT("package"), Targets[I]);
        Row->SetStringField(TEXT("file_sha1"), HashFile(File));
        Row->SetObjectField(TEXT("snapshot"), First);
        Row->SetBoolField(TEXT("repeat_equal"), true); Row->SetBoolField(TEXT("dirty_after_load"), Dirty);
        Row->SetNumberField(TEXT("lods"), Mesh->GetImportedResource()->LODModels.Num());
        Row->SetNumberField(TEXT("materials"), Mesh->Materials.Num());
        if (!Report.Emit(TEXT("mesh"), Row)) return 1;
        ++Count;
    }
    if (Count != 2 || !Pins.Check() || !Physical(Preparation, false) ||
        !HashFile(Preparation).Equals(TEXT("ac5742ef7b0e2666ecc8b55494a173fba3e5cd21"), ESearchCase::IgnoreCase))
        return WFRStop(TEXT("enforcer-mesh-final"));
    auto Done = WGRObject(); Done->SetNumberField(TEXT("meshes"), Count);
    Done->SetNumberField(TEXT("assets_saved"), 0); Done->SetBoolField(TEXT("selected_bytes_unchanged"), true);
    Done->SetBoolField(TEXT("runtime_behavior_verified"), false);
    return Report.Emit(TEXT("complete"), Done) ? 0 : 1;
}
