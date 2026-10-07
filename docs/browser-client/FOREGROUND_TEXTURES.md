# Foreground texture preparation

## Integrated verification on 2026-10-01

The parent reviewed and integrated the narrow proposal and lifetime followup.
The production entry exposes `?texturePreparation=1` explicitly; its default
remains off. Current World source is `cdea6c0797fef9c1eb3c219003475b7ea7ab8dc882cc3bb0680021231db55a6c`.
The combined focused CPU run passes63 cases. All twelve actual foreground GPU
cases pass in bundled Chromium153 and Firefox155, alongside all four current
shader cases. Real image, bitmap and authority-approved KTX paths preserve exact
full-frame hashes, both independently projected green centers, Source versions,
hooks, one/two real sampler allocations and three mips per compressed upload.
First draw makes zero additional foreground uploads; offscreen reveal still
uses the normal renderer. Both paths release every owned GPU/reference resource.
[Full numeric reports and retained failures](evidence/foreground-textures-gpu-20261001.json).

The first KTX different-sampler fixture assigned RepeatWrapping, which was already
its real initial sampler. It now selects the opposite actual sampler and checks
that difference independently; the six-mip and two-allocation assertions remain
unchanged. The accompanying Create failures remain visible and are separate from
these twelve passing texture cases. No public-Hub speed benefit or automatic
activation has been established.

## Original proposal and provenance

Prepared with substantial AI assistance. This is a default-off source candidate, not an activated production feature or a loading-speed claim. No browser, GPU, native process or service was launched for this proposal.

The base is exact production World `88d3b361810fcace58116bfdfad8ee8b5cd2ef8d89e29d3d1fcb59376591e4c6`. Apply the two narrow patches only after checking their before hashes in `FOREGROUND_TEXTURES_SOURCE.json`. Do not replace World with a stale whole-file snapshot. The existing standalone initializer `6bdd159fe21b3f1054287da55daf4ed2007dbc29e1be3f7de1e57dc0ef93b868` gains an optional predicate; callers without it retain the tested standalone contract. The production entry point is unchanged and does not activate the new option.

## Source-backed eligibility

The installed, lock-pinned Three 0.186.1 `WebGLRenderer.projectObject` prunes hidden ancestry, tests the drawable's layers (parent layers do not prune children), invokes public drawable frustum testing with current world transforms, and pushes only visible material-array slots represented by geometry groups. This proposal follows those rules, treating only the temporarily hidden owned publishing root as visible. Current root ancestry must reach the actual World Scene. Camera matrices, material slot, group membership and the exact map field are read again before each initializer task.

Opacity zero, backface rejection and zero draw ranges do not justify a texture-setup shortcut: `renderBufferDirect` calls `setProgram` before GPU/range culling. Unknown custom frustum/per-draw callbacks, LOD, SkinnedMesh, InstancedMesh and BatchedMesh stay on the original renderer path. Known static merged geometry is an ordinary Mesh and can qualify. Avatar fallbacks, pending rigs, labels and skeleton DataTexture updates keep their established lifetimes; this first experiment applies only to entity publishers held in the private World map.

A plan stores Texture references plus drawable/slot/field descriptors, not mutable Material snapshots. A replacement material/map, scene transfer, hidden ancestor, camera change, removed geometry group, approval revocation or model-reader cancellation is checked without inferring authority from asset userData. The exact connected approval is captured before compilation awaits. The same private GraphicsWarmupOwner owns compile completion and upload preparation. Readiness is published only through the existing caller after that owner succeeds.

## Bounds and unchanged quality

The initializer preserves Texture/Source versions, samplers, mipmaps, pixels, shader hooks and renderer Source-plus-sampler dedup. It calls public `renderer.initTexture` once per real MessageChannel task and rotates model jobs. No image size, DPR, resolution, material or collision changes occur.

Existing caps remain 64 jobs, 8192 borrowed Texture references, 4096 textures per root, 100000 objects per root and a 30-second preparation deadline. Foreground descriptors add a strict aggregate 65536 live-binding bound across World jobs, enforced before storing additional descriptors. Traversal uses iterator frames instead of recursive JS calls. Plans are cleared on every success/failure, with active and peak binding counters. Offscreen or newly visible maps still use the unchanged normal renderer path. Preparation counts are initializer calls, not unique GPU uploads. `foregroundTexturePreparation` records queued wall time; scheduler `totalInitMs/maxInitMs` record CPU time inside public calls. With this option enabled, existing `shaderPrepare` covers total prepublication work, including the additional upload phase.

One individual 4096-square upload is still synchronous and cannot be split using this public API. The candidate does not promise removal of that single-upload stall. It can only move known first-visible uploads out of the eventual draw and put task boundaries between them. Preparing hidden roots or unsupported dynamic bounds to inflate loading statistics is deliberately excluded.

## Verification

Executed locally, without network/GPU/service activity:

- `node --import tsx src/foreground-texture-plan.test.ts`: 15/15.
- `node --import tsx src/world-foreground-textures.test.ts`: 8/8 actual World methods.
- `node --import tsx src/world-texture-preparation.test.ts`: 11/11 unchanged scheduler cases.
- `node --import tsx src/world-graphics-warmup.test.ts`: 7/7 existing actual World warmup lifetimes.
- `./node_modules/.bin/tsc --noEmit`: passed.

Prepared, not executed here:

`npx playwright test tests/foreground-textures.browser.spec.ts --output ../build/foreground-textures-results`

Six cases per configured engine cover real decoded HTMLImageElement, real ImageBitmap and real authority-scoped NativeCompressedColorCache-validated KTX, each with equal/different samplers. They invoke actual BrowserWorld preparation, retain its WebGL renderer and assert exact full-frame baseline pixel hashes, Source/version/hook preservation, 1-versus-2 initial GPU textures, measured upload counts and allocation dimensions/mips, no hidden/offscreen residency, normal lazy reveal afterward and zero GPU resources/references after cleanup. The controlled authority/assets are fixture inputs, not a native-domain admission proof. No lossy color tolerance replaces the exact baseline comparison.

Before activation, run these GPU gates and a coherent production Hub comparison at unchanged DPR. Record initial/final upload counts split by HTMLImage/ImageBitmap/compressed/data, dimensions and max CPU upload time; foreground queue wait; graphicsSubmit peaks; ready time; real GPU texture counts; actual memory/load snapshots; movement/native agreement; and stock Firefox/Chromium steady FPS. A lower first-draw upload count alone is not faster total world loading or lower total memory.

Primary sources are the exact installed files and hashes in the provenance JSON, the official Three repository, and the public [renderer API](https://threejs.org/docs/#WebGLRenderer.initTexture). No presumed dedup solely by image/Source identity is used.
