"""Extracted production control-body tests. Not an Unreal compile or asset-write test."""
from pathlib import Path
import unittest
from test_weapon_grenade_repair import TYPES, host, method

HEADER = Path(__file__).parent / 'UT4Html5Compat/Source/UT4Html5Compat/Private/SupplementMaterialRepair.h'

class SupplementRepairTests(unittest.TestCase):
    def test_actual_slot_assignment_has_four_preconditions_and_only_four_writes(self):
        text = HEADER.read_text()
        body = method(text, 'bool AssignSlots()')
        slot = method(text, 'static int32 SMRSlot(')
        member = method(text, 'static int32 SMRMember(')
        host(r'''
#include <cassert>
using int32=int;
int gate=0,failAt=-1;bool ok(){return ++gate!=failAt;}
struct Slot{int*MaterialInterface=nullptr;};struct Mesh{Slot Materials[6];};
SLOT
MEMBER
struct State{Mesh owned[4];Mesh*Meshes[4]={&owned[0],&owned[1],&owned[2],&owned[3]};int olds[4]={1,2,3,4},news[4]={11,22,33,44},other=99;int*Copies[4]={&news[0],&news[1],&news[2],&news[3]};
 struct P{bool CheckFiles(){return ok();}}Proof;struct S{bool Unchanged(){return ok();}}Source;
 bool Equivalent(){return ok();}bool MeshesEqual(bool){return ok();}
BODY
};
int main(){for(int fail=-1;fail<=8;++fail){gate=0;failAt=fail;State s;
 for(int m=0;m<4;++m)for(int j=0;j<6;++j)s.owned[m].Materials[j].MaterialInterface=j==SMRSlot(m)?&s.olds[SMRMember(m)]:&s.other;
 const bool success=s.AssignSlots();assert(success==(fail<1));
 for(int m=0;m<4;++m)for(int j=0;j<6;++j){
 const bool changed=fail<1||fail>4;
 assert(s.owned[m].Materials[j].MaterialInterface==(j==SMRSlot(m)?(changed?s.Copies[SMRMember(m)]:&s.olds[SMRMember(m)]):&s.other));}
}}
'''.replace('SLOT',slot).replace('MEMBER',member).replace('BODY',body))

    def test_actual_save_loop_fault_at_every_gate_never_extends_scope_or_rolls_back(self):
        body=method(HEADER.read_text(),'bool SaveAll(const FString& BeforeHash)')
        sha=method((HEADER.parent/'WeaponTessellationUpgrade.h').read_text(),'static bool WTUSHA1(')
        host(TYPES+sha+r'''
const int RF_Public=1,RF_Standalone=2;
int gate=0,failAt=-1,saves=0;std::vector<FString>order;TMap<FString,FString>disk;
bool ok(){return ++gate!=failAt;}
FString HashFile(const FString&p){return disk.FindChecked(p);}
struct UObject{FString name;UObject*GetOutermost(){return this;}FString GetName(){return name;}void MarkPackageDirty(){}};
bool WGRReady(UObject*p){return p!=nullptr;}
struct UPackage{static bool SavePackage(UObject*,UObject*a,int,const char*p){if(!ok())return false;++saves;order.push_back(a->name);disk.Add(p,std::string(40,char('0'+saves)));return true;}};
struct P{
 std::vector<FString>Saves;FString BeforePath="before";TSharedPtr<FJsonObject>Files=WGRObject();TMap<FString,FString>OriginalHashes;
 struct PolicyT{TMap<FString,FString>Files;bool Check(const FString&){return ok();}}Policy;
 bool External(const FString&,bool){return ok();}
 bool CheckFiles(){for(auto&kv:Files->Values)if(HashFile(kv.Key)!=kv.Value->s)return false;return ok();}
};
struct S{P Proof;UObject*Master;UObject*Copies[4];UObject*Meshes[4];struct Src{bool Unchanged(){return ok();}}Source;
 bool Equivalent(){return ok();}bool MeshesEqual(bool changed){assert(changed);return ok();}
BODY
};
int main(){int gates=1;
 for(int fault=-1;fault<=gates+1;++fault){gate=0;failAt=fault;saves=0;order.clear();disk={};S s;UObject a[9];
 for(int i=0;i<9;++i){a[i].name=std::string("/Game/asset")+std::to_string(i);s.Proof.Saves.push_back(a[i].name);
  FString h=i<5?FString():FString(std::string(40,'a'));disk.Add(a[i].name,h);s.Proof.Files->SetStringField(a[i].name,h);s.Proof.Policy.Files.Add(a[i].name.ToLower(),a[i].name);if(i>=5)s.Proof.OriginalHashes.Add(a[i].name,h);}
 s.Master=&a[0];for(int i=0;i<4;++i){s.Copies[i]=&a[i+1];s.Meshes[i]=&a[i+5];}
 disk.Add("before",std::string(40,'b'));bool passed=s.SaveAll(std::string(40,'b'));if(fault==-1)gates=gate;
 assert(passed==(fault<1||fault>gates));assert(saves<=9);for(int i=0;i<saves;++i){assert(order[i]==s.Proof.Saves[i]);assert(HashFile(order[i])!=std::string(40,'a'));}
 if(fault>=1&&fault<=gates)assert(gate==fault);else assert(saves==9);
 }
}
'''.replace('BODY',body))

    def test_actual_mesh_comparison_rejects_geometry_metadata_and_non_target_changes(self):
        text=HEADER.read_text();body=method(text,'bool MeshesEqual(bool Changed) const')
        host(r'''
#include <cassert>
#include <memory>
#include <string>
#include <vector>
#include <map>
using int32=int;using FString=std::string;
#define TEXT(x) x
template<class T>struct TSharedPtr:std::shared_ptr<T>{using std::shared_ptr<T>::shared_ptr;TSharedPtr(std::shared_ptr<T>p):std::shared_ptr<T>(p){}bool IsValid()const{return bool(*this);}};
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;bool IsValidIndex(int i)const{return i>=0&&i<int(this->size());}};
struct FJsonObject;namespace EJson{enum Type{Object,String};}
struct FJsonValue{EJson::Type Type=EJson::Object;TSharedPtr<FJsonObject>o;TSharedPtr<FJsonObject>AsObject(){return o;}};
struct FJsonObject{std::map<std::string,std::string>fields;TArray<TSharedPtr<FJsonValue>>slots;void SetStringField(const char*k,const std::string&v){fields[k]=v;}bool TryGetArrayField(const char*k,const TArray<TSharedPtr<FJsonValue>>*&out){if(std::string(k)!="material_slots")return false;out=&slots;return true;}};
TSharedPtr<FJsonObject> MRValue(TSharedPtr<FJsonObject>o){return o;}
struct FWeaponRepair{bool Same(TSharedPtr<FJsonObject>a,TSharedPtr<FJsonObject>b){if(a->fields!=b->fields||a->slots.size()!=b->slots.size())return false;for(int i=0;i<int(a->slots.size());++i)if(a->slots[i]->o->fields!=b->slots[i]->o->fields)return false;return true;}};
struct Mat{std::string path;std::string GetPathName(){return path;}};
struct Slot{Mat*MaterialInterface;std::string metadata;};struct Mesh{TArray<Slot>Materials;std::string geometry="geometry",properties="properties";bool ready=true;};
struct FEnforcerMeshInvariant{static bool Snapshot(Mesh*m,TSharedPtr<FJsonObject>&out,FString&){if(!m->ready)return false;
 out=std::make_shared<FJsonObject>();out->fields={{"geometry",m->geometry},{"properties",m->properties}};
 for(auto&s:m->Materials){TSharedPtr<FJsonObject>o=std::make_shared<FJsonObject>();o->fields={{"material",s.MaterialInterface->path},{"metadata",s.metadata}};TSharedPtr<FJsonValue>v=std::make_shared<FJsonValue>();v->o=o;out->slots.push_back(v);}return true;}};
SLOT
MEMBER
struct S{Mesh owned[4];Mesh*Meshes[4]={&owned[0],&owned[1],&owned[2],&owned[3]};Mat old[4]={{"old0"},{"old1"},{"old2"},{"old3"}},news[4]={{"new0"},{"new1"},{"new2"},{"new3"}},other{"other"};Mat*Copies[4]={&news[0],&news[1],&news[2],&news[3]};struct Src{Mat*Original[4];}Source;TSharedPtr<FJsonObject>Baseline[4];
 S(){for(int m=0;m<4;++m){Source.Original[m]=&old[m];for(int j=0;j<6;++j)owned[m].Materials.push_back({j==SMRSlot(m)?&old[SMRMember(m)]:&other,std::to_string(j)});FString e;FEnforcerMeshInvariant::Snapshot(&owned[m],Baseline[m],e);}}
BODY
};
int main(){for(bool changed:{false,true}){S s;if(changed)for(int m=0;m<4;++m)s.owned[m].Materials[SMRSlot(m)].MaterialInterface=s.Copies[SMRMember(m)];assert(s.MeshesEqual(changed));
 for(int m=0;m<4;++m){auto&mesh=s.owned[m];mesh.geometry="different";assert(!s.MeshesEqual(changed));mesh.geometry="geometry";mesh.properties="different";assert(!s.MeshesEqual(changed));mesh.properties="properties";
 for(int j=0;j<6;++j){auto original=mesh.Materials[j];mesh.Materials[j].metadata="different";assert(!s.MeshesEqual(changed));mesh.Materials[j]=original;mesh.Materials[j].MaterialInterface=j==SMRSlot(m)?&s.other:&s.news[0];assert(!s.MeshesEqual(changed));mesh.Materials[j]=original;}
 mesh.ready=false;assert(!s.MeshesEqual(changed));mesh.ready=true;assert(s.MeshesEqual(changed));assert(s.Baseline[m]->slots[SMRSlot(m)]->o->fields["material"]==s.old[SMRMember(m)].path);
 }} }
'''.replace('SLOT',method(text,'static int32 SMRSlot(')).replace('MEMBER',method(text,'static int32 SMRMember(')).replace('BODY',body))

    def test_actual_file_gate_separates_originals_immutable_consumers_and_nine_outputs(self):
        body=method(HEADER.read_text(),'bool CheckFiles() const')
        sha=method((HEADER.parent/'WeaponTessellationUpgrade.h').read_text(),'static bool WTUSHA1(')
        types=TYPES.replace('struct FJsonObject;','''
namespace EJson{enum Type{Object,String};}
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}int Find(const T&v)const{for(int i=0;i<Num();++i)if((*this)[i]==v)return i;return -1;}};
struct FJsonObject;''')
        types=types.replace('struct FJsonValue {','struct FJsonValue {EJson::Type Type=EJson::String;TSharedPtr<FJsonObject>AsObject()const{return o;} ')
        types=types.replace('struct FJsonObject {','''struct FJsonObject {
 TArray<TSharedPtr<FJsonValue>>rows;
 bool TryGetArrayField(const char*k,const TArray<TSharedPtr<FJsonValue>>*&out)const{if(std::string(k)!="packages")return false;out=&rows;return true;}
''')
        host(types+sha+r'''
TMap<FString,FString>disk;bool evidence=true;FString denied;
FString Full(const FString&p){return p;}
FString HashFile(const FString&p){auto*v=disk.Find(p);return v?*v:FString();}
struct FPaths{static bool FileExists(const FString&p){return !HashFile(p).IsEmpty();}};
struct FPackageName{static bool DoesPackageExist(const FString&p,void*unused=nullptr,FString*out=nullptr){if(out)*out=p;return FPaths::FileExists(p);}};
struct P{
 TArray<FString>Saves;TSharedPtr<FJsonObject>Inputs=WGRObject(),Files=WGRObject();
 struct PolicyT{TMap<FString,FString>Files;bool Check(const FString&p)const{return p!=denied;}}Policy;
 bool Evidence()const{return evidence;}
BODY
};
int main(){P p;for(int i=0;i<9;++i){FString k=std::string("/Game/out")+std::to_string(i);p.Saves.push_back(k);p.Files->SetStringField(k,i<5?FString():FString(std::string(40,'a')));p.Policy.Files.Add(k.ToLower(),k);}
 for(int i=0;i<17;++i){auto r=WGRObject();FString k=i<4?p.Saves[i+5]:FString(std::string("/Game/source")+std::to_string(i));
  FString o=std::string("original/")+k; r->SetStringField("package",k);r->SetStringField("file",k);r->SetStringField("original_file",o);r->SetStringField("sha1",std::string(40,'a'));
  auto v=MakeShareable(new FJsonValue);v->Type=EJson::Object;v->o=r;p.Inputs->rows.push_back(v);disk.Add(k,std::string(40,'a'));disk.Add(o,std::string(40,'a'));}
 assert(p.CheckFiles());
 for(auto&v:p.Inputs->rows){auto r=v->AsObject();for(auto key:{"file","original_file"}){auto f=Str(r,key);disk.Add(f,std::string(40,'b'));assert(!p.CheckFiles());disk.Add(f,std::string(40,'a'));}}
 for(int i=0;i<9;++i){auto k=p.Saves[i];disk.Add(k,std::string(40,'b'));assert(!p.CheckFiles());p.Files->SetStringField(k,std::string(40,'b'));assert(p.CheckFiles());}
 evidence=false;assert(!p.CheckFiles());evidence=true;denied=p.Saves[8];assert(!p.CheckFiles());denied="";
 p.Files->Values.v[0].Key="unknown";assert(!p.CheckFiles());p.Files->Values.v[0].Key=p.Saves[0];assert(p.CheckFiles());
 p.Files->SetStringField("/Game/unallowed",std::string(40,'a'));assert(!p.CheckFiles());p.Files->Values.v.pop_back();
 p.Inputs->rows.pop_back();assert(!p.CheckFiles());
}
'''.replace('BODY',body))

    def test_strict_evidence_and_full_original_generation_are_retained(self):
        text=HEADER.read_text()
        self.assertIn('432b157e8c42414aca84276370b0d722e4a9e2dc',text)
        self.assertIn('Candidate.Read(Params)',text)
        check=method(text,'bool CheckFiles() const')
        self.assertIn('Rows->Num()!=17',check)
        self.assertIn('HashFile(O).Equals(H',check)
        self.assertIn('Files->Values.Num()!=9',check)
        evidence=method(text,'bool Evidence() const')
        self.assertIn('B->Num()!=4',evidence)
        self.assertIn('!Candidate.Check()',evidence)
        self.assertIn('Seen.Contains(P)',evidence)
        self.assertIn('HashFile(F).Equals(*H',evidence)
        read=method(text,'bool Read(const FString& Params,bool Verify)')
        self.assertIn('Policy.Read(Receipt,Preparation,Allowed)',read)
        self.assertIn('After->TryGetObjectField(TEXT("files")',read)
        self.assertIn('WGRNumber(After,TEXT("saved"),9)',read)
        self.assertIn('FPaths::FileExists(BeforePath)||FPaths::FileExists(AfterPath)',read)

    def test_compile_and_copies_preserve_chains_no_alias_or_original_asset_setter(self):
        text=HEADER.read_text();prepare=method(text,'bool Prepare()');eq=method(text,'bool Equivalent() const')
        self.assertIn('Copies[I-1]',prepare)
        self.assertIn('Copies[I-1]',eq)
        self.assertIn('WGRInstance(Source.Original[I],Source.V1,nullptr)',eq)
        self.assertIn('WGRInstance(Copies[I],Source.V1,nullptr)',eq)
        self.assertNotIn('Source.Original[I]->Set',text)
        self.assertNotIn('Source.V1->Set',text)
        self.assertIn('UpdateFromFunctionResource(false)',prepare)
        compile_body=method(text,'bool Compile()')
        for needle in ('I<4','Count==12','new FWSAOrdinaryResource','R->FinishCompilation()','WSAOrdinaryIDEqual','Samplers<=16','!Source.Unchanged()'):
            self.assertIn(needle,compile_body)

    def test_before_evidence_and_all_checks_precede_only_save_site(self):
        text=HEADER.read_text();entry=method(text,'static int32 SupplementMaterialRepair(')
        self.assertEqual(text.count('UPackage::SavePackage('),1)
        order=['Before.Open(', 'Before.Write(', 'Before.Close()', 'State.Prepare()', 'State.Compile()', 'State.AssignSlots()', 'State.SaveAll(']
        start=entry.index('FWGREvidence Before,After;')
        positions=[entry.index(x,start) for x in order]
        self.assertEqual(positions,sorted(positions))
        before_reserve=entry[:start]
        self.assertIn('if(Verify)',before_reserve)
        self.assertIn('if(Preflight)',before_reserve)
        self.assertNotIn('State.Prepare()',before_reserve)
        self.assertNotIn('State.AssignSlots()',before_reserve)
        self.assertNotIn('SaveAll',before_reserve)

if __name__=='__main__':unittest.main()
