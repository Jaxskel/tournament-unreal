"""Local control/policy regressions; no UE, assets, Windows, or browser execution.

Host fixtures execute extracted production C++ bodies with explicit fake I/O and
engine operations. They do not establish UE ABI, serialization, or shader behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponGrenadeRepair.h'
SPEC = HERE / 'repair.grenade.json'
PRIVATE = None


def method(text, signature):
    start = text.index(signature)
    begin = text.index('{', start)
    depth = 1
    i = begin + 1
    # These selected bodies have no braces in strings or comments.
    while depth:
        depth += (text[i] == '{') - (text[i] == '}')
        i += 1
    return text[start:i]


def host(code):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise unittest.SkipTest('host C++ compiler unavailable')
    with tempfile.TemporaryDirectory(prefix='grenade-repair-test-') as tmp:
        p = Path(tmp)
        (p / 'test.cpp').write_text(code)
        build = subprocess.run([compiler, '-std=c++14', str(p / 'test.cpp'), '-o', str(p / 'test')], capture_output=True, text=True)
        if build.returncode:
            raise AssertionError(build.stderr)
        run = subprocess.run([str(p / 'test')], capture_output=True, text=True)
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)


TYPES = r'''
#include <cassert>
#include <string>
#include <vector>
#include <memory>
#include <algorithm>
#include <cctype>
#define TEXT(x) x
#define UE_LOG(...) ((void)0)
using int32=int; using TCHAR=char;
namespace ESearchCase {enum Type {IgnoreCase};}
struct FString:std::string {
 using std::string::string; FString(){} FString(const std::string&s):std::string(s){}
 const char*operator*()const{return c_str();} int Len()const{return size();} bool IsEmpty()const{return empty();}
 FString ToLower()const{auto s=*this;std::transform(s.begin(),s.end(),s.begin(),[](char c){return std::tolower(c);});return s;}
 bool Equals(const FString&s,ESearchCase::Type)const{return ToLower()==s.ToLower();}
};
template<class T>struct TSharedPtr:std::shared_ptr<T>{using std::shared_ptr<T>::shared_ptr;
 TSharedPtr(){} TSharedPtr(std::shared_ptr<T>p):std::shared_ptr<T>(p){} bool IsValid()const{return bool(*this);}};
template<class T>TSharedPtr<T>MakeShareable(T*p){return TSharedPtr<T>(p);}
template<class K,class V>struct TMap {
 struct Pair{K Key;V Value;};std::vector<Pair> v;
 int Num()const{return v.size();} auto begin()const{return v.begin();}auto end()const{return v.end();}
 const V*Find(const K&k)const{for(auto&p:v)if(p.Key==k)return &p.Value;return nullptr;}
 V*Find(const K&k){for(auto&p:v)if(p.Key==k)return &p.Value;return nullptr;}
 void Add(const K&k,const V&v){auto*p=Find(k);if(p)*p=v;else this->v.push_back({k,v});}
 const V&FindChecked(const K&k)const{auto*p=Find(k);assert(p);return*p;}
};
struct FJsonObject;
struct FJsonValue {FString s;TSharedPtr<FJsonObject>o;FString AsString()const{return s;}};
struct FJsonObject {
 TMap<FString,TSharedPtr<FJsonValue>>Values;
 void SetStringField(const FString&k,const FString&v){auto p=MakeShareable(new FJsonValue);p->s=v;Values.Add(k,p);}
 void SetBoolField(const FString&k,bool v){SetStringField(k,v?"true":"false");}
 void SetNumberField(const FString&k,int v){SetStringField(k,std::to_string(v));}
 void SetObjectField(const FString&k,TSharedPtr<FJsonObject>o){auto p=MakeShareable(new FJsonValue);p->o=o;Values.Add(k,p);}
 TSharedPtr<FJsonObject>GetObjectField(const FString&k)const{return Values.FindChecked(k)->o;}
 bool TryGetStringField(const FString&k,FString&v)const{auto*p=Values.Find(k);if(!p||(*p)->o)return false;v=(*p)->s;return true;}
};
TSharedPtr<FJsonObject>WGRObject(){return MakeShareable(new FJsonObject);}
FString Str(TSharedPtr<FJsonObject>j,const TCHAR*k){auto*p=j->Values.Find(k);return p?(*p)->s:FString();}
FString WGRMaster(){return "/Game/NewMaster";}FString WGRLayer(){return "/Game/NewLayer";}FString WSATarget(){return "/Game/One";}
bool same(TSharedPtr<FJsonObject>a,TSharedPtr<FJsonObject>b){
 if(!a||!b)return a==b;if(a->Values.Num()!=b->Values.Num())return false;
 for(auto&x:a->Values){auto*y=b->Values.Find(x.Key);if(!y||x.Value->s!=(*y)->s||!same(x.Value->o,(*y)->o))return false;}return true;}
auto MRValue(TSharedPtr<FJsonObject>p){return p;}
struct FWeaponRepair {bool Same(TSharedPtr<FJsonObject>a,TSharedPtr<FJsonObject>b)const{return same(a,b);}
 bool Field(TSharedPtr<FJsonObject>a,TSharedPtr<FJsonObject>b,const char*k)const{return same(a->GetObjectField(k),b->GetObjectField(k));}};
'''


class GrenadeRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = HEADER.read_text()
        cls.spec = json.loads(SPEC.read_text())

    def test_frozen_spec_scope_and_hash(self):
        self.assertEqual(hashlib.sha1(SPEC.read_bytes()).hexdigest(), '2cc1070e4cda8af887c5eeefcf957abf1de6ff71')
        self.assertEqual(hashlib.sha256(SPEC.read_bytes()).hexdigest(), '051f1234803959fd2a1dd782b700ac8d3092a228ac908a7c3bfd4111d4b49053')
        s = self.spec
        self.assertEqual(s['save_packages'], [s['new_layer'], s['new_master'], s['one_p']])
        self.assertNotIn(s['three_p'], s['save_packages'])
        self.assertEqual(len(set(s['instances'])), 18)
        self.assertEqual(len(s['before_sha1']), 23)
        self.assertFalse(s['normal_constant_substitution'])
        self.assertFalse(s['runtime_acceptance'])
        for p in (s['new_layer'], s['new_master']):
            self.assertNotIn(p, s['before_sha1'])

    def test_actual_aftermath_table_rejects_each_immutable_drift_and_wrong_scope(self):
        sha = method((HEADER.parent / 'WeaponTessellationUpgrade.h').read_text(), 'static bool WTUSHA1(')
        body = method(self.text, 'bool FinalTable(')
        host(TYPES + sha + 'struct Proof{TSharedPtr<FJsonObject>Expected;\n' + body + r'''};
int main(){Proof p;p.Expected=WGRObject();p.Expected->SetStringField(WSATarget(),std::string(40,'a'));
 for(int i=0;i<22;i++)p.Expected->SetStringField("/Game/Other"+std::to_string(i),std::string(40,'b'));
 auto make=[&](){auto j=WGRObject();for(auto&kv:p.Expected->Values)j->SetStringField(kv.Key,kv.Value->s);
 j->SetStringField(WSATarget(),std::string(40,'c'));j->SetStringField(WGRMaster(),std::string(40,'d'));j->SetStringField(WGRLayer(),std::string(40,'e'));return j;};
 assert(p.FinalTable(make()));assert(!p.FinalTable(nullptr));
 for(int i=0;i<22;i++){auto j=make();j->SetStringField("/Game/Other"+std::to_string(i),std::string(40,'f'));assert(!p.FinalTable(j));}
 for(auto key:{WSATarget(),WGRMaster(),WGRLayer()})for(auto value:{FString(""),FString("123"),FString(std::string(40,'z'))}){
 auto j=make();j->SetStringField(key,value);assert(!p.FinalTable(j));}
 auto j=make();j->SetStringField(WSATarget(),std::string(40,'a'));assert(!p.FinalTable(j));
 j=make();j->SetStringField("/Game/Extra",std::string(40,'f'));assert(!p.FinalTable(j));
 j=make();j->Values.v.pop_back();assert(!p.FinalTable(j));
 j=make();j->Values.v.back().Key="/Game/Substitute";assert(!p.FinalTable(j));
}
''')

    def test_actual_snapshot_comparison_retains_all_semantics_and_local_dirty(self):
        body = method(self.text, 'bool Unchanged(bool Changed) const')
        host(TYPES + r'''
struct State{TSharedPtr<FJsonObject>Before,Now,DirtyBaseline;TSharedPtr<FJsonObject>Snapshot(bool)const{return Now;}
''' + body + r'''};
int main(){
 auto snap=[](){auto s=WGRObject();for(auto k:{"objects","instances","protected_dirty"}){auto x=WGRObject();x->SetStringField("field","same");s->SetObjectField(k,x);}return s;};
 State s;s.Before=snap();s.Now=snap();s.DirtyBaseline=s.Before->GetObjectField("protected_dirty");assert(s.Unchanged(true));
 for(auto k:{"objects","instances","protected_dirty"}){s.Now=snap();s.Now->GetObjectField(k)->SetStringField("field","changed");assert(!s.Unchanged(true));}
 // Fresh process gets a new dirty baseline only: old graph/instance facts still compare.
 s.Now=snap();s.Now->GetObjectField("protected_dirty")->SetStringField("field","fresh-dirty");s.DirtyBaseline=s.Now->GetObjectField("protected_dirty");assert(s.Unchanged(true));
 s.Now=snap();assert(!s.Unchanged(true));s.Before=nullptr;assert(!s.Unchanged(true));
}
''')

    def test_actual_lighting_field_policy_requires_present_empty_and_typed_false(self):
        body = method(self.text, 'static bool WGRLightingFields(')
        host(TYPES + body + r'''
int main(){auto a=WGRObject(),b=WGRObject();a->SetStringField("bUsedWithStaticLighting","True");
 assert(!WGRLightingFields(a,b,true,false)); // Missing is not the captured empty false.
 b->SetObjectField("bUsedWithStaticLighting",WGRObject());assert(!WGRLightingFields(a,b,true,false));
 b->SetStringField("bUsedWithStaticLighting","");assert(WGRLightingFields(a,b,true,false));
 assert(!WGRLightingFields(a,b,false,false));assert(!WGRLightingFields(a,b,true,true));
 for(auto v:{"False","True","0","garbage"}){b->SetStringField("bUsedWithStaticLighting",v);assert(!WGRLightingFields(a,b,true,false));}
 b->SetStringField("bUsedWithStaticLighting","");a->SetStringField("bUsedWithStaticLighting","");assert(!WGRLightingFields(a,b,true,false));
 assert(!WGRLightingFields(nullptr,b,true,false));
}
''')

    def test_actual_save_loop_failures_never_expand_scope_or_continue(self):
        body = method(self.text, 'bool SaveAll(const FString& BeforeHash)')
        sha = method((HEADER.parent / 'WeaponTessellationUpgrade.h').read_text(), 'static bool WTUSHA1(')
        host(TYPES + sha + r'''
const int RF_Public=1,RF_Standalone=2;
int gate=0,failAt=-1,saves=0;std::vector<FString>order;TMap<FString,FString>disk;
bool ok(){return ++gate!=failAt;}
FString HashFile(const FString&p){return disk.FindChecked(p);}
struct UObject {FString name;UObject*GetOutermost(){return this;}FString GetName(){return name;}void MarkPackageDirty(){assert(name==WGRLayer()||name==WGRMaster()||name==WSATarget());}};
struct UPackage {static bool SavePackage(UObject*,UObject*a,int,const char*p){if(!ok())return false;++saves;order.push_back(a->name);disk.Add(p,std::string(40,char('c'+saves)));return true;}};
struct P {std::vector<FString>Saves;FString BeforePath="before";TSharedPtr<FJsonObject>Expected;
 struct PolicyT{TMap<FString,FString>Files;bool Check(const FString&){return ok();}}Policy;
 struct OldT{bool External(const FString&,bool){return ok();}}Old;
 bool Files(TSharedPtr<FJsonObject>j){for(auto&kv:j->Values)if(HashFile(kv.Key)!=kv.Value->s)return false;return ok();}
 bool FinalTable(TSharedPtr<FJsonObject>j){return saves==3&&j->Values.Num()==3;}
};
struct State{P Proof;UObject *NewLayer,*NewMaster,*One;TSharedPtr<FJsonObject>Files;bool Equivalent(){return ok();}bool Unchanged(bool){return ok();}
''' + body + r'''};
int main(){int fullGates=0;
 for(int fault=-1;fault<=80;fault++){
 gate=0;failAt=fault;saves=0;order.clear();disk=TMap<FString,FString>();State s;UObject l{WGRLayer()},m{WGRMaster()},o{WSATarget()};
 s.NewLayer=&l;s.NewMaster=&m;s.One=&o;s.Proof.Saves={l.name,m.name,o.name};s.Files=WGRObject();s.Proof.Expected=WGRObject();
 for(auto p:s.Proof.Saves){s.Proof.Policy.Files.Add(p.ToLower(),p);disk.Add(p, p==WSATarget()?FString(std::string(40,'a')):FString());s.Files->SetStringField(p,disk.FindChecked(p));}
 s.Proof.Expected->SetStringField(WSATarget(),std::string(40,'a'));disk.Add("before",std::string(40,'b'));
 bool passed=s.SaveAll(std::string(40,'b'));if(fault==-1)fullGates=gate;
 assert(passed==(fault<1||fault>fullGates));assert(saves<=3);
 for(int i=0;i<saves;i++)assert(order[i]==s.Proof.Saves[i]);
 if(fault>=1&&fault<=fullGates)assert(gate==fault);else assert(saves==3);
 }
}
''')

    def test_actual_drain_failure_retains_roots_and_stays_failed(self):
        close = method(self.text, 'bool Close()\n    {\n        if (Closed)')
        host(r'''
#include <cassert>
#include <vector>
#define UE_LOG(...) ((void)0)
bool drained=true;int deleted=0,unrooted=0;
bool WSADrain(){return drained;}
struct ResourceType{bool finished=true;~ResourceType(){++deleted;}void FinishCompilation(){}bool IsCompilationFinished(){return finished;}};
struct Object{void RemoveFromRoot(){++unrooted;}};
struct State{bool Closed=false,CloseOK=false;ResourceType*Resource=nullptr;std::vector<Object*>Roots;
''' + close + r'''};
int main(){for(int fault=0;fault<3;fault++){deleted=unrooted=0;drained=fault!=1;Object o;State s;s.Roots={&o};s.Resource=new ResourceType;s.Resource->finished=fault!=2;
 assert(s.Close()==(fault==0));assert(s.Close()==(fault==0));assert(deleted==(fault==0));assert(unrooted==(fault==0));
 if(fault)delete s.Resource;}}
''')

    def test_actual_hold_does_not_adopt_preexisting_roots(self):
        hold = method(self.text, 'void Hold(UObject* O)')
        host(r'''
#include <cassert>
#include <vector>
struct UObject{bool rooted=false;int calls=0;bool IsRooted(){return rooted;}void AddToRoot(){rooted=true;++calls;}};
struct Objects:std::vector<UObject*>{void Add(UObject*o){push_back(o);}};
struct State{Objects Roots;
''' + hold + r'''};
int main(){State s;UObject old,newone;old.rooted=true;s.Hold(nullptr);s.Hold(&old);assert(s.Roots.empty()&&old.calls==0);
s.Hold(&newone);s.Hold(&newone);assert(s.Roots.size()==1&&s.Roots[0]==&newone&&newone.calls==1);}
''')

    def test_actual_top_level_default_and_explicit_apply_order(self):
        body = method(self.text, 'static int32 WeaponGrenadeRepair(')
        host(TYPES + r'''
bool GIsEditor=true;int GShaderCompilingManager=1;bool IsRunningCommandlet(){return true;}bool IsInGameThread(){return true;}
namespace FApp{bool CanEverRender(){return true;}}
int oldProof=0,prepared=0,compiled=0,saved=0,opened=0,written=0,verified=0,closed=0;bool failCompile=false,apply=false,verify=false;
struct FParse{static bool Param(const char*,const char*k){return FString(k)=="GrenadeApply"&&apply;}};
int WGRStop(const char*){return 1;}const char*WGRSpecSHA1="spec";
bool WTUSHA1(const FString&s){return s.size()==40;}FString HashFile(const FString&){return std::string(40,'a');}FString Full(const FString&s){return s;}
struct FWGRProof{FString BeforePath="before",AfterPath="after",PreparationHash="prep",ReceiptHash="receipt";
 struct OldT{bool External(const FString&,bool){return true;}}Old;
 bool Read(const FString&,bool){return true;}auto InitialFiles(){return WGRObject();}bool Files(TSharedPtr<FJsonObject>){return true;}};
struct Object{Object*GetOutermost(){return this;}bool IsDirty(){return false;}};
struct FWGRState {TSharedPtr<FJsonObject>Before,Files,Ids,DirtyBaseline;Object obj,*One=&obj;
 FWGRState(FWGRProof&){Files=WGRObject();Ids=WGRObject();}
 bool Gather(){assert(oldProof==1);return true;}bool CloneAbsent(){return true;}
 auto Snapshot(bool){auto j=WGRObject();j->SetObjectField("protected_dirty",WGRObject());return j;}
 bool TextureContracts(){return true;}bool Unchanged(bool){return true;}bool Equivalent(){return true;}
 bool Close(){++closed;return true;}
 bool Prepare(){assert(opened==2&&written==1&&oldProof==1);++prepared;return true;}
 bool Compile(){assert(prepared==1);++compiled;return !failCompile;}
 bool SaveAll(const FString&){assert(compiled==1&&!failCompile);saved=3;return true;}
};
bool WGRBeforeShape(TSharedPtr<FJsonObject>){return true;}
struct FWGREvidence{bool Open(const FString&){++opened;return true;}bool Write(TSharedPtr<FJsonObject>){++written;return true;}bool Close(){return true;}};
int WeaponTessellationUpgrade(const FString&,bool v){assert(v);++oldProof;return 0;}
int WGRFreshVerify(FWGRProof&,const FString&){++verified;return 0;}
''' + body + r'''
int main(){for(int scenario=0;scenario<5;scenario++){
 oldProof=prepared=compiled=saved=opened=written=verified=closed=0;apply=scenario==1||scenario==2||scenario==4;verify=scenario>=3;failCompile=scenario==2;
 int result=WeaponGrenadeRepair("params",verify);assert(result==((scenario==2||scenario==4)?1:0));
 if(scenario==0){assert(oldProof==1&&opened==0&&prepared==0&&compiled==0&&saved==0&&written==0);}
 if(scenario==1){assert(saved==3&&opened==2&&written==2&&prepared==1&&compiled==1&&closed==1);}
 if(scenario==2){assert(opened==2&&written==1&&saved==0);}
 if(scenario==3){assert(verified==1&&oldProof==0&&saved==0&&opened==0);}
 if(scenario==4){assert(verified==0&&oldProof==0&&saved==0&&opened==0);}
}}
''')

    def test_compile_reads_uniforms_only_after_success_and_all_six_qualities(self):
        compile_body = method(self.text, 'bool Compile()')
        self.assertIn('for (auto* Instance : {One, Three})', compile_body)
        self.assertIn('{EMaterialQualityLevel::Low, EMaterialQualityLevel::Medium, EMaterialQualityLevel::High}', compile_body)
        self.assertIn('Resource = new FWSAOrdinaryResource', compile_body)
        self.assertIn('const bool Valid = MapOK &&', compile_body)
        self.assertLess(compile_body.index('Map->CompiledSuccessfully()'), compile_body.index('GetUniform2DTextureExpressions()'))
        self.assertIn('WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId())', compile_body)
        self.assertIn('MRStatic(Requested.ParameterSet)', compile_body)
        self.assertNotIn('NoStaticLighting', compile_body)

    def test_actual_compile_body_invalid_maps_never_read_arrays_and_ordinary_policy(self):
        body = method(self.text, 'bool Compile()')
        alias = (HEADER.parent / 'WeaponSamplerAliasProbe.h').read_text()
        resource = method(alias, 'class FWSAOrdinaryResource final') + ';'
        host(TYPES + r'''
namespace EMaterialQualityLevel{enum Type{Low,High,Medium};}
namespace ERHIFeatureLevel{enum Type{ES2};}
const int SP_OPENGL_ES2_WEBGL=7;using EMaterialProperty=int;using EShaderFrequency=int;struct FMaterialCompiler{};
int fault=0,created=0,destroyed=0,cached=0,arrays=0,drains=0;
template<class T>struct Arr:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}bool Contains(T x)const{return std::find(this->begin(),this->end(),x)!=this->end();}};
struct FStaticParameterSet{int value=0;};
auto MRStatic(FStaticParameterSet s){auto j=WGRObject();j->SetNumberField("value",s.value);return j;}
struct Mat{int StateId;bool lighting=false;};struct Inst{int value;FString name;Inst*GetOutermost(){return this;}FString GetName(){return name;}void GetStaticParameterValues(FStaticParameterSet&s){s.value=value;}};
struct FMaterialShaderMapId{int BaseMaterialId=0,QualityLevel=0,FeatureLevel=0;FStaticParameterSet ParameterSet;Arr<int>ReferencedFunctions;};
bool WSAOrdinaryIDEqual(const FMaterialShaderMapId&a,const FMaterialShaderMapId&b){return a.BaseMaterialId==b.BaseMaterialId&&a.QualityLevel==b.QualityLevel&&a.ParameterSet.value==b.ParameterSet.value&&a.ReferencedFunctions==b.ReferencedFunctions;}
struct ShaderMap{FMaterialShaderMapId id;bool IsCompilationFinalized(){return fault!=2;}bool CompiledSuccessfully(){return fault!=3;}int GetShaderPlatform(){return fault==4?-1:SP_OPENGL_ES2_WEBGL;}const FMaterialShaderMapId&GetShaderMapId(){return id;}};
struct FMaterialResource{
 Mat*material=nullptr;Inst*instance=nullptr;int quality=0;ShaderMap map;
 FMaterialResource(){++created;}virtual~FMaterialResource(){++destroyed;}
 virtual bool IsPersistent()const{return true;}
 virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty,FMaterialCompiler*,EShaderFrequency,bool)const{return 0;}
 void SetMaterial(Mat*m,int q,bool,int,Inst*i){material=m;instance=i;quality=q;}
 bool IsUsedWithStaticLighting()const{return material->lighting||fault==12;}bool IsSpecialEngineMaterial(){return fault==13;}
 void GetShaderMapId(int,FMaterialShaderMapId&id){id.BaseMaterialId=material->StateId;id.QualityLevel=quality;id.FeatureLevel=0;id.ParameterSet.value=instance->value;id.ReferencedFunctions={202};if(fault==14)id.ParameterSet.value++;if(fault==15)id.ReferencedFunctions.push_back(101);}
 bool CacheShaders(FMaterialShaderMapId id,int,bool persistent){assert(!persistent&&!IsPersistent());++cached;map.id=id;if(fault==5)map.id.BaseMaterialId++;return fault!=1;}
 void FinishCompilation(){}bool IsCompilationFinished(){return fault!=10;}bool HasValidGameThreadShaderMap(){return fault!=6;}
 ShaderMap*GetGameThreadShaderMap(){return fault==7?nullptr:&map;}
 Arr<int>GetCompileErrors(){return Arr<int>(fault==8?1:0);}
 int GetSamplerUsage(){assert(fault==0||fault==9||fault==16);return fault==9?17:16;}
 Arr<int>GetUniform2DTextureExpressions(){++arrays;assert(fault==0||fault==16);return Arr<int>(fault==16?15:14);}
 Arr<int>GetUniformCubeTextureExpressions(){++arrays;assert(fault==0);return {};}
};
bool WSADrain(){++drains;return fault!=11;}
''' + resource + r'''
struct State{Mat master{303},layer{101},newlayer{202};Mat*NewMaster=&master,*Layer=&layer,*NewLayer=&newlayer;
 Inst one{1,"one"},three{2,"three"};Inst*One=&one,*Three=&three;FMaterialResource*Resource=nullptr;TSharedPtr<FJsonObject>Files;
 struct P{bool Files(TSharedPtr<FJsonObject>){return true;}}Proof;
 bool Equivalent(){return true;}bool Unchanged(bool){return true;}
''' + body + r'''};
int main(){for(fault=0;fault<=16;fault++){
 created=destroyed=cached=arrays=drains=0;State s;bool result=s.Compile();assert(result==(fault==0));
 if(fault==0){assert(cached==6&&created==6&&destroyed==6&&arrays==12&&drains==6);}
 else {assert(created==1);if(fault>=12&&fault<=15)assert(cached==0);if(fault!=16)assert(arrays==0);}
 // Failure paths leave the outstanding resource for FWGRState::Close, tested separately.
 if(s.Resource)delete s.Resource;
}}
''')

    def test_clone_ownership_before_updaters_and_exact_comparison_exceptions(self):
        prepare = method(self.text, 'bool Prepare()')
        self.assertLess(prepare.index('WSAOwnedGraph(Master, NewMaster)'), prepare.index('UpdateFromFunctionResource(false)'))
        self.assertLess(prepare.index('WSAOwnedGraph(Layer, NewLayer)'), prepare.index('UpdateFromFunctionResource(false)'))
        self.assertIn('for (const auto& A : WSAliases)', prepare)
        self.assertEqual(prepare.count('SetParentEditorOnly('), 1)
        self.assertIn('One->SetParentEditorOnly(NewMaster)', prepare)
        self.assertIn('Update.AddMaterialInstance(Three)', prepare)
        eq = method(self.text, 'bool Equivalent() const')
        fields = re.findall(r'(?:YP|RP)->SetStringField\(TEXT\("([^"]+)"\)', eq)
        self.assertEqual(fields, ['StateId', 'bUsedWithStaticLighting', 'LightingGuid', 'MaterialFunctionInfos', 'ParameterName'])
        self.assertIn('B[I].Function != (Target ? NewLayer : A[I].Function)', eq)
        self.assertIn('B[I].StateId != (Target ? NewLayer->StateId : A[I].StateId)', eq)
        self.assertIn('Aliased == 6', eq)
        self.assertIn('WSAInterfaces(C)', eq)
        self.assertNotIn('RemoveField', self.text)
        for forbidden in ('ClearDirty', 'SetDirtyFlag', 'DeleteFile', 'MoveFile', 'ExecuteConsoleCommand', 'ProcessEvent', 'GetAllAssets', 'GetAssetsByPath'):
            self.assertNotIn(forbidden, self.text)

    def test_fresh_verify_never_calls_old_verifier_or_writes(self):
        verify = method(self.text, 'static int32 WGRFreshVerify(')
        for forbidden in ('WeaponTessellationUpgrade(', 'SaveAll(', 'SavePackage(', 'DuplicateObject', 'SetParentEditorOnly(', '.Write(', '.Open('):
            self.assertNotIn(forbidden, verify)
        self.assertIn('Proof.FinalTable(*Table)', verify)
        self.assertLess(verify.index('Proof.Files(*Table)'), verify.index('StaticLoadObject('))
        self.assertLess(verify.index('FindPackage('), verify.index('StaticLoadObject('))
        self.assertIn('State.Unchanged(true)', verify)

    def test_separate_authority_and_evidence_are_mandatory(self):
        read = method(self.text, 'bool Read(const FString& Params, bool Verify)')
        self.assertIn('Policy.Read(Receipt, Preparation, Allowed)', read)
        self.assertIn('grenade-defaults-v1', read)
        self.assertIn('BackupHash != Str(Expected, *WSATarget())', read)
        for key in ('candidate_approval', 'asset_flag_false', 'resource_lighting_override', 'reference_ids_equal', 'pair_log', 'asset_flag_log'):
            self.assertIn(key, read)
        self.assertIn('CREATE_NEW', self.text)
        self.assertIn('FlushFileBuffers', self.text)
        self.assertEqual(self.text.count('UPackage::SavePackage('), 1)
        self.assertIn('for (int32 I = 0; I < 3; ++I)', self.text)

    def test_private_current23_tess_beforeimage_and_child(self):
        if PRIVATE is None:
            self.skipTest('pass --private-root work/ut4-html5 for pinned current-generation evidence')
        proof = PRIVATE / 'weapon-repair-run/uv0-current23-proof.json'
        tess = PRIVATE / 'weapon-tess-upgrade/native-apply1/aftermath.json'
        self.assertEqual(hashlib.sha1(proof.read_bytes()).hexdigest(), self.spec['current_proof_sha1'])
        self.assertEqual(hashlib.sha1(tess.read_bytes()).hexdigest(), self.spec['tess_aftermath_sha1'])
        p, t = json.loads(proof.read_text()), json.loads(tess.read_text())
        self.assertEqual(t['package_sha1'], self.spec['before_sha1'])
        self.assertEqual((len(p['original_dependencies']), len(p['artifacts'])), (48, 4))
        old = {r['package']: r['sha1'] for r in p['rows']}
        self.assertEqual([k for k in old if old[k] != t['package_sha1'][k]], [self.spec['source_master']])
        self.assertEqual(old[self.spec['one_p']], 'efff00497f03a94f3d0bcd7661bbcd303daa5218')
        self.assertEqual(old[self.spec['three_p']], 'f745815c17d9ebcc8bb8a8738050f3df6c147a52')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-root', type=Path)
    args, remaining = parser.parse_known_args()
    PRIVATE = args.private_root
    unittest.main(argv=[sys.argv[0]] + remaining)
