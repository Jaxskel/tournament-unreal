# Browser SceneColor experiment

`patch-browser-scene-color.py` exposes one exact, reversible four-source
experiment for UE4.15. It extends the existing WebGL/ES2 translucency path to
request and copy encoded SceneColor immediately before qualifying translucent
meshes. The experiment is deliberately limited to linear mobile HDR64
(`r.MobileHDR=1`, `r.MobileHDR32bppMode=0`), standard translucency, and views
without mobile multiview or separate translucency. It does not change any
material asset. It is not a general HTML5 renderer change.

The patcher defaults to read-only preflight. Point it at an isolated UE4.15
source root carrying the port marker and matching `Engine/Build/Build.version`:

```sh
python3 ports/html5/patch-browser-scene-color.py /path/to/UnrealTournament
python3 ports/html5/patch-browser-scene-color.py /path/to/UnrealTournament --apply
```

`--apply` requires all four complete source files to match their pinned original
hashes. It preflights every target before writing, requires exact original-byte
backups for any already-patched file, publishes verified exclusive backups for
all four files before replacing a source, and rechecks the inputs around each
write. Drift or an interrupted partial application is retained as evidence and
refused unless the required original backups are present. The patcher does not
copy engine sources into this repository, run builds, touch configuration, or
modify assets. The four output hashes are fixed in the patcher and independently
checked against the private experiment receipt when private captures are
available. Run `--apply` only during a coordinated source freeze with competing
writers idle: identity snapshots and rechecks detect observed drift but do not
provide a process lock.

After applying, a native engine rebuild and browser rebuild are required. Use a
fresh SceneColor diagnostic DDC, cook the intended content, and test the
matching runtime generation. The existing six-resource shader-probe PASS only
shows that those material shader maps compiled under the tested settings. It is
not visual approval, whole-renderer/global-copy validation, frame evidence, or
proof of runtime rendering correctness. Transparency, refraction, HDR behavior,
and world-normal-pass interactions still need matching-runtime validation.

Public synthetic checks run without licensed engine captures:

```sh
python3 -m unittest ports/html5/test_patch_browser_scene_color.py
```

To additionally compare the four private original captures and generated files
with their pinned receipt, supply the local `work/ut4-html5` directory:

```sh
python3 ports/html5/test_patch_browser_scene_color.py \
  --private-source-dir work/ut4-html5
```
