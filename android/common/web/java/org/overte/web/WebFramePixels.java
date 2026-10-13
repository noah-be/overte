// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.web;

import java.nio.ByteBuffer;

/** GL RGBA bottom-up rows become the existing little-endian premultiplied QImage ARGB32 (BGRA) contract. */
final class WebFramePixels {
    static void pack(ByteBuffer source, ByteBuffer destination, int width, int height, int rowStride, int pixelStride) {
        if (width < 1 || height < 1 || width > 2048 || height > 2048 || pixelStride < 4
                || rowStride < (long) width * pixelStride
                || source.limit() < (long) (height - 1) * rowStride + (long) (width - 1) * pixelStride + 4
                || destination.capacity() < (long) width * height * 4) throw new IllegalArgumentException("invalid frame layout");
        destination.clear();
        for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
            int input = (height - y - 1) * rowStride + x * pixelStride;
            int output = (y * width + x) * 4;
            destination.put(output, source.get(input + 2)); destination.put(output + 1, source.get(input + 1));
            destination.put(output + 2, source.get(input)); destination.put(output + 3, source.get(input + 3));
        }
        destination.position(0); destination.limit(width * height * 4);
    }
}
