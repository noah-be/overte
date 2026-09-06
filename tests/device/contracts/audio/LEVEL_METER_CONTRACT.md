# Shared audio level rendering without shader effects

InputPeak, MicBar, MicBarApplication and the audio settings noise meter now use
one LevelMeter. It draws the gutter and a bounded level into a Canvas.Image CPU
surface, with horizontal or bottom-up vertical color progression. This avoids
requiring a GraphicalEffects shader for the signal-level information on iOS's
software QML backend. Invalid/nonfinite levels draw only the gutter; finite
values clamp to 0..1. Existing mute, push-to-talk and gate bindings choose the
same visibility or zero-level states. The QML resource generator includes the
new QML file through its existing recursive resource collection.

The host test loads the complete actual InputPeak and LevelMeter with real Qt
Quick software rendering and reads the resulting pixels in memory. Its sole
AudioScriptingInterface boundary supplies the muted property. It checks green
fill, unfilled gutter, zero/full/NaN changes, mute image change and vertical
fill. A scratch-only white-fill mutation fails the green-pixel assertion.
There are no exported screenshots. These are host pixels, not MoltenVK present
or artifact/hardware evidence. The other three caller bindings are source-reviewed;
the complete audio application and microphone native operations are not emulated.

Other uses of GraphicalEffects (including microphone icon overlays), all retained
QML import/effect closure, full native rendering and original SH003/SH006/SH007
acceptance remain open. This change does not certify every audio control.

## Microphone state icon tinting

Both MicBar variants now use TintedImage with their original SVG choices and
state-color bindings. The Canvas.Image implementation colors the image through
source-in compositing, retaining its alpha silhouette on the software backend.
Source changes unload the prior image; a late load notification paints only the
current source. Empty/unavailable sources clear the drawing. This removes the
remaining GraphicalEffects dependency from both microphone-bar QML files.

`test_tinted_image.py` loads the actual mic-mute SVG and actual TintedImage on
real Qt Quick software rendering. Red/blue color changes, opaque and transparent
pixels, and source clearing are checked in memory. A source-over mutation loses
the transparent silhouette and fails. The MicBar state bindings are source-
reviewed; their entire application context and native microphone are not supplied
by this fixture. This does not close all retained QML effects or native UI gates.

The simplified UI InputPeak also consumes SharedAudio.LevelMeter. Its existing
showMuted alias remains independent of AudioScriptingInterface.muted. The real
software-pixel harness now loads both complete InputPeak variants and checks
level/NaN/color/visibility changes in each, then the shared vertical meter.
TabletMenu's backward glyph now uses its native text color property and the
existing hover color assignments, removing its redundant shader overlay; this
small caller change is source-reviewed, not a full tablet navigation test.
