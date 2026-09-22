# Fixed weapon fidelity repair

This operation restores the original layered weapon materials and first-person projection. It has not yet passed native helper compilation, shader cooking, or browser rendering. Use only the coordinated private content view; keep the native report, baseline, receipt and resulting package hashes together.

The fixed recipe selects 18 original MICs, five new graph clones, and four direct-parent changes. The other 14 MICs retain their original parent hierarchy and exact restored bytes. No mesh slots, transforms, textures, parameter overrides or original master/function packages are saved. All 23 destinations must be physical private COW paths, although only nine are saved by the native operation.

The cloned master retains the original default graph. At ES2 only, an outer material-attributes override supplies WorldPositionOffset from the original first-person function's `WPO Only` output. Its pixel attributes still compile the original layered graph. Two cloned functions use zero precomputed occlusion at ES2 and their original precomputed-AO expression by default. Two additional function clones redirect dependencies to those copies. The native report and independent graph review establish the specific WPO-output equivalence; this is not a general graph simplifier.

Before any save the helper compares all 720 original graph nodes after exact clone/AO-path normalization, checks the six added nodes and connections, and compares all 18 MIC parent chains, static GUIDs/values, effective scalar/vector/texture parameters and raw scalar/vector/texture/font/base-property bags. Original selected/dependency package hashes must match. Clone property comparisons allow only graph containers/root and regenerated StateId, LightingGuid and derived MaterialFunctionInfos to differ. Pinned MaterialInterface.cpp regenerates LightingGuid on duplication/edit. Other properties remain checked. Loading may dirty an original in memory; the helper never clears dirty state or saves that package.

## Separate COW preparation

The operator first preserves each old fallback's bytes and hash, verifies the original source pins, restores the 18 selected MICs from the original project, and creates physical parent directories for the five absent clone paths. Do not run the old `fallback_textured` operation again or label this recipe as that operation. `weapon_fidelity.py` performs no asset copy, restoration or edit.

From the repository root, generate a read-only plan using the exact reviewed native log:

```sh
python3 -B ports/html5/compat/weapon_fidelity.py --log /private/fidelity-native-1/report.log
```

After the separate COW preparation, inspect it and create new evidence files outside asset Content roots:

```sh
python3 -B ports/html5/compat/weapon_fidelity.py --log /private/fidelity-native-1/report.log --project /private/UnrealTournament --original-project /original/UnrealTournament --baseline-out /private/evidence/weapon-baseline.json --receipt-out /private/evidence/weapon-receipt.json
```

Existing outputs are refused. The recipe pins the complete report and deterministic private baseline; proprietary graph data stays private. Receipt inspection is not native verification, shader validation or a transaction lock. Keep the coordinated source/content freeze through apply and verification.

## Native integration and operation

The shared CPP owner adds top-level includes for `Materials/MaterialExpressionConstant.h`, `Materials/MaterialExpressionFeatureLevelSwitch.h` and `Materials/MaterialExpressionSetMaterialAttributes.h`, then includes `WeaponFidelityRepair.h` inside `UT4Compat` after the report helpers. Two separate early dispatch modes call `WeaponFidelityRepair(Params, false)` for `WeaponRepairApply` and `WeaponFidelityRepair(Params, true)` for `WeaponRepairVerify`. They must precede the generic Apply/manifest path.

Both modes require `-WeaponRepairSpec=<repair.weapons.json> -WeaponBaseline=<private baseline> -Receipt=<private COW receipt>` in a fresh editor commandlet process. Apply requires rendering; do not use NullRHI. Verification uses a separate fresh process and saves nothing. No `Manifest=` or `NoDependsGathering` is accepted. Native preflight rechecks physical paths and source bytes. After a successful apply, run Verify before cooking. Preserve per-package log hashes and independently confirm the other 14 MICs remain identical to their original sources.

A failed save can leave a partial private generation. There is no automatic rollback or permission to serve it: retain evidence and restore from the separately preserved private backups before retrying in a fresh process. Successful structural verification alone does not prove ES2 shader compilation, Panini placement, lighting or weapon color. Main owns the matched fresh cook/package and actual first/third-person browser checks.

## Local tests

```sh
python3 -B ports/html5/compat/test_weapon_fidelity.py --private-source-dir /private/weapon-fidelity-source --private-log /private/fidelity-native-1/report.log -v
```

Tests inspect real disposable filesystem layouts and the actual native baseline. The private-source test compiles the pinned SetMaterialAttributes and FeatureLevelSwitch methods on the host with small compiler/input stubs, proving demand selection while preserving the original method bodies. This is not a UE module or shader compile. Without the two private inputs those evidence tests explicitly skip.
