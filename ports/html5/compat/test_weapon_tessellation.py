"""Local-only proof, pinned-source and actual control-body tests; no UE/asset execution."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import test_weapon_fidelity as F

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponTessellationUpgrade.h'
PRIVATE_PROOF = None
PRIVATE_SOURCE = None
PRIVATE_LOG = None
PROOF_SHA256 = '0692e8d25917265381fa5ce73d5c307cb22abb0f3a1af399834606f6af54e2ea'
PROOF_SHA1 = 'f86076971bcdd3f4adee45ca27d1ec22da9f5f9b'
OLD_MASTER = '5d82999ff94ee56567fdcab1bd7918c5f533a7b2'
TESS_ID = 'A0119D44C456450D9C39C9331F72D8D1'


def compile_run(code):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise unittest.SkipTest('host C++ compiler required')
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / 'test.cpp').write_text(code)
        build = subprocess.run([compiler, '-std=c++14', str(p / 'test.cpp'), '-o', str(p / 'test')], capture_output=True, text=True)
        if build.returncode:
            raise AssertionError(build.stderr)
        run = subprocess.run([str(p / 'test')], capture_output=True, text=True)
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)


HOST_TYPES = r"""
#include <cassert>
#include <string>
#include <vector>
#include <memory>
#include <algorithm>
#include <cctype>
#define TEXT(x) x
using int32=int; using TCHAR=char;
namespace ESearchCase { enum Type {IgnoreCase}; }
struct FString : std::string {
 using std::string::string; FString(){} FString(const std::string& s):std::string(s){}
 const char* operator*() const{return c_str();} int Len()const{return size();}
 FString ToLower()const{FString s=*this;std::transform(s.begin(),s.end(),s.begin(),[](char c){return std::tolower(c);});return s;}
 bool Equals(const FString& b, ESearchCase::Type)const{return ToLower()==b.ToLower();}
 bool Contains(const FString& b)const{return find(b)!=npos;}
 bool EndsWith(const FString& b)const{return size()>=b.size()&&compare(size()-b.size(),b.size(),b)==0;}
};
template<class T> struct TSharedPtr : std::shared_ptr<T> {
 using std::shared_ptr<T>::shared_ptr; TSharedPtr(){} TSharedPtr(const std::shared_ptr<T>& p):std::shared_ptr<T>(p){}
 const TSharedPtr& ToSharedRef()const{return *this;}
};
template<class T> TSharedPtr<T> MakeShareable(T* p){return TSharedPtr<T>(p);}
template<class K,class V> struct TMap {
 struct Pair{K Key;V Value;}; std::vector<Pair> Values;
 auto begin()const{return Values.begin();} auto end()const{return Values.end();}
 bool Contains(const K& k)const{return Find(k)!=nullptr;} int Num()const{return Values.size();}
 const V* Find(const K& k)const{for(auto& p:Values)if(p.Key==k)return &p.Value;return nullptr;}
 V* Find(const K& k){for(auto& p:Values)if(p.Key==k)return &p.Value;return nullptr;}
 const V& FindChecked(const K& k)const{auto*p=Find(k);assert(p);return*p;}
 void Add(const K& k,const V& v){if(auto*p=Find(k))*p=v;else Values.push_back({k,v});}
};
struct FJsonObject;
struct FJsonValue{TSharedPtr<FJsonObject> Object;TSharedPtr<FJsonObject> AsObject()const{return Object;}};
struct FArray : std::vector<TSharedPtr<FJsonValue>> {int Num()const{return size();}};
struct FJsonObject {
 TMap<FString,FString> Strings; TMap<FString,TSharedPtr<FJsonObject>> Objects; TMap<FString,FArray> Arrays;
 const FArray& GetArrayField(const FString& k)const{return Arrays.FindChecked(k);}
 TSharedPtr<FJsonObject> GetObjectField(const FString& k)const{return Objects.FindChecked(k);}
 void SetStringField(const FString& k,const FString& v){Strings.Add(k,v);}
 void SetObjectField(const FString& k,TSharedPtr<FJsonObject> v){Objects.Add(k,v);}
 void SetBoolField(const FString&,bool){} void SetNumberField(const FString&,int){}
};
FString Str(TSharedPtr<FJsonObject> j,const char*k){auto*p=j->Strings.Find(k);return p?*p:FString();}
FString Full(const FString& p){return p;}
bool Within(const FString& p,const FString& r){return p==r||p.find(r+"/")==0;}
namespace FPaths {FString GameDir(){return "/selected/UnrealTournament";} FString GameContentDir(){return GameDir()+"/Content";}
FString GetPath(const FString&p){return p.substr(0,p.rfind('/'));}}
namespace FPackageName {FString LongPackageNameToFilename(const FString&p,const FString& ext){return FPaths::GameContentDir()+p.substr(5)+ext;}}
bool GamePackage(const FString&p){return p.find("/Game/")==0;}
struct DiskFile {FString hash;bool physical=true;}; TMap<FString,DiskFile> disk;
bool Physical(const FString&p,bool){auto*v=disk.Find(p);return v&&v->physical;}
FString HashFile(const FString&p){auto*v=disk.Find(p);return v?v->hash:FString();}
bool Fail(const FString&){return false;}
TSharedPtr<FJsonObject> captured;
bool ReadJson(const FString&,TSharedPtr<FJsonObject>& out){out=captured;return true;}
"""


class Tessellation(unittest.TestCase):
    def master(self):
        if PRIVATE_LOG is None:
            self.skipTest('pass --private-log for native all-branch evidence')
        rows = json.loads(F.W.baseline(PRIVATE_LOG, F.W.load_recipe()))['materials']
        return next(r for r in rows if r['material'].split('.', 1)[0] == F.W.report.MASTER)

    def source(self, file, sha):
        if PRIVATE_SOURCE is None:
            self.skipTest('pass --private-source-dir for pinned licensed sources')
        raw = (PRIVATE_SOURCE / file).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
        return raw.decode('utf-8-sig')

    def test_exact_inverse_preserves_all_old_variants_and_save_authority(self):
        F.without_tess(F.HEADER.read_text())
        text = HEADER.read_text()
        self.assertIn('WeaponFidelityRepair(Params, true, &R, Verify)', text)
        self.assertEqual(text.count('Policy.Save('), 1)
        self.assertIn('OnlyMaster.Add(WTUMaster().ToLower())', text)
        self.assertNotIn('Saves.Append', text)
        for forbidden in ('UpdateFromFunctionResource', 'SetMaterialFunction(', 'SetParentEditorOnly(', 'DuplicateObject', 'SetDirtyFlag', 'DeleteFile', 'MoveFile'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('->PostEditChange()'), 1)
        self.assertIn('Master->PostEditChange()', text)
        self.assertIn('if (VerifiedState) *VerifiedState = R;', F.HEADER.read_text())

    def test_native_refuses_standalone_eight_node_adoption(self):
        text = F.HEADER.read_text()
        admission = text.split('// WFR_TESS_ADMISSION_BEGIN')[1].split('// WFR_TESS_ADMISSION_END')[0]
        # Compile the actual admission expression, not a Python restatement.
        expression = re.search(r'if \((.*)\)\s*return WFRStop', admission, re.S).group(1)
        code = r'''
#include <cassert>
#define TEXT(x) x
struct ParamsType { bool uv, tess; const ParamsType* operator*() const {return this;} };
struct FParse { static bool Param(const ParamsType* p, const char* n) {return n[6]=='U' ? p->uv : p->tess;} };
bool reject(bool Verify, bool state, bool Tess1, ParamsType Params) { void* VerifiedState=state?&state:nullptr; return EXPRESSION; }
int main(){
 for(int v=0;v<2;v++) for(int s=0;s<2;s++) for(int t=0;t<2;t++) for(int u=0;u<2;u++) for(int f=0;f<2;f++) {
   bool expected=(s&&!v)||(t&&(!v||!s||!u))||(f&&!s);
   assert(reject(v,s,t,{bool(u),bool(f)})==expected);
 }
}
'''.replace('EXPRESSION', expression)
        compile_run(code)


    def test_actual_eight_node_constant_gate_rejects_wrong_value_owner_mode_or_shape(self):
        text = F.HEADER.read_text()
        body = text.split('// WFR_TESS_NODE_BEGIN\n')[1].split('// WFR_TESS_NODE_END')[0]
        code = r"""
#include <cassert>
#include <limits>
#define TEXT(x) x
const int MTM_NoTessellation=0;
struct Material {int D3D11TessellationMode=0;};
struct Inputs {int n=0;int Num()const{return n;}};
struct UMaterialExpressionConstant {float R=1;Material* Material=nullptr;void* Function=nullptr;Inputs input;Inputs GetInputs(){return input;}};
UMaterialExpressionConstant constant;bool absent=false;
UMaterialExpressionConstant* Node(void*,const char*,const char*){return absent?nullptr:&constant;}
template<class T>T* Cast(UMaterialExpressionConstant*p){return p;}
bool check(bool Tess1,bool Verify,bool UV0,Material* M){
BODY
return true;}
int main(){Material m,other;
 for(int fault=0;fault<10;fault++){
 constant=UMaterialExpressionConstant();constant.Material=&m;m.D3D11TessellationMode=0;absent=false;
 bool verify=true,uv=true;
 if(fault==1)absent=true;if(fault==2)constant.R=0;if(fault==3)constant.R=std::numeric_limits<float>::quiet_NaN();
 if(fault==4)constant.Material=&other;if(fault==5)constant.Function=&other;if(fault==6)constant.input.n=1;
 if(fault==7)m.D3D11TessellationMode=1;if(fault==8)verify=false;if(fault==9)uv=false;
 assert(check(true,verify,uv,&m)==(fault==0));
 }
}
""".replace('BODY', body)
        # Avoid a host C++ name-hiding diagnostic; UE uses UMaterial as its type.
        code = code.replace('struct Material ', 'struct UMaterial ').replace('Material*', 'UMaterial*').replace('Material m,other;', 'UMaterial m,other;')
        compile_run(code)

    def test_all_original_nodes_and_all_reachable_tess_branches_default_one(self):
        master = self.master()
        makes = [n for n in master['nodes'] if n['class'] == 'MaterialExpressionMakeMaterialAttributes']
        sets = [n for n in master['nodes'] if n['class'] == 'MaterialExpressionSetMaterialAttributes']
        self.assertEqual((len(makes), len(sets)), (8, 15))
        for n in makes:
            pins = [i for i in n['inputs'] if i['name'] == 'TessellationMultiplier']
            self.assertEqual(len(pins), 1)
            self.assertFalse(pins[0]['expression'])
        for n in sets:
            self.assertNotIn(TESS_ID, n['properties']['AttributeSetTypes'])
        proof = F.prove_uv0_identity(master, 'TessellationMultiplier', TESS_ID, 'one')
        self.assertEqual(tuple(len(proof[k]) for k in ('visited', 'blends', 'switches', 'leaves')), (104, 8, 10, 2))

    def test_tess_identity_refuses_modified_set_make_unknown_mask_cycle(self):
        master = self.master()
        proof = F.prove_uv0_identity(master, 'TessellationMultiplier', TESS_ID, 'one')
        leaf = next(iter(proof['leaves']))
        changed = copy.deepcopy(master)
        n = next(n for n in changed['nodes'] if n['path'] == leaf)
        next(p for p in n['inputs'] if p['name'] == 'TessellationMultiplier')['expression'] = 'not-default'
        with self.assertRaises(AssertionError):
            F.prove_uv0_identity(changed, 'TessellationMultiplier', TESS_ID, 'one')
        for mode in ('setter', 'unknown', 'mask', 'cycle'):
            changed = copy.deepcopy(master)
            root = changed['roots']['MaterialAttributes']
            n = next(n for n in changed['nodes'] if n['path'] == root['expression'])
            if mode == 'setter': n['properties']['AttributeSetTypes'] += TESS_ID
            if mode == 'unknown': n['class'] = 'UnknownAttributeProducer'
            if mode == 'mask': root['mask'][0] = 1
            if mode == 'cycle': n['inputs'][0]['expression'] = n['path']; n['inputs'][0]['output_index'] = 0
            with self.assertRaises(AssertionError):
                F.prove_uv0_identity(changed, 'TessellationMultiplier', TESS_ID, 'one')

    def test_actual_mic_activity_bypasses_no_tess_parent(self):
        text = self.source('MaterialInstance.cpp', '28d2409e0c7c7e30c42a7e8b9b9f56605962d5bbac5629e882c45bcf2f3b4668')
        active = F.method(text, 'bool UMaterialInstance::IsPropertyActive(')
        compile_body = F.method(text, 'int32 UMaterialInstance::CompilePropertyEx(')
        code = r'''
#include <cassert>
#define INDEX_NONE -1
typedef int int32; typedef int FGuid;
enum EMaterialProperty {MP_DiffuseColor,MP_SpecularColor,MP_TessellationMultiplier};
class FMaterialCompiler {};
struct ParentMaterial {int calls=0; bool IsPropertyActive(EMaterialProperty) const{return false;}
 int CompilePropertyEx(FMaterialCompiler*,const FGuid&){calls++;return 17;}};
struct UMaterialInstance {ParentMaterial* Parent=nullptr; bool IsPropertyActive(EMaterialProperty)const;
 int32 CompilePropertyEx(FMaterialCompiler*,const FGuid&);};
ACTIVE
COMPILE
int main(){ParentMaterial p; UMaterialInstance m; m.Parent=&p; FMaterialCompiler c;
 assert(!p.IsPropertyActive(MP_TessellationMultiplier)); assert(m.IsPropertyActive(MP_TessellationMultiplier));
 assert(!m.IsPropertyActive(MP_DiffuseColor)); assert(!m.IsPropertyActive(MP_SpecularColor));
 assert(m.CompilePropertyEx(&c,3)==17 && p.calls==1); m.Parent=nullptr; assert(m.CompilePropertyEx(&c,3)==-1);}
'''.replace('ACTIVE', active).replace('COMPILE', compile_body)
        compile_run(code)
        shared = self.source('MaterialShared.cpp', '1dff15c0b80b3818055d654144dba9a346d8d471540854f17d4d572492f37f32')
        line = next(l for l in shared.splitlines() if 'TEXT("TessellationMultiplier")' in l)
        self.assertIn('SF_Hull', line)
        self.assertIn('FVector4(1,0,0,0)', line.replace(' ', ''))
        self.assertIn('A0119D44', line)

    def test_pinned_capture_exact_scope_and_new_generation(self):
        if PRIVATE_PROOF is None:
            self.skipTest('pass --private-proof for immutable current23 evidence')
        raw = PRIVATE_PROOF.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), PROOF_SHA256)
        self.assertEqual(hashlib.sha1(raw).hexdigest(), PROOF_SHA1)
        proof = json.loads(raw)
        recipe = F.W.load_recipe()
        expected = set(recipe['instances']) | set(recipe['clones'].values())
        self.assertEqual({r['package'] for r in proof['rows']}, expected)
        self.assertEqual(len(proof['rows']), 23)
        self.assertEqual(len(proof['original_dependencies']), 48)
        self.assertEqual(len(proof['artifacts']), 4)
        row = next(r for r in proof['rows'] if r['role'] == 'master')
        self.assertEqual(row['sha1'].lower(), OLD_MASTER)
        self.assertTrue(all(r['nlink'] == 1 for r in proof['rows']))
        self.assertTrue(proof['capture_only']); self.assertFalse(proof['save_authority'])
        self.assertIn(PROOF_SHA1, HEADER.read_text())
        # No unsafe conversion of >2^53 identity integers in the native reader.
        self.assertNotIn('GetNumberField(TEXT("device"))', HEADER.read_text())
        self.assertNotIn('GetNumberField(TEXT("inode"))', HEADER.read_text())


    def test_actual_native_proof_checks_refuse_every_changed_file_and_scope(self):
        text = HEADER.read_text()
        body = text[text.index('static const TCHAR* WTUProofSHA1'):text.index('// Reserve evidence')]
        fixture = r"""
TSharedPtr<FJsonObject> snap(FString p,FString h){auto j=MakeShareable(new FJsonObject);j->SetStringField("path",p);j->SetStringField("sha1",h);disk.Add(p,{h,true});return j;}
void push(FArray& a,TSharedPtr<FJsonObject> j){auto v=MakeShareable(new FJsonValue);v->Object=j;a.push_back(v);}
void setup(){
 disk.Values.clear();captured=MakeShareable(new FJsonObject);
 captured->SetStringField("schema","weapon-uv0-current23-capture-v1");
 captured->SetStringField("project",FPaths::GameDir());captured->SetStringField("content",FPaths::GameContentDir());
 captured->SetStringField("root","/selected");captured->SetStringField("original","/original/UnrealTournament");
 FArray rows,deps,arts;
 for(int i=0;i<23;i++) {FString p=i==22?WTUMaster():FString("/Game/P"+std::to_string(i));
   auto j=snap(FPackageName::LongPackageNameToFilename(p,".uasset"),i==22?WTUOldMasterSHA1:"1111111111111111111111111111111111111111");
   j->SetStringField("package",p);push(rows,j);}
 for(int i=0;i<48;i++)push(deps,snap("/original/dep"+std::to_string(i),"2222222222222222222222222222222222222222"));
 for(int i=0;i<4;i++)push(arts,snap("/evidence/art"+std::to_string(i),"3333333333333333333333333333333333333333"));
 captured->Arrays.Add("rows",rows);captured->Arrays.Add("original_dependencies",deps);captured->Arrays.Add("artifacts",arts);
 captured->SetObjectField("recipe",snap("/evidence/recipe","4444444444444444444444444444444444444444"));
 captured->SetObjectField("baseline",snap("/evidence/baseline","5555555555555555555555555555555555555555"));
 disk.Add("/evidence/proof",{WTUProofSHA1,true});
}
int main(){
 setup();FWeaponTessProof p;assert(p.Read("/evidence/proof"));assert(p.Check(WTUOldMasterSHA1));
 // Every physical current/dependency/artifact/recipe/baseline/proof file matters.
 auto keys=disk.Values;
 for(auto kv:keys){auto old=disk.FindChecked(kv.Key);disk.Add(kv.Key,{"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",true});assert(!p.Check(WTUOldMasterSHA1));disk.Add(kv.Key,old);
   disk.Find(kv.Key)->physical=false;assert(!p.Check(WTUOldMasterSHA1));disk.Add(kv.Key,old);}
 FString master=p.CurrentFiles.FindChecked(WTUMaster());
 disk.Find(master)->hash="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
 assert(!p.Check(WTUOldMasterSHA1));assert(p.Check("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
 assert(!p.Check("short"));
 for(int fault=0;fault<7;fault++){
   setup();
   if(fault==0)disk.Find("/evidence/proof")->hash="6666666666666666666666666666666666666666";
   if(fault==1)captured->SetStringField("schema","wrong");
   if(fault==2)captured->SetStringField("project","/elsewhere");
   if(fault==3)captured->Arrays.Find("rows")->pop_back();
   if(fault==4)captured->Arrays.Find("rows")->at(1)->Object->SetStringField("package","/Game/P0");
   if(fault==5)captured->Arrays.Find("rows")->at(0)->Object->SetStringField("path","/wrong");
   if(fault==6)captured->Arrays.Find("rows")->back()->Object->SetStringField("sha1","6666666666666666666666666666666666666666");
   FWeaponTessProof q;assert(!q.Read("/evidence/proof"));
 }
}
"""
        compile_run(HOST_TYPES + body + fixture)

    def test_actual_save_tail_never_saves_on_failed_precondition_and_retains_partial_failure(self):
        text = HEADER.read_text()
        body = F.method(text, 'static int32 WeaponTessellationUpgrade(')
        tail = body[body.index('    if (!Expected || !R.WPO(Master)'):]
        # Execute the actual native final gate/save/evidence control flow. Stubs
        # supply failures; they do not restate that flow or write real assets.
        stubs = r"""
#define UE_LOG(...) ((void)0)
const char* WTUProofSHA1="f86076971bcdd3f4adee45ca27d1ec22da9f5f9b";
const char* WTUOldMasterSHA1="5d82999ff94ee56567fdcab1bd7918c5f533a7b2";
FString WTUMaster(){return "/Game/HTML5Compat/Weapons/V1/M_WeaponsBase";}
int fault=0,saves=0,writes=0,stops=0;
int WFRStop(const char*){stops++;return 1;}
struct Repair {bool WPO(void*){return fault!=1;} bool AO(int,const char*){return fault!=2;}
 TMap<FString,int> Objects;TMap<FString,FString> Clones;};
int WFRFinalChecks(Repair&,void*,int*){return fault==3?1:0;}
struct ProofType {TMap<FString,FString> CurrentHashes;
 bool Check(FString){return saves ? fault!=9 : fault!=4;}
 bool External(FString,bool){return fault!=5;}};
struct PolicyType {TMap<FString,FString> Files;
 bool Check(FString){return fault!=7;}
 bool Save(void*){saves++;disk.Find("/master")->hash="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";return fault!=8;}};
struct EvidenceType {bool Write(FString){writes++;return fault!=11;}};
template<class T=void>struct TJsonWriterFactory{static int Create(FString*){return 0;}};
struct FJsonSerializer {static bool Serialize(TSharedPtr<FJsonObject>,int){return fault!=10;}};
int operation(){
 void* Master=nullptr;int expected=1;int* Expected=fault==12?nullptr:&expected;Repair R;ProofType Proof;PolicyType Policy;EvidenceType Evidence;
 FString Backup="/backup",ReceiptPath="/receipt",ReceiptHash="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",MasterHash;
 FString MF="/Game/RestrictedAssets/Weapons/Global/Material/MF/";
 R.Clones.Add(MF+"MF_BaseShader_Textures","texture");R.Clones.Add(MF+"MF_Dirt","dirt");R.Objects.Add("texture",1);R.Objects.Add("dirt",2);
 Policy.Files.Add(WTUMaster().ToLower(),"/master");Proof.CurrentHashes.Add(WTUMaster(),WTUOldMasterSHA1);Proof.CurrentHashes.Add("/Game/Other","cccccccccccccccccccccccccccccccccccccccc");
 disk.Values.clear();disk.Add(Backup,{WTUOldMasterSHA1,true});disk.Add(ReceiptPath,{ReceiptHash,fault!=6});disk.Add("/master",{WTUOldMasterSHA1,true});
TAIL
int main(){
 for(fault=0;fault<=12;fault++){
  saves=writes=stops=0;int result=operation();
  if(fault==0){assert(result==0&&saves==1&&writes==1);}
  else if(fault<=7||fault==12){assert(result==1&&saves==0&&writes==0);}
  else {assert(result==1&&saves==1);assert(disk.FindChecked("/master").hash=="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");}
  if(fault==8||fault==9||fault==10)assert(writes==0);
  if(fault==11)assert(writes==1);
 }
}
""".replace('TAIL', tail)
        compile_run(HOST_TYPES + stubs)

    def test_exclusive_evidence_and_single_save_fail_closed_order(self):
        text = HEADER.read_text()
        body = F.method(text, 'static int32 WeaponTessellationUpgrade(')
        for earlier, later in (
            ('Proof.Read(', 'WeaponFidelityRepair('),
            ('Proof.Check(MasterHash)', 'WeaponFidelityRepair('),
            ('Policy.Read(', 'WeaponFidelityRepair('),
            ('WeaponFidelityRepair(', 'Evidence.Open('),
            ('Evidence.Open(', 'R.Add<'),
            ('R.Add<', 'WFRFinalChecks('),
            ('WFRFinalChecks(', 'Policy.Save('),
            ('Policy.Save(', 'tess-post-save-drift'),
            ('tess-post-save-drift', 'Evidence.Write('),
            ('Evidence.Write(', 'complete mode=apply'),
        ): self.assertLess(body.index(earlier), body.index(later))
        self.assertIn('CREATE_NEW', text)
        self.assertIn('FlushFileBuffers(Handle)', text)
        self.assertIn('Bytes.Length() > 65536', text)
        self.assertIn('if (Verify)', body)
        self.assertLess(body.index('complete mode=verify'), body.index('Evidence.Open('))
        self.assertIn('Set->Inputs.SetNum(4); Set->Inputs[3].Expression = One;', body)
        self.assertIn('One->R = 1.0f;', body)
        self.assertEqual(body.count('MP_TessellationMultiplier'), 1)
        self.assertNotIn('D3D11TessellationMode =', body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-source-dir', type=Path)
    parser.add_argument('--private-log', type=Path)
    parser.add_argument('--private-proof', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE_SOURCE, PRIVATE_LOG, PRIVATE_PROOF = args.private_source_dir, args.private_log, args.private_proof
    unittest.main(argv=[sys.argv[0]] + rest)
