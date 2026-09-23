// Fixed transient alias diagnostic, not a repair. Include after WeaponShaderProbe.h.
// Main translation unit additionally needs public ShaderCompiler.h outside its namespace.
struct FWSAlias
{
    const TCHAR* Node; const TCHAR* OldName; const TCHAR* NewName; const TCHAR* Guid;
};
static const FWSAlias WSAliases[] = {
    {TEXT("MaterialExpressionTextureObjectParameter_17"), TEXT("e R Layer Normal"), TEXT("e Base Layer Normal"), TEXT("FF77A8934852A85D34305B94EC473F94")},
    {TEXT("MaterialExpressionTextureObjectParameter_26"), TEXT("e G Layer Normal"), TEXT("e Base Layer Normal"), TEXT("5C74F7734F7EC4EB37C38B8362201791")},
    {TEXT("MaterialExpressionTextureObjectParameter_29"), TEXT("e B Layer Normal"), TEXT("e Base Layer Normal"), TEXT("2AF6375942A3BFBD21492481B5FF2751")},
    {TEXT("MaterialExpressionTextureObjectParameter_19"), TEXT("aa R Layer D"), TEXT("aa Base Layer D"), TEXT("54FD5F7845828802D7FB9BAD936DE0CD")},
    {TEXT("MaterialExpressionTextureObjectParameter_28"), TEXT("aa G Layer D"), TEXT("aa Base Layer D"), TEXT("C3F6E847483C20A897D23D8C67CE7983")},
    {TEXT("MaterialExpressionTextureObjectParameter_31"), TEXT("aa B Layer D"), TEXT("aa Base Layer D"), TEXT("71F42C274A302D3EF22B6FBC17269669")}
};
static FString WSATarget() { return TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher"); }
static FString WSALayer() { return TEXT("/Game/RestrictedAssets/Weapons/Global/Material/MF/MF_LayerSet"); }
static bool WSAField(const TSharedPtr<FJsonObject>& P, const TCHAR* Key, const FString& Expected)
{
    FString Value;
    return P.IsValid() && P->TryGetStringField(Key, Value) && Value == Expected;
}
// ALIAS_NAME_WRITE_BEGIN
static bool WSASetName(UMaterialExpression* E, const FWSAlias& A)
{
    if (!E || E->GetName() != A.Node || E->GetClass()->GetPathName() != TEXT("/Script/Engine.MaterialExpressionTextureObjectParameter") ||
        !E->HasAnyFlags(RF_Transient) || !E->GetOuter() || E->GetOuter()->GetName() != TEXT("UT4SamplerAliasLayer") ||
        E->GetOuter()->GetOuter() != GetTransientPackage() || !E->GetOuter()->HasAnyFlags(RF_Transient)) return false;
    UProperty* P = FindField<UProperty>(E->GetClass(), TEXT("ParameterName"));
    if (!P || P->ArrayDim != 1 || P->GetClass()->GetPathName() != TEXT("/Script/CoreUObject.NameProperty") || P->HasAnyPropertyFlags(CPF_Transient)) return false;
    auto Before = MRProperties(E, true);
    if (!WSAField(Before, TEXT("ParameterName"), A.OldName) || !WSAField(Before, TEXT("ExpressionGUID"), A.Guid)) return false;
    // Same public container accessor already used by the native Usage observer;
    // exact reflected type above permits only an FName, not an arbitrary property.
    FName* Name = static_cast<FName*>(P->ContainerPtrToValuePtr<void>(E));
    if (!Name || *Name != FName(A.OldName)) return false;
    *Name = FName(A.NewName);
    auto After = MRProperties(E, true);
    if (!WSAField(After, TEXT("ParameterName"), A.NewName)) return false;
    After->SetStringField(TEXT("ParameterName"), A.OldName);
    FWeaponRepair Compare;
    return Compare.Same(MRValue(Before), MRValue(After));
}
// ALIAS_NAME_WRITE_END

// Nontransient reflected fields plus every material root/expression input. No registry walk.
static TSharedPtr<FJsonObject> WSAObject(UObject* O)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetStringField(TEXT("class"), O->GetClass()->GetPathName());
    J->SetObjectField(TEXT("properties"), MRProperties(O, true));
    TArray<TSharedPtr<FJsonValue>> Pins;
    if (auto* E = Cast<UMaterialExpression>(O))
        for (auto* P : E->GetInputs()) Pins.Add(MRValue(MRPin(P)));
    if (auto* M = Cast<UMaterial>(O))
        for (int32 I = 0; I < MP_MAX; ++I) Pins.Add(MRValue(MRPin(M->GetExpressionInputForProperty(static_cast<EMaterialProperty>(I)))));
    J->SetArrayField(TEXT("inputs"), Pins);
    return J;
}
static bool WSADrain()
{
    if (!GShaderCompilingManager) return false;
    GShaderCompilingManager->FinishAllCompilation();
    return !GShaderCompilingManager->HasShaderJobs() && !GShaderCompilingManager->IsCompiling();
}

// ALIAS_LIGHTING_POLICY_BEGIN
// PostDuplicate regenerates this field for Material and MaterialInstanceConstant.
// Pin it immediately; normalize only the disposable comparison JSON, never an object.
struct FWSALightingPolicy
{
    UMaterialInterface* Source = nullptr;
    UMaterialInterface* Owned = nullptr;
    FGuid SourceId, ExpectedId;
    FString SourceText, ExpectedText;
    bool Capture(UMaterialInterface* Original, UMaterialInterface* Clone)
    {
        if (Source || Owned || !Original || !Clone || Original == Clone || Original->GetClass() != Clone->GetClass() ||
            Clone->GetOuter() != GetTransientPackage() || !Clone->HasAnyFlags(RF_Transient)) return false;
        const FString Class = Original->GetClass()->GetPathName();
        if (Class != TEXT("/Script/Engine.Material") && Class != TEXT("/Script/Engine.MaterialInstanceConstant")) return false;
        const FGuid OldId = Original->GetLightingGuid(), NewId = Clone->GetLightingGuid();
        if (!OldId.IsValid() || !NewId.IsValid() || NewId == OldId) return false;
        auto Old = MRProperties(Original, true); auto New = MRProperties(Clone, true);
        FString OldText, NewText;
        if (!Old->TryGetStringField(TEXT("LightingGuid"), OldText) || !New->TryGetStringField(TEXT("LightingGuid"), NewText) ||
            OldText.IsEmpty() || NewText.IsEmpty() || OldText == NewText) return false;
        Source = Original; Owned = Clone; SourceId = OldId; ExpectedId = NewId;
        SourceText = OldText; ExpectedText = NewText;
        return true;
    }
    bool Normalize(const TSharedPtr<FJsonObject>& Original, const TSharedPtr<FJsonObject>& Candidate) const
    {
        if (!Source || !Owned || !SourceId.IsValid() || !ExpectedId.IsValid() || SourceId == ExpectedId ||
            Owned->GetOuter() != GetTransientPackage() || !Owned->HasAnyFlags(RF_Transient) ||
            Source->GetLightingGuid() != SourceId || Owned->GetLightingGuid() != ExpectedId ||
            !WSAField(Original, TEXT("LightingGuid"), SourceText) || !WSAField(Candidate, TEXT("LightingGuid"), ExpectedText)) return false;
        Candidate->SetStringField(TEXT("LightingGuid"), SourceText);
        return true;
    }
};
// ALIAS_LIGHTING_POLICY_END

// ALIAS_OWNERSHIP_BEGIN
static bool WSAOwnershipFailure(UObject* Owner, UObject* Node, const TCHAR* Reason, int32 Pin = -1, const FString& Guid = FString())
{
    UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS ownership_failure owner=%s node=%s reason=%s pin=%d guid=%s"),
        Owner ? *Owner->GetPathName().Left(256) : TEXT("null"), Node ? *Node->GetName().Left(128) : TEXT("null"), Reason, Pin, *Guid.Left(64));
    return false;
}
static bool WSAOwnedPin(const FExpressionInput* Old, const FExpressionInput* New,
    const TArray<UMaterialExpression*>& Originals, const TArray<UMaterialExpression*>& Clones, UObject* Owner, UObject* Node, int32 Pin)
{
    if (!Old || !New) return Old == New || WSAOwnershipFailure(Owner, Node, TEXT("pin_presence"), Pin);
    if (!Old->Expression) return !New->Expression || WSAOwnershipFailure(Owner, Node, TEXT("unexpected_target"), Pin);
    for (int32 I = 0; I < Originals.Num(); ++I) if (Originals[I] == Old->Expression)
        return New->Expression == Clones[I] || WSAOwnershipFailure(Owner, Node, TEXT("target_correspondence"), Pin);
    return WSAOwnershipFailure(Owner, Node, TEXT("external_source_target"), Pin);
}
// Complete pass over BOTH graphs is required before any updater/setter. Paths are
// deliberately not canonicalized: an original pointer must never stand in for a clone.
static bool WSAOwnedGraph(UObject* Source, UObject* Clone, UMaterialFunction* Replaced = nullptr, UMaterialFunction* Replacement = nullptr)
{
    FWeaponRepair Inspect;
    auto* A = Inspect.Expressions(Source); auto* B = Inspect.Expressions(Clone);
    auto* SM = Cast<UMaterial>(Source); auto* CM = Cast<UMaterial>(Clone);
    auto* SF = Cast<UMaterialFunction>(Source); auto* CF = Cast<UMaterialFunction>(Clone);
    if (!Source || !Clone || Source == Clone || Source->GetClass() != Clone->GetClass() ||
        (!SM && !SF) || !A || !B || A->Num() != B->Num() || A->Num() > 8192)
        return WSAOwnershipFailure(Clone, nullptr, TEXT("graph_shape"));
    TArray<UMaterialExpression*> SeenA, SeenB;
    for (int32 I = 0; I < A->Num(); ++I)
    {
        auto* O = (*A)[I]; auto* N = (*B)[I];
        if (!O || !N || O == N || SeenA.Contains(O) || SeenB.Contains(N) || O->GetOuter() != Source || N->GetOuter() != Clone ||
            O->GetName() != N->GetName() || O->GetClass() != N->GetClass() || N->GraphNode)
            return WSAOwnershipFailure(Clone, N, TEXT("node_correspondence"), I);
        SeenA.Add(O); SeenB.Add(N);
        if (O->Material != SM || O->Function != SF || N->Material != CM || N->Function != CF)
            return WSAOwnershipFailure(Clone, N, TEXT("owner_backpointer"), I);
        if (auto* OC = Cast<UMaterialExpressionMaterialFunctionCall>(O))
        {
            auto* NC = Cast<UMaterialExpressionMaterialFunctionCall>(N);
            auto* Expected = Replaced && OC->MaterialFunction == Replaced && O->GetName() == TEXT("MaterialExpressionMaterialFunctionCall_0")
                ? Replacement : OC->MaterialFunction;
            if (!Expected || NC->MaterialFunction != Expected)
                return WSAOwnershipFailure(Clone, N, TEXT("called_function"), I);
        }
    }
    for (int32 I = 0; I < A->Num(); ++I)
    {
        const auto OP = (*A)[I]->GetInputs(); const auto NP = (*B)[I]->GetInputs();
        if (OP.Num() != NP.Num() || OP.Num() > 8192) return WSAOwnershipFailure(Clone, (*B)[I], TEXT("pin_count"));
        for (int32 P = 0; P < OP.Num(); ++P) if (!WSAOwnedPin(OP[P], NP[P], *A, *B, Clone, (*B)[I], P)) return false;
    }
    if (SM) for (int32 P = 0; P < MP_MAX; ++P)
        if (!WSAOwnedPin(SM->GetExpressionInputForProperty(static_cast<EMaterialProperty>(P)),
            CM->GetExpressionInputForProperty(static_cast<EMaterialProperty>(P)), *A, *B, Clone, nullptr, P)) return false;
    return true;
}
// The typed interface classes need not be included: first identify the exact pointer
// in the called function's public expression array, then read its reflected Id.
static bool WSAInterface(UMaterialExpressionMaterialFunctionCall* Call, const void* Pointer, const FGuid& Id, bool Input, int32 Pin)
{
    auto* Function = Call->MaterialFunction;
    const FString Guid = Id.ToString();
    const TCHAR* Class = Input ? TEXT("/Script/Engine.MaterialExpressionFunctionInput") : TEXT("/Script/Engine.MaterialExpressionFunctionOutput");
    if (!Function || !Pointer || !Id.IsValid() || Function->FunctionExpressions.Num() > 8192)
        return WSAOwnershipFailure(Call->GetOuter(), Call, TEXT("interface_missing"), Pin, Guid);
    int32 Matches = 0; bool Member = false;
    for (auto* E : Function->FunctionExpressions)
    {
        if (!E || E->GetOuter() != Function) return WSAOwnershipFailure(Function, Call, TEXT("interface_owner"), Pin, Guid);
        if (E->GetClass()->GetPathName() == Class && WSAField(MRProperties(E, true), TEXT("Id"), Guid))
        { ++Matches; if (static_cast<const void*>(E) == Pointer) Member = true; }
    }
    return (Member && Matches == 1) || WSAOwnershipFailure(Function, Call, TEXT("interface_membership_guid"), Pin, Guid);
}
static bool WSAInterfaces(UMaterialExpressionMaterialFunctionCall* Call)
{
    if (!Call || !Call->MaterialFunction || Call->MaterialFunction->FunctionExpressions.Num() > 8192 ||
        Call->FunctionInputs.Num() > 8192 || Call->FunctionOutputs.Num() > 8192)
        return WSAOwnershipFailure(nullptr, Call, TEXT("interface_shape"));
    TArray<FGuid> Inputs, Outputs;
    for (int32 I = 0; I < Call->FunctionInputs.Num(); ++I)
    {
        const auto& P = Call->FunctionInputs[I];
        if (Inputs.Contains(P.ExpressionInputId)) return WSAOwnershipFailure(Call->GetOuter(), Call, TEXT("duplicate_input_guid"), I, P.ExpressionInputId.ToString());
        if (!WSAInterface(Call, P.ExpressionInput, P.ExpressionInputId, true, I)) return false;
        Inputs.Add(P.ExpressionInputId);
    }
    for (int32 I = 0; I < Call->FunctionOutputs.Num(); ++I)
    {
        const auto& P = Call->FunctionOutputs[I];
        if (Outputs.Contains(P.ExpressionOutputId)) return WSAOwnershipFailure(Call->GetOuter(), Call, TEXT("duplicate_output_guid"), I, P.ExpressionOutputId.ToString());
        if (!WSAInterface(Call, P.ExpressionOutput, P.ExpressionOutputId, false, I)) return false;
        Outputs.Add(P.ExpressionOutputId);
    }
    int32 NI = 0, NO = 0;
    for (auto* E : Call->MaterialFunction->FunctionExpressions) if (E)
    {
        if (E->GetClass()->GetPathName() == TEXT("/Script/Engine.MaterialExpressionFunctionInput")) ++NI;
        if (E->GetClass()->GetPathName() == TEXT("/Script/Engine.MaterialExpressionFunctionOutput")) ++NO;
    }
    return (NI == Inputs.Num() && NO == Outputs.Num()) || WSAOwnershipFailure(Call->GetOuter(), Call, TEXT("interface_count"));
}
// ALIAS_OWNERSHIP_END

// ALIAS_ORDINARY_RESOURCE_BEGIN
// Ordinary ShouldCache/static-lighting policy; only shader-map persistence differs.
class FWSAOrdinaryResource final : public FMaterialResource
{
public:
    virtual bool IsPersistent() const override { return false; }
    mutable int32 TranslationRequests = 0;
    virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty Property, FMaterialCompiler* Compiler,
        EShaderFrequency OverrideShaderFrequency, bool bUsePreviousFrameTime) const override
    {
        ++TranslationRequests;
        return FMaterialResource::CompilePropertyAndSetMaterialProperty(Property, Compiler, OverrideShaderFrequency, bUsePreviousFrameTime);
    }
};
// Public dependency fields from the pinned engine's ID comparison; do not call
// the unexported FMaterialShaderMapId equality operator or compare only counts.
static bool WSAOrdinaryIDEqual(const FMaterialShaderMapId& A, const FMaterialShaderMapId& B)
{
    if (!WSPMaterialInstanceIdentitySubset(A, B) || A.ShaderTypeDependencies.Num() != B.ShaderTypeDependencies.Num() ||
        A.ShaderPipelineTypeDependencies.Num() != B.ShaderPipelineTypeDependencies.Num() ||
        A.VertexFactoryTypeDependencies.Num() != B.VertexFactoryTypeDependencies.Num()) return false;
    for (int32 I = 0; I < A.ShaderTypeDependencies.Num(); ++I)
        if (A.ShaderTypeDependencies[I].ShaderType != B.ShaderTypeDependencies[I].ShaderType ||
            A.ShaderTypeDependencies[I].SourceHash != B.ShaderTypeDependencies[I].SourceHash) return false;
    for (int32 I = 0; I < A.ShaderPipelineTypeDependencies.Num(); ++I)
        if (A.ShaderPipelineTypeDependencies[I].ShaderPipelineType != B.ShaderPipelineTypeDependencies[I].ShaderPipelineType ||
            A.ShaderPipelineTypeDependencies[I].StagesSourceHash != B.ShaderPipelineTypeDependencies[I].StagesSourceHash) return false;
    for (int32 I = 0; I < A.VertexFactoryTypeDependencies.Num(); ++I)
        if (A.VertexFactoryTypeDependencies[I].VertexFactoryType != B.VertexFactoryTypeDependencies[I].VertexFactoryType ||
            A.VertexFactoryTypeDependencies[I].VFSourceHash != B.VertexFactoryTypeDependencies[I].VFSourceHash) return false;
    return true;
}
// ALIAS_ORDINARY_RESOURCE_END

struct FWSAliasState
{
    FWeaponTessProof& Proof; FString MasterHash;
    UMaterial* Master = nullptr; UMaterialFunction* Layer = nullptr; UMaterialInstanceConstant* MI = nullptr;
    UMaterial* CloneMaster = nullptr; UMaterialFunction* CloneLayer = nullptr; UMaterialInstanceConstant* CloneMI = nullptr;
    FMaterialResource* Resource = nullptr;
    TArray<UObject*> Roots, Sources;
    TMap<UObject*, TSharedPtr<FJsonObject>> Before;
    TMap<UPackage*, bool> Dirty;
    TSharedPtr<FJsonObject> Hashes = MakeShareable(new FJsonObject);
    FGuid MasterId, LayerId;
    FWSALightingPolicy MasterLighting, MILighting;
    bool Captured = false, Closed = false, FinalOK = false, Attempted = false;
    bool OrdinaryLighting = false; // ALIAS_ORDINARY_STATE
    explicit FWSAliasState(FWeaponTessProof& P, const FString& H) : Proof(P), MasterHash(H) {}
    ~FWSAliasState() { Close(); }

    // ALIAS_LIFETIME_BEGIN
    bool Close()
    {
        if (Closed) return FinalOK;
        const bool Global = WSADrain();
        if (Resource) Resource->FinishCompilation();
        if (!Global || (Resource && !Resource->IsCompilationFinished()))
        {
            UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS undrained roots/resource retained until process exit"));
            Closed = true; return false;
        }
        if (Resource) { delete Resource; Resource = nullptr; }
        const bool SnapshotOK = !Captured || Unchanged();
        const bool BytesOK = Proof.Check(MasterHash);
        FinalOK = SnapshotOK && BytesOK;
        for (auto* O : Roots) O->RemoveFromRoot();
        Closed = true;
        if (!FinalOK) UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS source_snapshot_or_bytes_changed"));
        return FinalOK;
    }
    // ALIAS_LIFETIME_END

    bool Capture()
    {
        Master = FindObject<UMaterial>(nullptr, *ObjectPath(WTUMaster()));
        Layer = FindObject<UMaterialFunction>(nullptr, *ObjectPath(WSALayer()));
        MI = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(WSATarget()));
        if (!Master || !Layer || !MI || MI->Parent != Master || MI->GetMaterial() != Master || !Master->bUsedWithStaticLighting) return false;
        Sources.Add(Master); Sources.Add(MI);
        FWeaponRepair Inspect;
        for (int32 I = 0; I < Sources.Num(); ++I)
        {
            if (Sources.Num() > 8192) return false;
            UObject* O = Sources[I];
            auto* Es = Inspect.Expressions(O);
            if (Es) for (auto* E : *Es)
            {
                if (!E || E->GetOuter() != O || Sources.Contains(E)) return false;
                Sources.Add(E);
                if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                {
                    if (!C->MaterialFunction) return false;
                    Sources.AddUnique(C->MaterialFunction);
                }
            }
        }
        if (!Sources.Contains(Layer)) return false;
        for (auto* O : Sources)
        {
            Before.Add(O, WSAObject(O)); Dirty.Add(O->GetOutermost(), O->GetOutermost()->IsDirty());
            if (!MRHashPackage(O->GetOutermost()->GetName(), Hashes)) return false;
        }
        Captured = true;
        return Contracts(MI, Layer);
    }
    bool Unchanged() const
    {
        FWeaponRepair Compare;
        for (auto* O : Sources)
            if (!Compare.Same(MRValue(Before.FindChecked(O)), MRValue(WSAObject(O)))) return false;
        for (const auto& KV : Dirty) if (KV.Key->IsDirty() != KV.Value) return false;
        TSharedPtr<FJsonObject> Now = MakeShareable(new FJsonObject);
        for (const auto& KV : Hashes->Values)
            if (!MRHashPackage(KV.Key, Now) || Str(Now, *KV.Key) != KV.Value->AsString()) return false;
        return true;
    }
    bool Contracts(UMaterialInstanceConstant* Instance, UMaterialFunction* Function) const
    {
        const TCHAR* Canonical[] = {TEXT("e Base Layer Normal"), TEXT("aa Base Layer D")};
        const TCHAR* Nodes[] = {TEXT("MaterialExpressionTextureObjectParameter_3"), TEXT("MaterialExpressionTextureObjectParameter_9")};
        const TCHAR* Textures[] = {
            TEXT("/Game/RestrictedAssets/Environments/AutomotiveMaterials/Textures/CarPaint/T_Bump_N.T_Bump_N"),
            TEXT("/Game/RestrictedAssets/Weapons/Global/Material/MF/Flat_White.Flat_White")};
        FWeaponRepair Inspect;
        for (int32 G = 0; G < 2; ++G)
        {
            UTexture* Value = nullptr;
            if (!Instance->GetTextureParameterValue(FName(Canonical[G]), Value) || !Value || Value->GetPathName() != Textures[G]) return false;
            auto* Base = Inspect.Node(Function, Nodes[G], TEXT("MaterialExpressionTextureObjectParameter"));
            if (!Base) return false;
            auto P = MRProperties(Base, true);
            if (!WSAField(P, TEXT("ParameterName"), Canonical[G]) || !WSAField(P, TEXT("SamplerType"), G == 0 ? TEXT("SAMPLERTYPE_Normal") : TEXT("")) ||
                !WSAField(P, TEXT("Texture"), FString(TEXT("Texture2D'")) + Textures[G] + TEXT("'"))) return false;
            for (int32 I = G * 3; I < G * 3 + 3; ++I)
            {
                const auto& A = WSAliases[I];
                auto* E = Inspect.Node(Function, A.Node, TEXT("MaterialExpressionTextureObjectParameter"));
                UTexture* Other = nullptr;
                if (!E || !Instance->GetTextureParameterValue(FName(A.OldName), Other) || Other != Value) return false;
                auto Q = MRProperties(E, true);
                if (!WSAField(Q, TEXT("ParameterName"), A.OldName) || !WSAField(Q, TEXT("ExpressionGUID"), A.Guid) ||
                    !WSAField(Q, TEXT("Texture"), Str(P, TEXT("Texture"))) || !WSAField(Q, TEXT("SamplerType"), Str(P, TEXT("SamplerType")))) return false;
            }
        }
        auto* WeaponLayer = FindObject<UMaterialFunction>(nullptr, TEXT("/Game/RestrictedAssets/Weapons/Global/Material/MF/MF_WeaponLayer.MF_WeaponLayer"));
        if (!WeaponLayer) return false;
        for (const TCHAR* N : {TEXT("MaterialExpressionTextureSample_2"), TEXT("MaterialExpressionTextureSample_5")})
        {
            auto* E = Inspect.Node(WeaponLayer, N, TEXT("MaterialExpressionTextureSample"));
            if (!E) return false;
            auto P = MRProperties(E, true);
            if (!WSAField(P, TEXT("SamplerSource"), TEXT("SSM_Wrap_WorldGroupSettings")) || !WSAField(P, TEXT("MipValueMode"), TEXT("")) ||
                !WSAField(P, TEXT("MipValue"), TEXT("()")) || !WSAField(P, TEXT("CoordinatesDX"), TEXT("()")) || !WSAField(P, TEXT("CoordinatesDY"), TEXT("()"))) return false;
            const auto Pins = E->GetInputs();
            const bool Normal = FString(N) == TEXT("MaterialExpressionTextureSample_2");
            auto* UV = Inspect.Node(WeaponLayer, TEXT("MaterialExpressionStaticSwitch_0"), TEXT("MaterialExpressionStaticSwitch"));
            auto* Input = Inspect.Node(WeaponLayer, Normal ? TEXT("MaterialExpressionFunctionInput_17") : TEXT("MaterialExpressionFunctionInput_27"), TEXT("MaterialExpressionFunctionInput"));
            if (!UV || !Input || Pins.Num() != 2 || !Pins[0] || !Pins[1] || !Inspect.Pin(*Pins[0], UV) || !Inspect.Pin(*Pins[1], Input) ||
                !WSAField(P, TEXT("SamplerType"), Normal ? TEXT("SAMPLERTYPE_Normal") : TEXT(""))) return false;
        }
        FStaticParameterSet Static; Instance->GetStaticParameterValues(Static);
        const TCHAR* Names[] = {TEXT("Skeletal Mesh True"), TEXT("Simple Layer True"), TEXT("Detail Normal Per-Layer True"),
            TEXT("Single Layer True (No RGB layers)"), TEXT("Debug Checker Mode True"), TEXT("Base Layer Projected UVs"),
            TEXT("R Layer Projected UVs"), TEXT("G Layer Projected UVs"), TEXT("B Layer Projected UVs")};
        for (int32 I = 0; I < ARRAY_COUNT(Names); ++I)
        {
            int32 Count = 0;
            for (const auto& S : Static.StaticSwitchParameters) if (S.ParameterName == FName(Names[I]))
            { if (S.Value != (I == 0)) return false; ++Count; }
            if (Count != 1) return false;
        }
        return true;
    }
    template<typename T> T* Duplicate(T* Source, const TCHAR* Name)
    {
        if (FindObject<UObject>(GetTransientPackage(), Name)) return nullptr;
        T* O = DuplicateObject<T>(Source, GetTransientPackage(), FName(Name));
        if (!O) return nullptr;
        O->AddToRoot(); Roots.Add(O);
        if (O == Source || O->GetClass() != Source->GetClass() || O->GetOuter() != GetTransientPackage()) return nullptr;
        O->SetFlags(RF_Transient);
        return O;
    }
    bool Prepare()
    {
        // Reject every fixed-name collision before the first duplicate.
        for (const TCHAR* N : {TEXT("UT4SamplerAliasMaster"), TEXT("UT4SamplerAliasLayer"), TEXT("UT4SamplerAliasMIC")})
            if (FindObject<UObject>(GetTransientPackage(), N)) return false;
        CloneLayer = Duplicate(Layer, TEXT("UT4SamplerAliasLayer"));
        if (!CloneLayer) return false;
        CloneMaster = Duplicate(Master, TEXT("UT4SamplerAliasMaster"));
        if (!CloneMaster || !MasterLighting.Capture(Master, CloneMaster)) return false;
        CloneMI = Duplicate(MI, TEXT("UT4SamplerAliasMIC"));
        if (!CloneMI || !MILighting.Capture(MI, CloneMI)) return false;
        MasterId = FGuid::NewGuid(); LayerId = FGuid::NewGuid();
        CloneMaster->StateId = MasterId; CloneLayer->StateId = LayerId;
        if (!MasterId.IsValid() || !LayerId.IsValid() || MasterId == Master->StateId || LayerId == Layer->StateId || MasterId == LayerId) return false;
        FWeaponRepair Inspect;
        if (!WSAOwnedGraph(Master, CloneMaster) || !WSAOwnedGraph(Layer, CloneLayer)) return false;
        for (UObject* O : {static_cast<UObject*>(CloneMaster), static_cast<UObject*>(CloneLayer)})
            for (auto* E : *Inspect.Expressions(O))
            {
                if (!E || E->GetOuter() != O || E->GraphNode) return false;
                E->SetFlags(RF_Transient);
                if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                {
                    auto BeforeCall = MRProperties(C, true);
                    C->UpdateFromFunctionResource(false);
                    if (!Inspect.Same(MRValue(BeforeCall), MRValue(MRProperties(C, true)))) return false;
                    if (!WSAInterfaces(C)) return false;
                }
            }
        if (!WSAOwnedGraph(Master, CloneMaster) || !WSAOwnedGraph(Layer, CloneLayer)) return false;
        for (const auto& A : WSAliases)
        {
            auto* E = Inspect.Node(CloneLayer, A.Node, TEXT("MaterialExpressionTextureObjectParameter"));
            if (!E || !WSASetName(E, A)) return false;
        }
        auto* Call = Cast<UMaterialExpressionMaterialFunctionCall>(Inspect.Node(CloneMaster,
            TEXT("MaterialExpressionMaterialFunctionCall_0"), TEXT("MaterialExpressionMaterialFunctionCall")));
        if (!Call || Call->Material != CloneMaster || Call->MaterialFunction != Layer) return false;
        // All owned function interfaces were rebound above before any setter can compile.
        if (!Call->SetMaterialFunction(nullptr, Layer, CloneLayer) || !WSAInterfaces(Call)) return false;
        int32 Replaced = 0;
        for (auto& Info : CloneMaster->MaterialFunctionInfos) if (Info.Function == Layer)
        { if (Info.StateId != Layer->StateId) return false; Info.Function = CloneLayer; Info.StateId = LayerId; ++Replaced; }
        if (Replaced != 1) return false;
        if (!WSAOwnedGraph(Master, CloneMaster, Layer, CloneLayer) || !WSAOwnedGraph(Layer, CloneLayer)) return false;
        // Required for CompilePropertyEx routing AND cached base-property/permutation refresh.
        // May launch additional rendering-platform jobs and persist their DDC maps.
        CloneMI->SetParentEditorOnly(CloneMaster);
        return WSADrain() && Equivalent() && Unchanged();
    }
    bool Equivalent() const
    {
        if (!CloneMaster || !CloneLayer || !CloneMI || CloneMaster->StateId != MasterId || CloneLayer->StateId != LayerId ||
            CloneMI->Parent != CloneMaster || CloneMI->GetMaterial() != CloneMaster) return false;
        if (!WSAOwnedGraph(Master, CloneMaster, Layer, CloneLayer) || !WSAOwnedGraph(Layer, CloneLayer)) return false;
        for (UObject* O : {static_cast<UObject*>(CloneMaster), static_cast<UObject*>(CloneLayer)})
        {
            FWeaponRepair Inspect;
            for (auto* E : *Inspect.Expressions(O)) if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                if (!WSAInterfaces(C)) return false;
        }
        FWeaponRepair Compare;
        Compare.Canonical.Add(CloneMaster->GetPathName(), Master->GetPathName());
        Compare.Canonical.Add(CloneLayer->GetPathName(), Layer->GetPathName());
        Compare.Canonical.Add(CloneMI->GetPathName(), MI->GetPathName());
        const auto& A = Master->MaterialFunctionInfos; const auto& B = CloneMaster->MaterialFunctionInfos;
        if (A.Num() != B.Num()) return false;
        int32 Replaced = 0;
        for (int32 I = 0; I < A.Num(); ++I)
        {
            const bool Target = A[I].Function == Layer;
            if (B[I].Function != (Target ? CloneLayer : A[I].Function) || B[I].StateId != (Target ? LayerId : A[I].StateId)) return false;
            if (Target) ++Replaced;
        }
        if (Replaced != 1) return false;
        UObject* Old[] = {Master, Layer, MI}; UObject* New[] = {CloneMaster, CloneLayer, CloneMI};
        int32 Redirects = 0;
        for (int32 I = 0; I < 3; ++I)
        {
            auto X = WSAObject(Old[I]); auto Y = WSAObject(New[I]);
            auto XP = X->GetObjectField(TEXT("properties")); auto YP = Y->GetObjectField(TEXT("properties"));
            if (I == 0 && !MasterLighting.Normalize(XP, YP)) return false;
            if (I == 2 && !MILighting.Normalize(XP, YP)) return false;
            if (I < 2) YP->SetStringField(TEXT("StateId"), Str(XP, TEXT("StateId")));
            if (I == 0) YP->SetStringField(TEXT("MaterialFunctionInfos"), Str(XP, TEXT("MaterialFunctionInfos")));
            if (!Compare.Same(MRValue(X), MRValue(Y))) return false;
            auto* OE = Compare.Expressions(Old[I]); auto* NE = Compare.Expressions(New[I]);
            if (!OE) { if (NE) return false; continue; }
            if (!NE || OE->Num() != NE->Num()) return false;
            for (int32 J = 0; J < OE->Num(); ++J)
            {
                auto* O = (*OE)[J]; auto* N = (*NE)[J];
                if (!O || !N || N->GetOuter() != New[I] || O->GetName() != N->GetName()) return false;
                auto OP = WSAObject(O); auto NP = WSAObject(N);
                if (I == 1) for (const auto& R : WSAliases) if (N->GetName() == R.Node)
                {
                    auto P = NP->GetObjectField(TEXT("properties"));
                    if (Str(P, TEXT("ParameterName")) != R.NewName || Str(P, TEXT("ExpressionGUID")) != R.Guid) return false;
                    P->SetStringField(TEXT("ParameterName"), R.OldName); ++Redirects;
                }
                if (!Compare.Same(MRValue(OP), MRValue(NP))) return false;
            }
        }
        FStaticParameterSet OS, NS; MI->GetStaticParameterValues(OS); CloneMI->GetStaticParameterValues(NS);
        return Redirects == 6 && Compare.Same(MRValue(MRStatic(OS)), MRValue(MRStatic(NS)));
    }
    // ALIAS_ORDINARY_COMPILE_BEGIN
    bool CompileOrdinary()
    {
        if (!Contracts(MI, Layer) || !Equivalent() || !Proof.Check(MasterHash)) return false;
        auto* Control = new FWSAOrdinaryResource;
        Resource = Control; // Same RAII/root retention and global drain as the default.
        Control->SetMaterial(CloneMaster, EMaterialQualityLevel::High, true, ERHIFeatureLevel::ES2, CloneMI);
        FMaterialResource Reference; // Generates an ordinary ID only; never submits jobs.
        Reference.SetMaterial(CloneMaster, EMaterialQualityLevel::High, true, ERHIFeatureLevel::ES2, CloneMI);
        if (Control->IsSpecialEngineMaterial() || Control->IsPersistent() ||
            !Control->IsUsedWithStaticLighting() || !Reference.IsUsedWithStaticLighting()) return false;
        FMaterialShaderMapId Ordinary, Requested;
        Reference.GetShaderMapId(SP_OPENGL_ES2_WEBGL, Ordinary);
        Control->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
        if (!WSAOrdinaryIDEqual(Requested, Ordinary) || Requested.BaseMaterialId != MasterId ||
            Requested.QualityLevel != EMaterialQualityLevel::High || Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
            !Requested.ReferencedFunctions.Contains(LayerId) || Requested.ReferencedFunctions.Contains(Layer->StateId) ||
            Requested.ShaderTypeDependencies.Num() == 0) return false;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_ORDINARY begin selector=grenade1p-high-ordinary-lighting redirects=6 staticLighting=1 persistent=0 ordinaryDependenciesEqual=1 shaderDependencies=%d pipelineDependencies=%d vertexFactoryDependencies=%d incidentalRenderingJobs=possible incidentalDDCSaves=possible"),
            Requested.ShaderTypeDependencies.Num(), Requested.ShaderPipelineTypeDependencies.Num(), Requested.VertexFactoryTypeDependencies.Num());
        Attempted = true;
        const bool Cached = Control->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
        Control->FinishCompilation();
        if (!WSADrain() || !Control->IsCompilationFinished() || !Equivalent() || !Unchanged()) return false;
        auto* Map = Control->GetGameThreadShaderMap();
        const bool Valid = Cached && Control->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() && Map->CompiledSuccessfully() &&
            Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL && WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId()) && Control->GetCompileErrors().Num() == 0;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_ORDINARY result valid=%d samplers=%d translationRequests=%d ordinaryAcceptance=0"),
            Valid ? 1 : 0, Valid ? Control->GetSamplerUsage() : -1, Control->TranslationRequests);
        for (const FString& Error : Control->GetCompileErrors())
            UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_ORDINARY error text=%s"), *WFRContext(Error));
        if (!Valid) return false; // Failed-map uniform arrays and sampler usage are not evidence.
        const int32 Textures = Control->GetUniform2DTextureExpressions().Num(), Cubes = Control->GetUniformCubeTextureExpressions().Num();
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_ORDINARY bindings material2D=%d materialCube=%d pairedBaselineMeasured=0"), Textures, Cubes);
        return Textures == 14 && Cubes == 0 && Control->GetSamplerUsage() >= 0 && Control->GetSamplerUsage() <= 16;
    }
    // ALIAS_ORDINARY_COMPILE_END
    bool Compile()
    {
        if (OrdinaryLighting) return CompileOrdinary(); // ALIAS_ORDINARY_ROUTE
        if (!Contracts(MI, Layer) || !Equivalent() || !Proof.Check(MasterHash)) return false;
        auto* Diagnostic = new FWeaponShaderResource; Resource = Diagnostic;
        Resource->SetMaterial(CloneMaster, EMaterialQualityLevel::High, true, ERHIFeatureLevel::ES2, CloneMI);
        if (Resource->IsSpecialEngineMaterial()) return false;
        FMaterialShaderMapId Ordinary, Requested;
        Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Ordinary);
        Diagnostic->NoStaticLighting = true;
        Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
        FStaticParameterSet Effective; CloneMI->GetStaticParameterValues(Effective);
        FWeaponRepair Compare;
        if (Requested.BaseMaterialId != MasterId || Requested.QualityLevel != EMaterialQualityLevel::High || Requested.FeatureLevel != ERHIFeatureLevel::ES2 ||
            !Requested.ReferencedFunctions.Contains(LayerId) || Requested.ReferencedFunctions.Contains(Layer->StateId) ||
            Requested.ShaderTypeDependencies.Num() >= Ordinary.ShaderTypeDependencies.Num() ||
            Requested.ShaderPipelineTypeDependencies.Num() > Ordinary.ShaderPipelineTypeDependencies.Num() ||
            Requested.VertexFactoryTypeDependencies.Num() > Ordinary.VertexFactoryTypeDependencies.Num() ||
            !Compare.Same(MRValue(MRStatic(Effective)), MRValue(MRStatic(Requested.ParameterSet)))) return false;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS begin selector=grenade1p-high redirects=6 staticLighting=0 persistent=0 incidentalRenderingJobs=possible incidentalDDCSaves=possible"));
        Attempted = true;
        const bool Cached = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
        Resource->FinishCompilation();
        if (!WSADrain() || !Resource->IsCompilationFinished() || !Equivalent() || !Unchanged()) return false;
        auto* Map = Resource->GetGameThreadShaderMap();
        const bool Valid = Cached && Resource->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() && Map->CompiledSuccessfully() &&
            Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL && WSPMaterialInstanceIdentitySubset(Requested, Map->GetShaderMapId()) && Resource->GetCompileErrors().Num() == 0;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS result valid=%d samplers=%d translationRequests=%d ordinaryAcceptance=0"),
            Valid ? 1 : 0, Valid ? Resource->GetSamplerUsage() : -1, Diagnostic->TranslationRequests);
        for (const FString& Error : Resource->GetCompileErrors())
            UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS error text=%s"), *WFRContext(Error));
        if (!Valid) return false; // A failed map has no authoritative uniform array.
        const auto& Textures = Resource->GetUniform2DTextureExpressions();
        const auto& Cubes = Resource->GetUniformCubeTextureExpressions();
        if (Textures.Num() > 64 || Cubes.Num() > 64) return false;
        for (int32 Kind = 0; Kind < 2; ++Kind)
        {
            const auto& Bindings = Kind == 0 ? Textures : Cubes;
            for (int32 I = 0; I < Bindings.Num(); ++I)
            {
                auto* Expression = Bindings[I].GetReference(); UTexture* Texture = nullptr;
                if (!Expression || !Expression->GetType()) return false;
                Expression->GetGameThreadTextureValue(CloneMI, *Resource, Texture);
                if (!Texture) return false;
                UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS binding kind=%s index=%d type=%s textureIndex=%d texture=%s"),
                    Kind == 0 ? TEXT("2D") : TEXT("cube"), I, Expression->GetType()->GetName(), Expression->GetTextureIndex(), *Texture->GetPathName());
            }
        }
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS bindings material2D=%d materialCube=%d priorCapturedBaseline2D=20 expectedCandidate2D=14 pairedBaselineMeasured=0"), Textures.Num(), Cubes.Num());
        return Textures.Num() == 14 && Cubes.Num() == 0 && Resource->GetSamplerUsage() >= 0 && Resource->GetSamplerUsage() <= 16;
    }
};

// ALIAS_PAIR_IMPLEMENTATION_BEGIN
// Fixed two-MIC candidate. The child's stored overrides and parent relationship
// remain intact; only owned objects participate in compilation.
struct FWSAliasPairState : FWSAliasState
{
    UMaterialInstanceConstant* Child = nullptr;
    UMaterialInstanceConstant* CloneChild = nullptr;
    FWSALightingPolicy ChildLighting;
    TArray<FMaterialShaderMapId> RequestedIds;
    int32 Completed = 0, ValidResources = 0;
    explicit FWSAliasPairState(FWeaponTessProof& P, const FString& H) : FWSAliasState(P, H) {}
    static FString ChildTarget()
    { return TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_Launcher_3P"); }
    bool CapturePair()
    {
        if (!Capture()) return false;
        Child = FindObject<UMaterialInstanceConstant>(nullptr, *ObjectPath(ChildTarget()));
        if (!Child || Child == MI || Child->GetClass() != MI->GetClass() || Child->Parent != MI ||
            Child->GetMaterial() != Master || Sources.Contains(Child) ||
            Child->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad | RF_NeedPostLoadSubobjects)) return false;
        Sources.Add(Child); Before.Add(Child, WSAObject(Child));
        Dirty.Add(Child->GetOutermost(), Child->GetOutermost()->IsDirty());
        return MRHashPackage(Child->GetOutermost()->GetName(), Hashes) && Contracts(Child, Layer) && Unchanged();
    }
    bool PreparePair()
    {
        if (FindObject<UObject>(GetTransientPackage(), TEXT("UT4SamplerAliasChildMIC")) || !Prepare()) return false;
        CloneChild = Duplicate(Child, TEXT("UT4SamplerAliasChildMIC"));
        if (!CloneChild || !ChildLighting.Capture(Child, CloneChild) || CloneChild->Parent != MI ||
            !Equivalent() || !WSAOwnedGraph(Master, CloneMaster, Layer, CloneLayer) || !WSAOwnedGraph(Layer, CloneLayer)) return false;
        CloneChild->SetParentEditorOnly(CloneMI);
        return WSADrain() && PairEquivalent() && Unchanged();
    }
    bool PairEquivalent() const
    {
        if (!Equivalent() || !Child || !CloneChild || Child->Parent != MI || CloneChild->Parent != CloneMI ||
            CloneChild == Child || CloneChild->GetOuter() != GetTransientPackage() || !CloneChild->HasAnyFlags(RF_Transient) ||
            CloneChild->GetMaterial() != CloneMaster || CloneChild->GetClass() != Child->GetClass()) return false;
        FWeaponRepair Compare;
        Compare.Canonical.Add(CloneMaster->GetPathName(), Master->GetPathName());
        Compare.Canonical.Add(CloneMI->GetPathName(), MI->GetPathName());
        Compare.Canonical.Add(CloneChild->GetPathName(), Child->GetPathName());
        auto A = WSAObject(Child); auto B = WSAObject(CloneChild);
        if (!ChildLighting.Normalize(A->GetObjectField(TEXT("properties")), B->GetObjectField(TEXT("properties"))) ||
            !Compare.Same(MRValue(A), MRValue(B))) return false;
        FStaticParameterSet Old, New; Child->GetStaticParameterValues(Old); CloneChild->GetStaticParameterValues(New);
        return Compare.Same(MRValue(MRStatic(Old)), MRValue(MRStatic(New)));
    }
    // ALIAS_PAIR_COMPILE_ONE_BEGIN
    bool CompileOne(int32 Member, EMaterialQualityLevel::Type Quality)
    {
        if (Member < 0 || Member > 1 || int32(Quality) < 0 || int32(Quality) >= EMaterialQualityLevel::Num ||
            Resource || OrdinaryLighting || !Contracts(MI, Layer) || !Contracts(Child, Layer) ||
            !PairEquivalent() || !Unchanged() || !Proof.Check(MasterHash)) return false;
        auto* Instance = Member == 0 ? CloneMI : CloneChild;
        const FString Target = Member == 0 ? WSATarget() : ChildTarget();
        auto* Diagnostic = new FWeaponShaderResource; Resource = Diagnostic;
        Resource->SetMaterial(CloneMaster, Quality, true, ERHIFeatureLevel::ES2, Instance);
        if (Resource->IsSpecialEngineMaterial()) return false;
        FMaterialShaderMapId Ordinary, Requested;
        Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Ordinary);
        Diagnostic->NoStaticLighting = true;
        if (Resource->IsPersistent()) return false;
        Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested);
        FStaticParameterSet Effective; Instance->GetStaticParameterValues(Effective); FWeaponRepair Compare;
        if (Resource->IsUsedWithStaticLighting() || Requested.BaseMaterialId != MasterId || Requested.QualityLevel != Quality ||
            Requested.FeatureLevel != ERHIFeatureLevel::ES2 || !Requested.ReferencedFunctions.Contains(LayerId) ||
            Requested.ReferencedFunctions.Contains(Layer->StateId) || Requested.ShaderTypeDependencies.Num() == 0 ||
            Requested.ShaderTypeDependencies.Num() >= Ordinary.ShaderTypeDependencies.Num() ||
            Requested.ShaderPipelineTypeDependencies.Num() > Ordinary.ShaderPipelineTypeDependencies.Num() ||
            Requested.VertexFactoryTypeDependencies.Num() > Ordinary.VertexFactoryTypeDependencies.Num() ||
            !Compare.Same(MRValue(MRStatic(Effective)), MRValue(MRStatic(Requested.ParameterSet)) )) return false;
        for (const auto& Previous : RequestedIds) if (WSAOrdinaryIDEqual(Previous, Requested)) return false;
        RequestedIds.Add(Requested);
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_PAIR begin material=%s quality=%d redirects=6 staticLighting=0 persistent=0 masterId=%s layerId=%s incidentalDDCSaves=possible"),
            *Target, int32(Quality), *MasterId.ToString(), *LayerId.ToString());
        Attempted = true;
        const bool Cached = Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false);
        Resource->FinishCompilation();
        if (!WSADrain() || !Resource->IsCompilationFinished() || !PairEquivalent() || !Unchanged() || !Proof.Check(MasterHash)) return false;
        auto* Map = Resource->GetGameThreadShaderMap();
        const bool ValidMap = Cached && Resource->HasValidGameThreadShaderMap() && Map && Map->IsCompilationFinalized() &&
            Map->CompiledSuccessfully() && Map->GetShaderPlatform() == SP_OPENGL_ES2_WEBGL &&
            WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId()) && Resource->GetCompileErrors().Num() == 0;
        if (Resource->GetCompileErrors().Num() > 64) return false;
        for (const FString& Error : Resource->GetCompileErrors())
            UE_LOG(LogUT4Html5Compat, Warning, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_PAIR error material=%s quality=%d text=%s"), *Target, int32(Quality), *WFRContext(Error));
        const int32 Samplers = ValidMap ? Resource->GetSamplerUsage() : -1;
        const int32 Textures = ValidMap ? Resource->GetUniform2DTextureExpressions().Num() : -1;
        const int32 Cubes = ValidMap ? Resource->GetUniformCubeTextureExpressions().Num() : -1;
        const bool Valid = ValidMap && Samplers >= 0 && Samplers <= 16 && Textures == 14 && Cubes == 0;
        if (Valid)
        {
            const auto& Bindings = Resource->GetUniform2DTextureExpressions();
            for (int32 I = 0; I < Bindings.Num(); ++I)
            {
                auto* E = Bindings[I].GetReference(); UTexture* Texture = nullptr;
                if (!E || !E->GetType()) return false;
                E->GetGameThreadTextureValue(Instance, *Resource, Texture);
                if (!Texture) return false;
                UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_PAIR binding material=%s quality=%d index=%d type=%s textureIndex=%d texture=%s"),
                    *Target, int32(Quality), I, E->GetType()->GetName(), E->GetTextureIndex(), *Texture->GetPathName());
            }
        }
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_PAIR result material=%s quality=%d valid=%d samplers=%d material2D=%d materialCube=%d translationRequests=%d fullRequestedIdEqual=%d ordinaryAcceptance=0"),
            *Target, int32(Quality), Valid ? 1 : 0, Samplers, Textures, Cubes, Diagnostic->TranslationRequests, ValidMap ? 1 : 0);
        ++Completed; if (Valid) ++ValidResources;
        // Both global and resource compilation finished above; roots stay owned
        // until Close rechecks all original objects/packages and releases them.
        delete Resource; Resource = nullptr;
        return true; // Continue all six rows even when a shader map is invalid.
    }
    // ALIAS_PAIR_COMPILE_ONE_END
    // ALIAS_PAIR_LOOP_BEGIN
    bool CompilePair()
    {
        if (Completed || ValidResources || RequestedIds.Num()) return false;
        const EMaterialQualityLevel::Type Qualities[] = {EMaterialQualityLevel::Low, EMaterialQualityLevel::Medium, EMaterialQualityLevel::High};
        for (int32 Member = 0; Member < 2; ++Member)
            for (auto Quality : Qualities) if (!CompileOne(Member, Quality)) return false;
        return Completed == 6 && RequestedIds.Num() == 6 && PairEquivalent() && Unchanged();
    }
    // ALIAS_PAIR_LOOP_END
};
static int32 WSACompilePair(FWeaponTessProof& Proof, const FString& Hash)
{
    FWSAliasPairState State(Proof, Hash);
    if (!State.CapturePair()) return WFRStop(TEXT("sampler-alias-pair-source"));
    if (!State.PreparePair()) return WFRStop(TEXT("sampler-alias-pair-clones"));
    const bool Finished = State.CompilePair();
    if (!State.Close()) return WFRStop(TEXT("sampler-alias-pair-final"));
    if (!Finished || !State.Attempted || State.Completed != 6) return WFRStop(TEXT("sampler-alias-pair-incomplete"));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_PAIR complete selector=grenade-pair-all-qualities resources=6 valid=%d redirects=6 assetsSaved=0 staticLighting=0 persistent=0 ordinaryAcceptance=0 runtimeImmutabilityProven=0 incidentalDDCSaves=possible"), State.ValidResources);
    return State.ValidResources == 6 ? 0 : 1;
}
// ALIAS_PAIR_IMPLEMENTATION_END
// ALIAS_CONTROL_BEGIN
static int32 WeaponSamplerAliasProbe(const FString& Params)
{
    FString Mode;
    if (!GIsEditor || !IsRunningCommandlet() || !IsInGameThread() || !FApp::CanEverRender() ||
        !FParse::Value(*Params, TEXT("Mode="), Mode) || !Mode.Equals(TEXT("WeaponSamplerAliasProbe"), ESearchCase::IgnoreCase) ||
        !GShaderCompilingManager || WeaponTessellationUpgrade(Params, true) != 0) return WFRStop(TEXT("sampler-alias-admission"));
    FString Path;
    if (!FParse::Value(*Params, TEXT("WeaponCurrentProof="), Path)) return WFRStop(TEXT("sampler-alias-proof"));
    FWeaponTessProof Proof;
    if (!Proof.Read(Path) || !WSPQualityBranches()) return WFRStop(TEXT("sampler-alias-generation"));
    const FString* MasterFile = Proof.CurrentFiles.Find(WTUMaster());
    if (!MasterFile) return WFRStop(TEXT("sampler-alias-master-proof"));
    const FString Hash = HashFile(*MasterFile);
    if (!Proof.Check(Hash) || !WSADrain()) return WFRStop(TEXT("sampler-alias-before"));
    // ALIAS_PAIR_DISPATCH_BEGIN
    if (FParse::Param(*Params, TEXT("SamplerAliasGrenadePair")))
    {
        if (FParse::Param(*Params, TEXT("SamplerAliasOrdinaryLighting"))) return WFRStop(TEXT("sampler-alias-conflicting-selectors"));
        return WSACompilePair(Proof, Hash);
    }
    // ALIAS_PAIR_DISPATCH_END
    FWSAliasState State(Proof, Hash);
    State.OrdinaryLighting = FParse::Param(*Params, TEXT("SamplerAliasOrdinaryLighting")); // ALIAS_ORDINARY_FLAG
    if (!State.Capture()) return WFRStop(TEXT("sampler-alias-source-contract"));
    if (!State.Prepare()) return WFRStop(TEXT("sampler-alias-clone-contract"));
    const bool Valid = State.Compile();
    if (!State.Close()) return WFRStop(TEXT("sampler-alias-final-snapshot-or-drain"));
    if (!State.Attempted) return WFRStop(TEXT("sampler-alias-not-compiled"));
    // ALIAS_ORDINARY_COMPLETION_BEGIN
    if (State.OrdinaryLighting)
    {
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS_ORDINARY complete selector=grenade1p-high-ordinary-lighting resources=1 valid=%d redirects=6 assetsSaved=0 staticLighting=1 persistent=0 incidentalDDCSaves=possible ordinaryAcceptance=0 runtimeImmutabilityProven=0"), Valid ? 1 : 0);
        return Valid ? 0 : 1;
    }
    // ALIAS_ORDINARY_COMPLETION_END
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_SAMPLER_ALIAS complete selector=grenade1p-high resources=1 valid=%d redirects=6 assetsSaved=0 staticLighting=0 persistent=0 incidentalDDCSaves=possible ordinaryAcceptance=0 runtimeImmutabilityProven=0"), Valid ? 1 : 0);
    return Valid ? 0 : 1;
}
// ALIAS_CONTROL_END
