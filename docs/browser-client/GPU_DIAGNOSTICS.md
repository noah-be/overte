# Embedded texture GPU diagnostics

## Explicit hosted graphics comparison

The existing manual Browser client workflow also offers
`embedded_swangle_diagnostic`, a boolean that defaults false. Selecting it
supplies only `OVERTE_EMBEDDED_USE_SWANGLE=1` to the original embedded GPU step.
The runner adds exactly `--use-angle=swiftshader` for Google Chrome. Undefined,
empty and `0` retain the original mute-only arguments; unknown values refuse
before launch. All original pixel/frame/upload/sampler/cancellation assertions,
deadlines, failure observations and other workflow steps remain unchanged.

`requestedAngleMode` records `default` or `swiftshader-requested`. This is a
request, not observed backend identity or an explanation of context loss. Both
local owned-X11 requested/default comparisons pass and report the same renderer
family. Preserve same-source hosted successes and failures. Do not infer a fix
or driver cause from one selected success.

The current V26 code gates pass: 2874 product tests without skips, the
34-file production build, both original embedded fixture configuration builds
and repository quick profile. The [source proof](evidence/avatar-delivery-angle-source-checks-20261004.json)
retains the separate failed nine-service preflight: registered Native missing,
other eight births matching, cause unknown. No restart or native/session
acceptance follows from these code checks.

For one source-reviewed exact-head comparison on the authorized fork:

```sh
gh workflow run browser-client.yml --repo noah-be/overte \
  --ref feature/main/browser-client \
  -f startup_diagnostics=false -f avatar_sample_diagnostics=true \
  -f embedded_swangle_diagnostic=true
```

Confirm the actual fork and ref before dispatch. The full default workflow
continues to run; this input omits no acceptance step.

The authored embedded-FBX journey retains its original 20 exact pixel checks,
single shared image upload, independent samplers and actual model cancellation.
An empty frame is a failed assertion even when image decoding succeeded. A
passing run does not erase a same-source failure.

On failure, the existing runner makes one bounded 500 ms read of fixed diagnostic
data. It makes no additional read after the original 30 s fixture deadline and
preserves the original failure. Current version 4 retains the eleven-number
frame row and the paired `contextStates` row introduced in version 2:

```text
[frame, beforeRenderFrame, afterRenderFrame, contextLostBefore01, contextLostAfter01]
```

The counter and context state are sampled around the original render call.
This introduces no render retry, shader-readiness wait or GL-error consumption.
There are at most 20 rows; unknown fields, mismatched rows and invalid scalar
values are refused. A thrown render or pixel-readback call can omit a row.
These observations distinguish a lost-context early return from a render that
advances its counter without drawing. They do not alone establish a driver or
asset cause.

Version 3 also retains at most 16 lifecycle rows. Each row contains a fixed
event kind, phase, render-frame count, context-loss flag, trusted-event flag and
preparation-call count. The observer records the existing preparation call's
return without awaiting or modifying its Promise; this is not shader readiness.
The backend projection reports only unknown, SwiftShader, llvmpipe, ANGLE or
other. Fixed browser observations count selected console categories and record
page crash, premature close and disconnect. A failed assertion permits one
bounded read of the cumulative GPU-process crash count; no read follows the
original 30 s deadline. A zero crash count does not exclude context reset or
identify its cause. No raw console message, driver identifier or extra render
is exported.

Version 4 adds a separate `eventTimings` array, one row for each retained
lifecycle event, and a `timingRefused` flag. Each row is
`[eventIndex, relativeRoundedMsOrNull, compilingGraphicsOrNull]`. The first
observed event supplies the time origin; intervals are nondecreasing integers
bounded to 60000 ms, with at most 16 rows. These are new synchronous clock and
property observations at existing callbacks. They add no timer, Promise
continuation, render retry or shader-readiness wait. Invalid observations remain
null and mark refusal. A positive preparation count means the method remains
pending; zero means its existing finally path settled, not that the GPU is
healthy. Event delivery time is not a driver reset trigger time. Older artifacts
require their frozen version-3 decoder; current consumers refuse missing or
unknown version-4 fields.

At exact `3329dfc`, automatic run `37171816468` still fails after trusted
model-await context loss, while explicit run `37171981635` passes the browser
job and original pixels/upload/cancellation. A private owned headed experiment
with one explicit `--use-angle=swiftshader` flag also exceeds the original
165-second work budget before an inner report. Its three observed Chrome births
retire and source coherence holds; no backend mode or cause is inferred from
the missing report. No unsafe SwiftShader flag or production backend change is
installed. Actual version-4 hosted timing remains a separate required check.

At exact `78a0060`, automatic run `37167152055` retains a trusted context-loss
event during model-await, before the direct pixel test, on SwiftShader. The
same-source explicit run `37167669290` passes all 20 pixels, one upload,
independent samplers and cancellation on ANGLE/Vulkan SwiftShader. Keep both
outcomes. Separate local original/control headless measurements also pass; they
do not establish the initiating operation or repair the failed headed gate.

At published `6746424ca051`, the normal hosted run `37152499835` passes the original embedded
journey on ANGLE/Vulkan SwiftShader, while the explicit diagnostic run `37152626982`
fails with decoded red bytes, zero uploads, zero draw calls and transparent black
pixels. Both results remain recorded. The new context observations require fresh
hosted execution. The earlier local success used NVIDIA; a later private forced
software attempt reaches its unchanged outer work deadline without a completed
browser/GPU report. Its observed processes retire, but it provides no verified
software backend or pixel qualification.
