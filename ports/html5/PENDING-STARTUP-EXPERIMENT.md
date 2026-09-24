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
matching browser build is in progress, so compiled/runtime acceptance is still
unproven. It does not repair the
separate UT-Entry reflection-capture error. Strict multiplayer acceptance
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
