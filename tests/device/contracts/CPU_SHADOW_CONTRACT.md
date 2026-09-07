# CPU shadows for retained QML sources

Nine production callers use CpuDropShadow: DefaultFrameDecoration, FilterBar,
TabletButton, SquareLabel, ShadowRectangle, ShadowGlyph, ShadowImage and
AvatarProjectCard, plus all three Card effects. Each effect is placed before its visible source in sibling
paint order, preserving explicit z values. The component draws only the shadow;
it does not overlay an older captured foreground on live text or images.
Card retains its legacy dropSamples property for caller compatibility; it no longer
tunes the CPU kernel. dropSpread is real-valued and binds to the CPU spread.
Keyboard's unused graphical-effects import is removed.

The source tree is observed through item/image/text/Canvas changes and descendant
loaders, without a frame timer. Capture is single-flight. Content updates coalesce
without invalidating every in-flight frame; source/visibility/window changes
invalidate the generation and clear retained images. Component fields retain one active and one pending completed capture, plus
at most one in-flight grab; Qt-internal and cache lifetimes are not proved. A pending image is published only
when Canvas has loaded it and its generation/source context still applies. An
ancestor source is excluded from both tree observation and capture.

The CPU renderer uses an explicit separable Gaussian alpha filter with radius
support ceil(radius), sigma max(0.5,radius/2), transparent boundaries, and bilinear
sampling for offsets. Canvas.Image retains the output. putImageData uses its full
seven-argument area form, verified on the local Qt software renderer. Nonfinite
radius/offset values map to zero; negative radius maps to zero. This does not
assert equivalence to the old shader's kernel, samples, cached or spread API.
The explicit local spread contract maps finite values to [0,1], nonfinite values
to zero, and transforms blurred alpha a to min(255,a/(1-spread)). At one,
positive coverage becomes 255 while zero coverage stays zero. Shadow color
opacity is applied afterward. Spread changes repaint the retained capture.
This is a documented CPU replacement, not a verified old-shader transfer curve.
No general maximum-size or native frame/memory budget is qualified here.

Qt's Rectangle.gradient and GradientStop fields in the tested runtime lack
ordinary property notify signals. ShadowRectangle therefore exposes a reactive
wrapper gradient property, binds it to Rectangle and passes it to the effect.
Existing gradients are observed through their aggregate updated signal; border
updates also observe penChanged. These metadata signal dependencies are explicit;
no Qt private header or graphics ABI is used. Arbitrary unnotified gradient
replacement on another source item needs an explicit sourceGradient binding.
Qt5/native compatibility and version-specific signal behavior remain unqualified.

The repository test executes complete ShadowRectangle/ShadowGlyph/ShadowImage,
RoundImage and HiFiGlyphs components with real Qt software pixels. The glyph font
is an explicit fixture override and PNGs are generated fixtures. It covers source
replacement/clearing, gradient replacement and stop transparency, size/visibility,
window reappearance, and a continuously painted Canvas. That live check requires
visible shadow frames and verifies that current source pixels are not overwritten.
Eight other exact production effect items (including Card's three) execute with source/window/style seams;
the complete six surrounding controls are not instantiated by that test.

Short putImageData, omitted descendant painted notification and invalidated live
frames each fail meaningful pixel assertions. Additional local lifecycle evidence
covers nested source visibility/opacity and ancestor-source refusal/restoration.
Recorded host settle times include scheduling and rendering; they are neither
kernel benchmarks nor approved platform budgets.
Full retained-surface layout/semantics, old-shader pixel comparison, native Qt5/
iOS rendering, hardware performance and original39 acceptance remain open.
