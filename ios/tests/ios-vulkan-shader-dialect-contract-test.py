#!/usr/bin/env python3
"""Guard the shader payload selected by the iOS Vulkan backend."""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
shaders = (ROOT / "libraries/shaders/src/shaders/Shaders.cpp.in").read_text(
    encoding="utf-8"
)
shader_api = (ROOT / "libraries/gpu/src/gpu/Shader.cpp").read_text(encoding="utf-8")
vulkan_cache = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKPipelineCache.cpp"
).read_text(encoding="utf-8")

vulkan_payload = (
    "static const std::vector<Dialect> ALL_DIALECTS_VULKAN"
    "{ { Dialect::glsl450 } };"
)
if vulkan_payload not in shaders:
    raise SystemExit("Vulkan does not own an explicit GLSL 450/SPIR-V payload")

vulkan_case = """case hifi::properties::GraphicsAPI::Vulkan:
            // The Vulkan backend consumes the 450 SPIR-V payload and its
            // matching reflection. Falling through to the GLES dialect leaves
            // every source without the data requested by VKPipelineCache.
            return ALL_DIALECTS_VULKAN;"""
if vulkan_case not in shaders:
    raise SystemExit("Vulkan still falls through to the GLES shader dialect")

gles_case = """case hifi::properties::GraphicsAPI::GLES32:
            return ALL_DIALECTS_32ES;"""
if gles_case not in shaders:
    raise SystemExit("GLES 3.2 lost its explicit 310es shader payload")

if 'throw std::runtime_error("Invalid graphics API");' not in shaders:
    raise SystemExit("unknown graphics APIs do not fail closed")

reflection_start = shader_api.index("Shader::Reflection Shader::getReflection() const")
reflection_end = shader_api.index("Shader::~Shader()", reflection_start)
reflection = shader_api[reflection_start:reflection_end]
if "auto DEFAULT_DIALECT = Dialect::glsl450;" not in reflection:
    raise SystemExit("Vulkan reflection no longer defaults to the 450 payload")
if "GraphicsAPI::Vulkan" in reflection:
    raise SystemExit("Vulkan reflection is unexpectedly redirected from GLSL 450")

if "source.dialectSources.find(shader::Dialect::glsl450)" not in vulkan_cache:
    raise SystemExit("Vulkan pipeline cache no longer consumes the GLSL 450 SPIR-V payload")

print(
    "iOS Vulkan shader dialect contract valid: runtime sources, reflection, "
    "and pipeline SPIR-V all use GLSL 450"
)
