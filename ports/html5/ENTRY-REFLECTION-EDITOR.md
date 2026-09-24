# Entry reflection capture without the editor MainFrame

This is an explicit, Windows-only diagnostic experiment for the pinned UE4.15
editor. It adds a new flag; it is not a stock Unreal Engine launch option.
The first ordinary-editor attempt loaded UT-Entry but failed creating the main
window's swapchain in the SSH session. The experiment skips only that MainFrame
creation block, retaining editor initialization, the real rendering device, the
loaded map and core ticker.

Run the patcher against the marked isolated source root; default mode is read-only:

```powershell
python -B ports/html5/patch-editor-entry-reflection.py F:\TournamentUT4\browser-port
# After checking the source pins and excluding competing writers:
python -B ports/html5/patch-editor-entry-reflection.py F:\TournamentUT4\browser-port --apply
```

The patcher accepts only the complete pinned original source or its exact patched
output. It preserves an exclusive original backup, rejects physical-path/link
ambiguity and drift, and verifies a byte-exact inverse. It does not compile,
launch the editor, modify a map or grant package-save authority.

Rebuild the native **UnrealEd** module before launching. Use the ordinary editor
with the [Entry reflection diagnostic](compat/README.md#ut-entry-reflection-readback-diagnostic)
and add `-TournamentEntryReflectionNoMainFrame`. Skipping the MainFrame requires
both that flag and `-EntryReflectionDiagnostic`, plus unattended mode on Windows.
Immersive, VR, forced VR, automated map build, NullRHI and game mode exclude it.
All other launches execute the original MainFrame block.

The native diagnostic still requires the fixed original UT-Entry bytes in a
separate physical copy, the exact component/world, unchanged authored properties
and files, real capture-state advancement and finite HDR payload with all faces
and mips. Require its complete evidence and drained owned process tree. Exit 0,
a skipped-window log or compilation alone do not prove reflection capture.
The ordinary editor can still write editor configuration on exit; this option
is not a general no-UI or no-write mode. Other editor code may still request a
window. No synthetic payload, GUID substitution or commandlet/NullRHI bypass is
introduced.

Local validation: seven focused tests passed, including compiled predicate tests
for both platform branches and every launch-flag combination, private full-source
inverse, backup/idempotence, concurrent drift and hardlink rejection. Independent
read-only review found no scoped blocker. Windows preflight confirmed matching
source/DLL and idle writers. The actual UnrealEd compile/link then completed three
actions in 19.31 seconds. The owned supervisor was still draining a surviving
VS2015 telemetry helper at this checkpoint; that is not a completed build-run
receipt or a successful capture. The reflection retry remains pending.

```sh
python3 -B ports/html5/test_patch_editor_entry_reflection.py \
  --private-source-dir <private editor source captures> -v
```

Pinned original `UnrealEdGlobals.cpp` SHA-256:
`67901af8bdf558018c334dfb24b17118ead98cb92066f0e033ed168abd5d5dc3`.
Patched source SHA-256:
`9e5b2624ebd17f762e88b0c4ed88f5b15e59764911b5b2af931f07be5d70ec49`.
