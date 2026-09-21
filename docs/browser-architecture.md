# Browser responsiveness and architecture

## What is running today

Vercel serves a JavaScript UI and H.264 decoder. An authoritative native UT4 server and two native D3D11 clients run on the Windows RTX host. The game clients encode GPU backbuffers directly with NVENC; the Node gateway forwards video and controls through a Cloudflare tunnel over WebSocket/TCP. No Unreal game simulation or rendering runs in the browser. The browser does not download Epic game assets. Moving the static UI to Vercel did not change these facts.

The inspected Tournament Doom client bundle (https://game.tournament.com/assets/index-C_IUSM59.js, 2026-09-21) includes a Three.js/WebGL renderer, local player-state history and a reconciliation routine using the server's last processed input sequence. That is evidence of local browser rendering and prediction/reconciliation. It does not establish access to Tournament's private anti-cheat, rewards or ticket-validation implementation.

## Measured bottleneck

GPU capture/encoding now produces about 120 frames/s at 1440p. A Mac public-route sample received about 120 frames/s on average but repeatedly received no pictures for about 100 ms, followed by bursts. Source timestamps were comparatively regular. Drawing each decoded picture immediately inflated the apparent draw rate: several draws could happen between browser presentations, so the counter did not describe visibly distinct refreshes. A high stream FPS is not proof of responsive aiming or smooth delivery.

The current frontend improvement separates incoming decoded FPS from refresh-aligned presentations. A one-frame presenter retains only the newest decoded frame until the next animation callback, closes superseded frames immediately, and clears ownership on disconnect/resolution change. Mouse input is processed before presentation in that callback. The always-visible performance panel shows displayed FPS, network RTT, resolution, stream FPS and p95 presentation gap. Developer diagnostics also report skipped pictures and gaps above 50 ms. This bounds work and makes stalls measurable; it does not repair missing network delivery or provide local input prediction.

## Preserve this exact UT4 game

The next transport change should be standard WebRTC media, not video carried over a reliable WebSocket. Keep NVENC and the native authoritative game, packetize H.264 as RTP, and use the browser's WebRTC media pipeline for congestion control and loss recovery. Use short-lived, per-seat authenticated signaling; each browser may negotiate only its leased native player. Use ICE/STUN and authenticated TURN for networks without a direct route. Inputs need a separate bounded low-latency data channel, with explicit releases and the existing native input watchdog. Keep WebSocket as a clearly identified fallback, not as an invisible source of inconsistent results.

That requires a media sender on the GPU host and publicly reachable ICE/TURN infrastructure; a static Vercel deployment alone supplies neither. Validate NAT traversal from a second external network, loss/jitter recovery, input release, two-seat isolation, resolution changes and measured input-to-visible-response. Do not promise zero latency: the authoritative rendered response still travels over the network. No WebRTC backend is claimed to be deployed by this change.

## Match the Doom-style local rendering model

A native browser client must render the world, camera, animation, HUD and immediate input feedback on the player's GPU. Send input sequences to an authoritative game server; predict the local player's movement, reconcile acknowledged state, and interpolate remote players. Keep simulation and network ticks separate from the display loop. Asset streaming/caching belongs in the browser client; server-issued identity, scoring, hits, inventory and match outcomes remain authoritative.

The recovered UT4 Windows/UE4.15 editor executable cannot become that client by being uploaded to Fly or Vercel. Keeping this exact game requires a real engine/game/content port, compatibility work and asset-distribution rights. Choosing a browser-compatible arena engine with appropriately licensed content is a different game implementation and needs an explicit product decision. Do not silently replace UT4, label streamed video as native browser rendering, or connect provisional browser events to money/rewards.

## Acceptance criteria

- Counter remains visible while aiming, with separate stream and presentation rates.
- One pending presented frame at most; all superseded VideoFrame resources close.
- User-selected 1080p/1440p never changes automatically.
- Match controls, Escape, menus, fullscreen and independent seats survive the change.
- Report p95/p99/max frame gaps, source cadence and network arrivals separately.
- Measure actual input-to-visible-response before describing a transport change as a latency fix.
- For a local-rendering client, prove camera response without waiting for a server round trip and reconciliation under deliberate delay/loss.
