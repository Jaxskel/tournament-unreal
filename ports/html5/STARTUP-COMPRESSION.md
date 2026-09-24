# Optional startup package compression experiment

`prepare-startup-compression.py` prepares a new UnrealPak response file that stores
twelve fixed texture packages without zlib compression. It preserves the texture
payloads, including their mip data, and changes no engine or asset source. The
default command only prints a plan; `--output` exclusively creates a new response.
The helper never runs UnrealPak, cooks assets, or installs a runtime.

## Measured private comparison

On the tested private generation, all 9,173 pak entries passed inventory, local
header and stored-checksum checks. Every unselected compressed payload and
relative compression-block layout was identical. The twelve selected entries
were decoded and matched the new uncompressed payloads byte for byte. The new pak
was 60,223,598 bytes (57.43 MiB) larger. These checks were performed separately;
the response helper does not implement archive verification.

The separate [archive verification workflow](STARTUP-PACKAGING.md) now provides
read-only preflight and payload-equivalence checks for this fixed selection.

Six fresh headless Chrome runs used the same runtime, client, initial map and
1920×1080 viewport, alternating baseline/candidate in the order B,C,C,B,B,C.
Launch-to-observed native Ready times were:

| Package | Runs, seconds | Median, seconds |
| --- | --- | --- |
| Baseline | 13.7044, 13.1239, 13.1367 | 13.1367 |
| Twelve entries uncompressed | 12.1697, 11.9363, 12.0100 | 12.0100 |

The candidate reduced the median by **1.1267 seconds (8.58%)** in this comparison.
Timing ended at the first animation-frame sample reporting native Ready after the
trusted iframe `postRun` message. All six owned browsers exited cleanly. Input
hash checks pre-read the files; this is not a cold-disk or network-download test.
It does not establish gameplay FPS, GPU time, visual parity or a benefit on other
machines. The larger download is a tradeoff. Neither public/canonical runtime was
replaced by this experiment.

## Current scene-color generation comparison

The same fixed selection was rebuilt against the newer scene-color cook and
pending-startup runtime. This is a separate experiment: all **9,179 entries**
passed actual archive equivalence, including the twelve decoded texture
payloads and the other 9,167 stored payloads/compression layouts. The matching
legacy packager generated a new data/loader pair, and all six data slices matched
the private staging files. Engine source, cooked assets and playable preview
were unchanged.

Six fresh headless Chrome launches again used B,C,C,B,B,C, identical runtime,
client, manifest and 1080p startup settings:

| Package | Runs, seconds | Median, seconds |
| --- | --- | --- |
| Current baseline | 16.4789, 14.6627, 14.5688 | 14.6627 |
| Twelve entries uncompressed | 13.6107, 14.2513, 14.2094 | 14.2094 |

The measured median reduction was **0.4533 seconds (3.09%)**, while the data file
increased from 1,874,318,212 to 1,934,541,810 bytes: **60,223,598 additional bytes**.
All six browsers exited cleanly; input pins were rechecked after the comparison.
This smaller local benefit does not justify a default change without considering
the larger download. The candidate remains **optional and unpromoted**. The
historical 8.58% result must not be presented as the newer generation's result.
The same pre-read, headless and first-observed-Ready limitations above apply;
this is not a cold-network, visual-fidelity or gameplay-FPS measurement.

Private evidence SHA-256:

- Package result: `66d7abf81e826fe7fa83f541e941428373d851fb4fe2228218d74934121f8ae9`.
- Archive equivalence: `675ec204a5078ebbef100303f4c48e8b9e18a5cae81c258fe99dc3f8b5265a72`.
- Six-run report: `477726a27aa735bb7491a1bf292364e445fc8e036f10634c24dc0f75e85cb06f`.
- Candidate data: `8f00094304caa411c5ae067ca28330ca766e76e92442be9cb2e5687331d833bb`.

## Prepare a response

Use the matching engine's response generated for the intended cooked generation.
Review its SHA256 first. The helper requires all twelve fixed entries, unique
source/destination paths, canonical quoted paths and supported flags. Missing or
already-uncompressed selected entries fail; it does not silently select a subset.

```powershell
$inputResponse = 'F:\private\paklist.txt'
$inputHash = (Get-FileHash -LiteralPath $inputResponse -Algorithm SHA256).Hash
python -B ports/html5/prepare-startup-compression.py --input $inputResponse --input-sha256 $inputHash
if ($LASTEXITCODE) { throw 'Response preflight failed' }

# Explicit opt-in; this path must not already exist.
python -B ports/html5/prepare-startup-compression.py --input $inputResponse --input-sha256 $inputHash --output 'F:\private\paklist-startup.txt'
if ($LASTEXITCODE) { throw 'Response preparation failed' }
```

UTF-8 BOM, LF/CRLF, row order and all bytes outside the twelve `-compress`
removals are preserved. Each removed span includes one preceding separator byte.
The helper checks that reinserting those spans restores the exact input bytes.
Only `-compress` and `-encrypt` row flags are accepted; other flags fail rather
than being guessed. Existing output files, including links, are refused. On an
output I/O failure a partial new response may remain; it is never overwritten.

Build a **new private pak** with the matching UnrealPak and this response, keeping
the original ordering and other packaging arguments. **Do not add a global
`-compress` argument:** that would recompress the selected entries. Preserve the
original response, pak, logs, tool hash and full command. No source asset is copied
or changed by response preparation.

Before use, independently verify the pak's full entry inventory, checksums,
decoded payload equality, and unchanged unselected compression; an UnrealPak
health check alone does not prove equivalence to the original archive. Regenerate
the matching `file_packager` data/loader pair in a new output location, then use
the [package verification](PACKAGE-VERIFICATION.md) checks. That verifier compares
data slices with staged files; it does not replace decoded pak comparison.
Benchmark the coherent candidate generation before deciding whether its startup
benefit justifies the larger package. The helper reports
`archive_equivalence_verified: false` and `promotion: false` deliberately.

## Validation

```sh
python3 -B ports/html5/test_prepare_startup_compression.py -v
```

Synthetic tests cover strict paths/flags, duplicates, bounds, drift, exclusive
output, exact inverse and newline preservation. A private optional
`--private-response <path>` test checks the original 9,173-entry experiment:
input SHA256 `d59ff9ea7f05bf14ca18df26b98d55e98d56fbba03fe8f0b47ad4c0814b80cf8`
must produce `f2cd2c85d0598bbe5a1265b5f04ac6837fee00f83912c297d1ab4a5108aecc8a`.
No licensed engine, response paths or asset payloads are distributed here.
