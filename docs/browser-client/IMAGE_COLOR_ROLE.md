<!-- SPDX-License-Identifier: Apache-2.0 -->
# Image entity color texture eligibility

This proposal fixes one loader-role omission: `BrowserWorld.populateEntity`
loads an Image entity's texture as the explicit color/albedo role. Previously
the default `other` role silently bypassed the audited native KTX path even
when version1 metadata offered supported sRGB S3TC bytes. Scalar and normal
material maps retain their original-image paths. No downsampling, conversion,
new compression, deadline or permission change is introduced.

The pinned f91d15a source supports this role: `ImageEntityRenderer` requests
`TextureCache.getTexture(imageURL)` with `DEFAULT_TEXTURE`; default, albedo and
emissive all call the identical `process2DTextureColorFromImage(..., false)`.
The native SIMPLE Image renderer blends image alpha according to GPU texture
usage. This narrow change retains the current browser Image plane's blend,
depthWrite, UV transform, color space and cull behavior; it does not claim that
all Image entity properties already match native rendering.

The saved actual Hub snapshot has seven Images, three referring to **one shared**
`.texmeta.json` address. In the10:06 Firefox first session that metadata address
received three requests/957bytes, one download and two memory responses. This
establishes real affected content, not three unique payloads or a major speedup.

That session's first-ready sample retained96compressed sources/~66.66MB;
direct native KTX loading was already active. The original-image cache loaded
66images/67.13Mpx:44embedded Blob sources and22successful HTTP sources, plus
eight failures. Two-session uncompressed uploads reached300ms; compressed
base-level uploads peaked9ms. Summed phases overlap: shader preparation20.06s,
prepared-FBX waiting25.70s, actual FBX decode3.34s, parse4.98s and compressed
color17.77s do not individually represent wall-clock loading. Larger upload
dimensions remain2048²/4096²; no source identity was captured for those stalls.

The12CPU tests execute the actual private World methods and validated byte
cache. They prove supported compressed selection, color/flip/native alpha
ownership, controlled PNG fallback, malformed/denied refusal and cancellation.
Strict TypeScript checking passes. GPU and native framebuffer acceptance remain
pending; neither those CPU tests nor earlier KTX GPU tests are a measurement
of this new Image entity integration.

`tests/integration/image-compressed-world.mjs` is the new stock-engine GPU proof.
It uses previously SHA-pinned actual opaque768 and mask512 PNG/KTX files, fixed
cookie-owned fixture routes, actual BrowserWorld Image creation/rendering,
20pixelsampling frames, independent samplers/shared Source, fallback, native
mips and real delayed-fetch cancellation. It never joins or edits a domain.
Run once in each stock engine with the usual lab executable/display variables;
the fixture listens only on an owned127.0.0.1:5197 listener and preserves the
30-second in-page deadline. Native Image framebuffer comparison is separate:
publish the same relative metadata/PNG/KTX into an owned isolated lab folder,
create only expiring `browser-image-color-proof <UUID>` Image fixtures near
(60,10,0), capture the same camera in browser/native, and delete only those
owned IDs. Do not use public worlds for that authoring test.

The separate cross-model embedded dedup experiment is not integrated. The
measured Hub duplicate opportunity is only four payloads/1.17MB; retaining exact
comparison bytes would double that registry's per-entry storage cost. No
whole-world speed gain is promised for either change before a fresh coherent
production cohort.

## Root execution on2026-10-01

All12 CPU contracts and both actual stock GPU journeys passed. Chromium154
and Firefox156 rendered the opaque and alpha-mask768/512inputs with zero
full-size mask mismatches, RGB mean absolute errors0.276/1.885,20stableframes
per source and exactly20compressed mip uploads shared by independent samplers.
Actual delayed HTTP cancellation released all cache ownership. No capability
was overridden. The fallback case uses genuinely unsupported metadata; it
does not establish hardware lacking the supported codec.
[Portable proof](evidence/image-compressed-world-20261001.json).
