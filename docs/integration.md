# Tournament integration boundary

## Implemented locally

The native Tournament game mode owns match rules and travel. Its HUD reads replicated native player state. The original observability mutator emits server-side match/kill/ranking events with unique match IDs, monotonic event IDs, weapon damage classes, bot flags, and explicit `practice_demo: true` / `real_money: false` fields. UI interaction never creates a score or payout event.

This is a UT development mod. Tournament's private services have not been connected, and the UI must not suggest a usable wallet, a logged-in platform identity, or a withdrawable balance.

## Contracts still needed from Tournament

| Platform feature | Required production contract |
| --- | --- |
| Room entry | Separate Unreal game registration, room directory, ticket issue/validation, expiry, replay prevention, and authenticated player/session binding |
| Rewards | Authoritative ingestion endpoint, event authentication, idempotency on match/event IDs, weapon value configuration, finalization/settlement rules, account restrictions |
| Anti-cheat | Required movement/input/weapon/replay schema, ingestion credentials, expected server enforcement and rejection behavior |
| Spectating | Server-enforced delayed state/replay delivery; client-side hiding is insufficient |
| Hosting | Matching client/server revision distribution, address discovery, deployment/restart policy, networking, and operations access |

The existing Doom iframe interface uses `embed`, `mode`, `server`, `room`, and `watch`; lifecycle messages include `{type:'d2dm', event:'need-token'|'ready'|'kicked'}` and parent token replies `{type:'hitplay-token', token:...}`. Native Unreal does not itself run in an iframe. A later streaming/browser wrapper can implement this boundary, checking both `event.origin` and `event.source`, while its server validates the ticket. A token arriving from a browser is not evidence of identity until the platform service validates it.

Do not call Doom ticket/directory routes as if Unreal were already registered, fabricate a successful login, or add a parallel wallet/account system. The public UI is a visual reference; it does not expose the private production contracts.

## Weapon rewards and rankings

The demo retains native deathmatch scoring. Optional bridge practice points are configured against observed exact damage-class paths and are separate from native score. No assumed mapping from Doom's laser/super-shotgun to Unreal weapons is enabled. Real weapon values and top-three settlement rules belong to Tournament's game configuration and must be tested against staging before enabling rewards.

## Native UI

The HUD/menu use an original Canvas implementation of Tournament's gold/brown in-game presentation. Combat remains the native UT HUD. It is not a copied website/account frontend, and the menu has no outbound site links. Network clients can change local controls and presentation; they cannot change server mode, rotation, scores, or rewards.
