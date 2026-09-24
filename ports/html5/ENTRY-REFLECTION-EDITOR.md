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
actions in 19.31 seconds. A surviving VS2015 telemetry helper required an explicit external assist: the
exact supervisor job and exited command handles were inspected, and only the
creation-time/path/hash-verified helper was terminated through its retained
process handle. Both the assist and original supervisor then proved job zero;
the original build exited 0. This was **externally assisted**, not an unattended
cleanup pass. The second reflection run still failed: the MainFrame skip was observed, but
a `FGlobalEditorNotification` popup created another swapchain on editor frame 4.
The owned process drained with exit 3. All 39 map/source/DLL audit rows matched
before and after; only the diagnostic begin row was emitted. No capture or map
save succeeded.

```sh
python3 -B ports/html5/test_patch_editor_entry_reflection.py \
  --private-source-dir <private editor source captures> -v
```

Pinned original `UnrealEdGlobals.cpp` SHA-256:
`67901af8bdf558018c334dfb24b17118ead98cb92066f0e033ed168abd5d5dc3`.
Patched source SHA-256:
`9e5b2624ebd17f762e88b0c4ed88f5b15e59764911b5b2af931f07be5d70ec49`.

Native build result SHA-256:
`39ff26dd0f9f0b791044bb2bc891ab4e098759360368ff815fc3d075ac96e8eb`.
Built UnrealEd DLL SHA-256:
`36932508d66aea28d9a241d36610360731573166c28de2efda0c80c6a65f207c`.
External helper-assist result SHA-256:
`483b2d7590a050b31d646fbeb9851b17c5e4c460ed212b39e81906e5c6764f58`.


## Global notification follow-up

`patch-editor-entry-notifications.py` separately guards the observed
`FGlobalEditorNotification::BeginNotification` path with the same opt-in
conjunction. It returns an empty notification item before creating a window.
Normal launches remain unchanged. The existing caller tolerates empty items and
continues `ShouldShowNotification` polling. The four captured shader/texture/grass/
landscape subclasses only read work state and format notification text; rendering
and compilation are not disabled. This is not a blanket notification-manager
patch: separate navigation/distance-field notifications and other windows remain
outside its scope.

Apply to the same marked isolated root and rebuild UnrealEd. The separate exact
original backup and full-file pins are mandatory, including on idempotent use.
Seven local focused checks passed, including the captured Begin/End/Tick bodies
compiled with host stubs for both platform branches. The native UnrealEd build
then passed three actions in 13.78 seconds. Its owned runner retired only the
pinned VS2015 telemetry helper and proved job drain without an external assist.
The third capture run passed those window paths but failed on frame 99 when
the performance monitor opened another warning popup. Exit 3 and drained owned
processes were retained as a failed run; all 42 map/source/DLL audit rows remained
identical and no capture or map save completed.

```powershell
python -B ports/html5/patch-editor-entry-notifications.py F:\TournamentUT4\browser-port
python -B ports/html5/patch-editor-entry-notifications.py F:\TournamentUT4\browser-port --apply
```

Original notification source SHA-256:
`a540dabc6e921b0f4463a275827b2688238d30b465d05bf422ef474058c36ed0`.
Patched notification source SHA-256:
`a53bce9be1b8f5fa4d98e75c889a8dea201b4faa0d410130aefe259a335d5a2e`.

Notification build result SHA-256:
`ef7a28bec7d3dd65345460b4d8f9ef974b0161acc421c04025864944c72d4905`.
Current UnrealEd DLL SHA-256:
`49ec827b6b1aa5e84fac50617f4e82a7bf5ae482a79e6715f0ba885c10911f69`.

## Diagnostic performance-warning setting

The diagnostic plugin now temporarily disables the existing
`UEditorPerProjectUserSettings::bMonitorEditorPerformance` setting after reserving
its exclusive evidence file. The setting must remain disabled at capture admission
and is restored on early failure or module shutdown through a weak owner reference.
The helper does not call `SaveConfig`, change scalability, or disable rendering.
Ordinary editor configuration writes on exit remain outside that narrow claim.

The matching source checks this setting before issuing performance warnings.
Fifteen focused tests passed, including compiled restoration/lifetime checks and
exact inverses to the previous plugin source. Independent review found no scoped
blocker. The native plugin-only build then exited 0, retired its verified compiler
helper through the owned supervisor, and proved complete process-tree drain. The
next capture remains a diagnostic with no map-save authority.

Plugin build result SHA-256:
`0d46b3791e76a19d82da5623c009ffb05216c993abe6ff2802607f4293aa2567`.
Plugin DLL SHA-256:
`9c0a0ea44829d327033d27ea42935169e7ce935a258f4d1be5ec7df3a389c033`.
