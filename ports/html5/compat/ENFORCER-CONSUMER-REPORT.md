# Enforcer consumer report

`EnforcerConsumerReport` is a bounded, read-only UE4.15 commandlet mode for inspecting the Enforcer weapon and attachment consumer state. It does not save assets, change material assignments, execute pickup behavior, load a world, or grant repair authority.

## Fixed inputs and invocation

The native mode accepts `-Mode=EnforcerConsumerReport`, `-EnforcerInputs=<path>`, and `-EnforcerInputsSHA1=<sha1>`. The input file uses schema `ut4-enforcer-consumer-inputs-v1` and pins exactly seven package records by package name, resolved `.uasset` path, byte size, and SHA-1:

1. `/Game/RestrictedAssets/Weapons/Enforcer/Enforcer`
2. `/Game/RestrictedAssets/Weapons/Enforcer/Enforcer_Attach`
3. `/Game/RestrictedAssets/Weapons/Enforcer/Dual_Enforcer_Attach`
4. `/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_1p`
5. `/Game/RestrictedAssets/Weapons/Enforcer/Meshes/Enforcer_3p`
6. `/Game/RestrictedAssets/Weapons/Enforcer/Materials/M_Enforcer_Gun`
7. `/Game/RestrictedAssets/Weapons/Enforcer/Materials/Materials_thirdPerson/M_Enforcer_Gun_3rdPerson_Inst`

The native commandlet verifies the input digest and all seven file pins before loading, after each selected load, and at completion. It emits `COMPAT_WEAPON_ENFORCER` JSON rows under schema `ut4-enforcer-consumer-v1`. Validate the native log against the same input file with:

```sh
python3 enforcer_consumer_report.py <report.log> <inputs.json>
```

The validator requires a complete run, the fixed roots and their file pins, class/CDO and dual-default observations, component counts, and full selected-mesh material-slot observations. Its output remains evidence only; it does not authorize asset writes.

## Recorded native observation

The separate module-29 build exited 0 in 14.493 seconds. The native report process exited 0 and returned in 6.289 seconds; strict parsing accepted 297 rows, including 42 component observations. The 42 calls are observations, not 42 unique components. The native input pins cover seven selected packages. The external launcher additionally checked 25 protected files; their recorded before/after bytes were unchanged.

Across the five relevant CDO mesh components, slot 0 resolves through the Enforcer 1P or 3P mesh to its existing Enforcer material instance, while the component override is empty. This is inherited mesh-slot state, not a component override. The report also records 62 packages that became dirty in memory during normal loading; those observations were not cleared, and no asset was saved.

`GetPickupMeshTemplate` is reported as a native `UTInventory` function and was not executed. The report does not establish exclusive consumers, global dependency immutability, pickup appearance, repair safety, or visual acceptance. The current gray Enforcer appearance remains unresolved.

## Validation and provenance

The focused parser suite passed 11 tests. The existing assignment-report suite passed six tests with one private-spec test skipped; its inverse check covers the shared report-label parameterization. Native compilation and the native report were separate operations. Private run records are under `work/ut4-html5/enforcer-consumer-native-1`; the complete raw report is intentionally not copied here.

## Separate in-memory material candidate

`-Mode=EnforcerMaterialCandidate` takes the same fixed `EnforcerInputs` and digest, plus `-GrenadeAftermath=<path>` for the exact pinned 25-package generation. It requires commandlet rendering. It never adopts a write receipt, changes mesh slots, reparents an original material instance, aliases texture parameters, or saves a package.

The candidate duplicates the current repaired master and both Enforcer material instances into the transient package. Only the copied master's `bUsedWithStaticLighting` flag becomes false; only the copied instances are reparented. Source graphs, reflected properties, dirty observations, parameters, dependency file hashes and the selected package pins are compared before and after. Candidate comparison allows the intended parent/usage change and separately pinned clone identities; all other graph and raw/effective material values must agree.

Six ordinary `FMaterialResource` instances cover two materials at three qualities. Their static-lighting getter is not overridden. Shader maps are nonpersistent for this diagnostic, which also affects engine job priority; setter-triggered rendering-platform work can still populate DDC. Success requires completed valid maps, full requested/map identity agreement, no compile errors and at most 16 samplers. Resources and owned roots are released only after shader work drains; a failed drain retains them until process exit. This is compilation evidence, not asset-save authority, exclusive-consumer evidence, pixel parity or a frame-rate result.

Four local tests cover extracted close/entry failure paths and source boundaries. The separate module-30 build exited 0 in 14.868 seconds. The candidate process then exited 0 in 126.009 seconds: both materials passed Low/Medium/High with 15/16/16 samplers and 18 observed translation requests per resource. All six maps passed full identity and compile checks, followed by source/parameter/file checks and zero saves. Private raw log SHA-256 is `4a06f0d6dd39a4a6fa15b04f0444da379fa1fa4704a8cef407ddfe63a331e29d`; result SHA-256 is `81e20f22469d1ba051c7f3ddabf29b1225c7b48152468a5f23fc845bd62c0b02`. An independent review verified the six result rows. No Enforcer asset application, cook or browser visual acceptance is implied.

The subsequent private mesh preparation replaced the original eight-file `Meshes` junction with byte-identical, single-link private copies. It retained the old junction and two selected mesh beforeimages outside both engine trees. Nine disposable cases passed on Windows, including a forced second-rename failure; actual preparation exited 0 in 1.444 seconds with all eight copy hashes matching originals and 25 protected packages unchanged. The completion receipt SHA-256 is `3f694083a730b5509e4c3e92a246600a14a547de2a0d62775295f840a1b825bb`. No mesh content or slot was edited, and this preparation issues no asset-save receipt. The material repair and browser visual check remain pending.
