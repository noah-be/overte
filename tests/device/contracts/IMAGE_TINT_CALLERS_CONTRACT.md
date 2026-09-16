# BubbleIcon and Card badge through Shared ItemTint

BubbleIcon's actual image and Card's actual standalone badge now feed Shared
ItemTint instead of ColorOverlay. Original image URLs, sourceSize/fill mode,
geometry, color bindings and interaction/visibility logic remain. BubbleIcon's
last GraphicalEffects import is removed; Card still needs its shadow effects.

The full actual BubbleIcon runs on Qt6 software rendering with real SVG content,
MouseArea click dispatch and explicit AvatarInputs/Users/Tablet context seams.
Opaque white pixels, a test-driven green tint, enable/toggle/sound and hide/show
are checked. Card's actual image plus tint subtree runs with only surrounding
layout/color/state seams, checking visible pixels, disable/enable with height
zero, concurrency visibility and window hide/show. Initial hover position is
host-controlled and is not treated as a fixed 0.7-opacity acceptance condition.

These callers revealed two actual ItemTint start/resize gaps. Capture now waits
for a visible source window and retries on its visibility transition. After a
capture is painted, one completion-driven deferred repaint presents Canvas.Image
content following a zero-size resize. This is bounded per capture, without a
continuous timer or additional capture. Probes showed that the missing badge's
retained capture already had 355 nonempty pixels; an explicit repaint restored
145 solid green output pixels. Waiting for a frame swap did not fix the issue
and that experiment is absent from production. Removing the actual follow-up
paint flag fails the zero-height re-enable test. The full existing animated
overlay fixture checks frame playback, crop, source/size, opacity and lifetime
regressions on the changed Shared component.

No full Card/native Qt5/DPR/performance or exhaustive asynchronous lifetime proof
is claimed. The extra paint per capture has not been profiled on devices. No
image export/save introduced. Original39 render/privacy acceptance remains open.
