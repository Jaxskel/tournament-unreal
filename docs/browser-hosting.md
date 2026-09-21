# Browser hosting

The UT4 build uses UE4.15. The browser receives the game's own GPU-rendered viewport over an H.264/WebSocket stream decoded with WebCodecs; a separate native client process represents each of two browser seats. Both clients join one authoritative native server. Neither the desktop nor operating-system controls are exposed. This is a free development demo with no audio stream, accounts, wallet, settlement, or Tournament anti-cheat ingestion.

## Prepare the licensed Windows installation

Use the original-source build instructions in the main README, Node.js 20+, Python 3, and a GPU capable of running this old D3D11 engine. Keep every process using the installation stopped while building.

```powershell
python scripts/enable-offscreen.py F:\TournamentUT4\source\UnrealTournament-clean-master
./scripts/build-offscreen.ps1
./scripts/install-plugin.ps1
./scripts/build-plugin.ps1
cd browser
npm ci
cd ..
```

The offscreen patch adds the explicit `-TournamentOffscreen` flag, creates a GPU render-target texture instead of a desktop swap chain, and skips desktop presentation. It leaves normal native launches using their existing swap chain. Original graphics source files are backed up beside themselves as `.tournament-original`. The patch script was verified to reproduce the source used for the successful D3D11RHI build.

**Recovered content caveat:** the clean-master archive reports engine CL3228288 but includes UE4.15 assets saved through CL3525360, and lacks some optional EpicInternal character packages. On the demo host, `Engine/Build/PerforceBuild.txt` marks this as a local source-development installation so UE4.15 can attempt those assets. Package/custom-version checks remain; no network version checking is disabled. This is not proof that arbitrary mixed assets are compatible. Do not resave these packages or call this a matched shipping distribution. The default Malcolm character content exists under RestrictedAssets. Runtime verification must check visible characters, weapons, and both maps.

Read and accept the Epic agreement for your own installation with the existing explicit `-AcceptLicense` launcher option before unattended hosting. The local acceptance record is excluded from Git. This is not a grant to redistribute Epic assets or sell a separate commercial Unreal Tournament game.

## GPU and video encoder

On the demo PC, DXGI adapter 0 is AMD integrated graphics and adapter 1 is the RTX 5090. UE4.15's automatic heuristic picked the AMD GPU. `-GraphicsAdapter 1` writes `r.GraphicsAdapter=1` to `[Startup]` in `Engine/Config/ConsoleVariables.ini` before launching. Adapter indices are machine-specific: verify `Chosen D3D11 Adapter` and `Adapter Name` in both native client logs. Omit the option (default -1) for automatic selection on another host. No global Windows display preference is changed.

Install a Windows FFmpeg build linked from [FFmpeg's download page](https://ffmpeg.org/download.html), including `h264_nvenc`. The demo uses Gyan essentials 9.0.2, verified against its published SHA-256 before extraction. The executable is host-local and is not redistributed in this repository. Verify `ffmpeg -encoders` lists `h264_nvenc` and run a short encoder smoke test on the hosting account. Set the gateway's `FFMPEG_PATH` and the native supervisor's `-HardwareVideo` together. An incorrect pairing is rejected as invalid frame sizes, not silently interpreted as a different codec.

## Run

The components can run separately while debugging:

```powershell
# Terminal 1: gateway (configure the exact public origin if publishing).
cd browser
$env:PUBLIC_ORIGIN = 'https://YOUR-HOST.trycloudflare.com'
$env:FFMPEG_PATH = 'F:\TournamentUT4\work\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
npm start

# Terminal 2: supervisor owns a server plus two offscreen clients.
./scripts/start-web-game.ps1 -GraphicsAdapter 1 -HardwareVideo -StreamFPS 120
```

For a quick public demo, install `cloudflared` from Cloudflare's official release and run the combined supervisor instead:

```powershell
./scripts/start-web-demo.ps1 -Cloudflared F:\TournamentUT4\work\cloudflared.exe -GraphicsAdapter 1 -FFmpeg F:\TournamentUT4\work\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe
```

It starts a loopback tunnel, reads its generated HTTPS origin, configures the gateway to accept exactly that origin, and starts the native server and clients. The current address is written to `UnrealTournament/Saved/Tournament/Web/current-demo.local.json`. Wait until both seats in `/api/health` have fresh frames before sharing. Initial texture/shader cache preparation can take several minutes; a reachable landing page alone does not prove the game is playable.

Use a persistent Windows Scheduled Task running as the local user with S4U and no execution-time limit for unattended operation. A short-lived Windows SSH session can terminate its child processes. The offscreen build avoids requiring a signed-in desktop. Keep the PC awake and online. Quick-tunnel URLs change when their tunnel process restarts; a stable production address requires a named tunnel or hosted GPU deployment. See [Cloudflare's quick-tunnel documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

HTTP 8890, frame TCP 9001/9002 and control UDP 9101/9102 bind to loopback only. The native server is loopback UDP 7787, with a distinct beacon port 7788. Do not expose the frame/input ports publicly. [Gateway protocol, origin restrictions, and tests](../browser/README.md).

## Diagnose

- `/api/health`: seat availability, native connection, latest-frame age, rolling encoded FPS, raw FPS, raw/video drops, and outstanding acknowledgements. No frames means the page cannot admit a player.
- Native `Saved/Logs/Tournament/client-BrowserOne.log`, `client-BrowserTwo.log`, and `server.log`: asset preparation, join errors, crashes.
- `Saved/Tournament/Web/gateway-error.log` and tunnel log: browser/transport startup failures.
- Browser toolbar: decoded frame rate, WebSocket RTT, H.264 mode, and estimated video age. Age starts at raw receipt in the gateway and excludes native capture; neither metric is input-to-photon latency.
- Escape/Menu: native Tournament menu. Settings, diagnostics, and reconnect belong to the game; browser fullscreen belongs to the web toolbar.
- Disconnect/blur releases held controls. Native input also has a three-second watchdog. Each seat has exclusive control; a third browser gets an arena-full response.

The optimized mode targets 120 FPS at 1280×720 and approximately 12 Mbit/s per seat. Rendering uses the RTX, capture completion is asynchronous to the game thread, and NVENC replaces CPU JPEG compression. Raw-frame queues, WebSocket acknowledgements, and WebCodecs decode queues are bounded. Keyframes every ten pictures shorten recovery after a dropped prediction. Omitting both video options preserves the old 24 FPS JPEG diagnostic mode. See [measured performance](web-performance.md); transport tests are separate from live gameplay evidence.

## Keeping the arena ready

`start-web-game.ps1` preloads the authoritative server and both GPU seats before browser visitors join. It checks owned processes every two seconds and checks `/api/health` for fresh native frames. An exited process restarts the group after three seconds. A seat with no fresh frames for 120 seconds also triggers recovery (including hung processes). A missing HTTP gateway alone does not trigger repeated native restarts. First-run cache preparation can use `-FrameTimeoutSeconds 600`; warm the assets before sharing the URL.

The supervisor catches failures and retries continuously; Task Scheduler's finite restart count is not the recovery mechanism. Logs are appended directly to `Saved/Logs/Tournament/supervisor.log`, so a wrapper redirect is unnecessary. Each failed run preserves native logs in `recovery-<UTC timestamp>`; only the newest ten recovery directories are retained. `-Once` is available for fail-fast diagnostics. Stop the hosting task and its owned native processes before rebuilding the plugin.

The recovered build crashed during replication of a post-match cosmetic `FavoriteWeapon` class reference. The minidump placed the invalid object at offset `0x648` in the replicated player state, matching `AUTPlayerState::FavoriteWeapon` in its debug symbols. `TournamentGameState` skips generating stock cosmetic weapon highlights and retains server-owned frag standings. `TournamentDeathmatch` keeps the base engine end-of-match lifecycle and bot learning, displays the scoreboard, and rotates after 12 seconds without the character ceremony. Disabling the ceremony alone did not resolve the crash; no engine object-validity checks are bypassed.

The page joins immediately when a fresh seat exists. During a restart it retries HTTP 503 automatically, with Cancel and a 90-second deadline; a full arena still reports capacity immediately. Recovery is not instantaneous: native initialization takes time, so continuous preloading is what makes normal joins fast. This does not provide uptime while the Windows PC is off or offline.

When updating a Scheduled Task wrapper, verify that its old Node child actually exited before starting the replacement. Stopping the wrapper alone can leave `node server.js` alive with old code; verify process creation time and the new health fields after deployment. Stop only the gateway and its owned encoders, and preserve the tunnel process to retain the shared URL.

## 120 FPS configuration

`STREAM_FPS=120` is the gateway default and `-StreamFPS 120` is the native launcher default. The combined launcher passes the selected rate to both. To select the lower-bandwidth profile, set both `STREAM_FPS=60` and `-StreamFPS 60`; never change only one. The gateway advertises FPS to the browser so decode timestamps match the selected cadence.

At 120 FPS the clients render with a 240 FPS ceiling, providing capture scheduling headroom; capture and encoder output remain limited to 120. The launcher disables this game's legacy smooth-frame-rate cap. Mouse forwarding is capped at 120 Hz and the authenticated control budget covers simultaneous video receipts and mouse movement. Encoder conversion uses one CPU filter thread and NV12 input to NVENC; at most three pictures may be in flight through the encoder.

A 120 Hz display/browser presentation path is needed to see 120 distinct frames per second. Canvas draw/stream FPS is not a measurement of panel refresh. Higher capture cadence can still reduce frame age on a 60 Hz display. Network pauses cannot be eliminated by an FPS setting.


### Resolution and clarity

Pair the gateway `STREAM_RESOLUTION` with native `-StreamResolution`; both default to `720p`. Supported values are `540p`, `720p` and `1080p`. Restart both gateway and native clients after a profile change; reload browser clients. The combined launcher passes both settings automatically. Legacy JPEG mode stays at 540p.

| Profile | Native size | 120 FPS bitrate target | 60 FPS bitrate target |
| --- | --- | --- | --- |
| 540p | 960x540 | 6 Mbit/s | 4 Mbit/s |
| 720p (default) | 1280x720 | 12 Mbit/s | 8 Mbit/s |
| 1080p | 1920x1080 | 24 Mbit/s | 16 Mbit/s |

These are targets, not measured frame-rate guarantees. On this host, two-seat gameplay measured about 103-109 FPS at 720p; the 1080p test delivered about 50 FPS. Source rendering is 100% scale with motion blur/depth of field disabled, FXAA and 16x anisotropic filtering. H.264 High uses NVENC P3 with zero B-frames and lookahead; the VBV buffer represents about 32 ms of target bitrate. The 720p default preserves more detail than the old 540p profile while avoiding the larger 1080p speed regression. See the latest performance report before changing it.
