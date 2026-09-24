# Browser NoMCP cloud-write guard

A current-generation accelerated practice check reached native Ready, then
failed on an HTTP 404 for `/api/stats/accountId/.../bulk?ownertype=1` at match end.
The legacy player-state stats writer sends that POST directly; disabling the
analytics provider does not suppress it. The failed check is retained, not a
successful rotation result.

`patch-browser-cloud-stats.py` guards only `AUTPlayerState::WriteStatsToCloud`
when compiled for `PLATFORM_HTML5_BROWSER` **and** launched with explicit
`-NoMCP`. Native builds and browser runs without that argument retain the
original method. The guard does not mark a write successful, set the written
flag, create a fake backend response or change local scoring, XP, match-history
updates or travel scheduling in the caller. Other cloud reads/backend paths are
outside this fix's scope.

The patcher is read-only by default; `--apply` requires the matching isolated
source and preserves its original backup. `build-legacy.ps1` applies it before
the fresh compile/link. It does not edit game assets or served runtime files.

```sh
python3 -B ports/html5/test_patch_browser_cloud_stats.py -v
```

The matching native build and WASM conversion passed on September 23. A separate
private headless check completed accelerated Deck → Outpost → Deck travel in
70.1 seconds, with Ready epochs 1 → 2 → 3, unpaused native frames, matching
1920×1080 native/canvas dimensions, unchanged served inputs, no HTTP or page
errors, and owned-browser exit 0. This resolves the recorded reproduction; it
does not verify default-duration matches, network travel, FPS or visual fidelity.

The checked runtime uses the existing content package, independently of the
ongoing material cook. The private practice preview on port 8078 now serves it;
all fifteen served file hashes match the passing rotation capture. This runtime
update does not include the new material content.
Private evidence: `rotation-current-review/run-1790197355494/report.json`, SHA256
`de58175b7a784a875f31e9c79e4a767f73b91c474247efcb383125e18111005e`;
WASM `562456cd822d91a328ff0a14ef52f494902783c32a95baaa2c445ca1ae07fe86`.
