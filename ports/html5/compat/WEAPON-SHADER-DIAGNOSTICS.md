# Weapon shader and usage diagnostics

These original commandlet helpers inspect the pinned private weapon repair
generation. They are not an Apply mode and cannot authorize a material change.
They require the matching private recipe, baseline, current-generation proof,
one-master receipt, external beforeimage and reviewed Tess aftermath used by
fresh `WeaponTessVerify`. Licensed assets and those machine-specific records are
not included in this repository.

## All repaired materials, three quality levels

`-Mode=WeaponShaderBatchProbe -WeaponUV0 -WeaponTess1` runs a fresh read-only
eight-node Tess verification, then inspects exactly the recipe's 18 repaired MICs
at Low, High and Medium quality. Use `-AllowCommandletRendering` and the existing
verified private DDC graph. Supply the same proof arguments as the fresh verifier:
`WeaponRepairSpec`, `WeaponBaseline`, `Receipt`, `WeaponCurrentProof`,
`WeaponTessReceipt`, `WeaponMasterBackup`, `WeaponTessAftermath`, and
`WeaponTessAftermathSHA1`. Do not combine a `Mode` with `-WeaponShaderProbe`,
`-WeaponTessVerify` or `-WeaponTessUpgrade`; operation admission rejects that.

The batch deliberately tests a counterfactual. Each owned `FMaterialResource`
reports no static-lighting usage and is nonpersistent. No `UMaterial` flag,
instance parameter, asset file or global CVar is changed. The ordinary dependency
ID is recorded in memory first, then a new ID is generated through the override;
strict shader-type dependency reduction is required. It does not reuse the
ordinary ID. Nonpersistent resources also receive the engine's preview job
priority and do not request component recreation on completion.

Every resource must finish compilation before release. Compile-invalid results
are recorded while the batch continues through the fixed set; an undrained
resource, requested-identity discrepancy or changed pinned generation aborts. Acceptance
checks require a valid, finalized, successfully compiled WebGL ES2 map, matching
quality and material/instance identity subset, no compile errors, and sampler
usage in 0–16. The extra identity comparison is explicitly a subset; full shader
ID lookup remains the engine's responsibility.

Rows use `COMPAT_WEAPON_SHADER_BATCH`. Complete scope is exactly 54 unique
material/quality pairs plus the matching completion line. Exit0 requires all54
to be valid; exit1 may describe a complete diagnostic with failed materials or an
aborted run. Retain the full log and validate scope independently. The completion
always says `assetsSaved=0 ordinaryAcceptance=0`. Neither successful completion
nor one passing Enforcer shader proves ordinary material compilation, usage
safety, browser linkage, correct pixels, or runtime performance.

The existing `-WeaponShaderProbe` remains the ordinary two-Enforcer × three-quality
probe. Its explicit `-WeaponShaderEnforcer1PHigh` and
`-WeaponShaderNoStaticLighting` modifiers retain their distinct one-resource
diagnostic completion formats; they do not select arbitrary materials.

For a bounded failed-shader capture, add `-WeaponShaderGrenade1PHigh` to
`-Mode=WeaponShaderBatchProbe`. It retains the full generation verification and
all 18 instance prereads, then compiles only Grenade Launcher first-person at
High quality. The owned no-static-lighting override is unchanged; no static
parameter is overridden. Completion uses `COMPAT_WEAPON_SHADER_BATCH_DIAGNOSTIC`
with `selector=grenade1p-high` and exactly one resource, never the ordinary
54-resource completion. A failed shader still exits1 and remains useful diagnostic
evidence; it is not shader or appearance acceptance.

## Usage report and materials-only cohort

`-Mode=WeaponUsageReport` is a separate read-only usage audit. Its default scope
includes reverse material users, component templates, relevant maps and their
dependency closures. Missing hard dependencies, unexpected classes, newly dirty
packages, fingerprint drift and incomplete evidence abort the report. A missing
dependency in an unshipped WIP map can block this broad audit without proving that
the supported practice maps use that asset.

The explicit `-UsageDiagnosticCohort=materials` produces a smaller diagnostic:
the exact 20 native MIC descendants, including the selected 18, plus prerequisite,
preloaded and forward dependency checks. It retains reverse-reference metadata
but does not observe classes, map components or lighting scenarios. It requires
the spec's two hash-pinned historical report2 inputs and labels that failure as
historical, not revalidated. It does not waive current missing dependencies or
dirty-package checks.

This cohort uses prefix `COMPAT_WEAPON_USAGE_DIAGNOSTIC`, schema
`ut4-weapon-usage-diagnostic-v1`, terminal `diagnostic_end`, and **exit2** for a
fully observed diagnostic. Exit2 is never ordinary/global success. Failure or
partial evidence exits1. Every row says `global_usage_complete=false`. Omitting
the cohort preserves the ordinary report behavior; unsupported cohorts fail.
The frozen spec and SHA-bound `UsageInputs` manifest are required in either mode.

```sh
python3 -B ports/html5/compat/test_weapon_shader_batch_probe.py -v
python3 -B ports/html5/compat/test_weapon_usage.py -v
python3 -B ports/html5/compat/test_weapon_usage.py --diagnostic-log /private/report.log --native-exit-code 2
```

The last command also exits2 for a valid materials diagnostic. Local host tests
and structural fixtures do not prove UE compilation or native observations.
New native runs require matching source/DLL hashes, foreground completion,
unchanged input fingerprints and separately validated logs. Do not infer a safe
asset repair from a materials-only report; actual component/static-lighting usage
and fresh shader/browser checks remain separate work.

## Recorded native validation

Both new helpers compiled and linked in the private UE4.15 editor module. The
batch completed all 54 resources: 39 valid, 15 invalid, exit1. Standard Enforcer,
Flak, Lightning, Link and Rocket materials passed all three qualities under the
counterfactual. The custom Enforcer pattern, both Grenade Launcher materials and
both Sniper materials failed every quality. Compiler error counts ranged from
22–25 samplers for Pattern, 20–22 for Grenade, and 17–20 for Sniper. The `-1`
sampler field on invalid rows means no valid-map usage was available; it is not a
sampler count. Eleven before/after input pins matched and private DDC provenance
passed. These results are not ordinary shader acceptance.

The materials-only usage attempt exited1 during prerequisite inventory, before
fresh Verify or MIC observation. A registry-derived custom Link Gun candidate
references the absent `Lea_ArrowThingGradient` texture. This establishes neither
membership in the native 20-MIC closure nor a complete materials cohort. The
missing file was also absent from the original source tree; no replacement or
guard exception was introduced. The report and failed validation are retained.

## Fixed Grenade Blueprint graph observation

`-Mode=WeaponBlueprintReport -BlueprintOriginalContent=<absolute-original-Content>`
observes exactly the Grenade Launcher and its attachment Blueprint. Run in a fresh
editor commandlet process with `-nullrhi`. It compares both selected packages with
the operator-supplied original files before loading and again after the report.
It never saves packages, executes gameplay or explicitly compiles Blueprints.
Normal engine PostLoad may regenerate classes or normalize graph data; this is a
post-load observation, not a raw package or bytecode proof.

Rows with prefix `COMPAT_WEAPON_BLUEPRINT` enumerate graph ownership, nodes,
nontransient reflected properties, pin types/defaults/links and generated/native
function metadata. Bounds fail rather than report truncated completion. Interface
graphs outside this fixed capture are rejected. External member references remain
unresolved; implicit dependency loads and their bytes are not a complete audited
closure. Text defaults are exported display strings.

Successful observation requires exit0, contiguous sequences, two exact Blueprint
and after rows with unchanged hashes, and one terminal `kind="complete"` record
with `roots=2`, `assets_saved=false` and `global_immutability_proven=false`.
Dirty-after-load and final dirty states are observations; the helper never clears
them. A complete graph capture alone does not authorize sampler aliasing or claim
that all runtime material mutation paths have been covered.

```sh
python3 -B ports/html5/compat/test_weapon_blueprint_report.py -v
```

The optional `--private-source` argument exercises the captured matching UE4
public field declarations. Host fixtures are distinct from native UE execution.

The observer compiled and linked in the private editor module. A subsequent
native run returned exit0 with 623 contiguous records: two Blueprints, four
graphs, 50 nodes, 179 pins and 94 directed link records. Both selected package
hashes matched their original files before and after observation; both were
clean at the recorded dirty-state checks. Nine source, binary, configuration and
asset fingerprints remained unchanged. No assets were saved. The attachment
Blueprint had already loaded as a dependency before its explicit request, which
the report records. This is bounded post-load graph evidence, not proof of all
runtime texture mutations or permission to merge material parameters.

## Fixed transient sampler-alias experiment

`-Mode=WeaponSamplerAliasProbe` requires the same verified Tess/UV0 generation
and proof arguments as the existing shader probe. It targets only Grenade
Launcher first-person High. It duplicates the master, `MF_LayerSet` and MIC into
owned transient objects, then redirects three layer-normal parameter names to
the base-layer normal and three diffuse names to the base-layer diffuse.
Admission requires the effective textures to match within each group. Every
sample, UV, mip mode, scalar/vector calculation and static switch is preserved.
The original objects and package bytes are checked before and after; no package
save is permitted.

This intentionally removes independent override semantics in the **temporary
experiment**, so success cannot authorize a production alias. The separate live
material/skin contract and visual comparisons remain required. It retains the
previous owned-resource no-static-lighting policy and requests 14 material 2D
bindings, compared with 20 in the earlier captured baseline. A fresh valid map
and its full material binding array must establish that reduction. Default
normal and undercoat diffuse samples are unchanged.

Cloned-MIC parenting can start additional rendering-platform jobs and write
private DDC entries. These are distinct from the one nonpersistent WebGL
resource. Global and owned-resource jobs drain before cleanup; a failed drain
retains roots until process exit. The `COMPAT_WEAPON_SAMPLER_ALIAS` completion
record labels `ordinaryAcceptance=0` and `runtimeImmutabilityProven=0`.

```sh
python3 -B ports/html5/compat/test_weapon_sampler_alias_probe.py -v
```

Host tests and graph fixtures do not prove native compilation, binding reduction
or rendering equivalence.

The fixed experiment compiled and linked in the private UE4.15 module in 14.34
seconds. Its native commandlet returned exit0: one High resource, a valid WebGL
map, 16 maximum samplers, 14 material 2D bindings and no cube bindings. The earlier
captured baseline had 20 material 2D bindings; it was not remeasured in the same
run. All eleven wrapper input fingerprints remained unchanged, the source
object/graph checks passed, no assets were saved, and temporary debug settings
were restored. All 738 captured WebGL files matched their recorded sizes and
hashes. Independent comparison matched all 123 GLSL and 123 preprocessed USF
pairs to the captured baseline after only the intended binding merges, slot
renumbering and duplicate declarations. UV/mip and remaining shading calculations
were preserved. All 84 textured shaders still perform 22 material lookups: this
reduces bindings, not sampling work. Each of the three vertex-factory families
has 13 shaders with zero samplers, 8 with 14, 12 with 15 and 8 with 16.
Additional desktop-platform compilation from cloned-MIC parenting was
allowed and recorded separately from the nonpersistent WebGL resource.

This proves the fixed transient candidate compiles under the diagnostic's
no-static-lighting policy. It does not authorize permanent parameter aliases,
static-lighting changes, arbitrary skins, or a claim of browser visual parity.
The focused suite passed ten tests with the private graph evidence; the full
compatibility suite passed 147 tests with 26 explicit optional-evidence skips.
