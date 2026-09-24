# Grenade launcher assignment report

`-Mode=WeaponGrenadeAssignmentReport` inspects six fixed original weapon assets:
the Grenade Launcher weapon and attachment Blueprints, their first- and
third-person material instances, and the two skeletal meshes. It reports existing
class defaults, native and Blueprint component templates, assigned meshes and
material slots, material parent chains and static-lighting usage flags.

This is a read-only diagnostic for choosing a faithful material repair. It does
not establish that a material has no other consumers, that a live component has
no overrides, or that the renderer actually selects a particular lighting policy.
It creates no actors, loads no maps, invokes no Blueprint functions and saves no
assets. `GetPickupMeshTemplate` is inspected only for script presence and hash;
the function is never dispatched.

The private fixed spec binds six roots and their 647-package hard dependency set
to a captured registry and source API evidence. Licensed packages, registry
captures and the generation-specific spec remain private. The input receipt must
contain every package fingerprint, explicit logical-to-physical root mappings,
the original six package fingerprints, and the registry/API evidence files.
Unknown mappings, preloaded roots, changed files, new dirty packages, unexpected
loads and exhausted budgets fail the operation. Dirty flags are never cleared.

Run the commandlet in the isolated editor project with its reviewed private inputs:

```text
UE4Editor-Cmd.exe <isolated-project.uproject> -run=UT4Html5Compat
  -Mode=WeaponGrenadeAssignmentReport
  -GrenadeAssignmentSpec=<absolute-forward-slash-spec-path>
  -GrenadeAssignmentInputs=<absolute-forward-slash-inputs-path>
  -GrenadeAssignmentInputsSHA1=<exact-input-file-sha1>
  -GrenadeOriginalContent=<physical-original-project-Content>
  -nullrhi -unattended -nop4 -stdout -UTF8Output
```

Supply the coordinated private DDC graph and log path separately. Do not combine
this mode with a manifest, save receipt or another operation. A successful report
has contiguous `COMPAT_WEAPON_GRENADE_ASSIGNMENT` rows, six unique root rows, and
one final `complete` row reporting unchanged fingerprints and zero assets saved.
Partial rows or a nonzero exit are incomplete evidence. On failure the native
report does not promise a final full fingerprint pass; the private runner repeats
the external input capture even after native failure and retains both results.

Local checks:

```sh
python3 -B ports/html5/compat/test_weapon_grenade_assignment_report.py -v
# With the matching private evidence available:
python3 -B ports/html5/compat/test_weapon_grenade_assignment_report.py \
  --private-spec <fixed-spec-v1.json> -v
```

The host tests exercise extracted methods with stand-ins; the private test also
rederives the exact dependency set and source pins. They do not simulate UE
PostLoad or prove that all editor-only dependencies are in the cooked registry.
The integrated native module compiled and linked successfully in the selected
UE4 editor build (three actions, 14.89 seconds). The first native query exited 1
after loading the weapon Blueprint: it observed 35 packages outside the cooked
registry's admitted set and additional clean-to-dirty transitions in memory. It
produced no successful terminal row or component-assignment result. A cooked
registry alone therefore does not cover this editor load.

The external before/after capture matched all 659 observed files and 186 root
mappings, and all 11 fixed helper/configuration pins matched. This proves those
captured inputs stayed unchanged; it is not a before/after proof for the newly
discovered packages. A revised dependency manifest and explicit treatment of
PostLoad changes need review before another run. No guard was relaxed by this
first-run result. Material repair, shader cook and gameplay appearance remain
separate checks.

## Qualified post-load observation

The opt-in `-GrenadePostLoadDefaultsDiagnostic` stops the normal load loop after
its first Blueprint load and observes only already-loaded fixed objects. It uses
existing class defaults and stored component templates, never resolves effective
SCS templates through the engine's potentially loading accessor, and records
unavailable observations explicitly. Unknown dependencies and dirty transitions
remain failures; no whitelist or dirty baseline is extended.

Rows collected by this branch have `diagnostic_` kinds and explicitly deny repair
authority. Its `diagnostic_end` can describe a partial capture. The branch always
returns **exit 1** and never emits the strict `complete` record, even if all six
post-load roots are observed. Recorded file hashes are checked separately from
dirty-state failure. Object/package checks establish stability only for objects
visible to the engine iterator; unreachable and background-loading objects are
excluded by that API. No universal absence of allocation, property changes, or
runtime consumers is claimed. A diagnostic terminal is useful evidence for the
next investigation, not approval to save or promote a material repair.

The qualified branch subsequently compiled in the native editor module (three
actions, 14.06 seconds). Its native run returned the required exit 1 and captured
all six roots, with zero unavailable observations and no strict `complete` row.
The existing first-person weapon Mesh and third-person attachment Mesh were
skeletal components. Their body slots resolved to the expected first- and
third-person Grenade Launcher material instances, with no slot-zero override in
those observed defaults. The third-person instance inherited from the first-person
instance. The pickup function had native code and no Blueprint script in the
observed function record; it was not executed.

All 659 externally captured file observations and 11 fixed input pins remained
unchanged. Unknown-load and dirty-state failures remained present, so this is
qualified default-assignment evidence, not strict load admission, a live pickup
test, or global material-use closure. No asset was saved or promoted.
