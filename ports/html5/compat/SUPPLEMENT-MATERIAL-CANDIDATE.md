# Bio Rifle body and grenade-ammunition material diagnostic

`SupplementMaterialCandidate` tests whether four original material instances can use the repaired weapon graph without changing their appearance parameters. It operates on transient Unreal objects and has no asset-save path. Bio Rifle glass is excluded: its scene-color dependency needs a separate rendering solution.

The fixed targets are:

- `BioRifle/New/BIO_Weapon3p` and its `BIO_Weapon_1p_Inst` child.
- `GrenadeLauncher/Materials/Grenade/MIC_Grenade` and its `Material_ThirdPerson/MIC_Grenade_3P` child.

Paths above are under `/Game/RestrictedAssets/Weapons/`. The diagnostic pins all four originals, their original master, and the exact completed 33-package Enforcer generation. It duplicates `/Game/HTML5Compat/Weapons/V1/M_WeaponsBase` into the transient package, gives that copy new identity GUIDs, and disables static-lighting usage only on the copy. The four transient instances retain their two parent/child chains; only the two transient parents point to the transient repaired master. There are no texture aliases, constant-color replacements, source setters, mesh changes or saved packages.

## Invocation

Use the matching native editor/compat module with rendering and ordinary dependency gathering:

```text
-run=UT4Html5Compat -Mode=SupplementMaterialCandidate
-SupplementAftermath=<reviewed Enforcer aftermath.json>
-SupplementAftermathSHA1=632833e9512e68db02899077e06f5024555776ee
-AllowCommandletRendering -unattended -nop4
-DDC=TournamentBrowserGpu8MaterialsE001
```

The aftermath is generation-specific private evidence, not a portable authorization to modify assets. `Receipt`, `Manifest` and `NoDependsGathering` are rejected. This operation must run with exclusive access to the selected isolated project. A process-admission snapshot does not provide a lock.

The diagnostic compares the complete V1 master graph and its transient clone, all four raw override bags, effective scalar/vector/texture/static values, material properties and parent chains. Comparisons normalize only the expected object paths and new identity fields. It rechecks all four instances and original source objects before and after every resource compile, including the final one. Source package bytes, dependency bytes and recorded dirty states must remain unchanged.

Each instance compiles at Low, Medium and High quality using ordinary ES2 WebGL material resources. Success requires twelve complete valid maps, matching full requested shader-map identities, no compile errors and at most sixteen samplers per resource. Resources disable persistence for this diagnostic; shader-job ownership or cache misses are not inferred from completion alone. Compilation must drain before objects are released and before completion is emitted.

Require native exit zero and exactly one completion record:

```text
COMPAT_SUPPLEMENT_CANDIDATE complete resources=12 valid=12 assetsSaved=0 sourceUnchanged=1 runtimeAcceptance=0
```

Any earlier failure, missing resource or failed drain invalidates the result. Keep failed logs for diagnosis; transient objects are not persisted after process exit. Do not interpret a partial resource list as success.

## Verification boundary

Host tests execute the production instance comparator with bounded engine/JSON stand-ins. They reject individual changes to raw overrides, parent hierarchy, effective parameters, static switches, blend mode and other appearance fields. Separate tests cover invalid member indices, legacy logging-macro compilation, fixed scope and commandlet admission. These tests do not reproduce Unreal serialization or shader compilation.

Even a successful native diagnostic establishes only the transient shader candidate. A persistent repair still needs its own narrow copy-on-write operation, proof that disabling static-lighting usage is appropriate for the assigned consumers, fresh-process verification, coherent cooking/packaging and actual first-/third-person browser inspection. It does not prove Bio glass, visual parity, animation placement or performance targets.

## Captured native result

The matching native run completed in **268.710 seconds**, exited zero, and passed all twelve ordinary shader-resource checks. Bio parent and child used **15 samplers at all qualities**; grenade-ammunition parent and child used **15 at Low and 16 at Medium/High**. Every resource retained equal original parameter facts and a valid full shader-map identity. The final source/object checks passed and **zero assets were saved**. A separate post-run read rechecked all protected inputs and the five original source-package hashes; the diagnostic/editor workers were no longer running.

The raw result SHA-256 is `b0eef3b6d67c1a4102503f3de72f04b4615e73122003bf45d275160b899c1926`; native log SHA-256 is `b89f94007b5f975e0ae7c5e2fa03351866e1943489336d334b34f901c9b8af2d`. Private operator evidence retains the full invocation, source pins and failed first module build. That first build failed on an unbraced legacy logging macro; the braced correction passed native compilation and a dedicated host regression.

This result has **not** changed the playable content package. The four materials still require a reviewed persistent repair, fresh cook/package and browser acceptance. Bio glass remains outside this result.
