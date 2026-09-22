# Optional WebGL eight-influence GPU-skinning experiment

**Default off.** This is a reviewed source candidate, not a validated graphics feature. Use only a coordinated, marked physical UE4.15.0 CL3228288 browser checkout. The original-asset report found Malcolm1p/3p section palettes of at most51/66 bones, with up to8 influences; Enforcer1p/3p have at most6 bones and1 influence. Those are editor imported-resource measurements, not observations of the profiled live actor or cooked browser mesh.

The candidate keeps all bone indices and weights and the existing ES2 limit of75 bones per section. It permits the extra-influence shader factory only for `SP_OPENGL_ES2_WEBGL`. Runtime selection changes only under `PLATFORM_HTML5_BROWSER`. The existing shader and vertex streams already represent the second four weights; they still need fresh compilation and actual render/animation checks. Other native platform gates remain intact. Existing morph paths require their own matching shader permutations and validation; no cloth support is claimed.

## One explicit flag for both builds

After review and the main operator's coordinated source-apply window:

```powershell
# $port must be the isolated browser source root, not the licensed original.
./ports/html5/build-browser-editor.ps1 -SourceRoot $port -Workers 2 -ExperimentalGpuSkin8
./ports/html5/build-legacy.ps1 -SourceRoot $port -Workers 4 -ExperimentalGpuSkin8
```

Both wrappers call `configure-browser-gpu-skin.py` with an explicit opt-in. The shared gate pins the frozen patcher's SHA-256, checks both inspected source bodies/backups, and applies the pair only when enabled. Omitting the flag on an already or partially patched checkout fails before building; it does **not** silently disable the experiment or restore source. Use a separate unpatched checkout for ordinary builds, or coordinate restoration of exact verified originals. Do not remove original backups.

Read-only preflight is available without invoking a compiler:

```powershell
py -3 ./ports/html5/configure-browser-gpu-skin.py $port --phase native-editor --experimental-gpu-skin8 --editor-plan
```

The native wrapper rebuilds the full `UnrealTournamentEditor` target, which includes the Engine module containing `ShouldCache`, followed by the ShaderCompileWorker `ShaderFormatOpenGL` module. Building only a shader-format DLL would not update that Engine predicate. These commands use `-NoHotReload -2015`, configured worker limits, foreground execution, nonzero-exit failure, and restore the caller's UCRT environment value. Both wrappers invoke the same read-only admission check immediately before GPU source apply: MSBuild and compilers block globally; GUI/commandlet editors block when their physical executable or explicit project uses the selected root. Only a verified executable and project within the same foreign physical engine root may continue. Missing, relative, inaccessible, linked or ambiguous paths fail closed. Python drivers are parsed with the Windows argv API, so quoted `emcc`/`emcc.py` script paths block globally even between compiler children. Missing or undecodable Python command lines block; successfully parsed unrelated Python commands remain allowed. This does not claim to identify compiler work hidden inside arbitrary Python code. No process is stopped. This admission snapshot is not a cross-process lock: the operator still owns the coordinated source freeze. The unchanged optimizer helper still conservatively blocks any `UE4Editor-Cmd.exe` during its earlier preparation step, even a verified foreign one; the HTML5 wrapper therefore may refuse that case before the new scoped pre-apply check. It is not bypassed here. Existing toolchain, plugin and shader-compiler setup must already be present; this wrapper does not install them. The HTML5 wrapper retains its guarded optimizer and mandatory fresh JS/BC/memory/symbol generation behavior.

The wrappers write `gpu-skin-editor-inputs.json` and `gpu-skin-html5-inputs.json` in `UnrealTournament/Saved/Logs/BrowserPort`. They record the explicit flag, phase, frozen patcher hash and both full source hashes, with `status=source-inputs-only` and `validated=false`. A receipt exists before compilation and is **not** build success. Preserve the separate compiler logs/output receipts. Compare both experiment receipts' source hashes before assembling a test generation. Neither wrapper cooks, packages, serves, deploys or promotes a runtime.

## Shader-cache and package coherence

Changing `ShouldCache` does not by itself prove old derived shader maps have been invalidated. Omitting `-iterate` alone is insufficient evidence that a previously cached material shader map gained the new permutations.

The coordinated test batch must use a fresh **private** derived-data-cache graph/root epoch for the GPU8 and material changes, without deleting existing caches. The operator must verify the pinned engine's graph selection/configuration first; these wrappers deliberately do not invent a DDC command-line switch or alter cache configuration. Record the selected graph/root and log evidence that old/shared cache paths were not reused. Fresh-cook the required maps and dependencies without `-iterate`, and inspect cook results for the required extra-influence skeletal and morph permutations for the actual Malcolm materials. Native build success, an empty cook error count, and a global shader-cache file alone do not prove those material permutations exist or link.

Keep the newly built engine and newly cooked package/data pair in a private test generation. **Never promote or serve the GPU8 runtime with the old package's shader permutations.** Record engine JS/WASM/memory, package/data and material/shader provenance. Confirm the actual game chooses GPU skinning for the intended cooked meshes, produces no missing-permutation/link/draw errors, and preserves first/third-person animation, all weights, relevant morphs, movement and combat appearance. Compare the same workload's CPU profile and visual output; no performance or quality improvement is assumed from source changes.

## Capability and retained-data boundaries

The browser predicate queries the **actual** legacy game `Module.ctx`, checks it belongs to `Module.canvas`, and rejects a lost or unavailable context. Fewer than16 vertex attributes or1024 vertex uniform vectors, invalid values or query errors keep the CPU branch. These conservative values match one observed context; they are not a claimed universal shader minimum. The launcher preflight context is not used as evidence for this native decision. Checks are not cached across context replacement. This does not automatically replace an already-created mesh render object following context loss.

Pinned `ConsoleManager.cpp` (SHA-256 `dba39a2f457bb923d52d574552ca63a4c3d2af1bbebd7ef910922e62a77dc964`, lines2207–2213) registers `r.FreeSkeletalMeshBuffers` with default0: retain CPU buffers. The captured recursive search of Engine/Config, project Config and Saved/Config INI files found no override. **Neither fact is a live CVar read.** Record its effective value during the private experiment before relying on retained data.

`SkeletalMesh.cpp:1530–1620` controls CPU access during serialization. Its sink at2202–2213 releases CPU resources when the CVar is1 and `RequiresCPUSkinning` is false. With the candidate, an eligible mesh can satisfy that release condition. Setting the value back to0 later does not reconstruct already-freed vertex data. A later capability check returning CPU is therefore not a guaranteed fallback lifecycle: verify buffer retention and render-object recreation explicitly. Do not advertise context-loss recovery, force a capability result, reduce weights or bones, or change this CVar speculatively to hide a failure.

## Local checks and limitations

```sh
python3 -B ports/html5/test_configure_browser_gpu_skin.py -v
python3 -B ports/html5/test_patch_browser_gpu_skin.py --private-source-dir /path/to/private/skin-perf-source -v
```

The integration suite exercises default-off/no-write behavior, explicit opt-in, both phases' matching source records, refusal of partial/already-patched source without the flag, source/backup refusal, compiler command plans, scoped editor path classification, and wrapper ordering. The Win32 command-line parser regression runs on Windows and is explicitly skipped on other hosts; pure path/ownership cases run everywhere. PowerShell forwarding/environment checks are static source checks here, not execution of the wrappers. Candidate tests compile original/transformed actual method bodies on the host and separately execute the JavaScript capability body. They do not compile the Emscripten bridge or GLSL. New wrapper execution, the fresh-cache cook and actual GPU rendering remain operator verification steps. The frozen source patcher/test pair is unchanged by this integration.
