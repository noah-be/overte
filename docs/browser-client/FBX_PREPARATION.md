# Owned FBX preparation workers

Each browser world owns at most two preparation workers. Native FBX material-binding normalization, binary decompression, historical/custom Draco decoding and FBX reconstruction run on those threads. Three's final scene parsing and graphics submission remain separately measured on the render thread.

The pipeline transfers its input buffer when a queued request becomes active. Callers must retain a prepared-buffer promise rather than attempt to reuse a detached raw buffer. The worker result supplies `buffer` and measured `materialBindingsMs`/`decodeMs`; the world's `fbxPrepareWait` additionally includes queue and message delivery time.

Google's pinned modern and historical decoder factories execute directly inside the owned worker. There are no nested decoder workers in this path. Cancellation terminates the owned thread immediately, rejects its request, releases its byte weight and ignores late callbacks. It does not rely on recursive child-worker termination.

Bounds are two workers, 16 outstanding requests, 96 MiB of input weights, 32 MiB per input, 256 MiB per output and 256 MiB per codec heap. A request has at most 60 seconds of active preparation; entering Draco adaptation tightens the remaining deadline to at most 30 seconds. Repeated stage messages cannot reset either deadline. A world abort rejects both queued and active requests and terminates all its workers.

Vite must emit ES-format worker chunks (`worker: { format: 'es' }`) because the existing adapter retains an optional dynamic decoder import for other callers. Parser errors remain visible; overload, deadline and malformed-output errors are not converted into placeholder geometry.

The pure tests use owned worker doubles for transfer, ordering, revocation and malformed responses, plus actual real-time deadline timers and a real WebAssembly memory-growth boundary. They do not substitute for browser decoding evidence.

```sh
cd browser-client
node --import tsx --test --test-isolation=none tests/model-fbx-pool.test.ts
node tests/integration/model-fbx-pool-proof.mjs
OVERTE_FBX_POOL_BROWSER=firefox node tests/integration/model-fbx-pool-proof.mjs
```

The integration proof builds actual production-format workers and compares exact prepared bytes and Three geometry/material groups/skin-bone counts against the existing pipeline. It defaults to the packaged mannequin plus two authored fixtures encoded by the pinned real Google Draco 1.3.4 encoder: ordinary geometry, and native custom material/UV1/original-index data with a real two-bone remap. The authored fixture generator never copies public-world assets or patches encoded bytes. `OVERTE_FBX_POOL_FIXTURES` may supply a JSON array of 1–8 locally cached native FBX paths, including public-world baked meshes and Kim. Its temporary server binds an unused loopback port; it does not join or edit a domain. Results omit fixture paths and participant identifiers. A separate genuinely stalled worker verifies hard termination against a shortened real test deadline.

Current evidence: ten Node tests and TypeScript checking pass. Production-built preparation workers passed in Playwright Chromium 153.0.8010.12 and Firefox 155.0 on 2026-10-01. Each browser processed the five actual fixtures above with exact prepared-byte SHA-256 equality and equal Three geometry, material-group and skin-bone counts versus the existing pipeline. The two active buffers detached on transfer, all five requests settled with zero remaining input weight, and disposal terminated the two owned threads.

Chromium processed the cohort in 780.7 ms while the page's 16 ms responsiveness timer ran 48 times, with a 23.2 ms maximum gap; Firefox took 579 ms, with 34 ticks and a 20 ms maximum gap. These are focused cohort observations, not a public-world speed comparison. Both browsers also terminated a genuinely stalled worker against a shortened 75 ms test deadline (75.8/77 ms observed), freeing its outstanding job and worker immediately. No fake clock or simulated parser completion supplied that result.

The [portable evidence](evidence/fbx-preparation-browser.json) binds all eight implementation/proof source hashes and actual input/prepared hashes to the browser results. This proof requires no GPU context and joins no domain. Actual-world loading and graphics acceptance remain separate.

The authored custom fixture reaches native attribute IDs 1000–1002 through the official encoder API's sequential allocation (the API exposes no unique-ID setter). Its six vertices and two triangles produce a 25,140-byte Draco payload; the ordinary payload is 232 bytes. Two additional Node tests decode those actual bytes and verify exact material IDs, UV sets, original indices and reversed skin remapping through Three. Browser CI runs the production proof in both installed engines; the five cached real assets remain an optional additional local cohort.
