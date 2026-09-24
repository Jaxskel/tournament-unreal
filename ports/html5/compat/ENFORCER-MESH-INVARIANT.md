# Enforcer mesh baseline

`EnforcerMeshReport` reads the two fixed Enforcer skeletal meshes before their planned material-slot repair. It has no save operation. Admission requires the pinned seven-package consumer input, current 25-package material generation, completed private mesh-copy preparation, and physical selected mesh files. File pins are checked again after loading and reporting.

The snapshot hashes raw/final reference skeleton transforms, virtual-bone data, section flags and bone maps, CPU positions/tangents/UVs/colors/weights, topology, optional adjacency/import payloads and typed GPU skin vertices. It excludes padding and rejects unavailable required CPU data, oversized collections, morph/cloth payloads and nonempty GPU color buffers. Empty optional legacy import data is represented explicitly. This is a bounded helper for the observed meshes, not a general mesh serializer.

Separate material-slot records contain interface paths, slot/imported names and a metadata hash covering both legacy flags, UV initialization/override flags and all UV densities. This explicit capture is necessary because the engine marks `USkeletalMesh::Materials` transient, so generic property reporting omits it. Keeping interfaces separate permits a future repair to compare metadata exactly while admitting only slot zero's intended pointer replacement. This report admits no replacement.

Each mesh is snapshotted twice and must compare exactly, with no dirty-state change after loading. Normal PostLoad is allowed; global dependency immutability and runtime component ownership are not claimed.

## Private native verification

The revised helper compiled in the matching UE4 editor module (module 32, exit 0). A fresh read-only run completed in 5.648 seconds with two meshes, zero saves, clean selected packages and unchanged selected bytes. First-person has one LOD; third-person has four. Geometry matched the prior independent process exactly. Each mesh has `GunBase`, `Decal`, `CustomDecal` and `Bullets` slots. No slot changed.

Private evidence under `work/ut4-html5/enforcer-mesh-native-2/`:

- Raw report SHA-256: `1d65aec50a437c983da956a9524b38a2ba80a88daf71d9916009f9a08aa6a8ed`.
- Raw result SHA-256: `6d4115053833591732cba59bb5f2d82ef61eaff5d9cc5d144d7b29dc930a2f55`.
- Extracted records SHA-256: `f6ee44181b92865435b198bd8ea6edbc0dd608630388ca4546c00cb1b13d213f`.

Host tests execute extracted digest/bulk and slot-metadata methods plus the report's actual control flow with fake engine dependencies. Native compilation/execution supplies separate real-engine evidence. Asset-save roundtrip fidelity, an applied repair, cooking, browser appearance and performance remain pending.
