# Controlled asset-load E2E status

## Current status

The shared `asset-smoke` suite and its `asset-load` module are implemented.
The deterministic mock adapter executes the complete contract without hardware.
No product adapter advertises or implements `asset.load`, and no
product-specific CI runner schedules this suite. Real-adapter activation and
physical acceptance remain separate future work.

`asset.load` is a separate capability because a target-specific operation must
tell the running test client to create the controlled Image entity. It accepts
`assetId`, `url`, and `entityName`. Its `{requested: true}` result is retained
only as a diagnostic; it is never completion evidence. A future product
implementation must create one nearby, client-local `Image` entity with the
requested URL, the requested `OVERTE_E2E_ASSET_LOAD...` name, and
`userData.overteE2EAssetId` set to the requested ID. The existing probe then
observes it independently.

## Why a texture

The fixture serves a dedicated repository-owned 88-byte, 3-by-1 red/green/blue
PNG stored deterministically as
`fixture/asset-load-texture.png.base64`. The fixture manifest pins its decoded
byte length, dimensions, SHA-256 digest, MIME type, route, and test identity. A
small texture gives stronger portable script evidence than the alternatives:

- `TextureCache.prefetch()` exposes the native `Resource.State` progression;
  `FINISHED` is documented by the source API as completely loaded and ready.
- `ImageEntityRenderer` derives the entity's `naturalDimensions` from the
  decoded texture dimensions. The module requires `(1, 1/3, 0.01)`, so merely
  setting `imageURL` cannot pass.
- The asset has no model parser, animation, audio-device, login, domain, CDN, or
  production-content dependency.

## Required evidence

Each run adds a unique `requestId` query to the stable local asset route. The
module passes only when all of the following correlate to that exact URL and
asset ID:

1. Fixture telemetry records a completed HTTP `GET`, status 200, all 88 bytes,
   `image/png`, `Cache-Control: no-store`, and the pinned SHA-256 identity.
2. The in-client probe reports the texture resource as `finished`.
3. Exactly one tagged Image entity reports the exact URL, asset ID, name, a
   non-empty entity ID, and renderer-derived natural dimensions.
4. Independent adapter observations show the same process identity and a
   foreground application before, during, and after loading.

The request telemetry distinguishes a URL being assigned from its bytes being
requested. Conversely, an HTTP request alone cannot pass without the probe's
resource and entity evidence.

## Honest boundary

This proves that the fixture delivered the expected bytes, Overte's texture
resource completed decoding and became usable, and the uniquely tagged Image
entity's renderer consumed the texture dimensions. The available script APIs
do not expose a reliable per-entity "pixels presented in a completed frame"
signal. Therefore the test does **not** claim that a particular pixel was
displayed on a physical panel, nor does it use a screenshot or an artificial
fixture/mock success flag as that claim. Physical adapter acceptance may add a
separate render artifact, but it must keep the existing resource/entity proof.

Run the focused device-free contracts with:

```bash
python3 -m unittest tests.device.self_tests.test_asset_load -v
```

The fixture server publishes the required asset metadata in its ready file.
External orchestration may pass that metadata to `asset-smoke`; shared main
does not add a product-specific runner or adapter implementation.
