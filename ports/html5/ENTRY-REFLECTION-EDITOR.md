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

## Native readback result

The fourth normal-editor run passed in 72.812 seconds: exactly one capture at
128 pixels, all six faces and mip levels structurally valid, capture StateId
advanced, and all 78 authored-object records unchanged. The authored digest was
`72c5d75b7c786ec992026ef11eeb3a758431e01c`; decoded HDR payload SHA-1 was
`3804faae2cc8e0f9b93e101afe556eb7e1ed51d3`. All 524,280 RGBA channel values
were zero. This is the renderer-produced result for this entry map; zero values
are descriptive, and this does **not** prove useful lighting or visual fidelity.

The editor exited 0, its owned process tree drained, and all 42 map/source/DLL
audit rows matched before and after. Nine raw evidence files matched remote
size/hash pins. No package was saved. Persisting the capture needs a separate
one-map save, synchronous fresh-load verification before automatic recapture,
and a matching cook/package plus strict multiplayer rerun.

Diagnostic result SHA-256:
`def14970c3b4ba71f4826ce856dcf6c833834f22175dbae531ed057e0969f687`.

## Separate-load preservation diagnosis

The first one-map save attempt failed its authored-baseline check before calling
capture or `SavePackage`. Native exit 0 was not accepted as success. All 46 audited
file/link records remained unchanged, including the selected and original maps.

Two subsequent read-only normal-editor inspections each completed with 78 object
records and a drained owned process tree. All eighteen downloaded evidence files
matched remote size/SHA-256 pins. Comparing the full rows found exactly one changed
field: the persistent level's `LevelBuildDataId`. All other row bytes matched;
both runs also preserved all 46 file/link audit records.

Private inspection of the original, hash-pinned version-493 map found no serialized
`LevelBuildDataId` or `MapBuildData` name/tag and no custom-version entries. The
matching `ULevel::PostInitProperties` generates a new build-data GUID; legacy map
loading associates migrated light-volume data with it. The ID therefore has a real
registry relationship and must not be overwritten or ignored during a save.

The next preservation check must distinguish separate legacy loads from mutation
within one load: canonicalize only this exact field when comparing independently
loaded baselines, retain its actual value in full before/after capture and save
comparisons, and require that saved value on fresh reload. The earlier diagnostic
retained only its digest, so field-level equality with that run is not asserted.
A synchronous read-only load inspection is required before retrying the save;
normal-editor and commandlet object populations have not yet been shown equal.
Reflected rows alone do not cover custom-serialized build-data registry contents.

Read-only diagnosis artifact SHA-256:
`3d86d24e64db186a51d74d9ac477e6588c4de38141a4197ddfdf76cd71746599`.
No package save, persistence verification, cook, or multiplayer acceptance follows
from this diagnosis alone.

## Compiled persistence and read-only load helpers

`EntryReflectionMapRepair.h` adds a separate, fixed-one-map persistence operation
and a synchronous verifier. It requires pinned original/copy/backup files, the
reviewed capture proof and a separate single-map save receipt. Its only save call
uses the matching editor's exported `SavePackage`; partial failure preserves
external evidence and never automatically rolls back or adopts a new file.
The launcher separately audits all fifteen selected/original map pairs, five
junctions and pinned build/preparation inputs.

The corrected cross-load comparison normalizes only the exact persistent level's
valid nonzero build-data GUID in a copied snapshot. Capture and save still require
full raw equality with the initial in-process snapshot and a matching registry
key. The initial verifier also required that editor raw digest on fresh load;
the matched-load-state correction below replaces that inappropriate comparison.
The original diagnostic's digest remains
historical proof, rather than the new cross-process baseline. The canonical digest
from both complete inspections is `4fb768cf9ba362b390affa07c74d3237ab88ab85`.

A separate `-EntryMapInspectLoaded` branch of `EntryReflectionMapVerify` accepts
only the original map hash. It omits SaveProof arguments and records the synchronous
load's object rows, GUID and registry observation. It has no startup map, world
registration, ticker, capture, `PreSave` or package-save call. Different object
counts or absent migrated registry data are observations; they do not grant save
or persistence success. The caller must retain all file audits and actual owned
process completion.

Sixteen focused local tests passed, including compiled extracted canonicalization,
raw-equality/reload-ID and read-only-inspection code, plus source/API checks. The
matching Windows plugin-only build passed with complete process-tree drain and no
external assist. Plugin DLL SHA-256:
`e8397155a18bb313f65c8ef727222be0f60a59a16847107e004b8352b00737d9`.
This establishes compilation only; subsequent save/reload acceptance remains open.

Two original-map synchronous inspections then passed with native exit 0 and
complete owned-process drain. All eighteen raw evidence files matched remote
pins, and all 46 audited file/link rows matched within each run. Both captured
60 objects, with canonical digest
`ac7d121f2682ce525598ec3f9e990ca4ea1c6337`; only the generated level GUID
differed between runs. Neither load had a migrated build-data registry. No map
was saved or captured.

The running-editor snapshot contains eighteen additional objects and initialized
world transforms/editor helper fields. Thus its 78-object raw digest is not a
valid synchronous-reload baseline. This is a verifier limitation discovered before
any map write, not evidence of lost map objects.

The revised verifier requires those exact 60 original loaded rows, with only the
saved nonzero GUID, its exact registry reference and one exact registry object
added. It retains full 78-object raw equality within the editor capture/save.
It separately fingerprints the registry through its exported serializer into an
owned, bounded archive: uncooked, persistent saving, editor data retained, no
transaction or object loading. Names and object references are encoded by string
and path; external asset contents remain covered by the separate source audits.
The fingerprint compares exact traversal bytes, not a claimed canonical ordering.
The same hash, size and archive flags must survive capture, save and fresh reload.

Nineteen focused local tests and the plugin-only Windows build passed. The new
plugin DLL SHA-256 is
`a6dcf199cb7cda9ff35c75e65b15f8f036afe59fe8475e4ffaefd6a89e91ed0b`.
A normal-editor read-only registry probe then passed: 1,076 serialized bytes,
matching original canonical 78-object snapshot, all 46 audited file/link rows
unchanged, native exit 0 and complete owned-process drain. All nine downloaded
evidence files matched their remote size/hash pins. It requested no explicit
capture or package save. The output cap does not bound temporary allocations
inside the engine serializer. This validates the fingerprint operation; it does
not establish original legacy-to-editor migration equivalence, fresh-load
persistence, useful rendered lighting or multiplayer acceptance.

The subsequent save retry wrote the isolated map but failed its post-save
invariant. It remains a failed operation despite native process exit 0.
The registry hash/size/flags were identical immediately before capture and before
save; the final registry fields are empty because an earlier check or the
fingerprint operation failed. They do **not** establish changed registry bytes.
The single compound post-save check does not identify the failing predicate.

Only the selected Entry file changed among the 46 audited rows. The original,
external backup, other maps and pinned inputs stayed unchanged; the owned process
tree drained. The retained 62,417-byte map has SHA-256
`4cbe5cc94d9d9da9cb9b3cb72f453286c8e7a0198e81885b46960d80c6cbe5ac`.
Its tagged `LevelScriptActor` reference names `UT-Entry_C_0`, whereas the original
and read-only editor snapshot name `UT-Entry_C_1`. Matching `UWorld::PreSaveRoot`
source recompiles level Blueprints in a normal editor save. This is a concrete
candidate for the raw-object mismatch, not a complete account of post-save changes.
The captured HDR payload in this attempt also contains nonzero channels; that
alone does not establish visual correctness. No fresh-load acceptance, cook,
package promotion, reset or automatic retry follows from the failed save.

## Read-only inspection of the failed afterimage

`-EntryMapInspectFailedSave2` is a separate commandlet branch of
`EntryReflectionMapVerify`. It requires the exact failed map and raw failed-save
proof, with the existing original/backup receipt checks. It cannot accept a
successful-save proof or grant save authority. It performs one synchronous load,
without world registration, capture, ticking or `PreSave`. Snapshot, payload and
registry observations are attempted independently; a failure in one does not
silently suppress the others. Completion always reports
`preservation_accepted=false`.

Twenty-two focused tests and the Windows plugin-only build passed. The resulting
DLL SHA-256 is
`583a9ffd6f7048abb132c9d8a755ec0c20844f85fd42630b2cf4f8f8c88b253e`.
The actual fresh inspection exited 0 with owned-process drain, no save, and all
46 audited file/link rows unchanged. All nine downloaded evidence files matched
their remote size/hash pins.

The loaded 128-pixel HDR payload SHA-1
`0bd2927b7dd0a0c25ce37d180c1e066d03d54d59`, capture state, brightness and zero-channel
count match the pre-save record. Independent bounded extraction of the saved
package's compressed HDR bytes agrees. The registry fingerprint also matches:
1,076 bytes, SHA-1 `8f96c4c0c8ce7ac6f4295d0c75a3f46fe826de58`, with identical archive
flags and the saved level GUID. This establishes persistence of those payloads,
not complete map or visual acceptance.

The fresh 61-object snapshot differs from the original 60-object load by the
expected registry addition and these remaining changes:

- The level-script actor is named `UT-Entry_C_0` instead of `UT-Entry_C_1`; its
  complete reflected row is otherwise identical, and the level reference follows it.
- The preview Cube's `UCSModifiedProperties` entry for `BodyInstance` is empty.
  It was already empty in the original running-editor snapshot; all other Cube
  properties match the original synchronous load.
- Both CaptureOffset references and the WorldSettings root reference are empty.
  The pinned property-export implementation supports actual null references here,
  rather than a display-name difference. Their cause and preservation implications
  remain under investigation.

No comparison exclusions, reset, map promotion or successful-save reclassification
follow from this inspection. The failed raw result and original backup remain
preserved. Cooked/browser behavior and strict multiplayer startup are still open.

## Original and saved reference-state comparison

The additional `-EntryMapInspectReferences` flag requires the fixed failed-afterimage
route above, plus `-EntryMapReferenceImage=original` or `saved`. Each invocation
loads only one image in a fresh process. The original image uses a temporary,
unique mount for the original map directory and an explicit original package name;
both resolved and actual linker filenames must match the pinned source. `/Game`
must continue resolving to the isolated project. The mount is removed on every
ordinary return. No package contents or original files are written.

The diagnostic retains the exact original 60-object canonical snapshot or saved
61-object raw snapshot. It separately reports three reference values and their
named targets, including object/internal/class flags, validity, pending-kill state,
outer and creation method. Pending-kill objects are observed without invoking
archetype resolution or changing their lifetime. Unreachable/async-loading objects
remain outside enumeration. Completion still reports preservation false.

Twenty-five focused tests and the native plugin build passed. The resulting DLL
SHA-256 is `c49fafcff86606dd2050689407a1610b0fb4ee90cd4a68f9e1452eff38f205a4`.
Both actual read-only invocations completed with exit 0, complete owned-process
drain, unchanged 46-row audits, correct linker filenames, restored mount state
and matching snapshots. All eighteen downloaded evidence files matched remote
size/hash pins.

The original WorldSettings `StaticMeshComponent0` is already pending kill and
invalid, with native creation method and the default-subobject flag. The saved
image has neither that reference nor the named object. The matching component
initialization code marks stale native default subobjects for deletion; saving
excludes pending-kill objects. This is evidence of stale-component cleanup,
rather than disappearance of a previously valid root.

For CaptureOffset, both original references point to a valid billboard helper.
The saved package still contains the helper export and both non-null serialized
references. That export is marked not-for-client, not-for-server and
not-for-editor-game. The actual diagnostic context is client=true, server=false,
editor=true; the pinned loader filters the export in that context. Executing the
actual filter body in a host fixture confirms this path. On saved load, the two
references are null, while a constructor-created named helper still exists.
Neither null field alone demonstrates loss of the serialized editor helper.

These results do not change the raw failed save, permit broad property exclusions,
or establish browser rendering or multiplayer success. A separate, exact-generation
preservation review is required before using this afterimage for a fresh cook.


## Controlled cook after exact-generation review

A separate private, read-only adjudicator checks 150 pinned evidence/source files,
the exact 60-to-61 reflected-object changes, registry/HDR equality, source-backed
reference filtering and process/file audit continuity. Eleven adversarial tests
passed. Its result permits a controlled cook experiment for the exact saved map;
it explicitly retains the failed native save, false preservation acceptance and
unverified script behavior. No general property exclusions or successful-save
reclassification were introduced.

The cook launcher passed twelve focused tests independently and on Windows,
including atomic config staging, late file-identity drift, failed rename/fsync,
and preservation of the primary exception when cleanup also fails. The engine's
normal cook path does not consume the commandlet's old-cooker output override.
The launcher therefore moved the complete old `Saved/Cooked/HTML5` directory to
retained private evidence, then used the normal fresh output directory. It
removed only fourteen exact forced-directory lines from `DefaultGame.ini` for
this run and restored the original bytes after the owned process tree drained.
No engine source or content package was edited by the launcher.

The native cook completed in 27.254 seconds with exit 0 and zero engine errors.
The overall wrapper remains **failed** (`Unexpected cooked map set`): despite
`-cooksinglepackage`, output included Engine Entry and Example_Map as well as
UT-Entry. Ninety-seven files were produced. Warnings, including existing material
fallbacks, are retained. No broad adoption of these outputs is authorized by
this observation.

A separate terminal audit rehashed the previous 7,794 cooked files unchanged,
all 97 new files unchanged, all 46 protected observations and all 90 source/config
inputs, allowing only the explicitly recorded restored config identity. The
config bytes match the original. No compiler/editor processes remain owned by
this completed invocation. All thirteen downloaded raw evidence files match
remote byte counts and SHA-256 pins.

The exact new cooked Entry is 549,238 bytes, SHA-256
`b68a33595f6990cb86ba4a98c68e28e0532694346e491e308775eb35a1ff0613`.
A bounded read of its reflection component, interpreted using the pinned v511
unversioned package layout and reflection serializer, finds `EncodedHDR` valid
with 524,280 bytes: six faces and eight mips at size 128 in four-byte pixels.
The prior cooked component had valid=false. Encoded payload SHA-256:
`8310464bc4dd176e3c29d5726a5ae10b07472cd2210b8e2053943bb351124ffa`.
This proves the missing-data transition, not image fidelity. Eight export payloads
differ between old and new cooked maps; whole-map behavior is not established by
this check. Packaging must select only the verified Entry file, prove all other
archive entries unchanged, and pass fresh multiplayer/browser regression.

Raw cook wrapper result SHA-256:
`98cea2998ca4617a94a681be2fb9368f316e3ad254779de2c2030dda93ea6aa9`.
Raw cook log SHA-256:
`daf707596a1b30a25aa7ea843071ee7f9cdcdb422420e49c33750bcb070048e4`.


## Exact one-entry archive candidate

The controlled cook's extra files were not adopted. A separate packaging step
reused the prior 9,179-entry response and compression policy, selecting only the
new UT-Entry payload. UnrealPak integrity testing and the read-only
[replacement verifier](verify-entry-replacement.py) passed. All 9,178 non-Entry
entries retain their decoded and stored payload hashes, relative block framing,
compression methods, inventory order and mount. The replacement decodes exactly
to the cooked Entry hash above. All five non-pak data slices remain byte-identical.
Every owned packaging process exited 0 and drained.

The verifier requires explicit full input hashes, distinct physical files, the
pinned archive reader, exactly 9,179 entries and final input rechecks. Run it with
operator-owned licensed files; it neither writes archives nor grants whole-map
or browser acceptance:

```sh
python3 -B ports/html5/verify-entry-replacement.py \
  --baseline "$BASELINE_PAK" --baseline-sha256 "$BASELINE_SHA256" \
  --candidate "$CANDIDATE_PAK" --candidate-sha256 "$CANDIDATE_SHA256" \
  --cooked-entry "$COOKED_ENTRY" --cooked-entry-sha256 "$ENTRY_SHA256"
python3 -B ports/html5/test_verify_entry_replacement.py -v
```

Eight focused tests cover payload/framing drift, incorrect Entry bytes,
compression/order/mount changes, corruption, CLI count and final input rehashing.
Private package result SHA-256:
`478a293a578edb5937aa39b05d3746d774d698df2770837fdf458dae1fd601b0`.
Exact replacement proof SHA-256:
`6174ac0595e87431fc780c7ac13e6746c7d2a84f90fbfebcfd3022b95e951036`.

A separate preview retains all matching runtime/client records. Its first strict
two-client run failed during initialization and recorded rejected WebSocket
handshakes (403) on the old gateway. The next diagnostic uses its own exact-origin
gateway; the existing preview and gateway remain unchanged. This routing fix
is not an engine acceptance result. The failed save/cook-wrapper records remain
failed, and multiplayer, whole-map behavior and visual fidelity remain unverified.


The exact-origin route subsequently reached postRun/Ready in both clients and
sustained 30.050 seconds of paired traffic and native-frame advancement without a
fatal engine diagnostic. Reconnect then failed with a visible `.data` network
error while the second client remained Ready. That run is **failed**, not clean
multiplayer acceptance; its after-run served-file comparison was not reached.
Owned-browser exit was 0 and gateway sessions returned to zero. The next bounded
diagnostic records package-request metadata to distinguish the reconnect failure.


## Direct-package reconnect verification

The inherited candidate manifest had omitted `packageFiles`. Consequently the
existing client downloaded the large archive as a Blob before the generated
packager mounted an ArrayBuffer. An independent source review confirmed the
actual path. A detach-only diagnostic observed delayed natural backing-storage
reclamation; this did not identify a specific allocator failure or require forced
collection. Both failed reconnect records remain unchanged.

The corrected private manifest adds only:

```json
"packageFiles": ["UnrealTournament.data"]
```

All fourteen client/runtime/payload records remain identical. The existing
`Module.locateFile`/package-XHR path consumes that explicit declaration without
editing generated code. This matches `client/runtime.example.json`; operators
must retain it when constructing manifests from older generations. It also uses
a separate exact-origin gateway rather than weakening origin checks.

A fresh strict two-client run passed in 143.201 seconds. Both clients reached
postRun then Ready at 1080p, exchanged traffic through 31.092 seconds of paired
input dispatch, and advanced native frames. A reconnected through a new iframe,
new postRun event and new bidirectional socket; its old socket closed. B stayed
Ready at the same epoch while its native frames advanced. All fifteen served
hashes stayed unchanged, no page/network/socket errors were recorded, and no
fatal engine diagnostic fired. The owned browser exited 0 and gateway sessions
returned to zero. An independent read-only audit confirmed these results.

Generation SHA-256:
`978721029e146edd326f1a5a12d236d6e53d6cb7ac32142853fc4b6df81d91e9`.
Strict report SHA-256:
`62f676ed985af07ba2d485c5a2ebee8584547ee8ff93b4aac6a1dcb5c1fe66e5`.
This establishes bounded connectivity/reconnect, not player-shot combat, respawn,
multiplayer travel, FPS, whole-map script equivalence or native visual parity.


The same candidate subsequently passed practice menu/resolution verification in
50.458 seconds: 1080p → 1440p → 1080p, native/canvas agreement, centered contained
16:9 layout, pause/resume and unchanged Ready epoch. All fifteen served hashes
matched before/after; the owned browser exited 0. This headless check uses a
scaled CSS presentation and supplies no FPS, combat, audio or pointer-lock claim.
Settings report SHA-256:
`7cbce71707c8c34cae3716c8fd12f367d7ae8563019b82b527b247a4424ee81d`.


## Accelerated multiplayer rotation

The same fourteen asset records, with a separate exact-origin preview/gateway
and an isolated `GoalScore=1 / TimeLimit=1` native server, completed two-client
Deck → Outpost → Deck in **157.217 seconds**. Both clients reached Ready epochs
1 → 2 → 3 at 1920×1080, with advancing native frames and fresh sent/received
traffic on an open socket after every load. They remained live after the final
hash scan. All fifteen served hashes were unchanged; no page/network/socket
error was recorded. The owned browser exited 0 and gateway clients returned to
zero. Independent review confirmed the report; the temporary server, gateway,
tunnel and preview were then stopped by verified ownership. The playable 8086
preview and its default-duration server remain separate and running.

Report SHA-256:
`f236ef52ad65afde24cdd30025f8eb8407345f33458b9b0ede4a6d59bfab3fdc`.
Map identity is correlated from matching engine load logs and native Ready epochs,
not a new map-name export. This does not certify normal player combat, respawn,
default-duration rotation, frame pacing or native visual parity.

The first travel attempt remains failed: the verifier classified the legacy
adapter's periodic dependency-wait message as fatal. The matching generated
`addRunDependency` watcher emits that inventory every ten seconds without
aborting. The corrected classifier accepts an **explicit optional** initialization
context containing the pinned loader's exact dependency IDs. Only exact inventory
lines/header/footer are exempt before the matching iframe postRun event; generic
callers remain strict, fatal signatures take precedence, unknown IDs/errors remain
fatal, and startup deadlines do not reset. The private probe derives six file IDs
plus the data-file ID from the independently hashed served loader. Four focused
classifier/deadline tests, 113 unchanged diagnostic checks, and a private execution
of the actual pinned watcher validate the distinction. No product runtime or
licensed generated code was changed for this correction.
