// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

/** CSS-size texture coordinates and Android-density view coordinates share one transform. */
final class WebTextureScale {
    final int width, height, layoutWidth, layoutHeight;
    final float density;
    WebTextureScale(int requestedWidth, int requestedHeight, float displayDensity) {
        if (requestedWidth < 1 || requestedHeight < 1 || !Float.isFinite(displayDensity) || displayDensity <= 0)
            throw new IllegalArgumentException("invalid texture dimensions");
        double ratio = Math.min(1.0, 2048.0 / Math.max(requestedWidth, requestedHeight));
        width = Math.max(1, (int)Math.round(requestedWidth * ratio));
        height = Math.max(1, (int)Math.round(requestedHeight * ratio));
        density = displayDensity;
        double physicalWidth = width * (double)density, physicalHeight = height * (double)density;
        if (physicalWidth > 8192 || physicalHeight > 8192) throw new IllegalArgumentException("texture viewport exceeds budget");
        layoutWidth = Math.max(1, (int)Math.round(physicalWidth));
        layoutHeight = Math.max(1, (int)Math.round(physicalHeight));
    }
    float pointer(float coordinate) { return coordinate * density; }
}
