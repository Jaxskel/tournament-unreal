"""Bounded host control/lifetime tests, not UE compilation or shader equivalence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from test_weapon_tessellation import compile_run

HERE = Path(__file__).resolve().parent
PRIVATE = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private'
HEADER = PRIVATE / 'WeaponSamplerAliasProbe.h'
PRIVATE_GRAPH = None


def block(name):
    match = re.search(r'// ALIAS_' + name + r'_BEGIN\n(.*?)\s*// ALIAS_' + name + r'_END', HEADER.read_text(), re.S)
    if not match:
        raise AssertionError(name)
    return match.group(1)


class SamplerAlias(unittest.TestCase):
    def test_existing_probes_unchanged_and_owned_scope(self):
        pins = {
            'WeaponShaderProbe.h': 'a1f7d50fa9120eea13b6024f8da2188e08bc4aa7caab5013436fb48e34e902a4',
            'WeaponShaderBatchProbe.h': 'fe098c186505f708d130145b677203a863aa07fed2477110d475da7e52b5420c',
        }
        for name, digest in pins.items():
            self.assertEqual(hashlib.sha256((PRIVATE / name).read_bytes()).hexdigest(), digest)
        # Source integration is main-owned and intentionally outside this pair.
        s = HEADER.read_text()
        for forbidden in ('SavePackage(', 'SetDirtyFlag(', 'ClearDirty', 'PostEditChange(', 'SetParentInternal(',
                          'RebuildMaterialFunctionInfo(', 'SetGameThreadShaderMap(', 'SetTextureParameterValue'):
            self.assertNotIn(forbidden, s)
        self.assertNotRegex(s, r'->Parent\s*=(?!=)')
        self.assertEqual(s.count('CloneMI->SetParentEditorOnly(CloneMaster)'), 1)
        self.assertIn('SP_OPENGL_ES2_WEBGL', s)
        self.assertIn('priorCapturedBaseline2D=20', s)
        self.assertIn('pairedBaselineMeasured=0', s)
        self.assertIn('incidentalDDCSaves=possible', s)
        self.assertIn('ordinaryAcceptance=0', s)
        self.assertNotIn('#include', s)

    def test_exact_six_alias_recipe(self):
        rows = re.findall(r'\{TEXT\("(MaterialExpressionTextureObjectParameter_\d+)"\), TEXT\("([^"]+)"\), TEXT\("([^"]+)"\), TEXT\("([0-9A-F]+)"\)\}', HEADER.read_text())
        self.assertEqual(len(rows), 6)
        self.assertEqual([r[0].split('_')[-1] for r in rows], ['17', '26', '29', '19', '28', '31'])
        self.assertEqual([r[1] for r in rows], ['e R Layer Normal', 'e G Layer Normal', 'e B Layer Normal', 'aa R Layer D', 'aa G Layer D', 'aa B Layer D'])
        self.assertEqual([r[2] for r in rows], ['e Base Layer Normal'] * 3 + ['aa Base Layer D'] * 3)
        self.assertEqual(len({r[3] for r in rows}), 6)
        s = HEADER.read_text()
        self.assertEqual(s.count('TEXT("/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher")'), 1)
        self.assertIn('Textures.Num() == 14 && Cubes.Num() == 0', s)

    def test_actual_control_body_all_admission_and_failure_stages(self):
        # Actual production function, unchanged; dependencies are explicit host stubs.
        # Does not emulate UE duplication, reflection, linking, DDC or compilation.
        code = r'''
#include <cassert>
#include <string>
#include <vector>
#include <algorithm>
using TCHAR=char; using int32=int;
#define TEXT(x) x
struct FString:std::string{using std::string::string; FString(){} FString(const std::string&s):std::string(s){} const char*operator*()const{return c_str();}bool Equals(const FString&s,int)const{return *this==s;}};
namespace ESearchCase{int IgnoreCase=0;}
int scenario=0,verify=0,drains=0,captured=0,prepared=0,compiled=0,closed=0,complete=0;
bool GIsEditor=true;void*GShaderCompilingManager=(void*)1;
bool IsRunningCommandlet(){return scenario!=2;}bool IsInGameThread(){return scenario!=3;}
namespace FApp{bool CanEverRender(){return scenario!=4;}}
struct FParse{static bool Value(const char*,const char*key,FString&out){bool mode=std::string(key)=="Mode=";out=mode?(scenario==6?"WeaponRepairApply":"WeaponSamplerAliasProbe"):"proof";return scenario!=(mode?5:9);}};
int WFRStop(const char*){return 1;}
int WeaponTessellationUpgrade(const FString&,bool v){assert(v);++verify;return scenario==8;}
bool WSPQualityBranches(){return scenario!=11;}FString WTUMaster(){return "fixed-master";}FString HashFile(const FString&){return "hash";}
struct Map{FString value="masterfile";const FString*Find(const FString&){return scenario==12?nullptr:&value;}};
struct FWeaponTessProof{Map CurrentFiles;bool Read(const FString&){return scenario!=10;}bool Check(const FString&){return scenario!=13;}};
bool WSADrain(){++drains;return scenario!=14;}
struct FWSAliasState{bool done=false,Attempted=false;FWSAliasState(FWeaponTessProof&,const FString&){}~FWSAliasState(){if(!done)Close();}
 bool Capture(){++captured;return scenario!=15;}bool Prepare(){++prepared;return scenario!=16;}bool Compile(){++compiled;Attempted=scenario!=19;return scenario!=17&&scenario!=19;}
 bool Close(){assert(!done);done=true;++closed;return scenario!=18;}};
void log(const char*,...){++complete;}
#define UE_LOG(c,v,fmt,...) {log(fmt, ##__VA_ARGS__);}
'''+block('CONTROL')+r'''
int main(){for(scenario=0;scenario<=19;++scenario){verify=drains=captured=prepared=compiled=closed=complete=0;
 GIsEditor=scenario!=1;GShaderCompilingManager=scenario==7?nullptr:(void*)1;
 int result=WeaponSamplerAliasProbe("fixed");assert(result==(scenario?1:0));
 assert(verify==(scenario==0||scenario>=8));
 assert(captured==(scenario==0||scenario>=15));assert(prepared==(scenario==0||scenario>=16));
 assert(compiled==(scenario==0||scenario>=17));assert(closed==(scenario==0||scenario>=15));
 assert(complete==(scenario==0||scenario==17));}}
'''
        compile_run(code)

    def test_actual_lighting_guid_policy_is_narrow_and_pins_duplication(self):
        code = r'''
#include <cassert>
#include <string>
#include <map>
#include <memory>
using TCHAR=char;
#define TEXT(x) x
const int RF_Transient=1;
struct FString:std::string{using std::string::string;FString(){}FString(const std::string&s):std::string(s){}bool IsEmpty()const{return empty();}};
struct FGuid{int n=0;bool IsValid()const{return n!=0;}bool operator==(const FGuid&b)const{return n==b.n;}bool operator!=(const FGuid&b)const{return n!=b.n;}};
struct Class{FString path;FString GetPathName(){return path;}};
struct FJsonObject{std::map<FString,FString> fields;bool TryGetStringField(const char*k,FString&v){auto i=fields.find(k);if(i==fields.end())return false;v=i->second;return true;}
 void SetStringField(const char*k,const FString&v){fields[k]=v;}};
template<class T>using TSharedPtr=std::shared_ptr<T>;
struct UMaterialInterface{Class*cls=nullptr;void*outer=nullptr;bool transient=true;FGuid guid;FJsonObject props;
 Class*GetClass(){return cls;}void*GetOuter(){return outer;}bool HasAnyFlags(int){return transient;}FGuid GetLightingGuid(){return guid;}};
int transientPackage,otherPackage;void*GetTransientPackage(){return &transientPackage;}
TSharedPtr<FJsonObject> MRProperties(UMaterialInterface*o,bool all){assert(all);return std::make_shared<FJsonObject>(o->props);}
bool WSAField(TSharedPtr<FJsonObject> p,const char*k,const FString&v){FString got;return p&&p->TryGetStringField(k,got)&&got==v;}
'''+block('LIGHTING_POLICY')+r'''
int main(){for(int s=0;s<=28;++s){Class cls,other;cls.path=s==1?"/Script/Engine.MaterialInstanceConstant":"/Script/Engine.Material";other.path=cls.path;
 UMaterialInterface source,clone;source.cls=&cls;clone.cls=&cls;source.outer=&otherPackage;clone.outer=&transientPackage;
 source.guid.n=11;clone.guid.n=22;source.props.fields={{"LightingGuid","old"},{"other","unchanged"}};clone.props.fields={{"LightingGuid","new"},{"other","unchanged"}};
 if(s==5)clone.cls=&other;if(s==6)cls.path="/Script/Engine.MaterialFunction";if(s==7)clone.transient=false;if(s==8)clone.outer=&otherPackage;
 if(s==9)source.guid.n=0;if(s==10)clone.guid.n=0;if(s==11)clone.guid=source.guid;
 if(s==12)source.props.fields.erase("LightingGuid");if(s==13)clone.props.fields.erase("LightingGuid");
 if(s==14)source.props.fields["LightingGuid"]="";if(s==15)clone.props.fields["LightingGuid"]="";if(s==16)clone.props.fields["LightingGuid"]="old";
 FWSALightingPolicy p;bool captured=false;
 if(s!=25)captured=p.Capture(s==2?nullptr:&source,s==3?nullptr:s==4?&source:&clone);
 assert(captured==(s<2||s>=17&&s!=25));
 if(s==24)assert(!p.Capture(&source,&clone));
 if(s==17)clone.guid.n=33;if(s==18)source.guid.n=33;
 auto a=MRProperties(&source,true),b=MRProperties(&clone,true);
 if(s==19)a->fields["LightingGuid"]="other-old";if(s==20)b->fields["LightingGuid"]="other-new";
 if(s==21)clone.outer=&otherPackage;if(s==22)clone.transient=false;if(s==23)b->fields["other"]="changed";
 if(s==26)b->fields.erase("LightingGuid");if(s==27)p.ExpectedId.n=0;if(s==28)p.ExpectedId.n=44;
 auto beforeSource=source.props.fields,beforeClone=clone.props.fields;FGuid sourceId=source.guid,cloneId=clone.guid;
 bool ok=p.Normalize(a,b);assert(ok==(s<2||s==23||s==24));
 assert(source.props.fields==beforeSource&&clone.props.fields==beforeClone&&source.guid==sourceId&&clone.guid==cloneId);
 if(ok){assert(b->fields["LightingGuid"]=="old");assert((a->fields==b->fields)==(s!=23));}
 }}
'''
        compile_run(code)
        source = HEADER.read_text()
        prepare = source[source.index('    bool Prepare()'):source.index('    bool Equivalent()')]
        self.assertIn('CloneMaster = Duplicate(Master, TEXT("UT4SamplerAliasMaster"));\n        if (!CloneMaster || !MasterLighting.Capture(Master, CloneMaster))', prepare)
        self.assertIn('CloneMI = Duplicate(MI, TEXT("UT4SamplerAliasMIC"));\n        if (!CloneMI || !MILighting.Capture(MI, CloneMI))', prepare)
        self.assertIn('if (I == 0 && !MasterLighting.Normalize(XP, YP))', source)
        self.assertIn('if (I == 2 && !MILighting.Normalize(XP, YP))', source)
        unchanged = source[source.index('    bool Unchanged()'):source.index('    bool Contracts(')]
        self.assertNotIn('Normalize', unchanged)
        self.assertNotIn('LightingGuid', unchanged)

    def test_actual_close_drain_root_retention_and_idempotence(self):
        code = r'''
#include <cassert>
#include <vector>
#include <string>
using TCHAR=char;using FString=std::string;
#define TEXT(x) x
#define UE_LOG(...) {}
std::vector<int> events;bool globalOK=true,resourceOK=true,snapshotOK=true,proofOK=true;
bool WSADrain(){events.push_back(1);return globalOK;}
struct R{void FinishCompilation(){events.push_back(2);}bool IsCompilationFinished(){return resourceOK;}~R(){events.push_back(3);}};
struct O{void RemoveFromRoot(){events.push_back(6);}};
struct P{bool Check(const FString&){events.push_back(5);return proofOK;}};
struct State{bool Closed=false,FinalOK=false,Captured=true;R*Resource=new R;std::vector<O*>Roots;P Proof;FString MasterHash;
 bool Unchanged(){events.push_back(4);return snapshotOK;}
'''+block('LIFETIME')+r'''
};
int main(){for(int scenario=0;scenario<6;++scenario){events.clear();globalOK=scenario!=1;resourceOK=scenario!=2;snapshotOK=scenario!=3;proofOK=scenario!=4;
 O a,b;State s;s.Roots={&a,&b};if(scenario==5){delete s.Resource;s.Resource=nullptr;s.Captured=false;events.clear();}
 bool ok=s.Close();assert(ok==(scenario==0||scenario==5));auto first=events;assert(s.Close()==ok&&events==first);
 if(scenario==1||scenario==2){assert((events==std::vector<int>{1,2}));assert(s.Resource);delete s.Resource;}
 else{assert(!s.Resource);assert(events.back()==6);assert(events[0]==1);if(scenario!=5){assert(events[1]==2&&events[2]==3&&events[3]==4);}}}}
'''
        compile_run(code)

    def test_actual_name_writer_exact_type_owner_and_property_guards(self):
        code = r'''
#include <cassert>
#include <string>
#include <map>
#include <memory>
using TCHAR=char;
#define TEXT(x) x
const int RF_Transient=1,CPF_Transient=1;
using FString=std::string;
int scenario=0,writes=0;void*writeTarget=nullptr;
struct FName:std::string{using std::string::string;FName(){}FName(const FName&)=default;FName&operator=(const FName&b){if(this==writeTarget)++writes;std::string::operator=(b);return *this;}};
struct Class{FString path;FString GetPathName(){return path;}};
struct UObject{FString name;UObject*outer=nullptr;bool transient=true;Class cls;
 FString GetName(){return name;}UObject*GetOuter(){return outer;}bool HasAnyFlags(int){return transient;}Class*GetClass(){return &cls;}};
struct UMaterialExpression:UObject{FName value;};
UObject transientPackage,otherPackage;UObject*GetTransientPackage(){return &transientPackage;}
struct UProperty{int ArrayDim=1;Class cls;bool transient=false;Class*GetClass(){return &cls;}bool HasAnyPropertyFlags(int){return transient;}
 template<class T>T*ContainerPtrToValuePtr(UMaterialExpression*e){static FName bad("bad");return scenario==15?nullptr:static_cast<T*>(scenario==16?&bad:&e->value);}} property;
template<class T>T*FindField(Class*,const char*k){assert(FString(k)=="ParameterName");return scenario==9?nullptr:&property;}
struct J{std::map<FString,FString> values;void SetStringField(const char*k,const FString&v){values[k]=v;}};
using JP=std::shared_ptr<J>;
JP MRProperties(UMaterialExpression*e,bool all){assert(all);auto p=std::make_shared<J>();p->values={{"ParameterName",e->value},{"ExpressionGUID",scenario==14?"bad":"guid"},{"unrelated",writes&&scenario==17?"changed":"same"}};
 if(writes&&scenario==18)p->values["ParameterName"]="bad-export";return p;}
bool WSAField(JP p,const char*k,const FString&v){auto i=p->values.find(k);return i!=p->values.end()&&i->second==v;}
JP MRValue(JP p){return p;}struct FWeaponRepair{bool Same(JP a,JP b){return a->values==b->values;}};
struct FWSAlias{const char*Node,*OldName,*NewName,*Guid;};
'''+block('NAME_WRITE')+r'''
int main(){for(scenario=0;scenario<=18;++scenario){writes=0;writeTarget=nullptr;
 UObject owner;owner.name=scenario==6?"other":"UT4SamplerAliasLayer";owner.outer=scenario==7?&otherPackage:&transientPackage;owner.transient=scenario!=8;
 UMaterialExpression e;e.name=scenario==2?"other":"node";e.outer=scenario==5?nullptr:&owner;e.transient=scenario!=4;
 e.cls.path=scenario==3?"wrong":"/Script/Engine.MaterialExpressionTextureObjectParameter";e.value=FName(scenario==13?"wrong":"old");
 property.ArrayDim=scenario==10?2:1;property.cls.path=scenario==11?"StringProperty":"/Script/CoreUObject.NameProperty";property.transient=scenario==12;
 writeTarget=&e.value;FWSAlias a={"node","old","new","guid"};bool ok=WSASetName(scenario==1?nullptr:&e,a);
 assert(ok==(scenario==0));assert(writes==((scenario==0||scenario==17||scenario==18)?1:0));
 if(!writes)assert(e.value==(scenario==13?"wrong":"old"));}}
'''
        compile_run(code)

    def test_clone_and_sampler_gate_order(self):
        s = HEADER.read_text()
        prepare = s[s.index('    bool Prepare()'):s.index('    bool Equivalent()')]
        self.assertLess(prepare.index('FindObject<UObject>(GetTransientPackage(), N)'), prepare.index('CloneLayer = Duplicate'))
        admission = 'if (!WSAOwnedGraph(Master, CloneMaster) || !WSAOwnedGraph(Layer, CloneLayer)) return false;'
        self.assertLess(prepare.index(admission), prepare.index('for (UObject* O :'))
        self.assertEqual(prepare.count(admission), 2)  # Complete pass before loop, then again before setters.
        self.assertLess(prepare.rindex(admission), prepare.index('SetMaterialFunction('))
        self.assertLess(prepare.index('WSAOwnedGraph(Master, CloneMaster, Layer, CloneLayer)'), prepare.index('SetParentEditorOnly'))
        self.assertIn('SetMaterialFunction(nullptr, Layer, CloneLayer) || !WSAInterfaces(Call)', prepare)
        self.assertLess(prepare.index('UpdateFromFunctionResource(false)'), prepare.index('SetParentEditorOnly'))
        self.assertLess(prepare.index('Info.StateId = LayerId'), prepare.index('SetParentEditorOnly'))
        self.assertIn('return WSADrain() && Equivalent() && Unchanged()', prepare)
        compile_body = s[s.index('    bool Compile()'):s.index('// ALIAS_CONTROL_BEGIN')]
        self.assertLess(compile_body.index('Contracts(MI, Layer)'), compile_body.index('CacheShaders('))
        self.assertLess(compile_body.index('if (!Valid) return false'), compile_body.index('GetUniform2DTextureExpressions'))
        self.assertIn('WSPMaterialInstanceIdentitySubset', compile_body)
        self.assertIn('!Requested.ReferencedFunctions.Contains(LayerId)', compile_body)
        self.assertIn('Requested.ReferencedFunctions.Contains(Layer->StateId)', compile_body)

    def test_cp3_exact_inverse_to_frozen_cp2(self):
        s = HEADER.read_text()
        s = re.sub(r'// ALIAS_OWNERSHIP_BEGIN\n.*?// ALIAS_OWNERSHIP_END\n\n', '', s, count=1, flags=re.S)
        for args in ('Master, CloneMaster', 'Master, CloneMaster, Layer, CloneLayer'):
            line = f'        if (!WSAOwnedGraph({args}) || !WSAOwnedGraph(Layer, CloneLayer)) return false;\n'
            self.assertEqual(s.count(line), 2)
            s = s.replace(line, '')
        interface_loop = '''        for (UObject* O : {static_cast<UObject*>(CloneMaster), static_cast<UObject*>(CloneLayer)})
        {
            FWeaponRepair Inspect;
            for (auto* E : *Inspect.Expressions(O)) if (auto* C = Cast<UMaterialExpressionMaterialFunctionCall>(E))
                if (!WSAInterfaces(C)) return false;
        }
'''
        self.assertEqual(s.count(interface_loop), 1)
        s = s.replace(interface_loop, '')
        s = s.replace('                    if (!WSAInterfaces(C)) return false;',
                      '                    for (const auto& P : C->FunctionInputs) if (!P.ExpressionInput) return false;\n'
                      '                    for (const auto& P : C->FunctionOutputs) if (!P.ExpressionOutput) return false;')
        s = s.replace('SetMaterialFunction(nullptr, Layer, CloneLayer) || !WSAInterfaces(Call)',
                      'SetMaterialFunction(nullptr, Layer, CloneLayer)')
        self.assertEqual(hashlib.sha256(s.encode()).hexdigest(), '36fa9c5a84f0349e48c2d17bbddddc7efe42d9a6960477d6911ac8b9ea6888ee')

    def test_actual_ownership_and_interface_guards(self):
        # Execute the unmodified production guards. This does not simulate UE
        # DuplicateObject/updaters or prove native ABI, reflection or shader results.
        code = r'''
#include <cassert>
#include <string>
#include <vector>
#include <algorithm>
#include <map>
#include <cstdarg>
#include <cstdio>
using TCHAR=char;using int32=int;
#define TEXT(x) x
struct FString:std::string{using std::string::string;FString(){}FString(const std::string&s):std::string(s){}
 const char*operator*()const{return c_str();}FString Left(int n)const{return substr(0,n);}};
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}
 bool Contains(const T&v)const{return std::find(this->begin(),this->end(),v)!=this->end();}void Add(const T&v){this->push_back(v);}};
struct FGuid{int n=0;bool IsValid()const{return n!=0;}FString ToString()const{return std::to_string(n);}bool operator==(const FGuid&b)const{return n==b.n;}};
struct Class{FString path;FString GetPathName(){return path;}};
Class mat{"/Script/Engine.Material"},fun{"/Script/Engine.MaterialFunction"},expr{"expression"},call{"call"},in{"/Script/Engine.MaterialExpressionFunctionInput"},out{"/Script/Engine.MaterialExpressionFunctionOutput"};
struct UObject{virtual~UObject(){}UObject*outer=nullptr;Class*cls=&expr;FString name="node";std::map<FString,FString> props;
 UObject*GetOuter(){return outer;}FString GetName(){return name;}FString GetPathName(){return name;}Class*GetClass(){return cls;}};
struct UMaterial;struct UMaterialFunction;struct UMaterialExpression;
struct FExpressionInput{UMaterialExpression*Expression=nullptr;};
enum EMaterialProperty{P0,P1};const int MP_MAX=2;
struct UMaterialExpression:UObject{UMaterial*Material=nullptr;UMaterialFunction*Function=nullptr;void*GraphNode=nullptr;TArray<FExpressionInput*> pins;
 TArray<FExpressionInput*>GetInputs(){return pins;}};
struct UMaterial:UObject{TArray<UMaterialExpression*>Expressions;FExpressionInput roots[2];UMaterial(){cls=&mat;}
 FExpressionInput*GetExpressionInputForProperty(EMaterialProperty p){return &roots[p];}};
struct UMaterialFunction:UObject{TArray<UMaterialExpression*>FunctionExpressions;UMaterialFunction(){cls=&fun;}};
struct FI{void*ExpressionInput=nullptr;FGuid ExpressionInputId;};struct FO{void*ExpressionOutput=nullptr;FGuid ExpressionOutputId;};
struct UMaterialExpressionMaterialFunctionCall:UMaterialExpression{UMaterialFunction*MaterialFunction=nullptr;TArray<FI>FunctionInputs;TArray<FO>FunctionOutputs;UMaterialExpressionMaterialFunctionCall(){cls=&call;}};
template<class T>T*Cast(UObject*o){return dynamic_cast<T*>(o);}
struct FWeaponRepair{TArray<UMaterialExpression*>*Expressions(UObject*o){if(auto*m=Cast<UMaterial>(o))return &m->Expressions;if(auto*f=Cast<UMaterialFunction>(o))return &f->FunctionExpressions;return nullptr;}};
auto MRProperties(UObject*o,bool all)->std::map<FString,FString>{assert(all);return o->props;}
bool WSAField(const std::map<FString,FString>&p,const char*k,const FString&v){auto i=p.find(k);return i!=p.end()&&i->second==v;}
std::string lastLog;int logs=0;
void log(const char*fmt,...){char b[2048];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);lastLog=b;++logs;}
#define UE_LOG(c,v,...) log(__VA_ARGS__)
'''+block('OWNERSHIP')+r'''
struct Fixture{
 UMaterial master,clone;UMaterialFunction layer,cloneLayer,shared,other;
 UMaterialExpression a,b,la,lb;UMaterialExpressionMaterialFunctionCall c,d;
 FExpressionInput ap,bp,lp,cp;
 Fixture(){master.name="master";clone.name="clone";layer.name="layer";cloneLayer.name="cloneLayer";
 a.name=b.name="a";c.name=d.name="MaterialExpressionMaterialFunctionCall_0";la.name=lb.name="layerNode";
 a.outer=c.outer=&master;b.outer=d.outer=&clone;la.outer=&layer;lb.outer=&cloneLayer;
 a.Material=c.Material=&master;b.Material=d.Material=&clone;la.Function=&layer;lb.Function=&cloneLayer;
 master.Expressions={&a,&c};clone.Expressions={&b,&d};layer.FunctionExpressions={&la};cloneLayer.FunctionExpressions={&lb};
 ap.Expression=&c;bp.Expression=&d;lp.Expression=&la;cp.Expression=&lb;
 a.pins={&ap};b.pins={&bp};la.pins={&lp};lb.pins={&cp};master.roots[0].Expression=&a;clone.roots[0].Expression=&b;
 c.MaterialFunction=d.MaterialFunction=&shared;
 }
};
int updates=0;
bool Admission(Fixture& f){auto*Master=&f.master;auto*CloneMaster=&f.clone;auto*Layer=&f.layer;auto*CloneLayer=&f.cloneLayer;
 ACTUAL_TWO_GRAPH_ADMISSION
 ++updates;return true;
}
int main(){
 for(int s=0;s<3;++s){Fixture f;updates=0;
 if(s==1)f.lb.Function=&f.layer;if(s==2)f.cp.Expression=&f.la;
 assert(Admission(f)==(s==0));assert(updates==(s==0));}
 for(int s=0;s<=29;++s){Fixture f;logs=0;bool rebound=false;
 if(s==1)f.b.Material=&f.master;if(s==2)f.b.Function=&f.layer;if(s==3)f.lb.Function=&f.layer;
 if(s==4)f.bp.Expression=&f.c;if(s==5)f.clone.roots[0].Expression=&f.a;
 if(s==6)f.cp.Expression=&f.la;if(s==7)f.ap.Expression=&f.la;if(s==8)f.clone.roots[1].Expression=&f.b;
 if(s==9)f.b.outer=&f.master;if(s==10)f.b.GraphNode=(void*)1;if(s==11)f.b.name="different";
 if(s==12)f.b.cls=&call;if(s==13)f.clone.Expressions[0]=&f.a;if(s==14)f.clone.Expressions[1]=&f.b;
 if(s==15)f.clone.Expressions.push_back(&f.b);if(s==16)f.a.pins.push_back(nullptr);if(s==17)f.b.pins[0]=nullptr;
 if(s==18)f.b.Material=nullptr;if(s==19)f.a.Material=&f.clone;if(s==20)f.lb.Material=&f.master;
 if(s==21)f.d.MaterialFunction=&f.other;if(s==22)f.c.MaterialFunction=f.d.MaterialFunction=nullptr;
 if(s==23){f.c.MaterialFunction=&f.layer;f.d.MaterialFunction=&f.cloneLayer;rebound=true;}
 if(s==24){f.c.MaterialFunction=&f.layer;f.d.MaterialFunction=&f.cloneLayer;}
 if(s==25){f.c.MaterialFunction=&f.layer;f.d.MaterialFunction=&f.layer;rebound=true;}
 if(s==26)f.clone.Expressions[0]=nullptr;if(s==27)f.cloneLayer.FunctionExpressions[0]=nullptr;
 if(s==28){f.a.pins.push_back(nullptr);f.b.pins.push_back(nullptr);}
 if(s==29){f.ap.Expression=nullptr;f.bp.Expression=nullptr;}
 bool ok=WSAOwnedGraph(&f.master,&f.clone,rebound?&f.layer:nullptr,rebound?&f.cloneLayer:nullptr)&&WSAOwnedGraph(&f.layer,&f.cloneLayer);
 assert(ok==(s==0||s==23||s==28||s==29));assert(logs==!ok);
 if(!ok){assert(lastLog.find("owner=")!=std::string::npos&&lastLog.find("node=")!=std::string::npos&&lastLog.find("pin=")!=std::string::npos);}
 }
 for(int s=0;s<=18;++s){UMaterialFunction f,other;UMaterialExpression i,o,foreign,duplicate;UMaterialExpressionMaterialFunctionCall c;
 i.cls=foreign.cls=duplicate.cls=&in;o.cls=&out;i.outer=o.outer=duplicate.outer=&f;foreign.outer=&other;
 i.props["Id"]="1";o.props["Id"]="2";foreign.props["Id"]=duplicate.props["Id"]="1";
 f.FunctionExpressions={&i,&o};c.MaterialFunction=&f;c.FunctionInputs={{&i,{1}}};c.FunctionOutputs={{&o,{2}}};logs=0;
 if(s==1)c.FunctionInputs[0].ExpressionInput=&foreign;if(s==2)c.FunctionInputs[0].ExpressionInputId.n=9;
 if(s==3)c.FunctionOutputs[0].ExpressionOutput=&i;if(s==4)c.FunctionInputs[0].ExpressionInput=nullptr;
 if(s==5)c.FunctionInputs[0].ExpressionInputId.n=0;if(s==6)i.outer=&other;if(s==7)f.FunctionExpressions.push_back(&duplicate);
 if(s==8)c.FunctionInputs.push_back(c.FunctionInputs[0]);if(s==9)c.FunctionOutputs.push_back(c.FunctionOutputs[0]);
 if(s==10)c.FunctionOutputs.clear();if(s==11)i.props.erase("Id");if(s==12)c.MaterialFunction=nullptr;
 if(s==13)c.FunctionOutputs[0].ExpressionOutputId.n=1;if(s==14)i.cls=&expr;
 if(s==15)f.FunctionExpressions.push_back(nullptr);if(s==16){f.FunctionExpressions.clear();c.FunctionInputs.clear();c.FunctionOutputs.clear();}
 if(s==17)f.FunctionExpressions.resize(8193,&i);if(s==18)c.FunctionInputs.resize(8193,c.FunctionInputs[0]);
 bool ok=WSAInterfaces(&c);assert(ok==(s==0||s==16));assert(logs==!ok);
 if(!ok)assert(lastLog.find("guid=")!=std::string::npos);
 }
}
'''
        admission = re.search(r'        (if \(!WSAOwnedGraph\(Master, CloneMaster\) \|\| !WSAOwnedGraph\(Layer, CloneLayer\)\) return false;)', HEADER.read_text()).group(1)
        compile_run(code.replace('ACTUAL_TWO_GRAPH_ADMISSION', admission))

    def test_optional_pinned_graph_recipe_and_sampling_paths(self):
        if PRIVATE_GRAPH is None:
            self.skipTest('--private-graph not supplied; no native graph evidence exercised')
        raw = PRIVATE_GRAPH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '16f27d2dac0919264119a1cab0148f91cf69dac116354402f920dfe190ef331e')
        records = json.loads(raw)
        master = next(x for x in records if x.get('material', '').endswith('/M_WeaponsBase.M_WeaponsBase'))
        layer = {x['name']: x for x in master['nodes'] if x['owner'].endswith('/MF_LayerSet.MF_LayerSet')}
        rows = re.findall(r'\{TEXT\("(MaterialExpressionTextureObjectParameter_\d+)"\), TEXT\("([^"]+)"\), TEXT\("([^"]+)"\), TEXT\("([0-9A-F]+)"\)\}', HEADER.read_text())
        for name, old, new, guid in rows:
            node = layer[name]
            self.assertEqual(node['class'], 'MaterialExpressionTextureObjectParameter')
            self.assertEqual(node['properties']['ParameterName'], old)
            self.assertEqual(node['properties']['ExpressionGUID'], guid)
        weapon = {x['name']: x for x in master['nodes'] if x['owner'].endswith('/MF_WeaponLayer.MF_WeaponLayer')}
        for num, inputnum in [(2, 17), (5, 27)]:
            node = weapon['MaterialExpressionTextureSample_'+str(num)]
            self.assertEqual(node['properties']['SamplerSource'], 'SSM_Wrap_WorldGroupSettings')
            self.assertEqual(node['properties']['MipValueMode'], '')
            self.assertEqual([x['expression'].split(':')[-1] for x in node['inputs']], ['MaterialExpressionStaticSwitch_0', 'MaterialExpressionFunctionInput_'+str(inputnum)])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-graph', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE_GRAPH = args.private_graph
    unittest.main(argv=[sys.argv[0]] + rest)
