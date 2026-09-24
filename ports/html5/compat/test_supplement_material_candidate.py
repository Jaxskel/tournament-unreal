"""Focused source-contract and extracted-call tests; UE shader validation is separate."""
from pathlib import Path
import unittest

import test_weapon_fidelity as F
from test_weapon_tessellation import compile_run

ROOT = Path(__file__).parent
PRIVATE = ROOT / 'UT4Html5Compat/Source/UT4Html5Compat/Private'
HEADER = PRIVATE / 'SupplementMaterialCandidate.h'
WGR = PRIVATE / 'WeaponGrenadeRepair.h'


class SupplementCandidateTests(unittest.TestCase):
    def test_actual_close_retains_undrained_resources_and_roots(self):
        body = F.method(HEADER.read_text(), 'bool Close()')
        compile_run(r'''
#include <cassert>
#include <vector>
#define TEXT(x) x
#define UE_LOG(...) ((void)0)
int finishes=0, deletes=0, unroots=0, drains=0; bool drain=true;
struct R { bool done=true; void FinishCompilation(){++finishes;} bool IsCompilationFinished(){return done;} ~R(){++deletes;} };
struct O {void RemoveFromRoot(){++unroots;}};
bool WSADrain(){++drains;return drain;}
struct S { bool Closed=false,CloseOK=false; R* Resource=nullptr; std::vector<O*> Roots;
BODY
};
int main(){
 for(int d=0;d<2;++d)for(int f=0;f<2;++f){
  finishes=deletes=unroots=drains=0;drain=d; O o;S s;s.Roots.push_back(&o);s.Resource=new R;s.Resource->done=f;
  const bool ok=d&&f;assert(s.Close()==ok);assert(finishes==1&&drains==1);assert(deletes==ok&&unroots==ok);
  assert(s.Close()==ok);assert(finishes==1&&drains==1);
  if(!ok){assert(s.Resource);delete s.Resource;}else assert(!s.Resource);
 }
}
'''.replace('BODY', body))

    def test_fixed_pins_and_exact_four_target_hierarchy(self):
        text = HEADER.read_text()
        for digest in (
            '632833e9512e68db02899077e06f5024555776ee',
            '98cd7456492bb522726946e963b18c4eebb075bc',
            'affc9650c6a6799313af639491529b074700cd75',
            'd3da11ac075007c5978a881ac8971f6df74c1de1',
            'b1ac8f1d13406a0eba56312f03d5b75e8637c7d3',
            '2c68ebcd0e2f971e055a5c2488c3dee93d8c029e',
        ):
            self.assertIn(digest, text)
        self.assertIn('Files->Values.Num() != 33', text)
        self.assertIn('WGRNumber(J, TEXT("saved"), 5)', text)
        self.assertIn('Original[I - 1]', text)
        self.assertIn('Copies[1]->SetParentEditorOnly(Copies[0])', text)
        self.assertIn('Copies[3]->SetParentEditorOnly(Copies[2])', text)
        self.assertNotIn('\u00ad', text)

    def test_instance_facts_pass_null_for_every_source_and_transient_copy(self):
        text = HEADER.read_text()
        body = F.method(text, 'bool InstanceFacts(')
        compile_run(r'''
#include <cassert>
#include <memory>
#include <string>
using FString=std::string;
struct UMaterialInstanceConstant { std::string path; };
struct UMaterial { std::string path; };
struct FJsonObject {};
template<class T> struct TSharedPtr { std::shared_ptr<T> p; bool IsValid() const{return bool(p);} };
int calls=0, parentRewrites=0, aliasLookups=0;
TSharedPtr<FJsonObject> WGRInstance(UMaterialInstanceConstant* M, UMaterial* V1, UMaterial* NewMaster) {
  assert(M && V1); ++calls;
  const bool fixedPair = M->path=="/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher" ||
                         M->path=="/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_Launcher_3P";
  if (NewMaster && fixedPair) ++parentRewrites;
  if (fixedPair && NewMaster) ++aliasLookups;
  return {std::make_shared<FJsonObject>()};
}
struct S { UMaterial* V1;
BODY
};
int main(){UMaterial v{"V1"}; S s{&v};
 const char* names[]={"/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon3p",
 "/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon_1p_Inst",
 "/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Grenade/MIC_Grenade",
 "/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_3P",
 "/Transient.UT4SupplementBioParent","/Transient.UT4SupplementBioChild",
 "/Transient.UT4SupplementGrenadeParent","/Transient.UT4SupplementGrenadeChild"};
 for(const auto* n:names){UMaterialInstanceConstant m{n};TSharedPtr<FJsonObject> out;assert(s.InstanceFacts(&m,out)&&out.IsValid());}
 assert(calls==8&&parentRewrites==0&&aliasLookups==0);
}
'''.replace('BODY', body))
        wgr = WGR.read_text()
        instance = F.method(wgr, 'static TSharedPtr<FJsonObject> WGRInstance(')
        self.assertIn('if (NewMaster && Package == WSATarget())', instance)
        self.assertIn('if (Pair && NewMaster)', instance)

    def test_compile_requires_all_four_instances_and_twelve_ordinary_maps(self):
        text = HEADER.read_text()
        body = F.method(text, 'bool Compile()')
        self.assertIn('I < 4', body)
        self.assertIn('Count == 12', body)
        self.assertIn('WGRInstance(M, V1, nullptr)', text)
        self.assertIn('EffectiveEqual', body)
        self.assertIn('if (!RawEqual || !EffectiveEqual)', body)
        equivalent = F.method(text, 'bool Equivalent()')
        self.assertIn('for (int32 I = 0; I < 4; ++I)', equivalent)
        self.assertIn('!RawFactsEqual(OriginalFacts, CopyFacts, I)', equivalent)
        self.assertIn('Member < 0 || Member >= 4', F.method(text, 'bool RawFactsEqual('))
        self.assertIn('SourceDump.Len() > 131072', body)
        self.assertIn('WSPQualityBranches()', F.method(text, 'bool Gather()'))
        self.assertIn('WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId())', body)
        self.assertIn('Samplers <= 16', body)
        self.assertLess(body.index('Resource->FinishCompilation()'), body.index('delete Resource'))

    def test_mismatch_logging_compiles_with_legacy_compound_statement_macro(self):
        text = HEADER.read_text()
        start = text.index('                if (!SourceSerialized || !CandidateSerialized')
        end = text.index('                return false;', start)
        compile_run(r'''
#include <cassert>
int logged=0;
#define UE_LOG(...) { ++logged; }
struct FString { int length; int Len()const{return length;} };
void diagnostic(bool SourceSerialized,bool CandidateSerialized,int a,int b){
 FString SourceDump{a},CandidateDump{b};
BLOCK
}
int main(){diagnostic(true,true,1,1);diagnostic(false,true,1,1);diagnostic(true,true,131073,1);assert(logged==3);}
'''.replace('BLOCK', text[start:end]))

    def test_candidate_has_no_persistent_or_alias_mutation_surface(self):
        text = HEADER.read_text()
        for forbidden in ('SavePackage', 'FSavePolicy', 'SetAlias(', 'WSAliases'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('Resource->SetMaterial('), 1)
        self.assertEqual(text.count('SetParentEditorOnly('), 4)
        self.assertIn('FParse::Value(*Params, TEXT("Receipt=")', text)
        self.assertIn('FParse::Value(*Params, TEXT("Manifest=")', text)
        self.assertIn('runtimeAcceptance=0', text)


    def test_actual_full_facts_comparator_rejects_raw_effective_and_hierarchy_drift(self):
        # Production comparator; engine/JSON plumbing are bounded host fixtures.
        body = F.method(HEADER.read_text(), "bool RawFactsEqual(")
        compile_run(r'''
#include <cassert>
#include <map>
#include <memory>
#include <string>
#include <vector>
using FString=std::string;using int32=int;
#define TEXT(x) x
template<class T> struct TSharedPtr {std::shared_ptr<T> p; TSharedPtr(){} TSharedPtr(std::shared_ptr<T> q):p(q){} bool IsValid() const{return bool(p);} T* operator->()const{return p.get();}};
struct FJsonObject {std::map<std::string,std::string> fields;TSharedPtr<FJsonObject> props;TSharedPtr<FJsonObject> GetObjectField(const char* k){assert(std::string(k)=="properties");return props;}};
TSharedPtr<FJsonObject> MRValue(TSharedPtr<FJsonObject> p){return p;}
struct Obj {FString path;FString GetPathName()const{return path;}};
struct LightingPolicy {int member=-1;bool Normalize(TSharedPtr<FJsonObject> a,TSharedPtr<FJsonObject> b)const {if(!a.IsValid()||!b.IsValid()||a->fields["LightingGuid"]!="source"+std::to_string(member)||b->fields["LightingGuid"]!="copy"+std::to_string(member))return false;b->fields["LightingGuid"]=a->fields["LightingGuid"];return true;}};
struct Canon {std::vector<std::pair<FString,FString>> pairs;void Add(FString a,FString b){pairs.emplace_back(a,b);}FString norm(FString x)const{for(auto& p:pairs){size_t n=0;while((n=x.find(p.first,n))!=FString::npos){x.replace(n,p.first.size(),p.second);n+=p.second.size();}}return x;}};
struct FWeaponRepair {Canon Canonical;bool Same(TSharedPtr<FJsonObject> a,TSharedPtr<FJsonObject>b)const{if(!a.IsValid()||!b.IsValid()||a->fields.size()!=b->fields.size())return false;for(auto& k:a->fields){auto it=b->fields.find(k.first);if(it==b->fields.end()||Canonical.norm(k.second)!=Canonical.norm(it->second))return false;}if(a->props.IsValid()!=b->props.IsValid())return false;return !a->props.IsValid()||Same(a->props,b->props);}};
struct S {Obj* CloneV1;Obj* V1;Obj* OldMaster;Obj* Copies[4];Obj* Original[4];LightingPolicy Lighting[5];
BODY
};
TSharedPtr<FJsonObject> facts(int m,bool copy){auto a=TSharedPtr<FJsonObject>(std::make_shared<FJsonObject>());a->props=TSharedPtr<FJsonObject>(std::make_shared<FJsonObject>());a->props->fields["LightingGuid"]=(copy?"copy":"source")+std::to_string(m);a->props->fields["rawOverride"]="unchanged";a->props->fields["Parent"]=(m%2)?(copy?"copy":"source")+std::to_string(m-1):(copy?"cloneMaster":"oldMaster");a->fields={{"parents",a->props->fields["Parent"]+"/"+(copy?"cloneMaster":"oldMaster")},{"static_overrides","raw-static"},{"static_effective","effective-static"},{"scalars","scale=1"},{"vectors","color=1,2,3,4"},{"textures","original-N-original-AGD"},{"blend",m<2?"masked":"opaque"},{"shading","defaultlit"},{"two_sided","false"},{"opacity_mask_clip",".3333"}};return a;}
int main(){Obj cm{"cloneMaster"},v{"v1Master"},old{"oldMaster"};Obj cp[4],orig[4];S s; s.CloneV1=&cm;s.V1=&v;s.OldMaster=&old;for(int i=0;i<4;i++){cp[i].path="copy"+std::to_string(i);orig[i].path="source"+std::to_string(i);s.Copies[i]=&cp[i];s.Original[i]=&orig[i];s.Lighting[i+1].member=i;}
 assert(!s.RawFactsEqual(facts(0,false),facts(0,true),-1)); assert(!s.RawFactsEqual(facts(0,false),facts(0,true),4));
 for(int i=0;i<4;i++) {assert(s.RawFactsEqual(facts(i,false),facts(i,true),i));
  for(auto k:{"parents","static_overrides","static_effective","scalars","vectors","textures","blend","shading","two_sided","opacity_mask_clip"}){auto a=facts(i,false),b=facts(i,true);b->fields[k]+="drift";assert(!s.RawFactsEqual(a,b,i));}
  for(auto k:{"rawOverride","Parent","LightingGuid"}){auto a=facts(i,false),b=facts(i,true);b->props->fields[k]+="drift";assert(!s.RawFactsEqual(a,b,i));}
  auto a=facts(i,false),b=facts(i,true);b->fields.erase("textures");assert(!s.RawFactsEqual(a,b,i));
 }
}
'''.replace("BODY", body))


if __name__ == '__main__':
    unittest.main()
