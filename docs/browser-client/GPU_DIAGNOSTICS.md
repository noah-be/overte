# Embedded texture GPU diagnostics

The authored embedded-FBX journey retains its original 20 exact pixel checks,
single shared image upload, independent samplers and actual model cancellation.
An empty frame is a failed assertion even when image decoding succeeded. A
passing run does not erase a same-source failure.

On failure, the existing runner makes one bounded 500 ms read of fixed diagnostic
data. It makes no additional read after the original 30 s fixture deadline and
preserves the original failure. Version 2 retains the eleven-number frame row
and adds one paired `contextStates` row:

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

At published `6746424ca051`, the normal hosted run `37152499835` passes the original embedded
journey on ANGLE/Vulkan SwiftShader, while the explicit diagnostic run `37152626982`
fails with decoded red bytes, zero uploads, zero draw calls and transparent black
pixels. Both results remain recorded. The new context observations require fresh
hosted execution. The earlier local success used NVIDIA; a later private forced
software attempt reaches its unchanged outer work deadline without a completed
browser/GPU report. Its observed processes retire, but it provides no verified
software backend or pixel qualification.
