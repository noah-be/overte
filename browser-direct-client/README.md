# Overte direct browser client

This experimental client renders Overte on the visitor's device and connects
directly to the domain and assignment services through native WebRTC DataChannel
endpoints. Navigation, avatar rendering, PCM voice and the tablet run locally.
The static browser distribution is self-hosted. Implementation and tests were
materially assisted by OpenAI Codex.

Use Node.js 22.12 or later:

```bash
npm ci
npm run verify:reuse
npm run verify:sdk
npm test
npm run build
```

Serve `dist/` at the root of an HTTPS site, and enter the updated domain's actual
signaling endpoint. Domain and assignment servers must be built with
`OVERTE_BROWSER_TRANSPORT=ON`; existing public servers require an operator
upgrade before direct browser access works.

See the [build and deployment guide](../docs/browser-direct-client/BUILD.md),
[current evidence and pending acceptance](../docs/browser-direct-client/STATUS.md),
[isolated browser/native lab](../docs/browser-direct-client/LAB.md),
[renderer provenance](REUSE.md), and
[native protocol adaptations](../docs/browser-direct-client/SDK_PORT.md).
Current browser qualification is Chrome-only. The isolated current-production
journey passes25/25 criteria, including actual native synchronization and both
synthetic audio directions. A four-profile comparison measures29.46% shorter
complete-scene loading with the direct asset route at the same recorded quality.
Physical bidirectional speech, hardware fluidity and public-server upgrades
remain pending; see the status evidence for the limits.
