// Original observation-only helper. Include inside UT4Compat after MaterialPreflightReport.h.
// Caller includes Engine/Blueprint.h and EdGraph/{EdGraph,EdGraphNode,EdGraphPin}.h outside the namespace.
// PostLoad may normalize graphs/regenerate classes. No bytecode or dependency-closure proof.
static TArray<FString> WBPScope()
{
    TArray<FString> P;
    P.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/BP_GrenadeLauncher"));
    P.Add(TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/BP_GrenadeLauncher_Attach"));
    return P;
}
static FString WBPPath(const UObject* O) { return O ? O->GetPathName() : FString(); }
static TSharedPtr<FJsonObject> WBPObject() { return MakeShareable(new FJsonObject); }
struct FWBPOutput
{
    int32 Sequence = 0, Characters = 0, Nodes = 0, Pins = 0, Links = 0, Graphs = 0;
    bool Emit(TSharedPtr<FJsonObject> J, const TCHAR* Kind)
    {
        J->SetStringField(TEXT("schema"), TEXT("ut4-weapon-blueprint-v1")); J->SetStringField(TEXT("kind"), Kind);
        J->SetNumberField(TEXT("seq"), Sequence); J->SetBoolField(TEXT("read_only"), true);
        J->SetBoolField(TEXT("global_immutability_proven"), false);
        FString Text;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text)) ||
            Text.Len() > 65536 || Characters > 8 * 1024 * 1024 - Text.Len() || Sequence >= 65536) return false;
        Characters += Text.Len(); ++Sequence;
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_BLUEPRINT %s"), *Text); return true;
    }
};
struct FWBPFile
{
    FString Package, Original, Selected, Hash;
    bool Check() const
    {
        FString Current;
        return Physical(Original, false) && FPackageName::DoesPackageExist(Package, nullptr, &Current) && Full(Current) == Selected &&
            IFileManager::Get().FileSize(*Original) > 0 && IFileManager::Get().FileSize(*Original) <= 64 * 1024 * 1024 &&
            IFileManager::Get().FileSize(*Selected) > 0 && IFileManager::Get().FileSize(*Selected) <= 64 * 1024 * 1024 &&
            Hash.Len() == 40 && HashFile(Original) == Hash && HashFile(Selected) == Hash;
    }
};
// Public pin fields only: no unexported K2 entry points or generated struct exporters.
static TSharedPtr<FJsonObject> WBPPinType(const FEdGraphPinType& T)
{
    auto J = WBPObject(); J->SetStringField(TEXT("category"), T.PinCategory); J->SetStringField(TEXT("subcategory"), T.PinSubCategory);
    J->SetStringField(TEXT("object"), WBPPath(T.PinSubCategoryObject.Get()));
    J->SetStringField(TEXT("member_parent"), WBPPath(T.PinSubCategoryMemberReference.MemberParent));
    J->SetStringField(TEXT("member_name"), T.PinSubCategoryMemberReference.MemberName.ToString());
    J->SetStringField(TEXT("member_guid"), T.PinSubCategoryMemberReference.MemberGuid.ToString());
    J->SetBoolField(TEXT("array"), T.bIsArray); J->SetBoolField(TEXT("set"), T.bIsSet); J->SetBoolField(TEXT("map"), T.bIsMap);
    J->SetBoolField(TEXT("reference"), T.bIsReference); J->SetBoolField(TEXT("const"), T.bIsConst); J->SetBoolField(TEXT("weak"), T.bIsWeakPointer);
    auto V = WBPObject(); V->SetStringField(TEXT("category"), T.PinValueType.TerminalCategory);
    V->SetStringField(TEXT("subcategory"), T.PinValueType.TerminalSubCategory); V->SetStringField(TEXT("object"), WBPPath(T.PinValueType.TerminalSubCategoryObject.Get()));
    V->SetBoolField(TEXT("const"), T.PinValueType.bTerminalIsConst); V->SetBoolField(TEXT("weak"), T.PinValueType.bTerminalIsWeakPointer);
    J->SetObjectField(TEXT("map_value"), V); return J;
}
static FString WBPPinId(const UEdGraphPin* P)
{
    return P && P->GetOwningNodeUnchecked() && P->PinId.IsValid() ? WBPPath(P->GetOwningNodeUnchecked()) + TEXT(":") + P->PinId.ToString() : FString();
}
static bool WBPProperties(UObject* O, TSharedPtr<FJsonObject>& Out)
{
    int32 Count = 0;
    for (TFieldIterator<UProperty> It(O->GetClass()); It; ++It)
        if (++Count > 512 || (*It)->ArrayDim > 512) return false;
    Out = MRProperties(O, true); // Includes FunctionReference, VariableReference and MacroGraphReference where present.
    for (const TCHAR* Name : {TEXT("FunctionReference"), TEXT("VariableReference"), TEXT("MacroGraphReference")})
        if (FindField<UProperty>(O->GetClass(), Name) && !Out->HasField(Name)) return false;
    return true; // Native ExportText observations, not bytecode or resolved external-member evidence.
}
static bool WBPGraphs(UBlueprint* B, FWBPOutput& Out)
{
    if (B->ImplementedInterfaces.Num()) return false; // Interface graphs are outside this fixed first-pass capture.
    TArray<UEdGraph*> Queue; TSet<UEdGraph*> Seen; TSet<UEdGraphNode*> SeenNodes;
    TSet<FString> CapturedPins, RequiredPins;
    auto Add = [&](const TArray<UEdGraph*>& Graphs, const FString& Owner, const TCHAR* Family) -> bool
    {
        if (Graphs.Num() > 512) return false;
        for (UEdGraph* G : Graphs)
        {
            if (!G || !G->IsIn(B)) return false;
            auto J = WBPObject(); J->SetStringField(TEXT("owner"), Owner); J->SetStringField(TEXT("family"), Family); J->SetStringField(TEXT("graph"), WBPPath(G));
            if (!Out.Emit(J, TEXT("graph_reference"))) return false;
            if (!Seen.Contains(G)) { if (Seen.Num() >= 512) return false; Seen.Add(G); Queue.Add(G); }
        }
        return true;
    };
    if (!Add(B->UbergraphPages, WBPPath(B), TEXT("ubergraph")) || !Add(B->FunctionGraphs, WBPPath(B), TEXT("function")) ||
        !Add(B->MacroGraphs, WBPPath(B), TEXT("macro")) || !Add(B->DelegateSignatureGraphs, WBPPath(B), TEXT("delegate"))) return false;
    for (int32 I = 0; I < Queue.Num(); ++I)
    {
        UEdGraph* G = Queue[I]; if (++Out.Graphs > 1024 || G->Nodes.Num() > 4096 - Out.Nodes) return false;
        auto J = WBPObject(); J->SetStringField(TEXT("graph"), WBPPath(G)); J->SetStringField(TEXT("guid"), G->GraphGuid.ToString());
        J->SetStringField(TEXT("class"), WBPPath(G->GetClass())); J->SetNumberField(TEXT("nodes"), G->Nodes.Num());
        if (!Out.Emit(J, TEXT("graph")) || !Add(G->SubGraphs, WBPPath(G), TEXT("subgraph"))) return false;
        for (UEdGraphNode* N : G->Nodes)
        {
            if (!N || N->GetGraph() != G || SeenNodes.Contains(N) || N->DeprecatedPins.Num() || N->Pins.Num() > 32768 - Out.Pins) return false;
            SeenNodes.Add(N); ++Out.Nodes; auto Row = WBPObject(); TSharedPtr<FJsonObject> Properties;
            if (!WBPProperties(N, Properties)) return false;
            Row->SetStringField(TEXT("node"), WBPPath(N)); Row->SetStringField(TEXT("graph"), WBPPath(G));
            Row->SetStringField(TEXT("class"), WBPPath(N->GetClass())); Row->SetStringField(TEXT("guid"), N->NodeGuid.ToString());
            Row->SetObjectField(TEXT("properties"), Properties);
            if (!Out.Emit(Row, TEXT("node"))) return false;
            TArray<UEdGraphPin*> Pins = N->Pins; TSet<UEdGraphPin*> Visited; TSet<FString> Ids;
            for (int32 K = 0; K < Pins.Num(); ++K)
            {
                UEdGraphPin* P = Pins[K];
                if (!P || P->GetOwningNodeUnchecked() != N || P->bWasTrashed || WBPPinId(P).IsEmpty()) return false;
                if (Visited.Contains(P)) continue;
                if (++Out.Pins > 32768 || Ids.Contains(WBPPinId(P)) || P->SubPins.Num() > 32768 - Pins.Num() ||
                    P->LinkedTo.Num() > 131072 - Out.Links || (P->Direction != EGPD_Input && P->Direction != EGPD_Output)) return false;
                Visited.Add(P); Ids.Add(WBPPinId(P)); Pins.Append(P->SubPins); Out.Links += P->LinkedTo.Num();
                CapturedPins.Add(WBPPinId(P));
                auto Pin = WBPObject(); Pin->SetStringField(TEXT("id"), WBPPinId(P)); Pin->SetStringField(TEXT("node"), WBPPath(N));
                Pin->SetStringField(TEXT("name"), P->PinName); Pin->SetNumberField(TEXT("direction"), static_cast<int32>(P->Direction));
                Pin->SetObjectField(TEXT("type"), WBPPinType(P->PinType)); Pin->SetStringField(TEXT("default"), P->DefaultValue);
                Pin->SetStringField(TEXT("autogenerated_default"), P->AutogeneratedDefaultValue); Pin->SetStringField(TEXT("default_object"), WBPPath(P->DefaultObject));
                Pin->SetStringField(TEXT("default_text_display"), P->DefaultTextValue.ToString());
                Pin->SetBoolField(TEXT("hidden"), P->bHidden); Pin->SetBoolField(TEXT("default_ignored"), P->bDefaultValueIsIgnored);
                Pin->SetBoolField(TEXT("default_read_only"), P->bDefaultValueIsReadOnly); Pin->SetBoolField(TEXT("not_connectable"), P->bNotConnectable);
                TArray<TSharedPtr<FJsonValue>> Links, Subs;
                for (UEdGraphPin* L : P->LinkedTo)
                {
                    if (WBPPinId(L).IsEmpty() || L->bWasTrashed || !L->LinkedTo.Contains(P)) return false;
                    if (L->GetOwningNodeUnchecked()->IsIn(B)) RequiredPins.Add(WBPPinId(L));
                    Links.Add(MakeShareable(new FJsonValueString(WBPPinId(L))));
                }
                for (UEdGraphPin* S : P->SubPins)
                { if (WBPPinId(S).IsEmpty() || S->ParentPin != P) return false; Subs.Add(MakeShareable(new FJsonValueString(WBPPinId(S)))); }
                if ((P->ParentPin && (WBPPinId(P->ParentPin).IsEmpty() || !P->ParentPin->SubPins.Contains(P))) ||
                    (P->ReferencePassThroughConnection && WBPPinId(P->ReferencePassThroughConnection).IsEmpty())) return false;
                Pin->SetStringField(TEXT("parent_pin"), WBPPinId(P->ParentPin)); Pin->SetStringField(TEXT("reference_passthrough"), WBPPinId(P->ReferencePassThroughConnection));
                Pin->SetArrayField(TEXT("links"), Links); Pin->SetArrayField(TEXT("subpins"), Subs);
                if (!Out.Emit(Pin, TEXT("pin"))) return false;
            }
        }
    }
    for (const FString& Id : RequiredPins) if (!CapturedPins.Contains(Id)) return false;
    return true;
}
static int32 WeaponBlueprintReport(const FString& Params)
{
    FString OriginalContent, Forbidden;
    if (!GIsEditor || !IsInGameThread() || !FParse::Value(*Params, TEXT("BlueprintOriginalContent="), OriginalContent) || OriginalContent.IsEmpty() ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden)) return 1;
    if (OriginalContent.Len() < 4 || OriginalContent[1] != ':' || (OriginalContent[2] != '/' && OriginalContent[2] != '\\')) return 1;
    OriginalContent = Full(OriginalContent);
    if (!Physical(OriginalContent, false) || !IFileManager::Get().DirectoryExists(*OriginalContent)) return 1;
    const auto Paths = WBPScope(); TArray<FWBPFile> Files;
    const TCHAR* Parents[] = {TEXT("/Script/UnrealTournament.UTWeap_GrenadeLauncher"), TEXT("/Script/UnrealTournament.UTWeapAttachment_RocketLauncher")};
    for (const FString& P : Paths)
    {
        FWBPFile F; F.Package = P; F.Original = Full(OriginalContent / P.Mid(6) + TEXT(".uasset"));
        if (FindPackage(nullptr, *P) || !Within(F.Original, OriginalContent) || !Physical(F.Original, false) ||
            !FPackageName::DoesPackageExist(P, nullptr, &F.Selected)) return 1;
        F.Selected = Full(F.Selected);
        if (IFileManager::Get().FileSize(*F.Original) <= 0 || IFileManager::Get().FileSize(*F.Original) > 64 * 1024 * 1024) return 1;
        F.Hash = HashFile(F.Original); if (!F.Check()) return 1; Files.Add(F);
    }
    FWBPOutput Out; TArray<UBlueprint*> Loaded; TArray<bool> Dirty;
    for (int32 I = 0; I < Files.Num(); ++I)
    {
        for (const FWBPFile& F : Files) if (!F.Check()) return 1;
        const FWBPFile& F = Files[I]; const bool AutoLoaded = FindPackage(nullptr, *F.Package) != nullptr;
        // Pinned CL3228288 has LOAD_NoRedirects, but no LOAD_DisableCompileOnLoad.
        auto* B = LoadObject<UBlueprint>(nullptr, *ObjectPath(F.Package), nullptr, LOAD_NoRedirects);
        if (!B || B->GetClass() != UBlueprint::StaticClass() || WBPPath(B) != ObjectPath(F.Package) ||
            B->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad) || !B->ParentClass || WBPPath(B->ParentClass) != Parents[I] ||
            !B->ParentClass->HasAnyClassFlags(CLASS_Native) || !B->GeneratedClass || B->GeneratedClass->GetSuperClass() != B->ParentClass ||
            WBPPath(B->GeneratedClass) != ObjectPath(F.Package) + TEXT("_C") || B->GeneratedClass->ClassGeneratedBy != B ||
            WBPPath(B->GeneratedClass->GetClass()) != TEXT("/Script/Engine.BlueprintGeneratedClass")) return 1;
        Loaded.Add(B); Dirty.Add(B->GetOutermost()->IsDirty()); auto J = WBPObject();
        J->SetStringField(TEXT("blueprint"), WBPPath(B)); J->SetStringField(TEXT("parent_class"), Parents[I]); J->SetStringField(TEXT("generated_class"), WBPPath(B->GeneratedClass));
        J->SetNumberField(TEXT("parent_class_flags"), static_cast<uint32>(B->ParentClass->ClassFlags));
        J->SetStringField(TEXT("original_file"), F.Original); J->SetStringField(TEXT("selected_file"), F.Selected); J->SetStringField(TEXT("sha1_before"), F.Hash);
        J->SetBoolField(TEXT("dependency_loaded_before_request"), AutoLoaded); J->SetBoolField(TEXT("dirty_after_load"), Dirty.Last());
        J->SetBoolField(TEXT("compile_on_load_disabled"), false);
        J->SetStringField(TEXT("limitations"), TEXT("PostLoad-normalized own graphs; nontransient reflected text, not bytecode; text defaults are display strings; external references unresolved, dependency bytes unpinned; selected logical paths may traverse junctions and are byte-checked only."));
        if (!Out.Emit(J, TEXT("blueprint")) || !WBPGraphs(B, Out)) return 1;
        int32 Functions = 0;
        for (TFieldIterator<UFunction> It(B->GeneratedClass); It; ++It)
        {
            UFunction* Fn = *It; if (++Functions > 2048) return 1;
            auto R = WBPObject(); R->SetStringField(TEXT("blueprint"), WBPPath(B)); R->SetStringField(TEXT("function"), WBPPath(Fn));
            R->SetStringField(TEXT("owner"), WBPPath(Fn->GetOuter())); R->SetNumberField(TEXT("flags"), static_cast<uint32>(Fn->FunctionFlags));
            R->SetNumberField(TEXT("parameters"), Fn->NumParms); R->SetBoolField(TEXT("native"), Fn->HasAnyFunctionFlags(FUNC_Native));
            if (!Out.Emit(R, TEXT("function"))) return 1;
        }
    }
    for (int32 I = 0; I < Files.Num(); ++I)
    {
        if (!Files[I].Check()) return 1; auto J = WBPObject(); const bool Now = Loaded[I]->GetOutermost()->IsDirty();
        J->SetStringField(TEXT("blueprint"), WBPPath(Loaded[I])); J->SetStringField(TEXT("sha1_after"), HashFile(Files[I].Selected));
        J->SetBoolField(TEXT("dirty_after_load"), Dirty[I]); J->SetBoolField(TEXT("dirty_after_report"), Now);
        J->SetStringField(TEXT("dirty_observation"), Dirty[I] ? TEXT("dirty_at_first_postload_observation") : (Now ? TEXT("became_dirty_during_report_or_later_dependency_load") : TEXT("clean_at_both_observations")));
        if (!Out.Emit(J, TEXT("after"))) return 1;
    }
    auto Done = WBPObject(); Done->SetNumberField(TEXT("roots"), Loaded.Num()); Done->SetNumberField(TEXT("blueprints"), Loaded.Num()); Done->SetNumberField(TEXT("graphs"), Out.Graphs);
    Done->SetNumberField(TEXT("nodes"), Out.Nodes); Done->SetNumberField(TEXT("pins"), Out.Pins); Done->SetNumberField(TEXT("links"), Out.Links);
    Done->SetBoolField(TEXT("selected_original_bytes_unchanged"), true); Done->SetBoolField(TEXT("assets_saved"), false);
    return Out.Emit(Done, TEXT("complete")) ? 0 : 1;
}
