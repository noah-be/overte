// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <metal_stdlib>
using namespace metal;

struct BootstrapVertex {
    float4 position [[position]];
    half4 color;
};

struct SceneUniforms {
    float aspect;
    float yaw;
    float pitch;
    float zoom;
    float time;
    uint sceneLoaded;
    uint attendance;
    uint domainSeed;
};

float4x4 perspective(float aspect, float zoom) {
    const float f = 1.0 / tan(0.55 / max(zoom, 0.35));
    return float4x4(float4(f / max(aspect, 0.1), 0, 0, 0),
                    float4(0, f, 0, 0),
                    float4(0, 0, -1.002, -1),
                    float4(0, 0, -0.2002, 0));
}

float3 cubeVertex(uint vertexID) {
    constexpr float3 corners[] = {
        float3(-1,-1, 1), float3( 1,-1, 1), float3( 1, 1, 1), float3(-1, 1, 1),
        float3(-1,-1,-1), float3( 1,-1,-1), float3( 1, 1,-1), float3(-1, 1,-1)
    };
    constexpr ushort indices[] = {
        0,1,2, 0,2,3, 1,5,6, 1,6,2, 5,4,7, 5,7,6,
        4,0,3, 4,3,7, 3,2,6, 3,6,7, 4,5,1, 4,1,0
    };
    return corners[indices[vertexID]];
}

vertex BootstrapVertex overteSceneVertex(uint vertexID [[vertex_id]],
                                         uint instanceID [[instance_id]],
                                         constant SceneUniforms& uniforms [[buffer(0)]]) {
    float3 position = cubeVertex(vertexID);
    const uint column = instanceID % 5;
    const uint row = instanceID / 5;
    const float seedHeight = float((instanceID * 17 + uniforms.domainSeed) % 7) * 0.08;
    const float scale = instanceID == 25 ? 5.5 : 0.28 + seedHeight;
    const float3 center = instanceID == 25
        ? float3(0, -1.15, 0)
        : float3((float(column) - 2.0) * 1.05, -0.72 + scale, (float(row) - 2.0) * 1.05);
    position *= float3(instanceID == 25 ? 1.0 : 0.72, scale,
                       instanceID == 25 ? 1.0 : 0.72);
    position += center;

    const float cy = cos(uniforms.yaw), sy = sin(uniforms.yaw);
    const float cp = cos(uniforms.pitch), sp = sin(uniforms.pitch);
    position = float3(cy * position.x + sy * position.z, position.y,
                      -sy * position.x + cy * position.z);
    position = float3(position.x, cp * position.y - sp * position.z,
                      sp * position.y + cp * position.z);
    position.z -= 7.5;

    BootstrapVertex output;
    output.position = perspective(uniforms.aspect, uniforms.zoom) * float4(position, 1);
    const half accent = half((instanceID + uniforms.attendance) % 5) * 0.055h;
    output.color = instanceID == 25
        ? half4(0.05h, 0.10h, 0.16h, 1.0h)
        : half4(0.18h + accent, 0.48h + accent, 0.82h, 1.0h);
    return output;
}

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
