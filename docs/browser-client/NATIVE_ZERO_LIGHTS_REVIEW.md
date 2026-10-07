# Exact-zero point and spot light guard proposal

Status: integrated behind an immutable per-World option, disabled by default. A temporary entry-point opt-in was tested in actual Hub
sessions and then removed because it did not demonstrate a speed improvement. The standalone actual WebGL2
comparison passed in bundled Chromium and Firefox, including HDR, PCF shadows,
spot maps, native mask/blend and twenty-frame ownership/program stability.
Nine helper and ten actual World lifecycle contracts pass. Native alpha/state
reconfiguration and batching retain exact private ownership. Production build
passes. Actual stock Chromium passed all four fluid gates at45.3FPS, while Firefox
failed all four at25.4FPS. Both preserved movement/native synchronization/rejoin
and their measured native DPR. Live contents changed; no performance gain is claimed.

## Measured context and source boundary

BrowserWorld deliberately keeps eight point and eight spot slots visible so
changing nearby lights changes uniforms instead of recompiling all material
programs. It selects at most eight active lights in total and resets the
remaining intensities to exactly zero. Three 0.186.1 continues executing the
sixteen compiled point/spot contribution bodies.

The audited primary code is Three's [lighting fragment chunk](https://github.com/mrdoob/three.js/blob/r186/src/renderers/shaders/ShaderChunk/lights_fragment_begin.glsl.js),
[light uniform preparation](https://github.com/mrdoob/three.js/blob/r186/src/renderers/webgl/WebGLLights.js),
and [shader preprocessing and unrolling](https://github.com/mrdoob/three.js/blob/r186/src/renderers/webgl/WebGLProgram.js).
The installed 0.186.1 chunk is the exact local compatibility oracle:
SHA-256 `d73780c6a964327484c27b2fe283c1a511a6007805afcd0491090b5b3769bd68`,
7,454 UTF-16 code units. A length/fingerprint check plus exact captured-source
comparison rejects unaudited package/chunk changes. This compatibility check
is not a cryptographic authorization mechanism; per-material authorization is
the private hook registry described below.

WebGLLights multiplies color by intensity before setting the RGB uniform.
Therefore an exactly zero uniform color contributes no point/spot irradiance
under the valid finite light and geometry inputs used by BrowserWorld. The
proposal guards each complete contribution using exact component inequality,
not an epsilon, magnitude cutoff or authored intensity approximation. Tiny,
negative, HDR and single-channel nonzero RGB values execute the original body.
The original attenuation, projected spot map, shadow lookup and direct BRDF
body remains byte-identical inside the branch. The initial light assignment,
unroll directives, light uniforms and counts remain unchanged. Directional,
sun, area, indirect, ambient, probes and all other shader chunks are unchanged.
The private expanded string is installed only in that material's compilation;
global ShaderChunk is never modified.

This does not skip shadow-map generation, vertex shadow-coordinate generation,
DFG sampling or the lighting setup preceding the direct-light loops. A GPU
driver may flatten or speculate a uniform branch. Actual improvement requires
the controlled GPU and isolated same-DPR Hub measurements; source-level skipped
work does not establish a frame-rate improvement.

## Hook ownership and integration contract

`installNativeZeroLightShader(material)` accepts Standard/Physical, Phong and
Lambert materials only, with default exact hook pairs or a captured pair proved
by `matchesNativeAlphaHooks` for that same material. Basic, ShadowMaterial,
Normal, ShaderMaterial, arbitrary custom callbacks/cache keys and copied
callbacks are refused. Native haze is not implicitly accepted; its future
composable chain requires a separate private proof.

The wrapper invokes the proved native alpha callback before substituting its
single lighting include. `hasNativeZeroLightShader` and
`matchesNativeZeroLightHooks` prove both the exact registered wrapper pair and
its captured parent's live private ownership. A copied wrapper or forged
userData flag cannot pass. Installation is idempotent and the program key is
stable across uniform changes. There are no new uniforms or recurring jobs.
WeakMap entries and the one cached expanded chunk below 8 KiB bound helper overhead;
material lifetimes govern the private registry.

Existing native alpha and render-state APIs deliberately refuse a wrapped
callback. Later integration must use this order, explicitly on owned materials:

1. Detach an installed exact wrapper with `restoreNativeZeroLightShader`.
2. Apply native alpha/cull/state changes using their existing private checks.
3. Install the light guard once after successful native configuration.
4. For static batching, accept only `matchesNativeZeroLightHooks(material,
   compile, key)` in addition to the existing exact default/alpha pairs.

Do not broaden batching to arbitrary callback classes or asset userData.
`restoreNativeZeroLightShader` never overwrites a foreign mutation.
`cloneNativeMaterialWithZeroLightGuard` preserves the native alpha clone proof,
shared texture and cutoff while creating a distinct wrapper registration. It
temporarily exposes the proved parent only during the synchronous native clone
call; source material version remains unchanged. Clone failure restores the
exact source hooks. A callback mutation during an overridden clone is preserved,
not overwritten or authorized, and the returned clone is disposed on refusal.
Ordinary Three.clone cannot prove an owned composed hook and must not be used
as an integration substitute.

## Reproducible tests

CPU and types, from the browser package:

```sh
node --import tsx src/native-zero-lights.test.ts
./node_modules/.bin/tsc --noEmit
```

CPU cases validate complete-body reconstruction, the actual pinned Three
unroller with all sixteen indices, source drift refusal, exact RGB predicate,
idempotence and unchanged render state, unsupported/copy/receiver refusal,
native alpha composition and clone proof, reconfiguration ordering, foreign
mutation preservation, and failure cleanup. Result: **9 passed, 0 failed**.

Host-only GPU command, after copying the five manifest files into one coherent
reviewed source tree and coordinating the exclusive graphics slot:

```sh
npm run test:browser -- tests/native-zero-lights.browser.spec.ts --workers=1 --output ../build/native-zero-lights-browser-results
```

The fixture renders the unchanged baseline and proposed guard with eight point
and eight spot lights in Standard, Phong, Lambert and Physical/HDR cases, plus
native alpha mask/blend cases with genuine point/spot PCF shadow maps and spot
projected maps. Mixed, exactly zero and swapped active slots are compared over
all 16,384 RGBA components in each 64x64 image. The quantization limits are one
RGBA8 step or two half-float ULPs, with nonfinite HDR pixels refused. HDR must
actually exceed 1. Shadow maps must be allocated and receiver-shadow removal
must visibly change baseline pixels. All used guarded material programs must
contain eight unrolled guards of each light kind; compatible Standard materials
may share one GPU program. Uniform changes over twenty more frames
must leave material versions, program count, calls and triangles unchanged.
Actual WebGL2/HDR capability and clean browser errors are required. The fixture
does not replace these assertions with a synthetic connection or benchmark.

Pending: actual integrated Hub observations at unchanged DPR, drawing-buffer
dimensions and quality. Live world contents may change; report those limits
rather than implying an identical snapshot or isolated causal benchmark. No native mirrored proof,
presentation module, GPU observer or existing frozen manifest was modified.
