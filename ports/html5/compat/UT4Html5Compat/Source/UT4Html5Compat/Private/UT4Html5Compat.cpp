// Original compatibility tooling; contains no copied engine implementation.
#include "UT4Html5CompatCommandlet.h"
#include "Modules/ModuleManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/PackageName.h"
#include "Misc/Parse.h"
#include "Misc/App.h"
#include "Misc/SecureHash.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/CommandLine.h"
#include "HAL/PlatformStackWalk.h"
#include "UObject/Package.h"
#include "UObject/LinkerLoad.h"
#include "UObject/UObjectGlobals.h"
#include "Engine/SkeletalMesh.h"
#include "RHIDefinitions.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceConstant.h"
#include "Materials/MaterialExpressionTextureBase.h"
#include "Materials/MaterialExpressionTextureSampleParameter2D.h"
#include "Materials/MaterialExpressionVectorParameter.h"
#include "Materials/MaterialExpressionMultiply.h"
#include "Materials/MaterialExpressionConstant.h"
#include "Materials/MaterialExpressionFeatureLevelSwitch.h"
#include "Materials/MaterialExpressionSetMaterialAttributes.h"
#include "Materials/MaterialExpressionCustom.h"
#include "Materials/MaterialExpressionSceneDepth.h"
#include "Materials/MaterialExpressionCameraVectorWS.h"
#include "Materials/MaterialExpressionMaterialFunctionCall.h"
#include "Materials/MaterialFunction.h"
#include "MaterialShared.h"
#include "AssetRegistryModule.h"
#include "UObject/UnrealType.h"
#include "UObject/UObjectIterator.h"
#include "Editor.h"
#include "Engine/World.h"
#include "Engine/Level.h"
#include "Components/StaticMeshComponent.h"
#include "PhysicsEngine/BodySetup.h"
#include "CollisionQueryParams.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerStart.h"
#include "Components/CapsuleComponent.h"
#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <windows.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

IMPLEMENT_MODULE(FDefaultModuleImpl, UT4Html5Compat)
DEFINE_LOG_CATEGORY_STATIC(LogUT4Html5Compat, Log, All);

namespace UT4Compat
{
static const TCHAR* OldTextures = TEXT("/Game/EpicInternal/Character/86D_Robot/Textures/");
static const TCHAR* NewTextures = TEXT("/Game/RestrictedAssets/Character/Robot/Textures/");
static const TCHAR* RobotMaterials = TEXT("/Game/RestrictedAssets/Character/Robot/Materials/");
static const TCHAR* RobotNames[] = {
    TEXT("86D_Robot_Head_AO"), TEXT("86D_Robot_Head_M"), TEXT("86D_Robot_Head_N"),
    TEXT("86D_Robot_Legs_AO"), TEXT("86D_Robot_Legs_M"), TEXT("86D_Robot_Legs_N"), TEXT("86D_Robot_Visor_D")
};

static bool Fail(const FString& Message)
{
    UE_LOG(LogUT4Html5Compat, Error, TEXT("%s"), *Message);
    return false;
}
static FString Full(FString Path)
{
    Path = FPaths::ConvertRelativePathToFull(Path);
    FPaths::NormalizeFilename(Path);
    FPaths::CollapseRelativeDirectories(Path);
    while (Path.EndsWith(TEXT("/")) && Path.Len() > 3) Path = Path.LeftChop(1);
    return Path;
}
static bool Within(const FString& Path, const FString& Root)
{
    return Path.Equals(Root, ESearchCase::IgnoreCase) || Path.StartsWith(Root + TEXT("/"), ESearchCase::IgnoreCase);
}
static FString ObjectPath(const FString& Package)
{
    return Package + TEXT(".") + FPackageName::GetShortName(Package);
}
static bool GamePackage(const FString& Package)
{
    return Package.StartsWith(TEXT("/Game/")) && !Package.Contains(TEXT("..")) &&
        !Package.Contains(TEXT(".")) && !Package.Contains(TEXT("\\")) && FPackageName::IsValidLongPackageName(Package);
}
static FString Str(const TSharedPtr<FJsonObject>& Json, const TCHAR* Key)
{
    FString Value;
    Json->TryGetStringField(Key, Value);
    return Value;
}
static bool ReadJson(const FString& Filename, TSharedPtr<FJsonObject>& Json)
{
    FString Text;
    return FFileHelper::LoadFileToString(Text, *Filename) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) && Json.IsValid();
}
static FString HashFile(const FString& Filename)
{
    TArray<uint8> Data;
    if (!FFileHelper::LoadFileToArray(Data, *Filename)) return FString();
    uint8 Digest[20];
    FSHA1::HashBuffer(Data.GetData(), Data.Num(), Digest);
    return BytesToHex(Digest, 20);
}

// Reject junction/symlink ancestors and multiply-linked files. Does not resolve a
// reparse point and then approve its target. Fail closed on non-Windows builds.
static bool Physical(const FString& Filename, bool AllowMissingLeaf)
{
#if PLATFORM_WINDOWS
    const FString Path = Full(Filename);
    if (Path.Len() < 4 || Path[1] != ':' || Path[2] != '/') return Fail(TEXT("Only absolute local-drive paths are supported: ") + Path);
    FString Cursor = Path;
    bool Leaf = true;
    while (Cursor.Len() > 3)
    {
        const DWORD Attr = GetFileAttributesW(*Cursor);
        if (Attr == INVALID_FILE_ATTRIBUTES)
        {
            const DWORD Error = GetLastError();
            if (!(Leaf && AllowMissingLeaf && Error == ERROR_FILE_NOT_FOUND)) return Fail(TEXT("Missing/inaccessible path: ") + Cursor);
        }
        else
        {
            if (Attr & FILE_ATTRIBUTE_REPARSE_POINT) return Fail(TEXT("Refusing reparse point: ") + Cursor);
            if (Leaf && !(Attr & FILE_ATTRIBUTE_DIRECTORY))
            {
                HANDLE Handle = CreateFileW(*Cursor, FILE_READ_ATTRIBUTES,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
                BY_HANDLE_FILE_INFORMATION Info;
                const bool Safe = Handle != INVALID_HANDLE_VALUE && GetFileInformationByHandle(Handle, &Info) && Info.nNumberOfLinks == 1;
                if (Handle != INVALID_HANDLE_VALUE) CloseHandle(Handle);
                if (!Safe) return Fail(TEXT("Cannot establish single-link file: ") + Cursor);
            }
        }
        Leaf = false;
        Cursor = FPaths::GetPath(Cursor);
    }
    return true;
#else
    return Fail(TEXT("Physical save validation requires Windows."));
#endif
}

struct FEntry
{
    FString Package, Operation, Diffuse, SourceParameter, Parent, Shading;
    FLinearColor Tint = FLinearColor::White;
    bool Experimental = false;
    UMaterialInterface* Asset = nullptr;
    UTexture2D* Texture = nullptr;
};

static void ExpectedRobot(const FString& Package, TArray<FString>& Textures)
{
    int32 First = -1, Last = -1;
    if (Package == FString(RobotMaterials) + TEXT("M_86D_Robot_Head")) { First = 0; Last = 2; }
    if (Package == FString(RobotMaterials) + TEXT("M_86D_Robot_Legs")) { First = 3; Last = 5; }
    if (Package == FString(RobotMaterials) + TEXT("M_86D_Robot_Visor")) { First = 6; Last = 6; }
    for (int32 Index = First; First >= 0 && Index <= Last; ++Index)
        Textures.Add(ObjectPath(FString(NewTextures) + RobotNames[Index]));
}

static bool ParseManifest(const TSharedPtr<FJsonObject>& Json, TArray<FEntry>& Entries, TArray<FString>& Meshes, TSet<FString>& Saves)
{
    double Schema = 0;
    if (!Json->TryGetNumberField(TEXT("schema"), Schema) || Schema != 1) return Fail(TEXT("Expected manifest schema 1."));
    const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
    if (!Json->TryGetArrayField(TEXT("meshes"), Array)) return Fail(TEXT("Manifest requires a meshes array."));
    for (const auto& Item : *Array)
    {
        FString Path;
        if (!Item->TryGetString(Path)) return Fail(TEXT("Mesh paths must be strings."));
        Meshes.Add(Path);
    }
    if (!Json->TryGetArrayField(TEXT("assets"), Array)) return Fail(TEXT("Manifest requires an assets array."));
    for (const auto& Item : *Array)
    {
        if (Item->Type != EJson::Object) return Fail(TEXT("Asset entries must be objects."));
        const TSharedPtr<FJsonObject> J = Item->AsObject();
        FEntry E;
        E.Package = Str(J, TEXT("package")); E.Operation = Str(J, TEXT("operation"));
        E.Diffuse = Str(J, TEXT("diffuse_texture")); E.SourceParameter = Str(J, TEXT("source_parameter"));
        E.Parent = Str(J, TEXT("fallback_parent")); E.Shading = Str(J, TEXT("shading"));
        J->TryGetBoolField(TEXT("experimental"), E.Experimental);
        if (E.Shading.IsEmpty()) E.Shading = TEXT("default_lit");
        if (!GamePackage(E.Package) || Saves.Contains(E.Package.ToLower())) return Fail(TEXT("Invalid/duplicate package: ") + E.Package);
        Saves.Add(E.Package.ToLower());
        if (!E.Parent.IsEmpty())
        {
            if (!GamePackage(E.Parent) || !E.Parent.StartsWith(TEXT("/Game/HTML5Compat/")) || Saves.Contains(E.Parent.ToLower()))
                return Fail(TEXT("Parent must be a unique /Game/HTML5Compat/ package."));
            Saves.Add(E.Parent.ToLower());
        }
        const TArray<TSharedPtr<FJsonValue>>* Tint = nullptr;
        if (J->HasField(TEXT("tint")))
        {
            if (!J->TryGetArrayField(TEXT("tint"), Tint) || Tint->Num() != 3) return Fail(TEXT("tint must have three numbers in [0,1]."));
            float Values[3];
            for (int32 I = 0; I < 3; ++I)
            {
                double V = 0;
                if (!(*Tint)[I]->TryGetNumber(V) || !FMath::IsFinite(V) || V < 0 || V > 1) return Fail(TEXT("Invalid tint."));
                Values[I] = float(V);
            }
            E.Tint = FLinearColor(Values[0], Values[1], Values[2], 1);
        }
        if (E.Shading != TEXT("default_lit") && E.Shading != TEXT("unlit")) return Fail(TEXT("shading must be default_lit or unlit."));
        if (E.Operation == TEXT("repair_robot"))
        {
            TArray<FString> Expected; ExpectedRobot(E.Package, Expected);
            if (Expected.Num() == 0 || !E.Parent.IsEmpty() || !E.Diffuse.IsEmpty() || !E.SourceParameter.IsEmpty())
                return Fail(TEXT("repair_robot is restricted to the three named Robot materials."));
        }
        else if (E.Operation == TEXT("fallback_textured"))
        {
            if (E.Diffuse.IsEmpty() || FPackageName::ObjectPathToPackageName(E.Diffuse) == E.Diffuse)
                return Fail(TEXT("fallback_textured requires an explicit diffuse texture object path."));
        }
        else if (E.Operation == TEXT("fallback_color_experimental"))
        {
            if (!E.Experimental || !E.Diffuse.IsEmpty() || !E.SourceParameter.IsEmpty() || FMath::Max3(E.Tint.R, E.Tint.G, E.Tint.B) <= 0)
                return Fail(TEXT("Color fallback requires experimental=true, a visible tint and no texture/parameter."));
            E.Shading = TEXT("unlit");
        }
        else return Fail(TEXT("Unknown operation: ") + E.Operation);
        Entries.Add(E);
    }
    return true;
}

struct FSavePolicy
{
    FString ContentRoot, OriginalRoot;
    TMap<FString, FString> Files;
    bool Read(const FString& Receipt, const FString& Manifest, const TSet<FString>& Saves)
    {
        TSharedPtr<FJsonObject> J;
        if (!Physical(Receipt, false) || !ReadJson(Receipt, J)) return Fail(TEXT("Cannot read private COW receipt."));
        double Schema = 0;
        if (!J->TryGetNumberField(TEXT("schema"), Schema) || Schema != 1) return Fail(TEXT("Bad receipt schema."));
        if (Str(J, TEXT("manifest_sha1")).IsEmpty() || !Str(J, TEXT("manifest_sha1")).Equals(HashFile(Manifest), ESearchCase::IgnoreCase))
            return Fail(TEXT("Manifest changed since COW preparation; prepare a new overlay."));
        ContentRoot = Full(Str(J, TEXT("content_root")));
        OriginalRoot = Full(Str(J, TEXT("original_root")));
        if (Str(J, TEXT("original_root")).IsEmpty() || !ContentRoot.Equals(Full(FPaths::GameContentDir()), ESearchCase::IgnoreCase) ||
            !Full(Str(J, TEXT("project_dir"))).Equals(Full(FPaths::GameDir()), ESearchCase::IgnoreCase) || Within(ContentRoot, OriginalRoot))
            return Fail(TEXT("Receipt does not describe this private project."));
        if (!Physical(ContentRoot, false)) return false;
        const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
        if (!J->TryGetArrayField(TEXT("files"), Array)) return Fail(TEXT("Receipt lacks files."));
        for (const auto& V : *Array)
        {
            if (V->Type != EJson::Object) return Fail(TEXT("Invalid receipt entry."));
            auto O = V->AsObject();
            FString P = Str(O, TEXT("package")), F = Full(Str(O, TEXT("file")));
            if (!GamePackage(P) || !Saves.Contains(P.ToLower()) || Files.Contains(P.ToLower())) return Fail(TEXT("Receipt allowlist mismatch."));
            if (!F.Equals(Full(ContentRoot / P.Mid(6) + TEXT(".uasset")), ESearchCase::IgnoreCase)) return Fail(TEXT("Unexpected destination: ") + F);
            Files.Add(P.ToLower(), F);
        }
        if (Files.Num() != Saves.Num()) return Fail(TEXT("Incomplete save allowlist."));
        for (const auto& KV : Files) if (!Check(KV.Key)) return false;
        return true;
    }
    bool Check(const FString& Package) const
    {
        const FString* File = Files.Find(Package.ToLower());
        if (!File || !Within(*File, ContentRoot) || Within(*File, OriginalRoot)) return Fail(TEXT("Unallowlisted save: ") + Package);
        if (!Full(FPackageName::LongPackageNameToFilename(Package, TEXT(".uasset"))).Equals(*File, ESearchCase::IgnoreCase))
            return Fail(TEXT("Package resolves outside its private copy: ") + Package);
        return Physical(*File, true);
    }
    bool Save(UMaterialInterface* Asset) const
    {
        const FString P = Asset->GetOutermost()->GetName();
        if (!Check(P)) return false;
        Asset->MarkPackageDirty();
        const bool OK = UPackage::SavePackage(Asset->GetOutermost(), Asset, RF_Public | RF_Standalone, *Files.FindChecked(P.ToLower()));
        if (!OK) return Fail(TEXT("Save failed: ") + P);
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_SAVED %s"), *P);
        return true;
    }
};

static void CollectTextures(const TArray<UMaterialExpression*>& Expressions, TSet<UMaterialFunction*>& Seen, TArray<UTexture*>& Textures, bool& NullTexture)
{
    for (UMaterialExpression* Expr : Expressions)
    {
        if (auto* T = Cast<UMaterialExpressionTextureBase>(Expr))
        {
            if (T->Texture) Textures.AddUnique(T->Texture); else NullTexture = true;
        }
        if (auto* Call = Cast<UMaterialExpressionMaterialFunctionCall>(Expr))
        {
            if (Call->MaterialFunction && !Seen.Contains(Call->MaterialFunction))
            {
                Seen.Add(Call->MaterialFunction);
                CollectTextures(Call->MaterialFunction->FunctionExpressions, Seen, Textures, NullTexture);
            }
        }
    }
}
static TSharedPtr<FJsonObject> Describe(UMaterialInterface* M)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetStringField(TEXT("material"), M ? M->GetPathName() : TEXT("<null>"));
    if (!M) return J;
    J->SetStringField(TEXT("class"), M->GetClass()->GetName());
    UMaterial* Base = M->GetMaterial();
    J->SetStringField(TEXT("base_material"), Base ? Base->GetPathName() : TEXT("<null>"));
    TArray<TSharedPtr<FJsonValue>> Params, Textures;
    if (Base)
    {
        TArray<FName> Names; TArray<FGuid> IDs;
        Base->GetAllTextureParameterNames(Names, IDs);
        for (FName Name : Names)
        {
            UTexture* T = nullptr; const bool Found = M->GetTextureParameterValue(Name, T);
            TSharedPtr<FJsonObject> P = MakeShareable(new FJsonObject);
            P->SetStringField(TEXT("name"), Name.ToString());
            P->SetStringField(TEXT("value"), Found && T ? T->GetPathName() : TEXT("<null>"));
            Params.Add(MakeShareable(new FJsonValueObject(P)));
        }
        TArray<UTexture*> Ts; TSet<UMaterialFunction*> Seen; bool Null = false;
        CollectTextures(Base->Expressions, Seen, Ts, Null);
        for (UTexture* T : Ts) Textures.Add(MakeShareable(new FJsonValueString(T->GetPathName())));
        J->SetBoolField(TEXT("has_null_texture_expression"), Null);
    }
    J->SetArrayField(TEXT("texture_parameters"), Params);
    J->SetArrayField(TEXT("base_graph_textures_including_functions"), Textures);
    return J;
}
static void Emit(const TSharedPtr<FJsonObject>& J)
{
    FString Text;
    FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_REPORT %s"), *Text);
}
#include "MaterialPreflightReport.h"
#include "BlobShadowPreflightReport.h"
#include "WeaponPreflightReport.h"
#include "WeaponSupplementReport.h"
#include "PhysicsPreflightReport.h"
#include "WeaponFidelityRepair.h"
#include "BlobShadowExperiment.h"
static bool ReportMeshes(const TArray<FString>& Meshes)
{
    bool OK = true;
    for (const FString& Path : Meshes)
    {
        UObject* Obj = LoadObject<UObject>(nullptr, *Path);
        TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject); J->SetStringField(TEXT("mesh"), Path);
        TArray<TSharedPtr<FJsonValue>> Slots;
        auto Slot = [&](int32 Index, FName Name, UMaterialInterface* Material)
        {
            auto S = Describe(Material); S->SetNumberField(TEXT("slot"), Index); S->SetStringField(TEXT("slot_name"), Name.ToString());
            Slots.Add(MakeShareable(new FJsonValueObject(S)));
            if (!Material) OK = false;
        };
        if (auto* Mesh = Cast<USkeletalMesh>(Obj))
            for (int32 I = 0; I < Mesh->Materials.Num(); ++I) Slot(I, Mesh->Materials[I].MaterialSlotName, Mesh->Materials[I].MaterialInterface);
        else if (auto* StaticMesh = Cast<UStaticMesh>(Obj))
            for (int32 I = 0; I < StaticMesh->StaticMaterials.Num(); ++I) Slot(I, StaticMesh->StaticMaterials[I].MaterialSlotName, StaticMesh->StaticMaterials[I].MaterialInterface);
        else { Fail(TEXT("Not a loadable skeletal/static mesh: ") + Path); OK = false; }
        J->SetArrayField(TEXT("slots"), Slots); Emit(J);
    }
    return OK;
}

static void MakeSurface(UMaterial* M, const FEntry& E)
{
    M->PreEditChange(nullptr);
    M->Expressions.Empty();
    for (int32 P = 0; P < MP_MAX; ++P)
        if (FExpressionInput* Input = M->GetExpressionInputForProperty(EMaterialProperty(P))) *Input = FExpressionInput();
    M->bUseMaterialAttributes = false;
    M->MaterialDomain = MD_Surface; M->BlendMode = BLEND_Opaque;
    M->TwoSided = false; M->DitheredLODTransition = false;
    M->BaseColor.UseConstant = false; M->EmissiveColor.UseConstant = false;
    M->Normal.UseConstant = false; M->WorldPositionOffset.UseConstant = false;
    M->NumCustomizedUVs = 0;
    M->SetShadingModel(E.Shading == TEXT("unlit") ? MSM_Unlit : MSM_DefaultLit);
    M->Metallic.UseConstant = true; M->Metallic.Constant = 0;
    M->Roughness.UseConstant = true; M->Roughness.Constant = 0.7f;
    M->Specular.UseConstant = true; M->Specular.Constant = 0.5f;
    M->Opacity.UseConstant = true; M->Opacity.Constant = 1;
    M->OpacityMask.UseConstant = true; M->OpacityMask.Constant = 1;
    auto* Tint = NewObject<UMaterialExpressionVectorParameter>(M);
    Tint->ParameterName = TEXT("CompatTint"); Tint->DefaultValue = E.Tint;
    M->Expressions.Add(Tint);
    UMaterialExpression* Output = Tint;
    if (E.Texture)
    {
        auto* Sample = NewObject<UMaterialExpressionTextureSampleParameter2D>(M);
        Sample->ParameterName = E.SourceParameter.IsEmpty() ? FName(TEXT("CompatDiffuse")) : FName(*E.SourceParameter);
        Sample->Texture = E.Texture;
        Sample->AutoSetSampleType();
        M->Expressions.Add(Sample);
        auto* Mul = NewObject<UMaterialExpressionMultiply>(M);
        Mul->A.Connect(0, Sample); Mul->B.Connect(0, Tint); M->Expressions.Add(Mul); Output = Mul;
    }
    if (E.Shading == TEXT("unlit")) M->EmissiveColor.Connect(0, Output); else M->BaseColor.Connect(0, Output);
    // This is a new editor graph. Set usage before PostEditChange creates its
    // render resources; SetMaterialUsage would recompile a still-null resource.
    M->bUsedWithSkeletalMesh = true;
    M->PostEditChange();
}

static bool CheckRobot(UMaterialInterface* Asset, const FEntry& E)
{
    UMaterial* Base = Asset->GetMaterial();
    if (!Base) return Fail(TEXT("Robot base missing: ") + E.Package);
    TArray<UTexture*> Ts; TSet<UMaterialFunction*> Seen; bool Null = false;
    CollectTextures(Base->Expressions, Seen, Ts, Null);
    TArray<FString> Expected; ExpectedRobot(E.Package, Expected);
    for (const FString& Path : Expected)
    {
        bool Found = false;
        for (UTexture* T : Ts) if (T->GetPathName() == Path) Found = true;
        if (!Found) return Fail(TEXT("Robot texture not bound: ") + Path);
    }
    for (UTexture* T : Ts) if (T->GetPathName().StartsWith(OldTextures)) return Fail(TEXT("Old Robot texture reference remains."));
    if (FLinkerLoad* L = Asset->GetLinker())
        for (const FObjectImport& Import : L->ImportMap)
            if (Import.ObjectName.ToString().StartsWith(OldTextures)) return Fail(TEXT("Old Robot package import remains."));
    return true;
}
static bool CheckFallback(UMaterialInterface* Asset, const FEntry& E)
{
    UMaterial* M = Asset->GetMaterial();
    if (!M || M == UMaterial::GetDefaultMaterial(MD_Surface) || M->BlendMode != BLEND_Opaque || !M->bUsedWithSkeletalMesh || M->bUseMaterialAttributes)
        return Fail(TEXT("Fallback is not the expected opaque skeletal surface: ") + E.Package);
    if (M->GetShadingModel() != (E.Shading == TEXT("unlit") ? MSM_Unlit : MSM_DefaultLit)) return Fail(TEXT("Fallback shading mismatch."));
    if (!E.Parent.IsEmpty() && M->GetOutermost()->GetName() != E.Parent) return Fail(TEXT("Fallback parent mismatch."));
    if (auto* MI = Cast<UMaterialInstanceConstant>(Asset))
    {
        if (MI->GetBlendMode() != BLEND_Opaque || MI->GetShadingModel() != M->GetShadingModel()) return Fail(TEXT("Instance base overrides remain."));
    }
    FLinearColor Tint;
    if (!Asset->GetVectorParameterValue(TEXT("CompatTint"), Tint) || !Tint.Equals(E.Tint)) return Fail(TEXT("Fallback tint mismatch."));
    TArray<UTexture*> Ts; TSet<UMaterialFunction*> Seen; bool Null = false;
    CollectTextures(M->Expressions, Seen, Ts, Null);
    if (E.Operation == TEXT("fallback_textured"))
    {
        UTexture* T = nullptr;
        const FName Param = E.SourceParameter.IsEmpty() ? FName(TEXT("CompatDiffuse")) : FName(*E.SourceParameter);
        if (!Asset->GetTextureParameterValue(Param, T) || !T || T->GetPathName() != E.Diffuse || Ts.Num() != 1 || Null)
            return Fail(TEXT("Fallback diffuse texture mismatch: ") + E.Package);
    }
    else if (Ts.Num() || Null) return Fail(TEXT("Experimental color fallback unexpectedly references textures."));
    if (M->Expressions.Num() != (E.Operation == TEXT("fallback_textured") ? 3 : 1)) return Fail(TEXT("Unexpected fallback graph."));
    FExpressionInput* Output = M->GetExpressionInputForProperty(E.Shading == TEXT("unlit") ? MP_EmissiveColor : MP_BaseColor);
    if (!Output || !Output->Expression) return Fail(TEXT("Fallback output disconnected."));
    for (int32 P = 0; P < MP_MAX; ++P)
    {
        FExpressionInput* Input = M->GetExpressionInputForProperty(EMaterialProperty(P));
        if (Input && Input != Output && Input->Expression) return Fail(TEXT("Unexpected active fallback output."));
    }
    return true;
}

static bool RejectConfiguredRobotRedirects()
{
    TArray<FString> Redirects;
    GConfig->GetArray(TEXT("/Script/Engine.Engine"), TEXT("ActiveGameNameRedirects"), Redirects, GEngineIni);
    for (const FString& R : Redirects)
        if (R.Contains(OldTextures)) return Fail(TEXT("Remove persistent Robot redirects; Verify must run without them."));
    return true;
}
} // namespace UT4Compat

UUT4Html5CompatCommandlet::UUT4Html5CompatCommandlet(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    IsClient = true; IsServer = false; IsEditor = true; LogToConsole = true;
}

int32 UUT4Html5CompatCommandlet::Main(const FString& Params)
{
    using namespace UT4Compat;
    FString Mode, ManifestPath, ReceiptPath, MeshOverride;
    FParse::Value(*Params, TEXT("Mode="), Mode);
    FParse::Value(*Params, TEXT("Manifest="), ManifestPath);
    FParse::Value(*Params, TEXT("Receipt="), ReceiptPath);
    FParse::Value(*Params, TEXT("Meshes="), MeshOverride);
    // A separate read-only entry point: its spec cannot enter Apply/Verify or COW.
    if (Mode.Equals(TEXT("MaterialReport"), ESearchCase::IgnoreCase))
        return MaterialPreflightReport(Params);
    if (Mode.Equals(TEXT("BlobShadowReport"), ESearchCase::IgnoreCase))
        return BlobShadowPreflightReport(Params);
    if (Mode.Equals(TEXT("WeaponReport"), ESearchCase::IgnoreCase))
        return WeaponPreflightReport(Params);
    if (Mode.Equals(TEXT("WeaponSupplementReport"), ESearchCase::IgnoreCase))
        return WeaponSupplementReport(Params);
    if (Mode.Equals(TEXT("FidelityReport"), ESearchCase::IgnoreCase))
    {
        // Both fixed scopes report independently; neither can enter Apply.
        const int32 WeaponResult = WeaponPreflightReport(Params);
        const int32 BlobResult = BlobShadowPreflightReport(Params);
        return WeaponResult == 0 && BlobResult == 0 ? 0 : 1;
    }
    if (Mode.Equals(TEXT("PhysicsReport"), ESearchCase::IgnoreCase))
        return PhysicsPreflightReport(Params);
    if (Mode.Equals(TEXT("WeaponRepairApply"), ESearchCase::IgnoreCase))
        return WeaponFidelityRepair(Params, false);
    if (Mode.Equals(TEXT("WeaponRepairVerify"), ESearchCase::IgnoreCase))
        return WeaponFidelityRepair(Params, true);
    if (Mode.Equals(TEXT("BlobShadowExperiment"), ESearchCase::IgnoreCase))
        return BlobShadowExperiment(Params);
    const bool Apply = Mode.Equals(TEXT("Apply"), ESearchCase::IgnoreCase);
    const bool Verify = Mode.Equals(TEXT("Verify"), ESearchCase::IgnoreCase);
    const bool Report = Mode.Equals(TEXT("Report"), ESearchCase::IgnoreCase);
    if ((!Apply && !Verify && !Report) || ManifestPath.IsEmpty())
    { Fail(TEXT("Required: -Mode=Report|Apply|Verify -Manifest=<json>; Apply/Verify also require -Receipt=<json>.")); return 1; }
    if (Apply && !FApp::CanEverRender())
    { Fail(TEXT("Apply requires -AllowCommandletRendering and no -NullRHI; this engine needs material render resources before editing.")); return 1; }
    TSharedPtr<FJsonObject> Json;
    TArray<FEntry> Entries; TArray<FString> Meshes; TSet<FString> Saves;
    if (!ReadJson(ManifestPath, Json) || !ParseManifest(Json, Entries, Meshes, Saves)) return 1;
    if (!MeshOverride.IsEmpty()) { Meshes.Empty(); MeshOverride.ParseIntoArray(Meshes, TEXT(";"), true); }
    FSavePolicy Policy;
    if ((Apply || Verify) && (!Policy.Read(ReceiptPath, ManifestPath, Saves) || !RejectConfiguredRobotRedirects())) return 1;
    if (Apply || Verify)
    {
        // Main must be the first loader of every selected package in this process.
        for (const FEntry& E : Entries)
            if (FindPackage(nullptr, *E.Package)) { Fail(TEXT("Selected package already loaded; use a fresh process without startup asset loads: ") + E.Package); return 1; }
    }
    if (Apply)
    {
        bool Repair = false;
        for (const FEntry& E : Entries) Repair |= E.Operation == TEXT("repair_robot");
        if (Repair)
            for (const TCHAR* Name : RobotNames)
                FLinkerLoad::AddGameNameRedirect(FName(*(FString(OldTextures) + Name)), FName(*(FString(NewTextures) + Name)));
    }
    // Load/preflight the entire manifest before any asset mutation or save.
    bool ReportOK = true;
    for (FEntry& E : Entries)
    {
        E.Asset = LoadObject<UMaterialInterface>(nullptr, *ObjectPath(E.Package));
        if (!E.Asset)
        {
            Fail(TEXT("Cannot load selected material: ") + E.Package);
            if (Report) { ReportOK = false; continue; }
            return 1;
        }
        if (Report) { Emit(Describe(E.Asset)); continue; }
        if (Apply && E.Operation != TEXT("repair_robot"))
        {
            const bool Instance = Cast<UMaterialInstanceConstant>(E.Asset) != nullptr;
            if ((!Instance && !Cast<UMaterial>(E.Asset)) || (Instance != !E.Parent.IsEmpty()))
            { Fail(TEXT("Only UMaterial/MIC supported; MIC needs fallback_parent, UMaterial must omit it.")); return 1; }
            if (!E.Parent.IsEmpty() && (FindPackage(nullptr, *E.Parent) || FPackageName::DoesPackageExist(E.Parent)))
            { Fail(TEXT("Fallback parent must be new; refusing overwrite: ") + E.Parent); return 1; }
            if (E.Operation == TEXT("fallback_textured"))
            {
                E.Texture = LoadObject<UTexture2D>(nullptr, *E.Diffuse);
                if (!E.Texture || E.Texture->CompressionSettings == TC_Normalmap)
                { Fail(TEXT("Diffuse must be a loadable non-normal Texture2D: ") + E.Diffuse); return 1; }
                if (!E.SourceParameter.IsEmpty())
                {
                    UTexture* Original = nullptr;
                    if (!E.Asset->GetTextureParameterValue(FName(*E.SourceParameter), Original) || Original != E.Texture)
                    { Fail(TEXT("Explicit source_parameter does not resolve to diffuse_texture: ") + E.Package); return 1; }
                }
            }
        }
        if (E.Operation == TEXT("repair_robot") && !CheckRobot(E.Asset, E)) return 1;
        if (Verify && E.Operation != TEXT("repair_robot") && !CheckFallback(E.Asset, E)) return 1;
    }
    if (Report) return ReportMeshes(Meshes) && ReportOK ? 0 : 1;
    if (Verify)
    {
        const bool OK = ReportMeshes(Meshes);
        UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_VERIFY asset-structure=%s; HTML5 shaders and browser rendering still require cook/runtime tests."), OK ? TEXT("PASS") : TEXT("FAIL"));
        return OK ? 0 : 1;
    }
    for (FEntry& E : Entries)
    {
        if (!Policy.Check(E.Package) || (!E.Parent.IsEmpty() && !Policy.Check(E.Parent))) return 1;
        if (E.Operation != TEXT("repair_robot"))
        {
            UMaterial* Surface = Cast<UMaterial>(E.Asset);
            if (!Surface)
                Surface = NewObject<UMaterial>(CreatePackage(nullptr, *E.Parent), FName(*FPackageName::GetShortName(E.Parent)), RF_Public | RF_Standalone);
            {
                FMaterialUpdateContext Update;
                Update.AddMaterial(Surface);
                MakeSurface(Surface, E);
                if (auto* MI = Cast<UMaterialInstanceConstant>(E.Asset))
                {
                    Update.AddMaterialInstance(MI); MI->PreEditChange(nullptr);
                    MI->SetParentEditorOnly(Surface); MI->ClearParameterValuesEditorOnly();
                    FMaterialInstanceBasePropertyOverrides Overrides;
                    MI->UpdateStaticPermutation(FStaticParameterSet(), Overrides);
                    MI->PostEditChange();
                }
            }
            if (!CheckFallback(E.Asset, E)) return 1;
            if (Surface != E.Asset && !Policy.Save(Surface)) return 1;
        }
        if (!Policy.Save(E.Asset)) return 1;
    }
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_APPLY complete; launch a separate Verify process without redirects."));
    return 0;
}
