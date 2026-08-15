// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

// A deterministic local procedural-material target for the macOS quality matrix.
vec4 getProceduralColor() {
    vec2 cell = floor((_position.xz + vec2(0.5)) * 8.0);
    float checker = mod(cell.x + cell.y, 2.0);
    return mix(vec4(0.08, 0.95, 0.25, 1.0), vec4(0.85, 0.10, 0.90, 1.0), checker);
}
