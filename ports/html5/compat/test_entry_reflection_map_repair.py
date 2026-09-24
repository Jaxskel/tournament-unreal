"""Bounded local tests: extracted native admission/receipt logic and source-backed API contracts.
No UE/editor execution. Temporary host fixtures only; captured engine source stays private.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/EntryReflectionMapRepair.h'
API = REFLECTION = None


def section(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def compile_run(code):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise RuntimeError('Host C++ compiler required')
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'fixture.cpp'
        binary = Path(tmp) / 'fixture'
        source.write_text(code)
        result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', str(source), '-o', str(binary)], capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise AssertionError(result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.text = HEADER.read_text()

    def test_actual_verify_evidence_statement_compiles_and_short_circuits(self):
        statement = next(line for line in self.text.splitlines() if 'if (!Evidence.Open(Full(Output),R)' in line and 'TEXT("verify")' in line)
        compile_run(r'''
#include <cassert>
#define TEXT(x) x
const char* Full(const char* value){return value;}
int ERMRecord(const char*,const char*,int){return 1;}
int WFRStop(const char*){return 3;}
struct EvidenceStub {
 bool open,emit; int opens=0,emits=0;
 bool Open(const char*,int){++opens;return open;}
 bool Emit(int){++emits;return emit;}
};
int check(EvidenceStub& Evidence){const char* Output="out";int R=0;
''' + statement + r'''
return 0;}
int main(){for(int a=0;a<2;++a)for(int b=0;b<2;++b){
 EvidenceStub evidence{bool(a),bool(b)};
 assert(check(evidence)==((a&&b)?0:3));
 assert(evidence.opens==1);assert(evidence.emits==a);
}}
''')

    def test_inspection_pre_capture_boundary(self):
        block = section(self.text, '            // ENTRY_MAP_INSPECT_BEGIN', '            // ENTRY_MAP_INSPECT_END')
        for forbidden in ('SetCaptureIsDirty', 'UpdateReflectionCaptureContents', 'PreSave(', 'SavePackage('):
            self.assertNotIn(forbidden, block)
        self.assertLess(self.text.index('// ENTRY_MAP_INSPECT_END'), self.text.index('Capture.Target->SetCaptureIsDirty()'))
        self.assertIn('Authored.FindChecked(Key)', block)
        self.assertIn('Evidence.Emit(Row,8*1024*1024)', block)
        self.assertIn('TEXT("inspected")', self.text)

    def test_actual_inspection_branch_compiled(self):
        block = section(self.text, '            // ENTRY_MAP_INSPECT_BEGIN', '            // ENTRY_MAP_INSPECT_END')
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
#include <memory>
#include <algorithm>
#define TEXT(x) x
using FString=std::string;
template<class T> using TSharedPtr=std::shared_ptr<T>;
template<class T> struct TArray:std::vector<T>{void Sort(){std::sort(this->begin(),this->end());}};
struct FJsonObject{void SetBoolField(const char*,bool){} void SetNumberField(const char*,int){} void SetStringField(const char*,const FString&){} };
struct ReceiptStub{bool ok=true;bool Before(){return ok;}} Receipt;
struct CaptureStub{int World=0;bool CheckMapPins(){return Receipt.ok;}} Capture;
bool SettingsDisabled(){return Receipt.ok;}
TSharedPtr<FJsonObject> ERMRecord(const char*,const char*,ReceiptStub&){return std::make_shared<FJsonObject>();}
struct AuthoredStub{int count=78;int Num(){return count;}void GetKeys(TArray<FString>& k){k.push_back("object");} FString FindChecked(const FString&){return "exact row";}} Authored;
struct EvidenceStub{bool ok=true;int calls=0;bool Emit(TSharedPtr<FJsonObject>,int limit){assert(limit==8*1024*1024);++calls;return ok;}} Evidence;
bool finished=false,success=false;
void Finish(bool ok,const char*,TSharedPtr<FJsonObject>){finished=true;success=ok;}
const FString ERMCanonicalDigest="baseline";
const char* ERMInspect1SHA1="proof1";const char* ERMInspect2SHA1="proof2";
FString sourceDigest;bool registry;
bool ERMCanonical(AuthoredStub&,FString& out,FString& guid){out=sourceDigest;guid="guid";return true;}
bool ERMRegistryLinked(int,const FString&){return registry;}
bool branch(bool InspectOnly,bool SnapshotOK,FString Digest){sourceDigest=Digest;
''' + block + r'''
return true;}
int main(){for(int mask=0;mask<128;++mask){
 bool inspect=mask&1,snapshot=mask&2,count=mask&4,digest=mask&8,emit=mask&16,pins=mask&32;
 registry=mask&64;Authored.count=count?78:77;Receipt.ok=pins;Evidence.ok=emit;Evidence.calls=0;finished=false;success=false;
 bool continued=branch(inspect,snapshot,digest?"baseline":"different");
 bool stopped=inspect||!snapshot||!count||!digest||!registry;
 assert(continued==!stopped);assert(finished==stopped);
 assert(success==(stopped&&inspect&&snapshot&&emit&&pins));
 assert(Evidence.calls==(stopped&&snapshot?1:0));
}}
''')

    def canonical_fixture(self):
        shim = r'''
#include <cassert>
#include <string>
#include <iostream>
#define TEXT(x) x
using int32=int;using TCHAR=char;
const int INDEX_NONE=-1;
namespace ESearchCase{enum Type{CaseSensitive};}
namespace ESearchDir{enum Type{FromStart};}
struct FString:std::string{
 using std::string::string;FString(const std::string& s):std::string(s){}
 int Len()const{return size();}
 bool StartsWith(const FString& p,ESearchCase::Type)const{return compare(0,p.size(),p)==0;}
 int Find(const FString& p,ESearchCase::Type,ESearchDir::Type=ESearchDir::FromStart,int at=0)const{auto n=find(p,at);return n==npos?-1:int(n);}
 FString Mid(int at,int count=-1)const{return substr(at,count<0?npos:count);}
 FString Left(int n)const{return substr(0,n);}
};
const char* ERMLevelPath="/Game/RestrictedAssets/Maps/UT-Entry.UT-Entry:PersistentLevel";
'''
        return shim + section(self.text,'static bool ERMGuid(', 'static FString ERMRowsDigest(')

    def test_actual_canonicalization_negative_cases(self):
        compile_run(self.canonical_fixture() + r'''
int main(){
 FString id="19337B7446F57534494AC782897653F7",copy,guid;
 FString row=FString("/Script/Engine.Level\nOther[0]=authored\nLevelBuildDataId[0]=")+id+"\nAfter[0]=keep\n";
 const FString before=row;
 assert(ERMCanonicalLevelRow(ERMLevelPath,row,copy,guid));assert(row==before);assert(guid==id);
 assert(copy==FString("/Script/Engine.Level\nOther[0]=authored\nLevelBuildDataId[0]=")+FString(32,'0')+"\nAfter[0]=keep\n");
 assert(!ERMCanonicalLevelRow("other-level",row,copy,guid));
 assert(!ERMCanonicalLevelRow(ERMLevelPath,"/Script/Engine.Other\nLevelBuildDataId[0]="+id+"\n",copy,guid));
 assert(!ERMCanonicalLevelRow(ERMLevelPath,"/Script/Engine.Level\nOther[0]=1\n",copy,guid));
 assert(!ERMCanonicalLevelRow(ERMLevelPath,row+"LevelBuildDataId[0]="+id+"\n",copy,guid));
 assert(!ERMCanonicalLevelRow(ERMLevelPath,row+"LevelBuildDataId[1]="+id+"\n",copy,guid));
 for(FString bad:{FString(32,'0'),FString(32,'Z'),FString(31,'A'),FString(33,'A')})
  assert(!ERMCanonicalLevelRow(ERMLevelPath,"/Script/Engine.Level\nLevelBuildDataId[0]="+bad+"\n",copy,guid));
 FString changed=row;changed.replace(changed.find("authored"),8,"CHANGED!");
 FString normalized;assert(ERMCanonicalLevelRow(ERMLevelPath,changed,normalized,guid));
 assert(normalized.find("CHANGED!")!=FString::npos); // Never normalize another field.
}
''')

    def test_pinned_inspections_actual_canonical_rows_and_digest(self):
        root=HERE.parents[4]/'work/ut4-html5/entry-reflection-save'
        expected_pins=('cf5e348674462e227410397e4333dec8503b457d','201e78123abc635ed7d1114ab3d8317c0cebf151')
        normalized=[]
        for number,pin in enumerate(expected_pins,1):
            raw=(root/f'inspect{number}/inspect.jsonl').read_bytes()
            self.assertEqual(hashlib.sha1(raw).hexdigest(),pin);self.assertIn(pin,self.text)
            records=[json.loads(x) for x in raw.decode('utf-8').splitlines()]
            rows=records[1:-1];self.assertEqual(len(rows),78)
            target=[x for x in rows if x['object_path'].endswith(':PersistentLevel')]
            self.assertEqual(len(target),1)
            original=target[0]['snapshot_row']
            result=compile_run(self.canonical_fixture()+'\nint main(){FString copy,guid;assert(ERMCanonicalLevelRow(ERMLevelPath,'+json.dumps(original)+',copy,guid));std::cout<<copy;}')
            expected=re.sub(r'(?m)^LevelBuildDataId\[0\]=[0-9A-F]{32}$','LevelBuildDataId[0]='+'0'*32,original)
            self.assertEqual(result,expected)
            pairs=[(r['object_path'], result if r is target[0] else r['snapshot_row']) for r in rows]
            digest=hashlib.sha1()
            for key,row in pairs:
                for value in (key,row):digest.update(value.encode('utf-16le'));digest.update(b'\xff')
            self.assertEqual(digest.hexdigest(),'4fb768cf9ba362b390affa07c74d3237ab88ab85')
            normalized.append(pairs)
        self.assertEqual(normalized[0],normalized[1])
        self.assertIn('4fb768cf9ba362b390affa07c74d3237ab88ab85',self.text)

    def test_actual_raw_equality_and_reload_guid_checks(self):
        extra = r'''
#include <vector>
struct Item{FString Key,Value;};
template<class K,class V>struct TMap:std::vector<Item>{
 int Num()const{return this->size();}const V* Find(const K& key)const{for(auto& x:*this)if(x.Key==key)return &x.Value;return nullptr;}
};
'''
        source=self.canonical_fixture()+extra+section(self.text,'static bool ERMSHA1(', '// Cross-run proof:')+section(self.text,'static bool ERMReloadIdentity(', 'static bool ERMSame(')+section(self.text,'static bool ERMObjectsEqual(', 'struct FERMReceipt')
        compile_run(source+r'''
int main(){TMap<FString,FString>a;a.push_back({"level","raw-guid-A"});auto b=a;
assert(ERMObjectsEqual(a,b));b[0].Value="raw-guid-B";assert(!ERMObjectsEqual(a,b));
b=a;b[0].Key="different";assert(!ERMObjectsEqual(a,b));b=a;b.push_back({"extra","row"});assert(!ERMObjectsEqual(a,b));
FString raw(40,'a'),guid(32,'A'),other(32,'B');
assert(ERMReloadIdentity(raw,raw,guid,guid));assert(!ERMReloadIdentity(raw,FString(40,'b'),guid,guid));
assert(!ERMReloadIdentity(raw,raw,guid,other));assert(!ERMReloadIdentity(raw,raw,FString(32,'0'),FString(32,'0')));
}
''')
        same=section(self.text,'    bool SameAuthored()', '    void Finish(')
        self.assertIn('Digest == InitialRawDigest && ERMObjectsEqual(Authored,Now)',same)
        self.assertIn('ERMRegistryLinked(Capture.World,InitialLevelGuid)',same)
        verify=self.text.split('static int32 VerifyEntryReflectionMap(',1)[1]
        self.assertIn('ERMReloadIdentity(Digest,Str(Proof,TEXT("authored_digest")),LevelGuid,Str(Proof,TEXT("saved_level_guid")))',verify)

    def test_loaded_inspect_original_only_no_save_proof_and_no_mutations(self):
        loaded=section(self.text,'static int32 ERMInspectLoadedOriginal(', '// Synchronous commandlet-only')
        self.assertEqual(loaded.count('LoadPackage('),1)
        for token in ('SetCaptureIsDirty','UpdateReflectionCaptureContents','PreSave(', 'SavePackage(', 'AddTicker(', 'InitWorld(', 'RegisterComponent'):
            self.assertNotIn(token,loaded)
        self.assertIn('!R.Read(Params,true) || R.SelectedPin.SHA1!=ERDMapSHA1',loaded)
        self.assertLess(loaded.index('FindPackage('),loaded.index('LoadPackage('))
        self.assertIn('!World->Scene && ERMTarget(World,false,Target)',loaded)
        self.assertIn('const bool OK=RowsOK && R.Before();',loaded)
        self.assertNotIn('const bool OK=RowsOK && Matches',loaded)
        self.assertIn('MapBuildData->GetPathName() : FString()',loaded)
        self.assertIn('FParse::Value(*Params,TEXT("EntryMapSaveProof="),Forbidden) ||',loaded)
        self.assertIn('FParse::Value(*Params,TEXT("EntryMapSaveProofSHA1="),Forbidden) ||',loaded)
        verify=self.text.split('static int32 VerifyEntryReflectionMap(',1)[1]
        self.assertLess(verify.index('IsRunningCommandlet()'),verify.index('return ERMInspectLoadedOriginal'))
        self.assertLess(verify.index('return ERMInspectLoadedOriginal'),verify.index('R.Read(Params,false)'))
        start=section(self.text,'static int32 StartEntryReflectionMapSave(', 'static void ShutdownEntryReflectionMapSave(')
        self.assertIn('TEXT("EntryMapInspectLoaded")',start)
        self.assertEqual(self.text.count('!=ERMBaselineDigest'),0)
        self.assertEqual(self.text.count('!= ERMBaselineDigest'),1) # receipt provenance only

    def test_full_loaded_inspection_function_compiled_observational(self):
        body=section(self.text,'static int32 ERMInspectLoadedOriginal(', '// Synchronous commandlet-only')
        compile_run(r'''
#include <cassert>
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <algorithm>
#define TEXT(x) x
using FString=std::string;using int32=int;
template<class T>using TSharedPtr=std::shared_ptr<T>;
template<class T>struct TArray:std::vector<T>{void Sort(){std::sort(this->begin(),this->end());}};
template<class K,class V>struct TMap:std::map<K,V>{int Num()const{return this->size();}void GetKeys(TArray<K>& k)const{for(auto& p:*this)k.push_back(p.first);}const V& FindChecked(const K& k)const{return this->at(k);}};
struct FJsonObject{
 std::map<std::string,std::string> strings;std::map<std::string,bool> flags;
 void SetStringField(const char* k,const FString& v){strings[k]=v;}void SetBoolField(const char* k,bool v){flags[k]=v;}void SetNumberField(const char*,int){}
};
const char* ERDPackage="package";const char* ERDMapSHA1="original";
const char* ERMCanonicalDigest="canonical";const char* ERMInspect1SHA1="one";const char* ERMInspect2SHA1="two";
bool forbidden=false,original=true,present=false,registry=false,canonical=false,snapshot=true,pins=true;
int loads=0,emits=0;
struct FParse{static bool Value(const char*,const char* key,FString& out){if(std::string(key)=="EntryMapOutput="){out="output";return true;}return forbidden;}};
const char* operator*(const FString& s){return s.c_str();}
struct FERMReceipt{struct Pin{FString SHA1;}SelectedPin;bool Read(const FString&,bool originalOnly){assert(originalOnly);SelectedPin.SHA1=original?"original":"saved";return true;}bool Before(){return pins;}};
FString Full(const FString& s){return s;}
int WFRStop(const char*){return 3;}
TSharedPtr<FJsonObject> ERMRecord(const char* mode,const char* kind,FERMReceipt&){auto j=std::make_shared<FJsonObject>();j->SetStringField("mode",mode);j->SetStringField("kind",kind);return j;}
TSharedPtr<FJsonObject> completed;
struct FERMEvidence{bool Open(const FString&,FERMReceipt&){return true;}bool Emit(TSharedPtr<FJsonObject> j,int=16384){++emits;if(j->strings["kind"]=="complete")completed=j;return true;}};
struct UPackage{} package;
UPackage* FindPackage(void*,const char*){return present?&package:nullptr;}
const int LOAD_None=0;UPackage* LoadPackage(void*,const char*,int){++loads;return &package;}
struct Registry{FString GetPathName(){return "registry";}} registryObject;
struct Level{Registry* MapBuildData=nullptr;} level;
struct UWorld{void* Scene=nullptr;Level* PersistentLevel=&level;static UWorld* FindWorldInPackage(UPackage*); } world;
UWorld* UWorld::FindWorldInPackage(UPackage*){level.MapBuildData=registry?&registryObject:nullptr;return &world;}
struct UReflectionCaptureComponent{} target;
bool ERMTarget(UWorld*,bool registered,UReflectionCaptureComponent*& out){assert(!registered);out=&target;return true;}
struct FERDState{static bool Snapshot(UWorld*,UReflectionCaptureComponent*,TMap<FString,FString>& rows,FString& raw){raw="raw";rows["one"]="full row";return snapshot;}};
bool ERMCanonical(const TMap<FString,FString>&,FString& digest,FString& guid){digest="different";guid="guid";return canonical;}
bool ERMRegistryLinked(UWorld*,const FString&){return registry;}
''' + body + r'''
int main(){
 // Original synchronous PostLoad may have fewer objects/no registry/nonmatching digest.
 assert(ERMInspectLoadedOriginal("")==0);assert(loads==1);assert(emits==3);
 assert(completed->strings["status"]=="inspected");assert(completed->strings["registry_path"].empty());
 assert(!completed->flags["registry_link_valid"]);assert(!completed->flags["baseline_matches"]);
 assert(!completed->flags["save_attempted"]);assert(!completed->flags["package_saved"]);
 for(int which=0;which<3;++which){loads=0;forbidden=which==0;original=which!=1;present=which==2;
 assert(ERMInspectLoadedOriginal("")==3);assert(loads==0);}
 forbidden=false;original=true;present=false;loads=0;snapshot=false;
 assert(ERMInspectLoadedOriginal("")==3);assert(loads==1);assert(!completed->flags["snapshot_rows_complete"]);
}
''')

    def test_registry_export_and_source_contract(self):
        root=HERE.parents[4]/'work/ut4-html5/weapon-sampler-review/usage-api-extra'
        header=(root/'Engine__Source__Runtime__Engine__Classes__Engine__MapBuildDataRegistry.h').read_text()
        self.assertIn('ENGINE_API const FPrecomputedLightVolumeData* GetLevelBuildData(FGuid LevelId) const;',header)
        code=section(self.text,'static bool ERMRegistryLinked(', 'static bool ERMReloadIdentity(')
        for term in ('Level->GetPathName()==ERMLevelPath','/Script/Engine.Level','Level->LevelBuildDataId.IsValid()', 'Registry->GetPathName()==ERMRegistryPath','Registry->GetOutermost()==World->GetOutermost()', '/Script/Engine.MapBuildDataRegistry','Registry->GetLevelBuildData(Level->LevelBuildDataId)!=nullptr'):
            self.assertIn(term,code)
        self.assertNotIn('#include',self.text)

    def test_actual_save_predicate_every_combination(self):
        predicate = section(self.text, 'static bool ERMSaveAdmission(', 'static bool ERMSHA1(')
        compile_run('#include <cassert>\n' + predicate + r'''
int main(){for(unsigned mask=0;mask<(1u<<13);++mask){bool a[13];for(int i=0;i<13;++i)a[i]=(mask>>i)&1;
bool result=ERMSaveAdmission(a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7],a[8],a[9],a[10],a[11],a[12]);
assert(result==(mask==((1u<<13)-1-2)));}}
''')

    def test_actual_receipt_rejects_field_pin_and_path_drift(self):
        # Fake filesystem/JSON/parser only. Compile the actual receipt validator and
        # recheck functions, not a Python reimplementation of admission rules.
        helpers = section(self.text, 'static bool ERMSHA1(', '// Cross-run proof:') + section(self.text, 'static bool ERMSame(', 'static FString ERMBrightness(')
        receipt = section(self.text, 'struct FERMReceipt', '// Exclusive append-only')
        shim = r'''
#include <cassert>
#include <string>
#include <map>
#include <vector>
#include <memory>
#include <filesystem>
#include <algorithm>
using int32=int;using int64=long long;using TCHAR=char;
#define TEXT(x) x
namespace ESearchCase {enum Type{IgnoreCase};}
struct FString:std::string {
 using std::string::string;FString(){} FString(const std::string& s):std::string(s){}
 int Len()const{return size();}bool IsEmpty()const{return empty();}const char* operator*()const{return c_str();}
 FString ToLower()const{FString x=*this;std::transform(x.begin(),x.end(),x.begin(),::tolower);return x;}
 bool Contains(const char* x)const{return find(x)!=npos;}
 bool Equals(const char* x,ESearchCase::Type)const{return ToLower()==FString(x).ToLower();}
};
FString operator/(const FString& a,const FString& b){return std::string(a)+"/"+std::string(b);}
FString Full(const FString& s){return std::filesystem::path(s.c_str()).lexically_normal().string();}
bool Within(const FString& p,const FString& root){return p==root || p.rfind(std::string(root)+"/",0)==0;}
struct FPaths {
 static FString EngineDir(){return "/port/Engine";}static FString GameDir(){return "/port/Game";}
 static FString GameContentDir(){return "/port/Game/Content";}
 static FString GetPath(const FString& p){return std::filesystem::path(p.c_str()).parent_path().string();}
 static FString GetCleanFilename(const FString& p){return std::filesystem::path(p.c_str()).filename().string();}
};
static const char* ERDPackage="/Game/RestrictedAssets/Maps/UT-Entry";
static const char* ERDMapSHA1="653a6eb7a37f00c5238d210e5f45d7729117a246";
static const char* ERMBaselineDigest="72c5d75b7c786ec992026ef11eeb3a758431e01c";
static const char* ERMDiagnosticSHA1="916a90760ebbabc25d878a85ea46692c076495c4";
struct FPackageName{static FString LongPackageNameToFilename(const char*,const char*){return "/port/Game/Content/RestrictedAssets/Maps/UT-Entry.umap";}};
struct FParse{static bool Value(const char* args,const char* key,FString& out){std::string a=args;auto p=a.find(key);if(p==a.npos)return false;p+=std::string(key).size();auto end=a.find(' ',p);out=a.substr(p,end-p);return true;}};
template<class T>using TSharedPtr=std::shared_ptr<T>;
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}};
namespace EJson{enum Type{String,Number};}
struct FJsonValue{EJson::Type Type=EJson::String;FString value;FString AsString()const{return value;}};
struct FJsonObject {
 std::map<FString,FString> strings;std::map<FString,bool> bools;std::map<FString,double> numbers;TArray<TSharedPtr<FJsonValue>> list;
 bool TryGetBoolField(const char* k,bool& out){auto i=bools.find(k);if(i==bools.end())return false;out=i->second;return true;}
 bool TryGetNumberField(const char* k,double& out){auto i=numbers.find(k);if(i==numbers.end())return false;out=i->second;return true;}
 bool TryGetArrayField(const char* k,const TArray<TSharedPtr<FJsonValue>>*& out){if(std::string(k)!="save_allowlist")return false;out=&list;return true;}
};
static TSharedPtr<FJsonObject> document;
FString Str(const TSharedPtr<FJsonObject>& j,const char* key){return j->strings[key];}
bool ReadJson(const FString&,TSharedPtr<FJsonObject>& j){j=document;return true;}
struct FWURFile{FString Path,Target,SHA1,Identity;int64 Size=10;
 static bool Inspect(const FString&,bool,FWURFile&,const void* =nullptr,int64=1073741824LL);};
static std::map<FString,FWURFile> disk;
bool FWURFile::Inspect(const FString& p,bool,FWURFile& out,const void*,int64 limit){auto i=disk.find(p);if(i==disk.end()||i->second.Size>limit)return false;out=i->second;return true;}
'''
        main = r'''
int main(){
 const FString selected=FPackageName::LongPackageNameToFilename("","");
 const FString original="/original/Game/Content/RestrictedAssets/Maps/UT-Entry.umap";
 const FString receipt="/evidence/receipt.json",backup="/evidence/backup.umap",diagnostic="/evidence/diagnostic.json";
 const FString pin(40,'a'), after(40,'b');
 document=std::make_shared<FJsonObject>();
 document->strings={{"schema","ut4-entry-reflection-save-v1"},{"operation","save-entry-reflection"},{"package",ERDPackage},
 {"original_sha1",ERDMapSHA1},{"diagnostic_result_sha1",ERMDiagnosticSHA1},{"authored_digest",ERMBaselineDigest},
 {"original_map",original},{"selected_map",selected},{"backup",backup},{"diagnostic_result",diagnostic}};
 document->bools["native_save_authorized"]=true;document->numbers["authored_objects"]=78;
 auto value=std::make_shared<FJsonValue>();value->value=selected;document->list.push_back(value);
 int id=0;for(auto p:{selected,original,backup,diagnostic,receipt}){FWURFile f;f.Path=f.Target=p;f.Identity=std::to_string(++id);f.SHA1=ERDMapSHA1;disk[p]=f;}
 disk[receipt].SHA1=pin;disk[diagnostic].SHA1=ERMDiagnosticSHA1;
 FString args=std::string("EntryMapReceipt=")+receipt+" EntryMapReceiptSHA1="+pin+" EntryMapExpectedSHA1="+ERDMapSHA1;
 FERMReceipt good;assert(good.Read(args,true));assert(good.Before());
 for(auto key:{"schema","operation","package","original_sha1","diagnostic_result_sha1","authored_digest","original_map","selected_map","backup","diagnostic_result"}){
  auto old=document->strings[key];document->strings[key]="invalid";FERMReceipt r;assert(!r.Read(args,true));document->strings[key]=old;}
 document->bools["native_save_authorized"]=false;{FERMReceipt r;assert(!r.Read(args,true));}document->bools["native_save_authorized"]=true;
 document->numbers["authored_objects"]=77;{FERMReceipt r;assert(!r.Read(args,true));}document->numbers["authored_objects"]=78;
 document->list.push_back(value);{FERMReceipt r;assert(!r.Read(args,true));}document->list.pop_back();
 value->value=original;{FERMReceipt r;assert(!r.Read(args,true));}value->value=selected;
 for(auto p:{selected,original,backup,diagnostic,receipt}){auto old=disk[p];disk[p].SHA1=after;FERMReceipt r;assert(!r.Read(args,true));assert(!good.Before());disk[p]=old;}
 auto old=disk[selected].Identity;disk[selected].Identity=disk[original].Identity;{FERMReceipt r;assert(!r.Read(args,true));}disk[selected].Identity=old;
 auto oldpath=document->strings["backup"];document->strings["backup"]=selected;{FERMReceipt r;assert(!r.Read(args,true));}document->strings["backup"]=oldpath;
 disk[selected].SHA1=after;FString verify=std::string("EntryMapReceipt=")+receipt+" EntryMapReceiptSHA1="+pin+" EntryMapExpectedSHA1="+after;
 {FERMReceipt r;assert(r.Read(verify,false));assert(!r.Read(verify,true));}
 assert(!ERMSHA1("ABC"));assert(!ERMSHA1(FString(40,'A')));assert(ERMSHA1(pin));
}
'''
        compile_run(shim + helpers + receipt + main)

    def test_existing_diagnostic_and_cpp_inverse(self):
        for filename, expected in {
            'EntryReflectionDiagnostic.h': 'c1f8ea5d4b98146aefae2db71a4991e21b02ae2706f03fb41a94e684437bac7c',
            'UT4Html5Compat.cpp': '60c4773ba4ebe8e27cf5b6cd3a72682562c60594d62bc2c14ac429e86f55f1c6',
        }.items():
            data = (HEADER.parent/filename).read_bytes()
            if filename == 'UT4Html5Compat.cpp' and b'ENTRY_MAP_REPAIR_DECL_BEGIN' in data:
                self.assertEqual(hashlib.sha256(data).hexdigest(), 'c9279b8829bfdc681296a38d2a2bf864ac438123c9cf76844bd3d559ad5d08d2')
                for name in ('DECL', 'START', 'INCLUDE', 'VERIFY'):
                    data, count = re.subn(rb'(?m)^[ \t]*// ENTRY_MAP_REPAIR_'+name.encode()+rb'_BEGIN\n.*?^[ \t]*// ENTRY_MAP_REPAIR_'+name.encode()+rb'_END\n', b'', data, flags=re.S)
                    self.assertEqual(count, 1)
                data = data.replace(b'UT4Compat::ShutdownEntryReflectionMapSave(); ', b'')
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)

    def test_one_uncooked_save_and_dominating_checks(self):
        self.assertEqual(self.text.count('GEditor->SavePackage('), 1)
        tick = section(self.text,'    bool Tick(float)','static TSharedPtr<FERMState>')
        for token in ['ERMSaveAdmission(', 'SameAuthored(),Payload(', 'Receipt.Before() && Capture.CheckMapPins()', 'Evidence.Emit(Before)', 'SaveAttempted = true']:
            self.assertLess(tick.index(token),tick.index('GEditor->SavePackage('))
        self.assertIn('GError,nullptr,false,false,SAVE_None,nullptr,FDateTime::MinValue(),false',tick)
        self.assertIn('After.SHA1 != ERDMapSHA1',tick)
        self.assertLess(tick.index('IsDirty()!=Capture.PackageDirtyBefore'),tick.index('GEditor->SavePackage('))
        self.assertIn('PostHash==PayloadHash && PostBrightness==Brightness',tick)
        self.assertNotIn('3804faae',self.text)  # Earlier zero payload is not an admission constant.
        self.assertNotIn('SaveDirtyPackages',self.text)
        self.assertNotIn('SaveConfig(',self.text)
        self.assertNotIn('PostEditChange(',self.text)

    def test_setup_evidence_and_shutdown_restore_order(self):
        start=section(self.text,'static int32 StartEntryReflectionMapSave(', 'static void ShutdownEntryReflectionMapSave(')
        self.assertLess(start.index('Evidence.Open('),start.index('bAutoSaveEnable=false'))
        self.assertLess(start.index('PerformanceMonitor.Disable('),start.index('AddTicker('))
        self.assertIn('GEntryReflectionDiagnostic.IsValid()',start)
        self.assertIn('S->Capture.RestoreSettings(); return WFRStop',start)
        finish=section(self.text,'    void Finish(', '    bool Tick(float)')
        self.assertNotIn('RestoreSettings',finish)
        shutdown=section(self.text,'static void ShutdownEntryReflectionMapSave()', '// Synchronous commandlet-only')
        self.assertLess(shutdown.index('RemoveTicker'),shutdown.index('RestoreSettings'))

    def test_verifier_load_only_and_preload_absence(self):
        verify=self.text.split('static int32 VerifyEntryReflectionMap(',1)[1]
        self.assertEqual(verify.count('LoadPackage('),1)
        for token in ['SetCaptureIsDirty','UpdateReflectionCaptureContents','PreSave(', 'SavePackage(', 'AddTicker(', 'InitWorld(', 'RegisterComponent']:
            self.assertNotIn(token,verify)
        self.assertLess(verify.index('FindPackage('),verify.index('LoadPackage('))
        self.assertIn('ERMTarget(World,false,Capture.Target)',verify)
        self.assertIn('R.Before() && ERMUnchanged(ProofPin)',verify)
        for token in ['Lines.Num()!=3','saved_map_sha1','source_receipt_sha1','saved_identity','payload_sha1','brightness_bits','state_id','ActualDimension==128','ObjectsNow.Num()==78']:
            self.assertIn(token,verify)

    def test_source_backed_save_and_load_api(self):
        if API is None or REFLECTION is None:self.skipTest('private API dirs not supplied')
        editor=(API/'EditorEngine.h').read_text()
        self.assertIn('class UNREALED_API UEditorEngine',editor)
        self.assertIn('bool SavePackage( UPackage* InOuter, UObject* Base, EObjectFlags TopLevelFlags',editor)
        self.assertIn('bool bSlowTask = true',editor)
        impl=(API/'EditorEngine.cpp').read_text()
        body=section(impl,'bool UEditorEngine::SavePackage(', 'void UEditorEngine::OnPreSaveWorld(')
        self.assertIn('Result == ESavePackageResult::Success',body)
        reflection=(REFLECTION/'ReflectionCaptureComponent.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(reflection).hexdigest(),'92414bf58ffce0c3cc9ac93b422d5abe20410bf6ea41f953e609b639ff570965')
        text=reflection.decode()
        self.assertIn('Ar << ReflectionCaptureDDCVer',text)
        self.assertIn('if (SavedVersion != ReflectionCaptureDDCVer)',text)
        self.assertIn('Ar << FullHDRData->CompressedCapturedData',text)
        self.assertIn('ReadbackFromGPU(World)',text)
        header=(REFLECTION/'ReflectionCaptureComponent.h').read_text()
        self.assertIn('inline float GetAverageBrightness() const',header)


if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--editor-api-dir',type=Path)
    parser.add_argument('--reflection-source-dir',type=Path)
    args,rest=parser.parse_known_args();API=args.editor_api_dir;REFLECTION=args.reflection_source_dir
    unittest.main(argv=[__file__,*rest])
