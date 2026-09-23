"""Fixed assignment observer host regressions; no UE load, renderer or Windows run.

Actual C++ parent/component/default/template/load-observation bodies execute with
public-API stand-ins. JSON objects are field containers, not UE serialization.
The optional private test rederives the served-registry scope and verifies pins.
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
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponGrenadeAssignmentReport.h'
PRIVATE_SPEC = None
PREFIX = '/Game/RestrictedAssets/Weapons/GrenadeLauncher/'
ROOTS = [PREFIX + p for p in ('BP_GrenadeLauncher', 'BP_GrenadeLauncher_Attach',
    'Materials/MIC_Grenade_Launcher', 'Materials/Material_ThirdPerson/MIC_Grenade_Launcher_3P',
    'Meshes/Grenade_Launcher_1p', 'Meshes/Grenade_Launcher_3p')]


def compile_run(code):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise unittest.SkipTest('host C++ compiler required')
    with tempfile.TemporaryDirectory() as temporary:
        p = Path(temporary)
        (p / 'test.cpp').write_text(code)
        build = subprocess.run([compiler, '-std=c++14', str(p / 'test.cpp'), '-o', str(p / 'test')],
                               capture_output=True, text=True, timeout=45)
        if build.returncode:
            raise AssertionError(build.stderr)
        run = subprocess.run([str(p / 'test')], capture_output=True, text=True, timeout=10)
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)


def body(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


HOST = r'''
#include <cassert>
#include <string>
#include <vector>
#include <set>
#include <map>
#include <memory>
#include <algorithm>
#include <cstdint>
using int32=int;using int64=int64_t;using uint8=unsigned char;using TCHAR=char;
#define TEXT(x) x
constexpr int RF_NeedLoad=1,RF_NeedPostLoad=2,RF_Transient=4,CLASS_Native=8,FUNC_Native=16;
struct FString:std::string{using std::string::string;FString(){}FString(const std::string&s):std::string(s){}int Len()const{return size();}bool StartsWith(const char*p)const{return rfind(p,0)==0;}};
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;void Add(const T&x){this->push_back(x);}int Num()const{return this->size();}bool Contains(const T&x)const{return std::find(this->begin(),this->end(),x)!=this->end();}void Empty(){this->clear();}bool IsValidIndex(int i)const{return i>=0&&i<Num();}T&Last(){return this->back();}T*GetData(){return this->data();}};
template<class T>struct TSet:std::set<T>{void Add(const T&x){this->insert(x);}int Num()const{return this->size();}bool Contains(const T&x)const{return this->count(x);}};
template<class K,class V>struct TMap:std::map<K,V>{bool Contains(const K&x)const{return this->count(x);}};
template<class T>using TSharedPtr=std::shared_ptr<T>;
struct FJsonObject;
struct FJsonValue{TSharedPtr<FJsonObject>object;};
struct FJsonObject{
 std::map<FString,FString>s;std::map<FString,bool>b;std::map<FString,int>n;std::map<FString,TSharedPtr<FJsonObject>>o;std::map<FString,TArray<TSharedPtr<FJsonValue>>>a;
 void SetStringField(const char*k,const FString&v){s[k]=v;}void SetBoolField(const char*k,bool v){b[k]=v;}void SetNumberField(const char*k,int v){n[k]=v;}
 void SetObjectField(const char*k,TSharedPtr<FJsonObject>v){o[k]=v;}void SetArrayField(const char*k,const TArray<TSharedPtr<FJsonValue>>&v){a[k]=v;}
};
TSharedPtr<FJsonObject>WURObject(){return std::make_shared<FJsonObject>();}
TSharedPtr<FJsonValue>MRValue(TSharedPtr<FJsonObject>x){auto v=std::make_shared<FJsonValue>();v->object=x;return v;}
struct UClass;struct UFunction;struct UPackage;
struct UObject{virtual~UObject(){}FString path;UClass*cls=nullptr;UObject*outer=nullptr;int flags=0;std::map<FString,UObject*>props;std::map<FString,bool>bools;UFunction*fn=nullptr;FString GetPathName()const{return path;}UClass*GetClass()const{return cls;}bool HasAnyFlags(int f)const{return flags&f;}UObject*GetOuter(){return outer;}bool IsA(UClass*c)const;UFunction*FindFunction(const FString&){return fn;}};
FString WURPath(const UObject*o){return o?o->path:FString();}
struct UProperty{virtual~UProperty(){}};
struct UObjectPropertyBase:UProperty{FString name;UObject*GetObjectPropertyValue_InContainer(UObject*o){return o->props[name];}};
struct UBoolProperty:UProperty{FString name;bool GetPropertyValue_InContainer(UObject*o){return o->bools[name];}};
struct UClass:UObject{UClass*parent=nullptr;UObject*cdo=nullptr;bool native=false;std::map<FString,UProperty*>fields;UClass*GetSuperClass(){return parent;}UObject*GetDefaultObject(bool create){assert(!create);return cdo;}bool HasAnyClassFlags(int f){assert(f==CLASS_Native);return native;}};
bool UObject::IsA(UClass*c)const{for(auto*k=cls;k;k=k->parent)if(k==c)return true;return false;}
template<class T>T*Cast(UObject*x){return dynamic_cast<T*>(x);}
template<class T>T*FindField(UClass*c,const char*name){for(;c;c=c->parent){auto i=c->fields.find(name);if(i!=c->fields.end())return dynamic_cast<T*>(i->second);}return nullptr;}
using FName=FString;
struct UFunction:UObject{TArray<uint8>Script;bool native=false;bool HasAnyFunctionFlags(int f){assert(f==FUNC_Native);return native;}};
struct FSHAHash{uint8 Hash[20]{};FString ToString(){return "synthetic-hash-only";}};
struct FSHA1{static void HashBuffer(const void*,int count,void*){assert(count>0);}};
struct UMaterialInterface:UObject{};struct UMaterial:UMaterialInterface{unsigned bUsedWithStaticLighting=1,bUsedAsSpecialEngineMaterial=0;};struct UMaterialInstance:UMaterialInterface{UMaterialInterface*Parent=nullptr;};
struct Text{FString value;FString ToString()const{return value;}};
struct UActorComponent:UObject{};
struct UMeshComponent:UActorComponent{TArray<UMaterialInterface*>OverrideMaterials,resolved;int Count=-1,Mobility=2;int GetNumMaterials(){return Count==-1?resolved.Num():Count;}UMaterialInterface*GetMaterial(int i){return resolved.at(i);}UObject*GetAttachParent(){return outer;}Text GetAttachSocketName(){return {"Grip"};}};
struct USkinnedMeshComponent:UMeshComponent{UObject*SkeletalMesh=nullptr;};
struct UStaticMeshComponent:UMeshComponent{UObject*mesh=nullptr;UObject*GetStaticMesh(){return mesh;}};
struct AActor:UObject{TArray<UActorComponent*>components;void GetComponents(TArray<UActorComponent*>&out){out=components;}};
struct UBlueprintGeneratedClass;
struct USCS_Node:UObject{UActorComponent*ComponentTemplate=nullptr,*actual=nullptr;Text GetVariableName(){return {"MeshNode"};}UActorComponent*GetActualComponentTemplate(UBlueprintGeneratedClass*){return actual;}};
struct USimpleConstructionScript{TArray<USCS_Node*>nodes;const TArray<USCS_Node*>&GetAllNodes(){return nodes;}};
struct Key{bool valid=true;UObject*owner=nullptr;bool IsValid()const{return valid;}UObject*GetComponentOwner()const{return owner;}Text GetSCSVariableName()const{return {"MeshNode"};}Text GetAssociatedGuid()const{return {"guid"};}};
struct FComponentOverrideRecord{Key ComponentKey;UActorComponent*ComponentTemplate=nullptr;UClass*ComponentClass=nullptr;};
struct RecordIterator{TArray<FComponentOverrideRecord>*rows;int at=0;explicit operator bool()const{return at<rows->Num();}void operator++(){++at;}FComponentOverrideRecord&operator*(){return (*rows)[at];}};
struct UInheritableComponentHandler:UObject{TArray<FComponentOverrideRecord>records;RecordIterator CreateRecordIterator(){return {&records};}};
struct UBlueprintGeneratedClass:UClass{TArray<UActorComponent*>ComponentTemplates;USimpleConstructionScript*SimpleConstructionScript=nullptr;UInheritableComponentHandler*InheritableComponentHandler=nullptr;TArray<const UBlueprintGeneratedClass*>hierarchy;bool hierarchyOK=true;static bool GetGeneratedClassesHierarchy(UClass*c,TArray<const UBlueprintGeneratedClass*>&out){auto*b=dynamic_cast<UBlueprintGeneratedClass*>(c);out=b->hierarchy;return b->hierarchyOK;}};
struct FMath{static int Max(int a,int b){return std::max(a,b);}};
struct UPackage:UObject{bool dirty=false;bool IsDirty(){return dirty;}FString GetName(){return path;}};
TArray<UPackage*>Packages;UPackage transient;
UPackage*GetTransientPackage(){return &transient;}
template<class T>struct TObjectIterator{int at=0;explicit operator bool()const{return at<Packages.Num();}void operator++(){++at;}T*operator*(){return Packages[at];}};
struct FWURLedger{TMap<FString,FString>Packages;TSet<UPackage*>InitiallyDirty,InitiallyMemoryOnly;};
struct FWURRoot{FString Logical,Target,Role;};
FString Full(FString p){if(!p.empty()&&p.back()=='/')p.pop_back();return p;}
FString operator/(const FString&a,const char*b){return a+"/"+b;}
bool Within(const FString&p,const FString&r){return p==r||(p.rfind(r+"/",0)==0);}
struct FPaths{static FString GetPath(const FString&p){return p.substr(0,p.rfind('/'));}static FString GameDir(){return "F:/selected/UnrealTournament";}static FString EngineDir(){return "F:/selected/Engine";}};
'''


class GrenadeAssignment(unittest.TestCase):
    def test_fixed_scope_no_dispatch_and_admission_order(self):
        s = HEADER.read_text()
        self.assertEqual(re.findall(r'TEXT\("(/Game/[^"\n]+)"\)', s), ROOTS)
        for forbidden in ('GetAllAssets(', 'SearchAllAssets(', 'GetReferencers(', 'LoadPackage(',
                          'WeaponTessellationUpgrade(', 'SavePackage(', 'ClearDirty', 'SetDirtyFlag(',
                          'ProcessEvent(', 'SpawnActor', 'NewObject<', 'SetMaterial(', 'SetParentEditorOnly(',
                          'CompileBlueprint(', 'CreateOverriden', 'ValidateTemplates(', '#include'):
            self.assertNotIn(forbidden, s)
        self.assertEqual(s.count('LoadObject<'), 1)
        control = body(s, 'static int32 WeaponGrenadeAssignmentReport')
        self.assertIn('for (int32 I = 0; I < Fixed.Num(); ++I)', control)
        self.assertLess(control.index('WGAInputs('), control.index('LoadObject<'))
        self.assertLess(control.index('R.Ledger.Check()'), control.index('LoadObject<'))
        self.assertLess(control.index('R.Loaded(TEXT("after_load"))'), control.index('grenade-root-load'))
        self.assertLess(control.rindex('R.Ledger.Check()'), control.index('TEXT("complete"), Done'))
        self.assertNotIn('GetDefaultObject()', s)
        self.assertIn('GetDefaultObject(false)', s)
        self.assertIn('C->ClassGeneratedBy != B', s)
        self.assertIn('Three->Parent != One', s)
        self.assertIn('TEXT("global_usage_complete"), false', s)
        self.assertIn('TEXT("exclusive_runtime_consumption_proven"), false', s)
        self.assertIn('TEXT("normalization_attribution_claimed"), false', s)
        self.assertIn('TEXT("assetsSaved"), 0', s)
        self.assertIn('COMPAT_WEAPON_GRENADE_ASSIGNMENT %s', s)
        self.assertIn('Rows >= 8192', s)
        self.assertIn('8 * 1024 * 1024 - Line.Len()', s)
        admission = body(s, 'static bool WGAInputs')
        for x in ('!WGARootAllowed(Root, Original)', 'PackageNames.Contains(P)', 'Allowed.Contains(P)',
                  'WGARegistryAuditSHA1', 'Packages->Num() != 647', 'R.Ledger.Files.FindChecked(Key).SHA1'):
            self.assertIn(x, admission)

    def test_actual_parent_chain_bounds_and_root_boundary(self):
        s = HEADER.read_text()
        code = HOST + '\n'.join(body(s, x) for x in ('static bool WGAParentChain', 'static bool WGABudget', 'static bool WGARootAllowed')) + r'''
int main(){
 UMaterial master;UMaterialInstance one,three;one.Parent=&master;three.Parent=&one;TArray<UMaterialInterface*>chain;
 assert(WGAParentChain(&three,chain)&&chain.Num()==3&&chain[1]==&one&&chain.Last()==&master);
 one.Parent=&three;assert(!WGAParentChain(&three,chain));one.Parent=nullptr;assert(!WGAParentChain(&one,chain));
 UMaterialInterface unknown;assert(!WGAParentChain(&unknown,chain));assert(!WGAParentChain(nullptr,chain));
 one.Parent=&master;master.flags=RF_NeedPostLoad;assert(!WGAParentChain(&one,chain));master.flags=0;
 std::vector<UMaterialInstance>deep(64);for(int i=0;i<64;i++)deep[i].Parent=i==63?static_cast<UMaterialInterface*>(&master):&deep[i+1];
 assert(!WGAParentChain(&deep[0],chain));assert(WGAParentChain(&deep[1],chain)&&chain.Num()==64);
 assert(WGABudget(2048,8192,8589934592LL));assert(!WGABudget(2049,8192,0));assert(!WGABudget(1,8193,0));assert(!WGABudget(1,1,8589934593LL));assert(!WGABudget(1,1,-1));
 FString original="F:/original/UnrealTournament/Content";
 assert(WGARootAllowed({"F:/selected/UnrealTournament/Content/Weapons","F:/original/UnrealTournament/Content/Weapons","selected"},original));
 assert(WGARootAllowed({"F:/original/Engine/Content","F:/original/Engine/Content","source"},original));
 for(const FWURRoot&r:{FWURRoot{"F:/","F:/","selected"},FWURRoot{"F:/selected/EngineOther","F:/selected/Engine","selected"},FWURRoot{"F:/selected/Engine","F:/elsewhere","selected"},FWURRoot{"F:/original/Engine","F:/selected/Engine","source"},FWURRoot{"F:/selected/Engine","F:/original/Engine","other"}})assert(!WGARootAllowed(r,original));
}
'''
        compile_run(code)

    def test_actual_defaults_slots_templates_and_dirty_failures(self):
        s = HEADER.read_text()
        methods = '\n'.join(body(s, x) for x in ('    bool Loaded(', '    bool Material(', '    bool Component(', '    bool Defaults(', '    bool Templates('))
        code = HOST + body(s, 'static bool WGAParentChain') + r'''
struct FWGAReport{
 FWURLedger Ledger;FString Context;int Components=0,assetSlotsCalls=0,limit=8192;TSet<UPackage*>ObservedPackages;
 TArray<std::pair<FString,TSharedPtr<FJsonObject>>>rows;
 bool Emit(const char*kind,TSharedPtr<FJsonObject>j){if(rows.Num()>=limit)return false;rows.Add({kind,j});return true;}
 bool AssetSlots(UObject*mesh){assert(mesh);assetSlotsCalls++;return !mesh->HasAnyFlags(RF_NeedLoad|RF_NeedPostLoad);}
''' + methods + r'''
};
int main(){
 for(int scenario=0;scenario<15;scenario++){
  UClass componentClass,materialClass,nativeClass;componentClass.path="/Script/Engine.SkeletalMeshComponent";materialClass.path="/Script/Engine.Material";nativeClass.path="/Script/UT.NativeWeapon";nativeClass.native=true;
  UBoolProperty staticFlag,specialFlag;staticFlag.name="bUsedWithStaticLighting";specialFlag.name="bUsedAsSpecialEngineMaterial";materialClass.fields[staticFlag.name]=&staticFlag;materialClass.fields[specialFlag.name]=&specialFlag;
  UMaterial master;master.cls=&materialClass;master.path="/Selected/Master";master.bools[staticFlag.name]=true;
  UMaterialInstance one,three;one.Parent=&master;one.path="/Selected/1P";three.Parent=&one;three.path="/Selected/3P";
  UObject mesh;mesh.path="/Selected/Skeletal";mesh.cls=&componentClass;
  USkinnedMeshComponent nativeMesh,declared,actual,inherited;for(auto*p:{&nativeMesh,&declared,&actual,&inherited}){p->cls=&componentClass;p->path="/Template/Mesh";p->SkeletalMesh=&mesh;p->resolved.Add(&three);p->OverrideMaterials.Add(&one);}
  UObjectPropertyBase meshProp;meshProp.name="Mesh1P";nativeClass.fields[meshProp.name]=&meshProp;
  AActor nativeCDO,cdo;nativeCDO.cls=&nativeClass;nativeCDO.path="/NativeCDO";nativeClass.cdo=&nativeCDO;
  UBlueprintGeneratedClass leaf;leaf.path="/BP_C";leaf.parent=&nativeClass;leaf.cdo=&cdo;leaf.hierarchy.Add(&leaf);cdo.cls=&leaf;cdo.path="/CDO";cdo.props[meshProp.name]=&nativeMesh;cdo.components.Add(&nativeMesh);
  UFunction fn;fn.path="/BP_C/GetPickupMeshTemplate";fn.outer=&leaf;fn.Script.Add(1);cdo.fn=&fn;
  USCS_Node node;node.path="/BP/SCS";node.ComponentTemplate=&declared;node.actual=&actual;USimpleConstructionScript scs;scs.nodes.Add(&node);leaf.SimpleConstructionScript=&scs;leaf.ComponentTemplates.Add(&declared);
  UInheritableComponentHandler handler;leaf.InheritableComponentHandler=&handler;FComponentOverrideRecord rec;rec.ComponentTemplate=&inherited;rec.ComponentClass=&componentClass;rec.ComponentKey.owner=&leaf;handler.records.Add(rec);
  FWGAReport r;
  if(scenario==1)leaf.cdo=nullptr;
  if(scenario==2)node.actual=nullptr;
  if(scenario==3)handler.records[0].ComponentKey.valid=false;
  if(scenario==4)handler.flags=RF_NeedLoad;
  if(scenario==5)nativeMesh.Count=257;
  if(scenario==6)leaf.hierarchyOK=false;
  if(scenario==7)scs.nodes.Add(nullptr);
  if(scenario==8)leaf.ComponentTemplates.resize(257,&actual);
  if(scenario==9)nativeMesh.flags=RF_NeedPostLoad;
  if(scenario==10)master.flags=RF_NeedPostLoad;
  if(scenario==11)three.Parent=&three;
  if(scenario==12)r.limit=0;
  if(scenario==13)nativeClass.parent=&leaf;
  if(scenario==14)fn.Script.resize(1024*1024+1);
  bool ok=r.Templates(&leaf);assert(ok==(scenario==0));
  if(ok){bool defaults=false,slots=false,scsSeen=false,inheritedSeen=false,chain=false;
   for(auto&row:r.rows){auto&j=*row.second;
    if(row.first=="defaults"&&j.s["object"]=="/CDO"){defaults=true;assert(j.s["pickup_function_owner"]=="/BP_C");assert(j.n["pickup_script_bytes"]==1);assert(j.b["pickup_script_present"]&&!j.b["pickup_function_executed"]);assert(j.o["Mesh1P"]->s["value_class"]==componentClass.path);}
    if(row.first=="slot"){slots=true;assert(j.s["resolved"]==three.path&&j.s["override"]==one.path);}
    if(row.first=="scs"){scsSeen=true;assert(j.s["actual_template"]==actual.path);}
    if(row.first=="inherited")inheritedSeen=true;
    if(row.first=="material_chain"&&j.s["material"]==three.path){chain=true;assert(j.a["chain"].Num()==3&&j.b["used_with_static_lighting"]&&!j.b["special_engine_material"]);}
   }assert(defaults&&slots&&scsSeen&&inheritedSeen&&chain&&r.assetSlotsCalls>0);
  }
 }
 UPackage clean,dirty,unexpected,script;clean.path="/Known";dirty.path="/Dirty";unexpected.path="/Unknown";script.path="/Script/Core";dirty.dirty=true;Packages={&clean,&dirty,&unexpected,&script};
 FWGAReport r;r.Ledger.Packages[clean.path]="file";r.Ledger.Packages[dirty.path]="file";
 assert(!r.Loaded("after_load"));assert(r.rows.Num()==4);bool newDirty=false,unknown=false;
 for(auto&row:r.rows){auto&j=*row.second;if(j.s["package"]==dirty.path){newDirty=j.b["new_dirty"];assert(!j.b["normalization_attribution_claimed"]);}if(j.s["package"]==unexpected.path)unknown=j.b["unexpected_package"];}
 assert(newDirty&&unknown&&dirty.dirty);r.Ledger.InitiallyDirty.Add(&dirty);r.Ledger.InitiallyMemoryOnly.Add(&unexpected);assert(r.Loaded("later"));
}
'''
        compile_run(code)

    def test_private_registry_and_api_pins(self):
        if PRIVATE_SPEC is None:
            self.skipTest('pass --private-spec for exact resident registry/API validation')
        raw = PRIVATE_SPEC.read_bytes()
        spec = json.loads(raw)
        expected = re.search(r'WGASpecSHA1 = TEXT\("([0-9a-f]{40})"\)', HEADER.read_text())[1]
        self.assertEqual(hashlib.sha1(raw).hexdigest(), expected)
        workspace = PRIVATE_SPEC.resolve().parents[3]
        for p in [*spec['api_source_pins'], *[spec['registry'][k] for k in ('binary', 'json', 'audit')]]:
            data = (workspace / p['path']).read_bytes()
            self.assertEqual(len(data), p['bytes'])
            self.assertEqual(hashlib.sha1(data).hexdigest(), p['sha1'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), p['sha256'])
        registry = json.loads((workspace / spec['registry']['json']['path']).read_text())
        assets = {x['package']: x for x in registry['assets']}
        deps = {x['package']: x for x in registry['dependencies']}
        self.assertEqual(len(assets), 7871)
        self.assertEqual([x['package'] for x in spec['roots']], ROOTS)
        for root in spec['roots']:
            self.assertEqual(root['class'], assets[root['package']]['class'])
            self.assertEqual(root['object'], assets[root['package']]['object'])
        closure, queue = set(), ROOTS.copy()
        while queue:
            p = queue.pop()
            if p in closure:
                continue
            closure.add(p)
            queue.extend(deps[p]['hard'])
        self.assertEqual(sorted(closure), spec['hard_forward_packages'])
        self.assertEqual(len(closure), 647)
        self.assertFalse(any(assets[p]['class'] == 'World' for p in closure))
        for p in ROOTS:
            hard = sorted(x['package'] for x in deps.values() if p in x['hard'])
            self.assertEqual(hard, spec['registry']['direct_hard_referencers'][p])
        audit = json.loads((workspace / spec['registry']['audit']['path']).read_text())
        for row in audit['rows']:
            p = row['package']
            self.assertEqual(row['asset'], assets[p])
            self.assertEqual(row['dependencies'], deps[p])
            for kind in ('hard', 'soft'):
                self.assertEqual(sorted(x['package'] for x in row['directReferencers'] if x['kind'] == kind),
                                 sorted(x['package'] for x in deps.values() if p in x[kind]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-spec', type=Path)
    args, rest = parser.parse_known_args()
    PRIVATE_SPEC = args.private_spec
    unittest.main(argv=[__file__, *rest])
