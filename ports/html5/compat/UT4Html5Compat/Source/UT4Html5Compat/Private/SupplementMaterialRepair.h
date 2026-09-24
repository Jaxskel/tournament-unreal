// Fixed Bio-body / grenade-ammunition repair. Include after SupplementConsumerReport.h,
// EnforcerMeshInvariant.h and EnforcerMaterialRepair.h. No Blueprint or original-MIC saves.
static TArray<FString> SMRSaves()
{
    const FString D=TEXT("/Game/HTML5Compat/Weapons/V1/Supplement/");
    TArray<FString> P;
    P.Add(D+TEXT("M_WeaponsBase_Supplement"));
    P.Add(D+TEXT("MIC_Bio_3P")); P.Add(D+TEXT("MIC_Bio_1P"));
    P.Add(D+TEXT("MIC_GrenadeAmmo_1P")); P.Add(D+TEXT("MIC_GrenadeAmmo_3P"));
    P.Add(SCSupplementRoots[2]); P.Add(SCSupplementRoots[3]);
    P.Add(SCSupplementRoots[12]); P.Add(SCSupplementRoots[14]); return P;
}
static int32 SMRSlot(int32 Mesh) { return Mesh<2?0:4; }
static int32 SMRMember(int32 Mesh) { return Mesh==0?1:Mesh==1?0:Mesh; }
static int32 SMRStop(const TCHAR* Gate)
{ UE_LOG(LogUT4Html5Compat,Error,TEXT("COMPAT_SUPPLEMENT_REPAIR failure gate=%s"),Gate); return 1; }

struct FSupplementRepairProof
{
    FSavePolicy Policy; FSupplementCandidatePins Candidate;
    FString Preparation,PreparationHash,Receipt,ReceiptHash,InputsPath,OriginalProject,BeforePath,AfterPath,AfterHash;
    TSharedPtr<FJsonObject> Prep,Inputs,After,Files,Ids,Before;
    TArray<FString> Saves=SMRSaves(); TMap<FString,FString> OriginalHashes;
    static const TCHAR* InputsHash() { return TEXT("432b157e8c42414aca84276370b0d722e4a9e2dc"); }
    bool External(const FString& P,bool Missing) const
    {
        const FString F=Full(P);
        return !P.IsEmpty()&&!OriginalProject.IsEmpty()&&!Within(F,Full(FPaths::GetPath(OriginalProject)))&&
            !Within(F,Full(FPaths::GetPath(Full(FPaths::EngineDir()))))&&!Within(F,Full(FPaths::GameDir()))&&
            !F.ToLower().Contains(TEXT("/content/"))&&!F.ToLower().EndsWith(TEXT("/content"))&&Physical(F,Missing);
    }
    bool Json(const FString& P,TSharedPtr<FJsonObject>& J) const
    { const int64 N=IFileManager::Get().FileSize(*P);return N>0&&N<=32*1024*1024&&Physical(P,false)&&ReadJson(P,J); }
    bool Evidence() const
    {
        if(!External(Preparation,false)||!HashFile(Preparation).Equals(PreparationHash,ESearchCase::IgnoreCase)||
            !External(Receipt,false)||!HashFile(Receipt).Equals(ReceiptHash,ESearchCase::IgnoreCase)||
            !External(InputsPath,false)||!HashFile(InputsPath).Equals(InputsHash(),ESearchCase::IgnoreCase)||!Candidate.Check())return false;
        const TArray<TSharedPtr<FJsonValue>>* B=nullptr;
        if(!Prep->TryGetArrayField(TEXT("backups"),B)||B->Num()!=4)return false;
        TSet<FString> Seen;
        for(const auto& V:*B)
        {
            if(V->Type!=EJson::Object)return false;auto J=V->AsObject();const FString P=Str(J,TEXT("package")),F=Str(J,TEXT("file"));
            const int32 I=Saves.Find(P);const FString* H=OriginalHashes.Find(P);
            if(I<5||I>=9||!H||Seen.Contains(P)||!External(F,false)||!Str(J,TEXT("sha1")).Equals(*H,ESearchCase::IgnoreCase)||
                !HashFile(F).Equals(*H,ESearchCase::IgnoreCase))return false;
            Seen.Add(P);
        }
        if(After.IsValid()&&(!External(AfterPath,false)||!HashFile(AfterPath).Equals(AfterHash,ESearchCase::IgnoreCase)||
            !External(BeforePath,false)||!HashFile(BeforePath).Equals(Str(After,TEXT("before_sha1")),ESearchCase::IgnoreCase)))return false;
        return true;
    }
    bool CheckFiles() const
    {
        if(!Evidence()||!Files.IsValid()||Files->Values.Num()!=9)return false;
        const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
        if(!Inputs->TryGetArrayField(TEXT("packages"),Rows)||Rows->Num()!=17)return false;
        for(const auto& V:*Rows)
        {
            if(V->Type!=EJson::Object)return false;auto R=V->AsObject();const FString P=Str(R,TEXT("package"));
            const FString F=Full(Str(R,TEXT("file"))),O=Full(Str(R,TEXT("original_file"))),H=Str(R,TEXT("sha1"));
            FString Resolved;
            const int32 I=Saves.Find(P);const FString Expected=I>=5?Str(Files,*P):H;
            if(!FPackageName::DoesPackageExist(P,nullptr,&Resolved)||Full(Resolved)!=F||!HashFile(F).Equals(Expected,ESearchCase::IgnoreCase)||
                !HashFile(O).Equals(H,ESearchCase::IgnoreCase))return false;
        }
        for(int32 I=0;I<9;++I)
        {
            const FString& P=Saves[I];FString H;
            if(!Files->TryGetStringField(P,H)||!Policy.Check(P))return false;
            const FString F=Policy.Files.FindChecked(P.ToLower());
            if(H.IsEmpty())
            { if(I>=5||FPaths::FileExists(F)||FPackageName::DoesPackageExist(P))return false; }
            else if(!WTUSHA1(H)||!HashFile(F).Equals(H,ESearchCase::IgnoreCase))return false;
        }
        return true;
    }
    bool Read(const FString& Params,bool Verify)
    {
        FString Forbidden;
        if(FParse::Value(*Params,TEXT("Manifest="),Forbidden)||FParse::Value(*Params,TEXT("Receipt="),Forbidden)||!Candidate.Read(Params)||
            !FParse::Value(*Params,TEXT("SupplementPreparation="),Preparation)||!FParse::Value(*Params,TEXT("SupplementPreparationSHA1="),PreparationHash)||
            !WTUSHA1(PreparationHash)||!HashFile(Preparation).Equals(PreparationHash,ESearchCase::IgnoreCase)||!Json(Preparation,Prep)||
            Str(Prep,TEXT("schema"))!=TEXT("ut4-supplement-repair-preparation-v1")||Str(Prep,TEXT("operation"))!=TEXT("supplement-nine-assets-v1")||
            !Full(Str(Prep,TEXT("project_dir"))).Equals(Full(FPaths::GameDir()),ESearchCase::IgnoreCase))return false;
        InputsPath=Str(Prep,TEXT("inputs"));
        if(!HashFile(InputsPath).Equals(InputsHash(),ESearchCase::IgnoreCase)||!Json(InputsPath,Inputs))return false;
        OriginalProject=Full(Str(Inputs,TEXT("original_project")));
        if(OriginalProject.IsEmpty()||!Physical(OriginalProject,false)||!IFileManager::Get().DirectoryExists(*OriginalProject)||
            !Full(Str(Inputs,TEXT("project"))).Equals(Full(FPaths::GameDir()),ESearchCase::IgnoreCase)||
            !FParse::Value(*Params,TEXT("SupplementReceipt="),Receipt)||!FParse::Value(*Params,TEXT("SupplementReceiptSHA1="),ReceiptHash)||
            !WTUSHA1(ReceiptHash)||!HashFile(Receipt).Equals(ReceiptHash,ESearchCase::IgnoreCase))return false;
        const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
        if(!Inputs->TryGetArrayField(TEXT("packages"),Rows)||Rows->Num()!=17)return false;
        for(int32 I=0;I<17;++I)
        {
            if((*Rows)[I]->Type!=EJson::Object)return false;auto R=(*Rows)[I]->AsObject();const FString P=Str(R,TEXT("package")),H=Str(R,TEXT("sha1"));
            if(P!=SCSupplementRoots[I]||!WTUSHA1(H)||!H.Equals(Str(R,TEXT("original_sha1")),ESearchCase::IgnoreCase)||
                Full(Str(R,TEXT("file")))!=Full(FPackageName::LongPackageNameToFilename(P,TEXT(".uasset")))||
                Full(Str(R,TEXT("original_file")))!=Full(OriginalProject/TEXT("Content")/P.Mid(6)+TEXT(".uasset")))return false;
            OriginalHashes.Add(P,H.ToLower());
        }
        TSet<FString> Allowed;for(const auto& P:Saves)Allowed.Add(P.ToLower());
        TSharedPtr<FJsonObject> R;
        if(!Json(Receipt,R)||Str(R,TEXT("operation"))!=TEXT("supplement-nine-assets-v1")||!Policy.Read(Receipt,Preparation,Allowed)||
            !Within(OriginalProject,Policy.OriginalRoot)||Within(Full(FPaths::GameDir()),Policy.OriginalRoot))return false;
        if(!FParse::Value(*Params,TEXT("SupplementBefore="),BeforePath)||!FParse::Value(*Params,TEXT("SupplementRepairAftermath="),AfterPath)||
            !External(BeforePath,!Verify)||!External(AfterPath,!Verify)||Full(BeforePath).Equals(Full(AfterPath),ESearchCase::IgnoreCase))return false;
        Files=WGRObject();for(int32 I=0;I<9;++I)Files->SetStringField(Saves[I],I<5?FString():OriginalHashes.FindChecked(Saves[I]));
        if(Verify)
        {
            if(!FParse::Value(*Params,TEXT("SupplementRepairAftermathSHA1="),AfterHash)||!WTUSHA1(AfterHash)||
                !HashFile(AfterPath).Equals(AfterHash,ESearchCase::IgnoreCase)||!Json(AfterPath,After)||
                Str(After,TEXT("schema"))!=TEXT("ut4-supplement-repair-aftermath-v1")||!WGRBool(After,TEXT("complete"),true)||
                !WGRNumber(After,TEXT("saved"),9)||!Str(After,TEXT("preparation_sha1")).Equals(PreparationHash,ESearchCase::IgnoreCase)||
                !Str(After,TEXT("receipt_sha1")).Equals(ReceiptHash,ESearchCase::IgnoreCase))return false;
            const TSharedPtr<FJsonObject>* O=nullptr;
            if(!After->TryGetObjectField(TEXT("files"),O))return false;Files=*O;
            if(!After->TryGetObjectField(TEXT("ids"),O))return false;Ids=*O;
            if(!Json(BeforePath,Before)||Str(Before,TEXT("schema"))!=TEXT("ut4-supplement-repair-before-v1")||
                !Str(Before,TEXT("preparation_sha1")).Equals(PreparationHash,ESearchCase::IgnoreCase))return false;
            for(const auto& P:Saves)if(!WTUSHA1(Str(Files,*P)))return false;
        }
        else if(FPaths::FileExists(BeforePath)||FPaths::FileExists(AfterPath))return false;
        return CheckFiles();
    }
};

struct FSupplementRepairState
{
    FSupplementRepairProof& Proof; FSupplementMaterialCandidate Source;
    UMaterial* Master=nullptr; UMaterialInstanceConstant* Copies[4]={nullptr,nullptr,nullptr,nullptr};
    USkeletalMesh* Meshes[4]={nullptr,nullptr,nullptr,nullptr}; TSharedPtr<FJsonObject> Baseline[4],Ids;
    explicit FSupplementRepairState(FSupplementRepairProof& P):Proof(P),Source(P.Candidate){}
    bool Hold(UObject* O)
    { if(!WGRReady(O))return false;O->AddToRoot();Source.Roots.Add(O);return true; }
    bool Gather(bool Verify)
    {
        if(!Proof.CheckFiles()||!Source.Gather())return false;
        for(int32 I=0;I<4;++I)
        {
            const FString& P=Proof.Saves[I+5];
            Meshes[I]=LoadObject<USkeletalMesh>(nullptr,*ObjectPath(P));
            if(!Hold(Meshes[I])||Meshes[I]->GetClass()!=USkeletalMesh::StaticClass()||Meshes[I]->GetPathName()!=ObjectPath(P)||!Proof.CheckFiles())return false;
            if(Verify)
            {
                const TSharedPtr<FJsonObject>* B=nullptr;
                if(!Proof.Before->TryGetObjectField(*FString::Printf(TEXT("mesh%d"),I),B))return false;Baseline[I]=*B;
            }
            else
            {
                FString Error;if(!FEnforcerMeshInvariant::Snapshot(Meshes[I],Baseline[I],Error))
                { UE_LOG(LogUT4Html5Compat,Error,TEXT("COMPAT_SUPPLEMENT_REPAIR mesh=%s invariant=%s"),*P,*Error);return false; }
            }
        }
        if(Verify)
        {
            Master=LoadObject<UMaterial>(nullptr,*ObjectPath(Proof.Saves[0]));if(!Hold(Master))return false;
            for(int32 I=0;I<4;++I){Copies[I]=LoadObject<UMaterialInstanceConstant>(nullptr,*ObjectPath(Proof.Saves[I+1]));if(!Hold(Copies[I]))return false;}
            Ids=Proof.Ids;
            return Equivalent()&&MeshesEqual(true)&&Source.Unchanged()&&Proof.CheckFiles();
        }
        return MeshesEqual(false)&&Source.Unchanged()&&Proof.CheckFiles();
    }
    bool MeshesEqual(bool Changed) const
    {
        for(int32 I=0;I<4;++I)
        {
            auto* M=Meshes[I];const int32 Slot=SMRSlot(I),Member=SMRMember(I);
            if(!M||!Baseline[I].IsValid()||!M->Materials.IsValidIndex(Slot)||
                M->Materials[Slot].MaterialInterface!=(Changed?Copies[Member]:Source.Original[Member]))return false;
            TSharedPtr<FJsonObject> Now;FString Error;
            if(!FEnforcerMeshInvariant::Snapshot(M,Now,Error))return false;
            const TArray<TSharedPtr<FJsonValue>>* Slots=nullptr;
            if(!Now->TryGetArrayField(TEXT("material_slots"),Slots)||!Slots->IsValidIndex(Slot)||(*Slots)[Slot]->Type!=EJson::Object)return false;
            (*Slots)[Slot]->AsObject()->SetStringField(TEXT("material"),Source.Original[Member]->GetPathName());
            if(!FWeaponRepair().Same(MRValue(Baseline[I]),MRValue(Now)))return false;
        }
        return true;
    }
    bool Identity() const
    {
        if(!Ids.IsValid()||Ids->Values.Num()!=6||!Master||Master->GetClass()!=UMaterial::StaticClass()||Master->StateId==Source.V1->StateId||
            !Master->StateId.IsValid()||Master->StateId.ToString()!=Str(Ids,TEXT("master")))return false;
        UObject* Assets[]={Master,Copies[0],Copies[1],Copies[2],Copies[3]};
        for(int32 I=0;I<5;++I)
        {
            auto* A=Assets[I];auto* M=Cast<UMaterialInterface>(A);FGuid Expected;
            if(!M||!FGuid::Parse(Str(Ids,*FString::Printf(TEXT("lighting%d"),I)),Expected)||!Expected.IsValid()||M->GetLightingGuid()!=Expected||
                Expected==(I==0?Source.V1->GetLightingGuid():Source.Original[I-1]->GetLightingGuid())||
                A->GetPathName()!=ObjectPath(Proof.Saves[I])||A->GetOuter()!=A->GetOutermost()||A->GetOutermost()->GetName()!=Proof.Saves[I]||
                !A->HasAllFlags(RF_Public|RF_Standalone)||A->HasAnyFlags(RF_Transient))return false;
            if(I>0&&A->GetClass()!=UMaterialInstanceConstant::StaticClass())return false;
        }
        return true;
    }
    static bool NormalizeLighting(const TSharedPtr<FJsonObject>& A,const TSharedPtr<FJsonObject>& B)
    {
        FString X,Y;
        if(!A->TryGetStringField(TEXT("LightingGuid"),X)||!B->TryGetStringField(TEXT("LightingGuid"),Y)||X.IsEmpty()||Y.IsEmpty()||X==Y)return false;
        B->SetStringField(TEXT("LightingGuid"),X);return true;
    }
    bool Equivalent() const
    {
        if(!Identity()||!Source.V1->bUsedWithStaticLighting||Master->bUsedWithStaticLighting||!WSAOwnedGraph(Source.V1,Master))return false;
        FWeaponRepair Graph;Graph.Canonical.Add(Master->GetPathName(),Source.V1->GetPathName());
        auto A=WSAObject(Source.V1),B=WSAObject(Master);auto AP=A->GetObjectField(TEXT("properties")),BP=B->GetObjectField(TEXT("properties"));
        if(!AP->HasField(TEXT("StateId"))||!BP->HasField(TEXT("StateId"))||!NormalizeLighting(AP,BP)||
            !WGRLightingFields(AP,BP,Source.V1->bUsedWithStaticLighting,Master->bUsedWithStaticLighting))return false;
        BP->SetStringField(TEXT("StateId"),Str(AP,TEXT("StateId")));BP->SetStringField(TEXT("bUsedWithStaticLighting"),Str(AP,TEXT("bUsedWithStaticLighting")));
        if(!Graph.Same(MRValue(A),MRValue(B)))return false;
        for(int32 I=0;I<Source.V1->Expressions.Num();++I)
        {
            auto* E=Master->Expressions[I];
            if(E->HasAnyFlags(RF_Transient)||!Graph.Same(MRValue(WSAObject(Source.V1->Expressions[I])),MRValue(WSAObject(E))))return false;
            if(auto* C=Cast<UMaterialExpressionMaterialFunctionCall>(E))if(!WSAInterfaces(C))return false;
        }
        // Original master canonicalization is restricted to MIC facts, never the cloned graph.
        FWeaponRepair Instances;Instances.Canonical.Add(Master->GetPathName(),Source.V1->GetPathName());
        Instances.Canonical.Add(Source.OldMaster->GetPathName(),Source.V1->GetPathName());
        for(int32 I=0;I<4;++I)Instances.Canonical.Add(ObjectPath(Proof.Saves[I+1]),Source.Original[I]->GetPathName());
        for(int32 I=0;I<4;++I)
        {
            UMaterialInterface* Parent=(I==0||I==2)?static_cast<UMaterialInterface*>(Master):static_cast<UMaterialInterface*>(Copies[I-1]);
            if(Copies[I]->Parent!=Parent||Copies[I]->GetMaterial()!=Master)return false;
            auto X=WGRInstance(Source.Original[I],Source.V1,nullptr),Y=WGRInstance(Copies[I],Source.V1,nullptr);
            if(!X.IsValid()||!Y.IsValid()||!NormalizeLighting(X->GetObjectField(TEXT("properties")),Y->GetObjectField(TEXT("properties")))||
                !Instances.Same(MRValue(X),MRValue(Y)))return false;
        }
        return true;
    }
    bool Prepare()
    {
        if(!Proof.CheckFiles()||!Source.Unchanged()||!MeshesEqual(false))return false;
        for(int32 I=0;I<5;++I)if(FindPackage(nullptr,*Proof.Saves[I])||FPackageName::DoesPackageExist(Proof.Saves[I])||!Proof.Policy.Check(Proof.Saves[I]))return false;
        Master=DuplicateObject<UMaterial>(Source.V1,CreatePackage(nullptr,*Proof.Saves[0]),FName(*FPackageName::GetShortName(Proof.Saves[0])));
        if(!Hold(Master)||!WSAOwnedGraph(Source.V1,Master))return false;
        Master->SetFlags(RF_Public|RF_Standalone);Master->StateId=FGuid::NewGuid();
        for(auto* E:Master->Expressions)if(auto* C=Cast<UMaterialExpressionMaterialFunctionCall>(E))
        {
            auto BeforeCall=MRProperties(C,true);C->UpdateFromFunctionResource(false);
            if(!FWeaponRepair().Same(MRValue(BeforeCall),MRValue(MRProperties(C,true)))||!WSAInterfaces(C))return false;
        }
        Master->bUsedWithStaticLighting=false;Ids=WGRObject();Ids->SetStringField(TEXT("master"),Master->StateId.ToString());
        Ids->SetStringField(TEXT("lighting0"),Master->GetLightingGuid().ToString());
        for(int32 I=0;I<4;++I)
        {
            Copies[I]=DuplicateObject<UMaterialInstanceConstant>(Source.Original[I],CreatePackage(nullptr,*Proof.Saves[I+1]),FName(*FPackageName::GetShortName(Proof.Saves[I+1])));
            if(!Hold(Copies[I]))return false;Copies[I]->SetFlags(RF_Public|RF_Standalone);
            Ids->SetStringField(*FString::Printf(TEXT("lighting%d"),I+1),Copies[I]->GetLightingGuid().ToString());
            Copies[I]->SetParentEditorOnly((I==0||I==2)?static_cast<UMaterialInterface*>(Master):static_cast<UMaterialInterface*>(Copies[I-1]));
        }
        return WSADrain()&&Equivalent()&&MeshesEqual(false)&&Source.Unchanged()&&Proof.CheckFiles();
    }
    bool Compile()
    {
        int32 Count=0;
        for(int32 I=0;I<4;++I)for(auto Q:{EMaterialQualityLevel::Low,EMaterialQualityLevel::Medium,EMaterialQualityLevel::High})
        {
            if(!Equivalent()||!Source.Unchanged()||!Proof.CheckFiles()||Source.Resource)return false;
            auto*& R=Source.Resource;R=new FWSAOrdinaryResource;R->SetMaterial(Master,Q,true,ERHIFeatureLevel::ES2,Copies[I]);
            FMaterialShaderMapId ID;R->GetShaderMapId(SP_OPENGL_ES2_WEBGL,ID);FStaticParameterSet Static;Copies[I]->GetStaticParameterValues(Static);
            if(R->IsPersistent()||R->IsUsedWithStaticLighting()||R->IsSpecialEngineMaterial()||ID.BaseMaterialId!=Master->StateId||ID.QualityLevel!=Q||
                ID.FeatureLevel!=ERHIFeatureLevel::ES2||!FWeaponRepair().Same(MRValue(MRStatic(Static)),MRValue(MRStatic(ID.ParameterSet))))return false;
            const bool Cached=R->CacheShaders(ID,SP_OPENGL_ES2_WEBGL,false);R->FinishCompilation();
            if(!WSADrain()||!R->IsCompilationFinished())return false;auto* Map=R->GetGameThreadShaderMap();
            const bool MapOK=Cached&&R->HasValidGameThreadShaderMap()&&Map&&Map->IsCompilationFinalized()&&Map->CompiledSuccessfully()&&
                Map->GetShaderPlatform()==SP_OPENGL_ES2_WEBGL&&WSAOrdinaryIDEqual(ID,Map->GetShaderMapId())&&R->GetCompileErrors().Num()==0;
            const int32 Samplers=MapOK?R->GetSamplerUsage():-1;const bool Valid=MapOK&&Samplers>=0&&Samplers<=16;
            UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_SUPPLEMENT_REPAIR shader member=%d quality=%d valid=%d samplers=%d getterOverride=0 persistent=0"),I,int32(Q),Valid?1:0,Samplers);
            for(const auto& E:R->GetCompileErrors())UE_LOG(LogUT4Html5Compat,Warning,TEXT("COMPAT_SUPPLEMENT_REPAIR compiler_error %s"),*WFRContext(E));
            delete R;R=nullptr;if(!Valid||!Equivalent()||!Source.Unchanged()||!Proof.CheckFiles())return false;++Count;
        }
        return Count==12;
    }
    bool AssignSlots()
    {
        if(!Equivalent()||!MeshesEqual(false)||!Source.Unchanged()||!Proof.CheckFiles())return false;
        for(int32 I=0;I<4;++I)Meshes[I]->Materials[SMRSlot(I)].MaterialInterface=Copies[SMRMember(I)];
        return MeshesEqual(true)&&Equivalent()&&Source.Unchanged()&&Proof.CheckFiles();
    }
    bool SaveAll(const FString& BeforeHash)
    {
        UObject* Assets[]={Master,Copies[0],Copies[1],Copies[2],Copies[3],Meshes[0],Meshes[1],Meshes[2],Meshes[3]};
        for(int32 I=0;I<9;++I)
        {
            auto* A=Assets[I];const FString& P=Proof.Saves[I];
            if(!WGRReady(A)||A->GetOutermost()->GetName()!=P||!Equivalent()||!MeshesEqual(true)||!Source.Unchanged()||!Proof.CheckFiles()||
                !Proof.External(Proof.BeforePath,false)||!HashFile(Proof.BeforePath).Equals(BeforeHash,ESearchCase::IgnoreCase)||!Proof.Policy.Check(P))return false;
            A->MarkPackageDirty();
            if(!UPackage::SavePackage(A->GetOutermost(),A,RF_Public|RF_Standalone,*Proof.Policy.Files.FindChecked(P.ToLower())))return false;
            const FString H=HashFile(Proof.Policy.Files.FindChecked(P.ToLower())).ToLower();
            if(!WTUSHA1(H)||(I>=5&&H.Equals(Proof.OriginalHashes.FindChecked(P),ESearchCase::IgnoreCase)))return false;
            Proof.Files->SetStringField(P,H);
            if(!Proof.CheckFiles()||!Equivalent()||!MeshesEqual(true)||!Source.Unchanged())return false;
            UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_SUPPLEMENT_REPAIR saved ordinal=%d package=%s sha1=%s"),I+1,*P,*H);
        }
        return Proof.CheckFiles();
    }
};

static int32 SupplementMaterialRepair(const FString& Params,bool Verify,bool Preflight=false)
{
    if((Verify&&Preflight)||!GIsEditor||!IsInGameThread()||!FApp::CanEverRender()||FParse::Param(FCommandLine::Get(),TEXT("NoDependsGathering")))return SMRStop(TEXT("admission"));
    FSupplementRepairProof Proof;if(!Proof.Read(Params,Verify))return SMRStop(TEXT("proof"));
    FSupplementRepairState State(Proof);if(!State.Gather(Verify))return SMRStop(TEXT("gather"));
    if(Verify)
    {
        if(!State.Compile()||!State.Equivalent()||!State.MeshesEqual(true)||!State.Source.Unchanged()||!Proof.CheckFiles()||!State.Source.Close())return SMRStop(TEXT("fresh-verify"));
        UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_SUPPLEMENT_REPAIR complete mode=verify assetsSaved=0 materials=5 meshes=4 shaders=12 runtimeAcceptance=0"));return 0;
    }
    if(Preflight)
    {
        if(!State.MeshesEqual(false)||!State.Source.Unchanged()||!Proof.CheckFiles()||!State.Source.Close())return SMRStop(TEXT("preflight-final"));
        UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_SUPPLEMENT_REPAIR complete mode=preflight assetsSaved=0 meshes=4 shaders=0 runtimeAcceptance=0"));return 0;
    }
    FWGREvidence Before,After;
    if(!Proof.External(Proof.BeforePath,true)||!Proof.External(Proof.AfterPath,true)||!Before.Open(Proof.BeforePath)||!After.Open(Proof.AfterPath))return SMRStop(TEXT("reserve-evidence"));
    auto B=WGRObject();B->SetStringField(TEXT("schema"),TEXT("ut4-supplement-repair-before-v1"));B->SetStringField(TEXT("preparation_sha1"),Proof.PreparationHash.ToLower());
    B->SetObjectField(TEXT("original_semantics"),State.Source.Before);
    for(int32 I=0;I<4;++I)B->SetObjectField(*FString::Printf(TEXT("mesh%d"),I),State.Baseline[I]);
    if(!Before.Write(B)||!Before.Close())return SMRStop(TEXT("before-evidence"));const FString BeforeHash=HashFile(Proof.BeforePath);
    if(!WTUSHA1(BeforeHash)||!State.Prepare())return SMRStop(TEXT("prepare-copies"));
    if(!State.Compile())return SMRStop(TEXT("shader-resources"));
    if(!State.AssignSlots())return SMRStop(TEXT("assign-slots"));
    if(!State.SaveAll(BeforeHash))return SMRStop(TEXT("save-nine"));
    auto A=WGRObject();A->SetStringField(TEXT("schema"),TEXT("ut4-supplement-repair-aftermath-v1"));A->SetBoolField(TEXT("complete"),true);A->SetNumberField(TEXT("saved"),9);
    A->SetStringField(TEXT("preparation_sha1"),Proof.PreparationHash.ToLower());A->SetStringField(TEXT("receipt_sha1"),Proof.ReceiptHash.ToLower());A->SetStringField(TEXT("before_sha1"),BeforeHash.ToLower());
    A->SetObjectField(TEXT("files"),Proof.Files);A->SetObjectField(TEXT("ids"),State.Ids);A->SetBoolField(TEXT("runtime_acceptance"),false);
    if(!State.Equivalent()||!State.MeshesEqual(true)||!State.Source.Unchanged()||!Proof.CheckFiles()||!State.Source.Close()||!After.Write(A)||!After.Close())return SMRStop(TEXT("final-evidence"));
    const FString H=HashFile(Proof.AfterPath);TSharedPtr<FJsonObject> ReadBack;
    if(!WTUSHA1(H)||!Proof.Json(Proof.AfterPath,ReadBack)||!FWeaponRepair().Same(MRValue(A),MRValue(ReadBack))||
        !HashFile(Proof.AfterPath).Equals(H,ESearchCase::IgnoreCase)||!Proof.CheckFiles())return SMRStop(TEXT("aftermath-readback"));
    UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_SUPPLEMENT_REPAIR complete mode=apply assetsSaved=9 materials=5 meshes=4 shaders=12 runtimeAcceptance=0 aftermath_sha1=%s"),*H);return 0;
}
