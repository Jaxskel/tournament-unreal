// Original read-only observer. Include inside UT4Compat after WeaponTessellationUpgrade.h.
// Engine declarations must be included by the owning CPP outside this namespace.
// No Epic implementation is reproduced here. Partial log records are never success.
static const TCHAR* WURSpecSHA1 = TEXT("1b54ea67d5725d669d5bd8722b043c3759c8bf08");
static TSharedPtr<FJsonObject> WURObject() { return MakeShareable(new FJsonObject); }
static FString WURPath(const UObject* O) { return O ? O->GetPathName() : FString(); }
static TArray<FString> WURMaps()
{
    TArray<FString> R;
    R.Add(TEXT("/Game/RestrictedAssets/Maps/WIP/DM-DeckTest"));
    R.Add(TEXT("/Game/RestrictedAssets/Maps/UT-Entry"));
    R.Add(TEXT("/Game/RestrictedAssets/Maps/DM-Outpost23"));
    return R;
}
struct FWURLog
{
    int32 Rows = 0, Characters = 0;
    FString Run;
    bool MaterialsDiagnostic = false;
    TMap<FString, int32> Counts;
    bool Emit(const TCHAR* Kind, TSharedPtr<FJsonObject> J)
    {
        if (MaterialsDiagnostic && FString(Kind) == TEXT("complete")) return Fail(TEXT("Diagnostic cannot claim global completion"));
        J->SetStringField(TEXT("schema"), MaterialsDiagnostic ? TEXT("ut4-weapon-usage-diagnostic-v1") : TEXT("ut4-weapon-usage-v2"));
        if (MaterialsDiagnostic)
        {
            J->SetStringField(TEXT("cohort"), TEXT("materials")); J->SetBoolField(TEXT("global_usage_complete"), false);
            J->SetStringField(TEXT("global_scope_status"), TEXT("global_not_revalidated"));
        }
        J->SetStringField(TEXT("run"), Run);
        J->SetStringField(TEXT("kind"), Kind);
        J->SetNumberField(TEXT("sequence"), Rows);
        J->SetBoolField(TEXT("complete"), FString(Kind) == TEXT("complete"));
        J->SetBoolField(TEXT("read_only"), true);
        J->SetBoolField(TEXT("authorizes_material_flag_change"), false);
        FString Line;
        if (!FJsonSerializer::Serialize(J.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Line)) ||
            Rows >= 2000000 || Line.Len() > 65536 || Characters > 536870912 - Line.Len())
            return Fail(TEXT("WeaponUsageReport output budget; incomplete"));
        ++Rows; Characters += Line.Len(); ++Counts.FindOrAdd(FString(Kind));
        if (MaterialsDiagnostic) { UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_USAGE_DIAGNOSTIC %s"), *Line); }
        else { UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_WEAPON_USAGE %s"), *Line); }
        return true;
    }
};
// Read-only mappings are explicit, SHA-bound input-manifest entries. They do not
// change Physical(), proof admission or any save policy. Longest logical root wins;
// the handle-resolved target must equal physical_root + the exact relative suffix.
struct FWURRoot
{
    FString Logical, Target, Role;
};
static bool WURLocalPath(const FString& P)
{
    return P.Len() > 3 && ((P[0] >= 'A' && P[0] <= 'Z') || (P[0] >= 'a' && P[0] <= 'z')) &&
        P[1] == ':' && P[2] == '/' && !P.Mid(2).Contains(TEXT(":"));
}
#if PLATFORM_WINDOWS
static bool WURFinalPath(HANDLE H, FString& Out)
{
    TCHAR Buffer[32768];
    const DWORD N = GetFinalPathNameByHandleW(H, Buffer, 32768, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
    if (!N || N >= 32768) return false;
    FString P(Buffer); P.ReplaceInline(TEXT("\\"), TEXT("/"));
    if (P.StartsWith(TEXT("//?/"))) P = P.Mid(4);
    if (!WURLocalPath(P)) return false;
    Out = Full(P); return true;
}
static bool WURMappedOpen(const FString& Path, const FWURRoot& Root, bool Directory, HANDLE& H, FString& Target)
{
    H = INVALID_HANDLE_VALUE;
    if (!Within(Path, Root.Logical)) return false;
    const FString Expected = Root.Target + Path.Mid(Root.Logical.Len());
    H = CreateFileW(*Path, Directory ? FILE_READ_ATTRIBUTES : GENERIC_READ, FILE_SHARE_READ,
        nullptr, OPEN_EXISTING, Directory ? FILE_FLAG_BACKUP_SEMANTICS : FILE_ATTRIBUTE_NORMAL, nullptr);
    BY_HANDLE_FILE_INFORMATION Info;
    if (H != INVALID_HANDLE_VALUE && WURFinalPath(H, Target) && Target.Equals(Expected, ESearchCase::IgnoreCase) &&
        Physical(Target, false) && GetFileInformationByHandle(H, &Info) &&
        ((Info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0) == Directory && (Directory || Info.nNumberOfLinks == 1)) return true;
    if (H != INVALID_HANDLE_VALUE) CloseHandle(H);
    H = INVALID_HANDLE_VALUE; return false;
}
#endif
// Hash the held handle, not a second path-based open. No write/delete sharing;
// bounded streaming memory; verify the logical mapping again before closing.
struct FWURFile
{
    FString Path, Target, SHA1, Identity;
    FWURRoot Root;
    int64 Size = 0;
    bool Missing = false, Mapped = false;
    static bool Inspect(const FString& Path, bool MayBeMissing, FWURFile& Out, const FWURRoot* Mapping = nullptr,
        int64 Remaining = 68719476736LL, bool ReadBytes = true)
    {
        Out.Path = Full(Path);
        Out.Mapped = Mapping != nullptr;
        if (Mapping) Out.Root = *Mapping;
        if (!WURLocalPath(Out.Path) || (!Mapping && !Physical(Out.Path, MayBeMissing))) return false;
#if PLATFORM_WINDOWS
        const DWORD Attr = GetFileAttributesW(*Out.Path);
        if (Attr == INVALID_FILE_ATTRIBUTES)
        {
            if (!MayBeMissing || GetLastError() != ERROR_FILE_NOT_FOUND) return false;
            Out.Missing = true;
            if (Mapping)
            {
                HANDLE Parent; FString TargetParent;
                if (!WURMappedOpen(FPaths::GetPath(Out.Path), *Mapping, true, Parent, TargetParent)) return false;
                Out.Target = TargetParent / FPaths::GetCleanFilename(Out.Path);
                const DWORD TargetAttr = GetFileAttributesW(*Out.Target);
                const bool Absent = TargetAttr == INVALID_FILE_ATTRIBUTES && GetLastError() == ERROR_FILE_NOT_FOUND;
                HANDLE Again; FString AgainTarget;
                BY_HANDLE_FILE_INFORMATION A, B;
                bool Stable = WURMappedOpen(FPaths::GetPath(Out.Path), *Mapping, true, Again, AgainTarget);
                if (Stable)
                {
                    Stable = AgainTarget == TargetParent && GetFileInformationByHandle(Parent, &A) && GetFileInformationByHandle(Again, &B) &&
                        A.dwVolumeSerialNumber == B.dwVolumeSerialNumber && A.nFileIndexHigh == B.nFileIndexHigh && A.nFileIndexLow == B.nFileIndexLow;
                    CloseHandle(Again);
                }
                CloseHandle(Parent); return Stable && Absent && Physical(Out.Target, true);
            }
            Out.Target = Out.Path; return true;
        }
        HANDLE H = INVALID_HANDLE_VALUE;
        if (Mapping)
        { if (!WURMappedOpen(Out.Path, *Mapping, false, H, Out.Target)) return false; }
        else
        { Out.Target = Out.Path; H = CreateFileW(*Out.Path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr); }
        if (H == INVALID_HANDLE_VALUE) return false;
        BY_HANDLE_FILE_INFORMATION A, B;
        FString HeldTarget;
        bool OK = WURFinalPath(H, HeldTarget) && HeldTarget.Equals(Out.Target, ESearchCase::IgnoreCase) &&
            GetFileInformationByHandle(H, &A) && A.nNumberOfLinks == 1 && !(A.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY);
        if (OK)
        {
            Out.Size = (int64(A.nFileSizeHigh) << 32) | A.nFileSizeLow;
            if (Out.Size < 0 || Out.Size > 1073741824LL || Out.Size > Remaining) { CloseHandle(H); return false; }
            FSHA1 Hash; TArray<uint8> Buffer; if (ReadBytes) Buffer.SetNumUninitialized(1024 * 1024); int64 Read = 0;
            while (OK && ReadBytes && Read < Out.Size)
            {
                const DWORD Want = DWORD(FMath::Min<int64>(Buffer.Num(), Out.Size - Read)); DWORD Got = 0;
                OK = ReadFile(H, Buffer.GetData(), Want, &Got, nullptr) && Got == Want;
                if (OK) { Hash.Update(Buffer.GetData(), Got); Read += Got; }
            }
            if (ReadBytes)
            { uint8 Digest[20]; Hash.Final(); Hash.GetHash(Digest); Out.SHA1 = BytesToHex(Digest, 20).ToLower(); }
            OK = OK && GetFileInformationByHandle(H, &B) && B.nNumberOfLinks == 1 &&
                A.dwVolumeSerialNumber == B.dwVolumeSerialNumber && A.nFileIndexHigh == B.nFileIndexHigh && A.nFileIndexLow == B.nFileIndexLow &&
                A.nFileSizeHigh == B.nFileSizeHigh && A.nFileSizeLow == B.nFileSizeLow &&
                CompareFileTime(&A.ftLastWriteTime, &B.ftLastWriteTime) == 0 && CompareFileTime(&A.ftCreationTime, &B.ftCreationTime) == 0;
            Out.Identity = FString::Printf(TEXT("%08x:%08x%08x:%08x%08x:%08x%08x"), A.dwVolumeSerialNumber,
                A.nFileIndexHigh, A.nFileIndexLow, A.ftCreationTime.dwHighDateTime, A.ftCreationTime.dwLowDateTime,
                A.ftLastWriteTime.dwHighDateTime, A.ftLastWriteTime.dwLowDateTime);
            if (OK && Mapping)
            {
                HANDLE Again; FString TargetAgain;
                OK = WURMappedOpen(Out.Path, *Mapping, false, Again, TargetAgain);
                if (OK)
                {
                    BY_HANDLE_FILE_INFORMATION C;
                    OK = TargetAgain.Equals(Out.Target, ESearchCase::IgnoreCase) && GetFileInformationByHandle(Again, &C) &&
                        A.dwVolumeSerialNumber == C.dwVolumeSerialNumber && A.nFileIndexHigh == C.nFileIndexHigh && A.nFileIndexLow == C.nFileIndexLow;
                    CloseHandle(Again);
                }
            }
        }
        CloseHandle(H); return OK;
#else
        return false;
#endif
    }
};
struct FWURLedger
{
    TMap<FString, FWURFile> Files;
    TMap<FString, FString> Packages;
    TSet<UPackage*> InitiallyDirty;
    TSet<UPackage*> InitiallyMemoryOnly;
    TMap<FString, TArray<FString>> ConfigDirectories;
    TMap<FString, bool> ConfigPresence;
    FWURLog* Observer = nullptr;
    FString Phase = TEXT("admission");
    FString InventoryFrom, InventoryResolvedPath;
    int32 InventoryIndex = -1, InventoryDependencyIndex = -1, InventoryAll = -1, InventoryHard = -1;
    bool InventoryIsHard = false, InventoryExists = false;
    TArray<FWURRoot> ReadRoots;
    int64 Bytes = 0;
    const FWURRoot* Mapping(const FString& Path) const
    {
        const FWURRoot* Best = nullptr;
        for (const FWURRoot& R : ReadRoots)
            if (Within(Full(Path), R.Logical) && (!Best || R.Logical.Len() > Best->Logical.Len())) Best = &R;
        return Best;
    }
    bool Add(const FString& Path, bool MayBeMissing = false, const FString& Expected = FString(), bool ReadOnlyMapping = false)
    {
        const FString Canonical = Full(Path), Key = Canonical.ToLower();
        const FWURRoot* Root = ReadOnlyMapping ? Mapping(Canonical) : nullptr;
        if (ReadOnlyMapping && !Root) return false;
        if (FWURFile* Prior = Files.Find(Key))
        {
            if ((Prior->Missing && !MayBeMissing) || (!Expected.IsEmpty() && !Prior->SHA1.Equals(Expected, ESearchCase::IgnoreCase)) ||
                (Root && !Prior->Target.Equals(Root->Target + Canonical.Mid(Root->Logical.Len()), ESearchCase::IgnoreCase))) return false;
            // A selected physical file may have been fingerprinted during the
            // preloaded-package baseline. Strict reuse requires fresh strict
            // admission, never a mapped-file exemption from proof/save policy.
            if (!ReadOnlyMapping && Prior->Mapped)
            {
                FWURFile Strict;
                if (!FWURFile::Inspect(Path, MayBeMissing, Strict) || Strict.Target != Prior->Target ||
                    Strict.Identity != Prior->Identity || Strict.SHA1 != Prior->SHA1 || Strict.Missing != Prior->Missing || Strict.Size != Prior->Size) return false;
                *Prior = Strict;
            }
            return true;
        }
        FWURFile F;
        if (Files.Num() >= 100000 || !FWURFile::Inspect(Path, MayBeMissing, F, Root, 68719476736LL - Bytes) || F.Size < 0 ||
            Bytes > int64(68719476736LL) - F.Size || (!Expected.IsEmpty() && !F.SHA1.Equals(Expected, ESearchCase::IgnoreCase))) return false;
        Bytes += F.Size; Files.Add(Key, F); return true;
    }
    bool InventoryFailure(const TCHAR* Reason, const FString& From, const FString& Package,
        const FString& Path = FString(), int32 Edges = -1, int32 Queue = -1) const
    {
        if (Observer)
        {
            auto J = WURObject(); J->SetStringField(TEXT("reason"), Reason); J->SetStringField(TEXT("from"), From);
            J->SetStringField(TEXT("package"), Package); J->SetStringField(TEXT("path"), Path);
            J->SetStringField(TEXT("phase"), Phase); J->SetNumberField(TEXT("packages"), Packages.Num());
            J->SetNumberField(TEXT("files"), Files.Num()); J->SetNumberField(TEXT("bytes"), double(Bytes));
            J->SetNumberField(TEXT("edges"), Edges); J->SetNumberField(TEXT("queue"), Queue);
            J->SetNumberField(TEXT("from_index"), InventoryIndex); J->SetNumberField(TEXT("dependency_index"), InventoryDependencyIndex);
            J->SetNumberField(TEXT("all_count"), InventoryAll); J->SetNumberField(TEXT("hard_count"), InventoryHard);
            if (InventoryDependencyIndex >= 0)
            {
                J->SetBoolField(TEXT("hard"), InventoryIsHard); J->SetBoolField(TEXT("exists"), InventoryExists);
                J->SetStringField(TEXT("resolved_package_path"), InventoryResolvedPath);
            }
            J->SetNumberField(TEXT("package_limit"), 32768); J->SetNumberField(TEXT("file_limit"), 100000);
            J->SetNumberField(TEXT("byte_limit"), double(68719476736LL)); J->SetNumberField(TEXT("edge_limit"), 262144);
            if (!Path.IsEmpty())
                if (const FWURRoot* M = Mapping(Path))
                {
                    J->SetStringField(TEXT("logical_root"), M->Logical); J->SetStringField(TEXT("physical_root"), M->Target);
                    J->SetStringField(TEXT("expected_target"), M->Target + Full(Path).Mid(M->Logical.Len()));
                }
            Observer->Emit(TEXT("inventory_failure"), J);
        }
        return Fail(TEXT("WeaponUsageReport inventory failure: ") + FString(Reason) + TEXT(" from=") + WFRContext(From) +
            TEXT(" package=") + WFRContext(Package) + TEXT(" path=") + WFRContext(Path));
    }
    bool Package(const FString& P)
    {
        if (Packages.Contains(P)) return true;
        if (P.StartsWith(TEXT("/Script/"))) return true;
        FString File;
        if (Packages.Num() >= 32768) return InventoryFailure(TEXT("package_budget"), InventoryFrom, P);
        if (!FPackageName::IsValidLongPackageName(P)) return InventoryFailure(TEXT("invalid_package_name"), InventoryFrom, P);
        if (!FPackageName::DoesPackageExist(P, nullptr, &File)) return InventoryFailure(TEXT("package_missing"), InventoryFrom, P);
        if (!(File.EndsWith(TEXT(".uasset")) || File.EndsWith(TEXT(".umap")))) return InventoryFailure(TEXT("package_extension"), InventoryFrom, P, File);
        if (!Add(File, false, FString(), true)) return InventoryFailure(TEXT("main_file_admission"), InventoryFrom, P, File);
        if (!Add(FPaths::ChangeExtension(File, TEXT("uexp")), true, FString(), true))
            return InventoryFailure(TEXT("uexp_admission"), InventoryFrom, P, FPaths::ChangeExtension(File, TEXT("uexp")));
        if (!Add(FPaths::ChangeExtension(File, TEXT("ubulk")), true, FString(), true))
            return InventoryFailure(TEXT("ubulk_admission"), InventoryFrom, P, FPaths::ChangeExtension(File, TEXT("ubulk")));
        Packages.Add(P, Full(File)); return true;
    }
    bool ConfigDirectory(const FString& Directory, bool Initial)
    {
        const FString Root = Full(Directory);
        TArray<FString> Names;
        const bool Present = IFileManager::Get().DirectoryExists(*Root);
        if (!Initial && (!ConfigPresence.Contains(Root) || ConfigPresence.FindChecked(Root) != Present)) return false;
        if (Present)
        {
#if PLATFORM_WINDOWS
            TArray<FString> Directories; Directories.Add(Root); TSet<FString> Targets; int32 Entries = 0;
            for (int32 I = 0; I < Directories.Num(); ++I)
            {
                const FString Dir = Directories[I]; const FWURRoot* M = Mapping(Dir); if (!M) return false;
                HANDLE H; FString Target;
                if (!WURMappedOpen(Dir, *M, true, H, Target)) return false;
                if (Targets.Contains(Target.ToLower())) { CloseHandle(H); return false; }
                Targets.Add(Target.ToLower());
                // Enumerate incrementally: stop before growing arrays past the
                // budget, including non-INI entries, rather than cap afterwards.
                WIN32_FIND_DATAW Entry;
                HANDLE Search = FindFirstFileW(*(Target / TEXT("*")), &Entry);
                bool OK = Search != INVALID_HANDLE_VALUE || GetLastError() == ERROR_FILE_NOT_FOUND;
                if (Search != INVALID_HANDLE_VALUE)
                {
                    for (;;)
                    {
                        const FString N(Entry.cFileName);
                        if (N != TEXT(".") && N != TEXT(".."))
                        {
                            if (++Entries > 8192) { OK = false; break; }
                            if (Entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) Directories.Add(Dir / N);
                            else if (N.EndsWith(TEXT(".ini"), ESearchCase::IgnoreCase)) Names.Add(Dir / N);
                        }
                        if (!FindNextFileW(Search, &Entry)) { OK = GetLastError() == ERROR_NO_MORE_FILES; break; }
                    }
                    FindClose(Search);
                }
                HANDLE Again; FString AgainTarget; BY_HANDLE_FILE_INFORMATION A, B;
                if (OK && WURMappedOpen(Dir, *M, true, Again, AgainTarget))
                {
                    OK = AgainTarget == Target && GetFileInformationByHandle(H, &A) && GetFileInformationByHandle(Again, &B) &&
                        A.dwVolumeSerialNumber == B.dwVolumeSerialNumber && A.nFileIndexHigh == B.nFileIndexHigh && A.nFileIndexLow == B.nFileIndexLow;
                    CloseHandle(Again);
                }
                else OK = false;
                CloseHandle(H); if (!OK) return false;
            }
#else
            return false;
#endif
        }
        else
        {
#if PLATFORM_WINDOWS
            // Validate absence through an approved, existing ancestor. Access
            // errors and remapped ancestors are not evidence of absence.
            const FWURRoot* M = Mapping(Root); if (!M) return false;
            FString Ancestor = FPaths::GetPath(Root);
            while (Within(Ancestor, M->Logical) && !IFileManager::Get().DirectoryExists(*Ancestor))
            { const FString Parent = FPaths::GetPath(Ancestor); if (Parent == Ancestor) return false; Ancestor = Parent; }
            HANDLE H; FString Target;
            if (!WURMappedOpen(Ancestor, *M, true, H, Target)) return false;
            const FString MissingTarget = M->Target + Root.Mid(M->Logical.Len());
            const DWORD Attr = GetFileAttributesW(*MissingTarget), Error = GetLastError();
            const DWORD LogicalAttr = GetFileAttributesW(*Root), LogicalError = GetLastError();
            CloseHandle(H);
            if (Attr != INVALID_FILE_ATTRIBUTES || LogicalAttr != INVALID_FILE_ATTRIBUTES ||
                (Error != ERROR_FILE_NOT_FOUND && Error != ERROR_PATH_NOT_FOUND) ||
                (LogicalError != ERROR_FILE_NOT_FOUND && LogicalError != ERROR_PATH_NOT_FOUND)) return false;
#else
            return false;
#endif
        }
        if (Names.Num() > 8192) return false;
        for (FString& N : Names) N = Full(N);
        Names.Sort();
        if (!Initial) return ConfigDirectories.Contains(Root) && Names == ConfigDirectories.FindChecked(Root);
        for (const FString& N : Names) if (!Within(N, Root) || !Add(N, false, FString(), true) || Files.FindChecked(N.ToLower()).Size > 8 * 1024 * 1024) return false;
        ConfigDirectories.Add(Root, Names); ConfigPresence.Add(Root, Present); return true;
    }
    bool LoadFailure(const TCHAR* Issue, const FString& Package) const
    {
        if (Observer)
        {
            auto J = WURObject(); J->SetStringField(TEXT("issue"), Issue); J->SetStringField(TEXT("package"), Package);
            J->SetStringField(TEXT("phase"), Phase); J->SetBoolField(TEXT("normalization_attribution_claimed"), false);
            Observer->Emit(TEXT("load_observation"), J);
        }
        return Fail(TEXT("WeaponUsageReport incomplete: ") + FString(Issue) + TEXT(" package=") + WFRContext(Package) + TEXT(" phase=") + WFRContext(Phase));
    }
    // Native loader internals are not intercepted. Recheck the explicit package
    // and sidecars around every observer load; all dependency bytes are checked
    // before the first load and at completion. Main must freeze the source roots.
    bool LoadPins(const FString& Package) const
    {
        const FString* File = Packages.Find(Package);
        if (!File) return LoadFailure(TEXT("unfingerprinted_explicit_load"), Package);
        for (const FString& Path : {*File, FPaths::ChangeExtension(*File, TEXT("uexp")), FPaths::ChangeExtension(*File, TEXT("ubulk"))})
        {
            const FWURFile* A = Files.Find(Full(Path).ToLower()); FWURFile B;
            if (!A || !FWURFile::Inspect(Path, A->Missing, B, A->Mapped ? &A->Root : nullptr, 68719476736LL, false) ||
                A->Target != B.Target || A->Missing != B.Missing || A->Identity != B.Identity || A->Size != B.Size)
                return LoadFailure(TEXT("load_path_or_identity_drift"), Package);
        }
        return true;
    }
    bool BeforeLoad(const FString& Package, const FString& Where)
    { Phase = Where; return Loaded() && LoadPins(Package); }
    bool AfterLoad(const FString& Package) const { return Loaded() && LoadPins(Package); }
    bool Loaded() const
    {
        for (TObjectIterator<UPackage> It; It; ++It)
        {
            UPackage* P = *It;
            if (P->IsDirty() && !InitiallyDirty.Contains(P)) return LoadFailure(TEXT("dirty_after_baseline"), P->GetName());
            if (P == GetTransientPackage() || P->HasAnyFlags(RF_Transient) || P->GetName().StartsWith(TEXT("/Script/"))) continue;
            if (!Packages.Contains(P->GetName()) && !InitiallyMemoryOnly.Contains(P)) return LoadFailure(TEXT("unfingerprinted_loaded_package"), P->GetName());
        }
        return true;
    }
    bool Check(FWURLog* Log = nullptr) const
    {
        for (const auto& KV : Packages)
        {
            FString File;
            if (!FPackageName::DoesPackageExist(KV.Key, nullptr, &File) || !Full(File).Equals(KV.Value, ESearchCase::IgnoreCase)) return false;
        }
        for (const auto& KV : Files)
        {
            const FWURFile& A = KV.Value; FWURFile B;
            if (!FWURFile::Inspect(A.Path, A.Missing, B, A.Mapped ? &A.Root : nullptr) || A.Target != B.Target || A.Missing != B.Missing || A.Size != B.Size || A.Identity != B.Identity || A.SHA1 != B.SHA1)
                return Fail(TEXT("WeaponUsageReport input drift: ") + WFRContext(A.Path));
            if (Log)
            {
                auto J = WURObject(); J->SetStringField(TEXT("path"), A.Path); J->SetBoolField(TEXT("missing"), A.Missing);
                J->SetStringField(TEXT("target_before"), A.Target); J->SetStringField(TEXT("target_after"), B.Target);
                J->SetBoolField(TEXT("read_only_mapping"), A.Mapped); J->SetStringField(TEXT("logical_root"), A.Root.Logical);
                J->SetStringField(TEXT("physical_root"), A.Root.Target);
                J->SetNumberField(TEXT("bytes"), double(A.Size)); J->SetStringField(TEXT("physical_before"), A.Identity);
                J->SetStringField(TEXT("physical_after"), B.Identity); J->SetStringField(TEXT("sha1_before"), A.SHA1);
                J->SetStringField(TEXT("sha1_after"), B.SHA1); if (!Log->Emit(TEXT("file"), J)) return false;
            }
        }
        return Loaded();
    }
};
static TArray<TSharedPtr<FJsonValue>> WURStrings(const TArray<FString>& Values)
{
    TArray<TSharedPtr<FJsonValue>> R;
    for (const FString& S : Values) R.Add(MakeShareable(new FJsonValueString(S)));
    return R;
}
struct FWURReport
{
    IAssetRegistry& Registry;
    FWURLog Log;
    FWURLedger Ledger;
    TArray<FAssetData> Assets;
    TArray<FString> RegistryIdentity;
    TSet<FString> Closure, Referencers, BlueprintObjects, ClassPaths, MapPaths;
    TArray<UClass*> Classes;
    TArray<UWorld*> Worlds;
    TMap<FString, TArray<FString>> Queries;
    TSet<FString> MissingSoftPackages;
    TMap<FString, TArray<FString>> DependencyQueries;
    FString Context;
    int32 Edges = 0, Actors = 0, Components = 0;
    explicit FWURReport(IAssetRegistry& R) : Registry(R) { Ledger.Observer = &Log; }
    bool Query(const FString& P, EAssetRegistryDependencyType::Type Type, bool Reverse, TArray<FName>& Out)
    {
        // The captured declaration does not specify false-versus-empty semantics.
        // Never turn a failed query into a claim of complete, empty coverage.
        const bool OK = Reverse ? Registry.GetReferencers(FName(*P), Out, Type) : Registry.GetDependencies(FName(*P), Out, Type);
        if (OK && Out.Num() <= 32768) return true;
        auto J = WURObject(); J->SetStringField(TEXT("package"), P); J->SetBoolField(TEXT("reverse"), Reverse);
        J->SetNumberField(TEXT("dependency_type"), int32(Type)); J->SetBoolField(TEXT("query_succeeded"), OK);
        Log.Emit(TEXT("registry_query_failure"), J); return false;
    }
    bool RegistryRows(bool Initial)
    {
        TArray<FAssetData> Now; if (!Registry.GetAllAssets(Now, true)) return false;
        if (Registry.IsLoadingAssets() || Now.Num() == 0 || Now.Num() > 200000) return false;
        TArray<FString> IDs;
        for (const FAssetData& A : Now)
        {
            FString Generated, Parent;
            A.GetTagValue(FName(TEXT("GeneratedClass")), Generated); A.GetTagValue(FName(TEXT("ParentClass")), Parent);
            IDs.Add(A.ObjectPath.ToString() + TEXT("|") + A.PackageName.ToString() + TEXT("|") + A.AssetClass.ToString() + TEXT("|") + Generated + TEXT("|") + Parent);
            if (!Initial) continue;
            auto J = WURObject(); J->SetStringField(TEXT("object"), A.ObjectPath.ToString()); J->SetStringField(TEXT("package"), A.PackageName.ToString());
            J->SetStringField(TEXT("asset_class"), A.AssetClass.ToString()); J->SetStringField(TEXT("generated_class_tag"), Generated);
            J->SetStringField(TEXT("parent_class_tag"), Parent);
            if (!Log.Emit(TEXT("registry_asset"), J)) return false;
        }
        IDs.Sort();
        if (!Initial) return IDs == RegistryIdentity;
        Assets = MoveTemp(Now); RegistryIdentity = MoveTemp(IDs); return true;
    }
    bool InventoryFailure(const TCHAR* Reason, const FString& From, const FString& Package, int32 Edges, int32 Queue)
    {
        Context = FString(Reason) + TEXT(" from=") + From + TEXT(" package=") + Package;
        return Ledger.InventoryFailure(Reason, From, Package, FString(), Edges, Queue);
    }
    TArray<FString> DiagnosticPrerequisites;
    TMap<FString, FString> HistoricalInputs;
    bool PrepareMaterialsDiagnostic(const FString& Spec)
    {
        TSharedPtr<FJsonObject> J; if (!ReadJson(Spec, J)) return false;
        auto D = J->GetObjectField(TEXT("materials_diagnostic"));
        for (const auto& V : D->GetArrayField(TEXT("prerequisite_packages")))
        { const FString P = V->AsString(); if (!GamePackage(P) || DiagnosticPrerequisites.Contains(P)) return false; DiagnosticPrerequisites.Add(P); }
        if (DiagnosticPrerequisites.Num() != 28 || HistoricalInputs.Num() != 2) return false;
        for (const auto& V : D->GetArrayField(TEXT("history_files")))
        {
            auto H = V->AsObject(); const FString Role = Str(H, TEXT("role")); const FString* Path = HistoricalInputs.Find(Role);
            if (!Path || !Ledger.Add(*Path, false, Str(H, TEXT("sha1"))) ||
                double(Ledger.Files.FindChecked(Full(*Path).ToLower()).Size) != H->GetNumberField(TEXT("bytes"))) return false;
        }
        auto History = D->GetObjectField(TEXT("historical_failure"));
        History->SetStringField(TEXT("report_path"), HistoricalInputs.FindChecked(TEXT("usage-history-report2-log")));
        History->SetStringField(TEXT("result_path"), HistoricalInputs.FindChecked(TEXT("usage-history-report2-result")));
        return Log.Emit(TEXT("historical_failure"), History);
    }
    bool MaterialDiagnosticSeeds(TArray<FString>& Seeds)
    {
        Seeds = DiagnosticPrerequisites;
        TArray<FString> Candidates; Candidates.Add(WTUMaster());
        for (int32 I = 0; I < Candidates.Num(); ++I)
        {
            TArray<FName> Names; if (!Query(Candidates[I], EAssetRegistryDependencyType::Hard, true, Names)) return false;
            if (Names.Num() > 262144 - Edges) return false;
            Edges += Names.Num(); TArray<FString> Values;
            for (FName N : Names)
            {
                const FString P = N.ToString(); Values.Add(P); TArray<FAssetData> Rows;
                if (!Registry.GetAssetsByPackageName(N, Rows, true)) return false;
                for (const FAssetData& A : Rows)
                    if (A.AssetClass == FName(TEXT("MaterialInstanceConstant")) && !Candidates.Contains(P))
                    { if (Candidates.Num() >= 32768) return false; Candidates.Add(P); Seeds.AddUnique(P); }
            }
            Values.Sort(); Queries.Add(Candidates[I] + TEXT("|") + FString::FromInt(int32(EAssetRegistryDependencyType::Hard)), Values);
        }
        return true;
    }
    bool Inventory()
    {
        Ledger.Phase = TEXT("relevant_inventory");
        // Registry metadata is global; file fingerprints are scoped. Reverse
        // references find every potential user before any explicit native load.
        TArray<FString> Reverse; Reverse.Add(WTUMaster()); TSet<FString> Seen; Seen.Add(WTUMaster());
        int32 QueryEdges = 0;
        for (int32 I = 0; I < Reverse.Num(); ++I)
        {
            Ledger.InventoryIndex = I;
            TArray<FName> Names; const bool ReverseOK = Query(Reverse[I], EAssetRegistryDependencyType::Packages, true, Names);
            Ledger.InventoryAll = Names.Num();
            if (!ReverseOK)
                return InventoryFailure(TEXT("reverse_query"), Reverse[I], FString(), QueryEdges, Reverse.Num());
            if (Names.Num() > 32768 || Names.Num() > 262144 - QueryEdges)
                return InventoryFailure(TEXT("reverse_edge_budget"), Reverse[I], FString(), QueryEdges, Reverse.Num());
            QueryEdges += Names.Num(); TArray<FString> Values;
            for (FName N : Names)
            {
                const FString P = N.ToString(); Values.Add(P);
                if (Log.MaterialsDiagnostic)
                {
                    auto J = WURObject(); J->SetStringField(TEXT("dependency"), Reverse[I]); J->SetStringField(TEXT("referencer"), P);
                    J->SetStringField(TEXT("edge_types"), TEXT("Packages")); J->SetBoolField(TEXT("native_coverage_claimed"), false);
                    if (!Log.Emit(TEXT("referencer_metadata"), J)) return false;
                }
                if (!Seen.Contains(P))
                { if (Reverse.Num() >= 32768) return InventoryFailure(TEXT("reverse_queue_budget"), Reverse[I], P, QueryEdges, Reverse.Num()); Seen.Add(P); Reverse.Add(P); }
            }
            Values.Sort(); Queries.Add(Reverse[I] + TEXT("|") + FString::FromInt(int32(EAssetRegistryDependencyType::Packages)), Values);
        }
        Ledger.InventoryIndex = -1; Ledger.InventoryAll = -1;
        TArray<FString> Seeds = Reverse;
        if (Log.MaterialsDiagnostic)
        { if (!MaterialDiagnosticSeeds(Seeds)) return InventoryFailure(TEXT("material_candidate_preflight"), WTUMaster(), FString(), QueryEdges, Seeds.Num()); }
        else
        {
        for (const FString& P : WURMaps()) Seeds.AddUnique(P);
        TArray<FName> Bases;
        for (const TCHAR* N : {TEXT("UTWeapon"), TEXT("UTWeaponAttachment"), TEXT("UTPickupInventory"), TEXT("UTDroppedPickup")}) Bases.Add(FName(N));
        TSet<FName> Excluded, Derived; Registry.GetDerivedClassNames(Bases, Excluded, Derived);
        if (Derived.Num() > 8192) return InventoryFailure(TEXT("derived_class_budget"), FString::FromInt(Derived.Num()), FString(), QueryEdges, Seeds.Num());
        for (const FAssetData& A : Assets)
        {
            FString Generated; A.GetTagValue(FName(TEXT("GeneratedClass")), Generated);
            const FString Path = FPackageName::ExportTextPathToObjectPath(Generated);
            if (!Path.IsEmpty() && Derived.Contains(FName(*FPackageName::ObjectPathToObjectName(Path)))) Seeds.AddUnique(A.PackageName.ToString());
        }
        }
        for (const auto& KV : Ledger.Packages) Seeds.AddUnique(KV.Key);
        if (Seeds.Num() > 32768) return InventoryFailure(TEXT("seed_budget"), FString(), FString(), QueryEdges, Seeds.Num());
        int32 SeedIndex = 0;
        Ledger.InventoryAll = -1;
        for (const FString& P : Seeds)
        {
            Ledger.InventoryIndex = SeedIndex++;
            Ledger.InventoryFrom = P;
            if (!Ledger.Package(P)) return InventoryFailure(TEXT("seed_package_admission"), P, P, QueryEdges, Seeds.Num());
            auto J = WURObject(); J->SetStringField(TEXT("package"), P);
            if (!Log.Emit(TEXT("scope_seed"), J)) return InventoryFailure(TEXT("seed_output_budget"), P, P, QueryEdges, Seeds.Num());
        }
        TArray<FString> Queue = Seeds; TSet<FString> Queued;
        for (const FString& P : Queue) Queued.Add(P);
        QueryEdges = 0;
        for (int32 I = 0; I < Queue.Num(); ++I)
        {
            Ledger.InventoryFrom = Queue[I]; Ledger.InventoryIndex = I; Ledger.InventoryDependencyIndex = -1;
            Ledger.InventoryAll = -1; Ledger.InventoryHard = -1;
            TArray<FName> All, Hard;
            const bool AllOK = Query(Queue[I], EAssetRegistryDependencyType::Packages, false, All);
            Ledger.InventoryAll = All.Num();
            if (!AllOK) return InventoryFailure(TEXT("dependency_query"), Queue[I], FString(), QueryEdges, Queue.Num());
            const bool HardOK = Query(Queue[I], EAssetRegistryDependencyType::Hard, false, Hard);
            Ledger.InventoryHard = Hard.Num();
            if (!HardOK) return InventoryFailure(TEXT("hard_dependency_query"), Queue[I], FString(), QueryEdges, Queue.Num());
            if (All.Num() > 32768 || All.Num() > 262144 - QueryEdges)
                return InventoryFailure(TEXT("dependency_edge_budget"), Queue[I], FString(), QueryEdges, Queue.Num());
            QueryEdges += All.Num(); TArray<FString> Signature;
            for (FName N : Hard) if (!All.Contains(N))
                return InventoryFailure(TEXT("hard_not_in_packages_query"), Queue[I], N.ToString(), QueryEdges, Queue.Num());
            for (FName N : All)
            {
                ++Ledger.InventoryDependencyIndex;
                const FString P = N.ToString(); const bool IsHard = Hard.Contains(N);
                Signature.Add(P + (IsHard ? TEXT("|hard") : TEXT("|soft")));
                if (P.StartsWith(TEXT("/Script/"))) continue;
                FString File; const bool Exists = FPackageName::DoesPackageExist(P, nullptr, &File);
                Ledger.InventoryIsHard = IsHard; Ledger.InventoryExists = Exists; Ledger.InventoryResolvedPath = File;
                if (!FPackageName::IsValidLongPackageName(P))
                    return InventoryFailure(TEXT("invalid_dependency_name"), Queue[I], P, QueryEdges, Queue.Num());
                if (!Exists && IsHard)
                    return InventoryFailure(TEXT("missing_hard_dependency"), Queue[I], P, QueryEdges, Queue.Num());
                auto J = WURObject(); J->SetStringField(TEXT("from"), Queue[I]); J->SetStringField(TEXT("package"), P);
                J->SetBoolField(TEXT("hard"), IsHard); J->SetBoolField(TEXT("exists"), Exists);
                if (!Log.Emit(TEXT("package_dependency"), J))
                    return InventoryFailure(TEXT("dependency_output_budget"), Queue[I], P, QueryEdges, Queue.Num());
                if (!Exists) { MissingSoftPackages.Add(P); continue; }
                if (!Queued.Contains(P))
                {
                    if (Queue.Num() >= 32768) return InventoryFailure(TEXT("dependency_queue_budget"), Queue[I], P, QueryEdges, Queue.Num());
                    if (!Ledger.Package(P)) return InventoryFailure(TEXT("dependency_package_admission"), Queue[I], P, QueryEdges, Queue.Num());
                    Queued.Add(P); Queue.Add(P);
                }
            }
            Signature.Sort(); DependencyQueries.Add(Queue[I], Signature);
        }
        return true;
    }
    bool Refs(const FString& P, EAssetRegistryDependencyType::Type Type, TArray<FString>& Out)
    {
        TArray<FName> Names;
        // A successful empty query is valid; failed queries remain unknown.
        if (!Ledger.Packages.Contains(P)) return false;
        if (!Query(P, Type, true, Names)) return false;
        if (Names.Num() > 32768) return false;
        for (FName N : Names) Out.Add(N.ToString());
        Out.Sort(); const FString Key = P + TEXT("|") + FString::FromInt(int32(Type));
        if (const TArray<FString>* Prior = Queries.Find(Key)) return Out == *Prior;
        Queries.Add(Key, Out); return true;
    }
    bool QueryUnchanged()
    {
        for (const FString& P : MissingSoftPackages)
        { FString File; if (FPackageName::DoesPackageExist(P, nullptr, &File)) return false; }
        for (const auto& KV : DependencyQueries)
        {
            TArray<FName> All, Hard;
            if (!Query(KV.Key, EAssetRegistryDependencyType::Packages, false, All) ||
                !Query(KV.Key, EAssetRegistryDependencyType::Hard, false, Hard)) return false;
            TArray<FString> Signature;
            for (FName N : Hard) if (!All.Contains(N)) return false;
            for (FName N : All) Signature.Add(N.ToString() + (Hard.Contains(N) ? TEXT("|hard") : TEXT("|soft")));
            Signature.Sort(); if (Signature != KV.Value) return false;
        }
        for (const auto& KV : Queries)
        {
            FString P, T; if (!KV.Key.Split(TEXT("|"), &P, &T)) return false;
            TArray<FName> Names; if (!Query(P, EAssetRegistryDependencyType::Type(FCString::Atoi(*T)), true, Names)) return false;
            TArray<FString> Values; for (FName N : Names) Values.Add(N.ToString()); Values.Sort();
            if (Values != KV.Value) return false;
        }
        return true;
    }
    bool Materials()
    {
        TArray<FString> Queue; Queue.Add(WTUMaster()); Closure.Add(WTUMaster());
        for (int32 I = 0; I < Queue.Num(); ++I)
        {
            TArray<FString> RefsHere; if (!Refs(Queue[I], EAssetRegistryDependencyType::Hard, RefsHere)) return false;
            for (const FString& P : RefsHere)
            {
                TArray<FAssetData> Rows; if (!Registry.GetAssetsByPackageName(FName(*P), Rows, true)) return false;
                for (const FAssetData& A : Rows)
                {
                    if (A.AssetClass != FName(TEXT("MaterialInstanceConstant"))) continue;
                    if (!Ledger.BeforeLoad(P, TEXT("material:") + A.ObjectPath.ToString())) return false;
                    auto* M = LoadObject<UMaterialInstanceConstant>(nullptr, *A.ObjectPath.ToString());
                    if (!Ledger.AfterLoad(P) || !M || !M->Parent) return false;
                    if (WURPath(M->Parent) != ObjectPath(Queue[I]) || Closure.Contains(P)) continue;
                    if (Closure.Num() >= 21 || A.ObjectPath.ToString() != ObjectPath(P)) return false;
                    Closure.Add(P); Queue.Add(P);
                    auto J = WURObject(); J->SetStringField(TEXT("package"), P); J->SetStringField(TEXT("material"), WURPath(M));
                    J->SetStringField(TEXT("parent"), WURPath(M->Parent));
                    if (!Log.Emit(TEXT("mic"), J)) return false;
                }
            }
        }
        if (Closure.Num() != 21) return false;
        for (const FString& P : WRScope()) if (P != WRMaster() && !Closure.Contains(P)) return false;
        if (Log.MaterialsDiagnostic) return true;
        // Transitive package referencers include material -> mesh -> Blueprint/map.
        for (const FString& P : Queue) Referencers.Add(P);
        for (int32 I = 0; I < Queue.Num(); ++I)
        {
            TArray<FString> All, Hard;
            if (!Refs(Queue[I], EAssetRegistryDependencyType::Packages, All) || !Refs(Queue[I], EAssetRegistryDependencyType::Hard, Hard)) return false;
            for (const FString& P : All)
            {
                if (++Edges > 262144) return false;
                auto J = WURObject(); J->SetStringField(TEXT("dependency"), Queue[I]); J->SetStringField(TEXT("referencer"), P);
                J->SetBoolField(TEXT("hard"), Hard.Contains(P)); if (!Log.Emit(TEXT("referencer"), J)) return false;
                if (Referencers.Contains(P)) continue;
                if (Referencers.Num() >= 32768 || !Ledger.Packages.Contains(P)) return false;
                Referencers.Add(P); Queue.Add(P);
            }
        }
        return true;
    }
    bool AddClass(UClass* C)
    {
        if (!C || C->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad) || C->HasAnyClassFlags(CLASS_NewerVersionExists)) return false;
        const FString P = WURPath(C);
        if (ClassPaths.Contains(P)) return true;
        if (Classes.Num() >= 8192) return false;
        ClassPaths.Add(P); Classes.Add(C); return true;
    }
    bool DiscoverClasses()
    {
        TArray<FName> Names; TArray<UClass*> Bases;
        for (const TCHAR* N : {TEXT("UTWeapon"), TEXT("UTWeaponAttachment"), TEXT("UTPickupInventory"), TEXT("UTDroppedPickup")})
        {
            UClass* C = FindObject<UClass>(nullptr, *(FString(TEXT("/Script/UnrealTournament.")) + N));
            if (!C || !AddClass(C)) return false;
            Bases.Add(C); Names.Add(C->GetFName());
        }
        TSet<FName> Derived, Excluded, Covered; Registry.GetDerivedClassNames(Names, Excluded, Derived);
        if (Derived.Num() > 8192) return false;
        for (TObjectIterator<UClass> It; It; ++It)
            if ((*It)->HasAnyClassFlags(CLASS_Native))
                for (UClass* Base : Bases) if ((*It)->IsChildOf(Base))
                {
                    if (!AddClass(*It)) return false;
                    Covered.Add((*It)->GetFName());
                }
        for (const FAssetData& A : Assets)
        {
            FString Generated;
            A.GetTagValue(FName(TEXT("GeneratedClass")), Generated);
            const FString Path = FPackageName::ExportTextPathToObjectPath(Generated);
            const bool Family = !Path.IsEmpty() && Derived.Contains(FName(*FPackageName::ObjectPathToObjectName(Path)));
            const bool Ref = Referencers.Contains(A.PackageName.ToString()) && (!Generated.IsEmpty() || A.AssetClass == FName(TEXT("Blueprint")));
            if (!Family && !Ref) continue;
            if (Path.IsEmpty()) return false;
            if (!Ledger.BeforeLoad(A.PackageName.ToString(), TEXT("class:") + Path)) return false;
            UClass* C = LoadObject<UClass>(nullptr, *Path);
            if (!Ledger.AfterLoad(A.PackageName.ToString()) || !C || !AddClass(C)) return false;
            bool NativeFamily = false;
            for (UClass* Base : Bases) NativeFamily = NativeFamily || C->IsChildOf(Base);
            if (Family != NativeFamily) return false;
            if (Family) Covered.Add(C->GetFName());
            BlueprintObjects.Add(A.ObjectPath.ToString());
            auto J = WURObject(); J->SetStringField(TEXT("blueprint"), A.ObjectPath.ToString()); J->SetStringField(TEXT("class"), Path);
            J->SetBoolField(TEXT("registry_family"), Family); J->SetBoolField(TEXT("transitive_referencer"), Ref);
            if (!Log.Emit(TEXT("blueprint"), J)) return false;
        }
        for (FName N : Derived)
        {
            if (!Covered.Contains(N)) return false;
            auto J = WURObject(); J->SetStringField(TEXT("name"), N.ToString());
            if (!Log.Emit(TEXT("derived_class"), J)) return false;
        }
        return true;
    }
    // Read reflected object/class properties, including protected pickup defaults.
    // No getter UFunction is dispatched and no Blueprint code is evaluated.
    UObject* Property(UObject* O, const TCHAR* Name)
    {
        auto* P = FindField<UObjectPropertyBase>(O->GetClass(), Name);
        return P ? P->GetObjectPropertyValue_InContainer(O) : nullptr;
    }
    bool Defaults(UObject* O, const FString& Context)
    {
        if (!O || O->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
        auto J = WURObject(); J->SetStringField(TEXT("object"), WURPath(O)); J->SetStringField(TEXT("context"), Context);
        J->SetStringField(TEXT("class"), WURPath(O->GetClass()));
        for (const TCHAR* Name : {TEXT("AttachmentType"), TEXT("InventoryType"), TEXT("WeaponType"), TEXT("DroppedPickupClass"), TEXT("Inventory"), TEXT("Mesh"), TEXT("Mesh1P"), TEXT("PickupMesh")})
        {
            UObject* Value = Property(O, Name); auto P = WURObject();
            P->SetBoolField(TEXT("declared"), FindField<UObjectPropertyBase>(O->GetClass(), Name) != nullptr);
            P->SetStringField(TEXT("value"), WURPath(Value)); J->SetObjectField(Name, P);
            if (UClass* C = Cast<UClass>(Value)) if (!AddClass(C)) return false;
        }
        UFunction* F = O->FindFunction(FName(TEXT("GetPickupMeshTemplate")));
        J->SetStringField(TEXT("pickup_function"), WURPath(F));
        J->SetBoolField(TEXT("pickup_script_override"), F && F->Script.Num() > 0);
        J->SetNumberField(TEXT("pickup_script_bytes"), F ? F->Script.Num() : 0);
        J->SetBoolField(TEXT("pickup_function_executed"), false);
        UObject* Attachment = Property(O, TEXT("AttachmentType"));
        UClass* AttachmentClass = Cast<UClass>(Attachment);
        UObject* AttachmentCDO = AttachmentClass ? AttachmentClass->GetDefaultObject(false) : nullptr;
        if (AttachmentClass && !AttachmentCDO) return false;
        J->SetStringField(TEXT("attachment_cdo"), WURPath(AttachmentCDO));
        J->SetStringField(TEXT("attachment_mesh_default"), AttachmentCDO ? WURPath(Property(AttachmentCDO, TEXT("Mesh"))) : FString());
        return Log.Emit(TEXT("defaults"), J);
    }
    bool Hit(UMaterialInterface* M) const
    {
        // Also retain in-memory material instances resolving to the clone master.
        return M && ((Closure.Contains(M->GetOutermost()->GetName()) && WURPath(M) == ObjectPath(M->GetOutermost()->GetName())) ||
            WURPath(M->GetMaterial()) == ObjectPath(WTUMaster()));
    }
    bool Slots(UMeshComponent* C, const FString& Context)
    {
        const int32 Count = C->GetNumMaterials();
        if (Count < 0 || Count > 256 || C->OverrideMaterials.Num() > 256) return false;
        UObject* Mesh = nullptr;
        if (auto* S = Cast<UStaticMeshComponent>(C)) Mesh = S->GetStaticMesh();
        else if (auto* S = Cast<USkinnedMeshComponent>(C)) Mesh = S->SkeletalMesh;
        else return false; // Unknown mesh subclasses cannot silently disappear.
        auto J = WURObject(); J->SetStringField(TEXT("component"), WURPath(C)); J->SetStringField(TEXT("component_class"), WURPath(C->GetClass()));
        J->SetStringField(TEXT("context"), Context); J->SetStringField(TEXT("mesh"), WURPath(Mesh));
        J->SetBoolField(TEXT("is_static_mesh"), C->IsA(UStaticMeshComponent::StaticClass()));
        J->SetNumberField(TEXT("mobility"), int32(C->Mobility)); J->SetNumberField(TEXT("resolved_slot_count"), Count);
        J->SetStringField(TEXT("attach_parent"), WURPath(C->GetAttachParent()));
        J->SetStringField(TEXT("attach_socket"), C->GetAttachSocketName().ToString());
        TArray<TSharedPtr<FJsonValue>> Slots;
        for (int32 I = 0; I < FMath::Max(Count, C->OverrideMaterials.Num()); ++I)
        {
            auto Row = WURObject(); UMaterialInterface* M = I < Count ? C->GetMaterial(I) : nullptr;
            Row->SetNumberField(TEXT("slot"), I); Row->SetStringField(TEXT("resolved"), WURPath(M)); Row->SetBoolField(TEXT("closure_hit"), Hit(M));
            Row->SetStringField(TEXT("resolved_base"), M ? WURPath(M->GetMaterial()) : FString());
            Row->SetStringField(TEXT("override"), C->OverrideMaterials.IsValidIndex(I) ? WURPath(C->OverrideMaterials[I]) : FString());
            Slots.Add(MRValue(Row));
        }
        J->SetArrayField(TEXT("slots"), Slots);
        if (!Log.Emit(TEXT("component"), J)) return false;
        return !Mesh || AssetSlots(Mesh);
    }
    TSet<FString> DescribedMeshes;
    bool AssetSlots(UObject* Mesh)
    {
        Context = WURPath(Mesh);
        if (!Mesh || Mesh->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
        if (DescribedMeshes.Contains(WURPath(Mesh))) return true;
        // Reflection keeps this observer independent of static-mesh slot API changes.
        const TCHAR* Field = Mesh->IsA(UStaticMesh::StaticClass()) ? TEXT("StaticMaterials") : TEXT("Materials");
        auto* Array = FindField<UArrayProperty>(Mesh->GetClass(), Field);
        if (!Array) return false;
        auto* Struct = Cast<UStructProperty>(Array->Inner);
        auto* Material = Struct ? FindField<UObjectPropertyBase>(Struct->Struct, TEXT("MaterialInterface")) : nullptr;
        if (!Material) return false;
        FScriptArrayHelper Values(Array, Array->ContainerPtrToValuePtr<void>(Mesh));
        if (Values.Num() > 256) return false;
        TArray<TSharedPtr<FJsonValue>> Slots;
        for (int32 I = 0; I < Values.Num(); ++I)
        {
            auto* M = Cast<UMaterialInterface>(Material->GetObjectPropertyValue_InContainer(Values.GetRawPtr(I)));
            auto Row = WURObject(); Row->SetNumberField(TEXT("slot"), I); Row->SetStringField(TEXT("material"), WURPath(M));
            Row->SetStringField(TEXT("base_material"), M ? WURPath(M->GetMaterial()) : FString());
            Row->SetBoolField(TEXT("closure_hit"), Hit(M)); Slots.Add(MRValue(Row));
        }
        auto J = WURObject(); J->SetStringField(TEXT("mesh"), WURPath(Mesh)); J->SetStringField(TEXT("class"), WURPath(Mesh->GetClass()));
        J->SetArrayField(TEXT("default_slots"), Slots); DescribedMeshes.Add(WURPath(Mesh)); return Log.Emit(TEXT("mesh"), J);
    }
    bool Component(UActorComponent* C, const FString& Context)
    {
        if (!C || C->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad) || ++Components > 524288) return false;
        auto* Mesh = Cast<UMeshComponent>(C);
        auto J = WURObject(); J->SetStringField(TEXT("component"), WURPath(C)); J->SetStringField(TEXT("context"), Context);
        J->SetStringField(TEXT("class"), WURPath(C->GetClass())); J->SetBoolField(TEXT("mesh"), Mesh != nullptr);
        if (!Log.Emit(TEXT("component_scan"), J)) return false;
        return !Mesh || Slots(Mesh, Context);
    }
    TArray<FString> Roots;
    TMap<FString, TArray<FString>> Children;
    TMap<FString, TSet<FString>> Reachable;
    bool Maps()
    {
        Roots = WURMaps();
        for (const FAssetData& A : Assets)
        {
            if (!Referencers.Contains(A.PackageName.ToString())) continue;
            if (A.AssetClass == FName(TEXT("World"))) Roots.AddUnique(A.PackageName.ToString());
            if (A.AssetClass == FName(TEXT("StaticMesh")) || A.AssetClass == FName(TEXT("SkeletalMesh")))
            {
                if (!Ledger.BeforeLoad(A.PackageName.ToString(), TEXT("mesh:") + A.ObjectPath.ToString())) return false;
                UObject* Mesh = LoadObject<UObject>(nullptr, *A.ObjectPath.ToString());
                if (!Ledger.AfterLoad(A.PackageName.ToString()) || !Mesh || !AssetSlots(Mesh)) return false;
            }
        }
        TArray<FString> Queue = Roots;
        for (int32 I = 0; I < Queue.Num(); ++I)
        {
            const FString P = Queue[I];
            Context = P;
            if (MapPaths.Contains(P)) continue;
            if (MapPaths.Num() >= 512 || !Ledger.Packages.Contains(P)) return false;
            if (!Ledger.BeforeLoad(P, TEXT("map:") + P)) return false;
            UPackage* Package = LoadPackage(nullptr, *P, LOAD_None);
            if (!Ledger.AfterLoad(P)) return false;
            UWorld* W = Package ? UWorld::FindWorldInPackage(Package) : nullptr;
            if (!W || W->GetOutermost()->GetName() != P || !W->PersistentLevel || W->WorldComposition || !Ledger.Loaded()) return false;
            MapPaths.Add(P); Worlds.Add(W);
            auto J = WURObject(); J->SetStringField(TEXT("package"), P); J->SetStringField(TEXT("world"), WURPath(W));
            J->SetStringField(TEXT("level"), WURPath(W->PersistentLevel)); J->SetBoolField(TEXT("lighting_scenario"), W->PersistentLevel->bIsLightingScenario);
            J->SetStringField(TEXT("map_build_registry"), WURPath(W->PersistentLevel->MapBuildData));
            J->SetBoolField(TEXT("world_initialized_by_report"), false);
            TArray<FString> Next;
            if (W->StreamingLevels.Num() > 512) return false;
            for (ULevelStreaming* S : W->StreamingLevels)
            {
                if (!S) return false;
                const FString Primary = S->GetWorldAssetPackageName();
                if (Primary.IsEmpty()) return false;
                Next.AddUnique(Primary);
                if (!S->PackageNameToLoad.IsNone()) Next.AddUnique(S->PackageNameToLoad.ToString());
                if (S->LODPackageNames.Num() > 64 || S->LODPackageNamesToLoad.Num() > 64) return false;
                for (FName N : S->LODPackageNames) { if (N.IsNone()) return false; Next.AddUnique(N.ToString()); }
                for (FName N : S->LODPackageNamesToLoad) { if (N.IsNone()) return false; Next.AddUnique(N.ToString()); }
                auto Row = WURObject(); Row->SetStringField(TEXT("map"), P); Row->SetStringField(TEXT("streaming_object"), WURPath(S));
                Row->SetStringField(TEXT("primary"), Primary); Row->SetStringField(TEXT("package_to_load"), S->PackageNameToLoad.ToString());
                if (!Log.Emit(TEXT("streaming"), Row)) return false;
            }
            Next.Sort(); Children.Add(P, Next); J->SetArrayField(TEXT("sublevels_and_lods"), WURStrings(Next));
            if (!Log.Emit(TEXT("map"), J)) return false;
            for (const FString& Child : Next)
            {
                Queue.AddUnique(Child); if (Queue.Num() > 512) return false;
            }
        }
        for (const FString& Root : Roots)
        {
            TSet<FString> Seen; TArray<FString> Work; Work.Add(Root); Seen.Add(Root);
            for (int32 I = 0; I < Work.Num(); ++I)
                for (const FString& Child : Children.FindChecked(Work[I]))
                    if (!Seen.Contains(Child)) { Seen.Add(Child); Work.Add(Child); }
            Reachable.Add(Root, Seen);
            auto J = WURObject(); J->SetStringField(TEXT("root"), Root); Work.Sort();
            J->SetArrayField(TEXT("maps"), WURStrings(Work)); if (!Log.Emit(TEXT("map_scope"), J)) return false;
        }
        return true;
    }
    bool Related(const ULevel* A, const ULevel* B) const
    {
        for (const auto& KV : Reachable)
            if (KV.Value.Contains(A->GetOutermost()->GetName()) && KV.Value.Contains(B->GetOutermost()->GetName())) return true;
        return false;
    }
    bool BuildData(UStaticMeshComponent* C, int32 LOD, const TCHAR* Source, const FString& Owner, const FMeshMapBuildData* Data)
    {
        auto J = WURObject(); J->SetStringField(TEXT("component"), WURPath(C)); J->SetNumberField(TEXT("lod"), LOD);
        J->SetStringField(TEXT("source"), Source); J->SetStringField(TEXT("source_owner"), Owner);
        J->SetStringField(TEXT("build_data_id"), C->LODData[LOD].MapBuildDataId.ToString());
        J->SetBoolField(TEXT("record_present"), Data != nullptr); J->SetBoolField(TEXT("lightmap_present"), Data && Data->LightMap);
        const FLightMap2D* LM = Data && Data->LightMap ? Data->LightMap->GetLightMap2D() : nullptr;
        J->SetBoolField(TEXT("lightmap_2d"), LM != nullptr);
        J->SetBoolField(TEXT("hq_valid"), LM && LM->IsValid(0)); J->SetBoolField(TEXT("lq_valid"), LM && LM->IsValid(1));
        J->SetStringField(TEXT("hq_texture"), LM ? WURPath(LM->GetTexture(0)) : FString());
        J->SetStringField(TEXT("lq_texture"), LM ? WURPath(LM->GetTexture(1)) : FString());
        J->SetNumberField(TEXT("built_instance_entries"), Data ? Data->PerInstanceLightmapData.Num() : 0);
        J->SetBoolField(TEXT("active_world_selection_claimed"), false);
        return Log.Emit(TEXT("lighting"), J);
    }
    bool Lighting(UStaticMeshComponent* C, ULevel* Level)
    {
        Context = WURPath(C);
        if (C->LODData.Num() > 64) return false;
        auto Summary = WURObject(); Summary->SetStringField(TEXT("component"), WURPath(C)); Summary->SetStringField(TEXT("level"), WURPath(Level));
        Summary->SetNumberField(TEXT("lods"), C->LODData.Num()); Summary->SetBoolField(TEXT("native_active_lookup_executed"), false);
        auto* InstanceArray = FindField<UArrayProperty>(C->GetClass(), TEXT("PerInstanceSMData"));
        Summary->SetNumberField(TEXT("serialized_instances"), InstanceArray ? FScriptArrayHelper(InstanceArray, InstanceArray->ContainerPtrToValuePtr<void>(C)).Num() : 0);
        if (!Log.Emit(TEXT("lighting_component"), Summary)) return false;
        // Older packages retain their actual lightmaps in this annotation after
        // deserialization. Do not migrate them or call HandleLegacyMapBuildData.
        const auto* Legacy = GComponentsWithLegacyLightmaps.GetAnnotationMap().Find(C);
        if (Legacy && Legacy->Data.Num() > 64) return false;
        TSet<FGuid> UsedLegacy;
        for (int32 I = 0; I < C->LODData.Num(); ++I)
        {
            const auto& LOD = C->LODData[I];
            if (!BuildData(C, I, TEXT("override"), WURPath(C), LOD.OverrideMapBuildData.Get()) ||
                !BuildData(C, I, TEXT("legacy_lod"), WURPath(C), LOD.LegacyMapBuildData)) return false;
            const FMeshMapBuildData* LegacyData = nullptr;
            if (Legacy)
                for (const auto& Pair : Legacy->Data)
                    if (Pair.Key == LOD.MapBuildDataId)
                    {
                        if (LegacyData || !Pair.Value) return false;
                        LegacyData = Pair.Value; UsedLegacy.Add(Pair.Key);
                    }
            if (!BuildData(C, I, TEXT("legacy_annotation"), WURPath(C), LegacyData)) return false;
            const UMapBuildDataRegistry* Own = Level->MapBuildData;
            if (Own && Own->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
            if (!BuildData(C, I, TEXT("own_level_registry"), WURPath(Own), Own ? Own->GetMeshBuildData(LOD.MapBuildDataId) : nullptr)) return false;
            for (UWorld* W : Worlds)
            {
                ULevel* Scenario = W->PersistentLevel;
                if (Scenario == Level || !Scenario->bIsLightingScenario || !Related(Level, Scenario)) continue;
                const UMapBuildDataRegistry* R = Scenario->MapBuildData;
                if (R && R->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
                if (!BuildData(C, I, TEXT("scenario_registry_candidate"), WURPath(Scenario), R ? R->GetMeshBuildData(LOD.MapBuildDataId) : nullptr)) return false;
            }
        }
        return !Legacy || UsedLegacy.Num() == Legacy->Data.Num();
    }
    bool PlacedActors()
    {
        for (UWorld* W : Worlds)
        {
            ULevel* Level = W->PersistentLevel;
            if (Level->Actors.Num() > 262144 - Actors) return false;
            for (AActor* A : Level->Actors)
            {
                if (!A) continue;
                Context = WURPath(A); Ledger.Phase = TEXT("placed_actor:") + Context;
                ++Actors;
                bool PickupFamily = false;
                for (UClass* C = A->GetClass(); C; C = C->GetSuperClass())
                    if (WURPath(C) == TEXT("/Script/UnrealTournament.UTPickupInventory") || WURPath(C) == TEXT("/Script/UnrealTournament.UTDroppedPickup")) PickupFamily = true;
                if (PickupFamily && (!AddClass(A->GetClass()) || !Defaults(A, TEXT("placed_pickup")))) return false;
                TArray<UActorComponent*> Native; A->GetComponents(Native);
                if (Native.Num() > 4096) return false;
                auto J = WURObject(); J->SetStringField(TEXT("actor"), WURPath(A)); J->SetStringField(TEXT("class"), WURPath(A->GetClass()));
                J->SetStringField(TEXT("level"), WURPath(Level)); J->SetNumberField(TEXT("components"), Native.Num()); J->SetBoolField(TEXT("pickup_family"), PickupFamily);
                if (!Log.Emit(TEXT("actor"), J)) return false;
                for (UActorComponent* C : Native)
                {
                    if (!Component(C, WURPath(A))) return false;
                    if (auto* Static = Cast<UStaticMeshComponent>(C)) if (!Lighting(Static, Level)) return false;
                }
            }
        }
        return Ledger.Loaded();
    }
    bool Templates()
    {
        for (int32 I = 0; I < Classes.Num(); ++I)
        {
            UClass* C = Classes[I]; UObject* CDO = C->GetDefaultObject(false);
            Context = WURPath(C); Ledger.Phase = TEXT("templates:") + Context;
            if (!CDO || !Defaults(CDO, TEXT("cdo"))) return false;
            auto J = WURObject(); J->SetStringField(TEXT("class"), WURPath(C)); J->SetStringField(TEXT("cdo"), WURPath(CDO));
            J->SetStringField(TEXT("super"), WURPath(C->GetSuperClass()));
            if (!Log.Emit(TEXT("class"), J)) return false;
            if (AActor* Actor = Cast<AActor>(CDO))
            {
                TArray<UActorComponent*> Native; Actor->GetComponents(Native);
                if (Native.Num() > 4096) return false;
                for (UActorComponent* N : Native) if (!Component(N, WURPath(C) + TEXT(":cdo"))) return false;
            }
            auto* Actual = Cast<UBlueprintGeneratedClass>(C);
            if (!Actual) continue;
            TArray<const UBlueprintGeneratedClass*> Hierarchy;
            if (!UBlueprintGeneratedClass::GetGeneratedClassesHierarchy(C, Hierarchy) || Hierarchy.Num() > 64) return false;
            for (const UBlueprintGeneratedClass* B : Hierarchy)
            {
                if (B->ComponentTemplates.Num() > 4096) return false;
                for (UActorComponent* T : B->ComponentTemplates)
                {
                    auto Row = WURObject(); Row->SetStringField(TEXT("class"), WURPath(C)); Row->SetStringField(TEXT("owner_class"), WURPath(B));
                    Row->SetStringField(TEXT("template"), WURPath(T));
                    if (!Log.Emit(TEXT("add_component_template"), Row) || !Component(T, WURPath(C) + TEXT(":add_component:") + WURPath(B))) return false;
                }
                if (B->SimpleConstructionScript)
                {
                    const auto& Nodes = B->SimpleConstructionScript->GetAllNodes(); if (Nodes.Num() > 4096) return false;
                    for (USCS_Node* N : Nodes)
                    {
                        if (!N) return false;
                        UActorComponent* T = N->GetActualComponentTemplate(Actual);
                        auto Row = WURObject(); Row->SetStringField(TEXT("class"), WURPath(C)); Row->SetStringField(TEXT("owner_class"), WURPath(B));
                        Row->SetStringField(TEXT("node"), WURPath(N)); Row->SetStringField(TEXT("variable"), N->GetVariableName().ToString());
                        Row->SetStringField(TEXT("declared_template"), WURPath(N->ComponentTemplate)); Row->SetStringField(TEXT("actual_template"), WURPath(T));
                        if (!T || !Log.Emit(TEXT("scs"), Row) || !Component(T, WURPath(C) + TEXT(":scs:") + WURPath(N))) return false;
                    }
                }
                // Read the stored handler even when the engine feature flag is off.
                // Do not call any creating getter, validation or refresh method.
                UInheritableComponentHandler* H = B->InheritableComponentHandler;
                if (!H) continue;
                if (H->HasAnyFlags(RF_NeedLoad | RF_NeedPostLoad)) return false;
                int32 Records = 0;
                for (auto It = H->CreateRecordIterator(); It; ++It)
                {
                    const FComponentOverrideRecord& R = *It;
                    if (++Records > 4096 || !R.ComponentKey.IsValid() || !R.ComponentTemplate || !R.ComponentClass || !R.ComponentTemplate->IsA(R.ComponentClass)) return false;
                    auto Row = WURObject(); Row->SetStringField(TEXT("class"), WURPath(C)); Row->SetStringField(TEXT("handler"), WURPath(H));
                    Row->SetStringField(TEXT("key_owner"), WURPath(R.ComponentKey.GetComponentOwner()));
                    Row->SetStringField(TEXT("key_variable"), R.ComponentKey.GetSCSVariableName().ToString());
                    Row->SetStringField(TEXT("key_guid"), R.ComponentKey.GetAssociatedGuid().ToString());
                    Row->SetBoolField(TEXT("scs_key"), R.ComponentKey.IsSCSKey()); Row->SetBoolField(TEXT("ucs_key"), R.ComponentKey.IsUCSKey());
                    Row->SetStringField(TEXT("template"), WURPath(R.ComponentTemplate));
                    if (!Log.Emit(TEXT("inherited"), Row) || !Component(R.ComponentTemplate, WURPath(C) + TEXT(":inherited:") + WURPath(H))) return false;
                }
            }
            if (!Ledger.Loaded()) return false;
        }
        return true;
    }
};

static bool WURInputs(FWURReport& R, const FString& Path, const FString& Hash)
{
    if (!WTUSHA1(Hash) || !R.Ledger.Add(Path, false, Hash) || R.Ledger.Files.FindChecked(Full(Path).ToLower()).Size > 1024 * 1024) return false;
    TSharedPtr<FJsonObject> J;
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr; const TArray<TSharedPtr<FJsonValue>>* Roots = nullptr;
    if (!ReadJson(Path, J) || Str(J, TEXT("schema")) != TEXT("ut4-weapon-usage-inputs-v2") ||
        !J->TryGetArrayField(TEXT("read_only_roots"), Roots) || Roots->Num() < 1 || Roots->Num() > 1024 ||
        !J->TryGetArrayField(TEXT("files"), Rows) || Rows->Num() < 3 || Rows->Num() > 8192) return false;
    TSet<FString> LogicalRoots;
    for (const auto& V : *Roots)
    {
        if (V->Type != EJson::Object) return false;
        auto Row = V->AsObject(); FWURRoot Root;
        Root.Logical = Str(Row, TEXT("logical_root")); Root.Target = Str(Row, TEXT("physical_root")); Root.Role = Str(Row, TEXT("role"));
        // Require explicit canonical absolute paths, never resolve relative input.
        if (!WURLocalPath(Root.Logical) || !WURLocalPath(Root.Target) || Root.Logical != Full(Root.Logical) || Root.Target != Full(Root.Target) ||
            (Root.Role != TEXT("source") && Root.Role != TEXT("selected")) || LogicalRoots.Contains(Root.Logical.ToLower())) return false;
#if PLATFORM_WINDOWS
        HANDLE H; FString Target;
        if (!WURMappedOpen(Root.Logical, Root, true, H, Target)) return false;
        CloseHandle(H);
#else
        return false;
#endif
        LogicalRoots.Add(Root.Logical.ToLower()); R.Ledger.ReadRoots.Add(Root);
        auto Record = WURObject(); Record->SetStringField(TEXT("logical_root"), Root.Logical);
        Record->SetStringField(TEXT("physical_root"), Root.Target); Record->SetStringField(TEXT("role"), Root.Role);
        if (!R.Log.Emit(TEXT("read_root"), Record)) return false;
    }
    TSet<FString> Roles, Paths;
    for (const auto& V : *Rows)
    {
        if (V->Type != EJson::Object) return false;
        auto File = V->AsObject(); const FString P = Str(File, TEXT("path")), H = Str(File, TEXT("sha1")), Role = Str(File, TEXT("role"));
        const bool Config = Role == TEXT("html5-config");
        if (P.IsEmpty() || Role.IsEmpty() || Role.Len() > 128 || Paths.Contains(Full(P).ToLower()) || !WTUSHA1(H) || !R.Ledger.Add(P, false, H, Config)) return false;
        if (R.Log.MaterialsDiagnostic && (Role == TEXT("usage-history-report2-log") || Role == TEXT("usage-history-report2-result")))
        { if (R.HistoricalInputs.Contains(Role)) return false; R.HistoricalInputs.Add(Role, Full(P)); }
        Paths.Add(Full(P).ToLower()); Roles.Add(Role);
        auto Row = WURObject(); Row->SetStringField(TEXT("path"), Full(P)); Row->SetStringField(TEXT("sha1"), H.ToLower()); Row->SetStringField(TEXT("role"), Role);
        if (!R.Log.Emit(TEXT("input"), Row)) return false;
    }
    return Roles.Contains(TEXT("cook-scope")) && Roles.Contains(TEXT("html5-config")) && Roles.Contains(TEXT("engine-api-manifest"));
}
// UE4.15 trimming methods are non-const. Work on a copy of each input.
static FString WURTrim(FString Value) { return Value.Trim().TrimTrailing(); }
static bool WURConfigRows(FWURReport& R)
{
    TSet<FString> Seen;
    for (const auto& Dir : R.Ledger.ConfigDirectories)
        for (const FString& P : Dir.Value)
        {
            if (Seen.Contains(P)) continue;
            Seen.Add(P); FString Text;
            const FWURFile& Saved = R.Ledger.Files.FindChecked(P.ToLower()); FWURFile Before, After;
            if (!FWURFile::Inspect(P, false, Before, Saved.Mapped ? &Saved.Root : nullptr) || Before.Target != Saved.Target ||
                Before.Identity != Saved.Identity || Before.SHA1 != Saved.SHA1 || !FFileHelper::LoadFileToString(Text, *Before.Target) ||
                !FWURFile::Inspect(P, false, After, Saved.Mapped ? &Saved.Root : nullptr) || After.Target != Before.Target ||
                After.Identity != Before.Identity || After.SHA1 != Before.SHA1) return false;
            TArray<FString> Lines; Text.ParseIntoArrayLines(Lines, false); FString Section;
            for (int32 I = 0; I < Lines.Num(); ++I)
            {
                FString Line = WURTrim(Lines[I]);
                if (Line.StartsWith(TEXT("[")) && Line.EndsWith(TEXT("]"))) Section = Line.Mid(1, Line.Len() - 2);
                FString Key, Value;
                if (!Line.Split(TEXT("="), &Key, &Value)) continue;
                Key = WURTrim(Key);
                if (Key != TEXT("r.AllowStaticLighting") && Key != TEXT("r.SupportLowQualityLightmaps") &&
                    Key != TEXT("r.Mobile.EnableStaticAndCSMShadowReceivers") && Key != TEXT("bEnableInheritableComponents")) continue;
                if (Line.Len() > 4096 || Section.Len() > 4096) return false;
                auto J = WURObject(); J->SetStringField(TEXT("file"), P); J->SetNumberField(TEXT("line"), I + 1);
                J->SetStringField(TEXT("section"), Section); J->SetStringField(TEXT("key"), Key); J->SetStringField(TEXT("raw_value"), WURTrim(Value));
                J->SetBoolField(TEXT("effective_html5_value_claimed"), false);
                if (!R.Log.Emit(TEXT("config_assignment"), J)) return false;
            }
        }
    return true;
}
// Recognize only a distinct command-line token, excluding quoted path contents.
static bool WURDiagnosticCohort(const FString& Params, bool& Diagnostic)
{
    const FString Key = TEXT("UsageDiagnosticCohort"); int32 Count = 0; bool Quoted = false;
    Diagnostic = false;
    for (int32 I = 0; I < Params.Len(); ++I)
    {
        if (Params[I] == '"') { Quoted = !Quoted; continue; }
        if (Quoted || (I && Params[I - 1] != ' ' && Params[I - 1] != '\t' && Params[I - 1] != '\r' && Params[I - 1] != '\n')) continue;
        const int32 Start = Params[I] == '-' ? I + 1 : I, End = Start + Key.Len();
        if (!Params.Mid(Start, Key.Len()).Equals(Key, ESearchCase::IgnoreCase)) continue;
        if (End < Params.Len() && Params[End] != '=' && Params[End] != ' ' && Params[End] != '\t' && Params[End] != '\r' && Params[End] != '\n') continue;
        FString Value;
        if (++Count != 1 || End >= Params.Len() || Params[End] != '=' ||
            !FParse::Value(*Params.Mid(Start), TEXT("UsageDiagnosticCohort="), Value) || Value != TEXT("materials")) return false;
        Diagnostic = true;
    }
    return true;
}
static int32 WeaponUsageReport(const FString& Params)
{
    FString Mode, Spec, Inputs, InputsHash, ProofPath;
    FParse::Value(*Params, TEXT("Mode="), Mode);
    // This also protects direct invocation if the owning dispatcher is changed.
    if (!GIsEditor || !IsInGameThread() || !Mode.Equals(TEXT("WeaponUsageReport"), ESearchCase::IgnoreCase) ||
        FParse::Param(*Params, TEXT("WeaponTessUpgrade")) || FParse::Param(*Params, TEXT("WeaponTessVerify")) ||
        FParse::Param(*Params, TEXT("WeaponShaderProbe")) || FParse::Param(*Params, TEXT("WeaponShaderNoStaticLighting")) ||
        FParse::Param(*Params, TEXT("WeaponShaderEnforcer1PHigh")) || FParse::Param(FCommandLine::Get(), TEXT("NoDependsGathering")) ||
        !FParse::Value(*Params, TEXT("UsageReportSpec="), Spec) || !FParse::Value(*Params, TEXT("UsageInputs="), Inputs) ||
        !FParse::Value(*Params, TEXT("UsageInputsSHA1="), InputsHash) || !FParse::Value(*Params, TEXT("WeaponCurrentProof="), ProofPath))
        return WFRStop(TEXT("usage-admission"));
    bool Diagnostic = false;
    if (!WURDiagnosticCohort(Params, Diagnostic)) return WFRStop(TEXT("usage-diagnostic-cohort"));
    FWeaponTessProof Proof;
    if (!Proof.Read(ProofPath)) return WFRStop(TEXT("usage-proof"));
    IAssetRegistry& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry")).Get();
    FWURReport R(Registry); R.Log.Run = InputsHash.ToLower(); R.Log.MaterialsDiagnostic = Diagnostic;
    if (!R.Ledger.Add(Spec, false, WURSpecSHA1) || !R.Ledger.Add(ProofPath, false, WTUProofSHA1)) return WFRStop(TEXT("usage-spec-pins"));
    auto Begin = WURObject(); Begin->SetStringField(TEXT("spec_sha1"), WURSpecSHA1); Begin->SetStringField(TEXT("proof_sha1"), WTUProofSHA1);
    Begin->SetStringField(TEXT("master"), WTUMaster()); Begin->SetArrayField(TEXT("cook_maps"), WURStrings(WURMaps()));
    Begin->SetStringField(TEXT("project"), Full(FPaths::GameDir())); Begin->SetStringField(TEXT("content"), Full(FPaths::GameContentDir()));
    Begin->SetStringField(TEXT("engine"), Full(FPaths::EngineDir()));
    Begin->SetStringField(TEXT("loaded_engine_config"), Full(GEngineIni));
    Begin->SetStringField(TEXT("lighting_scope"), TEXT("serialized own-level, scenario-candidate, override and legacy records; no active-world selection"));
    Begin->SetBoolField(TEXT("effective_html5_cvars_verified"), false);
    if (Diagnostic) Begin->SetStringField(TEXT("lighting_scope"), TEXT("not inspected by materials diagnostic"));
    if (!R.Log.Emit(TEXT("begin"), Begin) || !WURInputs(R, Inputs, InputsHash)) return WFRStop(TEXT("usage-inputs"));
    for (TObjectIterator<UPackage> It; It; ++It)
    {
        if ((*It)->IsDirty()) R.Ledger.InitiallyDirty.Add(*It);
        auto J = WURObject(); J->SetStringField(TEXT("package"), (*It)->GetName()); J->SetBoolField(TEXT("dirty"), (*It)->IsDirty());
        if (!R.Log.Emit(TEXT("initial_package"), J)) return WFRStop(TEXT("usage-initial-package-budget"));
        FString File;
        if (FPackageName::DoesPackageExist((*It)->GetName(), nullptr, &File))
        { if (!R.Ledger.Package((*It)->GetName())) return WFRStop(TEXT("usage-preloaded-pins")); }
        else R.Ledger.InitiallyMemoryOnly.Add(*It);
    }
    for (const TCHAR* Key : {TEXT("WeaponRepairSpec="), TEXT("WeaponBaseline="), TEXT("Receipt="), TEXT("WeaponTessReceipt="), TEXT("WeaponMasterBackup="), TEXT("WeaponTessAftermath=")})
    {
        FString P; if (!FParse::Value(*Params, Key, P) || !R.Ledger.Add(P)) return WFRStop(TEXT("usage-verify-input"), Key);
    }
    for (const auto& KV : Proof.CurrentFiles) if (!R.Ledger.Add(KV.Value)) return WFRStop(TEXT("usage-current-input"), KV.Key);
    for (const TCHAR* Key : {TEXT("original_dependencies"), TEXT("artifacts")})
        for (const auto& V : Proof.Json->GetArrayField(Key))
            if (!R.Ledger.Add(Str(V->AsObject(), TEXT("path")), false, Str(V->AsObject(), TEXT("sha1")))) return WFRStop(TEXT("usage-proof-input"), Key);
    for (const TCHAR* Key : {TEXT("recipe"), TEXT("baseline")})
        if (!R.Ledger.Add(Str(Proof.Json->GetObjectField(Key), TEXT("path")), false, Str(Proof.Json->GetObjectField(Key), TEXT("sha1")))) return WFRStop(TEXT("usage-proof-input"), Key);
    for (const FString& Dir : {FPaths::EngineConfigDir(), FPaths::GameConfigDir(), FPaths::GameSavedDir() / TEXT("Config")})
        if (!R.Ledger.ConfigDirectory(Dir, true)) return WFRStop(TEXT("usage-config-inputs"), Dir);
    if (!R.Ledger.Add(GEngineIni, false, FString(), true)) return WFRStop(TEXT("usage-engine-config"));
    Registry.SearchAllAssets(true);
    if (!R.RegistryRows(true)) return WFRStop(TEXT("usage-registry-snapshot"));
    // Preserve complete relevant closure without fingerprinting unrelated assets.
    // Missing soft references are reported and rechecked, never silently adopted;
    // a required map/class/load outside the pinned inventory still fails closed.
    if (Diagnostic && !R.PrepareMaterialsDiagnostic(Spec)) return WFRStop(TEXT("usage-diagnostic-inputs"));
    if (!R.Inventory()) return WFRStop(TEXT("usage-relevant-inventory"), R.Context);
    for (const auto& KV : R.Ledger.Packages)
    {
        auto J = WURObject(); J->SetStringField(TEXT("package"), KV.Key); J->SetStringField(TEXT("file"), KV.Value);
        if (!R.Log.Emit(TEXT("package_file"), J)) return WFRStop(TEXT("usage-output-budget"));
    }
    auto Provenance = WURObject(); Provenance->SetBoolField(TEXT("search_all_assets_synchronous"), true);
    Provenance->SetBoolField(TEXT("is_loading_assets"), Registry.IsLoadingAssets()); Provenance->SetBoolField(TEXT("on_disk_assets_only"), true);
    Provenance->SetNumberField(TEXT("assets"), R.Assets.Num()); Provenance->SetNumberField(TEXT("packages"), R.Ledger.Packages.Num());
    Provenance->SetStringField(TEXT("fingerprint_scope"), TEXT("relevant-reference-class-map-dependencies-and-preloaded"));
    if (Diagnostic) Provenance->SetStringField(TEXT("fingerprint_scope"), TEXT("materials-prerequisites-preloaded-forward-closure"));
    Provenance->SetStringField(TEXT("referencer_types"), TEXT("Hard for MIC parent closure; Packages plus Hard classification for transitive referencers"));
    if (!R.Log.Emit(TEXT("registry"), Provenance) || !WURConfigRows(R)) return WFRStop(TEXT("usage-provenance"));
    R.Ledger.Phase = TEXT("fresh_tess_verify");
    if (!R.Ledger.Check()) return WFRStop(TEXT("usage-before-fingerprints"));
    const int32 VerifyResult = WeaponTessellationUpgrade(Params, true);
    if (!R.Ledger.Loaded() || VerifyResult != 0) return WFRStop(TEXT("usage-fresh-tess-verify"));
    const FString MasterHash = HashFile(Proof.CurrentFiles.FindChecked(WTUMaster()));
    if (!Proof.Check(MasterHash) || !R.Materials()) return WFRStop(TEXT("usage-closure"), R.Context);
    if (!Diagnostic)
    {
    if (!R.DiscoverClasses()) return WFRStop(TEXT("usage-class-discovery"), R.Context);
    if (!R.Maps() || !R.PlacedActors()) return WFRStop(TEXT("usage-map-inspection"), R.Context);
    if (!R.Templates()) return WFRStop(TEXT("usage-template-inspection"), R.Context);
    }
    if (!Proof.Check(MasterHash) || !R.RegistryRows(false) || !R.QueryUnchanged()) return WFRStop(TEXT("usage-generation-registry-drift"));
    for (const auto& KV : R.Ledger.ConfigDirectories) if (!R.Ledger.ConfigDirectory(KV.Key, false)) return WFRStop(TEXT("usage-config-inventory-drift"));
    R.Ledger.Phase = TEXT("final_fingerprints");
    if (!R.Ledger.Check(&R.Log)) return WFRStop(TEXT("usage-after-fingerprints"));
    auto Done = WURObject(), Counts = WURObject();
    for (const auto& KV : R.Log.Counts) Counts->SetNumberField(KV.Key, KV.Value);
    Done->SetObjectField(Diagnostic ? TEXT("row_counts_before_end") : TEXT("row_counts_before_complete"), Counts);
    Done->SetNumberField(Diagnostic ? TEXT("rows_before_end") : TEXT("rows_before_complete"), R.Log.Rows);
    Done->SetNumberField(TEXT("mic_count"), R.Closure.Num() - 1); Done->SetNumberField(TEXT("classes"), R.Classes.Num());
    Done->SetNumberField(TEXT("maps"), R.Worlds.Num()); Done->SetNumberField(TEXT("actors"), R.Actors); Done->SetNumberField(TEXT("components"), R.Components);
    Done->SetNumberField(TEXT("files"), R.Ledger.Files.Num()); Done->SetNumberField(TEXT("input_bytes"), double(R.Ledger.Bytes));
    Done->SetStringField(TEXT("master_sha1"), MasterHash.ToLower()); Done->SetBoolField(TEXT("all_fingerprints_unchanged"), true);
    Done->SetBoolField(TEXT("new_dirty_packages"), false); Done->SetNumberField(TEXT("initially_dirty_packages"), R.Ledger.InitiallyDirty.Num());
    Done->SetBoolField(TEXT("runtime_blueprint_behavior_verified"), false); Done->SetBoolField(TEXT("effective_html5_cvars_verified"), false);
    Done->SetNumberField(TEXT("assets_saved"), 0);
    if (Diagnostic)
    {
        Done->SetStringField(TEXT("cohort_status"), TEXT("observed")); Done->SetBoolField(TEXT("fresh_verify_passed"), true);
        return R.Log.Emit(TEXT("diagnostic_end"), Done) ? 2 : WFRStop(TEXT("usage-diagnostic-output"));
    }
    return R.Log.Emit(TEXT("complete"), Done) ? 0 : WFRStop(TEXT("usage-completion-output"));
}
