"""Execute actual admission code; conflicting diagnostic flags must never reach saves."""
import hashlib
from pathlib import Path
import re
import unittest
from test_weapon_tessellation import compile_run

CPP = Path(__file__).parent / 'UT4Html5Compat/Source/UT4Html5Compat/Private/UT4Html5Compat.cpp'
PATTERN = r'    // EXPLICIT_MODE_ADMISSION_BEGIN\n(.*?)    // EXPLICIT_MODE_ADMISSION_END\n'

def without_supplement_repair_dispatch(source):
    blocks = ['#include "SupplementMaterialRepair.h"\n']
    for mode, args in (('Preflight', 'false, true'), ('Apply', 'false'), ('Verify', 'true')):
        blocks.append('    if (Mode.Equals(TEXT("SupplementMaterialRepair%s"), ESearchCase::IgnoreCase))\n        return SupplementMaterialRepair(Params, %s);\n' % (mode, args))
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected one fixed supplement repair dispatch: ' + block)
        source = source.replace(block, '')
    return source


def without_supplement_consumer_dispatch(source):
    source = without_supplement_repair_dispatch(source)
    for block in ('#include "SupplementConsumerReport.h"\n',
                  '    if (Mode.Equals(TEXT("SupplementConsumerReport"), ESearchCase::IgnoreCase))\n        return SupplementConsumerReport(Params);\n'):
        if source.count(block) != 1:
            raise AssertionError('Expected one supplement consumer integration block: ' + block)
        source = source.replace(block, '')
    return source


def without_supplement_dispatch(source):
    source = without_supplement_consumer_dispatch(source)
    for block in ('#include "SupplementMaterialCandidate.h"\n',
                  '    if (Mode.Equals(TEXT("SupplementMaterialCandidate"), ESearchCase::IgnoreCase))\n        return SupplementMaterialCandidate(Params);\n'):
        if source.count(block) != 1:
            raise AssertionError('Expected one supplement integration block: ' + block)
        source = source.replace(block, '')
    return source


def without_enforcer_repair_dispatch(source):
    source = without_supplement_dispatch(source)
    blocks = ['#include "EnforcerMaterialRepair.h"\n']
    for mode, args in (('Preflight', 'false, true'), ('Apply', 'false'), ('Verify', 'true')):
        blocks.append('    if (Mode.Equals(TEXT("EnforcerMaterialRepair%s"), ESearchCase::IgnoreCase))\n        return EnforcerMaterialRepair(Params, %s);\n' % (mode, args))
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected one Enforcer repair dispatch: ' + block)
        source = source.replace(block, '')
    return source


def without_enforcer_dispatches(source):
    source = without_enforcer_repair_dispatch(source)
    mesh_blocks = ['// ENFORCER_MESH_DECLARATIONS_BEGIN\n#include "SkeletalMeshTypes.h"\n#include "RawIndexBuffer.h"\n#include "Serialization/BulkData.h"\n// ENFORCER_MESH_DECLARATIONS_END\n',
        '#include "EnforcerMeshInvariant.h"\n', '#include "EnforcerMeshReport.h"\n',
        '    if (Mode.Equals(TEXT("EnforcerMeshReport"), ESearchCase::IgnoreCase))\n        return EnforcerMeshReport(Params);\n']
    for block in mesh_blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected one Enforcer mesh integration block: ' + block)
        source = source.replace(block, '')
    for name in ('EnforcerMaterialCandidate', 'EnforcerConsumerReport'):
        blocks = ['#include "%s.h"\n' % name,
                  '    if (Mode.Equals(TEXT("%s"), ESearchCase::IgnoreCase))\n        return %s(Params);\n' % (name, name)]
        for block in blocks:
            if source.count(block) != 1:
                raise AssertionError('Expected one Enforcer integration block: ' + block)
            source = source.replace(block, '')
    return source


def without_grenade_repair_dispatch(source):
    source = without_enforcer_dispatches(source)
    blocks = ['#include "WeaponGrenadeRepair.h"\n',
        '    if (Mode.Equals(TEXT("WeaponGrenadeRepairApply"), ESearchCase::IgnoreCase))\n        return WeaponGrenadeRepair(Params, false);\n',
        '    if (Mode.Equals(TEXT("WeaponGrenadeRepairVerify"), ESearchCase::IgnoreCase))\n        return WeaponGrenadeRepair(Params, true);\n']
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected exactly one Grenade repair integration block: ' + block)
        source = source.replace(block, '')
    return source

def without_grenade_assignment_dispatch(source):
    source = without_grenade_repair_dispatch(source)
    blocks = ['#include "WeaponGrenadeAssignmentReport.h"\n',
        '    if (Mode.Equals(TEXT("WeaponGrenadeAssignmentReport"), ESearchCase::IgnoreCase))\n        return WeaponGrenadeAssignmentReport(Params);\n']
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected exactly one Grenade assignment integration block: ' + block)
        source = source.replace(block, '')
    return source

def without_alias_dispatch(source):
    source = without_grenade_assignment_dispatch(source)
    blocks = ['// SAMPLER_ALIAS_DECLARATIONS_BEGIN\n#include "ShaderCompiler.h"\n// SAMPLER_ALIAS_DECLARATIONS_END\n',
        '#include "WeaponSamplerAliasProbe.h"\n',
        '    if (Mode.Equals(TEXT("WeaponSamplerAliasProbe"), ESearchCase::IgnoreCase))\n        return WeaponSamplerAliasProbe(Params);\n']
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected exactly one sampler alias integration block: ' + block)
        source = source.replace(block, '')
    return source

def without_blueprint_dispatch(source):
    source = without_alias_dispatch(source)
    declarations = ('// WEAPON_BLUEPRINT_DECLARATIONS_BEGIN\n' +
        ''.join('#include "%s"\n' % n for n in ('Engine/Blueprint.h', 'EdGraph/EdGraph.h',
            'EdGraph/EdGraphNode.h', 'EdGraph/EdGraphPin.h')) + '// WEAPON_BLUEPRINT_DECLARATIONS_END\n')
    blocks = [declarations, '#include "WeaponBlueprintReport.h"\n',
        '    if (Mode.Equals(TEXT("WeaponBlueprintReport"), ESearchCase::IgnoreCase))\n        return WeaponBlueprintReport(Params);\n']
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected exactly one Blueprint observer integration block: ' + block)
        source = source.replace(block, '')
    return source

def without_readonly_dispatches(source):
    """Remove exact later dispatch additions, preserving each old hash proof."""
    names = ('AssetData.h', 'IAssetRegistry.h', 'HAL/FileManager.h', 'GameFramework/Actor.h',
             'Components/ActorComponent.h', 'Components/SceneComponent.h', 'Components/SkinnedMeshComponent.h',
             'Engine/BlueprintGeneratedClass.h', 'Engine/SimpleConstructionScript.h', 'Engine/SCS_Node.h',
             'Engine/InheritableComponentHandler.h', 'Engine/LevelStreaming.h', 'Engine/MapBuildDataRegistry.h',
             'LightMap.h', 'UObject/UObjectAnnotation.h')
    declarations = ('// WEAPON_USAGE_DECLARATIONS_BEGIN\n' + ''.join('#include "%s"\n' % n for n in names)
                    + '// WEAPON_USAGE_DECLARATIONS_END\n')
    source = without_blueprint_dispatch(source)
    blocks = [declarations]
    for name in ('WeaponUsageReport', 'WeaponShaderBatchProbe'):
        blocks += ['#include "%s.h"\n' % name,
                   '    if (Mode.Equals(TEXT("%s"), ESearchCase::IgnoreCase))\n        return %s(Params);\n' % (name, name)]
    for block in blocks:
        if source.count(block) != 1:
            raise AssertionError('Expected exactly one frozen readonly integration block: ' + block)
        source = source.replace(block, '')
    return source

class Admission(unittest.TestCase):
    def test_supplement_repair_dispatch_inverse_and_admission(self):
        source = CPP.read_text()
        self.assertEqual(hashlib.sha256(without_supplement_repair_dispatch(source).encode()).hexdigest(), '1e164763c40fbe2b1e9b8365087cbecf371aba9cc172a9bd3b258ea24410709a')
        for args in ('false, true', 'false', 'true'):
            self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return SupplementMaterialRepair(Params, ' + args + ');'))

    def test_supplement_consumer_inverse_and_admission_order(self):
        source = CPP.read_text()
        self.assertEqual(hashlib.sha256(without_supplement_consumer_dispatch(source).encode()).hexdigest(),
                         'f3b5786c6635d00e9cf7b75d53cf192bfce59da7f98acc0d762e7316df87c3fa')
        self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return SupplementConsumerReport(Params);'))

    def test_supplement_inverse_and_admission_order(self):
        source = CPP.read_text()
        self.assertEqual(hashlib.sha256(without_supplement_dispatch(source).encode()).hexdigest(),
                         '6a386c10e1752607e2515b64f4a6b27719f20e28d0bb4dd8a776e8d832594917')
        self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return SupplementMaterialCandidate(Params);'))

    def test_enforcer_repair_inverse_preserves_current_commandlet(self):
        source = CPP.read_text()
        self.assertEqual(hashlib.sha256(without_enforcer_repair_dispatch(source).encode()).hexdigest(),
                         '85aba8c32b63ee7d034ef50893405bc4763fc1c6e59d4ec0cf7e281cdfb68f8f')
        for args in ('false, true', 'false', 'true'):
            self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return EnforcerMaterialRepair(Params, ' + args + ');'))

    def test_enforcer_dispatch_inverse_preserves_prior_commandlet(self):
        source = CPP.read_text()
        self.assertEqual(hashlib.sha256(without_enforcer_dispatches(source).encode()).hexdigest(),
                         'd297876135b5a8fdfa773d6e67965bdf3465212766730c184e6e885c8ed6bbef')
        for name in ('EnforcerConsumerReport', 'EnforcerMaterialCandidate', 'EnforcerMeshReport'):
            self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return ' + name + '(Params);'))

    def test_grenade_repair_dispatch_inverse_preserves_prior_commandlet(self):
        source = CPP.read_text()
        self.assertEqual(hashlib.sha256(without_grenade_repair_dispatch(source).encode()).hexdigest(),
                         '2606a68f6b34924229ec322ccebbe82ab61eef2b02e9bd828fad580ff37358b6')
        self.assertLess(source.index('#include "WeaponSamplerAliasProbe.h"'), source.index('#include "WeaponGrenadeRepair.h"'))
        self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return WeaponGrenadeRepair(Params, false);'))
        self.assertLess(source.index('// EXPLICIT_MODE_ADMISSION_END'), source.index('return WeaponGrenadeRepair(Params, true);'))

    def test_only_admission_changed_and_it_precedes_every_dispatch(self):
        source = CPP.read_text()
        original, count = re.subn(PATTERN, '', without_readonly_dispatches(source), flags=re.S)
        self.assertEqual(count, 1)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),
                         '3bbbce4c601f75b5dc7ad4f57def0d9e15ff503b75c43104ede0e25822d88541')
        main = source[source.index('int32 UUT4Html5CompatCommandlet::Main('):]
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return MaterialPreflightReport('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponTessellationUpgrade('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponFidelityRepair('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponUsageReport('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponGrenadeAssignmentReport('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponShaderBatchProbe('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponBlueprintReport('))
        self.assertLess(main.index('// EXPLICIT_MODE_ADMISSION_END'), main.index('return WeaponSamplerAliasProbe('))

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
 const char* modes[]={"","WeaponRepairApply","WeaponRepairVerify","Apply","Verify","WeaponReport","BlobShadowExperiment","WeaponUsageReport","WeaponShaderBatchProbe","WeaponBlueprintReport","WeaponSamplerAliasProbe","EnforcerConsumerReport","EnforcerMaterialCandidate","SupplementMaterialCandidate","SupplementConsumerReport","EnforcerMeshReport","EnforcerMaterialRepairPreflight","EnforcerMaterialRepairApply","EnforcerMaterialRepairVerify"};
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
