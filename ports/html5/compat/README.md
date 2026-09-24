# UT4 UE4.15 HTML5 material compatibility tools

The [weapon shader and usage diagnostics](WEAPON-SHADER-DIAGNOSTICS.md) document the separate fixed-scope compilation counterfactual and materials-only usage cohort. Neither diagnostic authorizes an asset repair.

The [Enforcer consumer report](ENFORCER-CONSUMER-REPORT.md) records a fixed-seven-package, read-only native query and its evidence limits; it authorizes no asset repair.

The [Bio Rifle body and grenade-ammunition candidate](SUPPLEMENT-MATERIAL-CANDIDATE.md) compiles twelve ordinary shader resources from transient copies while checking the original material parameters and parent chains. It saves no assets and excludes Bio glass.

Original editor-only plugin and bounded copy-on-write preparation. No engine source
is bundled. The editor plugin now compiles against the isolated UT4 source, and Report has run on the recovered Malcolm and weapon assets. Twelve Python preparation tests pass. Apply/Verify and full browser appearance are tracked separately in the parent verification record.

## Fast path: compile and report first

Transfer this directory to, for example, `F:\TournamentUT4\tools\compat`. All commands
below are **for the main agent/operator**, not actions already performed.

Copy only `UT4Html5Compat` into the isolated project's physical
`F:\TournamentUT4\browser-port\UnrealTournament\Plugins` directory. Do not copy
anything into its junctioned `Content`. Use a new plugin destination or coordinate
updates to an existing version. The descriptor enables an `Editor` module; do not
change it to `EditorNoCommandlet`.

From PowerShell, build with the existing isolated engine/toolchain:

```powershell
$port = 'F:\TournamentUT4\browser-port'
$compat = 'F:\TournamentUT4\tools\compat'
$project = "$port\UnrealTournament\UnrealTournament.uproject"
$editor = "$port\Engine\Binaries\Win64\UE4Editor-Cmd.exe"
& "$port\Engine\Build\BatchFiles\Build.bat" UnrealTournamentEditor Win64 Development $project -WaitMutex -NoHotReloadFromIDE
if ($LASTEXITCODE) { throw 'Editor/plugin build failed' }
& $editor $project -run=UT4Html5Compat -Mode=Report "-Manifest=$compat\manifest.robot.json" -NullRHI -unattended -nop4 -stdout
if ($LASTEXITCODE) { throw 'Report failed; inspect the log' }
```

Apply requires `-AllowCommandletRendering` and must omit `-NullRHI`: this engine leaves new material render resources null under NullRHI, so editor material changes can crash. Report and fresh Verify may still use NullRHI.

Report does not save assets or register Robot redirects. Normal editor startup may
write logs/DDC and initiate shader work. `COMPAT_REPORT` lines contain compact JSON:
mesh slots, material class, base material, effective texture parameter names/values,
and base graph textures including nested material functions. The latter are graph
candidates, **not proof of textures used by a compiled ES2 permutation**. Broken
Robot import warnings in this initial report are expected.

The supplied manifest lists existing `malcolm_3p`, `malcolm_1p`, `Enforcer_1p`, and
`Enforcer_3p` package filenames. Their mesh classes/slots remain runtime-unverified.
Override them without changing the manifest using one quoted argument:

```powershell
"-Meshes=/Game/path/SkeletalMesh.SkeletalMesh;/Game/path/Weapon.Weapon"
```

This reports asset-level skeletal/static mesh slots. It does not enumerate Blueprint
component overrides or materials swapped by gameplay. Confirm those separately in
the Deck runtime test. Missing/non-mesh inputs and null slots produce a nonzero exit.

## Choose a small manifest

`manifest.robot.json` defaults to **only three Robot repairs**, never appearance
replacement. `manifest.browser-surfaces.json` additionally selects 18 weapon surface instances with explicit, Report-verified `OverlayMap` textures. It replaces their unsupported layered shading with a simple lit textured surface in private copies; its appearance remains subject to browser review. Make a separate manifest from it after reading the report. The seven
old texture package names are hard-coded exact mappings from
`/Game/EpicInternal/Character/86D_Robot/Textures/` to
`/Game/RestrictedAssets/Character/Robot/Textures/`: Head AO/M/N, Legs AO/M/N, Visor D.
They are registered only inside Apply, before this commandlet loads any assets.

For a selected direct `UMaterial`, add an entry shaped like this, replacing the
example texture/parameter with **actual Report output**:

```json
{
  "package": "/Game/RestrictedAssets/Character/Malcom_New/Materials/M_Malcom_Body",
  "operation": "fallback_textured",
  "diffuse_texture": "/Game/path/ActualDiffuse.ActualDiffuse",
  "source_parameter": "ActualDiffuseParameterFromReport",
  "tint": [1, 1, 1],
  "shading": "default_lit"
}
```

`diffuse_texture` is mandatory and explicitly selects a Texture2D. Optional
`source_parameter` is an assertion: before editing it must resolve on the selected
material to that exact texture. Omit it for a direct, non-parameterized texture.
The generated graph retains that parameter name, or uses `CompatDiffuse`.

For a `MaterialInstanceConstant` also specify a unique new parent, for example
`"fallback_parent": "/Game/HTML5Compat/M_Enforcer1P"`. Direct `UMaterial` entries
must omit it. The instance retains its existing package/object name. The parent is
also included in the physical save allowlist. Existing parents are never overwritten.
Do not select `M_WeaponsBase` to fix a few weapons; select the actual instances.

The fallback graph is an opaque surface with one diffuse sample multiplied by
`CompatTint`, roughness 0.7, metallic 0, no WPO/opacity mask, and skeletal usage.
`default_lit` is the default. Explicit `"shading": "unlit"` connects the texture
to emissive instead. Material-instance static parameters and base-property overrides
are reset. This intentionally drops complex overlays, transparency and team-color
logic; select ordinary body/weapon surface slots, not power-up effects. Revalidate
gameplay material swaps and team identification. It changes only manifest packages
and generated parents in the private overlay, but any other assets referencing the
same selected material will observe that private change.

For a temporary visibility diagnostic only, use `"operation":
"fallback_color_experimental"`, `"experimental": true`, and a nonblack `tint`, with
no diffuse/source parameter. It always uses unlit color. **This is not the default
game appearance.** No color fallback is enabled in the shipped manifest.

## Prepare private copies, then Apply and fresh Verify

Finalize the manifest before preparation: the receipt binds its SHA-1 and exact save
allowlist. Keep the manifest unchanged for Apply/Verify. Preparation is planning-only
unless `--execute` is present, and refuses relevant active editor/build processes.
It never terminates processes or starts compilers.

```powershell
$manifest = "$compat\manifest.robot.json" # Or your finalized selected-material manifest
$cowArgs = @(
  '--project', $project,
  '--isolated-root', $port,
  '--original-root', 'F:\TournamentUT4\source\UnrealTournament-clean-master',
  '--manifest', $manifest
)
# Plan first. In-place is the smallest setup for the already matching game binaries.
py -3 "$compat\prepare_cow.py" @cowArgs --mode inplace
# Execute only after inspecting the plan and with editors/cookers stopped.
py -3 "$compat\prepare_cow.py" @cowArgs --mode inplace --execute
if ($LASTEXITCODE) { throw 'COW preparation failed; inspect any staging tree' }
$receipt = "$port\UnrealTournament\html5-compat-cow.json"
& $editor $project -run=UT4Html5Compat -Mode=Apply "-Manifest=$manifest" "-Receipt=$receipt" -AllowCommandletRendering -unattended -nop4 -stdout
if ($LASTEXITCODE) { throw 'Apply failed; inspect partial private outputs before retrying' }
# This MUST be a new editor process, with no persistent Robot redirects configured.
& $editor $project -run=UT4Html5Compat -Mode=Verify "-Manifest=$manifest" "-Receipt=$receipt" -NullRHI -unattended -nop4 -stdout
if ($LASTEXITCODE) { throw 'Verify failed' }
py -3 "$compat\prepare_cow.py" --audit $receipt
```

An identical already-installed compatibility plugin is preserved, including binaries.
A differing source version fails closed. In-place preparation requires the real
`.tournament-browser-port` marker and verifies `Content` is specifically a directory
junction resolving under the declared original root. It prepares a sibling tree,
renames **the junction itself** to `Content.compat-original-junction`, then moves the
private tree into `Content`. The target directory is never moved or modified.

Alternatively, leave the isolated project's junction untouched:

```powershell
py -3 "$compat\prepare_cow.py" @cowArgs --mode shadow --shadow-project-dir 'F:\TournamentUT4\work\html5-compat\UnrealTournament'
py -3 "$compat\prepare_cow.py" @cowArgs --mode shadow --shadow-project-dir 'F:\TournamentUT4\work\html5-compat\UnrealTournament' --execute
```

Then set `$project` and `$receipt` to that shadow directory and use the same isolated
`$editor`. Shadow mode copies the same-named `.uproject` and existing Config, Source,
Binaries, Build, and Plugins, preserving matching binaries/configuration; Saved and
Intermediate start private. Build the plugin against this project if not already
copied built. Nested reparse points in support trees fail closed. The default total
copy budget is 2048 MiB, adjustable with `--max-copy-mib` after inspection. The engine
and bulk Content are not duplicated.

Both modes expand only selected content ancestors, copy loose sibling files, and
junction untouched directory subtrees for reading. No hardlinks are created.
Allowlisted package destinations and all their ancestors must be physical; the
commandlet additionally checks existing destination files have one link and that
package resolution matches the receipt. Saving rejects the original root and any
unallowlisted package. There is no save-all or redirector-fixup sweep.

Run no other editor or filesystem mutator against the overlay during Apply/Verify.
The commandlet rechecks each save but does not provide cross-process filesystem
locking. Apply preflights everything before mutation, but multiple package saves
are not a transaction. A failed save can leave partial **private** results. Existing
fallback parents make a repeated Apply fail rather than overwrite uncertain state.

Preparation never overwrites an existing overlay/receipt/staging tree. To change
the manifest, make a fresh shadow project, or after stopping consumers move the
physical in-place Content aside and rename `Content.compat-original-junction` back
to `Content`; preserve/inspect the old receipt and plugin version. Never recursively
delete an unfamiliar tree containing junctions. There is deliberately no automatic
recursive cleanup, source resave, or restore/delete operation.

## What Verify proves

- Robot target texture references are present and no old Robot package imports remain.
- Fallback parent, texture, tint, opaque surface, skeletal usage, and graph shape match.
- Selected saves remain under physical allowlisted paths; separate `--audit` checks
  hashes of copied source files and untouched copied siblings.
- A new process was used for selected-package loading; configured legacy Robot
  redirects are rejected. Do not add another plugin that registers those redirects.

It does **not** prove GLSL compilation, sampler count, complete cook coverage,
skinning, frame rate, or browser visibility. Follow with a targeted HTML5 cook and
Deck test of animated Malcolm, first-/third-person weapons and gameplay overrides.
The engine's separate fragment-only 16-sampler/version-62 patch is not included here.

## Validation and source API references

Run local tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ports/html5/compat -p 'test_*.py' -v`.
The tests exercise manifest restrictions, sparse traversal, symlink/hardlink rejection,
independent copies, and unchanged-source/sibling audits. Windows junction swap and
Unreal compilation/runtime remain untested until the main agent runs them.

Source-checked against `F:\TournamentUT4\browser-port\Engine\Source\`:

- `Runtime/CoreUObject/Public/UObject/LinkerLoad.h:164` and private `LinkerLoad.cpp:1736`:
  exact-package import remapping through legacy `AddGameNameRedirect` in editor builds.
- `Runtime/CoreUObject/Public/UObject/Package.h:520`: filename-based `SavePackage`.
- `Runtime/Engine/Classes/Materials/Material.h:1050,1370`: texture parameter names and
  editable material-property inputs.
- `Runtime/Engine/Classes/Materials/MaterialInstanceConstant.h:44,52,54,61` and
  `MaterialInstance.h:343`: editor setters and static/base-override updates.
- `Runtime/Engine/Public/MaterialShared.h:1776`: material update context.
- `Runtime/Engine/Classes/Materials/MaterialFunction.h:60`: nested expression traversal.
- `Runtime/Projects/Private/ModuleDescriptor.cpp:365`: Editor modules run in commandlets.

UE4.15 `TargetInfo` module rules and direct material-expression APIs are used; no
modern Python editor subsystem, `FSavePackageArgs`, or `FCoreRedirects` dependency.

## First five combat parents: read-only MaterialReport

The new `-Mode=MaterialReport` is a separate reporting path. It cannot use an Apply
manifest or COW receipt. Its native allowlist accepts exactly the five parents and
six variants in `report.materials-first5.json`: UDamage Glass, Skin, Overlay; Link
BeamMaterial and projectile Core; Skin/Overlay 1P, three beam instances and Core_Inst.
It adds no repair operation and does not prepare or save content. **The native module now builds and the read-only report has completed for all
11 licensed targets (exit 0, 0 errors, 3 warnings).** Preflight remains blocked by
five parent packages marked dirty in memory; no assets were saved. The COW audit
passes. Local tests cover the report contract, not Unreal shader compilation.

After main coordinates the UniformBuffer build and a safe editor window, transfer
these local plugin source changes and report tools to the existing isolated tooling
location. Do not replace source during another build. The following commands were exercised for the native build/report; they do not
constitute a successful repair preflight:

```powershell
$port = 'F:\TournamentUT4\browser-port'
$compat = 'F:\TournamentUT4\integration\ports\html5\compat' # Place the updated tools here first
$project = "$port\UnrealTournament\UnrealTournament.uproject"
$editor = "$port\Engine\Binaries\Win64\UE4Editor-Cmd.exe"
# Coordinate copying only the updated plugin source into the existing project plugin.
# Do not run prepare_cow.py: this report does not change the existing overlay/receipt.
$env:TOURNAMENT_UT4_UCRT_VERSION = '10.0.10240.0'
& "$port\Engine\Build\BatchFiles\Build.bat" UnrealTournamentEditor Win64 Development $project -Module UT4Html5Compat -NoUBTMakefiles -WaitMutex -NoHotReload -2015
if ($LASTEXITCODE) { throw 'MaterialReport module build failed' }
$log = 'F:\TournamentUT4\work\material-first5-report-1.log'
& $editor $project -run=UT4Html5Compat -Mode=MaterialReport "-ReportSpec=$compat\report.materials-first5.json" -NullRHI -unattended -nop4 -stdout "-abslog=$log"
if ($LASTEXITCODE) { throw 'MaterialReport failed; preserve log, do not continue to repair' }
py -3 "$compat\material_preflight.py" --report-log $log --out 'F:\TournamentUT4\work\material-first5-review-1.json'
if ($LASTEXITCODE) { throw 'Material preflight evidence differs or is incomplete; inspect native log' }
```

Use a fresh process for a second report and a fresh filename. After reviewing the first snapshot, compare the second with
`--baseline F:\TournamentUT4\work\material-first5-review-1.json`. Any drift in graph,
outputs/channel masks, constants, parameters, raw overrides, function/package
hashes, parent chain or referencers fails. Existing output files are never replaced.
Snapshots always say `apply_ready: false`; there is no automatic baseline approval.
The parser rejects missing completion, unexpected targets, dirty loaded packages,
missing override/mask evidence and known-edge/class/blend/parent disagreements.
Keep the native log even if validation fails; it contains the unexpected facts.

Native evidence includes:

- Every selected direct graph node and nested function graph, node class/owner,
  named input with ordinal, output index and all five mask fields. Reflected
  non-transient properties include constants, mip settings, function-call
  input/output GUID mappings and material flags; these are native text, not edits.
- Effective native blend/shading/two-sided/mask-clip getters, parent chains,
  effective scalar/vector/texture values, raw instance scalar/vector/texture/font
  and base-property overrides, plus separate static override/effective sets.
  RGBA values remain unclamped, including Skin's reported alpha 50.
- SHA-1 of the actual resolved selected/parent/function package files. The prior
  private SHA-256 entries in the spec are provenance only and are **not compared**
  to SHA-1. Before a future Apply plan, separately reconcile those source snapshots
  and pin the reviewed native package hashes. Core_Inst has no prior snapshot.
- Synchronous AssetRegistry scan followed by direct/transitive package referencers,
  without loading those dependents or expanding a save allowlist. Runtime string
  lookups, dynamic material instances and gameplay swaps require separate checks.
  `-NoDependsGathering` and selected packages absent from the on-disk registry are rejected.
  Graph/dependency budget exhaustion fails; it never reports truncated success.

The review must resolve these exact branch decisions before anyone adds Apply:

| Parent | Candidate boundary | Required preserved evidence |
|---|---|---|
| UDamage Glass | Emissive Lerp_7 → existing B/ParticleColor on ES2 | Native A/B pins/masks; translucent/unlit; Opacity Multiply_2; inspect refraction/depth-fade remaining reachability. |
| UDamage Skin | WPO Add_0 → existing A/Panini on ES2 | Function identity and call input/output GUIDs; bypass only B distortion; additive/unlit; Skin_1P overrides including unclamped Effect Color alpha. |
| UDamage Overlay | ES2 emissive → existing Color parameter | Verify actual Color node/value, opacity Constant_0 = 0.2, Panini/offset branch and Overlay_1P overrides; simplified appearance requires review. |
| Link BeamMaterial | WPO Add_0 → existing B projection on ES2; inspect WorldDisplacement too | A displacement versus B/Panini pin proof; preserve pixel samples; Inst_Translucent inherits through Inst2 and must retain its different blend. |
| Link Core | ES2 WPO zero only | WPO Multiply_8, ParticleColor opacity output mask, shared pixel noise samples untouched; first native Core_Inst lineage/overrides/effective settings still need review. |

The initial spec asserts only edges/classes/lineages already observed and provisional
native blend expectations. Output indices, channel masks, function input values,
remaining unsupported paths and all extra dependents need review from the first
native report before producing exact mutation assertions. No missing evidence is
filled with invented pin values. The existing opaque `fallback_textured` operation
must not be used for this batch. No assets were saved and no COW expansion, cook or browser verification was
performed. Native build and report results are described above.

Pinned source API checks: `MaterialExpression.h:244–246`, `MaterialExpressionIO.h:14–34`,
`MaterialExpressionMaterialFunctionCall.h:86–92`, `Material.h:1048–1049,1370`,
`MaterialInterface.h:580–583`, `MaterialInstance.h:180,199–217,381`,
`StaticParameterSet.h`, `IAssetRegistry.h:133,191`, and `UnrealType.h:311–313`.

Local verification for this addition: 27 compat tests pass (15 report/preflight tests,
including the actual MRPin C++ body against minimal data-container stubs, plus the
12 existing COW tests). Native compilation/reporting is separately observed; this
does not establish a passing shader permutation or visual correctness.

For diagnosis only, `-TraceDirty` adds an observer to MaterialReport. It is off by
default, records at most the first dirty-event stack for each of the 11 selected
packages, and records whether the event occurs during loading or description.
The delegate is removed on return; the observer never clears flags or saves.
`COMPAT_MATERIAL_DIRTY` lines are separate from the report contract. The
`package_dirty_before_description` field distinguishes loading from report getters.
The strict dirty-package preflight rejection remains in force.

Observed on the isolated native run: all five parents' first clean-to-dirty events
occurred during `LoadObject`, through `FLinkerLoad::CreateExport` →
`FObjectInitializer::PostConstructInit` → `UMaterialExpression::PostInitProperties`
→ `UObjectBaseUtility::MarkPackageDirty`. The pinned `MaterialExpressions.cpp:506`
calls `UpdateMaterialExpressionGuid(false, true)`; lines 915–929 generate a new
GUID when the current GUID is invalid and permit dirty marking. This construction-time event does not prove a
persisted GUID is missing, and observing only the first event cannot exclude later
fixups. All six instances remained clean. The observer rebuild and report exited 0;
post-run COW audit passed. Preflight still exited 1 without creating an accepted
baseline. Material facts and package hashes matched the run without the observer.

Disconnected native function inputs may have `OutputIndex = INDEX_NONE (-1)`
(`MaterialExpressions.cpp:8316`). Only disconnected -1 is accepted; connected
negative indices and values below -1 are rejected.
