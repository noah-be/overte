# NameCard audio meter on the Shared CPU renderer

The actual NameCard VU subtree now uses Shared LevelMeter. Its color positions
remain relative to the full gain-adjusted width: low #2c8e72 at 0, middle #1fc6a6
at .9 and high #ea4c5f at .91 through 1. Existing gain geometry, rounded gray base,
zero-gain marker, line and selected/present/nearby visibility remain. Audio levels
are clamped to [0,1], with nonfinite input empty, by the existing Shared painter.
The NameCard GraphicalEffects import and its last LinearGradient are removed.

LevelMeter adds configurable middle/high stop positions with unchanged defaults
(.5/1) for existing callers. The complete actual NameCard VU subtree and actual
LevelMeter run in Qt6 software rendering. Card selection/audio/gain, palette,
layout anchors and slider values are explicit surrounding context seams. Pixel
checks cover partial/full fill, the 91-percent red threshold, changed gain width,
zero/negative/NaN/over-range input and selected/own-card visibility. Changing the
actual high stop to 1 fails the red threshold assertion. Existing complete
InputPeak variants retain their separate software pixel regression checks.

This does not prove the whole NameCard or native Qt5/device journey, exact shader
antialiasing equivalence, accessibility/audio capture, or all remaining effects.
Radial gradients and dynamic shadow/mask callers remain separate source work.
