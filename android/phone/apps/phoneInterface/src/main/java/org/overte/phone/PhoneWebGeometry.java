// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;

/** Pixel mapping from the actual QML scene into its measured Qt Android surface. */
final class PhoneWebGeometry {
    static int[] map(int sceneWidth, int sceneHeight, int[] scene, int[] surface, int[] clip) {
        if (sceneWidth <= 1 || sceneHeight <= 1 || sceneWidth > 32768 || sceneHeight > 32768
                || scene == null || surface == null || clip == null
                || scene.length != 4 || surface.length != 4 || clip.length != 4
                || scene[2] <= scene[0] || scene[3] <= scene[1]
                || surface[2] <= surface[0] || surface[3] <= surface[1]) return null;
        double sx = (surface[2] - surface[0]) / (double) sceneWidth;
        double sy = (surface[3] - surface[1]) / (double) sceneHeight;
        int left = (int) Math.floor(surface[0] + scene[0] * sx);
        int top = (int) Math.floor(surface[1] + scene[1] * sy);
        int right = (int) Math.ceil(surface[0] + scene[2] * sx);
        int bottom = (int) Math.ceil(surface[1] + scene[3] * sy);
        int cl = Math.max(left, Math.max(surface[0], clip[0])), ct = Math.max(top, Math.max(surface[1], clip[1]));
        int cr = Math.min(right, Math.min(surface[2], clip[2])), cb = Math.min(bottom, Math.min(surface[3], clip[3]));
        if (cr <= cl || cb <= ct) return null;
        return new int[] { left, top, right, bottom, cl, ct, cr, cb };
    }
}
