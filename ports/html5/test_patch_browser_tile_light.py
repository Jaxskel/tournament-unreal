"""Generated fixtures, plus an optional private pinned source roundtrip."""
import hashlib, importlib.util, os, shutil, subprocess, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('tile',Path(__file__).with_name('patch-browser-tile-light.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
FIXTURE='''void FRendererModule::DrawTileMesh(int fixture)
{
    GSystemTextures.InitializeTextures(RHICmdList, FeatureLevel);
    DrawFixture();
}
'''
a,b=m.body_span(FIXTURE)
FIXTURE_HASH=hashlib.sha256(FIXTURE[a:b].encode()).hexdigest()

class TilePatch(unittest.TestCase):
 def transform(self,text):
  with patch.object(m,'EXPECTED_BODY_SHA256',FIXTURE_HASH):return m.transform(text)
 def test_roundtrip_and_idempotence(self):
  for nl in ['\n','\r\n']:
   src=FIXTURE.replace('\n',nl);out=self.transform(src)
   self.assertEqual(self.transform(out),out)
   self.assertEqual(out.replace(''.join('    '+s+nl for s in m.INSERT.splitlines()),''),src)
   self.assertLess(out.index(m.ANCHOR),out.index(m.MARKER));self.assertLess(out.index(m.MARKER),out.index('DrawFixture'))
 def test_source_and_guard_changes_rejected(self):
  out=self.transform(FIXTURE)
  for text in [FIXTURE.replace('DrawFixture','OtherDraw'),out.replace('#if PLATFORM_HTML5_BROWSER','#if 1'),out.replace('SingleFrame','MultiFrame'),out.replace('!View.','View.'),out+'// '+m.MARKER,FIXTURE+FIXTURE,FIXTURE.replace('\n','\r\n',1)]:
   with self.subTest(text=text[:50]):
    with self.assertRaises(ValueError):self.transform(text)
 def test_block_moved_rejected(self):
  out=self.transform(FIXTURE);block=''.join('    '+s+'\n' for s in m.INSERT.splitlines())
  moved=out.replace(block,'').replace('    DrawFixture();\n','    DrawFixture();\n'+block)
  with self.assertRaises(ValueError):self.transform(moved)
 @unittest.skipUnless(shutil.which('c++'),'C++ compiler unavailable')
 def test_exact_insert_semantics(self):
  cpp=r'''
#include <cassert>
namespace ERHIFeatureLevel { enum Type { ES2,ES3_1,SM4,SM5 }; }
struct FMobileDirectionalLightShaderParameters { int typedDefault=77; };
int allocations=0; enum Usage { UniformBuffer_SingleFrame };
template<class T> struct TUniformBufferRef {
 int value=0; bool IsValid() const { return value!=0; }
 static TUniformBufferRef CreateUniformBufferImmediate(const T& p,Usage) {
  ++allocations;TUniformBufferRef b;b.value=p.typedDefault;return b;
 }
};
struct ViewType {TUniformBufferRef<FMobileDirectionalLightShaderParameters> MobileDirectionalLightUniformBuffers[4];};
void run(ViewType& View, ERHIFeatureLevel::Type FeatureLevel) {
INSERT
}
int main(){
 for(int level=0;level<4;++level)for(int valid=0;valid<2;++valid){
  ViewType v;v.MobileDirectionalLightUniformBuffers[0].value=valid?42:0;
  for(int i=1;i<4;++i)v.MobileDirectionalLightUniformBuffers[i].value=100+i;
  int before=allocations;run(v,static_cast<ERHIFeatureLevel::Type>(level));
  bool fill=PLATFORM_HTML5_BROWSER&&level<ERHIFeatureLevel::SM4&&!valid;
  assert(allocations-before==int(fill));
  assert(v.MobileDirectionalLightUniformBuffers[0].value==(fill?77:valid?42:0));
  for(int i=1;i<4;++i)assert(v.MobileDirectionalLightUniformBuffers[i].value==100+i);
 }
}
'''.replace('INSERT',m.INSERT)
  with tempfile.TemporaryDirectory() as tmp:
   src=Path(tmp)/'test.cpp';src.write_text(cpp)
   for flag in [0,1]:
    exe=Path(tmp)/('test'+str(flag));subprocess.run(['c++','-std=c++11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',f'-DPLATFORM_HTML5_BROWSER={flag}',str(src),'-o',str(exe)],check=True,capture_output=True);subprocess.run([str(exe)],check=True)
 def test_physical_preflight_backup_and_idempotence(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'EXPECTED_BODY_SHA256',FIXTURE_HASH):
   root=Path(tmp).resolve();(root/'.tournament-browser-port').touch()
   version=root/'Engine/Build/Build.version';version.parent.mkdir(parents=True);version.write_text(json.dumps(dict(MajorVersion=4,MinorVersion=15,PatchVersion=0,Changelist=3228288)))
   src=root/m.SOURCE_PATH;src.parent.mkdir(parents=True);original=b'\xef\xbb\xbf'+FIXTURE.replace('\n','\r\n').encode();src.write_bytes(original)
   backup=Path(str(src)+m.BACKUP_SUFFIX)
   self.assertEqual(m.patch(root)['status'],'would-patch');self.assertFalse(backup.exists());self.assertEqual(src.read_bytes(),original)
   self.assertEqual(m.patch(root,True)['status'],'patched');self.assertEqual(backup.read_bytes(),original)
   stamp=src.stat().st_mtime_ns;self.assertEqual(m.patch(root,True)['status'],'already-patched');self.assertEqual(src.stat().st_mtime_ns,stamp)
   backup.unlink()
   with self.assertRaises(ValueError):m.patch(root,True)
 @unittest.skipUnless(os.environ.get('PRIVATE_TILE_SOURCE'),'private source not supplied')
 def test_pinned_actual_source(self):
  src=Path(os.environ['PRIVATE_TILE_SOURCE']).read_text();out=m.transform(src)
  self.assertEqual(m.transform(out),out)
  self.assertEqual(out.replace(''.join('\t\t'+s+'\n' for s in m.INSERT.splitlines()),''),src)

if __name__=='__main__':unittest.main()
