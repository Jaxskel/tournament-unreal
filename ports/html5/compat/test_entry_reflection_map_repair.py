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

    def test_failed_save2_inverse_and_readonly_boundary(self):
        clean=self.text
        for label in ('INSPECTION','ROUTE','SAVE_GUARD'):
            clean=re.sub(r'(?m)^ *// FAILED_SAVE2_'+label+r'_BEGIN\n.*?^ *// FAILED_SAVE2_'+label+r'_END\n', '', clean, flags=re.S)
        clean=clean.replace('\n\n\n// Routed only through', '\n\n// Routed only through')
        self.assertEqual(hashlib.sha256(clean.encode()).hexdigest(),'9e8679b103370128e3d7a70742e9b2de057401d82ef711b67f119a321893d891')
        body=section(self.text,'static int32 ERMInspectFailedSave2(', '// FAILED_SAVE2_INSPECTION_END')
        for token in ('SetCaptureIsDirty','UpdateReflectionCaptureContents','PreSave(', 'SavePackage(', 'AddTicker(', 'InitWorld(', 'RegisterComponent', 'GetMutableDefault'):
            self.assertNotIn(token,body)
        self.assertEqual(body.count('LoadPackage('),1)
        self.assertLess(body.index('FindPackage('),body.index('LoadPackage('))
        self.assertIn('!World->Scene && ERMTarget(World,false,Capture.Target)',body)
        self.assertIn('const bool OK=RowsOK && R.Before() && ERMUnchanged(ProofPin);',body)
        self.assertIn('TEXT("preservation_accepted"),false',body)
        for token in ('Lines.Num()!=4','ProofPin.SHA1!=ProofSHA','R.External(ProofPath)'):
            self.assertIn(token,body)

    def test_failed_save2_actual_proof_rows_and_input_guard(self):
        root=next(x for x in HERE.parents if (x/'work/ut4-html5').is_dir())
        raw=(root/'work/ut4-html5/entry-reflection-save/save2/save.jsonl').read_bytes()
        self.assertEqual(hashlib.sha1(raw).hexdigest(),'48e89afcf61055202073dc541de069ddbe0c0b68')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'93fdc135be17e776e8557a3b60d0b0125086d15ec1904e379999c114b536c6d9')
        self.assertNotEqual(hashlib.sha1(raw+b' ').hexdigest(),hashlib.sha1(raw).hexdigest())
        rows=[json.loads(x) for x in raw.splitlines()]
        helper=section(self.text,'static bool ERMFailedSave2Row(', 'static int32 ERMInspectFailedSave2(')
        admission=section(self.text,'    FERMReceipt R; FString Output,Forbidden,ProofPath,ProofSHA;', '    ProofPath=Full(ProofPath); FWURFile ProofPin;')
        assignments=[]
        for i,row in enumerate(rows):
            for key,value in row.items():
                if isinstance(value,str):assignments.append(f'rows[{i}]->strings[{json.dumps(key)}]={json.dumps(value)};')
                elif isinstance(value,bool):assignments.append(f'rows[{i}]->flags[{json.dumps(key)}]={str(value).lower()};')
        shim=r'''
#include <cassert>
#include <string>
#include <map>
#include <memory>
#define TEXT(x) x
using FString=std::string;using int32=int;using TCHAR=char;
const char* operator*(const FString& s){return s.c_str();}
template<class T>struct TSharedPtr:std::shared_ptr<T>{using std::shared_ptr<T>::shared_ptr;bool IsValid()const{return bool(*this);}};
struct FJsonObject{std::map<FString,FString> strings;std::map<FString,bool> flags;bool TryGetBoolField(const char* k,bool& v){if(!flags.count(k))return false;v=flags[k];return true;}};
FString Str(const TSharedPtr<FJsonObject>& j,const char* k){return j->strings[k];}
const char* ERDPackage="/Game/RestrictedAssets/Maps/UT-Entry";
FString mapSHA="7797936e53bf4267307b0f461ea532632fb8c4a1";bool receiptOK=true;
struct FERMReceipt{FString ReceiptSHA1,Selected;struct Pin{FString SHA1,Identity;}SelectedPin;bool Read(const FString&,bool forSave){assert(!forSave);SelectedPin.SHA1=mapSHA;return receiptOK;}};
std::map<FString,FString> args;bool originalFlag=false;
struct FParse{static bool Param(const char*,const char*){return originalFlag;}static bool Value(const char*,const char* key,FString& out){if(!args.count(key))return false;out=args[key];return true;}};
int WFRStop(const char*){return 3;}
'''
        code=shim+helper+'\nint admission(){FString Params;\n'+admission+'\nreturn 0;}\nint main(){\n'
        code+='TSharedPtr<FJsonObject> rows[4];for(auto& r:rows)r=TSharedPtr<FJsonObject>(new FJsonObject);\n'+'\n'.join(assignments)
        code+='\nFERMReceipt R;R.ReceiptSHA1=rows[0]->strings["source_receipt_sha1"];R.Selected=rows[0]->strings["selected"];R.SelectedPin.SHA1=mapSHA;R.SelectedPin.Identity=rows[3]->strings["saved_identity"];\n'
        code+=r'''
for(int i=0;i<4;++i){assert(ERMFailedSave2Row(rows[i],i,R));
 for(auto key:{"schema","mode","kind","package","source_receipt_sha1","selected"}){auto old=rows[i]->strings[key];rows[i]->strings[key]="bad";assert(!ERMFailedSave2Row(rows[i],i,R));rows[i]->strings[key]=old;}
 rows[i]->flags["visual_success_claim"]=true;assert(!ERMFailedSave2Row(rows[i],i,R));rows[i]->flags["visual_success_claim"]=false;
}
for(auto key:{"status","saved_map_sha1","saved_identity"}){auto old=rows[3]->strings[key];rows[3]->strings[key]="bad";assert(!ERMFailedSave2Row(rows[3],3,R));rows[3]->strings[key]=old;}
rows[3]->flags["save_attempted"]=false;assert(!ERMFailedSave2Row(rows[3],3,R));
args={{"FailedSaveProof=","proof"},{"FailedSaveProofSHA1=","48e89afcf61055202073dc541de069ddbe0c0b68"},{"EntryMapOutput=","out"}};
assert(admission()==0);auto valid=args;
for(auto key:{"FailedSaveProof=","FailedSaveProofSHA1=","EntryMapOutput="}){args=valid;args.erase(key);assert(admission()==3);}
args=valid;args["FailedSaveProofSHA1="]="bad";assert(admission()==3);
for(auto key:{"EntryMapSaveProof=","EntryMapSaveProofSHA1="}){args=valid;args[key]="forbidden";assert(admission()==3);}
args=valid;originalFlag=true;assert(admission()==3);originalFlag=false;
mapSHA="653a6eb7a37f00c5238d210e5f45d7729117a246";assert(admission()==3);
mapSHA="7797936e53bf4267307b0f461ea532632fb8c4a1";receiptOK=false;assert(admission()==3);
}
'''
        compile_run(code)

    def test_failed_save2_observations_independent_compiled(self):
        block=section(self.text,'    // FAILED_SAVE2_OBSERVATIONS_BEGIN','    // FAILED_SAVE2_OBSERVATIONS_END')
        compile_run(r'''
#include <cassert>
#include <string>
#include <map>
using FString=std::string;using int32=int;using int64=long long;
template<class K,class V>using TMap=std::map<K,V>;
struct Guid{FString ToString(){return "guid";}};struct Level{Guid LevelBuildDataId;};struct WorldStub{Level* PersistentLevel;};
bool snap,canon,payload,registry,linked;int sc,pc,rc;
struct FERDState{void* Target=nullptr;static bool Snapshot(WorldStub*,void*,TMap<FString,FString>&,FString&){++sc;return snap;}bool ValidatePayload(FString&,int32&,int64&){++pc;return payload;}FString StateIdText(){return "state";}};
bool ERMCanonical(const TMap<FString,FString>&,FString&,FString&){return canon;}
bool ERMRegistryLinked(WorldStub*,const FString&){return linked;}
bool ERMRegistryFingerprint(WorldStub*,void*,const FString&,FString&,int64&,FString&){++rc;return registry;}
FString ERMBrightness(void*){return "brightness";}
void run(bool TargetOK){Level level;WorldStub w{&level};WorldStub* World=&w;FERDState Capture;
TMap<FString,FString> Rows;FString Digest,CanonicalDigest,Guid,Payload,Brightness,State,RegistryHash,RegistryFlags;int32 Dimension=0;int64 Zeros=0,RegistryBytes=0;
''' + block + r'''
assert(SnapshotAttempted==TargetOK);assert(SnapshotOK==(TargetOK&&snap));assert(CanonicalOK==(TargetOK&&snap&&canon));
assert(PayloadAttempted==TargetOK);assert(PayloadOK==(TargetOK&&payload));assert(RegistryAttempted==(TargetOK&&linked));assert(RegistryOK==(TargetOK&&linked&&registry));
assert(sc==int(TargetOK)&&pc==int(TargetOK)&&rc==int(TargetOK&&linked));
}
int main(){for(int mask=0;mask<64;++mask){snap=mask&1;canon=mask&2;payload=mask&4;registry=mask&8;linked=mask&16;sc=pc=rc=0;run(mask&32);}}
''')

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
struct CaptureStub{int World=0;void* Target=nullptr;bool CheckMapPins(){return Receipt.ok;}} Capture;
bool SettingsDisabled(){return Receipt.ok;}
TSharedPtr<FJsonObject> ERMRecord(const char*,const char*,ReceiptStub&){return std::make_shared<FJsonObject>();}
struct AuthoredStub{int count=78;int Num(){return count;}void GetKeys(TArray<FString>& k){k.push_back("object");} FString FindChecked(const FString&){return "exact row";}} Authored;
struct EvidenceStub{bool ok=true;int calls=0;bool Emit(TSharedPtr<FJsonObject>,int limit){assert(limit==8*1024*1024);++calls;return ok;}} Evidence;
bool finished=false,success=false;
void Finish(bool ok,const char*,TSharedPtr<FJsonObject>){finished=true;success=ok;}
const FString ERMCanonicalDigest="baseline";
const char* ERMRegistryPath="registry";
const char* ERMInspect1SHA1="proof1";const char* ERMInspect2SHA1="proof2";
FString sourceDigest;bool registry;
bool ERMCanonical(AuthoredStub&,FString& out,FString& guid){out=sourceDigest;guid="guid";return true;}
bool ERMRegistryLinked(int,const FString&){return registry;}
void ERMFingerprintFields(TSharedPtr<FJsonObject>,const FString&,long long,const FString&){}
bool ERMRegistryFingerprint(int,void*,const FString&,FString&,long long&,FString&){return true;}
using int64=long long;
bool branch(bool InspectOnly,bool SnapshotOK,FString Digest){bool RegistryProbe=false;sourceDigest=Digest;
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
        source=self.canonical_fixture()+extra+section(self.text,'static bool ERMSHA1(', '// Cross-run proof:')+section(self.text,'static bool ERMReloadIdentity(', 'static bool ERMSame(')+section(self.text,'static bool ERMObjectsEqual(', '// Original bounded archive,')
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
        self.assertIn('ERMLoadedRowsAccepted(ObjectsNow,Str(Proof,TEXT("saved_level_guid")),CanonicalDigest)',verify)

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

    def test_actual_loaded61_contract_with_pinned60_and78_rows(self):
        root=HERE.parents[4]/'work/ut4-html5/entry-reflection-save'
        snapshots=[]
        for folder,pin in [('inspect-loaded-1','0113fb6a81bcf961d743db433c346a2fa0e046c1'),('inspect-loaded-2','306cde051c6b1d7201aa387be6b619492d193900'),('inspect1','cf5e348674462e227410397e4333dec8503b457d')]:
            raw=(root/folder/'inspect.jsonl').read_bytes();self.assertEqual(hashlib.sha1(raw).hexdigest(),pin)
            snapshots.append([json.loads(x) for x in raw.decode().splitlines()][1:-1])
            keys=[r['object_path'] for r in snapshots[-1]]
            self.assertEqual(keys,sorted(keys,key=str.lower)) # fixture shim must match pinned native order
            self.assertIn(pin,self.text)
        registry='/Script/Engine.MapBuildDataRegistry\nLevelLightingQuality[0]=(INVALID)\n'
        self.assertEqual(hashlib.sha1(registry.encode('utf-16le')).hexdigest(),'c60ae14ddad45b2c783be42abaf2dc3791554b2a')
        shim=r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
#include <map>
#include <algorithm>
#define TEXT(x) u##x
using int32=int;using TCHAR=char16_t;using uint8=uint8_t;using uint32=uint32_t;
const int INDEX_NONE=-1;
namespace ESearchCase{enum Type{CaseSensitive};}namespace ESearchDir{enum Type{FromStart};}
struct FString:std::u16string{
 using std::u16string::u16string;FString(const std::u16string&s):std::u16string(s){}int Len()const{return size();}
 const TCHAR*operator*()const{return c_str();}bool StartsWith(const FString&p,ESearchCase::Type)const{return compare(0,p.size(),p)==0;}
 int Find(const FString&p,ESearchCase::Type,ESearchDir::Type=ESearchDir::FromStart,int at=0)const{auto n=find(p,at);return n==npos?-1:int(n);}
 FString Mid(int at,int n=-1)const{return substr(at,n<0?npos:n);}FString Left(int n)const{return substr(0,n);}
 FString ToLower()const{FString r=*this;for(auto&c:r)if(c>=u'A'&&c<=u'Z')c+=32;return r;}
};
template<class T>struct TArray:std::vector<T>{void Sort(){std::sort(this->begin(),this->end(),[](const T&a,const T&b){return a.ToLower()<b.ToLower();});}};
template<class K,class V>struct TMap:std::map<K,V>{
 int Num()const{return this->size();}void Add(const K&k,const V&v){(*this)[k]=v;}void Remove(const K&k){this->erase(k);}
 void GetKeys(TArray<K>&out)const{for(auto&p:*this)out.push_back(p.first);}V&FindChecked(const K&k){return this->at(k);}const V&FindChecked(const K&k)const{return this->at(k);}
 const V*Find(const K&k)const{auto i=this->find(k);return i==this->end()?nullptr:&i->second;}
};
// Independent test SHA1, using standard 80-round definition, not production helper code.
struct FSHA1{
 std::vector<uint8>b;uint32 h[5]={0x67452301,0xefcdab89,0x98badcfe,0x10325476,0xc3d2e1f0};
 static uint32 rol(uint32 x,int n){return (x<<n)|(x>>(32-n));}
 void Update(const uint8*p,int n){b.insert(b.end(),p,p+n);}
 void Final(){uint64_t bits=b.size()*8;b.push_back(128);while(b.size()%64!=56)b.push_back(0);for(int i=7;i>=0;--i)b.push_back(bits>>(i*8));
 for(size_t o=0;o<b.size();o+=64){uint32 w[80];for(int i=0;i<16;++i)w[i]=(uint32(b[o+i*4])<<24)|(uint32(b[o+i*4+1])<<16)|(uint32(b[o+i*4+2])<<8)|b[o+i*4+3];
 for(int i=16;i<80;++i)w[i]=rol(w[i-3]^w[i-8]^w[i-14]^w[i-16],1);
 uint32 a=h[0],c=h[2],d=h[3],e=h[4],bb=h[1];for(int i=0;i<80;++i){uint32 f,k;
 if(i<20){f=(bb&c)|(~bb&d);k=0x5a827999;}else if(i<40){f=bb^c^d;k=0x6ed9eba1;}else if(i<60){f=(bb&c)|(bb&d)|(c&d);k=0x8f1bbcdc;}else{f=bb^c^d;k=0xca62c1d6;}
 uint32 t=rol(a,5)+f+e+k+w[i];e=d;d=c;c=rol(bb,30);bb=a;a=t;}h[0]+=a;h[1]+=bb;h[2]+=c;h[3]+=d;h[4]+=e;}}
 void GetHash(uint8*out){for(int i=0;i<20;++i)out[i]=h[i/4]>>(24-8*(i%4));}
};
FString BytesToHex(const uint8*p,int n){FString r;const char16_t*hex=u"0123456789abcdef";for(int i=0;i<n;++i){r+=hex[p[i]>>4];r+=hex[p[i]&15];}return r;}
const TCHAR* ERMLevelPath=TEXT("/Game/RestrictedAssets/Maps/UT-Entry.UT-Entry:PersistentLevel");
const TCHAR* ERMRegistryPath=TEXT("/Game/RestrictedAssets/Maps/UT-Entry.MapBuildDataRegistry");
'''
        code=shim+section(self.text,'static bool ERMGuid(', 'static bool ERMRegistryLinked(')
        for number,rows in enumerate(snapshots):
            code+=f'\nTMap<FString,FString> fixture{number}(){{TMap<FString,FString> rows;\n'
            for row in rows:code+='rows.Add(TEXT('+json.dumps(row['object_path'])+'),TEXT('+json.dumps(row['snapshot_row'])+'));\n'
            code+='return rows;}\n'
        code+=r'''
TMap<FString,FString> after(TMap<FString,FString> rows){
 rows.Add(ERMRegistryPath,ERMRegistryRow);
 FString level=rows.FindChecked(ERMLevelPath),normal,guid;
 assert(ERMCanonicalLevelRow(ERMLevelPath,level,normal,guid));
 auto at=level.find(guid);level.replace(at,32,u"11111111111111111111111111111111");
 auto map=level.find(u"MapBuildData[0]=\n");assert(map!=FString::npos);
 level.replace(map,FString(u"MapBuildData[0]=\n").size(),u"MapBuildData[0]=MapBuildDataRegistry'/Game/RestrictedAssets/Maps/UT-Entry.MapBuildDataRegistry'\n");
 rows.FindChecked(ERMLevelPath)=level;return rows;
}
int main(){FString digest,guid=TEXT("11111111111111111111111111111111");
 for(auto original:{fixture0(),fixture1()}){
 assert(original.Num()==60);FString canonical,oldGuid;assert(ERMCanonical(original,canonical,oldGuid));assert(canonical==ERMLoadedDigest);
 auto valid=after(original);assert(valid.Num()==61);assert(ERMLoadedRowsAccepted(valid,guid,digest));assert(digest==ERMLoadedDigest);
 assert(!ERMLoadedRowsAccepted(original,guid,digest));assert(!ERMLoadedRowsAccepted(valid,TEXT("22222222222222222222222222222222"),digest));
 auto bad=valid;bad.Remove(ERMRegistryPath);assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 bad=valid;bad.Add(TEXT("extra-registry"),ERMRegistryRow);assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 bad=valid;bad.FindChecked(ERMRegistryPath)=TEXT("/Script/Engine.MapBuildDataRegistry\nLevelLightingQuality[0]=Production\n");assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 bad=valid;bad.Remove(ERMRegistryPath);bad.Add(TEXT("wrong-registry-path"),ERMRegistryRow);assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 bad=valid;auto&row=bad.FindChecked(ERMLevelPath);row+=TEXT("UnexpectedAuthoredProperty[0]=True\n");assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 bad=valid;auto&wrong=bad.FindChecked(ERMLevelPath);wrong.replace(wrong.find(u"MapBuildDataRegistry'"),20,u"WrongBuildDataType___");assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 bad=valid;bad.FindChecked(ERMLevelPath)+=TEXT("MapBuildData[0]=\n");assert(!ERMLoadedRowsAccepted(bad,guid,digest));
 }
 assert(!ERMLoadedRowsAccepted(fixture2(),guid,digest)); // Never accept raw 78 editor rows as loaded preservation.
}
'''
        compile_run(code)

    def test_actual_bounded_archive_cap_seek_backpatch_names_null_flags(self):
        writer=section(self.text,'class FERMRegistryWriter :', 'static bool ERMRegistryFingerprint(')
        compile_run(r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <climits>
#include <string>
#include <vector>
#include <cstdarg>
#define TEXT(x) x
using int64=int64_t;using int32=int32_t;using uint8=uint8_t;using SIZE_T=size_t;
struct FString:std::string{using std::string::string;FString(const std::string&s):std::string(s){}int Len()const{return size();}
 static FString Printf(const char*fmt,...){char out[1024];va_list a;va_start(a,fmt);vsnprintf(out,sizeof(out),fmt,a);va_end(a);return out;}};
struct FName{FString s;FString ToString(){return s;}};
struct UObject{FString path;int calls=0;FString GetPathName(){++calls;return path;}};
template<class T>struct TArray:std::vector<T>{void Reserve(int32 n){this->reserve(n);}int Num()const{return this->size();}void SetNumUninitialized(int32 n,bool){this->resize(n);}T* GetData(){return this->data();}};
struct FMemory{static void Memcpy(void*a,const void*b,size_t n){memcpy(a,b,n);}};
struct FArchive{
 bool ArIsSaving=false,ArIsPersistent=false,ArIsLoading=false,ArIsTransacting=false,ArWantBinaryPropertySerialization=false,
 ArIsFilterEditorOnly=false,ArIsSaveGame=false,ArNoDelta=false,ArIsCountingMemory=false,ArIsObjectReferenceCollector=false,
 ArIsModifyingWeakAndStrongReferences=false,ArAllowLazyLoading=false,ArShouldSkipBulkData=false,ArUseCustomPropertyList=false,
 ArForceByteSwapping=false,ArForceUnicode=false,ArSerializingDefaults=false,error=false;
 unsigned ArPortFlags=0;void*ArCustomPropertyList=nullptr;int version=500;
 virtual ~FArchive(){}virtual void Serialize(void*,int64)=0;virtual void Seek(int64)=0;virtual int64 Tell()=0;virtual int64 TotalSize()=0;
 virtual FString GetArchiveName()const{return "";}virtual void Preload(UObject*){}virtual UObject*GetArchetypeFromLoader(const UObject*){return nullptr;}
 virtual FArchive&operator<<(FName&){return *this;}virtual FArchive&operator<<(UObject*&){return *this;}
 void SetError(){error=true;}void*CookingTarget()const{return nullptr;}int UE4Ver()const{return version;}int LicenseeUE4Ver()const{return 0;}
};
FArchive& operator<<(FArchive& a,FString& s){int32 n=s.size();a.Serialize(&n,4);if(n)a.Serialize(&s[0],n);return a;}
''' + writer + r'''
int main(){
 UObject subject{"subject"},defaults{"defaults"};uint8 b[8]={1,2,3,4,5,6,7,8};
 FERMRegistryWriter w(&subject,&defaults,8);assert(w.FlagsOK());auto flags=w.FlagsText();
 assert(flags.find("port=0")!=FString::npos);assert(flags.find("nodelta=0")!=FString::npos);
 w.Serialize(b,8);assert(w.TotalSize()==8);w.Seek(2);uint8 patch=99;w.Serialize(&patch,1);w.Seek(8);
 assert(w.Bytes[2]==99);assert(w.Tell()==8);assert(!w.Failed);
 w.Serialize(b,1);assert(w.Failed);auto old=w.Bytes;w.Seek(0);w.Serialize(b,8);assert(w.Bytes==old);
 for(int which=0;which<5;++which){FERMRegistryWriter x(&subject,&defaults,8);
 if(which==0)x.Seek(-1);if(which==1)x.Seek(1);if(which==2)x.Serialize(b,-1);if(which==3)x.Serialize(b,INT64_MAX);if(which==4)x.Serialize(nullptr,1);
 assert(x.Failed);assert(x.TotalSize()==0);x.Seek(0);x.Serialize(b,1);assert(x.TotalSize()==0);}
 FERMRegistryWriter invalid(&subject,&defaults,INT64_MAX);assert(invalid.Failed);assert(invalid.Bytes.capacity()==0);
 FERMRegistryWriter names(&subject,&defaults,256);FName name{"Actor_12"};names<<name;
 assert(names.TotalSize()==12);assert(memcmp(names.Bytes.GetData()+4,"Actor_12",8)==0);
 UObject* null=nullptr;auto at=names.Tell();names<<null;assert(names.Bytes[at]==0);assert(names.TotalSize()==at+5);
 UObject* ptr=&subject;at=names.Tell();names<<ptr;assert(names.Bytes[at]==1);assert(subject.calls==1);assert(ptr==&subject);
 assert(names.GetArchetypeFromLoader(&subject)==&defaults);names.Preload(&subject);assert(names.Failed);
 FERMRegistryWriter other(&subject,&defaults,8);other.GetArchetypeFromLoader(&defaults);assert(other.Failed);
 FERMRegistryWriter f(&subject,&defaults,8);f.ArPortFlags=1;assert(!f.FlagsOK());f.ArPortFlags=0;f.ArNoDelta=true;assert(!f.FlagsOK());
 f.ArNoDelta=false;f.ArIsLoading=true;assert(!f.FlagsOK());f.ArIsLoading=false;f.ArIsFilterEditorOnly=true;assert(!f.FlagsOK());
}
''')

    def test_registry_fingerprint_source_flags_and_proof_dominance(self):
        helper=section(self.text,'static bool ERMRegistryFingerprint(', 'static void ERMFingerprintFields(')
        self.assertIn('Class->GetDefaultObject(false)',helper)
        self.assertIn('Registry->Serialize(Writer)',helper)
        self.assertIn('Writer.FlagsText()!=InitialFlags',helper)
        self.assertIn('!ERMObjectsEqual(Before,After)',helper)
        self.assertIn('World->GetOutermost()->IsDirty()!=Dirty',helper)
        self.assertNotIn('NewObject',helper);self.assertNotIn('PreSave(',helper)
        tick=section(self.text,'    bool Tick(float)', 'static TSharedPtr<FERMState>')
        self.assertLess(tick.index('InitialRegistryHash,InitialRegistryBytes,InitialRegistryFlags'),tick.index('Capture.Target->SetCaptureIsDirty()'))
        self.assertLess(tick.index('BeforeRegistryHash!=InitialRegistryHash'),tick.index('GEditor->SavePackage('))
        self.assertGreater(tick.index('PostRegistryHash==InitialRegistryHash'),tick.index('GEditor->SavePackage('))
        self.assertIn('RegistryProbe && !S->InspectOnly',self.text)
        verify=self.text.split('static int32 VerifyEntryReflectionMap(',1)[1]
        self.assertIn('Lines.Num()!=4',verify)
        self.assertIn('Str(Row,TEXT("preservation_contract"))!=ERMPreservationContract',verify)
        self.assertIn('RegistryHash==ExpectedRegistryHash && double(RegistryBytes)==ExpectedRegistryBytes && RegistryFlags==ExpectedRegistryFlags',verify)
        root=HERE.parents[4]/'work/ut4-html5/entry-reflection-save/level-source'
        data=(root/'LazyObjectPtr.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),'70477e9625394550e658c78c8c4990d87c28ce49550f299846fc7a8f3c86dd22')
        saving=section(data.decode(),'if (Ar.IsSaving() || Ar.IsCountingMemory())','else if (Ar.IsLoading())')
        self.assertIn('GuidAnnotation.GetAnnotation(Object)',saving)
        self.assertIn('Ar.GetPortFlags() & PPF_DuplicateForPIE',saving)

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
        for token in ['Lines.Num()!=4','saved_map_sha1','source_receipt_sha1','saved_identity','payload_sha1','brightness_bits','state_id','ActualDimension==128','ObjectsNow.Num()==61']:
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
