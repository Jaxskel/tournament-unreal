#!/usr/bin/env python3
"""Bounded original tests; no UE editor, browser, assets or Windows processes.

Compiles the actual original shader BODY as host C++ with explicit helper/derivative
stubs, and the actual input-mask predicate. This is not HLSLcc/GLSL/UE compilation.
Private native evidence is optional; pass --private-baseline for all checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/BlobShadowExperiment.h'
SPEC = HERE / 'experiment.blob-shadow.json'
PRIVATE = None


def source(): return HEADER.read_text()


def body(text, name):
    start = text.index('{', text.index(name + '(')); depth = 1; end = start + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return text[start:end]


def shader(): return source().split('R"SHADER(', 1)[1].split(')SHADER"', 1)[0]


class ExperimentTests(unittest.TestCase):
    def test_recipe_is_byte_pinned(self):
        pin = re.search(r'BSXSpecSHA1 = TEXT\("([0-9a-f]{40})"\)', source()).group(1)
        self.assertEqual(hashlib.sha1(SPEC.read_bytes()).hexdigest(), pin)

    def test_exact_one_save_scope_and_no_blueprint_replacement(self):
        spec = json.loads(SPEC.read_text())
        self.assertEqual(spec['save_packages'], [spec['package']])
        self.assertTrue(spec['experimental']); self.assertFalse(spec['promotion_allowed'])
        text = source()
        self.assertEqual(text.count('Policy.Save('), 1)
        self.assertNotIn('SetParentEditorOnly', text)
        self.assertNotIn('SetMaterial(', text)
        self.assertNotIn('SavePackage(', text)  # Must use existing physical policy.
        self.assertNotIn('SetDirtyFlag(', text)

    def test_actual_scene_dependency_and_vector_width(self):
        text = source()
        self.assertIn('Custom->Inputs[0].Input.Expression = Depth;', text)
        self.assertIn('Custom->Inputs[1].Input.Expression = Camera;', text)
        self.assertIn('Depth->InputMode = EMaterialSceneAttributeInputMode::Coordinates;', text)
        self.assertIn('Custom->OutputType = CMOT_Float4;', text)
        self.assertNotIn('CalcSceneDepth(', shader())
        self.assertNotIn('SceneDepthTexture', shader())
        self.assertIn('ConvertToDeviceZ(ReceiverDepth)', shader())

    def test_no_unexported_expression_class_entry_points(self):
        text = source()
        for name in ('UMaterialExpressionSceneDepth', 'UMaterialExpressionCameraVectorWS'):
            for operation in ('Cast', 'CastChecked', 'NewObject', 'BSXAdd'):
                self.assertNotIn(operation + '<' + name + '>', text)
            self.assertNotIn(name + '::StaticClass', text)
        self.assertIn('NewObject<UMaterialExpression>(M, ExactClass, FName(Name))', text)
        self.assertIn('TEXT("/Script/Engine.")', body(text, 'BSXAddReflected'))
        self.assertIn('E->GetClass() != ExactClass', body(text, 'BSXAddReflected'))
        self.assertIn('E->GetClass() != ExactClass', body(text, 'BSXNode'))
        self.assertIn('ExactClass->IsChildOf(UMaterialExpression::StaticClass())', body(text, 'BSXAddReflected'))

    def test_derivatives_before_nonuniform_guard(self):
        code = shader()
        self.assertLess(code.index('ddx('), code.index('if ('))
        self.assertLess(code.index('ddy('), code.index('if ('))
        self.assertNotIn('discard', code)
        self.assertNotIn('clip(', code)

    def test_default_pin_is_copied_not_rebuilt(self):
        edit = body(source(), 'BSXEdit')
        self.assertIn('const FExpressionInput Original = *Mask->GetInput(0);', edit)
        self.assertIn('Switch->Default = Original;', edit)
        self.assertIn('Mask->GetInput(0)->Expression = Switch;', edit)
        self.assertNotIn('Mask->GetInput(0)->Mask', edit)
        self.assertNotIn('WorldPositionOffset', edit)

    def test_baseline_and_pristine_bytes_precede_edit_and_save(self):
        code = body(source(), 'BlobShadowExperiment')
        edit = code.index('BSXEdit(M)'); save = code.index('Policy.Save(M)')
        self.assertLess(code.index('BSXFacts(M, MasterBase, Registry, Verify'), edit)
        self.assertLess(code.index('BSXDisk(Pins, Verify)'), edit)
        self.assertLess(code.index('HashFile(SourceFile).Equals(PristineHash'), edit)
        self.assertLess(code.index('BSXFacts(M, MasterBase, Registry, true'), save)
        self.assertLess(code.index('BSXDisk(Pins, false)'), save)
        self.assertLess(code.index('Policy.Check(BSXPackage())'), save)

    def test_verify_and_report_do_not_enter_edit_block(self):
        code = body(source(), 'BlobShadowExperiment')
        self.assertIn('const bool Apply = Action == TEXT("Apply")', code)
        region = code[code.index('if (Apply)\n    {'):]
        self.assertLess(region.index('BSXEdit(M)'), region.index('Policy.Save(M)'))
        self.assertIn('Str(Previous, TEXT("target_sha1")) != HashFile(Target)', code)
        self.assertIn('BSXField(Previous, Out, TEXT("added_expressions"))', code)

    def test_no_visual_success_or_implicit_opt_in(self):
        text = source()
        self.assertIn('AcknowledgeApproximateBlobNormal', text)
        self.assertIn('!FApp::CanEverRender()', text)
        for name in ('promotion_allowed', 'shader_compile_verified', 'browser_render_verified', 'native_gbuffer_parity'):
            self.assertIn('SetBoolField(TEXT("%s"), false)' % name, text)
        self.assertIn('Shader link alone is not visual acceptance', text)
        self.assertIn('Text.Len() > 128 * 1024', text)

    def test_source_and_aftermath_paths_are_guarded(self):
        text = source()
        for fragment in ('!Physical(SourceFile, false)', '!Within(SourceFile, Policy.OriginalRoot)',
                         'Within(SourceFile, Policy.ContentRoot)', 'Within(Aftermath, Policy.ContentRoot)',
                         'Within(Aftermath, Policy.OriginalRoot)', 'FPaths::FileExists(Aftermath)',
                         '!Policy.Read(Receipt, SpecPath, Saves)'):
            self.assertIn(fragment, text)

    def test_dispatch_inverse_preserves_frozen_existing_modes(self):
        cpp = HEADER.with_name('UT4Html5Compat.cpp').read_text()
        for name in ('Constant', 'FeatureLevelSwitch', 'SetMaterialAttributes', 'Custom', 'SceneDepth', 'CameraVectorWS'):
            line = '#include "Materials/MaterialExpression%s.h"\n' % name
            self.assertEqual(cpp.count(line), 1); cpp = cpp.replace(line, '')
        for name in ('WeaponFidelityRepair', 'BlobShadowExperiment'):
            line = '#include "%s.h"\n' % name
            self.assertEqual(cpp.count(line), 1); cpp = cpp.replace(line, '')
        for mode, call in (('WeaponRepairApply', 'WeaponFidelityRepair(Params, false)'),
                           ('WeaponRepairVerify', 'WeaponFidelityRepair(Params, true)'),
                           ('BlobShadowExperiment', 'BlobShadowExperiment(Params)')):
            block = '    if (Mode.Equals(TEXT("%s"), ESearchCase::IgnoreCase))\n        return %s;\n' % (mode, call)
            self.assertEqual(cpp.count(block), 1); cpp = cpp.replace(block, '')
        self.assertEqual(hashlib.sha256(cpp.encode()).hexdigest(),
                         '2ab000d06f3a3224077786775c5694196fa1b9c2820e408fdccc4c73aea8b7fc')

    def test_private_baseline_and_native_all_rgba_mask(self):
        if PRIVATE is None: self.skipTest('pass --private-baseline for licensed native evidence')
        spec = json.loads(SPEC.read_text()); raw = PRIVATE.read_bytes()
        self.assertEqual(hashlib.sha1(raw).hexdigest(), spec['baseline_sha1'])
        base = json.loads(raw); self.assertEqual(base['report_sha256'], spec['report_sha256'])
        primary = next(x for x in base['materials'] if x['class'] == 'Material')
        node = next(n for n in primary['nodes'] if n['path'].endswith(':MaterialExpressionComponentMask_4'))
        self.assertEqual(node['inputs'][0]['mask'], [1, 1, 1, 1, 1])
        self.assertTrue(node['inputs'][0]['expression'].endswith(':MaterialExpressionSceneTexture_3'))
        world = next(n for n in primary['nodes'] if n['path'] == node['inputs'][0]['expression'])
        self.assertEqual(world['properties']['SceneTextureId'], 'PPI_WorldNormal')
        self.assertTrue(primary['package_dirty_before_description'])
        self.assertEqual(primary['package_sha1'][spec['package']].lower(), spec['original_sha1'][spec['package']].lower())
        self.assertFalse(primary['properties']['bUseFullPrecision'])

    def test_actual_shader_body_and_mask_predicate_host_execution(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler: self.fail('Host C++ compiler required for original-body fixture')
        prefix = r'''
#include <cassert>
#include <cmath>
#include <limits>
struct float3 { float x,y,z; float3(float a=0,float b=0,float c=0):x(a),y(b),z(c){};
 float3 operator-()const{return {-x,-y,-z};} void operator*=(float a){x*=a;y*=a;z*=a;} };
struct float4 {float x,y,z,w; float4(float a=0,float b=0,float c=0,float d=0):x(a),y(b),z(c),w(d){};
 float4(float3 a,float d):x(a.x),y(a.y),z(a.z),w(d){};};
float dot(float3 a,float3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
float3 cross(float3 a,float3 b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
float rsqrt(float x){return 1/std::sqrt(x);}
struct {float4 SvPosition;} Parameters;
float3 dx(1,0,0),dy(0,1,0);int derivativeCalls=0;
float3 ddx(float3){++derivativeCalls;return dx;} float3 ddy(float3){++derivativeCalls;return dy;}
float ConvertToDeviceZ(float z){return 1/z;}
float3 SvPositionToResolvedTranslatedWorld(float4 s){return {s.x,s.y,s.z};}
float4 run(float ReceiverDepth,float3 CameraDirection) {
'''
        suffix = r'''
}
struct UMaterialExpression {};
using int32=int;
struct FExpressionInput {UMaterialExpression* Expression=nullptr; int OutputIndex=0;
 int Mask=0,MaskR=0,MaskG=0,MaskB=0,MaskA=0;};
'''
        predicate = 'static bool BSXPin(const FExpressionInput& P, UMaterialExpression* E, bool RGBA = false)\n' + body(source(), 'BSXPin')
        main = r'''
int main(){
 for(float d : {100.f,1000.f,65000.f}){
  derivativeCalls=0;auto a=run(d,{0,0,-1});assert(a.x==0&&a.y==0&&a.z==-1&&a.w==0);assert(derivativeCalls==2);
  a=run(d,{0,0,1});assert(a.z==1&&a.w==0);
 }
 for(float d : {0.f,-1.f,65504.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){
  derivativeCalls=0;auto a=run(d,{0,0,-1});assert(a.x==0&&a.y==0&&a.z==0&&a.w==0);assert(derivativeCalls==2);
 }
 dy=dx; auto a=run(1000,{0,0,-1});assert(a.z==0);
 dx={2,1,0};dy={0,2,3};a=run(1000,{0,0,-1});assert(a.z<0);
 assert(std::abs(a.x*a.x+a.y*a.y+a.z*a.z-1)<1e-5);
 UMaterialExpression old,other;FExpressionInput p;p.Expression=&old;
 assert(BSXPin(p,&old));assert(!BSXPin(p,&other));assert(!BSXPin(p,&old,true));
 p.Mask=p.MaskR=p.MaskG=p.MaskB=p.MaskA=1;assert(BSXPin(p,&old,true));assert(!BSXPin(p,&old));
 for(int* field : {&p.Mask,&p.MaskR,&p.MaskG,&p.MaskB,&p.MaskA}){*field=0;assert(!BSXPin(p,&old,true));*field=1;}
 p.OutputIndex=1;assert(!BSXPin(p,&old,true));
}
'''
        with tempfile.TemporaryDirectory(prefix='ut4-blob-body-') as temp:
            root = Path(temp); cpp = root/'body.cpp'; exe = root/'body-test'
            cpp.write_text('#include <initializer_list>\n' + prefix + shader() + suffix + predicate + main)
            result = subprocess.run([compiler, '-std=c++14', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-baseline', type=Path)
    args, rest = parser.parse_known_args(); PRIVATE = args.private_baseline
    unittest.main(argv=[__file__, *rest])
