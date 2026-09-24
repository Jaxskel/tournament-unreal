# Bio body and grenade-ammunition material repair

`SupplementMaterialRepair.h` turns the validated transient material candidate into five dedicated packages and four narrowly scoped skeletal-mesh changes. It is not a Bio-glass repair or a claim of native visual parity.

The operation creates `/Game/HTML5Compat/Weapons/V1/Supplement/` packages:

- `M_WeaponsBase_Supplement`: copy of the verified V1 graph; fresh identity and static-lighting usage disabled.
- `MIC_Bio_3P` → the new master; `MIC_Bio_1P` → the new Bio parent.
- `MIC_GrenadeAmmo_1P` → the new master; `MIC_GrenadeAmmo_3P` → the new ammo parent.

Only `Bio_Rifle_1p` / `Bio_Rifle_3p` material slot 0 and `Grenade_Launcher_1p` / `Grenade_Launcher_3p` slot 4 change. Original MICs, other slots, Blueprint defaults, static/prototype meshes and the existing 33-package repaired generation remain unchanged. This avoids changing the other consumers found by the fixed 17-package native observation.

## Authority and invariants

The native helper pins the exact 17-package consumer capture (SHA-1 `432b157e8c42414aca84276370b0d722e4a9e2dc`) and existing Enforcer aftermath through `FSupplementCandidatePins`. Selected and original paths/hashes are rechecked; only the four declared mesh files may diverge. The nine output paths are fixed in code. A separate `ut4-supplement-repair-preparation-v1` preparation, `supplement-nine-assets-v1` physical COW receipt, and four hash-matched external beforeimages are required. The receipt's manifest hash binds the preparation, and its allowlist must contain exactly the nine outputs.

Before graph edits, the helper exclusively reserves before/after evidence and writes four original mesh snapshots. `FEnforcerMeshInvariant::Snapshot` is reusable here: it hashes the skeleton, imported/CPU/GPU vertex data, indices, section metadata and bulk data, and captures reflected properties plus all material slots. It rejects unsupported nonempty morph or cloth buffers. In the editor game thread, GPU-color buffers are accepted only with matching vertex counts and the expected stride; every RGBA channel is hashed without padding. Empty-color snapshots retain their prior digest and coverage text. The only allowed comparison normalization is the target slot's material path. All other slot metadata and geometry must compare exactly.

Persistent material checks preserve the complete V1 graph, four MIC raw/effective/static parameter bags and the two parent-child chains. Original-master path normalization applies only to instance facts. No parameter aliases or texture replacements are introduced. All 12 ordinary ES2 resources (four MICs × three qualities) must finish with valid matching shader maps and at most 16 samplers before the first save.

Save order is master, four MICs, then four meshes. Every save rechecks source hashes, semantic equivalence, mesh invariants, external before-evidence hash and the individual physical save policy. Partial failure retains the changed files and evidence and emits no completion; there is no automatic rollback or adoption on retry.

## Entry points

The shared explicit-mode admission guard precedes all three modes:

- `SupplementMaterialRepairPreflight`: read-only physical, source and mesh checks.
- `SupplementMaterialRepairApply`: create, validate, compile and save exactly nine packages.
- `SupplementMaterialRepairVerify`: fresh-process loading, strict saved-hash/identity and original mesh-snapshot checks, all 12 shader resources again, no saves.

Required named arguments are `SupplementAftermath`, `SupplementAftermathSHA1` (the old Enforcer generation), `SupplementPreparation`, `SupplementPreparationSHA1`, `SupplementReceipt`, `SupplementReceiptSHA1`, `SupplementBefore`, and `SupplementRepairAftermath`. Verify additionally requires `SupplementRepairAftermathSHA1`. Generic `Manifest` / `Receipt` arguments are rejected to avoid confusing the separate save authority. Rendering and normal dependency gathering are required.

## Verification status

Seven focused tests execute extracted file-gate, slot-assignment, mesh-comparison and save-loop bodies with host fixtures, plus source-contract checks. The save-loop fixture injects failure at every observed gate. Eight commandlet admission/inverse tests pass. These are not Unreal serialization tests.

The integrated Unreal editor compatibility module compiled successfully on Windows on 2026-09-24 UTC. Initial native preflight rejected the grenade first-person mesh because the checker did not yet support its 29,012 GPU vertex colors; it saved no assets. The extended checker passed six host tests, independent review, and native module 39 compilation (15.055 seconds, exit 0). Its read-safety basis is the pinned engine color allocation with CPU access and editor/commandlet resource-array retention. Sparse physical preparation completed with original byte hashes preserved. Native Apply, fresh Verify, a matching cook/package, and browser visual/combat acceptance remain separate requirements; shader-candidate success alone does not establish them.

The actual module-39 preflight then passed on all four meshes with zero saves. Apply passed in 255.911 seconds: twelve ordinary shader maps were valid (Bio 15 samplers at every quality; grenade ammunition 15/16/16), exactly nine packages were saved, and the independent prepared-generation check preserved all 173 remaining immutable snapshots. Original mesh snapshots include the grenade color payload; only the intended material-slot paths normalize in comparisons. A separate fresh-process Verify passed in 230.627 seconds with twelve valid maps, zero saves and the same immutable-source checks. Cook/package and browser acceptance remain pending.
