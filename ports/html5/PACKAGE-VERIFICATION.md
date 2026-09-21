# Verify a private legacy asset package

After the cook and UAT package command have exited successfully, verify the exact
staged bytes and their generated Emscripten `.data` archive:

```sh
python3 ports/html5/verify-package.py /private/output/UnrealTournament.data.js /private/output/UnrealTournament.data /private/stage/HTML5
```

The read-only command parses the packager's literal JSON metadata, requires full
contiguous coverage, checks every slice against its staged file, and emits sizes
and SHA256 hashes. It does not execute the loader. Files outside the stage root,
duplicate paths, missing files, truncation and same-size corruption fail the check.
Keep the generated loader and archive from the same packaging run. Private paths
appear in the report; inspect it before sharing.

Also run the matching engine's `UnrealPak -Test` and inspect `-List` for the required
maps, asset registry, global shader cache and platform configuration. The pinned
legacy UnrealPak returns zero on a healthy `-Test` and one on successful `-List`;
check the actual output as well. Byte equivalence alone cannot establish that the
cook contains the right assets, that shaders compiled correctly, or that gameplay
and map travel work. Keep each archive below the pinned browser filesystem's
supported file-size limit; the current build uses a 32-bit signed file offset.

After transfer, compare the destination archive's full SHA256 with the verified
source. Switch the loader and archive together while no browser is loading them.
Do not replace a converted JS/WASM/memory triple with UAT's original asm.js output.
Run the real browser verification separately. No licensed packages are included
with this checker; its corruption tests use small generated fixtures.
