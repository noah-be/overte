# Shared native section and window gradients

ContentSection, TabletContentSection and ScrollingWindow now use the native
Rectangle.gradient property instead of a GraphicalEffects LinearGradient. Their
vertical color stops, size/anchors and visibility expressions are unchanged;
shader-only start/end/cache properties and unused module imports are removed.
TabletContentSection remains intentionally hidden by its original default.

The focused test compiles each actual complete gradient item into a small Qt
Quick context with explicit layout/palette substitutes, then reads real software
renderer pixels. It checks original visibility, color or alpha progression and
explicit hiding. The hidden Tablet item is enabled only inside the drawing test.
Collapsing the gradient-stop interval in scratch fails the pixel assertions.
This is not full window/section layout, accessibility or native target evidence.

Source review also identified RoundImage -> TransparencyMask as an open
functional path: ShaderEffectSource hides the source images, and the shader
combines their pixels. A decorative-shadow exemption cannot cover that path.
Full retained effects/import closure and original SH003/SH007 acceptance remain
open; no capability is marked accepted from these isolated drawing checks.
