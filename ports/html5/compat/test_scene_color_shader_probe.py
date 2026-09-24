"""Focused local tests for the fixed read-only Bio glass shader probe.

These tests do not compile UE, launch shader jobs, or establish WebGL/render parity.
"""
import hashlib
import json
import argparse
from pathlib import Path
import re
import sys
import unittest

import test_weapon_tessellation as T

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/SceneColorShaderProbe.h'
OWNER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponShaderProbe.h'
CAPTURE = HERE.parents[4] / 'work/ut4-html5/scene-motion-1790037124212/report.json'
CAPTURE_SHA256 = 'fc5fa398876243015bbcc6001721fa1a7ce73652e79b8adad36298778e973f75'
MATERIAL_SHA256 = '9321f773745421303f9cc95931ac422c5c2a10361a09e9e05da458d83f74c817'
CPP_BASELINE_SHA256 = '5c48530a1a7b18e87440ab8d2390fe7281dadea9260e73e96e80f805a7953d6f'
PRIVATE_SOURCE_DIR = None
PRIVATE_CAPTURE = None
CPP = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/UT4Html5Compat.cpp'
PRIVATE_SOURCE_DIR = None
PRIVATE_CAPTURE = None
CPP = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/UT4Html5Compat.cpp'


class SceneColorProbeTests(unittest.TestCase):
    def setUp(self):
        self.text = HEADER.read_text()

    def test_only_two_pinned_glass_assets_and_fixed_six_shader_maps(self):
        self.assertIn('/Game/RestrictedAssets/Weapons/BioRifle/New/Bio_HazyGlass', self.text)
        self.assertIn('/Game/RestrictedAssets/Weapons/BioRifle/New/BIO_HazyGlass_1p', self.text)
        self.assertIn('FE39078269E9520697493A421D90BC9999FCB8BC', self.text)
        self.assertIn('1E4A99654A0694F3755F7937DA5175FDE28BCF87', self.text)
        self.assertIn('for (int32 AssetIndex = 0; AssetIndex < 2; ++AssetIndex)', self.text)
        self.assertIn('for (int32 Q = 0; Q < EMaterialQualityLevel::Num; ++Q)', self.text)
        self.assertIn('Resources == 6 && ValidResources == 6', self.text)
        self.assertIn('TEXT("SceneColorOriginalContent=")', self.text)

    def test_actual_map_acceptance_predicate_rejects_each_failed_gate(self):
        helper = self.text.split('static bool SCSHMapAccepted(', 1)[1].split('\n}\n\nstruct FSCSHFilePin', 1)[0]
        args, body = helper.split(')\n{', 1)
        code = r'''
#include <cassert>
using int32=int;
bool SCSHMapAccepted(ARGS){
BODY
}
int main(){
 assert(SCSHMapAccepted(true,true,true,true,true,true,true,true,true,0,16));
 assert(!SCSHMapAccepted(false,true,true,true,true,true,true,true,true,0,16));
 assert(!SCSHMapAccepted(true,false,true,true,true,true,true,true,true,0,16));
 assert(!SCSHMapAccepted(true,true,false,true,true,true,true,true,true,0,16));
 assert(!SCSHMapAccepted(true,true,true,false,true,true,true,true,true,0,16));
 assert(!SCSHMapAccepted(true,true,true,true,false,true,true,true,true,0,16));
 assert(!SCSHMapAccepted(true,true,true,true,true,false,true,true,true,0,16));
 assert(!SCSHMapAccepted(true,true,true,true,true,true,false,true,true,0,16));
 assert(!SCSHMapAccepted(true,true,true,true,true,true,true,false,true,0,16));
 assert(!SCSHMapAccepted(true,true,true,true,true,true,true,true,false,0,16));
 assert(!SCSHMapAccepted(true,true,true,true,true,true,true,true,true,1,16));
 assert(!SCSHMapAccepted(true,true,true,true,true,true,true,true,true,0,-1));
 assert(!SCSHMapAccepted(true,true,true,true,true,true,true,true,true,0,17));
} 
'''.replace('ARGS', args).replace('BODY', body)
        T.compile_run(code)

    def test_actual_junction_mapping_predicate_requires_every_pin(self):
        helper = self.text.split('static bool SCSHSelectedAccepted(', 1)[1].split('\n}\n\nstruct FSCSHFilePin', 1)[0]
        args, body = helper.split(')\n{', 1)
        code = r'''
#include <cassert>
using int32=int;
bool SCSHSelectedAccepted(ARGS){ BODY }
int main(){
 assert(SCSHSelectedAccepted(true,true,true,true,true));
 assert(!SCSHSelectedAccepted(false,true,true,true,true));
 assert(!SCSHSelectedAccepted(true,false,true,true,true));
 assert(!SCSHSelectedAccepted(true,true,false,true,true));
 assert(!SCSHSelectedAccepted(true,true,true,false,true));
 assert(!SCSHSelectedAccepted(true,true,true,true,false));
}
'''.replace('ARGS', args).replace('BODY', body)
        T.compile_run(code)

    def test_source_pins_bracket_loading_and_each_compile_is_drained(self):
        body = self.text.split('static int32 SceneColorShaderProbe(', 1)[1]
        self.assertLess(body.index('Pins.Read(OriginalContent)'), body.index('LoadPackage('))
        self.assertLess(body.index('Resource->CacheShaders(Requested, SP_OPENGL_ES2_WEBGL, false)'),
                        body.index('Resource->FinishCompilation();'))
        self.assertLess(body.index('Resource->FinishCompilation();'), body.index('Pins.Check();', body.index('Resource->FinishCompilation();')))
        owner = OWNER.read_text().split('struct FWeaponShaderOwner', 1)[1].split('static const TCHAR* WSPOrigin', 1)[0]
        self.assertIn('Resource->FinishCompilation();', owner)
        self.assertIn('if (Resource->IsCompilationFinished()) delete Resource;', owner)
        self.assertIn('NoStaticLighting', body)
        self.assertNotIn('NoStaticLighting = true', body)
        self.assertIn('FWURFile::Inspect(Row.Selected, false, Selected, &Mapping)', self.text)
        self.assertNotIn('Physical(Row.Selected', self.text)
        self.assertIn('Mapping.Target = OriginalContent;', self.text)
        self.assertIn('Selected.Target.Equals(Row.Original, ESearchCase::IgnoreCase)', self.text)

    def test_resource_receives_typed_instance_or_null_for_base(self):
        body = self.text.split('static int32 SceneColorShaderProbe(', 1)[1]
        self.assertIn('UMaterialInstance* ShaderInstance = AssetIndex == 0 ? nullptr : static_cast<UMaterialInstance*>(Instance);', body)
        self.assertIn('Resource->SetMaterial(Base, Quality, true, ERHIFeatureLevel::ES2, ShaderInstance);', body)
        self.assertNotIn('SetMaterial(Base, Quality, true, ERHIFeatureLevel::ES2, Material)', body)

    def test_domain_uses_umaterial_property_not_fmaterial_api(self):
        self.assertEqual(self.text.count('Base->MaterialDomain'), 2)
        self.assertIn('Base->MaterialDomain != MD_Surface', self.text)
        self.assertIn('Base->MaterialDomain == MD_Surface', self.text)
        self.assertNotIn('Base->GetMaterialDomain()', self.text)

    def test_pinned_umaterial_domain_declaration(self):
        if PRIVATE_SOURCE_DIR is None:
            self.skipTest('pass --private-source-dir for pinned Material.h declaration')
        material_header_path = PRIVATE_SOURCE_DIR / 'Material.h'
        material_bytes = material_header_path.read_bytes()
        self.assertEqual(hashlib.sha256(material_bytes).hexdigest(), MATERIAL_SHA256)
        material_header = material_bytes.decode('utf-8-sig')
        self.assertIn('TEnumAsByte<enum EMaterialDomain> MaterialDomain;', material_header)
        self.assertNotRegex(material_header, r'\bGetMaterialDomain\s*\(')

    def test_readonly_guards_and_no_asset_or_ddc_mutation_api(self):
        for flag in ('NoDependsGathering', 'Apply', 'Write', 'Save', 'SceneColorShaderApply', 'Manifest', 'Receipt'):
            self.assertIn(flag, self.text)
        for forbidden in ('SavePackage(', 'ClearAllCachedCookedPlatformData(', 'FlushShaderFileCache(',
                          'Modify('):
            self.assertNotIn(forbidden, self.text)
        self.assertNotRegex(self.text, r'\bbUsedWithStaticLighting\s*=(?!=)')
        self.assertNotRegex(self.text, r'\bParent\s*=(?!=)')
        self.assertIn('assetsSaved=0', self.text)
        self.assertIn('materialSettingsChanged=0', self.text)
        self.assertIn('diagnosticOnly=1', self.text)

    def test_captured_glass_failure_fixture_is_specific_and_stays_diagnostic(self):
        if PRIVATE_CAPTURE is None:
            self.skipTest('pass --private-capture for pinned native/browser glass failure capture')
        raw = PRIVATE_CAPTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CAPTURE_SHA256)
        capture = json.loads(raw)
        messages = '\n'.join(str(x) for x in capture.get('console', []))
        for package in ('Bio_HazyGlass.Bio_HazyGlass', 'BIO_HazyGlass_1p.BIO_HazyGlass_1p'):
            self.assertIn(package, messages)
        self.assertIn('Failed to compile', messages)
        self.assertIn('GLSL_ES2_WEBGL', messages)
        self.assertIn('Default Material will be used in game', messages)

    def test_cpp_dispatch_inverse_restores_pinned_baseline(self):
        text = CPP.read_text()
        include = '#include "SceneColorShaderProbe.h"\n'
        dispatch = ('    if (Mode.Equals(TEXT("SceneColorShaderProbe"), ESearchCase::IgnoreCase))\n'
                    '        return SceneColorShaderProbe(Params);\n')
        self.assertEqual(text.count(include), 1)
        self.assertEqual(text.count(dispatch), 1)
        inverse = text.replace(include, '', 1).replace(dispatch, '', 1)
        self.assertEqual(hashlib.sha256(inverse.encode()).hexdigest(), CPP_BASELINE_SHA256)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-source-dir', type=Path)
    parser.add_argument('--private-capture', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE_SOURCE_DIR = args.private_source_dir
    PRIVATE_CAPTURE = args.private_capture
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
