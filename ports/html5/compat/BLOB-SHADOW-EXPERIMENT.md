# One-material blob-shadow diagnostic

This is an explicitly acknowledged experiment, **not a native appearance fix**.
It reconstructs an approximate geometric receiver normal from the existing
HTML5 alpha-copy depth using derivatives. Half-float depth quantization, depth
edges and missing normal-map detail remain limitations. Shader link success alone
does not establish acceptable appearance.

Only `/Game/RestrictedAssets/Effects/Nick/M_Robust_BlobShadow` may be saved, as a
physical isolated COW file. The original source file, inverse MIC, miniCylinder,
BaseUTCharacter, all meshes and component transforms remain untouched. There are
no redirects, hidden-proxy substitutions, shader-library patches or raw primary
depth sampling.

The graph change appends four expressions: FeatureLevelSwitch, Custom, SceneDepth,
CameraVectorWS. Only `ComponentMask_4.Input.Expression` changes. Its original
output index and all-RGBA mask are retained; the switch Default copies the exact
original WorldNormal pin. ES2 selects a **float4** custom result so that mask stays
valid, and the existing RGB ComponentMask retains both native opacity and UV-scale
consumers. A connected SceneDepth input registers the compiler dependency; the
custom code uses that input and does not hide an untracked texture sample.
The pinned SceneDepth/CameraVectorWS classes have `NO_API` generated entry points.
The helper looks up their exact `/Script/Engine` classes, creates them through
exported `UMaterialExpression`, validates the class identity, and only then
accesses SceneDepth's public fields; it does not call their unexported StaticClass.

All old graph nodes, roots (including WPO), textures, parameters and inverse MIC
values must match the pinned native baseline. Intentional material-property
exceptions are full pixel precision and regenerated StateId/LightingGuid; the
latter are ordinary pinned PostEditChange behavior. The four appended expressions
and changed input are recorded in the aftermath receipt. Known load-dirty is
accepted only by this new diagnostic operation after exact native graph/property/
parameter and pristine source/target hash comparisons. No dirty flag is cleared;
existing report and repair modes are unchanged.

## Preparation and commands (main operator only, after review)

Compile the compat plugin against the pinned editor first. The recorded native
Apply and fresh-process Verify below establish the bounded asset operation; they
do not establish acceptable browser appearance.
Prepare exactly one physical COW target with all ancestors free of reparse points
and the target singly linked. Preserve the pristine source hash. Do not write
through the current Content/subdirectory junction. The existing generic
`prepare_cow.py` does not accept this experiment recipe; use a separately reviewed
one-file preparation and receipt. No installation-wide copy is needed.

The private baseline is `work/ut4-html5/blob-shadow-review/experiment-baseline.json`,
SHA1 `3b5702d33380ea7ae18746067594d51634da8500`, extracted from the two blob material
records in the pristine native Fidelity report. Keep it private. The public spec
pins its bytes and source package hashes; it contains no copied engine code.

The COW receipt uses the existing schema1 policy: `manifest_sha1` is the hash of
`experiment.blob-shadow.json`, `project_dir` and `content_root` identify the
isolated project, `original_root` identifies the protected original source root,
and `files` contains exactly one `{package,file}` pair for the primary material.
All paths are absolute. `BlobOriginalFile` must be the original primary file
inside that protected root; it is read/hash-checked only.

Run each action in a **fresh editor commandlet process**:

```powershell
$common = @(
  $project, '-run=UT4Html5Compat', '-Mode=BlobShadowExperiment',
  "-BlobExperimentSpec=$spec", "-BlobBaseline=$privateBaseline",
  "-Receipt=$cowReceipt", "-BlobOriginalFile=$originalPrimary",
  '-unattended', '-nop4'
)
& $editor @common -BlobAction=Report
& $editor @common -BlobAction=Apply -AllowCommandletRendering -AcknowledgeApproximateBlobNormal "-BlobAftermath=$newReceipt"
& $editor @common -BlobAction=Verify "-BlobAftermath=$newReceipt"
```

Create the aftermath directory beforehand; the Apply receipt filename must not
exist and must be outside Content and the original root. Apply saves only after
all comparisons and a final physical/hash preflight. The receipt records baseline,
source/target hashes, original roots/input mask, added expressions, GUID changes,
full precision and explicit `promotion_allowed:false`. Verify requires that exact
saved target hash and matching added-expression state. Report/Verify save nothing.
If saving succeeds but receipt writing fails, the command fails: preserve the
logs and do not promote. There is no automatic rollback. Recover only the selected
physical COW file from the audited original and rerun in a new process.

## Required aftermath before considering acceptance

Use a fresh private shader-cache/cook generation and a coherent private runtime/
package pair, coordinated with the GPU/weapon experiments. Inspect the actual
ES2 shader for the selected branch, `GL_OES_standard_derivatives`, full-precision
reconstruction, expected alpha-copy dependency, sampler limits and no fallback.
The pinned GLSL backend supports derivative emission; the existing game glue
enables the extension. Those source facts do not prove this shader compiles.

Compare native/default and experimental visuals on flat floor, slopes, floor/wall
edges, thin foreground occluders and moving feet at 1080/1440. Require actual
shadow draws, absence of solid/checkerboard cylinders, unchanged inverse mirroring,
no GL errors and acceptable edge/precision artifacts. Check the default SM4/SM5
branch independently. Record frame pacing for the same workload without assuming
an improvement. Failed visual comparison keeps this candidate experimental even
when Apply/Verify and shader linking pass.

Local focused checks:

```sh
python3 -B ports/html5/compat/test_blob_shadow_experiment.py --private-baseline /absolute/private/experiment-baseline.json -v
```

These include the actual original Custom body compiled on the host with explicit
helper/derivative stubs, the actual mask predicate, native baseline and wiring/
safety contracts. They are not a UE plugin build, HLSLcc compile or browser test.

## Recorded native operation

The private `blob-experiment-apply-3` and `blob-experiment-verify-1` runs on
2026-09-22 both returned native exit 0. Apply saved only the isolated primary
material; Verify saved nothing and reported the same target SHA1
`1a7457dadd880d552260cd1fe3394616852f0c49`. The original source SHA1 remained
`ef06feed570aab971fccd20c32edaf230a6c95bd`. Their result-file SHA256 values are
`0b9aa018729fa8545fc78a6739c13b6ae29ae693a86c33555c6d640a363811e0`
and `4c49ac6a82d781d3cf3c5bc9974303a2c7793b400c57276481378d92734cf0ab`.

These are historical native operation receipts, not a current shader/draw or
visual-parity certificate. The appearance checks above remain required; the
receiver-normal approximation is still experimental. Private logs and assets are
not distributed with this repository.
