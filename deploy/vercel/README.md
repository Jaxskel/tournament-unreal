# Vercel web client

Production: https://tournament-unreal.vercel.app

Vercel serves the actual HTML, controls and WebCodecs player. Browsers connect directly to the existing HTTPS/WSS game gateway; the video does not pass through a Vercel function or proxy. The Windows GPU host still runs the native server, both rendered players, GPU encoder and session gateway. It must remain awake and online. This deployment does not move Unreal onto Vercel or eliminate the tunnel dependency.

## Rebuild and deploy

From this directory, with Node.js and an authenticated Vercel CLI:

```sh
vercel link --project tournament-unreal
GAME_GATEWAY_ORIGIN=https://YOUR-GAME-GATEWAY node build.mjs
vercel deploy --prebuilt --prod
```

PowerShell:

```powershell
$env:GAME_GATEWAY_ORIGIN='https://YOUR-GAME-GATEWAY'
node build.mjs
vercel deploy --prebuilt --prod
```

The builder reads only the four public client files and writes Vercel Build Output API v3 under the ignored `.vercel/output` directory. No game assets, gateway server code, tokens or native binaries are uploaded. The input must be an exact HTTPS origin without a path or credentials. This is an explicit local/prebuilt deployment; pushing Git alone does not redeploy it.

Set `FRONTEND_ORIGINS=https://tournament-unreal.vercel.app` in the Windows gateway environment and restart only the gateway. Additional trusted frontend addresses must be comma-separated exact HTTPS origins. They do not become allowed gateway Host headers. Never use a wildcard for preview deployments. Existing same-origin play remains supported.

The static site has an exact gateway `connect-src` policy. The gateway allows CORS only for configured origins, validates join preflights, and applies the same explicit allowlist to WebSocket upgrades. Tokens remain single-use, short-lived reservations sent in the WebSocket authentication message; no cross-site cookies are needed. Native input/frame ports remain loopback-only.

The public Vercel alias stays the same across deployments. If the quick tunnel hostname changes, update `GAME_GATEWAY_ORIGIN` and rebuild/redeploy; a stable frontend alone does not make a temporary backend hostname permanent. A named tunnel/domain or a separate Windows GPU cloud host is needed to remove that remaining operational dependency.

Verify an unauthenticated GET to the production alias, CORS preflight, two independent browsers joining/firing, mouse capture and Escape, saved 1440p after reload, and disconnect releasing both seats. The unchanged tunnel URL remains available for recovery.


Playing fills the browser area with the native game view centered; Escape exposes the overlay toolbar and resolution selector. Fullscreen retains the same centered layout. UI and stream source sizes are independent, so resizing the browser never changes the saved native resolution.


## Verification (2026-09-21)

The production alias returns HTTP 200 without a Vercel login. The browser's join/health requests and binary video WebSocket connect to the exact configured game gateway. CORS preflight succeeds for the production alias and unit tests reject untrusted origins, invalid preflight headers and untrusted WebSocket upgrades.

The live 1080p/1440p browser test asserted the decoded dimensions and eleven centered-layout states, including 1280×720, 1512×982, 1920×1080 and 1360×800 browser windows, active aiming, menus and fullscreen. The source resolution stayed fixed while the window resized. Pointer lock hides the toolbar; Escape restores it without shifting the canvas. Normalized center clicks reached (0.5, 0.5), settings navigation worked, and disconnect/reload/rejoin retained 1440p. A reproduced Escape-during-pending-capture race was fixed and regression-tested. No page errors occurred. There are 67 passing gateway/frontend/video tests; CI also builds the static Vercel output.

Two independent unauthenticated Chrome profiles then joined through the Vercel alias together at full 2560×1440, measuring 119.3 and 118.4 decoded FPS in a short gameplay sample. Their views and source dimensions were independent, and both seats were released afterward. These are canvas draw rates, not physical panel-refresh or zero-latency guarantees.
