"""Execute actual admission code; conflicting diagnostic flags must never reach saves."""
import hashlib
from pathlib import Path
import re
import unittest
from test_weapon_tessellation import compile_run

CPP = Path(__file__).parent / 'UT4Html5Compat/Source/UT4Html5Compat/Private/UT4Html5Compat.cpp'
PATTERN = r'    // EXPLICIT_MODE_ADMISSION_BEGIN\n(.*?)    // EXPLICIT_MODE_ADMISSION_END\n'

class Admission(unittest.TestCase):
    def test_only_admission_changed_and_it_precedes_every_dispatch(self):
        source = CPP.read_text()
        original, count = re.subn(PATTERN, '', source, flags=re.S)
        self.assertEqual(count, 1)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),
                         '3bbbce4c601f75b5dc7ad4f57def0d9e15ff503b75c43104ede0e25822d88541')
        main = source[source.index('int32 UUT4Html5CompatCommandlet::Main('):]
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return MaterialPreflightReport('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponTessellationUpgrade('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponFidelityRepair('))

    def test_compiled_actual_guard_rejects_ambiguous_modes_before_side_effects(self):
        block = re.search(PATTERN, CPP.read_text(), re.S).group(1)
        compile_run(r'''
#include <cassert>
#include <sstream>
#include <string>
using int32=int;
#define TEXT(x) x
struct FString : std::string {
 using std::string::string;
 const char* operator*()const{return c_str();}
 bool IsEmpty()const{return empty();}
};
struct FParse {
 static bool Param(const char* args,const char* flag){
  std::istringstream stream(args);std::string item;
  while(stream>>item)if(item==std::string("-")+flag)return true;
  return false;
 }
};
int failures=0, reached=0;
bool Fail(const char*){++failures;return false;}
int admit(const FString& Params,const FString& Mode){
BLOCK
 ++reached;return 0;
}
int main(){
 const char* modes[]={"","WeaponRepairApply","WeaponRepairVerify","Apply","Verify","WeaponReport","BlobShadowExperiment"};
 const char* flags[]={"WeaponTessUpgrade","WeaponTessVerify","WeaponShaderProbe","WeaponShaderEnforcer1PHigh","WeaponShaderNoStaticLighting"};
 for(const char* mode:modes)for(int bits=0;bits<32;bits++){
  FString args;for(int i=0;i<5;i++)if(bits&(1<<i)){args+=" -";args+=flags[i];}
  // Permitted variant flags do not become operation selectors.
  args+=" -WeaponUV0 -WeaponTess1";
  const int operations=int(bool(bits&1))+int(bool(bits&2))+int(bool(bits&4));
  const bool rejected=operations>1||(operations&&mode[0])||((bits&24)&&!(bits&4));
  reached=failures=0;assert(admit(args,FString(mode))==int(rejected));
  assert(reached==int(!rejected));assert(failures==int(rejected));
 }
 // Explicit regression: diagnostic + Apply/Upgrade cannot enter saving dispatch.
 reached=0;assert(admit(FString("-WeaponShaderProbe -WeaponTessUpgrade"),FString(""))==1);assert(reached==0);
 reached=0;assert(admit(FString("-WeaponShaderProbe"),FString("WeaponRepairApply"))==1);assert(reached==0);
}
'''.replace('BLOCK', block))

if __name__ == '__main__':
    unittest.main()
