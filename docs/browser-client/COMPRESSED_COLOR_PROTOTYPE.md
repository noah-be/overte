# Native compressed color prototype

This is a standalone prototype. `BrowserWorld` and its material alpha pipeline do not import it. It does not change the existing original-PNG fallback or claim faster world loading. A controlled GPU comparison and a later cold Hub loading cohort are separate requirements.

`shared/native-ktx.mjs` contains the same strict parser used by the native KTX header audit. It accepts bounded little-endian KTX1, one non-array 2D face, audited S3TC formats, exact integer mip dimensions/block counts, and native `hifi.gpu` payload versions 1 and 2. It rejects malformed/truncated/trailing bytes, unsupported shapes, duplicate metadata keys and contradictory alpha usage. It maps native sRGB internal enums to Three's base compression format plus `SRGBColorSpace`; Three's unadapted `KTXLoader.parse` does not perform that mapping.

`NativeCompressedColorCache` requires explicit approved session and authority callbacks. The prototype does not invent those callbacks for the current world API. It only fetches an exact same-origin `/api/assets/<sessionId>?url=<original>` route with cookies and redirect refusal. Each reader rechecks authority before release, including cache hits. Revocation or disposal rejects readers, aborts owned fetches and retains active ownership until an uncancellable operation actually settles. No process-global account, domain or texture cache is introduced.

Default bounds are two active downloads, 128 queued keys, 512 readers (including ready-hit microtasks), 32 MiB per asset, 64 MiB/128 entries of retained CPU cache, and a 30-second deadline measured from enqueue. Approved authority tokens must be nonempty strings of at most 4 KiB UTF-8. Original URLs are at most 4096 characters and resolved URLs at most 16,384 characters; entry and queued-key limits additionally bound retained routing metadata. Configurable maxima are bounded. Streaming rejects oversized responses even without `Content-Length`. Contiguous assembly briefly retains both streamed chunks and the resulting byte array, so peak active download memory can exceed the retained cache budget. Live model-owned mip bytes and GPU storage also remain outside that cache budget; disposal of the world/cache alone cannot free a texture still owned by a model.

Each texture owns its sampler and UV transform while identical approved sources share immutable mip bytes and a Three source identity. A ready cache hit does not invalidate that source version. Only a private WeakMap establishes compressed alpha provenance; arbitrary `userData`, cloned textures, replaced sources and disposed textures cannot claim it. The standalone material helper honors explicit native opacity modes before automatic albedo alpha eligibility. It does not infer opacity from RGB and does not discard retained RGBA for scalar translucency.

Only native sRGB color maps are proposed here. Native BC5 normal maps require reconstructed Z and scalar maps require channel adaptation, so they remain outside this prototype. Missing GPU compression support or an incompatible known role produces `UnsupportedNativeCompression`; malformed assets remain errors. A later integration must choose the original PNG fallback explicitly, without hiding admission, timeout or invalid-data failures.

Compressed blocks cannot use `UNPACK_FLIP_Y_WEBGL`. `setCompressedColorFlipY` composes the corresponding flip after the authored texture matrix and retains independent sampler settings. Native FBX `createVec2Vector` stores `(s, -t)` while the image processor preserves image rows. That source evidence does not prove every imported model convention; the pixel fixture compares both orientation candidates against the actual original PNG before selecting a runtime strategy.

Validation available before host GPU execution:

```sh
cd browser-client
node --import tsx --test --test-isolation=none src/native-compressed-color.test.ts
OVERTE_KTX_AUDIT_ROOT=/absolute/ignored/hub-assets node --test --test-isolation=none lab/audit-native-ktx.test.mjs
node node_modules/typescript/bin/tsc --noEmit
```

The self-contained component cases cover deduplication, independent samplers, source versions, private alpha provenance, exact-route refusal, approval changes, stream cancellation, deadline ownership, ready-reader/key bounds, queue/LRU limits and non-power-of-two mip dimensions. Their generated compressed containers are lifecycle fixtures, not world evidence. The five separate audit cases use the saved real Hub KTX files.

The GPU harness uses SHA-pinned real opaque 768×768 and mask 512×512 Hub images/KTX. Its fixed local fixture server exposes only those four byte buffers behind an owned fixture cookie; it never joins a domain, requests a microphone, changes a world or exercises production authorization. Original PNG versus compressed sampling compares linear color, alpha coverage, UV orientation, full mip upload/minification and actual WebGL errors. Both stock engine runs must pass independently. Its rendering deadline remains 30 seconds.

```sh
OVERTE_LAB_BROWSER=system-chromium \
OVERTE_LAB_BROWSER_DISPLAY=:0 \
OVERTE_LAB_CHROMIUM=/absolute/stock-chromium \
OVERTE_LAB_CHROMIUM_LIBRARY_PATH=/matching/browser-libraries \
node tests/integration/compressed-color.mjs

OVERTE_LAB_BROWSER=system-firefox \
OVERTE_LAB_BROWSER_DISPLAY=:0 \
node tests/integration/compressed-color.mjs
```

The harness reads saved native KTX from the ignored Hub lab directory and fetches only the two exact public originals if their saved copies are absent. It verifies all four SHA-256 values before serving them. Reports remain under the ignored lab evidence directory until reviewed and curated. No GPU result or loading benefit is asserted by this document yet.
