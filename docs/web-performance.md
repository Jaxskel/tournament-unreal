# Browser stream performance — September 21, 2026

## Changes deployed

- Select the RTX 5090 explicitly. The old UE4.15 adapter heuristic chose the AMD integrated GPU; NVIDIA utilization was effectively zero before the change. Both native client logs now identify the RTX adapter. With both streams running, the RTX showed roughly 12% GPU utilization and 1% encoder utilization.
- Render and capture at up to 60 Hz. Remove the per-frame game-thread render flush and CPU JPEG compression from the optimized path. Keep one capture in flight and send completed frames immediately.
- Encode game-only BGRA backbuffers with FFmpeg 9.0.2/NVENC, H.264 Baseline, approximately 4 Mbit/s per seat, no B-frames or lookahead. Decode with WebCodecs. Raw pixels remain on the Windows host.
- Bound raw, network and decoder queues. Acknowledgements cover the browser endpoint beyond the tunnel. Ten-frame keyframe spacing shortens recovery after prediction is lost. Reset blocked decoders and recycle stalled encoders.
- Detect actual decoder capability. Select software decoding when hardware is unavailable, discard obsolete decoder callbacks, and report unsupported decoding instead of leaving an endless blank resynchronization screen.
- Keep native multiplayer, independent seat controls, authoritative match standings and automatic map rotation. No changes to movement, weapons, collision or game textures.

## Measurements

Measured through the public HTTPS demo, with the same Windows game host. FPS is counted from actual canvas draws; frame gaps are intervals between draws, not monitor scanout. Bandwidth counts binary video payloads and excludes transport overhead. These are short diagnostic samples, not an uptime or cross-device guarantee.

| Sample | Draw FPS | Median gap | 95th-percentile gap | Maximum gap | Video bandwidth |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before: JPEG, integrated GPU, Mac Chromium, ~15 seconds | 19.9 | 38.2 ms | 112.5 ms | 169.6 ms | 7.22 Mbit/s |
| H.264, two concurrent Mac Chromium seats, player 1, 30 seconds | 59.3 | 15.6 ms | 29.5 ms | 115.7 ms | 3.95 Mbit/s |
| H.264, two concurrent Mac Chromium seats, player 2, 30 seconds | 59.5 | 15.2 ms | 29.8 ms | 122.9 ms | 3.97 Mbit/s |
| Final build, Windows Edge 153 on wired host, with Mac player also connected, 20 seconds | 59.3 | 16.5 ms | 27.9 ms | 48.0 ms | — |

The Mac samples still contain intermittent ~100 ms network-delivery gaps. Separating raw-source timestamps from browser arrival/draw timestamps located these gaps after native capture. A 20-second simultaneous test found no native-source gap above 44 ms, while browser arrival gaps reached 120 ms. A direct LAN SSH forward to the same host also reproduced those pauses; testing HTTP/2 instead of QUIC did not remove them. The original public tunnel and URL were preserved.

On the wired Windows host, a separate **public-URL WebSocket transport probe** received 870 measured frames in an approximately 15-second run after discarding startup pictures: median gap 16.4 ms, p95 24.0 ms, p99 32.1 ms, maximum 36.3 ms, and **zero gaps above 50 ms**. A host-loopback probe also had no gaps above 50 ms. This isolates a problem specific to the Mac's network path; it does not prove a particular Wi-Fi driver or setting is the cause. The Windows transport probe is not a browser render benchmark. The subsequent Edge 153 browser test is listed separately above: it used the software-decoder fallback, rendered 1,186 frames, had p99 gaps of 32.6 ms and no gaps over 50 ms, and passed disconnect/rejoin without page errors. It ran headless on the host while the Mac controlled the other seat; this tests the public route but not a distant player location.

Toolbar RTT was commonly 17–30 ms. “Video age” estimates gateway raw receipt to browser draw using a clock offset derived from the best RTT. It excludes native capture, input processing and display scanout; do not present it as input-to-photon latency.

## Verification

- Windows Edge hardware decoding was unavailable under the hosting session. Capability detection selected software and restored actual gameplay; before this fix the page repeatedly attempted an unsupported hardware configuration.
- Native plugin compiled with the restored MSVC v140 toolchain; both rendered clients identify the RTX 5090.
- Two independent Chromium browser sessions joined simultaneously, displayed distinct views, captured the mouse, moved, fired, died and respawned. Both ran near 60 FPS while connected.
- Deck completed and rotated automatically to Outpost with the optimized native capture path. Both streams resumed on Outpost.
- Forty gateway/frontend/codec tests cover packet framing, independent seats, token/origin/input validation, missing pongs, menu state, disconnect/rejoin, encoder restart, stale acknowledgements, prediction loss, decoder resource cleanup, obsolete callbacks and unsupported hardware fallback. Eight authoritative-event tests and Windows launcher checks also pass.

## Reproduce and interpret

1. Start the paired native `-HardwareVideo` and gateway `FFMPEG_PATH` modes using [the hosting instructions](browser-hosting.md). Confirm the correct GPU in both native logs.
2. Warm both maps. Confirm both `/api/health` seats are fresh and report about 60 encoded FPS.
3. Join from two independent desktop browser profiles. Exercise aiming, movement, fire, respawn, Menu/Resume, Disconnect/Play Again and automatic map travel.
4. Measure canvas `drawImage` callbacks over a fixed interval after first-frame startup. Report average FPS plus p50/p95/p99/max gaps; average FPS alone hides bursts.
5. Compare binary packet arrival intervals against each packet's raw-receipt timestamp to separate native and delivery stalls. Check `encoderDropped`, `videoDropped` and `unacknowledgedFrames` in health. Drops during connection startup/keyframe synchronization are expected; increasing counts during steady play require investigation.
6. Repeat on the actual player's network. A fast desktop wired test does not establish smoothness on a different Wi-Fi connection.

This remains a two-seat native-game streaming demo at 960×540. It is not a downloadable browser/WASM engine. Audio, Tournament accounts, monetary rewards and private anti-cheat ingestion remain unavailable. Firefox and Safari gameplay/performance have not been verified. Reliable WebSocket transport can still pause under packet loss; moving to managed GPU hosting with a media transport such as WebRTC remains a future option if broader WAN testing requires it.
