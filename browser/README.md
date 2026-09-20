# Tournament Unreal browser gateway

A working two-seat JPEG/WebSocket streaming gateway and browser frontend for **native Unreal Tournament game viewports**. No game assets, engine code, desktop capture, OS input automation, accounts, or payouts are included here. The separate native plugin supplies frames and accepts game-controller input; both native seats must join the same multiplayer server.

The gateway and frontend are implemented. Automated transport and isolation tests pass. Native UT4 rendering, multiplayer, public tunnel operation, and actual browser gameplay are verified by the parent runtime task, not by these tests. The current browser revision requires the companion native `menu-state` handler described below. A gateway running alone shows a warming-up message, never a simulated game.

## Start on the machine running the native clients

Requires Node.js 20 or newer. This directory can be copied by itself to the Windows runtime host.

```powershell
cd F:\TournamentUT4\browser
npm ci
$env:PUBLIC_ORIGIN = 'https://YOUR-HOSTNAME.trycloudflare.com'
# Optional origin for the parent's SSH HTTP forwarding port on the Mac:
$env:EXTRA_ORIGINS = 'http://127.0.0.1:8791,http://localhost:8791'
npm start
```

On macOS/Linux, set the same variables before `npm start`:

```sh
npm ci
PUBLIC_ORIGIN=https://YOUR-HOSTNAME.trycloudflare.com EXTRA_ORIGINS=http://127.0.0.1:8791,http://localhost:8791 npm start
```

For a local-only run, omit both origin variables and visit `http://127.0.0.1:8890`. The Node HTTP listener and **all** native TCP/UDP connections bind/use `127.0.0.1`. The parent owns SSH forwarding and Cloudflare deployment. This package does not start tunnels, subprocesses, game clients, or a game server.

`PUBLIC_ORIGIN` must be the exact browser origin, including `https://` and without a trailing slash. `EXTRA_ORIGINS` accepts explicitly configured comma-separated origins for local forwards or an additional owned domain. Requests must have an allowed Host, and join/WebSocket requests must have an allowed Origin matching that Host. Wildcards and forwarded-header trust are not used. Configure the tunnel to preserve the public Host header. Set the actual tunnel URL and restart Node if the temporary hostname changes. Native clients must reconnect their TCP frame stream after a gateway restart.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8890` | Loopback HTTP and WebSocket listener |
| `SEAT0_FRAME_PORT` | `9001` | Loopback TCP frame input, native seat 0 |
| `SEAT1_FRAME_PORT` | `9002` | Loopback TCP frame input, native seat 1 |
| `SEAT0_INPUT_PORT` | `9101` | Loopback UDP controls to native seat 0 |
| `SEAT1_INPUT_PORT` | `9102` | Loopback UDP controls to native seat 1 |
| `PUBLIC_ORIGIN` | unset | Exact public browser origin |
| `EXTRA_ORIGINS` | unset | Explicit optional additional origins |

No port is an administrative API. `GET /api/health` reports native connection state, frame age, occupancy, and player count without internal addresses. Static files are served from an exact three-route allowlist.

## Native protocol — agreed wire format preserved

**Frames: native → gateway TCP.** Each native client connects to its seat's loopback TCP port and repeatedly sends a 4-byte **unsigned big-endian JPEG byte length**, followed by exactly that many JPEG bytes. Minimum 4 bytes; maximum **4 MiB (4,194,304 bytes)**. Standard JPEG SOI/EOI markers are required. Fragmented and coalesced TCP packets are supported. Oversized/invalid frames disconnect that native stream. Only one native producer per seat is accepted. An idle native connection closes after 15 seconds; the native plugin should retry connection and continue producing frames. The stream must contain only the game framebuffer, never the desktop.

The gateway keeps one latest JPEG per seat and sends it as one binary WebSocket message to that seat's controlling browser. If WebSocket `bufferedAmount > 512 KiB`, a new frame is dropped. There is no retry queue of stale frames; the next fresh frame resumes when writable. A single frame can itself be larger than that threshold, so the bound is the threshold plus at most one 4 MiB frame and transport overhead. The browser decodes at most one image at a time and retains at most one pending latest frame.

**Input: gateway → native loopback UDP.** Each datagram contains one UTF-8 JSON object. No newline or framing prefix is added. Native input must affect only that seat's own game viewport/controller.

```json
{"type":"key","key":"W","down":true}
{"type":"key","key":"W","down":false}
{"type":"mouse","dx":12,"dy":-4}
{"type":"menu","x":0.5,"y":0.7}
{"type":"menu-state","open":true}
{"type":"menu-state","open":false}
{"type":"reset"}
{"type":"heartbeat"}
```

Allowed keys, exactly: `W A S D SpaceBar LeftShift LeftControl One Two Three Four Five Six Seven Eight Nine Escape Tab Enter LeftMouseButton RightMouseButton`.

Mouse deltas are finite numbers clamped to ±300 per axis. Menu coordinates must be finite normalized numbers from 0 through 1, relative to the visible game image (fullscreen letterboxing excluded). Extra fields, arbitrary commands, console keys, client seat IDs, unknown keys, malformed JSON, and oversized payloads are rejected. UDP on loopback is not a guaranteed-delivery protocol: the native **three-second input watchdog** and resets remain necessary.

**Heartbeat and connection watchdog:** the gateway generates `{"type":"heartbeat"}` every approximately one second for each authenticated browser seat with validated browser activity within the past **three seconds**. Pending reservations receive no heartbeat. A separate watchdog checks approximately every 100 ms: after three seconds without browser input/ping/reset, it sends one native reset and an `input-state: suspended` browser notice, then suppresses native heartbeats. A half-open WebSocket cannot keep native held input alive. Late browser activity is preceded by reset even if the periodic check has not run yet. The seat reservation still expires at 90 seconds unless the socket closes sooner; suspending input does not transfer ownership. Fresh valid browser activity resumes heartbeats. Browser resets/blur release held controls while retaining the lease; fresh browser pings keep its heartbeat active. Disconnect, expired session, invalid control, native disconnect, and graceful gateway shutdown send reset. The native plugin releases all held controls if no valid input/heartbeat arrives for three seconds. Browsers cannot submit heartbeat messages themselves.

## Required companion native menu handler

This revision adds exactly one native control schema: **`{"type":"menu-state","open":boolean}`**. JPEG/TCP framing, keyboard names, relative mouse, normalized menu clicks, and port defaults are unchanged. The browser no longer relies on the toggle semantics of a synthetic Escape key.

The native owner must add an idempotent handler: `open:true` opens the Tournament menu only if closed; `open:false` closes it only if open. Repeating either request must not toggle the menu, restart a settings page, or stack ignore-move/look flags. Retain the desired state while the Tournament controller is temporarily unavailable during travel, then apply it to the new controller. Reset stays a held-input release, **not** a menu toggle. The gateway sends absolute close at new-seat authentication and release, and replays the owner's requested state when its native TCP producer reconnects.

Only `browser/` was changed for this revision. Deploy the companion native handler before treating these frontend menu fixes as runtime verified. No native frame return-message protocol or desktop input was added.

## Browser session protocol

1. `POST /api/join`, exact same origin, `Content-Type: application/json`, body `{}`. At most 1024 bytes. No requested seat ID is accepted.
2. If a free seat has a connected native source and a frame less than 10 seconds old, response `201` is `{token, expiresInMs:10000, websocket:"/stream"}`. Token is a random 256-bit, in-memory reservation. `409` means both seats are occupied; `503` means native frames are not ready. The page offers retry; there is no misleading queue position.
3. Open same-origin `ws(s)://HOST/stream` without URL query parameters. Within five seconds, send first text message `{"type":"auth","token":"…"}`. The unused lease must still be within its 10-second reservation lifetime. Tokens are single-use for one WebSocket and never stored in URLs or browser storage.
4. Gateway resets input and sends native `{"type":"menu-state","open":false}` for the new owner, then replies `{"type":"joined","seat":1,"width":960,"height":540,"audio":false}` (seat display numbers are 1 and 2), then sends binary JPEG frames.
5. Browser sends the validated input objects above. Browser `{"type":"ping","id":<nonnegative safe integer>}` receives `{"type":"pong","id":…}` without forwarding to native. No valid browser message for 90 seconds expires the active lease. The page pings once a second and disconnects after three seconds without a timely matching pong (checked every 250 ms). A late/unissued pong cannot refresh that watchdog. WebSocket RTT is measured with a monotonic browser clock. Gateway rate limits authenticated messages to 240/sec with burst capacity 480; mouse deltas accumulate between animation frames but transmit at **at most 60 Hz**, regardless of display refresh.
6. A native disconnect sends `{"type":"stream-state","state":"waiting"}` and clears its stale JPEG. That browser retains its lease while the native client reconnects. The gateway resets input and re-sends the owner's last requested absolute menu state when the native TCP source reconnects. A browser disconnect releases its seat immediately; Play Again requests a new lease, which may be a different seat. Native persistent player identity is outside this gateway.

At most eight WebSockets may await/hold sessions; only two can control native seats. Incoming WebSocket messages are capped at 1024 bytes and compression is disabled. Leases provide control isolation, not Tournament account authentication or a paid-access restriction. Anyone with the live demo URL may request a free seat.

## Frontend

Gold/brown Tournament presentation with a 960×540 responsive live canvas, Play/Play Again, availability, connection state, rendered-frame FPS, WebSocket round-trip time, mouse capture, Menu, fullscreen, and Disconnect. RTT is **not** glass-to-glass video latency or authoritative game ping.

WASD movement, Space jump, left/right mouse fire, 1–9 weapon selection, Shift, Control, Tab scoreboard and Enter are forwarded only for active game input. Escape releases pointer lock and requests an explicit native menu open/close state; it never sends a synthetic Escape key toggle. Successful mouse capture always requests `menu-state: false`, so an inherited/open native menu cannot keep movement locked. New ownership and lease release also explicitly close the native menu. A cursor click inside the canvas in **menu mode** sends normalized `menu` input; it does not recapture the mouse. After selecting native Resume, use **Capture mouse** to aim again. Native menu state has no return protocol, so browser menu mode is the requested state rather than a readback. A native Resume click can close the menu before the browser knows; a subsequent browser Close menu or Capture mouse sends the idempotent `open:false` request and cannot reopen it. Existing normalized menu-click packets are unchanged. Held input resets on blur, hidden tab, lost capture, disconnect, and page exit. Audio is visibly marked unavailable.

The first click acquires mouse capture and is not forwarded as a shot. Pointer lock needs a supported desktop browser and a user gesture. Fullscreen includes the toolbar. Game frames only fill the canvas; no desktop or remote machine controls are exposed.

## Verify

```sh
npm ci
npm run check
npm test
```

Tests use local sockets and tiny JPEG-marker fixtures to verify transport, not a fake playable game. They cover TCP fragmentation/coalescing and invalid sizes, bounded backpressure, strict control validation, two independent browsers' WebSocket seats, per-seat frame/input isolation and order, token reuse rejection, unauthorized/oversized input, origin/Host rejection, lease expiry, reset on disconnect, native reconnect, and heartbeats. There are **24 tests** including frontend event/state tests in an isolated DOM/WebSocket harness: native Resume → browser Close menu, inherited menu → capture, normalized menu clicks, Escape/pointer-lock event ordering, 360/1000 Hz mouse-rate bounds, missing/matching/late pongs, blur/disconnect/rejoin, plus real loopback tests for watchdog heartbeat suppression, absolute menu state isolation/replay, and reset-before-late-input ordering. The harness does not replace actual browser pointer-lock verification.

Runtime handoff checks for the parent: start the matching multiplayer server and two native clients; confirm both `/api/health` seats have fresh frames; join with two separate browser profiles; confirm distinct views and game-controlled inputs; fight/respawn; test menu clicks and mouse capture; hide a tab/close a browser while holding movement; verify the native watchdog stops held input; test a third browser's full message; disconnect/rejoin; then measure actual frame rate/latency through the public URL. This directory does not assert those gameplay checks have passed.

Native engine/content rights and public-demo permission remain governed by the parent project. This frontend labels play **Live demo / no rewards** and exposes no wallet, login imitation, reward settlement, or asset downloads.
