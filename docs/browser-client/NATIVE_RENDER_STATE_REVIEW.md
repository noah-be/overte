# Native culling and translucent draw state

The prepared `native-render-state.ts` helper is not yet integrated into BrowserWorld.
Its four unit tests and both Chromium/Firefox GPU cases passed on the host.
An actual native-client comparison must still pass before a renderer cohort is
published. No loading improvement is
claimed from the source audit alone.

The reviewed native source at commit `e8c7523a285b688af69955b4baef4ab95660499b`
establishes these standard mesh pipeline rules:

- `libraries/graphics/src/graphics/Material.cpp:31` defaults to `CULL_BACK`.
- `libraries/model-serializers/src/GLTFSerializer.cpp:1579` maps glTF
  `doubleSided` to `CULL_NONE`; FBX materials are constructed with the native
  default in `FBXSerializer_Material.cpp:216`.
- `libraries/render-utils/src/RenderPipelinesInit.cpp.in:134` disables depth
  writes for translucent geometry and uses source-alpha blending. The pipeline
  applies the material's cull mode at line 141.
- `libraries/render-utils/src/MeshPartPayload.cpp:203` issues one indexed draw,
  called once by the standard mesh rendering path. Native face normals are
  adjusted using `gl_FrontFacing` in `CullFace.slh:16`.
- Image and Text entities explicitly use `CULL_NONE`; ordinary Shape entities
  retain their material's default culling.

The installed Three 0.186.1 renderer uses two draws for transparent DoubleSide
materials unless `forceSinglePass` is enabled. It switches side and increments
`material.version` twice per render (`WebGLRenderer.js:2165`); the version
change requires shader-parameter lookup even when the compiled program is
already cached. The [official Material documentation](https://threejs.org/docs/pages/Material.html#forceSinglePass)
describes this two-pass behavior. The measured Hub CPU profile contains
10.133 seconds of `WebGLPrograms.getParameters` self time, but a new real-world
profile is required to attribute the savings from a correction.

The narrow helper preserves imported side by default, disables depth writes
only when the material is transparent, and applies the native single draw to
DoubleSide. Opaque masks retain depth writes. It does not change opacity,
cutoffs, texture pixels, lighting or shader callbacks, and refuses foreign
custom shader ownership. Explicit native cull-mode mapping is supported for
the controlled fixture; applying native BACK defaults broadly remains a
separate cohort. Three flips front-face winding for negative mesh determinants,
whereas the reviewed native standard GPU state retains CCW; mirrored assets
need actual winding comparisons first.

The GPU fixture uses a single mesh with the near red front-facing triangle
first and the green back-facing triangle second. With alpha 0.5 over black,
native source-state blending gives linear RGB `(0.25, 0.5, 0)`, whereas the
historical two-pass ordering gives `(0.5, 0.25, 0)`. An independent raw WebGL
implementation checks the native state against Three, including front/back
culling, one draw, stable shader versions over 20 frames and instancing.
This source-backed GPU check is distinct from capturing the actual native
client in the isolated managed domain. That comparison must preserve the
native mesh/index order and account for each renderer's display grading.

Reproduce unit verification with:

```sh
node --import tsx src/native-render-state.test.ts
npx tsc --noEmit
```

The GPU fixture is `tests/native-render-state.browser.spec.ts`. Run it in
Chromium and Firefox through the existing headed Mesa Playwright setup, with
an exclusive output directory and no concurrent performance measurement.
