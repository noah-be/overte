# Native-ignored FBX texture dependencies

The actual recorded Hub FBX input SHA256
`54a2529473e3178ee5154a310d4cf1a3b6add52e8f28578074d8730dd03d5996`
has thirteen Texture/Video pairs. Three of them are consumed exclusively by
`Maya|TEX_global_specular_cube`, `Maya|TEX_global_diffuse_cube`, and
`Maya|TEX_brdf_lut`. All three have embedded DDS bytes. Two are cubemaps and
one is a 2D lookup table. They are not albedo images.

Pinned native source `f91d15a08587dcd37c642234424b3215dd331724`,
`libraries/model-serializers/src/FBXSerializer.cpp:1155–1207`, ignores these
three exact auxiliary material slots. Its diffuse dispatch excludes
`tex_global_diffuse`; specular dispatch excludes `tex_global_specular`; no
BRDF lookup slot is recognized. The existing installed Three FBXLoader
loads every Texture before resolving supported material slots. Its unsupported
embedded DDS branch falls back to the authored filename. These unused objects
therefore cause three external DDS requests that the native material does not
make. Earlier investigation of embedded DDS decoding was superseded by this
complete unused-slot ownership proof. No DDS codec is needed for these inputs.

The conservative binary graph proof removes a Texture only when it has one
actual Video child and every outgoing consumer is an actual Material with one
of the three exact case-folded slot names. Used, mixed, unknown, layered,
missing-Video and ambiguous-ID graphs retain their original loading path.
Video Content is removed only when all consumers are removed and no incoming
or filename-alias ambiguity exists. Basename collisions, case variants,
unknown filenames and shared Videos preserve Content. No replacement image,
URL retry, origin expansion or geometry/material rewrite is introduced.
ASCII input is unchanged by this pruning proof.

The preparation worker combines this optional proof with its existing native
alpha normalization parse, avoiding another full parse of ordinary models.
Default calls to the alpha normalizer retain their existing behavior. The
worker's transfer, cancellation, 32 MiB input, 256 MiB output, queue ownership,
decode deadline and image-registry contracts are unchanged.

The real FBXLoader CPU control loads thirteen dependencies before pruning and
ten afterward: three DDS requests become zero; all ten embedded raster
inputs remain. The parsed geometry, material groups and rendered material/
sampler binding digest are identical. The private input stays immutable.
The output shrinks from 2,899,536 bytes to 748,328 bytes by omitting unused
objects and their original Content. All twenty actual CPU-control blob URLs
are revoked. This is prepared-buffer size, not an upstream download saving:
the original model must still be fetched in full.

Portable tests cover both binary header widths, skinned geometry, material and
sampler preservation, used/unknown/mixed consumers, shared Video Content,
filename aliases, malformed boundaries and combined normalization. The real
recorded input is intentionally private and excluded from the patch. Replaying
it requires the exact SHA-checked owned local input and emits safe aggregates.

Validation commands from `browser-client`:

```sh
node --import tsx --test --test-isolation=none tests/native-ignored-fbx.test.ts tests/fst-texture-admission.test.ts tests/baked-fbx.test.ts
npx tsc --noEmit
npx vite build --config vite.native-ignored-fbx.config.mjs
node --import tsx tests/audit-recorded-native-ignored-fbx.ts <private-exact-input> <safe-output>
```

The dedicated pixel fixture uses the real production preparation worker,
real browser ImageLoader and FBXLoader, and an authored embedded-raster model
with the same exact ignored binding. Its original control makes one real
owned HTTP404 dependency request; the pruned control makes none. No placeholder
image is injected. It compares unchanged geometry/material bindings and exact
64×64 GPU pixels for twenty frames, checks active-worker cancellation and
fresh replacement output, and releases all owned texture/worker/blob resources.
Root owns both stock browser invocations:

```sh
node --import tsx tests/integration/native-ignored-fbx-pixels.mjs
```

Use the existing explicit `OVERTE_LAB_BROWSER`, stock Chromium executable and
library-path variables, and owned display/port. There is no domain, microphone
or public-world mutation. The fixture has an unchanged thirty-second bound.
Stock Chromium154.0.8037.57 (2.845seconds) and Firefox156 (5.281seconds)
pass all twenty strict images: all81,920 pixels per engine are byte-identical
across original/pruned renders;988 colored pixels establish actual geometry.
The original control makes one owned404; the compiled production worker
removes it. Active-worker cancellation, exact fresh replacement output and
owned pool/image-registry cleanup also pass.
[Source-bound GPU evidence](evidence/native-ignored-fbx-pixels-20261002.json).
**Current Hub failure counts, native visual fidelity and whole loading
improvement are pending.** No speed or complete content-parity claim
follows from these CPU results. TGA failures remain a separate unknown.

A later source-frozen actual Hub pair retains82 source pins and exact production
bundles. Chromium loads295 models per admission, moves4.252/2.862metres and
passes all four original fluidness gates; actual native errors are below0.001m.
Firefox loads296/295 models, moves4.340/3.001metres and preserves native/rejoin,
but its two rejoined fluidness gates fail. Both actual original-image observers
retain10 uncensored errors and zero DDS failures (PNG network2, TGA HTTP6, JPEG
origin refusal2). Earlier DDS failures and later replay evidence remain recorded.
No accepted origin changes, suffix retry or unavailable-image replacement occurs.
This proves the unnecessary requests are absent in actual Hub use; scene/network/
shader variability prevents attributing a whole loading-speed or FPS gain.
[Actual unchanged-quality Hub pair](evidence/hub-native-ignored-fbx-stock-20261002.json).

## Continuous verification

The existing Browser client workflow now builds the dedicated production-worker
fixture and runs its unchanged exact-pixel controls in both bundled engines
under an owned Xvfb display with software Mesa. `bash -n
browser-client/lab/run-native-ignored-fbx-journey.sh` and all34 required repository
suites pass locally. Actual hosted execution remains pending; the separately
recorded stock-browser GPU results remain the current rendered evidence.
