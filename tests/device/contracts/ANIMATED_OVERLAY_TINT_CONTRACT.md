# Animated image overlay tint through public Qt capture

ImageOverlay now uses ItemTint in place of ColorOverlay. Actual AnimatedImage,
source/frame decoding, root opacity and script update functions remain.
Crop margins now follow overlay geometry and each ready source size. Zero crop
extents retain their automatic meaning rather than being overwritten by the first
image size; invalid or unavailable dimensions clear margins to finite defaults. ItemTint captures the visible source using public grabToImage, retains the
in-memory result URL and paints its alpha through Canvas.Image. No save/export call
is introduced. One capture is in flight; arriving frames coalesce into a follow-up.
Source/geometry/visibility generations discard obsolete results. The source's
original visible drawing remains below the tint, including partial tint alpha.

The complete actual ImageOverlay, Overlay and ItemTint run on a real Qt6 software
QQuickView. Hifi's otherwise unused module is registered as a test seam; there is
no fake overlay implementation. A generated two-frame transparent GIF verifies
repeated explicit frame selection, automatic playback of both frames, source alpha,
real cropping and tint pixels.
Script updates also verify partial opacity compositing, replacement and empty
sources, hide/show, and destruction while a fresh source is pending. Removing actual frame
refresh fails the frame pixel assertion. Initial alpha probe failure recorded the
incorrect grouped-opacity expectation: Qt propagates opacity to individual child
items, so the fixture now checks the resulting source-over composition.

This proves the tested host Qt paths only. Playback cadence/performance,
large images, slow rendering, every late-callback lifetime, Qt5/native backend,
DPR and physical overlay journey remain unaccepted. The fixture checks an explicit
crop after a 64-to-96 overlay resize and automatic extents across 32x32 and 64x48
source replacements. The former production path fails the resize assertion.
No full original39 render, privacy or artifact acceptance is claimed.
