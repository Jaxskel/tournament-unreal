# Verify the optional startup package

The existing [startup compression guide](STARTUP-COMPRESSION.md) documents the
fixed twelve-entry selection, response preparation and six-run headless comparison.
Its historical median improved from 13.1367 to 12.0100 seconds (8.5767%), with
60,223,598 additional bytes. Those measurements apply to that private generation;
they establish no FPS, cold-network, native-parity or promotion claim. Files were
pre-read by hashing; actual OS-cache residency was not measured.

`selective-startup-pak.py` adds only read-only v3 archive preflight/equivalence.
It reuses the existing `prepare-startup-compression.py` transform and `SELECTED`
tuple. The existing planner remains the only response writer: its default is
read-only, and `--output` explicitly creates a new response. Neither helper cooks,
runs UnrealPak, edits assets, generates data/loaders, or changes default packaging.

## Same-cook workflow

1. Pin a fresh baseline archive/container and its original UAT response from the
   **same cook** as the candidate. Retain the full inventory, matching UnrealPak
   identity, packaging arguments and order file. A repaired cook may add assets;
   the historical 9,173-entry count, hashes and offsets are not new evidence.
2. Run `check-plan` below, then use the existing response helper as documented in
   [STARTUP-COMPRESSION.md](STARTUP-COMPRESSION.md). Require all twelve fixed paths,
   supported original compression, and an exact response inverse. Match the newly
   prepared response hash to the checker’s reported transformed-response hash.
3. Separately build a new private pak with the matching official UnrealPak and
   original reviewed arguments/order file. **Do not add global `-compress`.**
   Response row order is preserved, but it is not proof of archive index order.
4. Run `verify` against the same baseline and original response. It checks actual
   archive index order and full equivalence, not merely UnrealPak exit status.
5. Regenerate the matching data/loader pair, validate every staged slice, and
   measure that coherent candidate before any separate promotion decision.

## Read-only commands

Both commands require caller-reviewed SHA256 pins. The baseline hash covers the
whole file. `--pak-start` and `--pak-length` identify its exact pak slice; defaults
are zero and the remaining file length. For a standalone baseline pak, use zero
and its size. For `.data`, use current loader metadata, including the correct
prefix/suffix boundaries. The candidate is a standalone pak.

These PowerShell examples assume all variables identify reviewed current inputs;
no command computes a hash and silently treats it as approval. `$response` is the
original response, not the transformed one. Commands emit JSON only.

```powershell
$inputs = @('--baseline', $baseline, '--baseline-sha256', $baselineSHA256,
            '--pak-start', "$pakStart", '--pak-length', "$pakLength",
            '--response', $response, '--response-sha256', $responseSHA256)

python -B ports/html5/selective-startup-pak.py check-plan @inputs
if ($LASTEXITCODE) { throw 'Archive preflight failed' }

# After separate response preparation and official UnrealPak packaging:
python -B ports/html5/selective-startup-pak.py verify @inputs `
  --candidate $candidatePak --candidate-sha256 $candidateSHA256
if ($LASTEXITCODE) { throw 'Archive equivalence failed' }
```

`check-plan` requires the response destination **set** to match the baseline
inventory, verifies the existing fixed-twelve transform/inverse, and checks growth
bounds. `verify` repeats preflight, checks mount, entry order/raw sizes, index/local
headers and all actual stored-payload checksums. Selected strict bounded-zlib
decoded bytes must equal candidate plain bytes; unselected stored bytes and
compression framing must match. Unsupported format, method or encryption fails
closed. Input identities/hashes are rechecked; success is not runtime acceptance.

Growth is bounded to 64 MiB, with the full baseline container plus growth strictly
below 2 GiB. Standalone pak input excludes any future `.data` prefix/other files;
check the complete regenerated `.data` size independently. The existing planner’s
JSON and private historical proposal/verification plans are different schemas:
use explicit current inputs, not old plan fields as missing evidence.

## Regenerate a coherent data/loader pair

Use the matching pinned legacy `file_packager` with `--no-heap-copy` from the
current candidate stage, following [BUILD.md](BUILD.md). Run the current
[verify-package.py checks](PACKAGE-VERIFICATION.md) against `.data`, `.data.js`
and every staged slice. Also run matching UnrealPak `-Test` and inspect `-List`
for current required maps, registry, shaders and configuration. Keep all new pins.
Packaging remains separate from the `build-legacy.ps1` compile/link step.

The private `prepare_candidate_data.py` is generation-fixed: old data/loader/pak
hashes, six metadata entries, a 5,396,441-byte prefix and a fixed candidate UUID
basis. It is not a generic fresh-cook integration. Do not reuse its offsets,
identity or receipts blindly. A fresh cook needs new baseline, response, inventory
and selected-entry evidence plus coherently regenerated `.data` and loader.

Only integration source, tests and documentation are public. Licensed engine
source/tools, assets, archives, runtime payloads and private response paths remain
private. Archive equivalence does not authorize serving or promoting a candidate.
