"""Actual control-body tests with fake I/O; native apply/serialization is separate."""
from pathlib import Path
import unittest
from test_weapon_grenade_repair import TYPES, host, method

HEADER = Path(__file__).parent / 'UT4Html5Compat/Source/UT4Html5Compat/Private/EnforcerMaterialRepair.h'


class EnforcerRepairTests(unittest.TestCase):
    def test_actual_file_table_accepts_only_fixed_five_changes(self):
        body = method(HEADER.read_text(), 'bool CheckFiles() const')
        sha = method((HEADER.parent / 'WeaponTessellationUpgrade.h').read_text(), 'static bool WTUSHA1(')
        types = TYPES.replace('FString AsString()const{return s;}', 'FString AsString()const{return s;} bool TryGetString(FString&out)const{if(o)return false;out=s;return true;}')
        host(types + sha + r'''
template<class T>struct Arr:std::vector<T>{using std::vector<T>::vector;int Find(const T&v)const{for(int i=0;i<int(this->size());++i)if((*this)[i]==v)return i;return -1;}};
TMap<FString,FString>disk;bool evidence=true;FString denied;
FString HashFile(const FString&p){auto*v=disk.Find(p);return v?*v:FString();}
bool Physical(const FString&p,bool missing){return p!=denied&&(missing||!HashFile(p).IsEmpty());}
struct FPaths{static bool FileExists(const FString&p){return !HashFile(p).IsEmpty();}};
struct FPackageName{static FString LongPackageNameToFilename(const FString&p,const char*){return p;}static bool DoesPackageExist(const FString&p){return FPaths::FileExists(p);}};
struct Proof{
 TSharedPtr<FJsonObject>Files=WGRObject();TMap<FString,FString>OriginalHashes;Arr<FString>Saves;
 bool Evidence()const{return evidence;}
BODY
};
int main(){Proof p;p.Saves={"/Game/new0","/Game/new1","/Game/new2","/Game/p28","/Game/p29"};
 for(int i=0;i<30;++i){FString k=std::string("/Game/p")+std::to_string(i),h=std::string(40,'a');p.OriginalHashes.Add(k,h);p.Files->SetStringField(k,h);disk.Add(k,h);}
 for(int i=0;i<3;++i)p.Files->SetStringField(p.Saves[i],"");assert(p.CheckFiles());
 for(auto k:p.Saves){disk.Add(k,std::string(40,'b'));p.Files->SetStringField(k,std::string(40,'b'));assert(p.CheckFiles());}
 disk.Add("/Game/p0",std::string(40,'c'));p.Files->SetStringField("/Game/p0",std::string(40,'c'));assert(!p.CheckFiles());
 disk.Add("/Game/p0",std::string(40,'a'));p.Files->SetStringField("/Game/p0",std::string(40,'a'));assert(p.CheckFiles());
 evidence=false;assert(!p.CheckFiles());evidence=true;denied=p.Saves[0];assert(!p.CheckFiles());denied="";
 p.Files->SetStringField("/Game/unknown",std::string(40,'a'));disk.Add("/Game/unknown",std::string(40,'a'));assert(!p.CheckFiles());
 p.Files->Values.v.erase(p.Files->Values.v.begin());assert(!p.CheckFiles());
}
'''.replace('BODY', body))

    def test_actual_consumer_sync_never_adopts_unchecked_disk_hashes(self):
        body = method(HEADER.read_text(), 'bool SyncConsumerMeshes()')
        host(TYPES + r'''
template<class T>struct Arr:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}};
struct IFileManager{static IFileManager&Get(){static IFileManager m;return m;}int FileSize(const char*){return 123;}};
bool filesOK=true,candidateOK=true;
struct Proof {
 Arr<FString>Saves={"new0","new1","new2","mesh1","mesh3"};TSharedPtr<FJsonObject>Files=WGRObject();
 struct C{struct R{Arr<TSharedPtr<FJsonObject>>Rows;}Consumers;bool Check(){return candidateOK;}}Candidate;
 bool CheckFiles(){return filesOK;}
BODY
};
int main(){Proof p;for(int i=0;i<7;++i){auto r=WGRObject();r->SetStringField("package",i==3?"mesh1":i==4?"mesh3":"other");r->SetStringField("file","file");r->SetStringField("sha1","old");p.Candidate.Consumers.Rows.push_back(r);}
 p.Files->SetStringField("mesh1","transaction1");p.Files->SetStringField("mesh3","transaction3");
 filesOK=false;assert(!p.SyncConsumerMeshes());for(auto r:p.Candidate.Consumers.Rows)assert(Str(r,"sha1")=="old");
 filesOK=true;assert(p.SyncConsumerMeshes());for(int i=0;i<7;++i)assert(Str(p.Candidate.Consumers.Rows[i],"sha1")== (i==3?"transaction1":i==4?"transaction3":"old"));
 candidateOK=false;assert(!p.SyncConsumerMeshes());candidateOK=true;
 p.Candidate.Consumers.Rows[3]->SetStringField("package","wrong");assert(!p.SyncConsumerMeshes());
 p.Candidate.Consumers.Rows.pop_back();assert(!p.SyncConsumerMeshes());
}
'''.replace('BODY',body))

    def test_actual_save_loop_all_failure_points_keep_fixed_order(self):
        body = method(HEADER.read_text(), 'bool SaveAll(const FString& BeforeHash)')
        sha = method((HEADER.parent / 'WeaponTessellationUpgrade.h').read_text(), 'static bool WTUSHA1(')
        host(TYPES + sha + r'''
const int RF_Public=1,RF_Standalone=2;
int gate=0,failAt=-1,saves=0;std::vector<FString>order;TMap<FString,FString>disk;
bool ok(){return ++gate!=failAt;}
FString HashFile(const FString&p){return disk.FindChecked(p);}
struct UObject {FString name;UObject*GetOutermost(){return this;}FString GetName(){return name;}void MarkPackageDirty(){}};
bool WGRReady(UObject*p){return p!=nullptr;}
struct UPackage{static bool SavePackage(UObject*,UObject*a,int,const char*p){if(!ok())return false;++saves;order.push_back(a->name);disk.Add(p,std::string(40,char('0'+saves)));return true;}};
struct ProofT {
 std::vector<FString>Saves;FString BeforePath="before";TSharedPtr<FJsonObject>Files=WGRObject();TMap<FString,FString>OriginalHashes;
 struct PolicyT{TMap<FString,FString>Files;bool Check(const FString&){return ok();}}Policy;
 bool External(const FString&,bool){return ok();}
 bool CheckFiles(){for(auto&kv:Files->Values)if(HashFile(kv.Key)!=kv.Value->s)return false;return ok();}
 bool SyncConsumerMeshes(){return CheckFiles();}
};
struct State {ProofT Proof;UObject*Master;UObject*Copies[2];UObject*Meshes[2];
 struct Src{bool Unchanged(){return ok();}}Source;
 bool Equivalent(){return ok();}bool MeshesEqual(bool changed){assert(changed);return ok();}
BODY
};
int main(){int gates=0;
 for(int fault=-1;fault<=140;++fault){gate=0;failAt=fault;saves=0;order.clear();disk={};State s;
 UObject a{"/Game/master"},b{"/Game/one"},c{"/Game/three"},d{"/Game/mesh1"},e{"/Game/mesh3"};
 s.Master=&a;s.Copies[0]=&b;s.Copies[1]=&c;s.Meshes[0]=&d;s.Meshes[1]=&e;s.Proof.Saves={a.name,b.name,c.name,d.name,e.name};
 for(int i=0;i<5;++i){auto p=s.Proof.Saves[i];FString h=i<3?FString():FString(std::string(40,'a'));
  disk.Add(p,h);s.Proof.Files->SetStringField(p,h);s.Proof.Policy.Files.Add(p.ToLower(),p);if(i>=3)s.Proof.OriginalHashes.Add(p,h);}
 disk.Add("before",std::string(40,'b'));bool passed=s.SaveAll(std::string(40,'b'));if(fault==-1)gates=gate;
 assert(passed==(fault<1||fault>gates));assert(saves<=5);for(int i=0;i<saves;++i)assert(order[i]==s.Proof.Saves[i]);
 if(fault>=1&&fault<=gates)assert(gate==fault);else assert(saves==5);
 }
}
'''.replace('BODY', body))

    def test_actual_slot_assignment_requires_all_preconditions_first(self):
        body = method(HEADER.read_text(), 'bool AssignSlots()')
        host(r'''
#include <cassert>
using int32=int;
int gate=0,failAt=-1;bool ok(){return ++gate!=failAt;}
struct Slot{int*MaterialInterface=nullptr;};struct Mesh{Slot Materials[4];};
struct State{Mesh a,b;Mesh*Meshes[2]={&a,&b};int old1=1,old3=3,new1=11,new3=33,other=5;int*Copies[2]={&new1,&new3};
 struct P{bool CheckFiles(){return ok();}}Proof;struct Src{bool Unchanged(){return ok();}}Source;
 bool Equivalent(){return ok();}bool MeshesEqual(bool){return ok();}
BODY
};
int main(){for(int fail=-1;fail<=8;++fail){gate=0;failAt=fail;State s;
 s.a.Materials[0].MaterialInterface=&s.old1;s.b.Materials[0].MaterialInterface=&s.old3;
 for(int i=1;i<4;++i)s.a.Materials[i].MaterialInterface=s.b.Materials[i].MaterialInterface=&s.other;
 bool success=s.AssignSlots();assert(success==(fail<1));
 bool changed=fail<1||fail>4;assert(s.a.Materials[0].MaterialInterface==(changed?&s.new1:&s.old1));
 assert(s.b.Materials[0].MaterialInterface==(changed?&s.new3:&s.old3));
 for(int i=1;i<4;++i)assert(s.a.Materials[i].MaterialInterface==&s.other&&s.b.Materials[i].MaterialInterface==&s.other);
}}
'''.replace('BODY', body))

    def test_actual_mesh_comparison_allows_only_slot_zero_interface(self):
        body = method(HEADER.read_text(), 'bool MeshesEqual(bool Changed) const')
        types = TYPES.replace('struct FJsonObject {',r'''
template<class T>struct Arr:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}};
struct FJsonObject {''').replace('TSharedPtr<FJsonObject>GetObjectField',r'''
 Arr<TSharedPtr<FJsonValue>>GetArrayField(const FString&k)const{Arr<TSharedPtr<FJsonValue>>a;for(auto&v:Values.FindChecked(k)->o->Values)a.push_back(v.Value);return a;}
 TSharedPtr<FJsonObject>GetObjectField''')
        types = types.replace('FString AsString()const{return s;}', 'FString AsString()const{return s;} TSharedPtr<FJsonObject>AsObject()const{return o;}')
        host(types + r'''
struct Material{FString path;FString GetPathName(){return path;}};
struct Slot{Material*MaterialInterface;FString metadata;};
struct Mesh{Arr<Slot>Materials;FString geometry="geometry";FString properties="properties";bool ready=true;};
bool WGRReady(Mesh*p){return p&&p->ready;}
struct FEnforcerMeshInvariant{static bool Snapshot(Mesh*m,TSharedPtr<FJsonObject>&j,FString&){
 j=WGRObject();j->SetStringField("geometry",m->geometry);j->SetStringField("properties",m->properties);
 auto slots=WGRObject();int i=0;for(auto&s:m->Materials){auto row=WGRObject();row->SetStringField("material",s.MaterialInterface->path);row->SetStringField("metadata_sha1",s.metadata);slots->SetObjectField(std::to_string(i++),row);}j->SetObjectField("material_slots",slots);return true;}};
struct State{
 Mesh a,b;Mesh*Meshes[2]={&a,&b};Material old1{"old1"},old3{"old3"},new1{"new1"},new3{"new3"},other{"other"};Material*Copies[2]={&new1,&new3};
 struct P{TSharedPtr<FJsonObject>Baseline[2];}Proof;struct Src{Material*Original[2];}Source;
 State(){Source.Original[0]=&old1;Source.Original[1]=&old3;FString e;for(int i=0;i<2;++i){Meshes[i]->Materials.push_back({Source.Original[i],"slot0"});for(int j=1;j<4;++j)Meshes[i]->Materials.push_back({&other,std::to_string(j)});FEnforcerMeshInvariant::Snapshot(Meshes[i],Proof.Baseline[i],e);}}
BODY
};
int main(){for(int changed=0;changed<2;++changed){
 State s;assert(s.MeshesEqual(false));if(changed){s.a.Materials[0].MaterialInterface=&s.new1;s.b.Materials[0].MaterialInterface=&s.new3;}
 assert(s.MeshesEqual(changed));auto original=s.Proof.Baseline[0]->GetArrayField("material_slots")[0]->AsObject();
 assert(Str(original,"material")=="old1"); // Comparison never edits the pinned baseline.
 for(int mesh=0;mesh<2;++mesh){auto*m=s.Meshes[mesh];m->geometry="mutated";assert(!s.MeshesEqual(changed));m->geometry="geometry";
 m->properties="mutated";assert(!s.MeshesEqual(changed));m->properties="properties";
 for(int slot=0;slot<4;++slot){auto saved=m->Materials[slot];m->Materials[slot].metadata="changed";assert(!s.MeshesEqual(changed));m->Materials[slot]=saved;
 m->Materials[slot].MaterialInterface=slot==0?&s.other:&s.new1;assert(!s.MeshesEqual(changed));m->Materials[slot]=saved;}
 m->ready=false;assert(!s.MeshesEqual(changed));m->ready=true;assert(s.MeshesEqual(changed));}
 }}
'''.replace('BODY',body))

    def test_actual_entry_failure_paths_and_read_only_modes(self):
        entry = method(HEADER.read_text(), 'static int32 EnforcerMaterialRepair(')
        sha = method((HEADER.parent / 'WeaponTessellationUpgrade.h').read_text(), 'static bool WTUSHA1(')
        types = TYPES.replace('#define UE_LOG(...) ((void)0)', r'''
#include <cstring>
bool completed=false;
template<class... T>void logline(const char* fmt,T...){if(std::strstr(fmt," complete "))completed=true;}
#define UE_LOG(category,level,fmt,...) logline(fmt,##__VA_ARGS__)
''')
        host(types + sha + r'''
int calls=0,fault=-1,opens=0,writes=0,assetSaves=0,prepares=0,compiles=0,assigns=0;
bool closed=false,corrupt=false;FString failedTag;TSharedPtr<FJsonObject>savedAfter;
bool ok(const char*t){++calls;if(calls==fault){failedTag=t;return false;}return true;}
bool GIsEditor=true;bool IsInGameThread(){return true;}
struct FApp{static bool CanEverRender(){return true;}};
struct FCommandLine{static const char*Get(){return "";}};
struct FParse{static bool Param(const char*,const char*){return false;}};
int EFRStop(const char*){return 1;}
FString HashFile(const FString&){return std::string(40,'a');}
struct FEnforcerRepairProof {
 FString BeforePath="before",AfterPath="after",PreparationHash="prep",ReceiptHash="receipt";
 TSharedPtr<FJsonObject>Baseline[2]={WGRObject(),WGRObject()},Files=WGRObject();
 bool Read(const FString&,bool){return ok("read");}
 bool External(const FString&,bool){return ok("external");}
 bool CheckFiles(){return ok("files");}
 bool Json(const FString&,TSharedPtr<FJsonObject>&j){if(!ok("readback"))return false;j=savedAfter;if(corrupt)j=WGRObject();return true;}
};
struct FEnforcerRepairState {
 explicit FEnforcerRepairState(FEnforcerRepairProof&){}
 TSharedPtr<FJsonObject>Ids=WGRObject();
 struct Src{TSharedPtr<FJsonObject>Before=WGRObject();bool Unchanged(){return ok("source");}
  bool Close(){if(!ok("drain"))return false;closed=true;return true;}}Source;
 bool Gather(bool){return ok("gather");}
 bool Compile(){++compiles;return ok("compile");}
 bool Equivalent(){return ok("equivalent");}
 bool MeshesEqual(bool){return ok("meshes");}
 bool Prepare(){++prepares;assert(opens==2&&writes==1);return ok("prepare");}
 bool AssignSlots(){++assigns;assert(compiles==1);return ok("assign");}
 bool SaveAll(const FString&){assert(assigns==1&&compiles==1);if(!ok("save"))return false;assetSaves=5;return true;}
};
struct FWGREvidence {
 FString path;
 bool Open(const FString&p){if(!ok("open"))return false;path=p;++opens;return true;}
 bool Write(TSharedPtr<FJsonObject>j){if(!ok("write"))return false;++writes;
  if(path=="after"){assert(closed&&assetSaves==5);savedAfter=j;}return true;}
 bool Close(){return ok("close-evidence");}
};
ENTRY
void reset(){calls=opens=writes=assetSaves=prepares=compiles=assigns=0;closed=completed=false;savedAfter=nullptr;failedTag="";}
int main(){
 for(int mode=0;mode<3;++mode){int total=0;
  for(int fail=-1;fail<=50;++fail){reset();fault=fail;corrupt=false;
   int result=EnforcerMaterialRepair("",mode==1,mode==2);if(fail==-1)total=calls;
   bool success=fail<1||fail>total;assert((result==0)==success);assert(completed==success);
   if(!success)assert(calls==fail);
   if(mode){assert(assetSaves==0&&prepares==0&&assigns==0&&opens==0&&writes==0);assert(compiles==(mode==1&&fail!=1&&fail!=2?1:0));}
   else {assert(assetSaves<=5);if(failedTag=="compile")assert(assetSaves==0&&assigns==0);}
   if(success){assert(closed);if(mode==0)assert(assetSaves==5&&writes==2);}
  }
 }
 reset();fault=-1;corrupt=true;assert(EnforcerMaterialRepair("",false)==1);assert(assetSaves==5&&!completed);
 reset();corrupt=false;assert(EnforcerMaterialRepair("",true,true)==1);assert(calls==0&&opens==0);
}
'''.replace('ENTRY', entry))

    def test_no_alias_or_original_material_write_and_scope_is_separate(self):
        text = HEADER.read_text()
        for forbidden in ('WSAliases', 'SetAlias(', 'SetDirtyFlag', 'ClearDirty', 'ProcessEvent', 'DeleteFile', 'MoveFile'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('UPackage::SavePackage('), 1)
        self.assertEqual(text.count('SetParentEditorOnly('), 1)
        self.assertIn('Copies[I]->SetParentEditorOnly(Master)', text)
        self.assertIn('Meshes[I]->Materials[0].MaterialInterface=Copies[I]', text)
        self.assertIn('Files->Values.Num()!=33', text)
        self.assertIn('OriginalHashes.Num()!=30', text)
        self.assertIn('Policy.Read(Receipt,Preparation,Allowed)', text)
        self.assertIn('enforcer-five-assets-v1', text)
        entry = method(text, 'static int32 EnforcerMaterialRepair(')
        self.assertLess(entry.index('Before.Open('), entry.index('State.Prepare('))
        self.assertLess(entry.index('State.Compile()'), entry.index('State.SaveAll('))
        self.assertLess(entry.rindex('State.Source.Close()'), entry.index('After.Write(A)'))
        verify = entry[entry.index('if(Verify)'):entry.index('FWGREvidence Before,After;')]
        for forbidden in ('SaveAll(', 'Prepare(', 'AssignSlots(', '.Open(', '.Write('):
            self.assertNotIn(forbidden, verify)


if __name__ == '__main__':
    unittest.main()
