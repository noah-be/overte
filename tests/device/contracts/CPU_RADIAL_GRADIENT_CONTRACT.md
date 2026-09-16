# Retained radial backgrounds

Frame and Web3DSurfaceAndroid use the shared Canvas.Image CpuRadialGradient.
Colors and stop positions are retained. The gradient center is the item center;
the two unit axes scale independently to item width and height. A stop at 0.5
reaches each edge midpoint, following the original Frame source comment. Frame's
size, offsets and focus/content/gradientsSupported visibility binding are retained.
The Android placeholder retains its URL text and hand overlay.

The component redraws after geometry, visibility, Canvas availability or stops
array replacement. Stops are value data; callers replace the array to update it.
The two production callers use fixed, valid stop arrays. This component does not
implement a general QtGraphicalEffects API, masks, offsets or blur. Canvas.Image
retains the CPU image without an additional cached shader layer.

The focused test executes both exact production gradient items and the registered
component through its real qmldir using Qt Quick's software renderer. Outer window,
content and gradient-capability context are fixtures. Image pixels verify opaque
background colors, shadow alpha falloff, transparent corners, independent axes,
resize, visibility/focus/content transitions, hide/show and clearing stops. Wrong
axis scaling and a moved shadow stop are required negative failures.

The local environment lacks the old Qt5 graphical-effects implementation, so this
is not a pixel-difference comparison with that shader. Complete Frame decoration,
Android overlays, hardware render paths, scale factors, performance budgets and
native visual acceptance remain open. No original39 node is accepted by this test.
