# Bio Rifle and grenade-ammunition consumers

`SupplementConsumerReport` is a read-only native query for the four materials tested by [SupplementMaterialCandidate](SUPPLEMENT-MATERIAL-CANDIDATE.md). It observes seventeen fixed packages: four material instances, their nine non-material-instance direct referencers from the captured native registry, and four weapon/attachment Blueprints. It does not repair or save assets.

The additional roots include the older `BIO_InGame4`, `Grenade_Launcher`, `Grenade_Launcher_1p_v0`, `Grenade_Launcher_ThirdPerson` and `Grenade_Primed` assets. Their names do not establish their classes or gameplay use. The report records actual loaded classes, material slots, parent chains, Blueprint class ownership, existing CDO/component templates, material overrides and mobility. Unknown extra-root classes are explicitly reported as class-only observations. Known material and Blueprint roots have strict type checks.

## Input and invocation

```text
-run=UT4Html5Compat -Mode=SupplementConsumerReport
-SupplementInputs=<inputs.json> -SupplementInputsSHA1=<exact input-file hash>
-nullrhi -unattended -nop4 -DDC=TournamentBrowserGpu8MaterialsE001
```

The `ut4-supplement-consumer-inputs-v1` input specifies the selected project, an operator-supplied original project, and all seventeen packages in the exact order declared in `SCSupplementRoots`. Each row supplies selected/original filenames, positive integral byte counts (at most 64 MiB), SHA-1 values, and existence fields. Both paths must be exact project-relative counterparts of the fixed package. Both files must match the supplied hashes and have identical sizes and hashes. The selected project must be the running commandlet's project. The file itself is bound by the supplied SHA-1 and rechecked with every selected/original asset before each explicit load and at completion. The main operator separately records SHA-256 evidence.

This is a byte-pinned read-only view, not the physical single-link save admission used by repair helpers. Selected files may live under the project's existing content junctions. The query does not prove the identity of the operator-supplied original project, full dependency immutability or concurrent-writer exclusion. Run it under the coordinated project freeze. Manifest/Receipt arguments and disabled dependency gathering are rejected.

`COMPAT_SUPPLEMENT_CONSUMER` JSON rows include root identity, mesh slots and inherited material chains, Blueprint/component defaults and direct asset-registry metadata. The registry query covers the four MICs and five extra roots; it does not load additional referencers. Failed metadata queries and unknown classes remain explicit. The registry is not proof of active gameplay or exclusive consumption.

Normal PostLoad may create in-memory dirty states. The report emits those observations without clearing them, attributing them to a benign cause, or saving them. Completion requires all selected and original file hashes to remain unchanged. There are no world loads, actor spawns, Blueprint function execution, component setters or asset-save operations.

Require exit zero and a final `complete` row with `root_packages=17`, `assets_saved=0`, both byte-unchanged fields true, and both repair/runtime authority fields false. Partial rows or a nonzero exit are not a complete report. A successful report still requires separate analysis before choosing a persistent repair, especially for static meshes, inherited overrides and shared consumers.

## Captured native observation

The matching module compiled successfully and the report completed in **16.404 seconds**, exit zero. It emitted seventeen roots, four Blueprint identities and 495 bounded rows. All selected/original bytes remained unchanged. A separate post-run read verified 120 protected input hashes and found no remaining editor/compiler workers. The report observed **193 new dirty packages in memory**, without attributing their cause, clearing them or saving them.

The recorded weapon/attachment defaults reference `Bio_Rifle_1p` and `Bio_Rifle_3p` (body slot 0), and `Grenade_Launcher_1p` and `Grenade_Launcher_3p` (ammunition slot 4). Their recorded override arrays contain no non-null material overrides. These are CDO/template observations, not executed gameplay or live render-component proof.

`BIO_InGame4`, `Grenade_Launcher`, `Grenade_Launcher_ThirdPerson` and `Grenade_Primed` are static meshes. `Grenade_Launcher_1p_v0` is skeletal, with a registry reference from `BP_UDamageSpawn`. This rules out treating the originals as exclusive to the four weapon views. A proposed repair therefore gives the four selected skeletal meshes dedicated materials and leaves these other consumers and original MICs untouched. It still needs its own preparation, native Apply/Verify, cook and browser acceptance.

Raw result SHA-256: `0fd7f57478af47c338a4485af698125b9f282b6c72d86a7a3b024015091ea88c`. Native log SHA-256: `afb1f0e1787882c236402a669c6e7bcb1734a8136757d08ebc079220a798aa78`. The diagnostic did not change the playable package or fix Bio glass.
