# Native glTF vertex-color alpha

This correction is prepared separately from the measured render-state cohort.
It has not been integrated into `BrowserWorld` or tested against native pixels.

The reviewed native source at `e8c7523a285b688af69955b4baef4ab95660499b`
accepts `COLOR_0` with three or four components in
`libraries/model-serializers/src/GLTFSerializer.cpp:575`. It unpacks normalized
accessor values to float32, then stores only RGB in `HFMMesh.colors` at line825.
The fourth component is discarded. That section also exists before the
April2026 glTF serializer changes, which affect joint initialization and
external texture retrieval rather than the color stream.

Three0.186.1 instead enables `vertexAlphas` when the color attribute has four
components (`src/renderers/webgl/WebGLPrograms.js:311`). An authored zero alpha
therefore makes a browser mesh invisible even when the native client renders
its RGB with ordinary material opacity. This discrepancy is independent of
the separate linear-versus-sRGB blending presentation difference.

`normalizeNativeGltfColors` visits the unique geometry of an owned, freshly
parsed native glTF scene and replaces four-component colors with RGB float32.
It preserves normalized integer and interleaved accessor values, source
buffers, positions, indices, groups, material opacity and texture alpha.
It leaves absent and three-component colors unchanged. It must be called only
on the glTF loader path before GPU upload; it is not a general glTF-standard
normalization and must not be applied to arbitrary browser assets.

The proposed integration point is after the existing safe material-state
validation of the glTF scene, before returning that scene from `loadModel`.
No `world.ts` change is part of this prepared module.

Four CPU tests pass and TypeScript checking passes. The prepared browser test
uses an actual indexed glTF loader input with normalized byte RGBA, zero
vertex alpha and material opacity0.5. It asserts that the historical input
is invisible, and that native RGB normalization produces linear one-half red
without changing the material opacity. This is a source-backed GPU oracle;
even a passing run would not substitute for an actual native/browser VEC4
fixture comparison. The browser test has not yet been run.
