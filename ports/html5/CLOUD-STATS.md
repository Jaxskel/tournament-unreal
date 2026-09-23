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

Source/fixture tests are not native compilation or browser acceptance. The next
matching engine build must be converted and tested through match completion,
with the endpoint absent and actual map travel still verified. The current
playable generation predates this guard; no runtime fix is claimed yet.
