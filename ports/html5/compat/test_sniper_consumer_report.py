"""Fixed-scope and extracted native pin-predicate tests for the sniper observer."""
from pathlib import Path
import re
import unittest

import test_weapon_fidelity as F
from test_weapon_tessellation import compile_run

ROOT = Path(__file__).parent
HEADER = ROOT / 'UT4Html5Compat/Source/UT4Html5Compat/Private/SniperConsumerReport.h'
EXPECTED = ['/Game/RestrictedAssets/Weapons/Sniper/BP_Sniper', '/Game/RestrictedAssets/Weapons/Sniper/BP_Sniper_Attach', '/Game/RestrictedAssets/Weapons/Sniper/Meshes/Sniper_Rifle_1p', '/Game/RestrictedAssets/Weapons/Sniper/Meshes/Sniper_Rifle_3p', '/Game/RestrictedAssets/Proto/UT3_Weapons/WP_SniperRifle/Meshes/SK_WP_SniperRifle_1P', '/Game/RestrictedAssets/Weapons/Sniper/Materials/M_Sniper_Rifle_Inst', '/Game/RestrictedAssets/Weapons/Sniper/Materials/Materials_thridperson/M_Sniper_Rifle_3P_Inst']


class SniperConsumerReportTests(unittest.TestCase):
    def test_compiled_fixed_scope_and_registry_roots(self):
        text = HEADER.read_text()
        block = re.search(r'static const TCHAR\* SCSniperRoots\[\] = \{(.*?)\n\};', text, re.S)
        self.assertIsNotNone(block)
        roots = re.findall(r'TEXT\("([^"]+)"\)', block.group(1))
        self.assertEqual(roots, EXPECTED)
        funcs = '\n'.join(F.method(text, s) for s in (
            'static int32 SCSniperRootCount()', 'static int32 SCSniperRootIndex(',
            'static bool SCSniperMIC(', 'static bool SCSniperBlueprint(',
            'static bool SCSniperRegistryRoot(',
        ))
        compile_run(r'''
#include <cassert>
#include <string>
using FString=std::string; using int32=int; using TCHAR=char;
#define TEXT(x) x
#define ARRAY_COUNT(a) (sizeof(a)/sizeof((a)[0]))
static const TCHAR* SCSniperRoots[] = {ROOTS};
FUNCS
int main(){
 assert(SCSniperRootCount()==7);
 for(int i=0;i<7;i++) assert(SCSniperRootIndex(SCSniperRoots[i])==i);
 assert(SCSniperRootIndex("/unlisted")==-1);
 for(int i=0;i<7;i++) assert(SCSniperMIC(i)==(i==5||i==6));
 for(int i=0;i<7;i++) assert(SCSniperBlueprint(i)==(i==0||i==1));
 for(int i=0;i<7;i++) assert(SCSniperRegistryRoot(i)==(i>=0&&i<7));
}
'''.replace('ROOTS', ','.join('"'+r+'"' for r in roots)).replace('FUNCS', funcs))

    def test_actual_native_pin_predicate_accepts_exact_and_rejects_drift(self):
        text = HEADER.read_text()
        body = F.method(text, 'static bool SCSniperPinMatches(')
        compile_run(r'''
#include <cassert>
#include <string>
#include <algorithm>
using int64=long long;
enum class ESearchCase { IgnoreCase };
struct FString {
 std::string v; FString(const char* s=""):v(s){} int Len()const{return (int)v.size();}
 bool Equals(const FString& b, ESearchCase)const {auto a=v,c=b.v;std::transform(a.begin(),a.end(),a.begin(),::tolower);std::transform(c.begin(),c.end(),c.begin(),::tolower);return a==c;}
 bool operator==(const FString& b)const{return v==b.v;}
};
BODY
int main(){FString p("F:/project/Content/x.uasset"),h("0123456789012345678901234567890123456789");
 assert(SCSniperPinMatches(p,p,h,h,17,17));
 FString upper("012345678901234567890123456789012345678A");
 assert(!SCSniperPinMatches(p,p,h,upper,17,17));
 assert(!SCSniperPinMatches(p,FString("F:/other/x.uasset"),h,h,17,17));
 assert(!SCSniperPinMatches(p,p,h,h,17,16));
 assert(!SCSniperPinMatches(p,p,h,h,0,0));
 assert(!SCSniperPinMatches(p,p,FString("bad"),h,17,17));}
'''.replace('BODY', body))

    def test_all_roots_rechecked_around_loads_and_report_stays_observational(self):
        text = HEADER.read_text()
        check = F.method(text, 'bool Check() const')
        for needle in ('HashFile(Path)', 'FPackageName::DoesPackageExist', 'X.Selected != SelectedExpected',
                       'X.Original != OriginalExpected', 'HashFile(X.Selected)', 'HashFile(X.Original)',
                       'SCSniperPinMatches'):
            self.assertIn(needle, check)
        run = F.method(text, 'static int32 SniperConsumerReport(')
        self.assertEqual(run.count('Inputs.Check()'), 3)  # input admission, before/after each root, final
        self.assertLess(run.index('Inputs.Check()'), run.index('LoadObject<UObject>'))
        self.assertLess(run.index('LoadObject<UObject>'), run.index('!Inputs.Check()', run.index('LoadObject<UObject>')))
        self.assertIn('normalization_attributed', run)
        self.assertIn('new_dirty_observation', run)
        self.assertIn('Registry.GetReferencers', text)
        self.assertIn('Registry.GetAssetsByPackageName', text)
        self.assertIn('unknown_root_class', text)
        for forbidden in ('SavePackage(', 'SpawnActor', 'Dispatch(', 'SetMaterial(', 'SetParent('):
            self.assertNotIn(forbidden, text)
        self.assertIn('live_closure_proven', run)


class SniperContractTests(unittest.TestCase):
    def test_actual_exact_paths_with_spec_comparison_copy(self):
        text = HEADER.read_text()
        helper = F.method((HEADER.parent / 'WeaponPreflightReport.h').read_text(), 'static bool WRExactPaths(')
        spec_check = F.method(text, 'bool SpecCheck() const')
        begin = spec_check.index('TArray<FString> Roots;')
        end = spec_check.index('return ReadJson', begin)
        setup = spec_check[begin:end]
        roots = re.search(r'static const TCHAR\* SCSniperRoots\[\] = \{.*?\n\};', text, re.S).group(0)
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
#include <memory>
#include <algorithm>
using FString=std::string; using TCHAR=char;
#define TEXT(x) x
namespace EJson { enum Type {String, Number}; }
template<class T> using TSharedPtr=std::shared_ptr<T>;
template<class T> struct TArray:std::vector<T> {
 void Add(const T& v){this->push_back(v);} int Num()const{return this->size();}
 void Sort(){std::sort(this->begin(),this->end());}
};
struct FJsonValue {EJson::Type Type=EJson::String; FString value; FString AsString()const{return value;} };
struct FJsonObject {
 TArray<TSharedPtr<FJsonValue>> values; bool present=true;
 bool TryGetArrayField(const TCHAR*,const TArray<TSharedPtr<FJsonValue>>*& out)const{out=&values;return present;}
};
ROOTS
HELPER
int main(){
 SETUP
 auto j=std::make_shared<FJsonObject>();
 for(const auto* p:SCSniperRoots){auto v=std::make_shared<FJsonValue>();v->value=p;j->values.Add(v);}
 const auto original=j->values;
 assert(WRExactPaths(j,"roots",Roots));
 std::reverse(j->values.begin(),j->values.end());assert(WRExactPaths(j,"roots",Roots));
 j->values.pop_back();assert(!WRExactPaths(j,"roots",Roots));
 j->values=original;j->values[0]=j->values[1];assert(!WRExactPaths(j,"roots",Roots));
 j->values=original;auto foreign=std::make_shared<FJsonValue>();foreign->value="/Game/foreign";
 j->values[0]=foreign;assert(!WRExactPaths(j,"roots",Roots));
 j->values=original;j->values.push_back(foreign);assert(!WRExactPaths(j,"roots",Roots));
 j->values=original;j->present=false;assert(!WRExactPaths(j,"roots",Roots));
 j->present=true;foreign->Type=EJson::Number;j->values[0]=foreign;assert(!WRExactPaths(j,"roots",Roots));
 // Sorting the local comparison copy must not reorder the admission manifest roots.
 assert(std::string(SCSniperRoots[0])=="/Game/RestrictedAssets/Weapons/Sniper/BP_Sniper");
 assert(std::string(SCSniperRoots[4]).find("/Proto/")!=std::string::npos);
}
'''.replace('ROOTS', roots).replace('HELPER', helper).replace('SETUP', setup))

    def test_fixed_spec_exact_scope(self):
        import json
        spec = json.loads((ROOT / 'report.sniper-consumer.json').read_text())
        self.assertEqual(spec['roots'], EXPECTED)
        self.assertEqual(len(set(EXPECTED)), 7)
        self.assertIs(spec['read_only'], True)
        self.assertIs(spec['repair_authority'], False)
        text = HEADER.read_text()
        check = F.method(text, 'bool SpecCheck() const')
        for term in ('HashFile(SpecPath)', 'WRExactPaths', 'ut4-sniper-consumer-spec-v1', '!Repair'):
            self.assertIn(term, check)

    def test_material_facts_and_existing_templates(self):
        text = HEADER.read_text()
        self.assertIn('MRDescribe(M, Registry, Facts)', text)
        self.assertIn('R.Emit(TEXT("material_facts"), Facts)', text)
        self.assertIn('R.Templates(G)', text)
        self.assertIn('!O->IsA(USkeletalMesh::StaticClass())', text)
        helper = (HEADER.parent / 'WeaponGrenadeAssignmentReport.h').read_text()
        templates = F.method(helper, 'bool Templates(')
        for term in ('GetDefaultObject(false)', 'GetActualComponentTemplate(Actual)', 'CreateRecordIterator'):
            self.assertIn(term, templates)
        self.assertIn('M->GetMaterial(I)', F.method(helper, 'bool Component('))

    def test_independent_original_and_selected_pins_no_equality_or_repair_claim(self):
        text = HEADER.read_text()
        check = F.method(text, 'bool Check() const')
        self.assertNotIn('X.SHA1.Equals(X.OriginalSHA1', check)
        for term in ('X.OriginalSHA1, HashFile(X.Original)', 'X.SHA1, HashFile(X.Selected)', 'SpecCheck()'):
            self.assertIn(term, check)
        read = F.method(text, 'bool Read()')
        for term in ('OB > 64 * 1024 * 1024', 'OB != double(int64(OB))', 'Values->Num() != SCSniperRootCount()'):
            self.assertIn(term, read)
        for term in ('SetDirtyFlag', 'SavePackage(', 'SpawnActor', 'ProcessEvent(', 'SetMaterial(', 'SetParent('):
            self.assertNotIn(term, text)

if __name__ == '__main__':
    unittest.main()
