"""Fixed-scope and extracted native pin-predicate tests for the supplement observer."""
from pathlib import Path
import re
import unittest

import test_weapon_fidelity as F
from test_weapon_tessellation import compile_run

ROOT = Path(__file__).parent
HEADER = ROOT / 'UT4Html5Compat/Source/UT4Html5Compat/Private/SupplementConsumerReport.h'
EXPECTED = [
    '/Game/RestrictedAssets/Weapons/BioRifle/BP_BioRifle',
    '/Game/RestrictedAssets/Weapons/BioRifle/BP_BioRifle_Attach',
    '/Game/RestrictedAssets/Weapons/BioRifle/Meshes/Bio_Rifle_1p',
    '/Game/RestrictedAssets/Weapons/BioRifle/Meshes/Bio_Rifle_3p',
    '/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_InGame4',
    '/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon3p',
    '/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_Weapon_1p_Inst',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/BP_GrenadeLauncher',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/BP_GrenadeLauncher_Attach',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Grenade/MIC_Grenade',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/Material_ThirdPerson/MIC_Grenade_3P',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher_1p',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher_1p_v0',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher_3p',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Launcher_ThirdPerson',
    '/Game/RestrictedAssets/Weapons/GrenadeLauncher/Meshes/Grenade_Primed',
]


class SupplementConsumerReportTests(unittest.TestCase):
    def test_compiled_fixed_scope_and_registry_roots(self):
        text = HEADER.read_text()
        block = re.search(r'static const TCHAR\* SCSupplementRoots\[\] = \{(.*?)\n\};', text, re.S)
        self.assertIsNotNone(block)
        roots = re.findall(r'TEXT\("([^"]+)"\)', block.group(1))
        self.assertEqual(roots, EXPECTED)
        funcs = '\n'.join(F.method(text, s) for s in (
            'static int32 SCSupplementRootCount()', 'static int32 SCSupplementRootIndex(',
            'static bool SCSupplementMIC(', 'static bool SCSupplementBlueprint(',
            'static bool SCSupplementRegistryRoot(',
        ))
        compile_run(r'''
#include <cassert>
#include <string>
using FString=std::string; using int32=int; using TCHAR=char;
#define TEXT(x) x
#define ARRAY_COUNT(a) (sizeof(a)/sizeof((a)[0]))
static const TCHAR* SCSupplementRoots[] = {ROOTS};
FUNCS
int main(){
 assert(SCSupplementRootCount()==17);
 for(int i=0;i<17;i++) assert(SCSupplementRootIndex(SCSupplementRoots[i])==i);
 assert(SCSupplementRootIndex("/unlisted")==-1);
 for(int i=0;i<17;i++) assert(SCSupplementMIC(i)==(i==5||i==6||i==9||i==10));
 for(int i=0;i<17;i++) assert(SCSupplementBlueprint(i)==(i==0||i==1||i==7||i==8));
 for(int i=0;i<17;i++) assert(SCSupplementRegistryRoot(i)==(i==4||i==5||i==6||i==9||i==10||i==11||i==13||i==15||i==16));
}
'''.replace('ROOTS', ','.join('"'+r+'"' for r in roots)).replace('FUNCS', funcs))

    def test_actual_native_pin_predicate_accepts_exact_and_rejects_drift(self):
        text = HEADER.read_text()
        body = F.method(text, 'static bool SCSupplementPinMatches(')
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
 assert(SCSupplementPinMatches(p,p,h,h,17,17));
 FString upper("012345678901234567890123456789012345678A");
 assert(!SCSupplementPinMatches(p,p,h,upper,17,17));
 assert(!SCSupplementPinMatches(p,FString("F:/other/x.uasset"),h,h,17,17));
 assert(!SCSupplementPinMatches(p,p,h,h,17,16));
 assert(!SCSupplementPinMatches(p,p,h,h,0,0));
 assert(!SCSupplementPinMatches(p,p,FString("bad"),h,17,17));}
'''.replace('BODY', body))

    def test_all_roots_rechecked_around_loads_and_report_stays_observational(self):
        text = HEADER.read_text()
        check = F.method(text, 'bool Check() const')
        for needle in ('HashFile(Path)', 'FPackageName::DoesPackageExist', 'X.Selected != SelectedExpected',
                       'X.Original != OriginalExpected', 'HashFile(X.Selected)', 'HashFile(X.Original)',
                       'SCSupplementPinMatches'):
            self.assertIn(needle, check)
        run = F.method(text, 'static int32 SupplementConsumerReport(')
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


if __name__ == '__main__':
    unittest.main()
