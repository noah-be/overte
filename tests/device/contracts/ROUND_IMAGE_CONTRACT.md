# Shared rounded avatar image without shader masking

RoundImage now draws its already-loaded Qt Image directly into Canvas.Image,
clipped to a rounded path, with the original native Rectangle border above it.
The source, fillMode, status, progress, radius and border API remains available.
Qt Image still owns source loading and cache/status transitions; Canvas does not
load the URL a second time and creates no export. Invalid/loading/empty images
clear the drawing. Layout/radius/fill-mode and completed source changes repaint.

Stretch, aspect-fit, aspect-crop, pad, tile, horizontal tile and vertical tile
retain the default centered Qt Image layout. Tiling uses explicit CPU draws;
large/tiny-tile performance and native/DPR behavior are not accepted here.
Qt Image and Canvas interpolation differ at source color discontinuities. The
fixture records that finding and compares interior regions for layout rather
than claiming every edge pixel is identical. Rounded clipping now has normal
Canvas antialiasing; it is not the old shader's binary alpha-threshold algorithm.

The full actual RoundImage QML runs in a real Qt6 software QQuickView. Tests
compare all seven fill-mode layouts to a real Qt Image reference, then check
rounded corners, visible center, border, ready/progress, empty and failed source
clearing. A real counted QQmlImageProvider confirms one request, including after
repainting. The pattern asset/provider are explicit test inputs; there is no
avatar/server/device artifact acceptance. The previous complete RoundImage and
TransparencyMask source files fail because expected image pixels are transparent
on this software backend. Initial filtering and pattern-drawing probe failures
are retained with the final evidence.

RoundImage's old TransparencyMask connection is removed. The legacy standalone
TransparencyMask components remain in source for other possible consumers;
absence of another static reference does not prove dynamic QML reachability.
Full retained QML closure, native MoltenVK present, avatar journey, visual quality,
thread/resource performance and all original SH003/SH007/IO009 gates remain open.
