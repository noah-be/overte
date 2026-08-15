#!/usr/bin/env python3
"""Guard Vulkan pipeline keys for draws without vertex input formats."""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
pipeline_cache = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKPipelineCache.cpp"
).read_text(encoding="utf-8")
backend = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text(
    encoding="utf-8"
)

key_start = pipeline_cache.index(
    "std::string Cache::Pipeline::getKey(const vks::Context& context) const"
)
key_end = pipeline_cache.index("VkStencilOpState Cache::getStencilOp", key_start)
key_body = pipeline_cache[key_start:key_end]

required_key_fragments = (
    "const auto vertexFormat = gpu::acquire(format);",
    'const std::string formatKey = vertexFormat',
    '? "present:" + vertexFormat->getKey()',
    ': "absent";',
    '+ "_" + formatKey',
)
for fragment in required_key_fragments:
    if fragment not in key_body:
        raise SystemExit(
            f"Vulkan pipeline key lost its optional-format discriminator: {fragment}"
        )

if "format->getKey()" in key_body:
    raise SystemExit("Vulkan pipeline key still dereferences an absent vertex format")

pipeline_start = pipeline_cache.index(
    "const Cache::PipelineLayout& Cache::getPipeline(const vks::Context& context)"
)
pipeline_body = pipeline_cache[pipeline_start:]
if "if (pipelineState.format)" not in pipeline_body:
    raise SystemExit("Vulkan pipeline creation no longer supports format-free draws")
if "gpu::acquire(pipelineState.format)" not in pipeline_body:
    raise SystemExit("Vulkan vertex input no longer acquires its guarded format")

input_start = backend.index("void VKBackend::do_setInputFormat")
input_end = backend.index("void VKBackend::do_setInputBuffer", input_start)
input_body = backend[input_start:input_end]
for fragment in (
    "_cache.pipelineState.setVertexFormat(format);",
    "if (format)",
    "reset(_input._format);",
    "_input._formatKey.clear();",
):
    if fragment not in input_body:
        raise SystemExit(
            f"Vulkan input-format state lost its valid null transition: {fragment}"
        )

print(
    "iOS Vulkan pipeline key contract valid: absent and present vertex formats "
    "are distinct, and format-free draws remain supported"
)
