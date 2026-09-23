# Fixed Grenade repair transition

This opt-in native operation writes exactly three selected-project packages, in
this order:

1. `/Game/HTML5Compat/Weapons/V1/Grenade/MF_LayerSet_Grenade` (new).
2. `/Game/HTML5Compat/Weapons/V1/Grenade/M_WeaponsBase_Grenade` (new).
3. `/Game/RestrictedAssets/Weapons/GrenadeLauncher/Materials/MIC_Grenade_Launcher`
   (existing 1P instance, parent change only).

The child 3P instance and the other 21 protected current packages retain their
bytes. The shared master, its compatibility functions, original 48 dependencies,
old four success artifacts, recipe, and baseline remain pinned. No normal or
diffuse constant substitution is performed. The new LayerSet has exactly the six
reviewed texture-object parameter-name redirects. Only master call 0 is redirected
to it. The new master disables its own static-lighting usage flag; the shared
master retains its flag. Existing graph UV, mip, arithmetic and switch branches
remain subject to strict comparison.

This specializes the captured fixed defaults. It does not preserve arbitrary
future independent overrides of the six redirected parameter names. Native
shader success is not visual acceptance, a runtime immutability proof, or a
promise about other material/skin assignments. Cook and browser evaluation remain
separate. No existing runtime or default probe mode is changed by this header.

## Integration and admission

Include `WeaponGrenadeRepair.h` inside `UT4Compat`, after the existing alias probe
header. It uses that header's ordinary nonpersistent resource, graph ownership,
interface and full shader-ID comparisons, plus the existing Tess/fidelity/proof
helpers. No new engine includes are required beyond the alias integration's
existing `ShaderCompiler.h` and material headers.

The entry is `WeaponGrenadeRepair(const FString& Params, bool Verify)`. Intended
mode dispatches are `WeaponGrenadeRepairApply` (`false`) and
`WeaponGrenadeRepairVerify` (`true`); the main integration owns their admission.
Both require editor commandlet/game-thread/rendering admission and ordinary
dependency gathering. Fresh processes are required.

Apply mode is a **read-only asset preflight by default**. Only `-GrenadeApply`
enables duplication, reparenting and saves. It first runs the existing full
18-material verifier through the Tess aftermath verifier. Pass that verifier's
existing flags and arguments unchanged, including `-WeaponUV0 -WeaponTess1`,
current proof, Tess receipt, master backup and pinned Tess aftermath. There is no
fallback admission for an already changed 1P parent.

Both modes additionally require:

```text
-GrenadePreparation=<external preparation.json>
-GrenadePreparationSHA1=<exact preparation SHA1>
-GrenadeReceipt=<external three-path receipt.json>
-GrenadeReceiptSHA1=<exact receipt SHA1>
-GrenadeBefore=<external before-semantics.json>
-GrenadeAftermath=<external aftermath.json>
```

Apply requires the last two paths to be absent, even during default preflight.
Explicit Apply reserves both with exclusive creation before graph mutation.
Verify instead requires these files and
`-GrenadeAftermathSHA1=<reviewed aftermath SHA1>`; `-GrenadeApply` is rejected in
Verify. Verify never invokes the old parent/hash verifier or any save operation.

## Preparation contract

`preparation.json` is the generation proof. Schema:
`ut4-grenade-repair-preparation-v1`. Required reference objects all have
`{"path": "<absolute physical external path>", "sha1": "<40 hex>"}`:

- `spec`: the fixed repository `repair.grenade.json`, copied externally if needed;
  SHA1 `2cc1070e4cda8af887c5eeefcf957abf1de6ff71`.
- `current_proof`: the exact original current23 capture.
- `tess_aftermath`: the exact successful one-master aftermath.
- `one_p_beforeimage`: the current selected 1P bytes, SHA1
  `efff00497f03a94f3d0bcd7661bbcd303daa5218`.
- `candidate_approval`: separately reviewed main-authored bridge acceptance.

`rows` contains exactly 23 objects `{package,path,sha1}` matching the selected
current generation in the fixed spec. The shared master is the sole exception
to the older current23 hashes, and must match the pinned Tess aftermath.
`new_destinations` contains exactly the two fixed new `{package,path}` objects.
The prep tool may retain additional SHA256, physical identity, timestamp,
sidecar-presence and provenance fields. Native code does not reinterpret JSON
integer filesystem identities as a replacement for the Python physical checks.

The distinct receipt uses schema `1`, operation `grenade-defaults-v1`,
`manifest_sha1` equal to the **preparation file's SHA1**, selected `project_dir`
and `content_root`, pinned `original_root`, and exactly three `files` entries
`{package,file}`. It grants no authority to the old 23-file write allowlist.
Its own hash is passed separately, avoiding a generation-proof/receipt hash cycle.

The candidate approval uses schema `ut4-grenade-candidate-approval-v1`,
`reviewed:true`, `resources:6`, `valid:6`, `native_exit:0`,
`asset_flag_false:true`, `resource_lighting_override:false`,
`reference_ids_equal:true`, and `pair_log`/`asset_flag_log` reference objects.
These external reviewed facts are mandatory inputs, not a claim that the reader
re-parses or independently certifies the raw shader logs. Do not author approval
from a running or failed bridge. No bridge result hash is invented in this source.

Main must provide the external beforeimage and physical three-path COW receipt,
create the two destinations' empty physical parent separately, and hold exclusive
operational ownership of the selected tree. Prep execution is external-only.
Both new assets must be absent. Path/hash checks are repeated before each save;
they are not an OS transaction or a concurrent-writer lock.

## Mutation and verification boundaries

Before mutation, native code writes the full source graph/property and 18-instance
snapshot under the successful old verifier. The snapshot includes raw override
bags, effective scalar/vector/texture values, static parameters and parent chains.
The child remains parented to 1P, with its distinct Panini switch preserved.
Exactly the six aliased effective texture reads are compared through their
canonical names after reparenting; raw instance override arrays are not rewritten.

Both owned graphs must pass direct owner/input pointer correspondence before any
function updater. Function interfaces are checked by membership and GUID.
Comparison-only exceptions are the new object paths, six parameter names,
master/function StateIds, newly generated master LightingGuid, exact replaced
function dependency identity, new master's static-lighting flag, and the 1P parent.
Typed identities must remain stable. The pinned bool exporter represents false as
a **present empty string**; field type/presence and the actual typed false flag
are checked separately. Missing fields are not accepted as false.

No broad cache/property omission or dirty clearing is used. Protected-package
dirty states must stay equal within each process. Fresh Verify records its own
post-load dirty baseline and compares source graph/parameter semantics to the
before file; dirty flags are not treated as serialized cross-process state.
The intentionally modified 1P package's before/after dirty observations are
recorded separately. Incidental owned/MI shader jobs and DDC writes can occur.

All six 1P/3P × Low/Medium/High WEBGL resources use the ordinary lighting policy
and `IsPersistent=false`. Their complete requested IDs, effective static sets,
new function dependency, shader status, 14 material 2D bindings, zero cube bindings
and at-most-16 sampler count must pass before saving. Failed maps never supply
uniform-array observations. Global/resource jobs must drain before resource
destruction and release of held roots; an undrained failure retains them until
process exit.

After exactly three successful saves, an exclusive aftermath records the 25-file
hash table, clone IDs, before-file hash, preparation/receipt hashes, and bounded
success counts. Fresh Verify requires every protected old hash to match, a changed
1P hash and both new hashes, then loads the exact 25 packages, repeats graph and
all-18 semantic checks, and compiles the same six ordinary resources. It saves zero
assets. Its success is required separately from Apply.

Any partial save, failed flush, or crash remains fail-closed for explicit manual
review. Reserved evidence or partially written assets are never adopted as a new
starting state. There is no automatic rollback, overwrite of existing new assets,
or atomic three-package commit promise.

## Local checks

```sh
python3 -B ports/html5/compat/test_weapon_grenade_repair.py -v
# From the workspace root, including resident private generation evidence:
python3 -B outputs/tournament-ut4/ports/html5/compat/test_weapon_grenade_repair.py \
  --private-root work/ut4-html5 -v
```

The host tests execute extracted control bodies for admission/order, save failures,
table validation, semantic/dirty comparisons, bool export policy, resource drain,
and failed shader-map handling. Engine calls and filesystem writes are simulated.
These tests do not establish UE compile/link compatibility, actual asset
serialization/reload equivalence, race-free saving, cooked output or appearance.
