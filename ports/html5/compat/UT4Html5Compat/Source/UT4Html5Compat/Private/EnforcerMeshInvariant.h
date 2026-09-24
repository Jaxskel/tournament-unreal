#pragma once

// Read-only pre/post mesh snapshot. No UObject serialization, setters, or package mutation.
struct FEnforcerMeshInvariant
{
    static constexpr uint32 MaxVertices=2000000, MaxIndices=12000000, MaxBulkBytes=64u*1024u*1024u, MaxBones=2048;
    struct FDigest
    {
        FSHA1 Hash;
        void Raw(const void* P,uint32 N) { if (N) Hash.Update(static_cast<const uint8*>(P),N); }
        void U32(uint32 V) { uint8 B[4]={uint8(V),uint8(V>>8),uint8(V>>16),uint8(V>>24)}; Raw(B,4); }
        void I32(int32 V) { U32(uint32(V)); }
        void Bool(bool V) { U32(V?1:0); }
        void Float(float V) { uint32 B; FMemory::Memcpy(&B,&V,sizeof(B)); U32(B); }
        void Vec(const FVector& V) { Float(V.X);Float(V.Y);Float(V.Z); }
        void Quat(const FQuat& Q) { Float(Q.X);Float(Q.Y);Float(Q.Z);Float(Q.W); }
        void Name(const FString& S) { FTCHARToUTF8 B(*S); U32(uint32(B.Length())); Raw(B.Get(),uint32(B.Length())); }
        template<class T> void Array(const TArray<T>& A) { U32(uint32(A.Num())); for(const T& V:A) U32(uint32(V)); }
        FString Finish() { uint8 B[20]; Hash.Final();Hash.GetHash(B);return BytesToHex(B,20).ToLower(); }
    };
    static bool Bulk(FDigest& D,const FUntypedBulkData& B)
    {
        const int32 N=B.GetBulkDataSize(); if(N<0||uint32(N)>MaxBulkBytes)return false;
        D.U32(uint32(N)); if(!N)return true;
        const void* P=B.LockReadOnly(); if(!P)return false;
        D.Raw(P,uint32(N)); B.Unlock(); return true;
    }
    static FString SlotMetadata(const FSkeletalMaterial& M)
    {
        FDigest D;
        D.Name(M.MaterialSlotName.ToString()); D.Name(M.ImportedMaterialSlotName.ToString());
        D.Bool(M.bEnableShadowCasting_DEPRECATED); D.Bool(M.bRecomputeTangent_DEPRECATED);
        D.Bool(M.UVChannelData.bInitialized); D.Bool(M.UVChannelData.bOverrideDensities);
        for(int32 I=0;I<MAX_TEXCOORDS;++I) D.Float(M.UVChannelData.LocalUVDensities[I]);
        return D.Finish();
    }
    template<bool Extra> static bool GPU(FDigest& D,const FSkeletalMeshVertexBuffer& B)
    {
        const uint32 Inf=Extra?MAX_TOTAL_INFLUENCES:MAX_INFLUENCES_PER_STREAM;
        if(!B.GetVertexPtr<Extra>(0))return false;
        for(uint32 I=0;I<B.GetNumVertices();++I)
        {
            const auto* V=B.GetVertexPtr<Extra>(I);
            D.U32(V->TangentX.Vector.Packed);D.U32(V->TangentZ.Vector.Packed);
            for(uint32 J=0;J<Inf;++J){D.U32(V->InfluenceBones[J]);D.U32(V->InfluenceWeights[J]);}
            D.Vec(B.GetVertexPositionSlow(I));
            for(uint32 U=0;U<B.GetNumTexCoords();++U){FVector2D UV=B.GetVertexUV(I,U);D.Float(UV.X);D.Float(UV.Y);}
        }
        return true;
    }
    static bool ColorShape(const FSkeletalMeshVertexColorBuffer& B,uint32 Expected)
    {
        const uint32 N=B.GetNumVertices();
        return N==0||(N==Expected&&N<=MaxVertices&&B.GetStride()==sizeof(FGPUSkinVertexColor));
    }
    static bool Colors(FDigest& D,const FSkeletalMeshVertexColorBuffer& B,uint32 Expected)
    {
        if(!ColorShape(B,Expected))return false;
        const uint32 N=B.GetNumVertices();D.U32(N);
        // Empty streams retain the old digest exactly. Native loading allocates
        // color data with CPU access; editor/commandlet resource arrays do not discard it.
        if(N)D.U32(B.GetStride());
        for(uint32 I=0;I<N;++I)
        {
            const FColor& C=B.VertexColor(I);
            D.U32(C.R);D.U32(C.G);D.U32(C.B);D.U32(C.A);
        }
        return true;
    }
    static bool Snapshot(USkeletalMesh* Mesh,TSharedPtr<FJsonObject>& Out,FString& Error)
    {
        Out.Reset(); if(!GIsEditor||!IsInGameThread()){Error=TEXT("editor game thread required");return false;}
        FSkeletalMeshResource* R=Mesh?Mesh->GetImportedResource():nullptr;bool HasColors=false;
        if(!Mesh||!R||R->LODModels.Num()<1||R->LODModels.Num()>MAX_SKELETAL_MESH_LODS||Mesh->MorphTargets.Num()||Mesh->ClothingAssets.Num()||Mesh->Materials.Num()<1||Mesh->Materials.Num()>256)
        {Error=TEXT("mesh unavailable or morph/cloth unsupported");return false;}
        const FReferenceSkeleton& Ref=Mesh->RefSkeleton;
        const auto& RawInfo=Ref.GetRawRefBoneInfo(); const auto& RawPose=Ref.GetRawRefBonePose();
        const auto& FinalInfo=Ref.GetRefBoneInfo(); const auto& FinalPose=Ref.GetRefBonePose();
        const auto& ReqVB=Ref.GetRequiredVirtualBones(); const auto& UsedVB=Ref.GetVirtualBoneRefData();
        if(RawInfo.Num()<=0||RawInfo.Num()!=RawPose.Num()||FinalInfo.Num()<=0||FinalInfo.Num()!=FinalPose.Num()||
           RawInfo.Num()>int32(MaxBones)||FinalInfo.Num()>int32(MaxBones)||ReqVB.Num()>int32(MaxBones)||UsedVB.Num()>int32(MaxBones))
        {Error=TEXT("reference skeleton arrays unavailable or oversized");return false;}
        // Preflight every variable-sized LOD collection and index buffer before hashing/allocating arrays.
        for(int32 L=0;L<R->LODModels.Num();++L)
        {
            const FStaticLODModel& Lod=R->LODModels[L];
            if(!Lod.NumVertices||Lod.NumVertices>MaxVertices||Lod.Sections.Num()<1||Lod.Sections.Num()>4096||Lod.NumTexCoords>MAX_TEXCOORDS||
               Lod.VertexBufferGPUSkin.GetNumVertices()!=Lod.NumVertices||Lod.VertexBufferGPUSkin.GetNumTexCoords()!=Lod.NumTexCoords||!Lod.VertexBufferGPUSkin.IsVertexDataValid()||
               Lod.MorphTargetVertexInfoBuffers.GetNumInfluencedVerticesByMorphs()!=0||Lod.APEXClothVertexBuffer.GetNumVertices()!=0||
               !ColorShape(Lod.ColorVertexBuffer,Lod.NumVertices)||(Lod.ColorVertexBuffer.GetNumVertices()!=0&&!Mesh->bHasVertexColors))
            {Error=FString::Printf(TEXT("LOD GPU/section metadata invalid: lod=%d vertices=%u sections=%d uv=%u gpuVertices=%u gpuUV=%u gpuValid=%d morph=%u cloth=%u colors=%u"),
                L,Lod.NumVertices,Lod.Sections.Num(),uint32(Lod.NumTexCoords),Lod.VertexBufferGPUSkin.GetNumVertices(),
                Lod.VertexBufferGPUSkin.GetNumTexCoords(),Lod.VertexBufferGPUSkin.IsVertexDataValid()?1:0,
                Lod.MorphTargetVertexInfoBuffers.GetNumInfluencedVerticesByMorphs(),Lod.APEXClothVertexBuffer.GetNumVertices(),Lod.ColorVertexBuffer.GetNumVertices());return false;}
            HasColors|=Lod.ColorVertexBuffer.GetNumVertices()!=0;
            uint64 SoftTotal=0;
            for(const FSkelMeshSection& S:Lod.Sections)
            {
                if(S.NumVertices<=0||S.SoftVertices.Num()!=S.NumVertices||uint32(S.NumVertices)>MaxVertices||
                   S.HasApexClothData()||S.ApexClothMappingData.Num()||S.PhysicalMeshVertices.Num()||S.PhysicalMeshNormals.Num()||S.BoneMap.Num()>int32(MaxBones))
                {Error=TEXT("soft vertices invalid or cloth unsupported");return false;}
                SoftTotal+=uint32(S.NumVertices);if(SoftTotal>Lod.NumVertices){Error=TEXT("section vertices exceed LOD");return false;}
            }
            if(SoftTotal!=Lod.NumVertices||Lod.ActiveBoneIndices.Num()>int32(MaxBones)||Lod.RequiredBones.Num()>int32(MaxBones)||
               Lod.MeshToImportVertexMap.Num()>int32(MaxVertices)||Lod.MultiSizeIndexContainer.GetDataTypeSize()<2||Lod.MultiSizeIndexContainer.GetDataTypeSize()>4)
            {Error=TEXT("LOD arrays or index format invalid");return false;}
            if(!Lod.MultiSizeIndexContainer.IsIndexBufferValid()||Lod.MultiSizeIndexContainer.GetIndexBuffer()->Num()<=0||
               uint32(Lod.MultiSizeIndexContainer.GetIndexBuffer()->Num())>MaxIndices||
               (Lod.AdjacencyMultiSizeIndexContainer.IsIndexBufferValid()&&Lod.AdjacencyMultiSizeIndexContainer.GetIndexBuffer()->Num()>int32(MaxIndices)))
            {Error=TEXT("LOD index count invalid");return false;}
            if(Lod.RawPointIndices.GetBulkDataSize()<0||uint32(Lod.RawPointIndices.GetBulkDataSize())>MaxBulkBytes||
               Lod.LegacyRawPointIndices.GetBulkDataSize()<0||uint32(Lod.LegacyRawPointIndices.GetBulkDataSize())>MaxBulkBytes)
            {Error=TEXT("import bulk size invalid");return false;}
        }
        FDigest D;
        auto BoneArrays=[&](const TArray<FMeshBoneInfo>& Info,const TArray<FTransform>& Pose)
        {D.U32(uint32(Info.Num()));for(int32 I=0;I<Info.Num();++I){D.Name(Info[I].Name.ToString());D.I32(Info[I].ParentIndex);D.Vec(Pose[I].GetTranslation());D.Quat(Pose[I].GetRotation());D.Vec(Pose[I].GetScale3D());}};
        BoneArrays(RawInfo,RawPose);BoneArrays(FinalInfo,FinalPose);D.Array(ReqVB);D.U32(uint32(UsedVB.Num()));
        for(const FVirtualBoneRefData& V:UsedVB){D.I32(V.VBRefSkelIndex);D.I32(V.SourceRefSkelIndex);D.I32(V.TargetRefSkelIndex);}
        for(int32 L=0;L<R->LODModels.Num();++L)
        {
            const FStaticLODModel& Lod=R->LODModels[L];D.U32(Lod.NumVertices);D.U32(Lod.NumTexCoords);
            D.Array(Lod.ActiveBoneIndices);D.Array(Lod.RequiredBones);D.U32(uint32(Lod.Sections.Num()));
            for(const FSkelMeshSection& S:Lod.Sections)
            {
                D.U32(uint32(S.MaterialIndex));D.U32(S.BaseIndex);D.I32(S.NumTriangles);D.U32(S.BaseVertexIndex);D.I32(S.NumVertices);
                D.U32(uint32(S.TriangleSorting));D.Bool(S.bRecomputeTangent);D.Bool(S.bCastShadow);D.Bool(S.bDisabled);
                D.I32(S.CorrespondClothSectionIndex);D.I32(S.CorrespondClothAssetIndex);D.I32(S.ClothAssetSubmeshIndex);D.I32(S.MaxBoneInfluences);D.Array(S.BoneMap);
                for(const FSoftSkinVertex& V:S.SoftVertices)
                {
                    D.Vec(V.Position);
                    D.U32(V.TangentX.Vector.Packed);D.U32(V.TangentY.Vector.Packed);D.U32(V.TangentZ.Vector.Packed);
                    for(int32 U=0;U<MAX_TEXCOORDS;++U){D.Float(V.UVs[U].X);D.Float(V.UVs[U].Y);}
                    D.U32(V.Color.R);D.U32(V.Color.G);D.U32(V.Color.B);D.U32(V.Color.A);
                    for(int32 B=0;B<MAX_TOTAL_INFLUENCES;++B){D.U32(V.InfluenceBones[B]);D.U32(V.InfluenceWeights[B]);}
                }
            }
            TArray<uint32> Idx;Lod.MultiSizeIndexContainer.GetIndexBuffer(Idx);D.Array(Idx);
            const bool HasAdj=Lod.AdjacencyMultiSizeIndexContainer.IsIndexBufferValid();D.Bool(HasAdj);
            if(HasAdj){TArray<uint32> Adj;Lod.AdjacencyMultiSizeIndexContainer.GetIndexBuffer(Adj);D.Array(Adj);}else D.U32(0);
            D.Array(Lod.MeshToImportVertexMap);D.I32(Lod.MaxImportVertex);
            if(!Bulk(D,Lod.RawPointIndices)||!Bulk(D,Lod.LegacyRawPointIndices)){Error=TEXT("bulk read failed");return false;}
            const auto& G=Lod.VertexBufferGPUSkin;D.U32(G.GetNumVertices());D.U32(G.GetStride());D.U32(G.GetNumTexCoords());D.Bool(G.GetUseFullPrecisionUVs());D.Bool(G.HasExtraBoneInfluences());
            if(G.HasExtraBoneInfluences()?!GPU<true>(D,G):!GPU<false>(D,G)){Error=TEXT("GPU vertex payload unavailable");return false;}
            if(!Colors(D,Lod.ColorVertexBuffer,Lod.NumVertices)){Error=TEXT("color buffer shape changed");return false;}
        }
        Out=MRProperties(Mesh,true);if(!Out.IsValid()){Error=TEXT("reflected properties unavailable");return false;}
        // Materials is CPF_Transient in this engine: MRProperties deliberately omits it.
        // Keep interfaces separate from metadata so the repair can admit only slot 0's pointer.
        TArray<TSharedPtr<FJsonValue>> Slots;
        for(const FSkeletalMaterial& M:Mesh->Materials)
        {
            TSharedPtr<FJsonObject> S=MakeShareable(new FJsonObject);
            S->SetStringField(TEXT("material"),M.MaterialInterface?M.MaterialInterface->GetPathName():TEXT(""));
            S->SetStringField(TEXT("slot"),M.MaterialSlotName.ToString());
            S->SetStringField(TEXT("imported_slot"),M.ImportedMaterialSlotName.ToString());
            S->SetStringField(TEXT("metadata_sha1"),SlotMetadata(M));
            Slots.Add(MakeShareable(new FJsonValueObject(S)));
        }
        Out->SetArrayField(TEXT("material_slots"),Slots);
        Out->SetStringField(TEXT("invariant_sha1"),D.Finish());
        Out->SetStringField(TEXT("coverage"),HasColors?TEXT("raw/final skeleton and virtual-bone arrays; section flags; fieldwise CPU/import/index/adjacency/GPU skin and RGBA color data; padding excluded; nonempty morph/cloth buffers rejected"):TEXT("raw/final skeleton and virtual-bone arrays; section flags; fieldwise CPU/import/index/adjacency/GPU skin data; padding excluded; nonempty morph/cloth/color GPU buffers rejected"));
        return true;
    }
};
