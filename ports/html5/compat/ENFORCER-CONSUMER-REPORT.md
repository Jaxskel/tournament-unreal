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
