// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <metal_stdlib>
using namespace metal;

struct BootstrapVertex {
    float4 position [[position]];
    half4 color;
};

vertex BootstrapVertex overteBootstrapVertex(uint vertexID [[vertex_id]]) {
    constexpr float2 positions[] = {
        float2(0.0, 0.45),
        float2(-0.4, -0.3),
        float2(0.4, -0.3),
    };
    constexpr half4 colors[] = {
        half4(0.44h, 0.43h, 0.70h, 1.0h),
        half4(0.95h, 0.95h, 1.0h, 1.0h),
        half4(0.20h, 0.55h, 0.95h, 1.0h),
    };

    BootstrapVertex output;
    output.position = float4(positions[vertexID], 0.0, 1.0);
    output.color = colors[vertexID];
    return output;
}

fragment half4 overteBootstrapFragment(BootstrapVertex input [[stage_in]]) {
    return input.color;
}

