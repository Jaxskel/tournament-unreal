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


def block(name, source=None):
    match = re.search(r'// ALIAS_' + name + r'_BEGIN\n(.*?)\s*// ALIAS_' + name + r'_END', HEADER.read_text() if source is None else source, re.S)
    if not match:
        raise AssertionError(name)
    return match.group(1)


def without_asset(source):
    for name, indent in [('STATE', '    '), ('NORMALIZE', '            '), ('IMPLEMENTATION', ''),
                         ('ADMISSION', '    '), ('DISPATCH', '        ')]:
        pattern = re.escape(indent + '// ALIAS_ASSET_' + name + '_BEGIN\n') + r'.*?' + re.escape(indent + '// ALIAS_ASSET_' + name + '_END\n')
        source, count = re.subn(pattern, '', source, flags=re.S)
        if count != 1:
            raise AssertionError(name)
    return source


def without_pair(source):
    source = without_asset(source)
    for name, indent in [('IMPLEMENTATION', ''), ('DISPATCH', '    ')]:
        pattern = re.escape(indent + '// ALIAS_PAIR_' + name + '_BEGIN\n') + r'.*?' + re.escape(indent + '// ALIAS_PAIR_' + name + '_END\n')
        source, count = re.subn(pattern, '', source, flags=re.S)
        if count != 1:
            raise AssertionError(name)
    return source


def without_ordinary_control(source):
    source = without_pair(source)
    for name, indent, extra in [('ORDINARY_RESOURCE', '', '\n'), ('ORDINARY_COMPILE', '    ', ''), ('ORDINARY_COMPLETION', '    ', '')]:
        pattern = re.escape(indent + '// ALIAS_' + name + '_BEGIN\n') + r'.*?' + re.escape(indent + '// ALIAS_' + name + '_END\n' + extra)
        source, count = re.subn(pattern, '', source, flags=re.S)
        if count != 1:
            raise AssertionError(name)
    for tag in ('STATE', 'ROUTE', 'FLAG'):
        source, count = re.subn(r'^.*// ALIAS_ORDINARY_' + tag + r'\n', '', source, flags=re.M)
        if count != 1:
            raise AssertionError(tag)
    for new, old in [
        ('FMaterialResource* Resource = nullptr;', 'FWeaponShaderResource* Resource = nullptr;'),
        ('auto* Diagnostic = new FWeaponShaderResource; Resource = Diagnostic;', 'Resource = new FWeaponShaderResource;'),
        ('Diagnostic->NoStaticLighting = true;', 'Resource->NoStaticLighting = true;'),
        ('Diagnostic->TranslationRequests);', 'Resource->TranslationRequests);'),
    ]:
        if source.count(new) != 1:
            raise AssertionError(new)
        source = source.replace(new, old)
    return source


class SamplerAlias(unittest.TestCase):
    def test_actual_asset_resource_with_production_ordinary_policy(self):
        # Reuse the instrumented engine boundary from the pair fixture, then
        # substitute the actual ordinary resource and actual asset compile body.
        # Exact replacements below alter only host stand-ins, not production code.
        captured = []
        global compile_run
        original_compile = compile_run
        try:
            compile_run = captured.append
            self.test_actual_pair_resource_map_guards_and_failure_rows()
        finally:
            compile_run = original_compile
        self.assertEqual(len(captured), 1)
        code = captured[0]

        def replace(old, new):
            nonlocal code
            self.assertEqual(code.count(old), 1, old)
            code = code.replace(old, new)

        replace(block('PAIR_COMPILE_ONE'), block('ASSET_COMPILE_ONE'))
        replace('find("_PAIR result")', 'find("_ASSET result")')
        replace('virtual bool IsUsedWithStaticLighting()const{return true;}',
                'virtual bool IsUsedWithStaticLighting()const{return false;}')
        replace('struct FMaterialResource{int TranslationRequests',
                'enum EMaterialProperty{P};enum EShaderFrequency{F};struct FMaterialCompiler{};int ordinaryMismatch=0;\nstruct FMaterialResource{int TranslationRequests')
        replace('virtual~FMaterialResource(){++destroyed;}',
                'virtual~FMaterialResource(){++destroyed;}\n virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty,FMaterialCompiler*,EShaderFrequency,bool)const{return 0;}')
        ordinary_class = block('ORDINARY_RESOURCE').split('static bool WSAOrdinaryIDEqual', 1)[0]
        replace('struct FWeaponShaderResource:FMaterialResource{', ordinary_class + '\nstruct FWeaponShaderResource:FMaterialResource{')
        replace('if(scenario==3)out.ParameterSet.value=99;',
                'if(ordinaryMismatch&&!IsPersistent())out.VertexFactoryTypeDependencies[0].VFSourceHash=99;if(scenario==3)out.ParameterSet.value=99;')
        replace('TArray<FMaterialShaderMapId>RequestedIds;', '''TArray<FMaterialShaderMapId>RequestedIds,NoStaticReferences;bool AssetFlagChanged=true;
 State(){for(int m=0;m<2;++m)for(int q:{0,2,1}){FMaterialShaderMapId id;id.QualityLevel=q;id.ParameterSet.value=m+1;NoStaticReferences.Add(id);}}''')
        # Persistent reference is a second stack resource; neither it nor the
        # no-static comparison IDs submit jobs. Destruction counts include it.
        replace('assert(destroyed==!aborted);', 'assert(destroyed==(s>=27?0:(aborted?1:2)));')
        replace('assert(destroyed==(s>=27?0:1));', 'assert(destroyed==(s>=27?0:2));')
        code = code.replace('.CompileOne(', '.CompileAssetOne(')
        replace('State x;assert(x.CompileAssetOne(m,q)&&x.ValidResources==1);',
                'State x;x.Completed=m*3+(q==EMaterialQualityLevel::Low?0:q==EMaterialQualityLevel::Medium?1:2);assert(x.CompileAssetOne(m,q)&&x.ValidResources==1);')
        replace('assert(x.IsPersistent()&&x.IsUsedWithStaticLighting());',
                'assert(x.IsPersistent()&&!x.IsUsedWithStaticLighting());')
        offset = code.rfind('\n}')
        self.assertGreater(offset, 0)
        code = code[:offset] + r'''
 scenario=0;
 for(int test=0;test<5;++test){caches=0;ordinaryMismatch=test==0;State x;
  if(test==1)x.NoStaticReferences[0].ShaderTypeDependencies[0].SourceHash=99;
  if(test==2)x.AssetFlagChanged=false;if(test==3)x.NoStaticReferences.clear();if(test==4)x.Completed=6;
  assert(!x.CompileAssetOne(0,EMaterialQualityLevel::Low)&&caches==0);
 }
''' + code[offset:]
        compile_run(code)

    def test_asset_selector_loop_and_no_success_on_partial(self):
        # Actual selector gates and fixed loop; failures stop before any false
        # complete/valid-six interpretation. Ordinary single control stays separate.
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
using int32=int;
#define TEXT(x) x
namespace EMaterialQualityLevel{enum Type{Low=0,High=1,Medium=2,Num=3};}
struct IDs{int n=0;int Num(){return n;}};
struct S{bool AssetFlagChanged=true;int Completed=0,ValidResources=0,fail=-1;IDs RequestedIds,NoStaticReferences{6};std::vector<int>calls;
 bool PairEquivalent(){return true;}bool Unchanged(){return true;}
 bool CompileAssetOne(int m,EMaterialQualityLevel::Type q){int i=calls.size();calls.push_back(m*3+int(q));if(i==fail)return false;++Completed;++RequestedIds.n;return true;}
''' + block('ASSET_LOOP') + r'''
};
struct FString:std::string{using std::string::string;const char*operator*()const{return c_str();}};
bool pair=false,asset=false,ordinary=false;int invoked=0;
struct FParse{static bool Param(const char*,const char*k){auto s=std::string(k);return s=="SamplerAliasGrenadePair"?pair:s=="SamplerAliasAssetFlag"?asset:ordinary;}};
int WFRStop(const char*){return 1;}int WSACompilePair(int,int){invoked=1;return 2;}int WSACompileAssetPair(int,int){invoked=2;return 3;}
int route(){FString Params="";int Proof=0,Hash=0;
''' + block('ASSET_ADMISSION') + block('PAIR_DISPATCH') + r'''
return 4;}
int main(){for(int p=0;p<2;++p)for(int a=0;a<2;++a)for(int o=0;o<2;++o){pair=p;asset=a;ordinary=o;invoked=0;int result=route();
 bool reject=a&&!p||p&&o;assert(result==(reject?1:!p?4:a?3:2));assert(invoked==(reject||!p?0:a?2:1));}
 const std::vector<int>expected{0,2,1,3,5,4};
 for(int f=-1;f<6;++f){S s;s.fail=f;assert(s.CompileAssetPair()==(f<0));assert(s.Completed==(f<0?6:f));assert(s.calls.size()==(f<0?6:f+1));
  for(int i=0;i<int(s.calls.size());++i)assert(s.calls[i]==expected[i]);assert(s.ValidResources==0);}
 {S s;s.AssetFlagChanged=false;assert(!s.CompileAssetPair()&&s.calls.empty());}
 {S s;s.NoStaticReferences.n=5;assert(!s.CompileAssetPair()&&s.calls.empty());}
}
''')

    def test_actual_asset_completion_keeps_failure_and_closes(self):
        implementation = block('ASSET_IMPLEMENTATION')
        control = implementation[implementation.index('static int32 WSACompileAssetPair'):]
        compile_run(r'''
#include <cassert>
#include <string>
using int32=int;using FString=std::string;
#define TEXT(x) x
int scenario=0,closed=0,completed=0;struct FWeaponTessProof{};
int WFRStop(const char*){return 1;}
struct FWSAliasAssetState{bool done=false,Attempted=false;int Completed=0,ValidResources=0;
 FWSAliasAssetState(FWeaponTessProof&,const FString&){}~FWSAliasAssetState(){if(!done)Close();}
 bool CapturePair(){return scenario!=1;}bool PreparePair(){return scenario!=2;}bool PrepareAssetFlag(){return scenario!=3;}
 bool CompileAssetPair(){Attempted=scenario!=6;Completed=scenario==7?5:6;ValidResources=scenario==8?5:6;return scenario!=4;}
 bool Close(){assert(!done);done=true;++closed;return scenario!=5;}};
void log(const char*s,...){auto line=std::string(s);assert(line.find("ordinaryAcceptance=0")!=std::string::npos&&line.find("repairAuthority=0")!=std::string::npos);++completed;}
#define UE_LOG(c,v,...) log(__VA_ARGS__)
''' + control + r'''
int main(){for(scenario=0;scenario<=8;++scenario){closed=completed=0;FWeaponTessProof proof;assert(WSACompileAssetPair(proof,"hash")==bool(scenario));
 assert(closed==1);assert(completed==(scenario==0||scenario==8));}}
''')

    def test_asset_inverse_and_narrow_normalization(self):
        s = HEADER.read_text()
        self.assertEqual(hashlib.sha256(without_asset(s).encode()).hexdigest(),
                         'ee9471c5eafbe60b88bfd34f087a753d9d9d555bd0af64351d75bb46e8d3bbd1')
        self.assertEqual(s.count('CloneMaster->bUsedWithStaticLighting = false;'), 1)
        self.assertIn('if (I == 0 && !NormalizeAssetFlag(XP, YP)) return false;', s)
        preparation = block('ASSET_PREPARE')
        self.assertNotIn('->CacheShaders(', preparation)
        self.assertLess(preparation.index('!WSADrain()'), preparation.index('MasterId = Fresh'))
        self.assertLess(preparation.index('MasterId = Fresh'), preparation.index('Reference.GetShaderMapId'))
        self.assertLess(preparation.index('NoStaticReferences.Num() != 6 || !WSADrain()'), preparation.index('CloneMaster->bUsedWithStaticLighting = false;'))
        compile_run(r'''
#include <cassert>
#include <map>
#include <memory>
#include <string>
using TCHAR=char;
#define TEXT(x) x
const int RF_Transient=1;int package,other;void*GetTransientPackage(){return &package;}
struct FString:std::string{using std::string::string;FString(){}FString(const std::string&s):std::string(s){}bool IsEmpty()const{return empty();}};
struct FJsonObject{std::map<FString,FString>values;void SetStringField(const char*k,const FString&v){values[k]=v;}};
template<class T>using TSharedPtr=std::shared_ptr<T>;
bool WSAField(TSharedPtr<FJsonObject>p,const char*k,const FString&v){return p->values.count(k)&&p->values[k]==v;}
struct Material{bool bUsedWithStaticLighting=true,transient=true;void*outer=&package;void*GetOuter(){return outer;}bool HasAnyFlags(int){return transient;}};
struct State{Material*Master=nullptr,*CloneMaster=nullptr;
''' + block('ASSET_STATE') + r'''
};
int main(){for(int n=0;n<14;++n){Material source,owned;owned.bUsedWithStaticLighting=false;State s;s.Master=&source;s.CloneMaster=&owned;
 s.AssetFlagChanged=n!=1;s.SourceStaticLightingText="True";s.OwnedStaticLightingText="";
 auto a=std::make_shared<FJsonObject>(),b=std::make_shared<FJsonObject>();a->values={{"bUsedWithStaticLighting","True"},{"other","original"}};b->values={{"bUsedWithStaticLighting",""},{"other","candidate"}};
 if(n==2)s.Master=nullptr;if(n==3)s.CloneMaster=nullptr;if(n==4)s.CloneMaster=s.Master;if(n==5)source.bUsedWithStaticLighting=false;
 if(n==6)owned.bUsedWithStaticLighting=true;if(n==7)owned.outer=&other;if(n==8)owned.transient=false;if(n==9)s.SourceStaticLightingText="";
 if(n==10)s.OwnedStaticLightingText="True";if(n==11)a->values.erase("bUsedWithStaticLighting");if(n==12)b->values.erase("bUsedWithStaticLighting");if(n==13)b->values["bUsedWithStaticLighting"]="True";
 auto av=a->values,bv=b->values;bool originalFlag=source.bUsedWithStaticLighting,ownedFlag=owned.bUsedWithStaticLighting;
 assert(s.NormalizeAssetFlag(a,b)==(n<2));assert(a->values==av);assert(source.bUsedWithStaticLighting==originalFlag&&owned.bUsedWithStaticLighting==ownedFlag);
 if(n==0){assert(b->values["bUsedWithStaticLighting"]=="True"&&b->values["other"]=="candidate");}else assert(b->values==bv);
}}
''')

    def test_actual_asset_preparation_reference_only_and_one_owned_flag(self):
        overrides = (PRIVATE / 'WeaponShaderProbe.h').read_text().split('// WSP_CF_OVERRIDES_BEGIN\n', 1)[1].split('// WSP_CF_OVERRIDES_END', 1)[0]
        comparator = block('ORDINARY_RESOURCE').split('static bool WSAOrdinaryIDEqual', 1)[1]
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <algorithm>
using int32=int;using TCHAR=char;
#define TEXT(x) x
int scenario=0,drains=0,ids=0,live=0;const int RF_Transient=1,SP_OPENGL_ES2_WEBGL=9;
int package,other;void*GetTransientPackage(){return &package;}
struct FString:std::string{using std::string::string;FString(){}FString(const std::string&s):std::string(s){}bool IsEmpty()const{return empty();}};
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}void Add(const T&v){this->push_back(v);}bool Contains(const T&v)const{return std::find(this->begin(),this->end(),v)!=this->end();}};
struct FGuid{int v=0;bool IsValid()const{return v!=0;}bool operator==(const FGuid&o)const{return v==o.v;}bool operator!=(const FGuid&o)const{return v!=o.v;}
 static FGuid NewGuid(){return {scenario==18?0:scenario==19?10:scenario==20?5:scenario==21?20:100};}};
namespace EMaterialQualityLevel{enum Type{Low=0,High=1,Medium=2,Num=3};}namespace ERHIFeatureLevel{enum Type{ES2=2};}
struct FStaticParameterSet{int value=0;};
struct O{FGuid StateId;bool bUsedWithStaticLighting=true,transient=true;void*outer=&package;int staticValue=0;void*GetOuter(){return outer;}bool HasAnyFlags(int){return transient;}void GetStaticParameterValues(FStaticParameterSet&s){s.value=staticValue;}};
struct FJsonObject{std::map<FString,FString>values;bool TryGetStringField(const char*k,FString&v){if(!values.count(k))return false;v=values[k];return true;}void SetStringField(const char*k,const FString&v){values[k]=v;}};
template<class T>using TSharedPtr=std::shared_ptr<T>;
O*original=nullptr;
TSharedPtr<FJsonObject>MRProperties(O*o,bool){auto p=std::make_shared<FJsonObject>();p->values={{"bUsedWithStaticLighting",o->bUsedWithStaticLighting?"True":""},{"other","same"}};
 if(scenario==30&&o!=original&&o->bUsedWithStaticLighting)p->values.erase("bUsedWithStaticLighting");
 if(scenario==31&&o==original)p->values["bUsedWithStaticLighting"]="different";
 if(scenario==32&&!o->bUsedWithStaticLighting)p->values.erase("bUsedWithStaticLighting");
 if(scenario==33&&!o->bUsedWithStaticLighting)p->values["bUsedWithStaticLighting"]="True";
 if(scenario==34&&!o->bUsedWithStaticLighting)p->values["other"]="changed";return p;}
bool WSAField(TSharedPtr<FJsonObject>p,const char*k,const FString&v){return p->values.count(k)&&p->values[k]==v;}
FString MRValue(TSharedPtr<FJsonObject>p){FString s;for(auto&kv:p->values)s+=kv.first+kv.second;return s;}
int MRStatic(const FStaticParameterSet&s){return s.value;}int MRValue(int x){return x;}
struct FWeaponRepair{template<class T>bool Same(const T&a,const T&b){return a==b;}};
struct SD{int ShaderType=1,SourceHash=2;};struct PD{int ShaderPipelineType=3,StagesSourceHash=4;};struct VD{int VertexFactoryType=5,VFSourceHash=6;};
struct FMaterialShaderMapId{FGuid BaseMaterialId;int QualityLevel=0,FeatureLevel=2;FStaticParameterSet ParameterSet;TArray<FGuid>ReferencedFunctions{FGuid{20}};TArray<SD>ShaderTypeDependencies{SD{}};TArray<PD>ShaderPipelineTypeDependencies{PD{}};TArray<VD>VertexFactoryTypeDependencies{VD{}};};
bool WSPMaterialInstanceIdentitySubset(const FMaterialShaderMapId&a,const FMaterialShaderMapId&b){return a.BaseMaterialId==b.BaseMaterialId&&a.QualityLevel==b.QualityLevel&&a.FeatureLevel==b.FeatureLevel&&a.ParameterSet.value==b.ParameterSet.value&&a.ReferencedFunctions==b.ReferencedFunctions;}
static bool WSAOrdinaryIDEqual''' + comparator + r'''
struct FMaterialResource{O*master=nullptr,*instance=nullptr;int quality=0;FMaterialResource(){++live;}virtual~FMaterialResource(){--live;}
 virtual bool IsPersistent()const{return true;}virtual bool IsUsedWithStaticLighting()const{return master->bUsedWithStaticLighting;}
 bool IsSpecialEngineMaterial(){return false;}
 void SetMaterial(O*m,int q,bool hasq,int f,O*i){assert(m->bUsedWithStaticLighting&&m->StateId.v==100&&hasq&&f==2);master=m;instance=i;quality=q;}
 void GetShaderMapId(int p,FMaterialShaderMapId&id){assert(p==9&&!IsPersistent()&&!IsUsedWithStaticLighting()&&master->bUsedWithStaticLighting);++ids;
  id.BaseMaterialId=master->StateId;id.QualityLevel=quality;id.ParameterSet.value=instance->staticValue;
  if(scenario==22)id.BaseMaterialId.v=99;if(scenario==23)id.QualityLevel=99;if(scenario==24)id.FeatureLevel=99;if(scenario==25)id.ReferencedFunctions={FGuid{30}};
  if(scenario==26)id.ShaderTypeDependencies.clear();if(scenario==27)id.ParameterSet.value=99;}
};
struct FWeaponShaderResource:FMaterialResource{
''' + overrides + r'''
};
bool WSADrain(){++drains;assert(live==0);return scenario!=7&&!(scenario==29&&drains==2);}
bool WSAOwnedGraph(O*,O*,O* =nullptr,O* =nullptr){return scenario!=17;}
struct State{O master,clone,layer,cloneLayer,one,child;O*Master=&master,*CloneMaster=&clone,*Layer=&layer,*CloneLayer=&cloneLayer,*MI=&one,*Child=&child,*CloneMI=&one,*CloneChild=&child;
 bool AssetFlagChanged=false,OrdinaryLighting=false;void*Resource=nullptr;int Completed=0;TArray<FMaterialShaderMapId>RequestedIds,NoStaticReferences;TArray<O*>Roots;FGuid MasterId{10},LayerId{20};FString MasterHash,SourceStaticLightingText,OwnedStaticLightingText;
 struct P{State*s;bool Check(const FString&){return scenario!=10&&!(scenario==37&&s->AssetFlagChanged);}}Proof{this};
 State(){original=Master;master.StateId={5};clone.StateId=MasterId;layer.StateId={30};one.staticValue=1;child.staticValue=scenario==28?1:2;Roots.Add(CloneMaster);}
 bool PairEquivalent(){assert(live==0);return scenario!=8&&!(scenario==35&&AssetFlagChanged);}
 bool Unchanged(){return scenario!=9&&!(scenario==36&&AssetFlagChanged);}bool Contracts(O*,O*){return scenario!=11;}
''' + block('ASSET_PREPARE') + r'''
};
int main(){for(scenario=0;scenario<=37;++scenario){drains=ids=live=0;State s;
 if(scenario==1)s.AssetFlagChanged=true;if(scenario==2)s.Resource=&package;if(scenario==3)s.Completed=1;if(scenario==4)s.RequestedIds.Add({});if(scenario==5)s.NoStaticReferences.Add({});
 if(scenario==6)s.OrdinaryLighting=true;if(scenario==12)s.master.bUsedWithStaticLighting=false;if(scenario==13)s.clone.bUsedWithStaticLighting=false;
 if(scenario==14)s.clone.outer=&other;if(scenario==15)s.clone.transient=false;if(scenario==16)s.Roots.clear();
 bool originalFlag=s.master.bUsedWithStaticLighting;assert(s.PrepareAssetFlag()==(scenario==0));assert(live==0&&s.master.bUsedWithStaticLighting==originalFlag);
 if(scenario==0){assert(ids==6&&drains==2&&s.AssetFlagChanged&&!s.clone.bUsedWithStaticLighting&&s.master.bUsedWithStaticLighting);assert(s.clone.StateId.v==100);}
 if(scenario>=1&&scenario<=21)assert(ids==0);
 if(scenario>=22&&scenario<=27)assert(ids==1);
 if(scenario==28)assert(ids==4);
 if(scenario>=29)assert(ids==6);
 if(scenario>=32)assert(!s.clone.bUsedWithStaticLighting);
}}
''')

    def test_empty_false_export_inverse_and_prior_body_rejection(self):
        # Native MRProperties/ExportText default-false is a PRESENT empty string.
        # Restoring only the two old checks reconstructs the compiled fcb bridge.
        source = HEADER.read_text()
        replacements = [
            ('SourceStaticLightingText.IsEmpty() || SourceStaticLightingText == OwnedStaticLightingText',
             'SourceStaticLightingText.IsEmpty() || OwnedStaticLightingText.IsEmpty() || SourceStaticLightingText == OwnedStaticLightingText'),
            ('            OwnedStaticLightingText == SourceStaticLightingText) return false;',
             '            OwnedStaticLightingText.IsEmpty() || OwnedStaticLightingText == SourceStaticLightingText) return false;'),
        ]
        prior = source
        for new, old in replacements:
            self.assertEqual(prior.count(new), 1)
            prior = prior.replace(new, old)
        self.assertEqual(hashlib.sha256(prior.encode()).hexdigest(),
                         'fcb4ac626e66ce605bce03f94f8f2240882c27ee94e6b58adfa6d22cd37f520a')
        captured = []
        global compile_run
        original_compile = compile_run
        try:
            compile_run = captured.append
            self.test_asset_inverse_and_narrow_normalization()
            self.test_actual_asset_preparation_reference_only_and_one_owned_flag()
        finally:
            compile_run = original_compile
        self.assertEqual(len(captured), 2)
        normalize, prepare = captured
        self.assertEqual(normalize.count(block('ASSET_STATE')), 1)
        normalize = normalize.replace(block('ASSET_STATE'), block('ASSET_STATE', prior))
        normalize = normalize.replace('==(n<2)', '==(n==1)')
        normalize = normalize.replace('if(n==0){assert', 'if(false){assert')
        original_compile(normalize)
        self.assertEqual(prepare.count(block('ASSET_PREPARE')), 1)
        prepare = prepare.replace(block('ASSET_PREPARE'), block('ASSET_PREPARE', prior))
        prepare = prepare.replace('s.PrepareAssetFlag()==(scenario==0)', 's.PrepareAssetFlag()==false')
        prepare = prepare.replace('ids==6&&drains==2&&s.AssetFlagChanged', 'ids==6&&drains==2&&!s.AssetFlagChanged')
        original_compile(prepare)

    def test_actual_child_prepare_preserves_parent_bags_and_static_values(self):
        pair = block('PAIR_IMPLEMENTATION')
        methods = pair[pair.index('    bool PreparePair()'):pair.index('    // ALIAS_PAIR_COMPILE_ONE_BEGIN')]
        # Exact child preparation/comparison bodies. Duplication/reflection are
        # instrumented; this proves control/comparison rejection, not UE behavior.
        compile_run(r'''
#include <cassert>
#include <string>
#include <map>
#include <memory>
using FString=std::string;
#define TEXT(x) x
const int RF_Transient=1;
int scenario=0,prepares=0,duplicates=0,setters=0,drains=0;
int package,otherPackage;void*GetTransientPackage(){return &package;}
struct UObject{};
template<class T>T*FindObject(void*,const char*){return scenario==1?reinterpret_cast<T*>(1):nullptr;}
template<class T>using TSharedPtr=std::shared_ptr<T>;
struct FJsonObject{std::map<FString,FString>values;TSharedPtr<FJsonObject>properties;
 TSharedPtr<FJsonObject>GetObjectField(const char*){return properties;}};
struct FStaticParameterSet{int value=0;};
struct Obj:UObject{Obj*Parent=nullptr,*material=nullptr;void*outer=&package;bool transient=true;int cls=1,staticValue=42;FString path,guid="old",bag="Panini=false;child-overrides";
 Obj*GetMaterial(){return material;}void*GetOuter(){return outer;}bool HasAnyFlags(int){return transient;}int GetClass(){return cls;}FString GetPathName(){return path;}
 void GetStaticParameterValues(FStaticParameterSet&s){s.value=staticValue;}
 void SetParentEditorOnly(Obj*p){++setters;Parent=p;material=p->material;}
};
TSharedPtr<FJsonObject>WSAObject(Obj*o){auto j=std::make_shared<FJsonObject>();j->properties=std::make_shared<FJsonObject>();j->properties->values={{"guid",o->guid},{"parent",o->Parent->path},{"bag",o->bag}};return j;}
FString MRValue(TSharedPtr<FJsonObject>j){FString s;for(auto&kv:j->properties->values)s+=kv.first+":"+kv.second+";";return s;}
FString MRStatic(const FStaticParameterSet&s){return std::to_string(s.value);}FString MRValue(FString s){return s;}
struct FWeaponRepair{struct C:std::map<FString,FString>{void Add(FString a,FString b){(*this)[a]=b;}}Canonical;
 bool Same(FString a,FString b){for(auto&kv:Canonical){size_t i;while((i=b.find(kv.first))!=FString::npos)b.replace(i,kv.first.size(),kv.second);}return a==b;}};
struct Lighting{bool Capture(Obj*,Obj*){return scenario!=4;}bool Normalize(TSharedPtr<FJsonObject>a,TSharedPtr<FJsonObject>b)const{
 if(scenario==14||a->values["guid"]!="old"||b->values["guid"]!="new")return false;b->values["guid"]=a->values["guid"];return true;}};
bool WSAOwnedGraph(Obj*,Obj*,Obj* =nullptr,Obj* =nullptr){return scenario!=7;}
bool WSADrain(){++drains;return scenario!=8;}
struct State{Obj master,cloneMaster,layer,cloneLayer,one,cloneOne,child,cloneChild;
 Obj*Master=&master,*CloneMaster=&cloneMaster,*Layer=&layer,*CloneLayer=&cloneLayer,*MI=&one,*CloneMI=&cloneOne,*Child=&child,*CloneChild=nullptr;Lighting ChildLighting;
 State(){master.path="original-master";cloneMaster.path="owned-master";one.path="original-one";cloneOne.path="owned-one";child.path="original-child";cloneChild.path="owned-child";
 child.Parent=&one;child.material=&master;one.material=&master;cloneOne.material=&cloneMaster;}
 bool Prepare(){++prepares;return scenario!=2;}bool Equivalent()const{return scenario!=6;}bool Unchanged(){return scenario!=15;}
 Obj*Duplicate(Obj*o,const char*){++duplicates;cloneChild=*o;cloneChild.path="owned-child";cloneChild.guid="new";
  if(scenario==5)cloneChild.Parent=&master;if(scenario==9)cloneChild.bag="flattened";if(scenario==10)cloneChild.staticValue=7;
  if(scenario==11)cloneChild.transient=false;if(scenario==12)cloneChild.outer=&otherPackage;if(scenario==13)cloneChild.cls=2;
  return scenario==3?nullptr:&cloneChild;}
''' + methods + r'''
};
int main(){for(scenario=0;scenario<=15;++scenario){prepares=duplicates=setters=drains=0;State s;auto oldBag=s.child.bag,oldGuid=s.child.guid;auto oldParent=s.child.Parent;
 assert(s.PreparePair()==(scenario==0));assert(prepares==(scenario!=1));assert(duplicates==(scenario!=1&&scenario!=2));
 bool set=scenario==0||scenario>=8;assert(setters==set&&drains==set);
 assert(s.child.bag==oldBag&&s.child.guid==oldGuid&&s.child.Parent==oldParent);
 if(scenario==0){assert(s.CloneChild->Parent==s.CloneMI&&s.CloneChild->bag==oldBag);assert(s.PairEquivalent());s.CloneChild->Parent=s.CloneMaster;assert(!s.PairEquivalent());}
}}
''')

    def test_actual_pair_loop_and_opt_in(self):
        # Production loop and dispatch, with an instrumented compile boundary.
        # Enum deliberately uses High=1, Medium=2 as in the pinned old engine.
        compile_run(r'''
#include <cassert>
#include <vector>
#include <utility>
#include <string>
using int32=int;
#define TEXT(x) x
namespace EMaterialQualityLevel{enum Type{Low=0,High=1,Medium=2,Num=3};}
struct IDs{int count=0;int Num(){return count;}};
struct S{int Completed=0,ValidResources=0,fail=-1;bool equivalent=true,unchanged=true;IDs RequestedIds;
 std::vector<std::pair<int,int>>calls;
 bool CompileOne(int m,EMaterialQualityLevel::Type q){int i=calls.size();calls.push_back({m,q});if(i==fail)return false;++Completed;++RequestedIds.count;if(i%2)++ValidResources;return true;}
 bool PairEquivalent(){return equivalent;}bool Unchanged(){return unchanged;}
''' + block('PAIR_LOOP') + r'''
};
struct FString:std::string{using std::string::string;const char*operator*()const{return c_str();}};
bool pairFlag=false,ordinaryFlag=false;int pairCalls=0;
struct FParse{static bool Param(const char*,const char*k){return std::string(k)=="SamplerAliasGrenadePair"?pairFlag:ordinaryFlag;}};
int WFRStop(const char*){return 9;}int WSACompilePair(int,int){++pairCalls;return 7;}
int route(){FString Params="";int Proof=0,Hash=0;
''' + block('PAIR_DISPATCH', without_asset(HEADER.read_text())) + r'''
return 3;}
int main(){
 const std::vector<std::pair<int,int>>expected{{0,0},{0,2},{0,1},{1,0},{1,2},{1,1}};
 for(int f=-1;f<6;++f){S s;s.fail=f;assert(s.CompilePair()==(f<0));assert(s.calls.size()==(f<0?6:f+1));
  for(int i=0;i<int(s.calls.size());++i)assert(s.calls[i]==expected[i]);
  assert(s.Completed==(f<0?6:f));assert(s.ValidResources==(f<0?3:f/2));}
 for(int x=0;x<5;++x){S s;if(x==0)s.Completed=1;if(x==1)s.ValidResources=1;if(x==2)s.RequestedIds.count=1;if(x==3)s.equivalent=false;if(x==4)s.unchanged=false;
  assert(!s.CompilePair());assert(s.calls.size()==(x<3?0:6));}
 for(int p=0;p<2;++p)for(int o=0;o<2;++o){pairFlag=p;ordinaryFlag=o;pairCalls=0;assert(route()==(p?(o?9:7):3));assert(pairCalls==(p&&!o));}
}
''')

    def test_actual_pair_resource_map_guards_and_failure_rows(self):
        # Actual per-resource body, ordinary full-ID comparator and static check.
        # No UE shader/DDC/device behavior is represented by these stand-ins.
        ordinary = block('ORDINARY_RESOURCE')
        comparator = ordinary[ordinary.index('static bool WSAOrdinaryIDEqual'):]
        probe = (PRIVATE / 'WeaponShaderProbe.h').read_text()
        overrides = probe.split('// WSP_CF_OVERRIDES_BEGIN\n', 1)[1].split('// WSP_CF_OVERRIDES_END', 1)[0]
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
#include <algorithm>
using int32=int;using TCHAR=char;
#define TEXT(x) x
struct FString:std::string{using std::string::string;FString(){}FString(const std::string&s):std::string(s){}const char*operator*()const{return c_str();}};
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}bool Contains(T x)const{return std::find(this->begin(),this->end(),x)!=this->end();}void Add(const T&v){this->push_back(v);}};
namespace EMaterialQualityLevel{enum Type{Low=0,High=1,Medium=2,Num=3};}namespace ERHIFeatureLevel{enum Type{ES2=2};}
const int SP_OPENGL_ES2_WEBGL=5;
struct Guid{int n=0;bool operator==(const Guid&b)const{return n==b.n;}bool operator!=(const Guid&b)const{return n!=b.n;}FString ToString()const{return std::to_string(n);}};
struct FStaticParameterSet{int value=0;};int MRStatic(const FStaticParameterSet&s){return s.value;}int MRValue(int x){return x;}
struct FWeaponRepair{bool Same(int a,int b){return a==b;}};
struct SD{int ShaderType=1,SourceHash=2;};struct PD{int ShaderPipelineType=3,StagesSourceHash=4;};struct VD{int VertexFactoryType=5,VFSourceHash=6;};
struct FMaterialShaderMapId{Guid BaseMaterialId{10};int QualityLevel=0,FeatureLevel=2;FStaticParameterSet ParameterSet;TArray<Guid>ReferencedFunctions{Guid{20}};TArray<SD>ShaderTypeDependencies{SD{}};TArray<PD>ShaderPipelineTypeDependencies{PD{}};TArray<VD>VertexFactoryTypeDependencies{VD{}};};
bool WSPMaterialInstanceIdentitySubset(const FMaterialShaderMapId&a,const FMaterialShaderMapId&b){return a.BaseMaterialId==b.BaseMaterialId&&a.QualityLevel==b.QualityLevel&&a.FeatureLevel==b.FeatureLevel&&a.ParameterSet.value==b.ParameterSet.value&&a.ReferencedFunctions==b.ReferencedFunctions;}
''' + comparator + r'''
int scenario=0,caches=0,finishes=0,drains=0,destroyed=0,samplerReads=0,uniformReads=0,proofs=0,contracts=0,bindings=0,results=0,equivalences=0;
struct MI{int identity=0;void GetStaticParameterValues(FStaticParameterSet&s){s.value=identity;}};
struct LayerType{Guid StateId{30};};struct UTexture{FString GetPathName(){return "texture";}};
struct FMaterialResource;
struct ExprType{const char*GetName(){return "texture-expression";}};
struct Expr{ExprType type;UTexture tex;ExprType*GetType(){return scenario==23?nullptr:&type;}int GetTextureIndex(){return 0;}
 void GetGameThreadTextureValue(MI*,FMaterialResource&,UTexture*&t){++bindings;t=scenario==24?nullptr:&tex;}};
struct Binding{Expr e;Expr*GetReference()const{return scenario==22?nullptr:const_cast<Expr*>(&e);}};
struct Map{FMaterialShaderMapId id;bool IsCompilationFinalized(){return scenario!=12;}bool CompiledSuccessfully(){return scenario!=13;}
 int GetShaderPlatform(){return scenario==14?99:5;}const FMaterialShaderMapId&GetShaderMapId(){return id;}};
struct FMaterialResource{int TranslationRequests=1,q=0;MI*instance=nullptr;Map map;TArray<FString>errors;TArray<Binding>textures;
 virtual~FMaterialResource(){++destroyed;}
 void SetMaterial(void*,int quality,bool hasq,int f,MI*m){assert(hasq&&f==2);q=quality;instance=m;}
 bool IsSpecialEngineMaterial(){return scenario==1;}virtual bool IsPersistent()const{return true;}virtual bool IsUsedWithStaticLighting()const{return true;}
 void GetShaderMapId(int platform,FMaterialShaderMapId&out){assert(platform==5);out=FMaterialShaderMapId{};out.QualityLevel=q;out.ParameterSet.value=instance->identity;
  if(IsUsedWithStaticLighting())out.ShaderTypeDependencies.push_back(SD{});
  if(!IsUsedWithStaticLighting()){if(scenario==3)out.ParameterSet.value=99;if(scenario==4)out.BaseMaterialId.n=99;if(scenario==5)out.ReferencedFunctions={Guid{30}};}}
 bool CacheShaders(const FMaterialShaderMapId&id,int platform,bool apply){assert(platform==5&&!apply&&!IsUsedWithStaticLighting()&&!IsPersistent());++caches;map.id=id;
  if(scenario==15)map.id.ShaderTypeDependencies[0].SourceHash=99;if(scenario==16)map.id.ShaderPipelineTypeDependencies[0].StagesSourceHash=99;
  if(scenario==17)map.id.VertexFactoryTypeDependencies[0].VFSourceHash=99;
  if(scenario==18)errors.push_back("compile failed");if(scenario==25)errors.resize(65,"compile failed");return scenario!=7;}
 void FinishCompilation(){++finishes;}bool IsCompilationFinished(){return scenario!=9;}Map*GetGameThreadShaderMap(){return scenario==11?nullptr:&map;}
 bool HasValidGameThreadShaderMap(){return scenario!=10;}const TArray<FString>&GetCompileErrors(){return errors;}
 int GetSamplerUsage(){++samplerReads;return scenario==19?17:scenario==20?-1:16;}
 const TArray<Binding>&GetUniform2DTextureExpressions(){++uniformReads;textures.resize(scenario==21?13:14);return textures;}
 TArray<int>GetUniformCubeTextureExpressions(){++uniformReads;return TArray<int>(scenario==26?1:0);}
};
struct FWeaponShaderResource:FMaterialResource{
''' + overrides + r'''
};
bool WSADrain(){++drains;return scenario!=8;}FString WFRContext(const FString&s){return s;}FString WSATarget(){return "1p";}
void log(const char*f,...){if(std::string(f).find("_PAIR result")!=std::string::npos)++results;}
#define UE_LOG(c,v,...) log(__VA_ARGS__)
struct State{MI one{1},child{2};MI*MI=&one,*Child=&child,*CloneMI=&one,*CloneChild=&child;void*CloneMaster=nullptr;LayerType layer,*Layer=&layer;
 FMaterialResource*Resource=nullptr;bool OrdinaryLighting=false,Attempted=false;int Completed=0,ValidResources=0;
 Guid MasterId{10},LayerId{20};FString MasterHash="hash";TArray<FMaterialShaderMapId>RequestedIds;
 struct P{bool Check(const FString&){++proofs;return scenario!=27;}}Proof;
 bool Contracts(struct MI*,LayerType*){++contracts;return scenario!=28;}
 bool PairEquivalent(){++equivalences;return scenario!=29;}bool Unchanged(){return scenario!=30;}
 FString ChildTarget(){return "3p";}~State(){delete Resource;}
''' + block('PAIR_COMPILE_ONE') + r'''
};
int main(){for(int s=0;s<=30;++s){scenario=s;caches=finishes=drains=destroyed=samplerReads=uniformReads=proofs=contracts=bindings=results=equivalences=0;
 {State x;if(s==6){FMaterialShaderMapId old;old.ParameterSet.value=1;x.RequestedIds.Add(old);}
 bool finished=x.CompileOne(0,EMaterialQualityLevel::Low);
 bool pre=s==1||s>=3&&s<=6||s>=27;bool aborted=pre||s==8||s==9||s==22||s==23||s==24||s==25;
 assert(finished==!aborted);assert(x.Completed==!aborted);assert(results==!aborted);
 assert(x.ValidResources==(s==0||s==2));assert(caches==!pre);assert(finishes==caches);assert(drains==caches);
 bool readable=s==0||s==2||s>=19&&s<=24||s==26;assert(samplerReads==readable);
 if(!readable)assert(uniformReads==0);assert(destroyed==!aborted);
 if(!aborted)assert(x.Resource==nullptr);
 }assert(destroyed==(s>=27?0:1));}
 // Medium is numerically greater than High in this engine; both must compile.
 scenario=0;for(int m=0;m<2;++m)for(auto q:{EMaterialQualityLevel::Low,EMaterialQualityLevel::High,EMaterialQualityLevel::Medium}){State x;assert(x.CompileOne(m,q)&&x.ValidResources==1);}
 for(int m:{-1,2}){State x;assert(!x.CompileOne(m,EMaterialQualityLevel::High)&&!x.Resource);}
 {State x;assert(!x.CompileOne(0,static_cast<EMaterialQualityLevel::Type>(3))&&!x.Resource);}
 {FWeaponShaderResource x;assert(x.IsPersistent()&&x.IsUsedWithStaticLighting());x.NoStaticLighting=true;assert(!x.IsPersistent()&&!x.IsUsedWithStaticLighting());}
}
''')

    def test_persistence_order_fix_inverse_to_native_pair_attempt(self):
        s = without_asset(HEADER.read_text())
        old = '        if (Resource->IsSpecialEngineMaterial() || Resource->IsPersistent()) return false;\n'
        new = '        if (Resource->IsSpecialEngineMaterial()) return false;\n'
        pair = block('PAIR_COMPILE_ONE')
        self.assertLess(pair.index('GetShaderMapId(SP_OPENGL_ES2_WEBGL, Ordinary)'), pair.index('Diagnostic->NoStaticLighting = true'))
        self.assertLess(pair.index('Diagnostic->NoStaticLighting = true'), pair.index('if (Resource->IsPersistent())'))
        self.assertLess(pair.index('if (Resource->IsPersistent())'), pair.index('GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested)'))
        restored = pair.replace(new, old).replace('        if (Resource->IsPersistent()) return false;\n', '')
        self.assertEqual(s.count(pair), 1)
        inverse = s.replace(pair, restored)
        self.assertEqual(hashlib.sha256(inverse.encode()).hexdigest(),
                         '9535b297136b8d50988e987b4ec2ad268497f46fb92482dcdb7184175c661533')

    def test_pair_inverse_and_child_hierarchy_guards(self):
        s = HEADER.read_text()
        self.assertEqual(hashlib.sha256(without_pair(s).encode()).hexdigest(),
                         'f68c8acb8112f8096a67aa7de9bdd77fab2a7921800659a316e68573427b2d10')
        pair = block('PAIR_IMPLEMENTATION')
        self.assertIn('Child->Parent != MI', pair)
        self.assertIn('CloneChild->Parent != CloneMI', pair)
        self.assertIn('ChildLighting.Normalize', pair)
        self.assertIn('Compare.Canonical.Add(CloneMI->GetPathName(), MI->GetPathName())', pair)
        self.assertIn('Compare.Same(MRValue(A), MRValue(B))', pair)
        self.assertIn('MRStatic(Old)', pair)
        prepare = pair[pair.index('bool PreparePair()'):pair.index('bool PairEquivalent()')]
        self.assertLess(prepare.index('FindObject<UObject>'), prepare.index('!Prepare()'))
        self.assertLess(prepare.index('WSAOwnedGraph(Layer, CloneLayer)'), prepare.index('SetParentEditorOnly'))
        self.assertIn('CloneChild->SetParentEditorOnly(CloneMI)', prepare)
        self.assertNotIn('CloneChild->SetParentEditorOnly(CloneMaster)', pair)
        for forbidden in ('LoadObject<', 'LoadPackage(', 'NewObject<', 'SetTextureParameterValue', 'SetScalarParameterValue', 'SavePackage('):
            self.assertNotIn(forbidden, pair)

    def test_ordinary_delta_inverse_preserves_frozen_cp3(self):
        old = without_ordinary_control(HEADER.read_text())
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(), '1667b38e55f07e1e65516fe0dec947998f4d1c5585bb40ed4729957bfcc07fd4')

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
int scenario=0,verify=0,drains=0,captured=0,prepared=0,compiled=0,closed=0,complete=0;bool ordinary=false;std::string completion;
bool GIsEditor=true;void*GShaderCompilingManager=(void*)1;
bool IsRunningCommandlet(){return scenario!=2;}bool IsInGameThread(){return scenario!=3;}
namespace FApp{bool CanEverRender(){return scenario!=4;}}
struct FParse{static bool Param(const char*,const char*key){assert(std::string(key)=="SamplerAliasOrdinaryLighting");return ordinary;}static bool Value(const char*,const char*key,FString&out){bool mode=std::string(key)=="Mode=";out=mode?(scenario==6?"WeaponRepairApply":"WeaponSamplerAliasProbe"):"proof";return scenario!=(mode?5:9);}};
int WFRStop(const char*){return 1;}
int WeaponTessellationUpgrade(const FString&,bool v){assert(v);++verify;return scenario==8;}
bool WSPQualityBranches(){return scenario!=11;}FString WTUMaster(){return "fixed-master";}FString HashFile(const FString&){return "hash";}
struct Map{FString value="masterfile";const FString*Find(const FString&){return scenario==12?nullptr:&value;}};
struct FWeaponTessProof{Map CurrentFiles;bool Read(const FString&){return scenario!=10;}bool Check(const FString&){return scenario!=13;}};
bool WSADrain(){++drains;return scenario!=14;}
struct FWSAliasState{bool done=false,Attempted=false,OrdinaryLighting=false;FWSAliasState(FWeaponTessProof&,const FString&){}~FWSAliasState(){if(!done)Close();}
 bool Capture(){assert(OrdinaryLighting==ordinary);++captured;return scenario!=15;}bool Prepare(){++prepared;return scenario!=16;}bool Compile(){++compiled;Attempted=scenario!=19;return scenario!=17&&scenario!=19;}
 bool Close(){assert(!done);done=true;++closed;return scenario!=18;}};
void log(const char*f,...){++complete;completion=f;}
#define UE_LOG(c,v,fmt,...) {log(fmt, ##__VA_ARGS__);}
'''+re.sub(r'    // ALIAS_PAIR_DISPATCH_BEGIN\n.*?    // ALIAS_PAIR_DISPATCH_END\n', '', block('CONTROL', without_asset(HEADER.read_text())), flags=re.S)+r'''
int main(){for(int o=0;o<2;++o)for(scenario=0;scenario<=19;++scenario){ordinary=o;completion.clear();verify=drains=captured=prepared=compiled=closed=complete=0;
 GIsEditor=scenario!=1;GShaderCompilingManager=scenario==7?nullptr:(void*)1;
 int result=WeaponSamplerAliasProbe("fixed");assert(result==(scenario?1:0));
 assert(verify==(scenario==0||scenario>=8));
 assert(captured==(scenario==0||scenario>=15));assert(prepared==(scenario==0||scenario>=16));
 assert(compiled==(scenario==0||scenario>=17));assert(closed==(scenario==0||scenario>=15));
 assert(complete==(scenario==0||scenario==17));
 if(complete){assert((completion.find("_ORDINARY complete")!=std::string::npos)==ordinary);assert(completion.find(ordinary?"staticLighting=1":"staticLighting=0")!=std::string::npos);}}}
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

    def test_actual_ordinary_resource_id_and_compile_failure_paths(self):
        # Exact new resource, dependency comparison and control compile body.
        # Engine services are stubs; this is not a native compile or sampler-budget result.
        code = r'''
#include <cassert>
#include <string>
#include <vector>
#include <algorithm>
using int32=int;using TCHAR=char;
struct FString:std::string{using std::string::string;const char*operator*()const{return c_str();}};
#define TEXT(x) x
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}bool Contains(T x)const{return std::find(this->begin(),this->end(),x)!=this->end();}};
namespace EMaterialQualityLevel{enum Type{High=1};}namespace ERHIFeatureLevel{enum Type{ES2=2};}
enum EMaterialProperty{Property=3};enum EShaderFrequency{Frequency=4};struct FMaterialCompiler{};
const int SP_OPENGL_ES2_WEBGL=5;
struct SD{int ShaderType=1,SourceHash=2;};struct PD{int ShaderPipelineType=3,StagesSourceHash=4;};struct VD{int VertexFactoryType=5,VFSourceHash=6;};
struct FMaterialShaderMapId{int BaseMaterialId=10,QualityLevel=1,FeatureLevel=2,identity=7;TArray<int>ReferencedFunctions{20};TArray<SD>ShaderTypeDependencies{SD{},SD{7,8}};TArray<PD>ShaderPipelineTypeDependencies{PD{}};TArray<VD>VertexFactoryTypeDependencies{VD{}};};
bool WSPMaterialInstanceIdentitySubset(const FMaterialShaderMapId&a,const FMaterialShaderMapId&b){return a.BaseMaterialId==b.BaseMaterialId&&a.QualityLevel==b.QualityLevel&&a.FeatureLevel==b.FeatureLevel&&a.identity==b.identity&&a.ReferencedFunctions==b.ReferencedFunctions;}
int scenario=0,ids=0,caches=0,finishes=0,drains=0,uniformReads=0,samplerReads=0,equivalences=0,logs=0,propertyCalls=0;
bool sourceStatic=true;FMaterialShaderMapId referenceId;
struct Map{FMaterialShaderMapId id;bool IsCompilationFinalized(){return scenario!=21;}bool CompiledSuccessfully(){return scenario!=22;}
 int GetShaderPlatform(){return scenario==23?99:SP_OPENGL_ES2_WEBGL;}const FMaterialShaderMapId&GetShaderMapId(){return id;}};
struct UMaterialFunction{int StateId=30;};
struct FMaterialResource{
 Map map;TArray<FString>errors;virtual~FMaterialResource(){}virtual bool IsPersistent()const{return true;}virtual bool IsUsedWithStaticLighting()const{return sourceStatic;}
 virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty p,FMaterialCompiler*c,EShaderFrequency f,bool previous)const{assert(p==Property&&c&&f==Frequency&&previous);++propertyCalls;return 37;}
 void SetMaterial(void*,int q,bool hasq,int f,void*){assert(q==1&&hasq&&f==2);}bool IsSpecialEngineMaterial(){return scenario==4;}
 void GetShaderMapId(int platform,FMaterialShaderMapId&out){assert(platform==5);++ids;assert(IsUsedWithStaticLighting());out=FMaterialShaderMapId{};
  if(IsPersistent()){referenceId=out;return;}assert(ids==2);
  if(scenario==6)out.BaseMaterialId=99;if(scenario==7)out.QualityLevel=99;if(scenario==8)out.FeatureLevel=99;
  if(scenario==9)out.ReferencedFunctions.clear();if(scenario==10)out.ReferencedFunctions.push_back(30);if(scenario==11)out.ShaderTypeDependencies.clear();
  if(scenario==12)out.ShaderTypeDependencies[0].ShaderType=99;if(scenario==13)out.ShaderTypeDependencies[0].SourceHash=99;
  if(scenario==30)out.identity=99;if(scenario==31)out.ShaderPipelineTypeDependencies[0].StagesSourceHash=99;if(scenario==32)out.VertexFactoryTypeDependencies[0].VertexFactoryType=99;
 }
 bool CacheShaders(const FMaterialShaderMapId&id,int platform,bool apply){assert(ids==2&&platform==5&&!apply&&!IsPersistent()&&IsUsedWithStaticLighting());++caches;map.id=id;
  if(scenario==24)map.id.VertexFactoryTypeDependencies[0].VFSourceHash=99;if(scenario==25)errors.push_back("compile error");return scenario!=14;}
 void FinishCompilation(){++finishes;}bool IsCompilationFinished(){return scenario!=16;}Map*GetGameThreadShaderMap(){return scenario==20?nullptr:&map;}
 bool HasValidGameThreadShaderMap(){return scenario!=19;}const TArray<FString>&GetCompileErrors(){return errors;}
 int GetSamplerUsage(){++samplerReads;return scenario==28?17:scenario==29?-1:16;}
 TArray<int>GetUniform2DTextureExpressions(){++uniformReads;return TArray<int>(scenario==26?13:14);}
 TArray<int>GetUniformCubeTextureExpressions(){++uniformReads;return TArray<int>(scenario==27?1:0);}
};
bool WSADrain(){++drains;return scenario!=15;}FString WFRContext(const FString&s){return s;}
void log(const char*,...){++logs;}
#define UE_LOG(c,v,...) log(__VA_ARGS__)
'''+block('ORDINARY_RESOURCE')+r'''
struct State{FMaterialResource*Resource=nullptr;void*MI=nullptr,*CloneMaster=nullptr,*CloneMI=nullptr;UMaterialFunction layer,*Layer=&layer;
 int MasterId=10,LayerId=20;FString MasterHash="hash";bool Attempted=false;
 struct P{bool Check(const FString&){return scenario!=3;}}Proof;
 bool Contracts(void*,UMaterialFunction*){return scenario!=1;}bool Equivalent(){++equivalences;return scenario!=2&&!(scenario==17&&equivalences==2);}bool Unchanged(){return scenario!=18;}
 ~State(){delete Resource;}
'''+block('ORDINARY_COMPILE')+r'''
};
int main(){
 // Exact dependency equality rejects same-size substitutions and hash drift.
 for(int s=0;s<11;++s){FMaterialShaderMapId a,b;
  if(s==1)b.identity=9;if(s==2)b.ShaderTypeDependencies.clear();if(s==3)b.ShaderTypeDependencies[0].ShaderType=9;
  if(s==4)b.ShaderTypeDependencies[0].SourceHash=9;if(s==5)b.ShaderPipelineTypeDependencies.clear();
  if(s==6)b.ShaderPipelineTypeDependencies[0].ShaderPipelineType=9;if(s==7)b.ShaderPipelineTypeDependencies[0].StagesSourceHash=9;
  if(s==8)b.VertexFactoryTypeDependencies.clear();if(s==9)b.VertexFactoryTypeDependencies[0].VertexFactoryType=9;if(s==10)b.VertexFactoryTypeDependencies[0].VFSourceHash=9;
  assert(WSAOrdinaryIDEqual(a,b)==(s==0));}
 FWSAOrdinaryResource resource;FMaterialCompiler compiler;
 for(bool flag:{false,true}){sourceStatic=flag;assert(resource.IsUsedWithStaticLighting()==flag);assert(!resource.IsPersistent());}
 assert(resource.TranslationRequests==0);assert(resource.CompilePropertyAndSetMaterialProperty(Property,&compiler,Frequency,true)==37);
 assert(resource.TranslationRequests==1&&propertyCalls==1);
 for(scenario=0;scenario<=32;++scenario){sourceStatic=scenario!=5;ids=caches=finishes=drains=uniformReads=samplerReads=equivalences=logs=0;State s;
  bool ok=s.CompileOrdinary();assert(ok==(scenario==0));bool submitted=scenario==0||(scenario>=14&&scenario<=29);
  assert(s.Attempted==submitted);assert(caches==submitted);assert(finishes==submitted);assert(drains==submitted);
  bool validMap=scenario==0||(scenario>=26&&scenario<=29);assert(uniformReads==(validMap?2:0));
  if(!validMap)assert(samplerReads==0);
  if(submitted)assert(ids==2);
 }
}
'''
        compile_run(code)

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
        s = without_ordinary_control(HEADER.read_text())
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
        # Pin actual native text representation, including field presence.
        self.assertEqual(master['properties']['bUsedWithStaticLighting'], 'True')
        blob = next(x for x in records if x.get('material', '').endswith('/M_Robust_BlobShadow.M_Robust_BlobShadow'))
        self.assertEqual(blob['properties']['bUsedWithStaticLighting'], '')
        self.assertIs(blob['two_sided'], False)
        self.assertEqual(blob['properties']['TwoSided'], '')
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
