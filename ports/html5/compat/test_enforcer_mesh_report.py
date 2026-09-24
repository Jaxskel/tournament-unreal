"""Execute the actual report control flow; native mesh inspection is separately tested in UE."""
from pathlib import Path
import unittest
import test_weapon_fidelity as F
from test_weapon_tessellation import compile_run

HEADER = Path(__file__).parent / 'UT4Html5Compat/Source/UT4Html5Compat/Private/EnforcerMeshReport.h'


class ReportTests(unittest.TestCase):
    def test_actual_report_failures_cannot_emit_completion(self):
        body = F.method(HEADER.read_text(), 'static int32 EnforcerMeshReport(')
        compile_run(r'''
#include <cassert>
#include <string>
#include <memory>
#include <vector>
using int32=int;
#define TEXT(x) x
namespace ESearchCase {enum Type{IgnoreCase};}
struct FString:std::string{
 using std::string::string;FString(){}FString(const std::string&s):std::string(s){}
 const char*operator*()const{return c_str();}bool Equals(const FString&s,ESearchCase::Type)const{return *this==s;}
};
template<class T>struct TSharedPtr:std::shared_ptr<T>{
 using std::shared_ptr<T>::shared_ptr;TSharedPtr(){}TSharedPtr(std::shared_ptr<T>p):std::shared_ptr<T>(p){}
 bool IsValid()const{return bool(*this);}
};
struct FJsonObject{
 int value=1;void SetStringField(const char*,const FString&){}void SetObjectField(const char*,TSharedPtr<FJsonObject>){}
 void SetBoolField(const char*,bool){}void SetNumberField(const char*,int){}
};
TSharedPtr<FJsonObject>WGRObject(){return std::make_shared<FJsonObject>();}
int MRValue(TSharedPtr<FJsonObject>p){return p->value;}
struct FWeaponRepair{bool Same(int a,int b){return a==b;}};
int scenario=0,checks=0,failCheck=0,loads=0,snapshots=0,rows=0,complete=0;
bool GIsEditor=true;bool IsInGameThread(){return true;}
struct FCommandLine{static const char*Get(){return "";}};
struct FParse{
 static bool Param(const char*,const char*){return false;}
 static bool Value(const char*,const char*key,FString&out){out=std::string(key)=="Mode="?"EnforcerMeshReport":"proof";return true;}
};
bool Physical(const FString&,bool){return scenario!=1;}
FString HashFile(const FString&){return scenario==2?"bad":"ac5742ef7b0e2666ecc8b55494a173fba3e5cd21";}
struct FEnforcerCandidatePins{
 struct C{FString Hash="hash";}Consumers;
 bool Read(const FString&){return scenario!=3;}
 bool Check(){return ++checks!=failCheck;}
};
std::vector<FString>ECRRoots(){return {"a","b","c","mesh1","mesh3","d","e"};}
FString ObjectPath(const FString&s){return s;}
struct FPackageName{static bool DoesPackageExist(const FString&s,void*,FString*out){*out=s;return true;}};
struct Array{int Num(){return 4;}};
struct Resource{Array LODModels;};
struct Package{bool dirty=false;bool IsDirty(){return dirty;}};
struct USkeletalMesh{
 Package package;Resource resource;Array Materials;
 int GetClass(){return 1;}static int StaticClass(){return 1;}
 Package*GetOutermost(){return &package;}Resource*GetImportedResource(){return &resource;}
}meshes[2];
template<class T>T*LoadObject(void*,const char*){++loads;return scenario==4?nullptr:&meshes[loads-1];}
bool WGRReady(USkeletalMesh*m){return m!=nullptr;}
struct FEnforcerMeshInvariant{
 static bool Snapshot(USkeletalMesh*m,TSharedPtr<FJsonObject>&out,FString&){
  ++snapshots;out=WGRObject();if(scenario==6&&snapshots==2)out->value=2;
  if(scenario==7&&snapshots==1)m->package.dirty=true;
  return scenario!=5;
 }
};
struct FWGAReport{
 const char*Schema=nullptr;const char*Prefix=nullptr;FString Run;
 bool Emit(const char*kind,TSharedPtr<FJsonObject>){
  if(scenario==8)return false;
  if(std::string(kind)=="complete")++complete;else ++rows;return true;
 }
};
int WFRStop(const char*,const FString& = FString()){return 1;}
BODY
void reset(){checks=loads=snapshots=rows=complete=0;for(auto&m:meshes)m.package.dirty=false;}
int main(){
 scenario=0;failCheck=0;reset();assert(EnforcerMeshReport("")==0);assert(loads==2&&snapshots==4&&rows==2&&complete==1);
 for(scenario=1;scenario<=8;++scenario){reset();assert(EnforcerMeshReport("")==1);assert(complete==0);}
 scenario=0;for(failCheck=1;failCheck<=7;++failCheck){reset();assert(EnforcerMeshReport("")==1);assert(complete==0);}
}
'''.replace('BODY', body))


if __name__ == '__main__':
    unittest.main()
