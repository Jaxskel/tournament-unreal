"""Owned-candidate failure-path host tests; native UE/shader validation is separate."""
from pathlib import Path
import unittest
import test_weapon_fidelity as F
from test_weapon_tessellation import compile_run

HEADER = Path(__file__).parent / 'UT4Html5Compat/Source/UT4Html5Compat/Private/EnforcerMaterialCandidate.h'


class CandidateTests(unittest.TestCase):
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

    def test_actual_entry_failures_never_emit_completion(self):
        body = F.method(HEADER.read_text(), 'static int32 EnforcerMaterialCandidate(')
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
using FString=std::string;using int32=int;
#define TEXT(x) x
bool GIsEditor=true;bool IsInGameThread(){return true;}
struct FApp {static bool CanEverRender(){return true;}};
struct FCommandLine {static const char* Get(){return "";}};
struct FParse {static void Value(const char*,const char*,FString& out){out="EnforcerMaterialCandidate";}static bool Param(const char*,const char*){return false;}};
const char* operator*(const FString& s){return s.c_str();}
int gate=0,step=0,complete=0,closed=0;std::vector<std::string> calls;
bool next(const char* n){calls.push_back(n);return ++step!=gate;}
struct FEnforcerCandidatePins {bool Read(const FString&){return next("pins");}};
struct FEnforcerCandidate {
 explicit FEnforcerCandidate(FEnforcerCandidatePins&){}~FEnforcerCandidate(){++closed;}
 bool Gather(){return next("gather");}bool Prepare(){return next("prepare");}bool Compile(){return next("compile");}
 bool Unchanged(){return next("unchanged");}bool Close(){return next("close");}
};
int WFRStop(const char*){return 1;}
#define UE_LOG(...) (++complete)
BODY
int main(){for(gate=0;gate<=7;++gate){step=complete=closed=0;calls.clear();int r=EnforcerMaterialCandidate("");
 assert((r==0)==(gate==0));assert(complete==(gate==0));assert(closed==(gate!=1));
 if(gate)assert(step==gate);else assert(step==7);
}}
'''.replace('BODY', body))

    def test_compile_uses_ordinary_resource_and_full_map_identity(self):
        text = HEADER.read_text()
        compile_body = F.method(text, 'bool Compile()')
        self.assertIn('new FWSAOrdinaryResource', compile_body)
        self.assertIn('WSAOrdinaryIDEqual(Requested, Map->GetShaderMapId())', compile_body)
        self.assertIn('MapOK ? Resource->GetSamplerUsage() : -1', compile_body)
        self.assertLess(compile_body.index('Resource->FinishCompilation()'), compile_body.index('delete Resource'))
        self.assertIn('return Count == 6;', compile_body)
        for forbidden in ('SavePackage', 'FSavePolicy', 'SetMaterial(', 'SetAlias(', 'SetName(', 'WSAliases'):
            if forbidden == 'SetMaterial(':
                self.assertEqual(text.count(forbidden), 1)  # Resource only, no component setter.
            else:
                self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('SetParentEditorOnly('), 1)
        self.assertIn('Copies[I]->SetParentEditorOnly(CloneMaster)', text)

    def test_fixed_generation_and_source_guards(self):
        text = HEADER.read_text()
        self.assertIn('81a52a86f48c7d58c812870c4fbd515b95cbfa51', text)
        self.assertIn('f276720c105f3d754a53ff7cf38bff24b514fceb', text)
        self.assertIn('Files->Values.Num() != 25', text)
        self.assertIn('HashFile(File).Equals(H, ESearchCase::IgnoreCase)', text)
        self.assertIn('for (const auto& KV : DependencyFiles)', text)
        self.assertIn('Dirty->SetBoolField', text)
        self.assertIn('Lighting[I + 1].Normalize', text)
        self.assertIn('Compare.Same(MRValue(A), MRValue(B))', text)
        self.assertIn('WSAOwnedGraph(Master, CloneMaster)', text)


if __name__ == '__main__':
    unittest.main()
