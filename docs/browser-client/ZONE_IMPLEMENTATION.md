# Prepared native Zone effects

This is continuation code prepared with substantial AI assistance. It is not yet imported by `BrowserWorld`, and it is not evidence of rendered native Zone parity. The earlier restricted platform allowed offline Firefox CPU/image-worker proof but no WebGL2. CLI Full access is now restored; fresh GPU, public-domain and native comparison results are still required for this module.

Implemented and unit-tested source is in `src/zone-effects.ts` and `src/zone-texture-worker.ts`. `src/zone-effects.test.ts` has 27 passing cases. TypeScript passes. The three cases in `tests/zone-effects.browser.spec.ts` are prepared for both configured browsers but have not run.

## Source contract

Native references are pinned to fork commit `cafd1f2b28bf513a53aec22f73260efcfed0e715`, inspected from the canonical checkout. These are source comparisons, not an assertion that an older native release executes identical code.

- [EntityItem containment](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/entities/src/EntityItem.cpp.in) and [compound Zone containment](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/entities/src/ZoneEntityItem.cpp.in): transformed registration bounds, strict equal-radius sphere boundary, ellipsoid/cylinder boundaries, loaded compound geometry versus unloaded box fallback.
- [Layered Zones](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/entities-renderer/src/EntityTreeRenderer.h) and [Zone renderer](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/entities-renderer/src/RenderableZoneEntityItem.cpp): volume then UUID priority; independent enabled/disabled/inherit selection; authored light direction rotated into world space.
- [Haze parameters](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/graphics/src/graphics/Haze.h) and [Haze shader](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/graphics/src/graphics/Haze.slh): exponential range, integrated altitude density, glare cone, distant background blend and separate key attenuation.
- [Skybox](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/graphics/src/graphics/Skybox.cpp) and [texture processing](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/image/src/image/TextureProcessing.cpp): inverse Zone rotation, black neutral textured tint and native atlas face layout/flips.
- [Native SH projection](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/gpu/src/gpu/Texture.cpp), [SH evaluation](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/graphics/src/graphics/SphericalHarmonics.shared.slh), [light blend](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/graphics/src/graphics/Light.cpp) and [ambient BRDF](https://github.com/noah-be/overte/blob/cafd1f2b28bf513a53aec22f73260efcfed0e715/libraries/render-utils/src/LightAmbient.slh): signed projection basis/cube axes, 32-by-32 tile integration, full tile pixel averaging and final normalization; authored constant ambient when no map; native Breezeway coefficients when the native map path uses that preset.

`resolveZoneEnvironment` operates on original entity properties, preserving independent component inheritance. `CompoundZoneContains` must call actual loaded collision geometry. A false result must not be replaced with a bounding box. The callback returns `undefined` only while the real resource is unavailable.

`NativeZoneEnvironment` is a prepared owner of sky geometry, directional light and shared haze uniforms. It aborts replaced/closed sky loads, removes owned scene resources, restores original fallback light visibility/intensity, and safely detaches its exact material hooks. Its key light remains present with zero intensity when disabled, avoiding an unnecessary shader light-count variant. Native shadow bias/cascade conversion is not validated; requested shadows produce an explicit warning and remain disabled.

## Lifecycle and resource limits

Sky requests accept an AbortSignal and default to a 30-second deadline. Successful and error bodies are bounded. The maximum asset source is 64 MiB; metadata is 64 KiB with one original-image reference and no metadata recursion. HTTPS and `atp:` relative originals use the existing authorized resolver and dependency-path helper.

Decoded source images are limited to 32 million pixels; source plus derived cube faces is limited to 64 million pixels. Cube faces are bounded to 4096 pixels. HDR/TGA/PNG/JPEG headers are checked before image decoding. Large or highly compressed HDR/TGA sources use an owned worker, bounded also inside the decoder; completion, failure and cancellation terminate that worker. Small synchronous decoding is allowed only below both 512 KiB compressed input and 65,536 decoded pixels. Browser bitmap decoding remains asynchronous and closes late bitmaps after cancellation. Other browser image formats still lack equivalent header preflight and require review before broad support claims.

Atlas extraction yields during typed pixel loops and between canvas face copies. Partial DataTextures and all transferred cube faces are disposed. SH integration accepts already decoded native linear cube pixels, is bounded by the same aggregate pixel limit, yields during actual tile pixel averaging, and checks cancellation/deadline. Its analytic tests cover isotropic radiance and a signed single-face impulse. They do not claim GPU bit equality: JavaScript accumulation uses double precision rather than native float accumulation/packed GPU formats.

## Shader integration constraints

Haze composition uses a private WeakMap. `hasNativeHazeShader(material, parentIsSafe)` accepts only the exact owned compile/cache pair and an independently reviewed parent. Asset `userData` cannot grant trust. `restoreNativeHazeShader` restores only that exact pair, preserving any later foreign mutation. A second environment cannot silently reuse another environment's uniforms.

For a later alpha/texture override, the required order is: restore the exact owned haze wrapper, configure native alpha, then attach haze again. Cloning must preserve the reviewed captured alpha parent and install a fresh wrapper; copying an arbitrary wrapped callback is unsafe. Static batching must prove the parent through default hooks or the private native-alpha registry. The prepared haze hook uses position after projection/skinning/morphing/batching, and blends linear haze before tone/display conversion. Directional key attenuation is supported in the fragment-lit Phong/Standard path; vertex-lit Lambert and coincident independent directional lights require further review.

## Remaining integration work

Native ambient projection/evaluation and authored state are available as pure functions. The class deliberately does not replace the renderer's ambient lighting: a reviewed native renderer adapter is missing. Native ambient diffuse/specular uses a specific Fresnel LUT and filtered cubemap mip path. Three LightProbe/PMREM cannot be described as identical without normalization, BRDF and pixel comparisons. Panorama-to-native-cube conversion and packed/native linear color decoding also need reviewed inputs for SH projection. No approximation has been silently substituted.

Before importing the class into `BrowserWorld`, review ambient/shadow handling, private alpha/haze composition and cloning, material lifecycle, source changes, containment resources and atlas orientation. Run the prepared browser cases on actual WebGL in Chromium and Firefox, add a real native/reference scene comparison, and repeat the measured public Hub performance journey. Do not remove current unsupported-content warnings until those effects are actually integrated and verified.

Offline commands already passed:

```sh
node --import tsx src/zone-effects.test.ts
npx tsc --noEmit
```

Pending browser command:

```sh
npx playwright test tests/zone-effects.browser.spec.ts --output ../build/zone-browser-results
```
