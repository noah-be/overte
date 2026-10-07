# Native linear transparency and presentation

This is a source-backed proposal, not an implemented renderer change. The real
native/browser render-state fixture passed all five face/depth/order cases in
Chromium and Firefox. Its assertion proves channel dominance and material
state, not absolute color equality. The captured native blended colors differ
from the current browser output; that difference remains an explicit limit.

## Source cause

The reviewed native source at `e8c7523a285b688af69955b4baef4ab95660499b`
creates its lighting texture as floating-point `R11G11B10` in
`libraries/render-utils/src/DeferredFramebuffer.cpp:89`.
`RenderTransparentDeferred::run` draws translucent geometry into that lighting
framebuffer before the separate `ToneMapAndResample` presentation job
(`RenderDeferredTask.cpp:250`, `ToneMapAndResampleTask.cpp:83`).

The final `toneMapping.slf` explicitly uses `GL_FRAMEBUFFER_SRGB` for conversion
to the presentation framebuffer. Its default SRGB curve leaves linear color
unchanged before that conversion. The default is source-defined in
`graphics/Tonemapping.h:30` and `ToneMapAndResampleTask.h:80`.

Three0.186.1's standard material shader instead runs
`colorspace_fragment` before fixed-function blending into the normal browser
canvas. That chunk calls `linearToOutputTexel`. Pure red and green therefore
remain full-strength source channels, but alpha blending stores one-half and
one-quarter directly as presentation values rather than encoding the completed
linear blend once.

The fixture's native linear source-alpha result `(0.25, 0.5, 0)` corresponds to
approximately `(137, 188, 0)` in eight-bit sRGB. Actual native captures from
both desktop engines were about `(136, 187, 0)`. The current browser capture
was `(64, 127, 0)`. A single half-opacity red face was about187 in native
and127 in the browser. Opaque/masked primary colors were255 in both. These
observations support the source-defined compositing explanation without
changing the existing native pixel oracle.

## Proposed independent renderer stage

Render the visitor's local world into an owned linear render target, then run
one full-screen tone/encoding pass into the actual browser canvas. Preserve
source-alpha blending, native depth/cull state and material/texture alpha.
Do not compensate by changing opacity, authored colors or texture gamma.

Faithful HDR requires verifying a renderable floating-point target on both
supported desktop engines. Native uses a floating-point lighting attachment;
an unsigned-byte fallback would clip HDR and requires an honest supported-mode
decision. Native tone/exposure is a whole-world presentation stage, whereas
the current renderer uses per-material Three tone mapping. That behavior must
be reviewed explicitly rather than accidentally applying tone mapping twice.

The integration needs resize/DPR handling, bounded owned GPU allocations,
disposal and reconnect, antialiasing, depth preservation, snapshots of the
local visitor canvas, and shader/texture readiness. The DOM/native Tablet UI
must not become part of the world target. Render-target presentation also adds
work, so real Hub loading and steady movement must be measured independently
of the currently frozen render-state cohort.

Future acceptance should compare absolute native/browser blended pixels with
known native tone/exposure, repeat positive fractional opacity and mask cases,
verify opaque color presentation and screenshot exports, and rerun actual
Chromium/Firefox Hub performance and native coexistence. No compositor code,
quality reduction or test-bound change is included in this proposal.

## Prepared helper contract

`WorldPresentation` is prepared in a separate module and has not been
integrated into the browser world. It owns one half-float RGBA linear world
target and a full-screen native tone/encoding draw. Its default is the
source-defined native SRGB curve and exposureEV0. It does not silently reuse
Three's current ACES per-material presentation. The prepared native filmic
formula preserves its complete inherited MIT notice; production notices must
include that source attribution before distributing an integrated build.

`resize(cssWidth, cssHeight, DPR)` checks exact requested antialiasing against
the format-specific GPU sample counts and checks actual framebuffer
completeness. It refuses unsupported requests instead of reducing quality.
Allocation uses a conservative256MiB owned peak-target memory budget, including
the previous and replacement targets simultaneously during transactional resize.
It refuses a replacement whose combined estimate exceeds that budget; no hidden
quality reduction or 2x budget exception applies. A failed
replacement releases its candidate and retains the previous target/canvas.
Unsigned-byte rendering is available only as an explicit caller choice and
reports its HDR clipping limitation.

`render(scene, camera)` renders the linear world then one output draw, with
renderer state restored even on failure. Both renderer-global CSS defaults and
the previously bound target's effective physical viewport/scissor/test are
preserved, without changing its viewport/scissor metadata. Combined world/output draw counts
remain observable. Presentation pause suppresses drawing; `capture` forces a
fresh local visitor-world render and exports its PNG even while paused.
`prepare(object, camera, lightingScene)` compiles for the actual linear target
and restores renderer state immediately while asynchronous shader readiness
remains pending. It does not claim that compile readiness uploads textures.
`dispose` releases only owned resources and leaves the caller's renderer alive.

Ten mocked-renderer CPU contracts passed, including custom target restoration
and the aggregate old-plus-replacement peak allocation limit. The prepared GPU fixture
must verify actual half-float/MSAA4 support, native linear blending followed
by sRGB presentation, repeated-frame shader stability, DPR sizing, paused
snapshot freshness and GPU texture disposal in both desktop engines. No GPU
execution or actual-world performance result is claimed for this helper.
