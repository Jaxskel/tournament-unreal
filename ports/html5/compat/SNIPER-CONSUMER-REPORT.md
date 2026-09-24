# Read-only Sniper consumer report

`SniperConsumerReport` inspects seven fixed packages before choosing a repair for
Sniper materials still reported as browser fallbacks. It loads the weapon and
attachment Blueprints, the first-/third-person meshes and legacy prototype mesh,
and the two original Sniper material instances. It reports existing CDO/SCS
components, effective slots and overrides, parent chains, material parameters and
direct registry referencers. It does not execute Blueprint gameplay, spawn an
actor, change a material, save packages or establish global/live usage closure.

The fixed [specification](report.sniper-consumer.json) and an operator-captured
input manifest are required, each with an explicit SHA1. The manifest schema is
`ut4-sniper-consumer-inputs-v1`, with `read_only: true`, absolute `project` and
`original_project` paths, and `packages` in the specification's exact seven-root
order. Each entry contains `package`, `file`, `original_file`, `sha1`,
`original_sha1`, `sha256`, `original_sha256`, `bytes`, `original_bytes`,
`selected_exists: true` and `original_exists: true`.

Selected and original bytes are independently pinned; equality is not assumed.
The native helper checks both SHA1s and sizes before loading, around each root and
before completion. SHA256 fields are provenance only in native code: the launcher
must independently verify those hashes, physical paths and any additional
protected dependencies. The seven root checks do not certify every dependency.
Ordinary PostLoad can dirty memory; newly dirty packages are reported without
clearing dirtiness or authorizing a save.

Run in a fresh editor commandlet with the matching compiled compat plugin:

```powershell
& $editor $project -run=UT4Html5Compat -Mode=SniperConsumerReport `
  "-SniperSpec=$spec" "-SniperSpecSHA1=$specSha1" `
  "-SniperInputs=$inputs" "-SniperInputsSHA1=$inputsSha1" `
  -nullrhi -unattended -nop4 -stdout -UTF8Output
```

Do not supply `Manifest`, `Receipt` or `NoDependsGathering`. Treat nonzero exit,
partial rows or missing final `COMPAT_SNIPER_CONSUMER` completion as failure.
Validate row schema/run/sequence, the exact seven root identities and two material
identities, zero saves and the completion nonclaims. A successful report does not
prove successful browser shader compilation, runtime assignment or appearance.

Focused checks:

```sh
python3 -B ports/html5/compat/test_sniper_consumer_report.py -v
```

These execute selected predicates compiled on the host and check the fixed scope;
they do not substitute for compiling and executing the complete UE plugin.

## Recorded native run

The revised plugin built against the pinned editor and the fresh read-only run
returned exit 0, 290 records and complete owned-process drain. All seven selected
and seven original root-file hashes remained unchanged. It observed 71 newly
dirty in-memory packages; none was saved or accepted as a normalization.

The first-person weapon CDO resolves body slot 0 to `M_Sniper_Rifle_Inst`; the
attachment CDO resolves slots 0 and 2 to `M_Sniper_Rifle_3P_Inst`. Both material
instances reach the existing HTML5Compat weapon master through their original
Enforcer ancestry. The 1P/3P effective Panini values remain true/false. Separate
emissive, legacy and decal slots are recorded. These are native defaults and
templates, not a live browser weapon draw or a repair. Direct referencers also
include prototype meshes and material variants outside the two selected MICs,
so changing their shared parent is not justified by this report alone.

Private result SHA256: `c1988044d37bb7d320dd4c22d4a664a7e679b4d447d24a23c0e9a316a521597c`;
records SHA256: `ca09a1eab313b3634baa3eb083fb9f1b3a2f95606939313a00da911191571a21`.
The earlier run stopped before its explicit root loads because the specification checker passed
an unsorted expected list to a helper that sorts observed paths. Sorting only the
comparison copy fixes that rejection; the seven-row input order remains strict.
The failed evidence is retained. Seven focused tests now cover that contract.
