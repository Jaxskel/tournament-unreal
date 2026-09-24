# Browser pending-startup log experiment

`patch-browser-pending-startup.py` is a read-only-by-default, exact one-file
UE4.15 source patch. `--apply` is explicit and accepts only the pinned
`Engine/Source/Runtime/Engine/Private/GameInstance.cpp` original. It creates a
verified exclusive original backup before replacement and rejects modified
source or an already-patched file without that backup.

The browser-only guard suppresses the first `Failed to enter` error log when
`Browse` returns `EBrowseReturnVal::Pending`. It leaves the existing startup
map fallback/bootstrap intact. Other platforms retain the original source
behavior, and the later default-map failure/exit path is unchanged. Pending
connectivity is not treated as successful multiplayer acceptance: subsequent
socket, handshake, and travel failures must still be observed and handled.

The exact candidate is now applied to the isolated source tree, with the pinned
original backup verified and the original project unchanged. The local private
suite passed all six tests (including the extracted control-flow matrix); Windows
passed five synthetic tests with the optional private-source test skipped. The
matching browser build completed successfully: one Engine unity compilation and
a fresh link, with tracked source hashes unchanged. The official pinned converter
then completed; the new WASM and matching memory initializer are retained as a
separate private generation. A headless check of that generation passed practice
startup, menu pause/resume and 1080p → 1440p → 1080p changes with matching
native/canvas dimensions and centered 16:9 presentation. All fifteen served
inputs were unchanged; fourteen backing files were independently rehashed.
The owned browser exited cleanly. This is not a performance, pointer-lock, combat
or multiplayer test. Runtime join acceptance is still unproven. The patch does
not repair the separate UT-Entry reflection-capture error. Strict multiplayer acceptance
remains pending; this log correction alone cannot establish a successful join.
The patcher’s identity snapshots and rechecks are not a process lock, so apply
only during a coordinated source freeze with competing writers idle.

Synthetic public checks run with the repository unittest suite. To also test the
captured source bytes and run the private extracted-block browser/native control
matrix, supply the local capture directory:

```sh
python3 ports/html5/test_patch_browser_pending_startup.py \
  --private-source-dir work/ut4-html5/mp-supplement-1/source
```

Private evidence: build result SHA-256
`704363382673e08513170ef61ca2102111eb5185034fba7853da3dbe3477651b`,
link receipt `90e647608fb741e5ab683913131fe83306e21d0cd9a661cc98647c7b8ce00ac3`,
conversion result `669b694f45dd690b2b948916697014d7eaebcc19b9e1e93d5c693871dc8eb35e`.
Converted WASM: `1820882b719dbc1bc6feb7c305465ac4f4f9f366b921bc6c34c020768885c3f1`;
matching memory: `ebaaa0f9afdae11f08535f3991876621f88fb409fb01ed2b862d0129317ec45b`.
The earlier playable preview remains unchanged.

Settings report SHA-256: `eabf3d2cbdee2b495137731b55ce0762bea72679c820a9e01cd204ab50f7dd05`.
The diagnostic uses port 8083; it does not replace the playable preview.
