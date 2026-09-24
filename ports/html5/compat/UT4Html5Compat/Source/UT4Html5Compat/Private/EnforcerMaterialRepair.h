// Exactly three dedicated material copies and two skeletal-mesh slot-zero writes.
// Include after EnforcerMaterialCandidate.h and EnforcerMeshInvariant.h.
static TArray<FString> EFRSaves()
{
    const FString D=TEXT("/Game/HTML5Compat/Weapons/V1/Enforcer/");
    TArray<FString> P; P.Add(D+TEXT("M_WeaponsBase_Enforcer")); P.Add(D+TEXT("MIC_Enforcer_1P")); P.Add(D+TEXT("MIC_Enforcer_3P"));
    P.Add(ECRRoots()[3]); P.Add(ECRRoots()[4]); return P;
}
static int32 EFRStop(const TCHAR* Gate)
{ UE_LOG(LogUT4Html5Compat, Error, TEXT("COMPAT_ENFORCER_REPAIR failure gate=%s"),Gate); return 1; }
struct FEnforcerRepairProof
{
    FSavePolicy Policy;
    FEnforcerCandidatePins Candidate;
    FString Preparation, PreparationHash, Receipt, ReceiptHash, BeforePath, AfterPath, AfterHash, OriginalRoot;
    TSharedPtr<FJsonObject> Prep, Artifacts, After, Files, Ids;
    TMap<FString,FString> OriginalHashes;
    TSharedPtr<FJsonObject> Baseline[2];
    TArray<FString> Saves=EFRSaves();
    bool External(const FString& P,bool Missing) const
    {
        const FString F=Full(P);
        return !OriginalRoot.IsEmpty() && !Within(F,Full(FPaths::GetPath(Full(FPaths::EngineDir())))) &&
            !Within(F,OriginalRoot) && !F.ToLower().Contains(TEXT("/content/")) && !F.ToLower().EndsWith(TEXT("/content")) && Physical(F,Missing);
    }
    bool Json(const FString& P,TSharedPtr<FJsonObject>& J) const
    { const int64 N=IFileManager::Get().FileSize(*P); return N>0 && N<=32*1024*1024 && Physical(P,false) && ReadJson(P,J); }
    bool Artifact(const TCHAR* Key,const TCHAR* Hash,FString& P) const
    {
        const TSharedPtr<FJsonObject>* J=nullptr;
        if(!Artifacts.IsValid() || !Artifacts->TryGetObjectField(Key,J)) return false;
        P=Str(*J,TEXT("path"));
        return Str(*J,TEXT("sha1")).Equals(Hash,ESearchCase::IgnoreCase) && External(P,false) && HashFile(P).Equals(Hash,ESearchCase::IgnoreCase);
    }
    bool Evidence() const
    {
        if(!External(Preparation,false) || !HashFile(Preparation).Equals(PreparationHash,ESearchCase::IgnoreCase) ||
            !External(Receipt,false) || !HashFile(Receipt).Equals(ReceiptHash,ESearchCase::IgnoreCase)) return false;
        if(After.IsValid() && (!External(AfterPath,false)||!HashFile(AfterPath).Equals(AfterHash,ESearchCase::IgnoreCase)||
            !External(BeforePath,false)||!HashFile(BeforePath).Equals(Str(After,TEXT("before_sha1")),ESearchCase::IgnoreCase)))return false;
        const TCHAR* Keys[]={TEXT("current25"),TEXT("consumer7"),TEXT("cow"),TEXT("mesh_baseline"),TEXT("candidate_result"),TEXT("candidate_log"),TEXT("grenade_aftermath")};
        const TCHAR* Hashes[]={TEXT("0c095f341809c849e888ffef66360bd3799d9d91"),TEXT("81a52a86f48c7d58c812870c4fbd515b95cbfa51"),
            TEXT("ac5742ef7b0e2666ecc8b55494a173fba3e5cd21"),TEXT("8fb92f359837aadda55e4ff1afee8dc1b7d3d8a2"),
            TEXT("2c77591e9cc8fe8a22791965c0ba7d54db513c16"),TEXT("b71c0e5431343ab9bee0e06d167cc14cf10c4685"),TEXT("f276720c105f3d754a53ff7cf38bff24b514fceb")};
        for(int32 I=0;I<7;++I){FString P;if(!Artifact(Keys[I],Hashes[I],P))return false;}
        const TArray<TSharedPtr<FJsonValue>>* Backups=nullptr;
        if(!Prep->TryGetArrayField(TEXT("backups"),Backups) || Backups->Num()!=2) return false;
        TSet<FString> Seen;
        for(const auto& V:*Backups)
        {
            if(V->Type!=EJson::Object)return false; auto J=V->AsObject(); const FString P=Str(J,TEXT("package")),F=Str(J,TEXT("path"));
            if((P!=Saves[3]&&P!=Saves[4]) || Seen.Contains(P) || !OriginalHashes.Contains(P) || !External(F,false) ||
                !Str(J,TEXT("sha1")).Equals(OriginalHashes.FindChecked(P),ESearchCase::IgnoreCase) ||
                !HashFile(F).Equals(OriginalHashes.FindChecked(P),ESearchCase::IgnoreCase)) return false;
            Seen.Add(P);
        }
        return true;
    }
    bool CheckFiles() const
    {
        if(!Evidence() || !Files.IsValid() || Files->Values.Num()!=33) return false;
        for(const auto& KV:Files->Values)
        {
            FString H; if(!KV.Value->TryGetString(H))return false;
            const int32 S=Saves.Find(KV.Key); const FString* Old=OriginalHashes.Find(KV.Key);
            if(!Old && (S<0 || S>2))return false;
            if(Old && S!=3 && S!=4 && !H.Equals(*Old,ESearchCase::IgnoreCase))return false;
            const FString F=FPackageName::LongPackageNameToFilename(KV.Key,TEXT(".uasset"));
            if(!Physical(F,H.IsEmpty()))return false;
            if(H.IsEmpty()){if(S<0||S>2||FPaths::FileExists(F)||FPackageName::DoesPackageExist(KV.Key))return false;}
            else if(!WTUSHA1(H)||!HashFile(F).Equals(H,ESearchCase::IgnoreCase))return false;
        }
        return true;
    }
    // Only transaction-produced/pinned aftermath mesh hashes replace the two observation rows.
    // Original consumer input bytes remain hard-pinned; this does not adopt current unknown bytes.
    bool SyncConsumerMeshes()
    {
        if(!CheckFiles() || Candidate.Consumers.Rows.Num()!=7)return false;
        for(int32 I=3;I<5;++I)
        {
            auto& Row=Candidate.Consumers.Rows[I]; const FString P=Str(Row,TEXT("package"));
            if(P!=Saves[I])return false;
            Row->SetStringField(TEXT("sha1"),Str(Files,*P));
            Row->SetNumberField(TEXT("bytes"),IFileManager::Get().FileSize(*Str(Row,TEXT("file"))));
        }
        return Candidate.Check();
    }
    bool Read(const FString& Params,bool Verify)
    {
        FString Forbidden;
        if(FParse::Value(*Params,TEXT("Manifest="),Forbidden)||FParse::Value(*Params,TEXT("Receipt="),Forbidden)||
            !FParse::Value(*Params,TEXT("EnforcerPreparation="),Preparation)||!FParse::Value(*Params,TEXT("EnforcerPreparationSHA1="),PreparationHash)||!WTUSHA1(PreparationHash)||
            !FParse::Value(*Params,TEXT("EnforcerReceipt="),Receipt)||!FParse::Value(*Params,TEXT("EnforcerReceiptSHA1="),ReceiptHash)||!WTUSHA1(ReceiptHash)||
            !HashFile(Preparation).Equals(PreparationHash,ESearchCase::IgnoreCase)||!Json(Preparation,Prep)||
            Str(Prep,TEXT("schema"))!=TEXT("ut4-enforcer-repair-preparation-v1")||Str(Prep,TEXT("operation"))!=TEXT("enforcer-five-assets-v1")||
            !Full(Str(Prep,TEXT("project_dir"))).Equals(Full(FPaths::GameDir()),ESearchCase::IgnoreCase))return false;
        OriginalRoot=Full(Str(Prep,TEXT("original_root")));
        const TSharedPtr<FJsonObject>* A=nullptr;
        if(!Prep->TryGetObjectField(TEXT("artifacts"),A)||(*A)->Values.Num()!=7)return false; Artifacts=*A;
        FString P; TSharedPtr<FJsonObject> J;
        if(!Artifact(TEXT("cow"),TEXT("ac5742ef7b0e2666ecc8b55494a173fba3e5cd21"),P)||!Json(P,J)||
            !J->TryGetObjectField(TEXT("plan"),A)||!Full(Str(*A,TEXT("original"))).Equals(OriginalRoot,ESearchCase::IgnoreCase)||
            !Full(Str(*A,TEXT("root"))).Equals(Full(FPaths::GetPath(Full(FPaths::EngineDir()))),ESearchCase::IgnoreCase))return false;
        if(!Artifact(TEXT("consumer7"),TEXT("81a52a86f48c7d58c812870c4fbd515b95cbfa51"),Candidate.Consumers.Path)||!Json(Candidate.Consumers.Path,J))return false;
        Candidate.Consumers.Hash=TEXT("81a52a86f48c7d58c812870c4fbd515b95cbfa51");
        const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
        if(!J->TryGetArrayField(TEXT("packages"),Rows)||Rows->Num()!=7)return false;
        const auto Roots=ECRRoots();
        for(int32 I=0;I<7;++I)
        {
            if((*Rows)[I]->Type!=EJson::Object)return false;auto R=(*Rows)[I]->AsObject();
            if(Str(R,TEXT("package"))!=Roots[I])return false;
            Candidate.Consumers.Rows.Add(R);OriginalHashes.Add(Roots[I],Str(R,TEXT("sha1")).ToLower());
        }
        if(!Artifact(TEXT("grenade_aftermath"),TEXT("f276720c105f3d754a53ff7cf38bff24b514fceb"),Candidate.AfterPath)||!Json(Candidate.AfterPath,J)||
            !J->TryGetObjectField(TEXT("package_sha1"),A)||(*A)->Values.Num()!=25)return false;
        Candidate.Files=*A;
        for(const auto& KV:Candidate.Files->Values)
        {
            FString H;if(!KV.Value->TryGetString(H)||!WTUSHA1(H))return false;H=H.ToLower();
            if(OriginalHashes.Contains(KV.Key)&&OriginalHashes.FindChecked(KV.Key)!=H)return false;OriginalHashes.Add(KV.Key,H);
        }
        if(OriginalHashes.Num()!=30||!Prep->TryGetArrayField(TEXT("sources"),Rows)||Rows->Num()!=30)return false;
        TSet<FString> Seen;
        for(const auto& V:*Rows)
        {
            if(V->Type!=EJson::Object)return false;auto R=V->AsObject();const FString Q=Str(R,TEXT("package"));const FString* H=OriginalHashes.Find(Q);
            if(!H||Seen.Contains(Q)||!Str(R,TEXT("sha1")).Equals(*H,ESearchCase::IgnoreCase)||
                !Full(Str(R,TEXT("file"))).Equals(Full(FPackageName::LongPackageNameToFilename(Q,TEXT(".uasset"))),ESearchCase::IgnoreCase))return false;Seen.Add(Q);
        }
        if(!Prep->TryGetArrayField(TEXT("outputs"),Rows)||Rows->Num()!=5)return false;
        TSet<FString> Allowed;
        for(int32 I=0;I<5;++I)
        {
            if((*Rows)[I]->Type!=EJson::Object)return false;auto R=(*Rows)[I]->AsObject();
            if(Str(R,TEXT("package"))!=Saves[I]||!Full(Str(R,TEXT("file"))).Equals(Full(FPackageName::LongPackageNameToFilename(Saves[I],TEXT(".uasset"))),ESearchCase::IgnoreCase))return false;
            Allowed.Add(Saves[I].ToLower());
        }
        if(!External(Preparation,false)||!External(Receipt,false)||!HashFile(Receipt).Equals(ReceiptHash,ESearchCase::IgnoreCase)||!Json(Receipt,J)||
            Str(J,TEXT("operation"))!=TEXT("enforcer-five-assets-v1")||!Policy.Read(Receipt,Preparation,Allowed)||!Policy.OriginalRoot.Equals(OriginalRoot,ESearchCase::IgnoreCase))return false;
        if(!Artifact(TEXT("mesh_baseline"),TEXT("8fb92f359837aadda55e4ff1afee8dc1b7d3d8a2"),P))return false;
        FString Text;TArray<TSharedPtr<FJsonValue>> MeshRows;
        if(!FFileHelper::LoadFileToString(Text,*P)||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),MeshRows)||MeshRows.Num()!=3)return false;
        for(int32 I=0;I<2;++I)
        {
            auto R=MeshRows[I]->AsObject();if(Str(R,TEXT("package"))!=Saves[I+3]||!R->TryGetObjectField(TEXT("snapshot"),A))return false;Baseline[I]=*A;
        }
        if(!FParse::Value(*Params,TEXT("EnforcerBefore="),BeforePath)||!FParse::Value(*Params,TEXT("EnforcerAftermath="),AfterPath)||
            !External(BeforePath,!Verify)||!External(AfterPath,!Verify)||Full(BeforePath).Equals(Full(AfterPath),ESearchCase::IgnoreCase))return false;
        Files=WGRObject();for(const auto& KV:OriginalHashes)Files->SetStringField(KV.Key,KV.Value);
        for(int32 I=0;I<3;++I)Files->SetStringField(Saves[I],TEXT(""));
        if(Verify)
        {
            if(!FParse::Value(*Params,TEXT("EnforcerAftermathSHA1="),AfterHash)||!WTUSHA1(AfterHash)||!HashFile(AfterPath).Equals(AfterHash,ESearchCase::IgnoreCase)||!Json(AfterPath,After)||
                Str(After,TEXT("schema"))!=TEXT("ut4-enforcer-repair-aftermath-v1")||!WGRBool(After,TEXT("complete"),true)||!WGRNumber(After,TEXT("saved"),5)||
                !Str(After,TEXT("preparation_sha1")).Equals(PreparationHash,ESearchCase::IgnoreCase)||!Str(After,TEXT("receipt_sha1")).Equals(ReceiptHash,ESearchCase::IgnoreCase)||
                !HashFile(BeforePath).Equals(Str(After,TEXT("before_sha1")),ESearchCase::IgnoreCase)||!After->TryGetObjectField(TEXT("files"),A))return false;Files=*A;
            if(!After->TryGetObjectField(TEXT("ids"),A))return false;Ids=*A;
            for(const auto& S:Saves)if(!WTUSHA1(Str(Files,*S)))return false;
        }
        else if(FPaths::FileExists(BeforePath)||FPaths::FileExists(AfterPath))return false;
        return SyncConsumerMeshes();
    }
};

struct FEnforcerRepairState
{
    FEnforcerRepairProof& Proof;
    FEnforcerCandidate Source;
    USkeletalMesh* Meshes[2]={nullptr,nullptr};
    UMaterial* Master=nullptr;
    UMaterialInstanceConstant* Copies[2]={nullptr,nullptr};
    TSharedPtr<FJsonObject> Ids;
    explicit FEnforcerRepairState(FEnforcerRepairProof& P):Proof(P),Source(P.Candidate){}
    bool Hold(UObject* O)
    {
        if(!O||O->IsRooted())return false;O->AddToRoot();Source.Roots.Add(O);return true;
    }
    bool Gather(bool Verify)
    {
        if(!Proof.CheckFiles()||!Source.Gather())return false;
        for(int32 I=0;I<2;++I)
        {
            Meshes[I]=LoadObject<USkeletalMesh>(nullptr,*ObjectPath(Proof.Saves[I+3]));
            if(!WGRReady(Meshes[I])||Meshes[I]->GetClass()!=USkeletalMesh::StaticClass()||!Hold(Meshes[I])||!Proof.CheckFiles())return false;
        }
        if(!Verify)return MeshesEqual(false)&&Source.Unchanged();
        Master=LoadObject<UMaterial>(nullptr,*ObjectPath(Proof.Saves[0]));
        if(!WGRReady(Master)||!Hold(Master))return false;
        for(int32 I=0;I<2;++I)
        {
            Copies[I]=LoadObject<UMaterialInstanceConstant>(nullptr,*ObjectPath(Proof.Saves[I+1]));
            if(!WGRReady(Copies[I])||!Hold(Copies[I]))return false;
        }
        Ids=Proof.Ids;
        return WSADrain()&&Equivalent()&&MeshesEqual(true)&&Source.Unchanged()&&Proof.CheckFiles();
    }
    bool MeshesEqual(bool Changed) const
    {
        for(int32 I=0;I<2;++I)
        {
            auto* M=Meshes[I];TSharedPtr<FJsonObject> Now;FString Error;
            if(!WGRReady(M)||M->Materials.Num()!=4||M->Materials[0].MaterialInterface!=(Changed?Copies[I]:Source.Original[I])||
                !FEnforcerMeshInvariant::Snapshot(M,Now,Error)||!Now.IsValid())return false;
            const auto& OldSlots=Proof.Baseline[I]->GetArrayField(TEXT("material_slots"));
            const auto& NewSlots=Now->GetArrayField(TEXT("material_slots"));
            if(OldSlots.Num()!=4||NewSlots.Num()!=4||Str(OldSlots[0]->AsObject(),TEXT("material"))!=Source.Original[I]->GetPathName())return false;
            if(Changed)
            {
                if(!Copies[I]||Str(NewSlots[0]->AsObject(),TEXT("material"))!=Copies[I]->GetPathName())return false;
                // Normalize only this one field in disposable JSON. All other slots/metadata remain exact.
                NewSlots[0]->AsObject()->SetStringField(TEXT("material"),Source.Original[I]->GetPathName());
            }
            if(!FWeaponRepair().Same(MRValue(Proof.Baseline[I]),MRValue(Now)))return false;
        }
        return true;
    }
    bool Identity() const
    {
        if(!WGRReady(Master)||Master->GetClass()!=UMaterial::StaticClass()||!Ids.IsValid()||Ids->Values.Num()!=4||
            !Master->StateId.IsValid()||Master->StateId==Source.Master->StateId||Str(Ids,TEXT("master"))!=Master->StateId.ToString())return false;
        UMaterialInterface* Old[]={Source.Master,Source.Original[0],Source.Original[1]};
        UMaterialInterface* New[]={Master,Copies[0],Copies[1]};
        for(int32 I=0;I<3;++I)
        {
            auto* N=New[I];
            if(!WGRReady(N)||N==Old[I]||N->GetClass()!=Old[I]->GetClass()||N->GetPathName()!=ObjectPath(Proof.Saves[I])||
                N->GetOuter()!=N->GetOutermost()||N->HasAnyFlags(RF_Transient)||!N->HasAllFlags(RF_Public|RF_Standalone)||
                !N->GetLightingGuid().IsValid()||N->GetLightingGuid()==Old[I]->GetLightingGuid()||
                Str(Ids,*FString::Printf(TEXT("lighting%d"),I))!=N->GetLightingGuid().ToString())return false;
        }
        return Copies[0]->Parent==Master&&Copies[1]->Parent==Master;
    }
    bool NormalizeLighting(const TSharedPtr<FJsonObject>& A,const TSharedPtr<FJsonObject>& B) const
    {
        FString X,Y;
        if(!A->TryGetStringField(TEXT("LightingGuid"),X)||!B->TryGetStringField(TEXT("LightingGuid"),Y)||X.IsEmpty()||Y.IsEmpty()||X==Y)return false;
        B->SetStringField(TEXT("LightingGuid"),X);return true;
    }
    bool Equivalent() const
    {
        if(!Identity()||!Source.Master->bUsedWithStaticLighting||Master->bUsedWithStaticLighting||!WSAOwnedGraph(Source.Master,Master))return false;
        FWeaponRepair Compare;Compare.Canonical.Add(Master->GetPathName(),Source.Master->GetPathName());
        for(int32 I=0;I<2;++I)
        {
            if(Copies[I]->GetMaterial()!=Master)return false;
            Compare.Canonical.Add(Copies[I]->GetPathName(),Source.Original[I]->GetPathName());
        }
        auto A=WSAObject(Source.Master),B=WSAObject(Master);
        auto AP=A->GetObjectField(TEXT("properties")),BP=B->GetObjectField(TEXT("properties"));
        if(!AP->HasField(TEXT("StateId"))||!BP->HasField(TEXT("StateId"))||!NormalizeLighting(AP,BP)||
            !WGRLightingFields(AP,BP,Source.Master->bUsedWithStaticLighting,Master->bUsedWithStaticLighting))return false;
        BP->SetStringField(TEXT("StateId"),Str(AP,TEXT("StateId")));
        BP->SetStringField(TEXT("bUsedWithStaticLighting"),Str(AP,TEXT("bUsedWithStaticLighting")));
        if(!Compare.Same(MRValue(A),MRValue(B)))return false;
        for(int32 I=0;I<Source.Master->Expressions.Num();++I)
        {
            auto* E=Master->Expressions[I];
            if(E->HasAnyFlags(RF_Transient)||!Compare.Same(MRValue(WSAObject(Source.Master->Expressions[I])),MRValue(WSAObject(E))))return false;
            if(auto* C=Cast<UMaterialExpressionMaterialFunctionCall>(E))if(!WSAInterfaces(C))return false;
        }
        for(int32 I=0;I<2;++I)
        {
            auto X=WGRInstance(Source.Original[I],Source.Master,nullptr),Y=WGRInstance(Copies[I],Source.Master,nullptr);
            if(!X.IsValid()||!Y.IsValid()||!NormalizeLighting(X->GetObjectField(TEXT("properties")),Y->GetObjectField(TEXT("properties")))||
                !Compare.Same(MRValue(X),MRValue(Y)))return false;
        }
        return true;
    }
    bool Prepare()
    {
        if(!Proof.CheckFiles()||!Source.Unchanged()||!MeshesEqual(false))return false;
        for(int32 I=0;I<3;++I)
            if(FindPackage(nullptr,*Proof.Saves[I])||FPackageName::DoesPackageExist(Proof.Saves[I])||!Proof.Policy.Check(Proof.Saves[I]))return false;
        Master=DuplicateObject<UMaterial>(Source.Master,CreatePackage(nullptr,*Proof.Saves[0]),FName(*FPackageName::GetShortName(Proof.Saves[0])));
        if(!Hold(Master)||!WSAOwnedGraph(Source.Master,Master))return false;
        Master->SetFlags(RF_Public|RF_Standalone);Master->StateId=FGuid::NewGuid();
        for(auto* E:Master->Expressions)if(auto* C=Cast<UMaterialExpressionMaterialFunctionCall>(E))
        {
            auto Before=MRProperties(C,true);C->UpdateFromFunctionResource(false);
            if(!FWeaponRepair().Same(MRValue(Before),MRValue(MRProperties(C,true)))||!WSAInterfaces(C))return false;
        }
        Master->bUsedWithStaticLighting=false;
        Ids=WGRObject();Ids->SetStringField(TEXT("master"),Master->StateId.ToString());Ids->SetStringField(TEXT("lighting0"),Master->GetLightingGuid().ToString());
        for(int32 I=0;I<2;++I)
        {
            Copies[I]=DuplicateObject<UMaterialInstanceConstant>(Source.Original[I],CreatePackage(nullptr,*Proof.Saves[I+1]),FName(*FPackageName::GetShortName(Proof.Saves[I+1])));
            if(!Hold(Copies[I])||Copies[I]->GetPathName()!=ObjectPath(Proof.Saves[I+1]))return false;
            Copies[I]->SetFlags(RF_Public|RF_Standalone);
            Ids->SetStringField(*FString::Printf(TEXT("lighting%d"),I+1),Copies[I]->GetLightingGuid().ToString());
            Copies[I]->SetParentEditorOnly(Master);
        }
        return WSADrain()&&Equivalent()&&MeshesEqual(false)&&Source.Unchanged()&&Proof.CheckFiles();
    }
    bool Compile()
    {
        int32 Count=0;
        for(int32 I=0;I<2;++I)for(auto Q:{EMaterialQualityLevel::Low,EMaterialQualityLevel::Medium,EMaterialQualityLevel::High})
        {
            if(!Equivalent()||!Source.Unchanged()||!Proof.CheckFiles()||Source.Resource)return false;
            auto*& R=Source.Resource;R=new FWSAOrdinaryResource;R->SetMaterial(Master,Q,true,ERHIFeatureLevel::ES2,Copies[I]);
            FMaterialShaderMapId ID;R->GetShaderMapId(SP_OPENGL_ES2_WEBGL,ID);FStaticParameterSet Static;Copies[I]->GetStaticParameterValues(Static);
            if(R->IsPersistent()||R->IsUsedWithStaticLighting()||R->IsSpecialEngineMaterial()||ID.BaseMaterialId!=Master->StateId||ID.QualityLevel!=Q||
                ID.FeatureLevel!=ERHIFeatureLevel::ES2||!FWeaponRepair().Same(MRValue(MRStatic(Static)),MRValue(MRStatic(ID.ParameterSet))))return false;
            const bool Cached=R->CacheShaders(ID,SP_OPENGL_ES2_WEBGL,false);R->FinishCompilation();
            if(!WSADrain()||!R->IsCompilationFinished())return false;
            auto* Map=R->GetGameThreadShaderMap();
            const bool MapOK=Cached&&R->HasValidGameThreadShaderMap()&&Map&&Map->IsCompilationFinalized()&&Map->CompiledSuccessfully()&&
                Map->GetShaderPlatform()==SP_OPENGL_ES2_WEBGL&&WSAOrdinaryIDEqual(ID,Map->GetShaderMapId())&&R->GetCompileErrors().Num()==0;
            const int32 Samplers=MapOK?R->GetSamplerUsage():-1;const bool Valid=MapOK&&Samplers>=0&&Samplers<=16;
            UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_ENFORCER_REPAIR shader member=%d quality=%d valid=%d samplers=%d getterOverride=0 persistent=0"),I,int32(Q),Valid?1:0,Samplers);
            for(const auto& E:R->GetCompileErrors())UE_LOG(LogUT4Html5Compat,Warning,TEXT("COMPAT_ENFORCER_REPAIR compiler_error %s"),*WFRContext(E));
            delete R;R=nullptr;if(!Valid||!Equivalent()||!Source.Unchanged()||!Proof.CheckFiles())return false;++Count;
        }
        return Count==6;
    }
    bool AssignSlots()
    {
        if(!Equivalent()||!MeshesEqual(false)||!Source.Unchanged()||!Proof.CheckFiles())return false;
        // Both meshes and all four slots were validated before the first pointer assignment.
        for(int32 I=0;I<2;++I)Meshes[I]->Materials[0].MaterialInterface=Copies[I];
        return MeshesEqual(true)&&Equivalent()&&Source.Unchanged()&&Proof.CheckFiles();
    }
    bool SaveAll(const FString& BeforeHash)
    {
        UObject* Assets[]={Master,Copies[0],Copies[1],Meshes[0],Meshes[1]};
        for(int32 I=0;I<5;++I)
        {
            auto* A=Assets[I];const FString& P=Proof.Saves[I];
            if(!WGRReady(A)||A->GetOutermost()->GetName()!=P||!Equivalent()||!MeshesEqual(true)||!Source.Unchanged()||!Proof.CheckFiles()||
                !Proof.External(Proof.BeforePath,false)||!HashFile(Proof.BeforePath).Equals(BeforeHash,ESearchCase::IgnoreCase)||!Proof.Policy.Check(P))return false;
            A->MarkPackageDirty();
            if(!UPackage::SavePackage(A->GetOutermost(),A,RF_Public|RF_Standalone,*Proof.Policy.Files.FindChecked(P.ToLower())))return false;
            const FString H=HashFile(Proof.Policy.Files.FindChecked(P.ToLower())).ToLower();
            if(!WTUSHA1(H)||(I>=3&&H.Equals(Proof.OriginalHashes.FindChecked(P),ESearchCase::IgnoreCase)))return false;
            Proof.Files->SetStringField(P,H);
            if(!Proof.SyncConsumerMeshes()||!Equivalent()||!MeshesEqual(true)||!Source.Unchanged())return false;
            UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_ENFORCER_REPAIR saved ordinal=%d package=%s sha1=%s"),I+1,*P,*H);
        }
        return Proof.CheckFiles();
    }
};

static int32 EnforcerMaterialRepair(const FString& Params,bool Verify,bool Preflight=false)
{
    if((Verify&&Preflight)||!GIsEditor||!IsInGameThread()||!FApp::CanEverRender()||FParse::Param(FCommandLine::Get(),TEXT("NoDependsGathering")))return EFRStop(TEXT("admission"));
    FEnforcerRepairProof Proof;if(!Proof.Read(Params,Verify))return EFRStop(TEXT("proof"));
    FEnforcerRepairState State(Proof);if(!State.Gather(Verify))return EFRStop(TEXT("gather"));
    if(Verify)
    {
        if(!State.Compile()||!State.Equivalent()||!State.MeshesEqual(true)||!State.Source.Unchanged()||!Proof.CheckFiles()||!State.Source.Close())return EFRStop(TEXT("fresh-verify"));
        UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_ENFORCER_REPAIR complete mode=verify assetsSaved=0 materials=3 meshes=2 shaders=6 runtimeAcceptance=0"));return 0;
    }
    if(Preflight)
    {
        if(!State.MeshesEqual(false)||!State.Source.Unchanged()||!Proof.CheckFiles()||!State.Source.Close())return EFRStop(TEXT("preflight-final"));
        UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_ENFORCER_REPAIR complete mode=preflight assetsSaved=0 meshes=2 shaders=0 runtimeAcceptance=0"));return 0;
    }
    FWGREvidence Before,After;
    if(!Proof.External(Proof.BeforePath,true)||!Proof.External(Proof.AfterPath,true)||!Before.Open(Proof.BeforePath)||!After.Open(Proof.AfterPath))return EFRStop(TEXT("reserve-evidence"));
    auto B=WGRObject();B->SetStringField(TEXT("schema"),TEXT("ut4-enforcer-repair-before-v1"));B->SetStringField(TEXT("preparation_sha1"),Proof.PreparationHash.ToLower());
    B->SetObjectField(TEXT("original_semantics"),State.Source.Before);B->SetObjectField(TEXT("mesh1"),Proof.Baseline[0]);B->SetObjectField(TEXT("mesh3"),Proof.Baseline[1]);
    if(!Before.Write(B)||!Before.Close())return EFRStop(TEXT("before-evidence"));const FString BeforeHash=HashFile(Proof.BeforePath);
    if(!WTUSHA1(BeforeHash)||!State.Prepare())return EFRStop(TEXT("prepare-copies"));
    if(!State.Compile())return EFRStop(TEXT("shader-resources"));
    if(!State.AssignSlots())return EFRStop(TEXT("assign-slots"));
    if(!State.SaveAll(BeforeHash))return EFRStop(TEXT("save-five"));
    auto A=WGRObject();A->SetStringField(TEXT("schema"),TEXT("ut4-enforcer-repair-aftermath-v1"));A->SetBoolField(TEXT("complete"),true);A->SetNumberField(TEXT("saved"),5);
    A->SetStringField(TEXT("preparation_sha1"),Proof.PreparationHash.ToLower());A->SetStringField(TEXT("receipt_sha1"),Proof.ReceiptHash.ToLower());A->SetStringField(TEXT("before_sha1"),BeforeHash.ToLower());
    A->SetObjectField(TEXT("files"),Proof.Files);A->SetObjectField(TEXT("ids"),State.Ids);A->SetBoolField(TEXT("runtime_acceptance"),false);
    if(!State.Equivalent()||!State.MeshesEqual(true)||!State.Source.Unchanged()||!Proof.CheckFiles()||!State.Source.Close()||!After.Write(A)||!After.Close())return EFRStop(TEXT("final-evidence"));
    const FString SavedAfterHash=HashFile(Proof.AfterPath);TSharedPtr<FJsonObject> ReadBack;
    if(!WTUSHA1(SavedAfterHash)||!Proof.Json(Proof.AfterPath,ReadBack)||!FWeaponRepair().Same(MRValue(A),MRValue(ReadBack))||
        !HashFile(Proof.AfterPath).Equals(SavedAfterHash,ESearchCase::IgnoreCase)||!Proof.CheckFiles())return EFRStop(TEXT("aftermath-readback"));
    UE_LOG(LogUT4Html5Compat,Display,TEXT("COMPAT_ENFORCER_REPAIR complete mode=apply assetsSaved=5 materials=3 meshes=2 shaders=6 runtimeAcceptance=0 aftermath_sha1=%s"),*SavedAfterHash);return 0;
}
