# Browser hosting

The UT4 build uses UE4.15. The browser receives the game's own GPU-rendered viewport over a JPEG/WebSocket stream; a separate native client process represents each of two browser seats. Both clients join one authoritative native server. Neither the desktop nor operating-system controls are exposed. This is a free development demo with no audio stream, accounts, wallet, settlement, or Tournament anti-cheat ingestion.

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

## Run

The components can run separately while debugging:

```powershell
# Terminal 1: gateway (configure the exact public origin if publishing).
cd browser
$env:PUBLIC_ORIGIN = 'https://YOUR-HOST.trycloudflare.com'
npm start

# Terminal 2: supervisor owns a server plus two offscreen clients.
./scripts/start-web-game.ps1
```

For a quick public demo, install `cloudflared` from Cloudflare's official release and run the combined supervisor instead:

```powershell
./scripts/start-web-demo.ps1 -Cloudflared F:\TournamentUT4\work\cloudflared.exe
```

It starts a loopback tunnel, reads its generated HTTPS origin, configures the gateway to accept exactly that origin, and starts the native server and clients. The current address is written to `UnrealTournament/Saved/Tournament/Web/current-demo.local.json`. Wait until both seats in `/api/health` have fresh frames before sharing. Initial texture/shader cache preparation can take several minutes; a reachable landing page alone does not prove the game is playable.

Use a persistent Windows Scheduled Task running as the local user with S4U and no execution-time limit for unattended operation. A short-lived Windows SSH session can terminate its child processes. The offscreen build avoids requiring a signed-in desktop. Keep the PC awake and online. Quick-tunnel URLs change when their tunnel process restarts; a stable production address requires a named tunnel or hosted GPU deployment. See [Cloudflare's quick-tunnel documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

HTTP 8890, frame TCP 9001/9002 and control UDP 9101/9102 bind to loopback only. The native server is loopback UDP 7787, with a distinct beacon port 7788. Do not expose the frame/input ports publicly. [Gateway protocol, origin restrictions, and tests](../browser/README.md).

## Diagnose

- `/api/health`: seat availability, native connection, latest-frame age. No frames means the page cannot admit a player.
- Native `Saved/Logs/Tournament/client-BrowserOne.log`, `client-BrowserTwo.log`, and `server.log`: asset preparation, join errors, crashes.
- `Saved/Tournament/Web/gateway-error.log` and tunnel log: browser/transport startup failures.
- Browser toolbar: received frame rate and WebSocket RTT. RTT is not end-to-end video latency.
- Escape/Menu: native Tournament menu. Settings, diagnostics, and reconnect belong to the game; browser fullscreen belongs to the web toolbar.
- Disconnect/blur releases held controls. Native input also has a three-second watchdog. Each seat has exclusive control; a third browser gets an arena-full response.

The initial implementation captures at most 24 frames per second at 960×540, with bounded queues that drop stale frames under backpressure. It does not claim a tested 60 FPS stream or production availability. Transport tests are separate from live gameplay evidence.
