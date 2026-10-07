# Embedded texture loading proposal

Status: integrated into the topic worktree. Actual stock Chromium154 and Firefox156 passed production-built BrowserWorld, worker, image decode, twenty GPU frames, one shared-source upload, independent samplers, cancellation and revocation. See [curated GPU proof](evidence/embedded-world-gpu-20261001.json) and [actual short Hub cohort](evidence/hub-embedded-runtime-20261001.json). The unchanged Firefox fluid gates still fail.

The stage-only stock Firefox 156 report dated 2026-10-01 07:44:07 UTC reached its first sampled all-model-task readiness at 28.941 seconds. The first session recorded 211 completed images, 9 failed images, 131 cache hits and 65 ready-cache evictions. Summed image loading and decoding were 23.803/8.827 seconds, with 1307/520 ms maxima. The first ready sample also recorded summed FBX decode of 2.951 seconds, FBX texture waits of 5.644 seconds, shader preparation of 63.709 seconds and alpha processing of 21.438 seconds. These phases overlap and include waits; they are not additive wall time or pure CPU measurements.

The report's two-session GPU trace contains 9.851 seconds in `texSubImage2D` with a 322 ms maximum. Forty-five uploads exceeded 50 ms; four had 4096×4096 image inputs. Some other uploads are dynamic data textures. This does not establish that embedded images caused those slow calls. The run failed unchanged Firefox fluidness acceptance, despite real loading, movement and reconnect results.

Three's actual FBX loader turns each raw binary `Video.Content` into a new Blob URL on every parse. The existing World image cache correctly keys by resolved source URL; two parses of the same approved prepared FBX therefore miss this cache for raw embedded images. ASCII/base64 FBX images already generate stable data URIs. Observer-only `sourceKinds` counters now expose five fixed categories without source addresses or Blob IDs. The subsequent actual Chrome Hub sample starting 08:24:49 UTC recorded 76 blob image requests, 74 unique Blob URLs and 2 blob cache hits. The parent's completed cohorts confirmed 74 unique Blob URLs per session. A distinct Blob URL is not proof of distinct image content; the affected content-duplicate count and loading benefit remain unmeasured.

The prototype extracts exact eligible raw bytes in the owned FBX preparation worker, computes SHA-256 and substitutes a short marker only for that embedded `Content` property. Geometry, material IDs/connections, filenames and pixel bytes are preserved. A per-World registry binds marker resolution to the actual prepared-buffer identity and its descriptors. It creates one owned Blob URL per approved owner/content digest; each parse still receives a separate Texture and sampler. Different World instances never share Blob identities. There is no global cache, URL-method monkeypatch, base64 expansion or arbitrary Blob/file/network proxy. Other native content remains unchanged.

Extraction is bounded at 8 MiB per image, 16 MiB of unique bytes and 64 conversions. Oversized and unsupported entries retain their original content and increment explicit fallback counters. The proposed registry defaults to 64 MiB/128 entries/16 scopes, preserves in-use entries during LRU pressure and revokes its URLs on World abort. Parsed/decode scopes close only after the existing texture and alpha work settles, or their model signal aborts. Active pressure is rejected; it is not hidden by enlarged deadlines or unbounded fallback allocation. Image-cache URL-key and pixel budgets remain unchanged.

Pool validation counts actual transferred descriptor bytes, refuses forged counts/duplicate records and retains only bounded fields. The unchanged 256 MiB worker-output limit includes both model and descriptor bytes; the unchanged 128 MiB prepared-cache limit charges the same combined byte count. Detached cached descriptors trigger eviction and fresh preparation. The World proposal creates its registry within the existing World abort boundary and closes each scope in the existing load-manager `finally`. It adds bounded aggregate extraction/fallback/URL counters without retaining addresses.

Forty-seven focused CPU tests passed, including existing image/pool/cache regressions, real Three FBX parsing with both 32-bit and 64-bit headers, an actual Vite-built modified preparation worker, forged/detached descriptor refusal and cancellation ownership. Unmodified repeated parsing produced two Blob URLs/two Sources; the scoped proposal produced one URL/one Source with separate samplers and identical geometry. Exact descriptor PNG bytes and SHA-256 agree. The worker proof uses a Node worker_threads browser-global adapter; its image callbacks are controlled inputs, so it is not browser decode or GPU proof. TypeScript checking and both fixture production builds passed.

The prepared `tests/integration/embedded-world.mjs` fixture exercises actual `BrowserWorld.loadModel`, its production-built worker and real browser HTML image decoding. It checks exact PNG pixels, 20 rendered frames, one shared-source GPU upload with independent samplers, real model cancellation and World cleanup. It passed on both stock Chromium and Firefox; initial fixture failures are retained in the curated evidence. It opens only an owned authored fixture server, connects to no domain and requests no microphone. Its 30-second outer/model deadlines are unchanged.

Reproduction in the isolated snapshot:

```sh
npx vite build --config vite.embedded.config.mjs --configLoader native
node --import tsx --test --test-isolation=none tests/embedded-fbx-accounting.test.ts tests/embedded-fbx.test.ts tests/embedded-fbx-worker.test.ts tests/model-fbx-pool.test.ts tests/prepared-fbx-cache.test.ts src/world-image-cache.test.ts
npx tsc --noEmit
npx vite build --config vite.embedded-world.config.mjs --configLoader native
OVERTE_LAB_BROWSER=system-chromium OVERTE_LAB_BROWSER_DISPLAY=:0 OVERTE_LAB_CHROMIUM=/path/to/stock/chromium OVERTE_LAB_CHROMIUM_LIBRARY_PATH=/path/to/chromium-libraries node tests/integration/embedded-world.mjs
OVERTE_LAB_BROWSER=system-firefox OVERTE_LAB_BROWSER_DISPLAY=:0 node tests/integration/embedded-world.mjs
```

Adoption followed source-ownership review and both real-browser fixture passes. Actual Hub requests now show44 unique Blob images with32 cache hits versus74/2 before; no statistically isolated whole-world speed benefit is claimed. The fallback paths for unsupported image types remain the original loader path; this prototype does not claim to repair their existing Blob lifetime. GLB embedded-image behavior is unchanged. Frozen compressed-color and authority proposals were not modified.

AI assistance: this prototype and its tests were substantially developed with Codex.

A bounded observer now reports content counts without exposing addresses or digests. Actual Hub retained44 owner entries representing40 distinct contents; four cross-model duplicates account for1,170,879bytes. Cross-model sharing remains unimplemented. Observer CPU contracts and both actual GPU fixtures pass.
