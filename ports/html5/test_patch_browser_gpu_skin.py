"""Original bounded fixtures; optional private actual-body compile/roundtrip."""
import argparse, contextlib, hashlib, importlib.util, io, json, os
from pathlib import Path
import shutil, subprocess, sys, tempfile, unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('gpu_skin',Path(__file__).with_name('patch-browser-gpu-skin.py'))
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
PRIVATE=None
PRODUCTION_SPECS=M.SPECS
RUNTIME_FIXTURE='''{
 const int32 MaxGPUSkinBones = GetFeatureLevelMaxNumberOfBones(FeatureLevel);
 const int32 MaxBonesPerChunk = GetMaxBonesPerSection();
 RETURN
}'''.replace('RETURN',M.RUNTIME_OLD)
CACHE_FIXTURE='''{
 CONDITION { return false; }
 return Material->IsUsedWithSkeletalMesh() || Material->IsSpecialEngineMaterial();
}'''.replace('CONDITION',M.CACHE_OLD)

def fixture(spec):
 body=RUNTIME_FIXTURE if spec['name']=='runtime' else CACHE_FIXTURE
 prefix=M.INCLUDE_ANCHOR+'\n' if spec['name']=='runtime' else ''
 return (prefix+spec['signature']+'\n'+body+'\n// unrelated fixture trailer\n').encode()

class Case(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.specs=[];self.sources=[]
  for spec in M.SPECS:
   source=fixture(spec);start,end=M.body_span(source.decode(),spec)
   self.specs.append(dict(spec,body_sha256=M.digest(source[start:end])));self.sources.append(source)
  self.scope=patch.object(M,'SPECS',tuple(self.specs));self.scope.start();self.addCleanup(self.scope.stop)
 def tree(self,crlf=False):
  (self.root/'.tournament-browser-port').touch();v=self.root/'Engine/Build/Build.version';v.parent.mkdir(parents=True)
  v.write_text(json.dumps(dict(MajorVersion=4,MinorVersion=15,PatchVersion=0,Changelist=3228288)))
  for spec,source in zip(self.specs,self.sources):
   p=self.root/spec['path'];p.parent.mkdir(parents=True,exist_ok=True)
   p.write_bytes(b'\xef\xbb\xbf'+source.replace(b'\n',b'\r\n') if crlf else source)
 def run_patch(self,apply=False):
  with contextlib.redirect_stdout(io.StringIO()):return M.patch(self.root,apply)
 def test_roundtrip_idempotence_and_outside_bytes(self):
  for spec,source in zip(self.specs,self.sources):
   for bom,nl in [(b'',b'\n'),(b'\xef\xbb\xbf',b'\r\n')]:
    inp=bom+source.replace(b'\n',nl);out=M.transform(inp,spec)
    self.assertEqual(out,M.transform(out,spec));self.assertTrue(out.endswith(b'// unrelated fixture trailer'+nl))
    self.assertEqual(out.replace(spec['new'].replace('\n',nl.decode()).encode(),spec['old'].encode()).replace(M.INCLUDE.replace('\n',nl.decode()).encode(),b''),inp)
 def test_body_near_misses_duplicate_and_moved_marker_rejected(self):
  for spec,source in zip(self.specs,self.sources):
   text=source.decode();out=M.transform(source,spec).decode()
   for bad in [text.replace(spec['old'],spec['old']+' /* drift */'),text+text,out+'// '+M.MARKER,out.replace(spec['new'],spec['new'].replace(M.MARKER,M.MARKER+'_ALTERED',1)),out.replace(spec['new'],spec['old'])+spec['new']]:
    with self.subTest(spec=spec['name'],bad=bad[-25:]),self.assertRaises(ValueError):M.transform(bad.encode(),spec)
 def test_mixed_newlines_and_include_drift_rejected(self):
  with self.assertRaises(ValueError):M.transform(self.sources[0].replace(b'\n',b'\r\n',1),self.specs[0])
  with self.assertRaises(ValueError):M.transform(self.sources[0].replace(M.INCLUDE_ANCHOR.encode(),b'#include "Other.h"'),self.specs[0])
 def test_preflight_no_writes_apply_backups_idempotence(self):
  self.tree(crlf=True);before={s['path']:(self.root/s['path']).read_bytes() for s in self.specs};self.run_patch()
  for s in self.specs:self.assertFalse(Path(str(self.root/s['path'])+M.BACKUP_SUFFIX).exists())
  self.run_patch(True);stamps=[(self.root/s['path']).stat().st_mtime_ns for s in self.specs];self.run_patch(True)
  self.assertEqual(stamps,[(self.root/s['path']).stat().st_mtime_ns for s in self.specs])
  for s in self.specs:self.assertEqual(Path(str(self.root/s['path'])+M.BACKUP_SUFFIX).read_bytes(),before[s['path']])
 def test_bad_second_body_prevents_all_writes(self):
  self.tree();p=self.root/self.specs[1]['path'];p.write_bytes(p.read_bytes().replace(b'return false',b'return true'))
  with self.assertRaises(ValueError):self.run_patch(True)
  self.assertEqual((self.root/self.specs[0]['path']).read_bytes(),self.sources[0]);self.assertFalse(list(self.root.rglob('*'+M.BACKUP_SUFFIX)))
 def test_bad_second_backup_prevents_all_writes(self):
  self.tree();Path(str(self.root/self.specs[1]['path'])+M.BACKUP_SUFFIX).write_bytes(b'unknown')
  with self.assertRaises(ValueError):self.run_patch(True)
  self.assertEqual((self.root/self.specs[0]['path']).read_bytes(),self.sources[0]);self.assertFalse(Path(str(self.root/self.specs[0]['path'])+M.BACKUP_SUFFIX).exists())
 def test_missing_or_modified_backup_after_apply_refused(self):
  self.tree();self.run_patch(True);b=Path(str(self.root/self.specs[0]['path'])+M.BACKUP_SUFFIX);old=b.read_bytes();b.unlink()
  with self.assertRaises(ValueError):self.run_patch(True)
  b.write_bytes(old.replace(b'const int32',b'const  int32',1))
  with self.assertRaises(ValueError):self.run_patch(True)
 def test_interrupted_pair_recoverable_from_exact_backups(self):
  self.tree();real=os.replace;count=0
  def replace(*args):
   nonlocal count
   count+=1
   if count==2:raise OSError('fixture interrupted second replacement')
   return real(*args)
  with patch.object(M.os,'replace',replace),self.assertRaises(OSError):self.run_patch(True)
  self.assertIn(M.MARKER.encode(),(self.root/self.specs[0]['path']).read_bytes());self.assertEqual((self.root/self.specs[1]['path']).read_bytes(),self.sources[1])
  self.run_patch(True);self.run_patch()
 def test_source_race_refuses_replacement(self):
  self.tree();real=M.recheck;count=0
  def check(item):
   nonlocal count
   count+=1
   if count==5:item['path'].write_bytes(item['source']+b'// concurrent\n')
   real(item)
  with patch.object(M,'recheck',check),self.assertRaises(ValueError):self.run_patch(True)
  self.assertNotIn(M.MARKER.encode(),(self.root/self.specs[0]['path']).read_bytes())
 def test_marker_version_and_hardlinks_refused(self):
  self.tree();marker=self.root/'.tournament-browser-port';marker.unlink()
  with self.assertRaises(ValueError):self.run_patch(True)
  marker.touch();v=self.root/'Engine/Build/Build.version';saved=v.read_bytes();v.write_text('{}')
  with self.assertRaises(ValueError):self.run_patch(True)
  v.write_bytes(saved);p=self.root/self.specs[0]['path'];os.link(p,self.root/'shared')
  with self.assertRaises(ValueError):self.run_patch(True)
 def test_linked_ancestor_refused(self):
  self.tree();alias=self.root/'alias'
  try:alias.symlink_to(self.root/'Engine',target_is_directory=True)
  except OSError as e:self.skipTest('Host cannot create symlink: '+str(e))
  with self.assertRaises(ValueError):M.physical(alias/'Build/Build.version')
 def test_exact_capability_js_missing_lost_low_recreated_errors(self):
  node=shutil.which('node')
  if not node:self.skipTest('Node unavailable')
  code='''const assert=require('node:assert/strict');
function check(Module){ BODY }
const canvas={};
function context(a=16,u=1024){return {canvas,MAX_VERTEX_ATTRIBS:1,MAX_VERTEX_UNIFORM_VECTORS:2,isContextLost:()=>false,getParameter:k=>k===1?a:u};}
assert.equal(check(undefined),0);assert.equal(check({}),0);
let m={canvas,ctx:context()};assert.equal(check(m),1);
for(const [a,u] of [[15,1024],[16,1023],[NaN,1024],[16,Infinity],['16',1024],[16,null]]){m.ctx=context(a,u);assert.equal(check(m),0);}
m.ctx=context(32,2048);assert.equal(check(m),1);
m.ctx.canvas={};assert.equal(check(m),0);
m.ctx=context();m.ctx.isContextLost=()=>true;assert.equal(check(m),0);
m.ctx=context();m.ctx.getParameter=()=>{throw Error('driver')};assert.equal(check(m),0);
m.ctx=context();delete m.ctx.isContextLost;assert.equal(check(m),0);
m.ctx=context();assert.equal(check(m),1);m.ctx=context(8,128);assert.equal(check(m),0);m.ctx=context();assert.equal(check(m),1);
'''.replace('BODY',M.CAPABILITY_JS)
  result=subprocess.run([node,'-e',code],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
 def compile_bodies(self,sources,specs):
  compiler=shutil.which('c++')
  if not compiler:self.skipTest('C++ compiler unavailable')
  bodies=[]
  for source,spec in zip(sources,specs):
   old=source.decode('utf-8-sig').replace('\r\n','\n');new=M.transform(source,spec).decode('utf-8-sig').replace('\r\n','\n')
   a,b=M.body_span(old,spec);c,d=M.body_span(new,spec);bodies.extend([old[a:b],new[c:d]])
  code=r'''
#include <cassert>
using int32=int;
namespace ERHIFeatureLevel {enum Type{ES2,ES3_1,SM4,SM5};}
enum EShaderPlatform{SP_OPENGL_ES2_WEBGL,SP_OPENGL_ES2_ANDROID,SP_OPENGL_ES2_IOS,SP_OPENGL_PCES2,SP_PCD3D_ES2,SP_METAL,SP_PCD3D_SM4,SP_PCD3D_SM5};
ERHIFeatureLevel::Type GetMaxSupportedFeatureLevel(EShaderPlatform p){return p<=SP_PCD3D_ES2?ERHIFeatureLevel::ES2:p==SP_METAL?ERHIFeatureLevel::ES3_1:p==SP_PCD3D_SM4?ERHIFeatureLevel::SM4:ERHIFeatureLevel::SM5;}
int GetFeatureLevelMaxNumberOfBones(ERHIFeatureLevel::Type f){return f==ERHIFeatureLevel::ES2?75:256;}
int palette=0,queries=0;bool extra=false,cap=false;
int GetMaxBonesPerSection(){return palette;}bool HasExtraBoneInfluences(){return extra;}
#define EM_ASM_INT(...) (++queries,cap?1:0)
bool originalRuntime(ERHIFeatureLevel::Type FeatureLevel) RUNTIME_OLD_BODY
bool changedRuntime(ERHIFeatureLevel::Type FeatureLevel) RUNTIME_NEW_BODY
struct FMaterial{bool used,special;bool IsUsedWithSkeletalMesh()const{return used;}bool IsSpecialEngineMaterial()const{return special;}};
struct FShaderType{};
template<bool bExtraBoneInfluencesT> bool originalCache(EShaderPlatform Platform,const FMaterial* Material,const FShaderType* ShaderType) CACHE_OLD_BODY
template<bool bExtraBoneInfluencesT> bool changedCache(EShaderPlatform Platform,const FMaterial* Material,const FShaderType* ShaderType) CACHE_NEW_BODY
int main(){
 for(int f=0;f<4;++f)for(int n:{0,74,75,76,256,257})for(int e=0;e<2;++e)for(int c=0;c<2;++c){
  auto feature=static_cast<ERHIFeatureLevel::Type>(f);palette=n;extra=e;cap=c;queries=0;
  bool old=originalRuntime(feature),now=changedRuntime(feature);
  bool eligible=PLATFORM_HTML5_BROWSER&&f==0&&n<=75&&e;
  assert(now==(eligible&&c?false:old));assert(queries==int(eligible));
 }
 for(int p=0;p<8;++p)for(int used=0;used<2;++used)for(int special=0;special<2;++special){
  FMaterial mat{bool(used),bool(special)};auto platform=static_cast<EShaderPlatform>(p);
  assert(changedCache<false>(platform,&mat,nullptr)==originalCache<false>(platform,&mat,nullptr));
  bool expected=p==SP_OPENGL_ES2_WEBGL?bool(used||special):originalCache<true>(platform,&mat,nullptr);
  assert(changedCache<true>(platform,&mat,nullptr)==expected);
 }
}
'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
  for key,body in zip(['RUNTIME_OLD_BODY','RUNTIME_NEW_BODY','CACHE_OLD_BODY','CACHE_NEW_BODY'],bodies):code=code.replace(key,body)
  source=self.root/'compiled.cpp';source.write_text(code)
  for browser in [0,1]:
   exe=self.root/('compiled'+str(browser));p=subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-DPLATFORM_HTML5_BROWSER='+str(browser),str(source),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);subprocess.run([str(exe)],check=True)
 def test_compiled_positive_negative_native_and_browser_fixture_bodies(self):self.compile_bodies(self.sources,self.specs)
 def test_private_actual_bodies_roundtrip_and_compiled_semantics(self):
  if not PRIVATE:self.skipTest('Supply --private-source-dir for pinned engine bodies')
  # Restore production pins, never rewrite the inspected files.
  specs=PRODUCTION_SPECS
  sources=[(PRIVATE/s['path'].name).read_bytes() for s in specs]
  for source,spec in zip(sources,specs):
   out=M.transform(source,spec);self.assertEqual(M.transform(out,spec),out)
   clean=out.decode('utf-8-sig').replace('\r\n','\n').replace(spec['new'],spec['old'],1).replace(M.INCLUDE,'',1)
   self.assertEqual(clean,source.decode('utf-8-sig').replace('\r\n','\n'))
  self.compile_bodies(sources,specs)

if __name__=='__main__':
 parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--private-source-dir',type=Path);args,rest=parser.parse_known_args();PRIVATE=args.private_source_dir
 unittest.main(argv=[sys.argv[0]]+rest)
