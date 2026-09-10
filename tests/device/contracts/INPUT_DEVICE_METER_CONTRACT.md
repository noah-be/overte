# Complete simplified microphone button on the software renderer

InputDeviceButton now uses Shared TintedImage and LevelImage instead of two
ColorOverlays, an OpacityMask and a LinearGradient. Its actual SVG source/state,
geometry, theme colors, MouseArea and AudioScriptingInterface bindings remain.
The input level is finite-clamped to [0,1]. LevelImage paints a source-alpha-masked
low/middle/high gradient from bottom to top, with grey above the fill boundary,
consistent with Shared LevelMeter. This is not a pixel-equivalence assertion for
the old rotated shader gradient. All GraphicalEffects and unused style imports
are removed. Canceling a grabbed mouse contact clears the button-owned pushingToTalk press
just as release does. Hiding the button or disabling push-to-talk also clears it; actual capture termination and concurrent input arbitration are
separate native acceptance requirements.

TintedImage exposes its painting step as an overridable QML function. Its source
loading and Canvas availability behavior are shared by LevelImage; the default
solid tint remains unchanged. No second independent source loader is introduced.

The full actual component loads in real Qt6 software QQuickView with actual
SimplifiedConstants and original SVG assets. Audio state and Tablet sound/enums
are explicit test seams. Pixels prove visible and masked initial, half/full,
muted and clipping states, grey/green fill positions and invalid-level bounds.
Real Qt mouse click, press, release and ungrab events exercise mute and push-to-talk.
Replacing the meter painting with a solid tint fails pixels; removing the actual
onCanceled handler fails the ungrab state assertion. The base tint fixture also
remains passing. No native audio capture/permission lifecycle, complete top bar,
Qt5/native renderer or original 39-node acceptance is claimed.
