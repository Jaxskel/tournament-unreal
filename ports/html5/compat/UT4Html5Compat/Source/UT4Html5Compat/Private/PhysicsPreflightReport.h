// Original bounded native editor query report. No asset saves or collision setters.
// Included inside UT4Compat; deliberately separate from Apply/Verify.
static bool PPFiniteBound(double Value, double Min, double Max)
{
    return FMath::IsFinite(Value) && Value >= Min && Value <= Max;
}
static bool PPQueryDimensions(int Count, double Above, double Below, double Radius, double HalfHeight)
{
    return Count >= 1 && Count <= 5 && PPFiniteBound(Above, 0, 1024) &&
        PPFiniteBound(Below, 1, 8192) && PPFiniteBound(Radius, 1, 200) &&
        PPFiniteBound(HalfHeight, Radius, 300);
}
static bool PPValidOffset(double Value, double Previous, bool First)
{
    return PPFiniteBound(Value, 0, 1024) && (First ? Value == 0 : Value > Previous);
}
static TArray<TSharedPtr<FJsonValue>> PPVector(const FVector& V)
{
    TArray<TSharedPtr<FJsonValue>> A;
    A.Add(MakeShareable(new FJsonValueNumber(V.X)));
    A.Add(MakeShareable(new FJsonValueNumber(V.Y)));
    A.Add(MakeShareable(new FJsonValueNumber(V.Z)));
    return A;
}
static TSharedPtr<FJsonObject> PPComponent(UPrimitiveComponent* C)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetStringField(TEXT("component"), C->GetPathName());
    J->SetStringField(TEXT("class"), C->GetClass()->GetPathName());
    J->SetStringField(TEXT("owner"), C->GetOwner() ? C->GetOwner()->GetPathName() : TEXT(""));
    J->SetArrayField(TEXT("location"), PPVector(C->GetComponentLocation()));
    J->SetArrayField(TEXT("scale"), PPVector(C->GetComponentScale()));
    J->SetStringField(TEXT("rotation"), C->GetComponentRotation().ToString());
    J->SetArrayField(TEXT("bounds_origin"), PPVector(C->Bounds.Origin));
    J->SetArrayField(TEXT("bounds_extent"), PPVector(C->Bounds.BoxExtent));
    J->SetBoolField(TEXT("registered"), C->IsRegistered());
    J->SetBoolField(TEXT("physics_state_created"), C->IsPhysicsStateCreated());
    J->SetNumberField(TEXT("collision_enabled"), C->GetCollisionEnabled());
    J->SetStringField(TEXT("collision_profile"), C->GetCollisionProfileName().ToString());
    J->SetNumberField(TEXT("pawn_response"), C->GetCollisionResponseToChannel(ECC_Pawn));
    J->SetNumberField(TEXT("visibility_response"), C->GetCollisionResponseToChannel(ECC_Visibility));
    J->SetBoolField(TEXT("owner_present"), C->GetOwner() != nullptr);
    if (C->GetOwner()) J->SetBoolField(TEXT("actor_collision_enabled"), C->GetOwner()->GetActorEnableCollision());
    else J->SetField(TEXT("actor_collision_enabled"), MakeShareable(new FJsonValueNull));
    FBodyInstance* BI = C->GetBodyInstance();
    J->SetBoolField(TEXT("body_instance_valid"), BI && BI->IsValidBodyInstance());
    UStaticMeshComponent* S = Cast<UStaticMeshComponent>(C);
    UStaticMesh* Mesh = S ? S->GetStaticMesh() : nullptr;
    J->SetStringField(TEXT("static_mesh"), Mesh ? Mesh->GetPathName() : TEXT(""));
    UBodySetup* B = C->GetBodySetup();
    J->SetStringField(TEXT("body_setup"), B ? B->GetPathName() : TEXT(""));
    if (B)
    {
        J->SetNumberField(TEXT("collision_trace_flag_raw"), B->CollisionTraceFlag);
        J->SetNumberField(TEXT("collision_trace_flag_effective"), B->GetCollisionTraceFlag());
        J->SetNumberField(TEXT("convex_count"), B->AggGeom.ConvexElems.Num());
        J->SetNumberField(TEXT("box_count"), B->AggGeom.BoxElems.Num());
        J->SetNumberField(TEXT("sphere_count"), B->AggGeom.SphereElems.Num());
        J->SetNumberField(TEXT("capsule_count"), B->AggGeom.SphylElems.Num());
        J->SetBoolField(TEXT("created_physics_meshes"), B->bCreatedPhysicsMeshes);
        J->SetBoolField(TEXT("has_cooked_collision_data"), B->bHasCookedCollisionData);
#if WITH_PHYSX
        J->SetNumberField(TEXT("native_triangle_mesh_count"), B->TriMeshes.Num());
#endif
        J->SetBoolField(TEXT("body_setup_package_dirty"), B->GetOutermost()->IsDirty());
    }
    return J;
}
static TSharedPtr<FJsonObject> PPHit(const FHitResult& Hit)
{
    TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
    J->SetBoolField(TEXT("blocking"), Hit.bBlockingHit);
    J->SetBoolField(TEXT("start_penetrating"), Hit.bStartPenetrating);
    J->SetNumberField(TEXT("time"), Hit.Time);
    J->SetNumberField(TEXT("penetration_depth"), Hit.PenetrationDepth);
    J->SetArrayField(TEXT("impact_point"), PPVector(Hit.ImpactPoint));
    J->SetArrayField(TEXT("impact_normal"), PPVector(Hit.ImpactNormal));
    J->SetNumberField(TEXT("face_index"), Hit.FaceIndex);
    J->SetNumberField(TEXT("item"), Hit.Item);
    if (Hit.Component.IsValid()) J->SetObjectField(TEXT("component"), PPComponent(Hit.Component.Get()));
    return J;
}
static int32 PhysicsPreflightReport(const FString& Params)
{
    FString SpecPath, Forbidden;
    if (!FParse::Value(*Params, TEXT("PhysicsSpec="), SpecPath) ||
        FParse::Value(*Params, TEXT("Manifest="), Forbidden) || FParse::Value(*Params, TEXT("Receipt="), Forbidden))
    { Fail(TEXT("PhysicsReport requires only -PhysicsSpec=<bounded json>.")); return 1; }
    TSharedPtr<FJsonObject> Spec;
    if (!ReadJson(SpecPath, Spec) || Str(Spec, TEXT("schema")) != TEXT("ut4-physics-query-v1")) return 1;
    const FString Map = Str(Spec, TEXT("map"));
    if (Map != TEXT("/Game/RestrictedAssets/Maps/WIP/DM-DeckTest"))
    { Fail(TEXT("PhysicsReport is limited to the isolated Deck map.")); return 1; }
    const TArray<TSharedPtr<FJsonValue>>* Input = nullptr;
    double Above = 0, Below = 0, Radius = 0, HalfHeight = 0;
    if (!Spec->TryGetArrayField(TEXT("forward_offsets"), Input) ||
        !Spec->TryGetNumberField(TEXT("above"), Above) ||
        !Spec->TryGetNumberField(TEXT("below"), Below) ||
        !Spec->TryGetNumberField(TEXT("capsule_radius"), Radius) ||
        !Spec->TryGetNumberField(TEXT("capsule_half_height"), HalfHeight) ||
        !PPQueryDimensions(Input->Num(), Above, Below, Radius, HalfHeight))
    { Fail(TEXT("Invalid finite PhysicsReport query budget/dimensions.")); return 1; }
    TArray<double> Offsets;
    for (const auto& V : *Input)
    {
        if (V->Type != EJson::Number || !PPValidOffset(V->AsNumber(), Offsets.Num() ? Offsets.Last() : 0, Offsets.Num() == 0)) return 1;
        Offsets.Add(V->AsNumber());
    }
    if (Offsets[0] != 0) return 1;
    // Validate everything before the first map load. Fresh process, no PIE/gameplay.
    FString MapFile;
    if (!GEditor || !GIsEditor || !FPackageName::DoesPackageExist(Map, nullptr, &MapFile))
    { Fail(TEXT("Missing native editor or Deck package.")); return 1; }
    // Commandlet world initialization: avoid MAP LOAD's interactive editor-mode dependency.
    UPackage* Package = LoadPackage(nullptr, *MapFile, LOAD_None);
    UWorld* World = Package ? UWorld::FindWorldInPackage(Package) : nullptr;
    if (!World || World->GetOutermost()->GetName() != Map) return 1;
    World->WorldType = EWorldType::Editor;
    World->AddToRoot();
    if (!World->bIsWorldInitialized)
    {
        UWorld::InitializationValues IVS;
        IVS.RequiresHitProxies(false).ShouldSimulatePhysics(false).EnableTraceCollision(true)
            .CreateNavigation(false).CreateAISystem(false).AllowAudioPlayback(false).CreatePhysicsScene(true);
        World->InitWorld(IVS);
    }
    GEditor->GetEditorWorldContext().SetCurrentWorld(World);
    GWorld = World;
    World->PersistentLevel->UpdateModelComponents();
    World->UpdateWorldComponents(true, false);
    if (!World || World != GWorld || World->GetOutermost()->GetName() != Map ||
        World->WorldType != EWorldType::Editor || !World->PersistentLevel || !World->GetPhysicsScene())
    { Fail(TEXT("Native world/map/editor physics-scene identity mismatch.")); return 1; }
    if (World->PersistentLevel->Actors.Num() < 1) return 1;
    World->EnsureCollisionTreeIsBuilt();
    TArray<APlayerStart*> Starts;
    for (TActorIterator<APlayerStart> It(World); It; ++It) Starts.Add(*It);
    if (Starts.Num() < 1 || Starts.Num() > 32) { Fail(TEXT("Native Deck PlayerStart count outside 1..32 budget.")); return 1; }
    Starts.Sort([](const APlayerStart& A, const APlayerStart& B) { return A.GetPathName() < B.GetPathName(); });
    TArray<FVector> Points;
    TArray<TSharedPtr<FJsonValue>> Anchors;
    for (APlayerStart* Start : Starts)
    {
        const FVector Location = Start->GetActorLocation();
        const FRotator Rotation = Start->GetActorRotation();
        if (Location.ContainsNaN() || Rotation.ContainsNaN()) return 1;
        TSharedPtr<FJsonObject> A = MakeShareable(new FJsonObject);
        A->SetStringField(TEXT("actor"), Start->GetPathName());
        A->SetArrayField(TEXT("location"), PPVector(Location));
        A->SetStringField(TEXT("rotation"), Rotation.ToString());
        A->SetNumberField(TEXT("yaw_degrees"), Rotation.Yaw);
        A->SetArrayField(TEXT("forward"), PPVector(Rotation.Vector()));
        if (Start->GetCapsuleComponent()) A->SetObjectField(TEXT("start_capsule"), PPComponent(Start->GetCapsuleComponent()));
        Anchors.Add(MakeShareable(new FJsonValueObject(A)));
        for (double Offset : Offsets) Points.Add(Location + Rotation.Vector() * Offset);
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject);
    Result->SetStringField(TEXT("schema"), TEXT("ut4-physics-report-v1"));
    Result->SetStringField(TEXT("world"), World->GetPathName());
    Result->SetStringField(TEXT("map"), Map);
    Result->SetStringField(TEXT("map_file"), MapFile);
    Result->SetStringField(TEXT("map_sha1"), HashFile(MapFile));
    Result->SetBoolField(TEXT("editor_world_equals_gworld"), true);
    Result->SetBoolField(TEXT("physics_scene_present"), true);
    Result->SetBoolField(TEXT("has_begun_play"), World->HasBegunPlay());
    Result->SetNumberField(TEXT("world_type"), World->WorldType);
    Result->SetNumberField(TEXT("persistent_actor_slots"), World->PersistentLevel->Actors.Num());
    Result->SetBoolField(TEXT("read_only"), true);
    Result->SetObjectField(TEXT("query"), Spec);
    Result->SetArrayField(TEXT("player_starts"), Anchors);
    Result->SetNumberField(TEXT("player_start_count"), Starts.Num());
    TArray<TSharedPtr<FJsonValue>> Queries;
    for (int32 I = 0; I < Points.Num(); ++I)
    {
        for (int32 Complex = 0; Complex < 2; ++Complex)
        {
            FCollisionQueryParams Q(FName(TEXT("UT4PhysicsReport")), Complex != 0);
            Q.bReturnFaceIndex = true;
            for (APlayerStart* StartActor : Starts) Q.AddIgnoredActor(StartActor);
            const FVector Start = Points[I] + FVector(0, 0, Above), End = Points[I] - FVector(0, 0, Below);
            TSharedPtr<FJsonObject> J = MakeShareable(new FJsonObject);
            J->SetNumberField(TEXT("point_index"), I);
            J->SetNumberField(TEXT("start_index"), I / Offsets.Num());
            J->SetNumberField(TEXT("forward_offset"), Offsets[I % Offsets.Num()]);
            J->SetArrayField(TEXT("point"), PPVector(Points[I]));
            J->SetBoolField(TEXT("complex"), Complex != 0);
            J->SetArrayField(TEXT("start"), PPVector(Start)); J->SetArrayField(TEXT("end"), PPVector(End));
            TArray<FHitResult> Hits;
            World->LineTraceMultiByChannel(Hits, Start, End, ECC_Pawn, Q);
            TArray<TSharedPtr<FJsonValue>> H;
            for (const FHitResult& Hit : Hits) H.Add(MakeShareable(new FJsonValueObject(PPHit(Hit))));
            J->SetArrayField(TEXT("down_line_hits"), H);
            FHitResult Down;
            World->SweepSingleByChannel(Down, Points[I], End, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(Radius, HalfHeight), Q);
            J->SetObjectField(TEXT("down_capsule"), PPHit(Down));
            if ((I + 1) % Offsets.Num() != 0)
            {
                FHitResult Forward;
                World->SweepSingleByChannel(Forward, Points[I], Points[I+1], FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(Radius, HalfHeight), Q);
                J->SetObjectField(TEXT("forward_capsule"), PPHit(Forward));
            }
            Queries.Add(MakeShareable(new FJsonValueObject(J)));
        }
    }
    Result->SetArrayField(TEXT("queries"), Queries);
    TArray<TSharedPtr<FJsonValue>> Nearby;
    for (TObjectIterator<UPrimitiveComponent> It; It; ++It)
    {
        UPrimitiveComponent* C = *It;
        if (C->IsTemplate() || C->GetWorld() != World) continue;
        const FBox Box = C->Bounds.GetBox();
        bool Near = false;
        for (const FVector& P : Points)
            Near |= Box.Intersect(FBox(P - FVector(Radius + 32, Radius + 32, Below), P + FVector(Radius + 32, Radius + 32, Above)));
        if (!Near) continue;
        if (Nearby.Num() >= 4096) { Fail(TEXT("Nearby component budget exceeded; narrow points/range.")); return 1; }
        Nearby.Add(MakeShareable(new FJsonValueObject(PPComponent(C))));
    }
    Result->SetArrayField(TEXT("nearby_components"), Nearby);
    Result->SetBoolField(TEXT("map_package_dirty"), World->GetOutermost()->IsDirty());
    FString Text;
    FJsonSerializer::Serialize(Result.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    UE_LOG(LogUT4Html5Compat, Display, TEXT("COMPAT_PHYSICS_REPORT %s"), *Text);
    return 0;
}
