"""Bounded local host tests; no UE build, shader jobs, asset writes or Windows calls."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import unittest
import test_weapon_fidelity as F
from test_weapon_tessellation import compile_run

HERE=Path(__file__).resolve().parent
HEADER=HERE/'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponShaderProbe.h'
PRIVATE_SOURCE=None
PRIVATE_LOG=None

def without_counterfactual(text):
    for name in ('OVERRIDES','FLAG','ADMISSION','ID_CHECK','BEGIN_LOG','BEGIN_LOG_CLOSE','RESULT_LOG','RESULT_LOG_CLOSE','ERROR_LOG','ERROR_LOG_CLOSE','COMPLETION'):
        text,count=re.subn(r'^ +// WSP_CF_'+name+r'_BEGIN\n.*?^ +// WSP_CF_'+name+r'_END\n','',text,flags=re.M|re.S)
        if count != 1: raise AssertionError((name,count))
    return text.replace('const bool DiagnosticOne = Counterfactual || FParse::Param',
                        'const bool DiagnosticOne = FParse::Param')

class Probe(unittest.TestCase):
    def test_counterfactual_requires_strict_dependency_reduction(self):
        text=HEADER.read_text()
        block=text.split('// WSP_CF_ID_CHECK_BEGIN\n')[1].split('// WSP_CF_ID_CHECK_END')[0]
        code=r'''
#include <cassert>
#define TEXT(x) x
struct Deps {int n;int Num()const{return n;}};
struct ID {Deps ShaderTypeDependencies,ShaderPipelineTypeDependencies,VertexFactoryTypeDependencies;};
int WFRStop(const char*,const char*){return 1;}
int check(bool Counterfactual,ID Requested,ID OrdinaryRequested){const char*Target="fixed";
BLOCK
return 0;}
int main(){ID ordinary{{12},{3},{3}};
 for(int cf=0;cf<2;cf++)for(int types=0;types<15;types++)for(int pipes=0;pipes<5;pipes++)for(int vfs=0;vfs<5;vfs++){
  ID requested{{types},{pipes},{vfs}};
  assert(check(cf,requested,ordinary)==int(cf&&(types>=12||pipes>3||vfs>3)));
 }
}
'''.replace('BLOCK',block)
        compile_run(code)

    def test_actual_log_branches_with_pinned_statement_macro_shape(self):
        macro=self.source('LogMacros.h','04ae83e71f23ec5a2b4f8c9b04e939b4167728b3820d7a5f880423972de6b541')
        self.assertRegex(macro,r'#define UE_LOG\(CategoryName, Verbosity, Format, \.\.\.\) \\\n\s*\{')
        text=HEADER.read_text()
        blocks=[]
        for name in ('BEGIN_LOG','RESULT_LOG','ERROR_LOG'):
            blocks.append(text.split('// WSP_CF_'+name+'_BEGIN\n')[1].split('// WSP_CF_'+name+'_CLOSE_END')[0])
        code=r'''
#include <cassert>
#include <string>
#include <vector>
#define TEXT(x) x
std::vector<std::string> logs;
// The pinned UE_LOG expands to a compound statement, not do/while or an expression.
#define UE_LOG(category,verbosity,fmt,...) { logs.push_back(fmt); }
void run(bool Counterfactual){
BLOCKS
}
int main(){for(int cf=0;cf<2;cf++){
 logs.clear();run(cf);assert(logs.size()==3);
 for(const auto&s:logs)assert((s.find("COUNTERFACTUAL")!=std::string::npos)==bool(cf));
}}
'''.replace('BLOCKS','\n'.join(blocks))
        compile_run(code)

    def test_counterfactual_inverse_recovers_exact_frozen_selector(self):
        text=HEADER.read_text()
        self.assertEqual(hashlib.sha256(without_counterfactual(text).encode()).hexdigest(),
                         '80205be4d88e3d3111b80519b3512cdaa6e277fbb58eae949048d8a7c2e2a635')
        body=F.method(text,'static int32 WeaponShaderProbe(')
        self.assertLess(body.index('Resource->NoStaticLighting = Counterfactual;'),body.index('Resource->GetShaderMapId(SP_OPENGL_ES2_WEBGL, Requested)'))
        self.assertEqual(body.count('Resource->GetShaderMapId('),2)
        self.assertNotIn('Requested =',body)
        self.assertLess(body.index('Proof.Check(MasterHash)'),body.index('Resource->SetMaterial('))
        self.assertLess(body.rindex('Proof.Check(MasterHash)'),body.index('// WSP_CF_COMPLETION_BEGIN'))
        self.assertNotIn('bUsedWithStaticLighting =',body)

    def test_actual_counterfactual_overrides_admission_selection_and_completion(self):
        text=HEADER.read_text()
        resource=text[text.index('class FWeaponShaderResource'):text.index('struct FWeaponShaderOwner')]
        def block(prefix,name):
            return text.split('// WSP_'+prefix+'_'+name+'_BEGIN\n')[1].split('// WSP_'+prefix+'_'+name+'_END')[0]
        code=r'''
#include <cassert>
#include <string>
#include <vector>
#include <utility>
using int32=int;using TCHAR=char;using EMaterialProperty=int;using EShaderFrequency=int;
struct FMaterialCompiler{};
struct FMaterialShaderMapId{};
const int SP_OPENGL_ES2_WEBGL=9;
#define TEXT(x) x
std::string label;
#define UE_LOG(category,level,fmt,...) (label=fmt)
namespace EMaterialQualityLevel {enum Type{Low,High,Medium,Num};}
struct FMaterialResource {
 bool asset=true,persistent=true,special=false;
 virtual bool IsUsedWithStaticLighting()const{return asset;}
 virtual bool IsPersistent()const{return persistent;}
 bool IsSpecialEngineMaterial()const{return special;}
 void GetShaderMapId(int,FMaterialShaderMapId&){}
 virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty,FMaterialCompiler*,EShaderFrequency,bool)const{return 0;}
};
RESOURCE
struct MasterType{bool bUsedWithStaticLighting=true;};
int WFRStop(const char*,const char*){return 1;}
int admit(bool Counterfactual,MasterType*Master,FWeaponShaderResource*Resource){const char*Target="fixed";
ADMISSION
return 0;}
bool parse(const std::string&Params,const char*flag){return Params.find(flag)!=std::string::npos;}
struct ParamsType:std::string {using std::string::string;const ParamsType&operator*()const{return *this;}};
struct FParse{static bool Param(const std::string&Params,const char*flag){return parse(Params,flag);}};
int complete(bool Counterfactual,bool DiagnosticOne,bool Success,int Resources){
CF_COMPLETION
ONE_COMPLETION
label="ordinary";return Success&&Resources==6?0:1;}
int main(){
 for(int asset=0;asset<2;asset++)for(int persistent=0;persistent<2;persistent++)for(int cf=0;cf<2;cf++){
  FWeaponShaderResource r;r.asset=asset;r.persistent=persistent;r.NoStaticLighting=cf;
  FMaterialResource*base=&r;
  assert(base->IsUsedWithStaticLighting()==bool(!cf&&asset));
  assert(base->IsPersistent()==bool(!cf&&persistent));
  assert(r.asset==bool(asset)&&r.persistent==bool(persistent));
 }
 for(int cf=0;cf<2;cf++)for(int asset=0;asset<2;asset++)for(int special=0;special<2;special++){
  MasterType m;m.bUsedWithStaticLighting=asset;FWeaponShaderResource r;r.special=special;
  bool bad=cf&&(!asset||special);assert(admit(cf,&m,&r)==int(bad));
  assert(r.NoStaticLighting==bool(cf&&!bad));assert(m.bUsedWithStaticLighting==bool(asset));
 }
 for(int flags=0;flags<4;flags++){
  ParamsType Params; if(flags&1)Params+="WeaponShaderNoStaticLighting ";
  if(flags&2)Params+="WeaponShaderEnforcer1PHigh";
CF_FLAG
ONE_FLAG
  assert(Counterfactual==bool(flags&1));assert(DiagnosticOne==bool(flags));
  const TCHAR*Targets[]={"fixed1p","fixed3p"};std::vector<std::pair<int,int>>chosen;
  for(const TCHAR*Target:Targets){
TARGET
   for(int32 Q=0;Q<EMaterialQualityLevel::Num;Q++){
QUALITY
    chosen.push_back({Target==Targets[0]?0:1,Q});
   }
  }
  assert(chosen.size()==(flags?1:6));
  if(flags)assert(chosen[0].first==0&&chosen[0].second==EMaterialQualityLevel::High);
  for(int good=0;good<2;good++)for(int count=0;count<8;count++){
   assert(complete(Counterfactual,DiagnosticOne,good,count)==((good&&count==(flags?1:6))?0:1));
   if(Counterfactual)assert(label.find("COUNTERFACTUAL complete")!=std::string::npos&&label.find("ordinaryAcceptance=0")!=std::string::npos);
   else if(DiagnosticOne)assert(label.find("DIAGNOSTIC complete")!=std::string::npos);
   else assert(label=="ordinary");
  }
 }
}
'''
        replacements={'RESOURCE':resource,'ADMISSION':block('CF','ADMISSION'),
                      'CF_COMPLETION':block('CF','COMPLETION'),'ONE_COMPLETION':block('ONE','COMPLETION'),
                      'CF_FLAG':block('CF','FLAG'),'ONE_FLAG':block('ONE','FLAG'),
                      'TARGET':block('ONE','TARGET'),'QUALITY':block('ONE','QUALITY')}
        for token,body in replacements.items():code=code.replace('\n'+token+'\n','\n'+body+'\n')
        compile_run(code)
        for name in ('BEGIN_LOG','RESULT_LOG','ERROR_LOG'):
            log=block('CF',name)
            self.assertIn('if (Counterfactual)',log)
            self.assertIn('COMPAT_WEAPON_SHADER_COUNTERFACTUAL',log)
            self.assertTrue(log.rstrip().endswith('{'))

    def test_pinned_dependency_generation_and_nonpersistent_save_policy(self):
        shared=self.source('MaterialShared.cpp','1dff15c0b80b3818055d654144dba9a346d8d471540854f17d4d572492f37f32')
        shader=self.source('MaterialShader.cpp','fb6a364da46108106f73ce0890d4f3b30cec26e925a6c7b16d2c6d664511be6c')
        header=self.source('MaterialShared.h','39760eb4df52dbadd47ee40d639e6144bb3fa0918c53ab7b292927b4054f0aed')
        get=F.method(shared,'void FMaterial::GetShaderMapId(')
        self.assertIn('GetDependentShaderAndVFTypes(Platform, ShaderTypes, ShaderPipelineTypes, VFTypes);',get)
        self.assertIn('OutId.SetShaderDependencies(ShaderTypes, ShaderPipelineTypes, VFTypes);',get)
        deps=F.method(shared,'void FMaterial::GetDependentShaderAndVFTypes(')
        self.assertIn('ShaderType->ShouldCache(Platform, this, VertexFactoryType)',deps)
        self.assertIn('VertexFactoryType->ShouldCache(Platform, this, ShaderType)',deps)
        for name in ('IsUsedWithStaticLighting','IsPersistent','IsSpecialEngineMaterial'):
            self.assertIn('ENGINE_API virtual bool '+name+'() const override;',header)
        self.assertIn('bIsPersistent = Material->IsPersistent();',shader)
        self.assertRegex(shader,r'if \(bIsPersistent\)\s*\{\s*SaveToDerivedDataCache\(\);')
        self.assertIn('bSynchronousCompile || !Material->IsPersistent()',shader)
        self.assertIn('const bool bRecreateComponentRenderStateOnCompletion = Material->IsPersistent();',shader)
        # Dependency arrays participate in engine-owned equality/key generation;
        # the probe deliberately does not call these unexported APIs.
        for name in ('ShaderTypeDependencies','ShaderPipelineTypeDependencies','VertexFactoryTypeDependencies'):
            self.assertIn(name,F.method(shader,'bool FMaterialShaderMapId::operator==('))
            self.assertIn(name,F.method(shader,'void FMaterialShaderMapId::AppendKeyString('))

    def source(self,name,sha):
        if PRIVATE_SOURCE is None:self.skipTest('pass --private-source-dir for licensed pinned API bodies')
        raw=(PRIVATE_SOURCE/name).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),sha)
        return raw.decode('utf-8-sig')

    def test_fixed_one_selector_inverse_recovers_full_six_resource_probe(self):
        text=without_counterfactual(HEADER.read_text())
        for name in ('FLAG','TARGET','QUALITY','COMPLETION'):
            text,count=re.subn(r'^ +// WSP_ONE_'+name+r'_BEGIN\n.*?^ +// WSP_ONE_'+name+r'_END\n','',text,flags=re.M|re.S)
            self.assertEqual(count,1)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         '4927128d4a940192a9c36d93865692d8373bc02e289a39f735e497ebb15edd98')
        self.assertIn('FParse::Param(*Params, TEXT("WeaponShaderEnforcer1PHigh"))',HEADER.read_text())
        self.assertNotIn('FParse::Value(*Params, TEXT("Target',HEADER.read_text())

    def test_actual_selector_and_completion_accept_only_fixed_one_or_original_six(self):
        text=HEADER.read_text()
        blocks={name:text.split('// WSP_ONE_'+name+'_BEGIN\n')[1].split('// WSP_ONE_'+name+'_END')[0]
                for name in ('TARGET','QUALITY','COMPLETION')}
        code=r'''
#include <cassert>
#include <vector>
#include <utility>
using int32=int;using TCHAR=char;
#define TEXT(x) x
#define UE_LOG(...) ((void)0)
namespace EMaterialQualityLevel {enum Type{Low,High,Medium,Num};}
int complete(bool DiagnosticOne,bool Success,int Resources){
COMPLETION
return Success && Resources == 6 ? 0 : 1;
}
int main(){const TCHAR* Targets[]={"fixed1p","fixed3p"};
 for(int diagnostic=0;diagnostic<2;diagnostic++){
  bool DiagnosticOne=diagnostic;std::vector<std::pair<int,int>> chosen;
  for(const TCHAR* Target:Targets){
TARGET
   for(int32 Q=0;Q<EMaterialQualityLevel::Num;++Q){
QUALITY
    chosen.push_back({Target==Targets[0]?0:1,Q});
   }
  }
  if(DiagnosticOne){assert(chosen.size()==1&&chosen[0].first==0&&chosen[0].second==EMaterialQualityLevel::High);}
  else {assert(chosen.size()==6);for(int i=0;i<6;i++)assert(chosen[i].first==i/3&&chosen[i].second==i%3);}
  for(int good=0;good<2;good++)for(int count=0;count<8;count++)
   assert(complete(DiagnosticOne,good,count)==((good&&count==(DiagnosticOne?1:6))?0:1));
 }
}
'''
        for name,body in blocks.items():code=code.replace(name,body)
        compile_run(code)
        self.assertIn('COMPAT_WEAPON_SHADER_DIAGNOSTIC complete selector=enforcer1p-high',blocks['COMPLETION'])
        self.assertIn('COMPAT_WEAPON_SHADER complete resources=%d valid=%d assetsSaved=0',text)

    def test_actual_counter_delegates_exact_arguments_and_return(self):
        text=HEADER.read_text()
        resource=text[text.index('class FWeaponShaderResource'):text.index('struct FWeaponShaderOwner')]
        code=r'''
#include <cassert>
using int32=int;using EMaterialProperty=int;using EShaderFrequency=int;
struct FMaterialCompiler{};
struct FMaterialResource {
 virtual bool IsUsedWithStaticLighting()const{return true;}
 virtual bool IsPersistent()const{return true;}
 mutable int calls=0;mutable int p=-1,f=-1;mutable bool b=false;mutable FMaterialCompiler*c=nullptr;
 virtual int32 CompilePropertyAndSetMaterialProperty(EMaterialProperty P,FMaterialCompiler*C,EShaderFrequency F,bool B)const{
 calls++;p=P;c=C;f=F;b=B;return -217;}
};
RESOURCE
int main(){FWeaponShaderResource r;FMaterialCompiler c;
 for(int p=0;p<24;p++)for(int f=0;f<6;f++)for(int b=0;b<2;b++){
 int old=r.TranslationRequests;assert(r.CompilePropertyAndSetMaterialProperty(p,&c,f,b)==-217);
 assert(r.TranslationRequests==old+1&&r.calls==old+1&&r.p==p&&r.c==&c&&r.f==f&&r.b==bool(b));}
}
'''.replace('RESOURCE',resource)
        compile_run(code)

    def test_actual_owner_drains_before_delete_and_retains_undrained(self):
        text=HEADER.read_text()
        owner=text[text.index('struct FWeaponShaderOwner'):text.index('static const TCHAR* WSPOrigin')]
        code=r'''
#include <cassert>
#define TEXT(x) x
int logs=0,finishes=0,destroys=0;bool done=true;
#define UE_LOG(...) (++logs)
struct FWeaponShaderResource {void FinishCompilation(){finishes++;}bool IsCompilationFinished(){return done;}
 ~FWeaponShaderResource(){assert(finishes>destroys);destroys++;}};
OWNER
int main(){
 {FWeaponShaderOwner owner;}assert(finishes==1&&destroys==1&&logs==0);
 done=false;FWeaponShaderResource* retained;
 {FWeaponShaderOwner owner;retained=owner.Resource;}assert(finishes==2&&destroys==1&&logs==1);
 done=true;retained->FinishCompilation();delete retained;assert(destroys==2);
}
'''.replace('OWNER',owner)
        compile_run(code)

    def test_actual_map_acceptance_rejects_completion_only_and_wrong_identity_subset(self):
        body=F.method(HEADER.read_text(),'static int32 WeaponShaderProbe(')
        predicate=body.split('const bool ValidMap = ',1)[1].split(';',1)[0]
        code=r'''
#include <cassert>
const int SP_OPENGL_ES2_WEBGL=7;namespace ERHIFeatureLevel{const int ES2=0;}
struct ID{int n=4;};struct MapType{bool final=true,success=true;int platform=7;ID id;
 bool IsCompilationFinalized(){return final;}bool CompiledSuccessfully(){return success;}
 int GetShaderPlatform(){return platform;}ID GetShaderMapId(){return id;}};
struct ResourceType{bool valid=true;int feature=0,quality=2;
 bool HasValidGameThreadShaderMap(){return valid;}int GetFeatureLevel(){return feature;}int GetQualityLevel(){return quality;}};
struct ErrorsType{int n=0;int Num()const{return n;}};
bool WSPMaterialInstanceIdentitySubset(ID a,ID b){return a.n==b.n;}
bool evaluate(bool Cached,ResourceType*Resource,MapType*Map,ErrorsType Errors,ID Requested,int Quality){return PREDICATE;}
int main(){
 for(int fault=0;fault<10;fault++){
 ResourceType r;MapType m;ErrorsType e;ID id;bool cached=true;MapType*mp=&m;
 if(fault==1)cached=false;if(fault==2)r.valid=false;if(fault==3)mp=nullptr;if(fault==4)m.final=false;
 if(fault==5)m.success=false;if(fault==6)m.platform=8;if(fault==7)m.id.n=5;if(fault==8)r.quality=1;if(fault==9)e.n=1;
 assert(evaluate(cached,&r,mp,e,id,2)==(fault==0));}
 ResourceType r;MapType m;ErrorsType e;ID id;r.feature=1;assert(!evaluate(true,&r,&m,e,id,2));
}
'''.replace('PREDICATE',predicate)
        compile_run(code)

    def test_actual_origin_labels_do_not_overclaim_new_jobs(self):
        body=F.method(HEADER.read_text(),'static const TCHAR* WSPOrigin(')
        code=r'''
#include <cassert>
#include <string>
using int32=int;using TCHAR=char;
#define TEXT(x) x
BODY
int main(){assert(std::string(WSPOrigin(1,false))=="translation-observed");
 assert(std::string(WSPOrigin(1,true))=="translation-observed");
 assert(std::string(WSPOrigin(0,true))=="no-local-translation-pending-or-shared");
 assert(std::string(WSPOrigin(0,false))=="no-local-translation-complete-at-return");}
'''.replace('BODY',body)
        compile_run(code)
        self.assertIn('newShaderJobs=unknown',HEADER.read_text())
        self.assertIn('identityCheck=material-instance-subset',HEADER.read_text())
        subset=F.method(HEADER.read_text(),'static bool WSPMaterialInstanceIdentitySubset(')
        for field in ('ShaderTypeDependencies','ShaderPipelineTypeDependencies','VertexFactoryTypeDependencies'):
            self.assertNotIn(field,subset)
            self.assertIn(field,HEADER.read_text())
        self.assertIn('not full-ID equality',HEADER.read_text())

    def test_fixed_scope_prior_verify_and_six_drained_resources(self):
        text=HEADER.read_text()
        for forbidden in ('SavePackage','Policy.Save','SetParent','MarkPackageDirty','UpdateFromFunctionResource','BeginCacheForCookedPlatformData','CacheResourceShadersForCooking','SetGameThreadShaderMap','SetRenderingThreadShaderMap','FMaterialShaderMap::FindId'):
            self.assertNotIn(forbidden,text)
        self.assertIn('WeaponTessellationUpgrade(Params, true)',text)
        self.assertEqual(text.count('TEXT("/Game/RestrictedAssets/Weapons/Enforcer/'),2)
        self.assertIn('Resources == 6',text)
        self.assertIn('Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false)',text)
        self.assertIn('Resource->SetMaterial(Master, Quality, true, ERHIFeatureLevel::ES2, MI)',text)
        self.assertIn('MRStatic(Requested.ParameterSet)',text)
        self.assertIn('MRStatic(Effective)',text)
        self.assertIn('Proof.Check(MasterHash)',text)
        body=F.method(text,'static int32 WeaponShaderProbe(')
        cached=body.index('const bool Cached =')
        finish=body.index('Resource->FinishCompilation();',cached)
        self.assertNotIn('return ',body[cached:finish])
        self.assertLess(finish,body.index('const bool ValidMap'))
        self.assertIn('Samplers >= 0 && Samplers <= 16',body)
        self.assertIn('FMath::Min(Errors.Num(), 8)',body)

    def test_pinned_cache_overload_and_virtual_id_include_static_parameters(self):
        shared=self.source('MaterialShared.cpp','1dff15c0b80b3818055d654144dba9a346d8d471540854f17d4d572492f37f32')
        method=F.method(shared,'bool FMaterial::CacheShaders(EShaderPlatform Platform, bool bApplyCompletedShaderMapForRendering)')
        self.assertIn('GetShaderMapId(Platform, NoStaticParametersId)',method)
        self.assertIn('CacheShaders(NoStaticParametersId, Platform, bApplyCompletedShaderMapForRendering)',method)
        material=(PRIVATE_SOURCE/'Material.cpp').read_text(encoding='utf-8-sig')
        body=F.method(material,'void FMaterialResource::GetShaderMapId(')
        self.assertIn('MaterialInstance->GetBasePropertyOverridesHash(OutId.BasePropertyOverridesHash)',body)
        self.assertIn('MaterialInstance->GetStaticParameterValues(CompositedStaticParameters)',body)
        self.assertIn('OutId.ParameterSet = CompositedStaticParameters',body)
        header=(PRIVATE_SOURCE/'MaterialShared.h').read_text(encoding='utf-8-sig')
        for token in ('ENGINE_API FMaterialResource();','ENGINE_API void FinishCompilation();','ENGINE_API bool IsCompilationFinished() const;',
                      'ENGINE_API bool HasValidGameThreadShaderMap() const;','ENGINE_API int32 GetSamplerUsage() const;',
                      'ENGINE_API bool CacheShaders(const FMaterialShaderMapId& ShaderMapId, EShaderPlatform Platform, bool bApplyCompletedShaderMapForRendering);',
                      'ENGINE_API virtual void GetShaderMapId(EShaderPlatform Platform, FMaterialShaderMapId& OutId) const override;'):
            self.assertIn(token,header)
        # Cached completion is explicitly weaker than successful compilation.
        valid=F.method(shared,'bool FMaterial::HasValidGameThreadShaderMap() const')
        self.assertNotIn('CompiledSuccessfully',valid)
        begin=F.method(shared,'bool FMaterial::BeginCompileShaderMap(')
        self.assertIn('MaterialTranslator.Translate()',begin)
        self.assertIn('!GShaderCompilingManager->AllowAsynchronousShaderCompiling()',begin)

    def test_native_quality_graph_and_cook_policy_require_all_three(self):
        if PRIVATE_LOG is None or PRIVATE_SOURCE is None:self.skipTest('pass source/log for native quality policy evidence')
        rows=json.loads(F.W.baseline(PRIVATE_LOG,F.W.load_recipe()))['materials']
        master=next(r for r in rows if r['material'].split('.',1)[0]==F.W.report.MASTER)
        switches=[n for n in master['nodes'] if n['class']=='MaterialExpressionQualitySwitch']
        self.assertEqual(len(switches),1)
        switch=switches[0]
        self.assertTrue(switch['path'].endswith('MF_Oilness:MaterialExpressionQualitySwitch_0'))
        self.assertEqual([p['name']for p in switch['inputs']],['Default','Low','High','Medium'])
        self.assertTrue(all(p['expression']for p in switch['inputs']))
        material=(PRIVATE_SOURCE/'Material.cpp').read_text(encoding='utf-8-sig')
        body=F.method(material,'void UMaterial::GetQualityLevelNodeUsage(')
        self.assertIn('SwitchNode->Inputs[InputIndex].IsConnected()',body)
        self.assertIn('OutQualityLevelsUsed[InputIndex] = true;',body)
        instance=self.source('MaterialInstance.cpp','28d2409e0c7c7e30c42a7e8b9b9f56605962d5bbac5629e882c45bcf2f3b4668')
        cook=F.method(instance,'void UMaterialInstance::CacheResourceShadersForCooking(')
        self.assertIn('QualityLevelIndex < EMaterialQualityLevel::Num',cook)
        self.assertIn('QualityLevelsUsed[QualityLevelIndex]',cook)
        self.assertIn('CacheShadersForResources(ShaderPlatform, ResourcesToCache, false)',cook)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private-source-dir',type=Path);p.add_argument('--private-log',type=Path)
    args,rest=p.parse_known_args();PRIVATE_SOURCE,PRIVATE_LOG=args.private_source_dir,args.private_log
    unittest.main(argv=[sys.argv[0]]+rest)
