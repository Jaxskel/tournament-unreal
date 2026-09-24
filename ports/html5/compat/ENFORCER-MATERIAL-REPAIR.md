# Dedicated Enforcer material repair

This operation addresses the Enforcer gun-body material without changing the original material instances, which are also inherited by other weapons. It creates a dedicated copy of the already repaired weapon master and two Enforcer instances, disables static-lighting usage only on the new master, and changes material slot 0 on the two existing Enforcer skeletal meshes. It introduces no texture aliases, constant colors, mesh transforms, or animation changes.

The source proposal is supported by a native, transient-copy experiment: both Enforcer instances compiled valid ES2 WebGL shader maps at all three material qualities, with 15/16/16 samplers. That experiment did not save assets. The persistent repair subsequently passed native Apply and fresh-process Verify: exactly five assets were saved, then reloaded and verified with zero additional saves. Apply took 123.052 seconds; Verify took 114.564 seconds. Both runs passed all six ordinary shader-resource checks, and the other 28 tracked packages retained their hashes and identities. The mesh geometry and complete slot metadata matched the original baselines after normalizing only the two intended slot-0 material paths. A cook and actual browser appearance check are still required.

## Fixed operation

The five-package save allowlist is:

- `/Game/HTML5Compat/Weapons/V1/Enforcer/M_WeaponsBase_Enforcer`
- `/Game/HTML5Compat/Weapons/V1/Enforcer/MIC_Enforcer_1P`
- `/Game/HTML5Compat/Weapons/V1/Enforcer/MIC_Enforcer_3P`
- `/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_1p`
- `/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_3p`

The last two paths must already be physical, independent copies. The other three must be absent. The private preparation creates two verified external mesh beforeimages and a separate five-file receipt. It binds the current 30 existing packages, seven reviewed evidence artifacts, native geometry/slot baselines, and exact destination paths. It must not adopt an earlier operation's save receipt.

The native helper independently checks the pinned proof bytes, source hashes, physical paths and single-link files. Python preparation separately checks filesystem identities; the native JSON reader does not convert inode or timestamp numbers through floating point.

## Native modes

All three modes use `-run=UT4Html5Compat` and require rendering, the editor/game thread, normal dependency gathering, and these fixed-operation arguments:

```text
-EnforcerPreparation=<inputs.json> -EnforcerPreparationSHA1=<exact hash>
-EnforcerReceipt=<save-receipt.json> -EnforcerReceiptSHA1=<exact hash>
-EnforcerBefore=<new external before.json>
-EnforcerAftermath=<new external aftermath.json>
```

- `-Mode=EnforcerMaterialRepairPreflight` loads the original generation and compares both meshes with their recorded native baselines. It does not create evidence files, duplicate materials, compile the six test resources, assign slots, or save assets.
- `-Mode=EnforcerMaterialRepairApply` reserves both external evidence files exclusively, records the original semantics, duplicates and validates the materials, and compiles six ordinary shader resources before assigning either slot. It then saves exactly the five allowlisted packages in order.
- `-Mode=EnforcerMaterialRepairVerify` also requires `-EnforcerAftermathSHA1=<reviewed Apply hash>`. It runs in a fresh process, loads the saved generation, repeats full semantic and geometry comparisons, and recompiles/checks all six resources. It saves nothing. The two evidence paths must refer to that completed Apply.

Original and copied graphs, parameter values, override bags and parent chains are compared after normalizing only the dedicated paths and intentional new identity/static-lighting fields. Source materials and dependencies remain unchanged. The recorded geometry digest includes skeletons, sections, indices, positions, tangents, UVs, colors, all eight skin influences and supported import payloads. Both meshes retain all slot names, UV metadata and nonzero material assignments; only slot 0's interface may differ.

Failures stop the operation. Partial saves and evidence remain for diagnosis, with no automatic rollback, deletion or retry adoption. A receipt or partially written aftermath is insufficient: require a successful process exit, the exact completion record, matching hashes, and a separate successful fresh Verify. Shader resources must drain before completion evidence is written, and the aftermath is read back and compared before success is logged.

## Verification limits

The host tests execute extracted production control bodies with fake engine/file operations. They cover the bounded file table, transaction-known consumer hash updates, both-slot admission, each save-loop failure point, read-only modes, resource-drain ordering and aftermath corruption. They do not emulate Unreal serialization, shader compilation or Windows filesystem semantics.

After native Apply and fresh Verify, require a coherent new cook/package and actual browser inspection of first-person, third-person and dual-wield Enforcers, including decals, bullets, animation and placement. Keep the previous playable generation until that result is verified. No visual-parity, frame-rate, live Blueprint-consumer or gameplay claim follows from these preparation tests.
