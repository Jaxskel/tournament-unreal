"""Actual batch control-body host tests. No UE, shader compiler or asset execution."""
import hashlib
import json
from pathlib import Path
import re
import unittest
from test_weapon_tessellation import compile_run

HERE = Path(__file__).resolve().parent
PRIVATE = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private'
HEADER = PRIVATE / 'WeaponShaderBatchProbe.h'
GRENADE = '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher'


class BatchProbe(unittest.TestCase):
    def test_selector_inverse_restores_frozen_54_resource_header(self):
        source = HEADER.read_bytes()
        for name in ('SELECTOR', 'TARGET', 'QUALITY', 'COMPLETION'):
            pattern = (rb' *// GRENADE_BASELINE_' + name.encode() + rb'_BEGIN\n.*?'
                       rb' *// GRENADE_BASELINE_' + name.encode() + rb'_END\n')
            source, count = re.subn(pattern, b'', source, flags=re.S)
            self.assertEqual(count, 1)
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         '9992f071ed8fa47c44ab9cb5035757b7052a482030e3206d36307d01308e15f4')
        recipe = json.loads((HERE / 'repair.weapons.json').read_text())
        self.assertEqual(recipe['instances'].count(GRENADE), 1)
        self.assertEqual(HEADER.read_text().count('TEXT("' + GRENADE + '")'), 1)

    def test_fixed_scope_equals_recipe_instances(self):
        source = (PRIVATE / 'WeaponPreflightReport.h').read_text()
        scope = source.split('static TArray<FString> WRScope()')[1].split('static TArray<FString> WRMeshes()')[0]
        paths = re.findall(r'Paths.Add\(TEXT\("([^"]+)"\)\)', scope)
        master = '/Game/RestrictedAssets/Weapons/Global/Material/M_WeaponsBase'
        self.assertEqual(len(paths), 19)
        self.assertEqual(len(set(paths)), 19)
        recipe = json.loads((HERE / 'repair.weapons.json').read_text())
        self.assertEqual(set(paths) - {master}, set(recipe['instances']))

    def test_cpp_delta_leaves_existing_modes_and_probe_unchanged(self):
        from test_commandlet_mode_admission import without_blueprint_dispatch
        source = without_blueprint_dispatch((PRIVATE / 'UT4Html5Compat.cpp').read_text()).encode()
        include = b'#include "WeaponShaderBatchProbe.h"\n'
        branch = (b'    if (Mode.Equals(TEXT("WeaponShaderBatchProbe"), ESearchCase::IgnoreCase))\n'
                  b'        return WeaponShaderBatchProbe(Params);\n')
        self.assertEqual(source.count(include), 1)
        self.assertEqual(source.count(branch), 1)
        old = source.replace(include, b'').replace(branch, b'')
        self.assertEqual(hashlib.sha256(old).hexdigest(), 'ad5ad6f4e36809e2c941be959ab274a5a6db8a387b6322269f1068cfbeee7277')
        self.assertEqual(hashlib.sha256((PRIVATE / 'WeaponShaderProbe.h').read_bytes()).hexdigest(),
                         'a1f7d50fa9120eea13b6024f8da2188e08bc4aa7caab5013436fb48e34e902a4')
        body = HEADER.read_text()
        for forbidden in ('SavePackage', 'SetParent', 'PostEditChange', 'bUsedWithStaticLighting =', 'SetGameThreadShaderMap'):
            self.assertNotIn(forbidden, body)
        self.assertEqual(body.count('WeaponTessellationUpgrade(Params, true)'), 1)

    def test_actual_entire_batch_control_body(self):
        # Engine types are stubs; the complete new production function is compiled
        # unchanged. This checks control flow, not UE ABI or shader correctness.
        code = r'''
#include <cassert>
#include <string>
#include <vector>
#include <set>
#include <algorithm>
#include <cstdio>
#include <cstdarg>
#include <sstream>
using int32=int;using TCHAR=char;
#define TEXT(x) x
struct FString:std::string {using std::string::string;FString(const std::string&s):std::string(s){} FString(){} const char*operator*()const{return c_str();}};
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}int Remove(const T&x){int n=this->size();this->erase(std::remove(this->begin(),this->end(),x),this->end());return n-this->size();}};
template<class T>struct TSet:std::set<T>{bool Contains(const T&x)const{return this->count(x);}void Add(const T&x){this->insert(x);}};
int scenario=0,checks=0,created=0,destroyed=0,finish=0,cached=0,rows=0,complete=0,verify=0,idCalls=0,prereads=0;
std::set<std::pair<std::string,int>> seen;
std::vector<std::string> logs;
void log(const char*fmt,...){char out[2048];va_list a;va_start(a,fmt);vsnprintf(out,sizeof(out),fmt,a);va_end(a);logs.push_back(out);std::string s=fmt;if(s.find(" result ")!=s.npos)++rows;if(s.find(" complete ")!=s.npos)++complete;}
// Match pinned UE_LOG compound-statement shape, avoiding dangling-else assumptions.
#define UE_LOG(category,verbosity,fmt,...) {log(fmt, ##__VA_ARGS__);}
int WFRStop(const char*,const FString&=FString()){return 1;}
bool GIsEditor=true;bool IsInGameThread(){return true;}namespace FApp{bool CanEverRender(){return true;}}
int WeaponTessellationUpgrade(const FString&,bool readonly){assert(readonly);++verify;return scenario==1;}
struct FParse{static bool Value(const char*,const char*,FString&out){out="proof";return scenario!=2;}
static bool Param(const char*args,const char*flag){std::istringstream s(args);std::string token;while(s>>token)if(token==std::string("-")+flag)return true;return false;}};
FString WTUMaster(){return "clone-master";}FString WRMaster(){return "original-master";}FString ObjectPath(const FString&x){return x;}
FString HashFile(const FString&){return "master-hash";}
struct FWeaponTessProof{struct{FString FindChecked(const FString&){return "file";}}CurrentFiles;
bool Read(const FString&){return scenario!=3;}bool Check(const FString&){++checks;return !(scenario==4||(scenario==23&&checks==2));}};
bool WSPQualityBranches(){return scenario!=5;}
const char* Grenade="GRENADE_PATH";
const char* RecipeTargets[]={RECIPE_TARGETS};
TArray<FString> WRScope(){TArray<FString> p;p.push_back(WRMaster());for(const char*t:RecipeTargets)p.push_back(t);if(scenario==6)p.pop_back();if(scenario==7)p[2]=p[1];if(scenario==25)for(auto&t:p)if(t==Grenade)t="wrong-grenade";return p;}
namespace EMaterialQualityLevel{enum Type{Low,High,Medium,Num};}
namespace ERHIFeatureLevel{enum Type{ES2,SM5};}
const int SP_OPENGL_ES2_WEBGL=9;
struct FStaticParameterSet{int value=41;};
struct UMaterial{bool bUsedWithStaticLighting=true;int StateId=7;}master;
struct UMaterialInstanceConstant{FString path;UMaterial*GetMaterial(){return scenario==8?nullptr:&master;}void GetStaticParameterValues(FStaticParameterSet&o){o.value=41;}}instances[19];
template<class T>T*FindObject(void*,const char*);
template<>UMaterial*FindObject<UMaterial>(void*,const char*){return scenario==9?nullptr:&master;}
template<>UMaterialInstanceConstant*FindObject<UMaterialInstanceConstant>(void*,const char*p){if(created==0)++prereads;int i=0;while(i<18&&std::string(p)!=RecipeTargets[i])++i;assert(i<18||std::string(p)=="wrong-grenade");instances[i].path=p;return &instances[i];}
struct Deps{int n=10;int Num()const{return n;}};
struct FMaterialShaderMapId{int BaseMaterialId=7,QualityLevel=0,FeatureLevel=0;FStaticParameterSet ParameterSet;Deps ShaderTypeDependencies,ShaderPipelineTypeDependencies,VertexFactoryTypeDependencies;};
int MRStatic(const FStaticParameterSet&x){return x.value;}int MRValue(int x){return x;}
struct FWeaponRepair{bool Same(int a,int b){return a==b;}};
struct MapType{FMaterialShaderMapId id;bool IsCompilationFinalized(){return scenario!=16;}bool CompiledSuccessfully(){return scenario!=17;}int GetShaderPlatform(){return scenario==18?0:9;}const FMaterialShaderMapId&GetShaderMapId(){return id;}};
bool WSPMaterialInstanceIdentitySubset(const FMaterialShaderMapId&,const FMaterialShaderMapId&){return scenario!=19;}
const char*WSPOrigin(int,bool){return "stub-origin";}FString WFRContext(const FString&x){return x;}
namespace FMath{int Min(int a,int b){return std::min(a,b);}}
struct FWeaponShaderResource{
bool NoStaticLighting=false,done=true;int TranslationRequests=0,q=0;FString target;MapType map;TArray<FString> errors;
void SetMaterial(UMaterial*m,EMaterialQualityLevel::Type quality,bool enabled,ERHIFeatureLevel::Type feature,UMaterialInstanceConstant*mi){assert(m==&master&&enabled&&feature==0);q=quality;target=mi->path;}
bool IsSpecialEngineMaterial(){return scenario==10;}
void GetShaderMapId(int platform,FMaterialShaderMapId&o){assert(platform==9);++idCalls;o.QualityLevel=q;if(NoStaticLighting){o.ShaderTypeDependencies.n=scenario==11?10:9;if(scenario==12)o.ParameterSet.value=99;}}
bool CacheShaders(const FMaterialShaderMapId&id,int platform,bool apply){assert(NoStaticLighting&&platform==9&&!apply);assert(verify==1&&checks==1&&prereads==19);assert(id.ParameterSet.value==41);assert(seen.insert({target,q}).second);map.id=id;++cached;++TranslationRequests;done=false;if(scenario==20)errors.push_back("compile error");return scenario!=13;}
bool IsCompilationFinished(){return done;}void FinishCompilation(){++finish;if(scenario!=14)done=true;}
MapType*GetGameThreadShaderMap(){return scenario==15?nullptr:&map;}
const TArray<FString>&GetCompileErrors(){return errors;}bool HasValidGameThreadShaderMap(){return true;}
int GetFeatureLevel(){return 0;}int GetQualityLevel(){return q;}int GetSamplerUsage(){return scenario==21?17:(scenario==22?-1:16);}
};
struct FWeaponShaderOwner{FWeaponShaderResource*Resource;FWeaponShaderOwner():Resource(new FWeaponShaderResource){++created;}~FWeaponShaderOwner(){Resource->FinishCompilation();if(Resource->IsCompilationFinished()){delete Resource;++destroyed;}else delete Resource;/* host fixture only: production retains */}};
BODY
int main(){
for(bool selected:{false,true})for(scenario=0;scenario<=(selected?25:24);scenario++){
checks=created=destroyed=finish=cached=rows=complete=verify=idCalls=prereads=0;seen.clear();logs.clear();master.bUsedWithStaticLighting=scenario!=24;
int result=WeaponShaderBatchProbe(selected?"-WeaponShaderGrenade1PHigh -WeaponUV0 -WeaponTess1":"fixed");
const int expected=selected?1:54;
assert((result==0)==(scenario==0));assert(verify==1);
if(scenario==0){assert(created==expected&&destroyed==expected&&cached==expected&&rows==expected&&complete==1&&checks==2&&idCalls==2*expected&&seen.size()==expected);assert(logs.back().find("ordinaryAcceptance=0")!=std::string::npos);}
if(scenario>=13&&scenario<=22&&scenario!=14){assert(cached==expected&&rows==expected&&complete==1&&destroyed==expected);assert(logs.back().find("valid=0")!=std::string::npos);}
if(scenario==14){assert(cached==1&&destroyed==0&&rows==0&&complete==0&&finish==2);}
if(scenario==23){assert(cached==expected&&destroyed==expected&&checks==2&&complete==0);}
if(scenario>=1&&scenario<=12){assert(cached==0&&complete==0);}
if(scenario>=24){assert(created==0&&complete==0);}
if(selected&&cached){assert(seen.size()==1&&seen.count({Grenade,EMaterialQualityLevel::High})==1);}
if(complete){assert(logs.back().find(selected?"COMPAT_WEAPON_SHADER_BATCH_DIAGNOSTIC complete selector=grenade1p-high":"COMPAT_WEAPON_SHADER_BATCH complete")!=std::string::npos);if(selected){assert(logs.back().find("resources=1 ")!=std::string::npos);assert(logs.back().find("staticLighting=0 persistent=0 assetsSaved=0 ordinaryAcceptance=0")!=std::string::npos);}}
if(cached&&scenario!=14)assert(finish==2*expected);
assert(master.bUsedWithStaticLighting==(scenario!=24));
}
scenario=0;
for(const char*args:{"-WeaponShaderGrenade1PHighExtra","WeaponShaderGrenade1PHigh","-Other=WeaponShaderGrenade1PHigh"}){
checks=created=destroyed=finish=cached=rows=complete=verify=idCalls=prereads=0;seen.clear();logs.clear();
assert(WeaponShaderBatchProbe(args)==0);assert(cached==54&&rows==54&&complete==1);
assert(logs.back().find("COMPAT_WEAPON_SHADER_BATCH complete")!=std::string::npos);
}
}
'''
        recipe = json.loads((HERE / 'repair.weapons.json').read_text())
        code = code.replace('GRENADE_PATH', GRENADE).replace('RECIPE_TARGETS', ','.join(json.dumps(x) for x in recipe['instances']))
        compile_run(code.replace('BODY', HEADER.read_text()).replace('const FString&=FString()', 'const FString& = FString()'))


if __name__ == '__main__':
    unittest.main()
