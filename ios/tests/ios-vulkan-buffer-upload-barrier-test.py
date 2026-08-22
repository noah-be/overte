#!/usr/bin/env python3
"""Guard Vulkan transfer visibility for every GPU buffer consumer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
buffer_header = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKBuffer.h"
).read_text(encoding="utf-8")
buffer_source = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKBuffer.cpp"
).read_text(encoding="utf-8")
backend_source = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp"
).read_text(encoding="utf-8")

for stage in (
    "VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT",
    "VK_PIPELINE_STAGE_VERTEX_INPUT_BIT",
    "VK_PIPELINE_STAGE_VERTEX_SHADER_BIT",
    "VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT",
    "VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT",
):
    if stage not in buffer_header:
        raise SystemExit(f"uploaded buffers no longer wait for consumer stage: {stage}")

for usage, access in (
    ("gpu::Buffer::UniformBuffer", "VK_ACCESS_UNIFORM_READ_BIT"),
    ("gpu::Buffer::ResourceBuffer", "VK_ACCESS_SHADER_READ_BIT"),
    ("gpu::Buffer::IndexBuffer", "VK_ACCESS_INDEX_READ_BIT"),
    ("gpu::Buffer::VertexBuffer", "VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT"),
    ("gpu::Buffer::IndirectBuffer", "VK_ACCESS_INDIRECT_COMMAND_READ_BIT"),
):
    if f"usage & {usage}" not in buffer_source or access not in buffer_source:
        raise SystemExit(f"uploaded {usage} data lacks {access} visibility")

if buffer_source.count(".dstAccessMask = getReadAccessMask(),") != 2:
    raise SystemExit("immediate and delayed Vulkan uploads must use typed read access")
if "READ_PIPELINE_STAGES" not in buffer_source:
    raise SystemExit("immediate Vulkan uploads lost their consumer-stage wait")
if "VKBuffer::READ_PIPELINE_STAGES" not in backend_source:
    raise SystemExit("batched Vulkan uploads lost their consumer-stage wait")

print(
    "Vulkan buffer upload barrier valid: vertex, index, indirect, uniform, and "
    "resource reads are visible"
)
