// Original, opt-in read-only diagnostic. Included only by TournamentHTML5Controls.cpp.
// No engine implementation, arbitrary commands, asset loading, or collision setters.
#pragma once
#include "Engine/Engine.h"
#include "Engine/Level.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerStart.h"
#include "Components/CapsuleComponent.h"
#include "Components/ModelComponent.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysXPublic.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include <stdio.h>
#include <stdarg.h>

namespace TournamentPhysicsReport {
// Portable policy/output code is compiled directly by the focused local tests.
struct Admission
{
    bool GameThread, OptIn, Ready, Standalone, NoNetwork, Deck, Scene;
    double ExpectedEpoch, ActualEpoch;
};
static int Check(const Admission& A)
{
    if (!A.GameThread) return -1;
    if (!A.OptIn) return -2;
    if (!A.Ready) return 0;
    if (!FMath::IsFinite(A.ExpectedEpoch) || A.ExpectedEpoch <= 0 ||
        A.ExpectedEpoch > 4294967295.0 || A.ExpectedEpoch != A.ActualEpoch) return -3;
    if (!A.Standalone || !A.NoNetwork) return -4;
    if (!A.Deck || !A.Scene) return -5;
    return 1;
}
struct Budget
{
    double Epoch = 0;
    unsigned Count = 0;
    bool Take(double NewEpoch)
    {
        if (Epoch != NewEpoch) { Epoch = NewEpoch; Count = 0; }
        if (Count == 4) return false;
        ++Count;
        return true;
    }
};
struct Output
{
    char Lines[64][512];
    unsigned Count = 0;
    bool Truncated = false;
    double Epoch, Frame;
    unsigned Snapshot;
    Output(double E, double F, unsigned S) : Epoch(E), Frame(F), Snapshot(S) {}
    void Add(const char* Format, ...)
    {
        if (Count >= 63) { Truncated = true; return; }
        char Payload[384];
        va_list Args;
        va_start(Args, Format);
        const int Length = vsnprintf(Payload, sizeof(Payload), Format, Args);
        va_end(Args);
        if (Length < 0) { Payload[0] = 0; Truncated = true; }
        if (Length >= static_cast<int>(sizeof(Payload))) Truncated = true;
        Payload[sizeof(Payload)-1] = 0;
        for (unsigned I = 0; Payload[I]; ++I)
            if (static_cast<unsigned char>(Payload[I]) < 32 || static_cast<unsigned char>(Payload[I]) > 126) Payload[I] = '?';
        snprintf(Lines[Count], sizeof(Lines[Count]), "UT4PHYS v1 e=%.0f f=%.0f n=%u %s", Epoch, Frame, Snapshot, Payload);
        ++Count;
    }
    void Finish()
    {
        snprintf(Lines[Count], sizeof(Lines[Count]), "UT4PHYS v1 e=%.0f f=%.0f n=%u end rows=%u truncated=%d",
            Epoch, Frame, Snapshot, Count + 1, Truncated ? 1 : 0);
        ++Count;
    }
};
// End portable policy/output code.

struct Triangle182
{
    unsigned Indices[3];
    physx::PxVec3 Vertices[3];
    bool Indices16 = false, HasRemap = false;
    unsigned OriginalFace = 0;
};
static bool ReadTriangle182(const physx::PxTriangleMesh* Mesh, Triangle182& T)
{
    if (!Mesh || Mesh->getNbTriangles() <= 182 || Mesh->getNbVertices() == 0) return false;
    const void* Indices = Mesh->getTriangles();
    const physx::PxVec3* Vertices = Mesh->getVertices();
    if (!Indices || !Vertices) return false;
    T.Indices16 = Mesh->getTriangleMeshFlags().isSet(physx::PxTriangleMeshFlag::e16_BIT_INDICES);
    for (unsigned I=0; I<3; ++I)
    {
        T.Indices[I] = T.Indices16 ? static_cast<const physx::PxU16*>(Indices)[182*3+I]
            : static_cast<const physx::PxU32*>(Indices)[182*3+I];
        if (T.Indices[I] >= Mesh->getNbVertices()) return false;
    }
    // Validate every index before accessing any vertex; the optional remap has nbTriangles entries.
    for (unsigned I=0; I<3; ++I)
    {
        T.Vertices[I] = Vertices[T.Indices[I]];
        if (!T.Vertices[I].isFinite()) return false;
    }
    const physx::PxU32* Remap = Mesh->getTrianglesRemap();
    T.HasRemap = Remap != nullptr;
    T.OriginalFace = Remap ? Remap[182] : 0;
    return true;
}
class TargetOnlyFilter : public physx::PxQueryFilterCallback
{
    const physx::PxRigidActor* TargetActor;
    const physx::PxShape* TargetShape;
public:
    unsigned Calls = 0, TargetCalls = 0;
    TargetOnlyFilter(const physx::PxRigidActor* A, const physx::PxShape* S) : TargetActor(A), TargetShape(S) {}
    virtual physx::PxQueryHitType::Enum preFilter(const physx::PxFilterData&, const physx::PxShape* Shape,
        const physx::PxRigidActor* Actor, physx::PxHitFlags&) override
    {
        ++Calls;
        if (Actor == TargetActor && Shape == TargetShape)
        { ++TargetCalls; return physx::PxQueryHitType::eBLOCK; }
        return physx::PxQueryHitType::eNONE;
    }
    virtual physx::PxQueryHitType::Enum postFilter(const physx::PxFilterData&, const physx::PxQueryHit&) override
    { return physx::PxQueryHitType::eNONE; } // No post-filter flag is requested.
};
static void RayHit(Output& O, const char* Kind, bool HasHit, const physx::PxRaycastHit& H)
{
    // Misses have no valid distance/position/normal; never read those fields.
    if (!HasHit) { O.Add("ray kind=%s hit=0",Kind); return; }
    O.Add("ray kind=%s hit=1 distance=%.6f face=%u point=%.6f,%.6f,%.6f normal=%.6f,%.6f,%.6f",
        Kind,H.distance,H.faceIndex,H.position.x,H.position.y,H.position.z,H.normal.x,H.normal.y,H.normal.z);
}
static void MeshProbe(Output& O, const physx::PxScene* Scene, const physx::PxRigidActor* Actor,
    const physx::PxShape* Shape, const physx::PxTriangleMeshGeometry& G)
{
    // Caller holds the sync scene read lock. No flush, refit, or scene/geometry writes.
    const physx::PxTransform GlobalPose = Actor->getGlobalPose() * Shape->getLocalPose();
    if (!G.isValid() || !GlobalPose.isValid())
    { O.Add("meshProbe skipped=invalidGeometryOrPose"); return; }
    const physx::PxBounds3 LocalBounds = G.triangleMesh->getLocalBounds();
    const physx::PxBounds3 ActorBounds = Actor->getWorldBounds(1.0f);
    O.Add("meshBounds min=%.6f,%.6f,%.6f max=%.6f,%.6f,%.6f",LocalBounds.minimum.x,LocalBounds.minimum.y,LocalBounds.minimum.z,
        LocalBounds.maximum.x,LocalBounds.maximum.y,LocalBounds.maximum.z);
    O.Add("actorBounds inflation=1 min=%.6f,%.6f,%.6f max=%.6f,%.6f,%.6f",ActorBounds.minimum.x,ActorBounds.minimum.y,ActorBounds.minimum.z,
        ActorBounds.maximum.x,ActorBounds.maximum.y,ActorBounds.maximum.z);
    Triangle182 T;
    if (!ReadTriangle182(G.triangleMesh,T))
    { O.Add("meshProbe skipped=triangle182Unreadable"); return; }
    O.Add("triangle internal=182 indexBits=%d indices=%u,%u,%u remapPresent=%d originalFace=%u expectedFace=%d",
        T.Indices16 ? 16 : 32,T.Indices[0],T.Indices[1],T.Indices[2],T.HasRemap,T.OriginalFace,T.HasRemap && T.OriginalFace==625);
    for (unsigned I=0; I<3; ++I)
        O.Add("triangleVertex slot=%u index=%u local=%.6f,%.6f,%.6f",I,T.Indices[I],T.Vertices[I].x,T.Vertices[I].y,T.Vertices[I].z);
    const physx::PxVec3 Origin(4600.f,4670.f,633.2301025390625f+256.f), Direction(0.f,0.f,-1.f);
    const physx::PxHitFlags HitFlags(physx::PxHitFlag::eDEFAULT);
    O.Add("raySpec origin=%.6f,%.6f,%.6f dir=0,0,-1 length=2304 maxHits=1",Origin.x,Origin.y,Origin.z);
    physx::PxRaycastHit Direct;
    const unsigned DirectCount=physx::PxGeometryQuery::raycast(Origin,Direction,G,GlobalPose,2304.f,HitFlags,1,&Direct);
    RayHit(O,"geometry",DirectCount!=0,Direct);
    TargetOnlyFilter Filter(Actor,Shape);
    const physx::PxQueryFilterData Query(physx::PxFilterData(0,0,0,0),physx::PxQueryFlag::eSTATIC | physx::PxQueryFlag::ePREFILTER);
    physx::PxRaycastBuffer SceneHit;
    const bool Result=Scene->raycast(Origin,Direction,2304.f,SceneHit,HitFlags,Query,&Filter,nullptr);
    O.Add("sceneRay result=%d block=%d prefilterCalls=%u targetCalls=%u targetHit=%d staticOnly=1 queryWords=0,0,0,0",
        Result,SceneHit.hasBlock,Filter.Calls,Filter.TargetCalls,
        SceneHit.hasBlock && SceneHit.block.actor==Actor && SceneHit.block.shape==Shape);
    RayHit(O,"targetScene",SceneHit.hasBlock,SceneHit.block);
}

static void Component(Output& O, const char* Label, UPrimitiveComponent* C)
{
    if (!C) { O.Add("%s missing=1", Label); return; }
    AActor* Owner = C->GetOwner();
    FBodyInstance* BI = C->GetBodyInstance();
    const FVector P = C->GetComponentLocation(), S = C->GetComponentScale();
    O.Add("%s name=%s owner=%s actorCollision=%d registered=%d physics=%d bodyValid=%d enabled=%d profile=%s object=%d pawn=%d static=%d",
        Label, TCHAR_TO_UTF8(*C->GetName()), Owner ? TCHAR_TO_UTF8(*Owner->GetName()) : "none",
        Owner ? (Owner->GetActorEnableCollision() ? 1 : 0) : -1, C->IsRegistered(), C->IsPhysicsStateCreated(),
        BI && BI->IsValidBodyInstance(), static_cast<int>(C->GetCollisionEnabled()),
        TCHAR_TO_UTF8(*C->GetCollisionProfileName().ToString()), static_cast<int>(C->GetCollisionObjectType()),
        static_cast<int>(C->GetCollisionResponseToChannel(ECC_Pawn)), static_cast<int>(C->GetCollisionResponseToChannel(ECC_WorldStatic)));
    O.Add("%s pos=%.6f,%.6f,%.6f scale=%.6f,%.6f,%.6f", Label, P.X,P.Y,P.Z,S.X,S.Y,S.Z);
}
static void ActorShapes(Output& O, FBodyInstance* BI, UBodySetup* B, FPhysScene* Physics, int SceneType)
{
    // UE4.15 asserts on the async index when that scene is disabled; do not query it.
    if (SceneType == PST_Async && !Physics->HasAsyncScene())
    { O.Add("px scene=%d present=0 asyncEnabled=0 inspected=0",SceneType); return; }
    physx::PxScene* Scene = Physics->GetPhysXScene(SceneType);
    if (!BI || !Scene) { O.Add("px scene=%d present=%d body=%d inspected=0", SceneType, Scene != nullptr, BI != nullptr); return; }
    // Each actor is read under its own world's scene lock, including the async actor.
    SCOPED_SCENE_READ_LOCK(Scene);
    physx::PxRigidActor* Actor = BI->GetPxRigidActor_AssumesLocked(SceneType);
    if (!Actor) { O.Add("px scene=%d actor=0", SceneType); return; }
    const physx::PxTransform Pose = Actor->getGlobalPose();
    const unsigned Total = Actor->getNbShapes();
    O.Add("px scene=%d actor=1 inScene=%d expectedScene=%d shapes=%u pos=%.6f,%.6f,%.6f quat=%.6f,%.6f,%.6f,%.6f",
        SceneType, Actor->getScene() != nullptr, Actor->getScene() == Scene, Total,
        Pose.p.x,Pose.p.y,Pose.p.z,Pose.q.x,Pose.q.y,Pose.q.z,Pose.q.w);
    physx::PxShape* Shapes[8];
    const unsigned Count = Actor->getShapes(Shapes, 8);
    if (Total > Count) { O.Truncated = true; O.Add("px scene=%d shapesOmitted=%u", SceneType, Total-Count); }
    bool Probed = false;
    for (unsigned I = 0; I < Count; ++I)
    {
        const physx::PxShape* Shape = Shapes[I];
        const physx::PxFilterData Q = Shape->getQueryFilterData(), F = Shape->getSimulationFilterData();
        const physx::PxTransform Local = Shape->getLocalPose();
        const physx::PxShapeFlags Flags = Shape->getFlags();
        O.Add("shape scene=%d i=%u geometry=%d flags=%u query=%d sim=%d q=%u,%u,%u,%u filter=%u,%u,%u,%u",
            SceneType,I,static_cast<int>(Shape->getGeometryType()),static_cast<unsigned>(Flags),
            Flags.isSet(physx::PxShapeFlag::eSCENE_QUERY_SHAPE),Flags.isSet(physx::PxShapeFlag::eSIMULATION_SHAPE),
            Q.word0,Q.word1,Q.word2,Q.word3,F.word0,F.word1,F.word2,F.word3);
        O.Add("shapePose scene=%d i=%u pos=%.6f,%.6f,%.6f quat=%.6f,%.6f,%.6f,%.6f", SceneType,I,
            Local.p.x,Local.p.y,Local.p.z,Local.q.x,Local.q.y,Local.q.z,Local.q.w);
        physx::PxTriangleMeshGeometry G;
        if (Shape->getGeometryType() == physx::PxGeometryType::eTRIANGLEMESH && Shape->getTriangleMeshGeometry(G))
        {
            int Match = -1;
            if (B) for (int J = 0; J < FMath::Min(B->TriMeshes.Num(),8); ++J) if (B->TriMeshes[J] == G.triangleMesh) { Match = J; break; }
            O.Add("shapeMesh scene=%d i=%u bodyMesh=%d vertices=%u triangles=%u flags=%u scale=%.6f,%.6f,%.6f rotation=%.6f,%.6f,%.6f,%.6f",
                SceneType,I,Match,G.triangleMesh ? G.triangleMesh->getNbVertices() : 0,
                G.triangleMesh ? G.triangleMesh->getNbTriangles() : 0,static_cast<unsigned>(G.meshFlags),
                G.scale.scale.x,G.scale.scale.y,G.scale.scale.z,G.scale.rotation.x,G.scale.rotation.y,G.scale.rotation.z,G.scale.rotation.w);
            if (!Probed && SceneType==PST_Sync && Match==0 && B && B->GetFName()==FName(TEXT("BodySetup_15")))
            {
                Probed=true;
                MeshProbe(O,Scene,Actor,Shape,G);
            }
        }
    }
    if (SceneType==PST_Sync && !Probed) O.Add("meshProbe skipped=targetShapeMissing");
}
static void Hit(Output& O, const char* Kind, int Complex, const FHitResult& H)
{
    UPrimitiveComponent* C = H.Component.Get();
    O.Add("hit kind=%s complex=%d block=%d penetrating=%d time=%.6f depth=%.6f component=%s face=%d point=%.6f,%.6f,%.6f normal=%.6f,%.6f,%.6f",
        Kind,Complex,H.bBlockingHit,H.bStartPenetrating,H.Time,H.PenetrationDepth,
        C ? TCHAR_TO_UTF8(*C->GetName()) : "none",H.FaceIndex,H.ImpactPoint.X,H.ImpactPoint.Y,H.ImpactPoint.Z,
        H.ImpactNormal.X,H.ImpactNormal.Y,H.ImpactNormal.Z);
}
static void Snapshot(Output& O, UWorld* World, APlayerController* Player)
{
    APawn* Pawn = Player->GetPawn();
    ACharacter* Character = Cast<ACharacter>(Pawn);
    UCapsuleComponent* Capsule = Character ? Character->GetCapsuleComponent() : nullptr;
    Component(O, "capsule", Capsule);
    if (Pawn)
    {
        const FVector P = Pawn->GetActorLocation(), V = Pawn->GetVelocity();
        O.Add("pawn name=%s actorCollision=%d pos=%.6f,%.6f,%.6f velocity=%.6f,%.6f,%.6f",
            TCHAR_TO_UTF8(*Pawn->GetName()),Pawn->GetActorEnableCollision(),P.X,P.Y,P.Z,V.X,V.Y,V.Z);
    }
    else O.Add("pawn missing=1");
    if (Capsule) O.Add("capsule radius=%.6f halfHeight=%.6f",Capsule->GetScaledCapsuleRadius(),Capsule->GetScaledCapsuleHalfHeight());
    UCharacterMovementComponent* Movement = Character ? Character->GetCharacterMovement() : nullptr;
    if (Movement)
    {
        UPrimitiveComponent* Base = Character->GetMovementBase();
        O.Add("movement mode=%d custom=%d base=%s floorBlocking=%d floorWalkable=%d floorDistance=%.6f",
            static_cast<int>(Movement->MovementMode),Movement->CustomMovementMode,
            Base ? TCHAR_TO_UTF8(*Base->GetName()) : "none",Movement->CurrentFloor.bBlockingHit,
            Movement->CurrentFloor.IsWalkableFloor(),Movement->CurrentFloor.FloorDist);
        Hit(O,"currentFloor",0,Movement->CurrentFloor.HitResult);
    }
    else O.Add("movement missing=1");
    UModelComponent* Model = FindObjectFast<UModelComponent>(World->PersistentLevel,FName(TEXT("ModelComponent_65")));
    Component(O,"model65",Model);
    UBodySetup* B = Model ? Model->ModelBodySetup : nullptr; // Existing pointer; no lazy body creation.
    if (B)
    {
        O.Add("body name=%s expected=%d created=%d cooked=%d neverCook=%d raw=%d effective=%d doubleSided=%d tris=%d convex=%d boxes=%d spheres=%d capsules=%d",
            TCHAR_TO_UTF8(*B->GetName()),B->GetFName()==FName(TEXT("BodySetup_15")),B->bCreatedPhysicsMeshes,
            B->bHasCookedCollisionData,B->bNeverNeedsCookedCollisionData,static_cast<int>(B->CollisionTraceFlag),
            static_cast<int>(B->GetCollisionTraceFlag()),B->bDoubleSidedGeometry,B->TriMeshes.Num(),
            B->AggGeom.ConvexElems.Num(),B->AggGeom.BoxElems.Num(),B->AggGeom.SphereElems.Num(),B->AggGeom.SphylElems.Num());
        const int Count = FMath::Min(B->TriMeshes.Num(),8);
        if (Count != B->TriMeshes.Num()) O.Truncated = true;
        for (int I=0; I<Count; ++I)
        {
            const physx::PxTriangleMesh* Mesh = B->TriMeshes[I];
            O.Add("bodyMesh i=%d present=%d vertices=%u triangles=%u",I,Mesh!=nullptr,
                Mesh ? Mesh->getNbVertices() : 0,Mesh ? Mesh->getNbTriangles() : 0);
        }
    }
    else O.Add("body missing=1");
    FBodyInstance* BI = Model ? Model->GetBodyInstance() : nullptr;
    ActorShapes(O,BI,B,World->GetPhysicsScene(),PST_Sync);
    ActorShapes(O,BI,B,World->GetPhysicsScene(),PST_Async);
    // Both actor read locks have ended before any world query or output.
    APlayerStart* StartActor = FindObjectFast<APlayerStart>(World->PersistentLevel,FName(TEXT("PlayerStart_3")));
    const FVector Anchor(4600.f,4670.f,633.2301025390625f);
    if (StartActor)
    {
        const FVector P = StartActor->GetActorLocation();
        O.Add("start3 present=1 matches=%d pos=%.6f,%.6f,%.6f",P.Equals(Anchor,0.001f),P.X,P.Y,P.Z);
    }
    else O.Add("start3 present=0");
    TArray<APlayerStart*> Starts;
    if (World->PersistentLevel->Actors.Num()>4096)
    { O.Truncated=true; O.Add("traceSkipped reason=actorScanBudget"); return; }
    for (AActor* Actor : World->PersistentLevel->Actors)
    {
        APlayerStart* Start=Cast<APlayerStart>(Actor);
        if (!Start) continue;
        if (Starts.Num()==32)
        { O.Truncated=true; O.Add("traceSkipped reason=startBudget"); return; }
        Starts.Add(Start);
    }
    const FVector Top = Anchor+FVector(0,0,256), Bottom = Anchor-FVector(0,0,2048);
    O.Add("traceSpec x=4600 y=4670 anchorZ=633.230103 above=256 below=2048 radius=40 halfHeight=108 channel=Pawn ignorePawn=%d ignoreStarts=%d",Pawn!=nullptr,Starts.Num());
    for (int Complex=0; Complex<2; ++Complex)
    {
        FCollisionQueryParams Q(FName(TEXT("TournamentPhysicsReport")),Complex!=0);
        Q.bReturnFaceIndex=true;
        if (Pawn) Q.AddIgnoredActor(Pawn); // Native reference has no live pawn at the anchor.
        for (APlayerStart* Start : Starts) Q.AddIgnoredActor(Start);
        TArray<FHitResult> Hits;
        World->LineTraceMultiByChannel(Hits,Top,Bottom,ECC_Pawn,Q);
        O.Add("line complex=%d hits=%d",Complex,Hits.Num());
        const int Count=FMath::Min(Hits.Num(),4);
        if (Count!=Hits.Num()) O.Truncated=true;
        for (int I=0; I<Count; ++I) Hit(O,"line",Complex,Hits[I]);
        FHitResult Down;
        World->SweepSingleByChannel(Down,Anchor,Bottom,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(40.f,108.f),Q);
        Hit(O,"capsule",Complex,Down);
    }
}
} // namespace TournamentPhysicsReport

// Status: 1 emitted (including missing data); 0 not Ready; -1 wrong thread;
// -2 no launch opt-in; -3 invalid/stale epoch; -4 network; -5 map/scene; -6 budget.
extern "C" EMSCRIPTEN_KEEPALIVE int TournamentBrowserPhysicsReport(double ExpectedEpoch)
{
    using namespace TournamentPhysicsReport;
    // Do not even inspect engine/world objects from another thread or without opt-in.
    if (!IsInGameThread()) return -1;
    if (!FParse::Param(FCommandLine::Get(),TEXT("TournamentPhysicsReport"))) return -2;
    if (!TournamentBrowserReady()) return 0;
    UWorld* World=BrowserWorld();
    const FWorldContext* Context=GEngine->GetWorldContextFromWorld(World);
    const double ActualEpoch=TournamentBrowserSessionEpoch();
    const Admission A={true,true,true,World->GetNetMode()==NM_Standalone,
        Context && !Context->PendingNetGame && Context->ActiveNetDrivers.Num()==0 && !World->GetNetDriver(),
        World->PersistentLevel && World->GetOutermost()->GetName()==TEXT("/Game/RestrictedAssets/Maps/WIP/DM-DeckTest"),
        World->GetPhysicsScene()!=nullptr,ExpectedEpoch,ActualEpoch};
    const int Status=Check(A);
    if (Status!=1) return Status;
    static Budget Calls;
    if (!Calls.Take(ActualEpoch)) return -6;
    Output O(ActualEpoch,static_cast<double>(GFrameCounter),Calls.Count);
    O.Add("begin map=DM-DeckTest standalone=1 ready=1");
    Snapshot(O,World,BrowserPlayer());
    O.Finish();
    for (unsigned I=0; I<O.Count; ++I) puts(O.Lines[I]);
    return 1;
}
