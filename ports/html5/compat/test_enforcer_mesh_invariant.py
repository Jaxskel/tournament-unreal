"""Host-check the extracted C++ digest/bulk bodies; not a UE Snapshot compile."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from test_weapon_tessellation import compile_run

HEADER = pathlib.Path(__file__).parent / "UT4Html5Compat/Source/UT4Html5Compat/Private/EnforcerMeshInvariant.h"
SRC = HEADER.read_text(encoding="utf-8")


def body_after(signature):
    start = SRC.index(signature)
    opening = SRC.index("{", start)
    depth = 0
    for pos in range(opening, len(SRC)):
        if SRC[pos] == "{": depth += 1
        elif SRC[pos] == "}":
            depth -= 1
            if depth == 0:
                return SRC[start:pos + 1]
    raise AssertionError("unclosed C++ method")


class EnforcerMeshInvariantTests(unittest.TestCase):
    def test_actual_slot_metadata_covers_every_field_except_interface(self):
        slot = body_after("static FString SlotMetadata(")
        compile_run(r'''
#include <cassert>
#include <string>
#include <cstring>
using FString=std::string;using int32=int;
constexpr int MAX_TEXCOORDS=4;
struct Name {FString value="name";FString ToString()const{return value;}};
struct UV {bool bInitialized=false,bOverrideDensities=false;float LocalUVDensities[4]={};};
struct FSkeletalMaterial {Name MaterialSlotName,ImportedMaterialSlotName;
 bool bEnableShadowCasting_DEPRECATED=false,bRecomputeTangent_DEPRECATED=false;UV UVChannelData;int MaterialInterface=1;};
struct FDigest {FString s;void Name(const FString&x){s+=std::to_string(x.size())+":"+x;}
 void Bool(bool x){s+=x?'1':'0';}void Float(float x){s.append(reinterpret_cast<const char*>(&x),sizeof(x));}FString Finish(){return s;}};
BODY
int main(){FSkeletalMaterial original;auto baseline=SlotMetadata(original);
 for(int field=0;field<10;++field){auto m=original;switch(field){
 case 0:m.MaterialSlotName.value="changed";break;case 1:m.ImportedMaterialSlotName.value="changed";break;
 case 2:m.bEnableShadowCasting_DEPRECATED=true;break;case 3:m.bRecomputeTangent_DEPRECATED=true;break;
 case 4:m.UVChannelData.bInitialized=true;break;case 5:m.UVChannelData.bOverrideDensities=true;break;
 default:m.UVChannelData.LocalUVDensities[field-6]=1.0f;break;}
 assert(SlotMetadata(m)!=baseline);}
 auto changed=original;changed.MaterialInterface=2;assert(SlotMetadata(changed)==baseline);
}
'''.replace('BODY', slot))

    def test_extracted_digest_and_bulk_bodies(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("no host C++ compiler available")
        digest = body_after("struct FDigest")
        bulk = body_after("static bool Bulk(")
        shim = r'''#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <cstdio>
using uint8=uint8_t; using uint32=uint32_t; using int32=int32_t;
struct FString:std::string { using std::string::string; const char* operator*()const{return c_str();} };
template<class T> struct TArray:std::vector<T> { using std::vector<T>::vector; int32 Num()const{return int32(this->size());} };
struct FVector { float X=0,Y=0,Z=0; }; struct FQuat { float X=0,Y=0,Z=0,W=1; };
struct FMemory { static void Memcpy(void* a,const void* b,size_t n){std::memcpy(a,b,n);} };
struct FTCHARToUTF8 { std::string S; FTCHARToUTF8(const char* p):S(p){} const char* Get()const{return S.data();} int Length()const{return int(S.size());} };
struct Hex { FString S; FString ToLower()const{return S;} };
static Hex BytesToHex(const uint8*,int){return {"digest"};}
struct FSHA1 { std::vector<uint8> Bytes; void Update(const uint8* p,uint32 n){Bytes.insert(Bytes.end(),p,p+n);} void Final(){} void GetHash(uint8* p){std::memset(p,0,20);} };
struct FUntypedBulkData { std::vector<uint8> Data; int Locks=0,Unlocks=0; int32 GetBulkDataSize()const{return int32(Data.size());} const void* LockReadOnly()const{auto* M=const_cast<FUntypedBulkData*>(this);++M->Locks;return Data.empty()?nullptr:Data.data();} void Unlock()const{++const_cast<FUntypedBulkData*>(this)->Unlocks;} };
'''
        main = r'''
int main(){
  FEnforcerMeshInvariant::FDigest a,b;
  a.U32(0x12345678); b.U32(0x12345679); if(a.Hash.Bytes==b.Hash.Bytes)return 1;
  FEnforcerMeshInvariant::FDigest f,g; f.Float(1.0f); g.Float(2.0f); if(f.Hash.Bytes==g.Hash.Bytes)return 2;
  FEnforcerMeshInvariant::FDigest x,y; TArray<uint32> p{1,2},q{2,1}; x.Array(p); y.Array(q); if(x.Hash.Bytes==y.Hash.Bytes)return 3;
  FUntypedBulkData empty; FEnforcerMeshInvariant::FDigest e; if(!FEnforcerMeshInvariant::Bulk(e,empty)||empty.Locks||empty.Unlocks||e.Hash.Bytes.size()!=4)return 4;
  FUntypedBulkData data; data.Data={4,5,6}; FEnforcerMeshInvariant::FDigest d; if(!FEnforcerMeshInvariant::Bulk(d,data)||data.Locks!=1||data.Unlocks!=1||d.Hash.Bytes.size()!=7)return 5;
  FUntypedBulkData large; large.Data.resize(FEnforcerMeshInvariant::MaxBulkBytes+1); FEnforcerMeshInvariant::FDigest z; if(FEnforcerMeshInvariant::Bulk(z,large)||large.Locks)return 6;
  return 0;
}
'''
        source = shim + "\nstruct FEnforcerMeshInvariant { static constexpr uint32 MaxBulkBytes=64u*1024u*1024u;\n" + digest + ";\n" + bulk + "\n};\n" + main
        with tempfile.TemporaryDirectory(prefix="enforcer-mesh-host-") as td:
            cpp, exe = pathlib.Path(td) / "test.cpp", pathlib.Path(td) / "test"
            cpp.write_text(source)
            built = subprocess.run([compiler, "-std=c++14", str(cpp), "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_snapshot_source_covers_requested_field_groups(self):
        for token in ("GetRawRefBoneInfo()", "GetRawRefBonePose()", "GetRefBoneInfo()", "GetRefBonePose()",
                      "GetRequiredVirtualBones()", "GetVirtualBoneRefData()", "ActiveBoneIndices", "RequiredBones",
                      "TriangleSorting", "bRecomputeTangent", "bCastShadow", "bDisabled", "CorrespondClothSectionIndex",
                      "MaxBoneInfluences", "TangentX.Vector.Packed", "TangentY.Vector.Packed", "TangentZ.Vector.Packed",
                      "GetNumInfluencedVerticesByMorphs()!=0", "APEXClothVertexBuffer.GetNumVertices()!=0",
                      "ColorVertexBuffer.GetNumVertices()!=0", "GetIndexBuffer()->Num()", "GetStride()", "GetUseFullPrecisionUVs()"):
            self.assertIn(token, SRC)

    def test_snapshot_source_prebounds_payloads_and_handles_optional_empty_data(self):
        self.assertIn("uint32(Lod.MultiSizeIndexContainer.GetIndexBuffer()->Num())>MaxIndices", SRC)
        self.assertIn("uint32(Lod.LegacyRawPointIndices.GetBulkDataSize())>MaxBulkBytes", SRC)
        self.assertIn("const bool HasAdj=", SRC)
        self.assertIn("if(!N)return true", SRC)
        self.assertIn("Hash.Update", SRC)

    def test_actual_color_shape_and_digest_preserve_empty_and_all_channels(self):
        shape=body_after("static bool ColorShape(")
        colors=body_after("static bool Colors(")
        compile_run(r'''
#include <cassert>
#include <cstdint>
#include <vector>
using uint32=uint32_t;using uint8=uint8_t;
constexpr uint32 MaxVertices=2000000;
struct FColor{uint8 R=1,G=2,B=3,A=4;};
struct FGPUSkinVertexColor{FColor VertexColor;};
struct FSkeletalMeshVertexColorBuffer{
 uint32 count=2,stride=4;mutable int reads=0;std::vector<FColor>values=std::vector<FColor>(2);
 uint32 GetNumVertices()const{return count;}uint32 GetStride()const{return stride;}
 const FColor&VertexColor(uint32 i)const{++reads;assert(i<values.size());return values[i];}
};
struct FDigest{std::vector<uint32>words;void U32(uint32 x){words.push_back(x);}};
SHAPE
COLORS
int main(){
 FSkeletalMeshVertexColorBuffer b;FDigest d;assert(Colors(d,b,2));assert(b.reads==2);assert(d.words==std::vector<uint32>({2,4,1,2,3,4,1,2,3,4}));
 for(int v=0;v<2;++v)for(int c=0;c<4;++c){auto changed=b;auto&x=changed.values[v];switch(c){case 0:x.R=8;break;case 1:x.G=8;break;case 2:x.B=8;break;case 3:x.A=8;break;}FDigest other;assert(Colors(other,changed,2));assert(other.words!=d.words);}
 for(int bad=0;bad<3;++bad){auto x=b;x.reads=0;if(bad==0)x.count=1;if(bad==1)x.stride=8;if(bad==2)x.count=MaxVertices+1;FDigest fail;assert(!Colors(fail,x,2));assert(x.reads==0&&fail.words.empty());}
 b.count=0;b.stride=0;b.reads=0;FDigest empty;assert(Colors(empty,b,2));assert(empty.words==std::vector<uint32>({0}));assert(b.reads==0);
}
'''.replace('SHAPE',shape).replace('COLORS',colors))

    def test_snapshot_has_no_asset_mutators_or_serialization(self):
        for forbidden in ("->Serialize(", "->MarkPackageDirty(", "->Save(", "->Modify(", "->SetMaterial("):
            self.assertNotIn(forbidden, SRC)


if __name__ == "__main__":
    unittest.main()
