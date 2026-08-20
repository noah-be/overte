#!/usr/bin/env python3
"""Guard Vulkan pipeline identity and format handling."""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
pipeline_cache = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKPipelineCache.cpp"
).read_text(encoding="utf-8")
backend = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text(
    encoding="utf-8"
)
tone_mapping = (
    ROOT / "libraries/render-utils/src/ToneMapAndResampleTask.cpp"
).read_text(encoding="utf-8")
pipeline_header = (
    ROOT / "libraries/gpu-vk/src/gpu/vk/VKPipelineCache.h"
).read_text(encoding="utf-8")
vulkan_tools = (ROOT / "libraries/vk/src/vk/VulkanTools.h").read_text(
    encoding="utf-8"
)
vulkan_debug = (ROOT / "libraries/vk/src/vk/VulkanDebug.cpp").read_text(
    encoding="utf-8"
)
vulkan_context = (ROOT / "libraries/vk/src/vk/Context.cpp").read_text(
    encoding="utf-8"
)

tone_mapping_batch = tone_mapping.index(
    'gpu::doInBatch("Resample::run", args->_context, [&](gpu::Batch& batch) {'
)
tone_mapping_pipeline = tone_mapping.index("batch.setPipeline(", tone_mapping_batch)
tone_mapping_reset = tone_mapping.index("batch.setInputFormat({});", tone_mapping_batch)
if tone_mapping_reset > tone_mapping_pipeline:
    raise SystemExit("tone mapping must clear inherited vertex input before selecting its pipeline")

for fragment in (
    '#include <os/log.h>',
    'std::to_string(static_cast<int>(res))',
    'os_log_fault(OS_LOG_DEFAULT, "OVERTE_IOS_VULKAN_FATAL %{public}s"',
    'std::cerr << "OVERTE_IOS_VULKAN_FATAL "',
):
    if fragment not in vulkan_tools:
        raise SystemExit(
            f"iOS Vulkan failures no longer retain their exact result in unified logs: {fragment}"
        )

for fragment in (
    "OVERTE_IOS_VULKAN_DEBUG %{public}s",
    "os_log_fault(OS_LOG_DEFAULT",
    "os_log_error(OS_LOG_DEFAULT",
    "if (!vkCreateDebugUtilsMessengerEXT || !vkDestroyDebugUtilsMessengerEXT)",
    "Could not create Vulkan debug messenger:",
):
    if fragment not in vulkan_debug:
        raise SystemExit(
            f"MoltenVK debug-utils diagnostics are not fail-closed on iOS: {fragment}"
        )

for fragment in (
    "MoltenVK reports driver-side shader conversion",
    "if (enableValidation",
    "|| enableDebugMarkers",
    "debug::setupDebugging(instance);",
    "debug::freeDebugCallback(instance);",
):
    if fragment not in vulkan_context:
        raise SystemExit(
            f"release iOS lost its MoltenVK debug messenger lifecycle: {fragment}"
        )

for fragment in (
    "inputAssembly.topology == VK_PRIMITIVE_TOPOLOGY_LINE_STRIP",
    "inputAssembly.topology == VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP",
    "inputAssembly.primitiveRestartEnable = stripTopology ? VK_TRUE : VK_FALSE;",
    'makePipelineDetails("OVERTE_IOS_VULKAN_PIPELINE_CREATE", nullptr)',
    "OVERTE_IOS_VULKAN_PIPELINE_CONTEXT",
    "getVulkanShaderDiagnosticFingerprint(vertexSpirv)",
    "getVulkanShaderDiagnosticFingerprint(fragmentSpirv)",
    '<< " vertex_bindings=" << builder.vertexInputState.bindingDescriptions.size()',
    '<< " vertex_attributes=" << builder.vertexInputState.attributeDescriptions.size()',
    '<< " primitive_restart=" << builder.inputAssemblyState.primitiveRestartEnable',
    '<< " vertex_descriptors=" << pipelineLayout.vertexReflection.descriptorCount()',
    "binding.binding < MAX_NUM_INPUT_BUFFERS",
    '<< "/set=" << strideWasSet',
    'os_log_info(OS_LOG_DEFAULT, "%{public}s", createDetails.c_str())',
    'makePipelineDetails("OVERTE_IOS_VULKAN_PIPELINE_CREATED", nullptr)',
    'os_log_info(OS_LOG_DEFAULT, "%{public}s", createdDetails.c_str())',
    'os_log_fault(OS_LOG_DEFAULT, "%{public}s", failureDetails.c_str())',
):
    if fragment not in pipeline_cache:
        raise SystemExit(
            f"failed iOS Vulkan pipelines no longer emit bounded state context: {fragment}"
        )

key_start = pipeline_cache.index(
    "std::string Cache::Pipeline::getKey(const vks::Context& context, Cache& cache) const"
)
key_end = pipeline_cache.index("VkStencilOpState Cache::getStencilOp", key_start)
key_body = pipeline_cache[key_start:key_end]

required_key_fragments = (
    "const auto vertexFormat = gpu::acquire(format);",
    'const std::string formatKey = vertexFormat',
    '? "present:" + vertexFormat->getKey()',
    ': "absent";',
    'key += "_" + formatKey;',
)
for fragment in required_key_fragments:
    if fragment not in key_body:
        raise SystemExit(
            f"Vulkan pipeline key lost its optional-format discriminator: {fragment}"
        )

if "format->getKey()" in key_body:
    raise SystemExit("Vulkan pipeline key still dereferences an absent vertex format")

for fragment in (
    "cache.getShaderIdentity(pipelineOwner)",
    'std::string key = "shader:" + std::to_string(shaderIdentity);',
):
    if fragment not in key_body:
        raise SystemExit(
            f"Vulkan dynamic pipeline identity lost its payload boundary: {fragment}"
        )
if "makeProgramId(vertexShader.id, fragmentShader.id)" in key_body:
    raise SystemExit(
        "Vulkan pipeline identity still aliases all INVALID_SHADER programs"
    )

helper_start = pipeline_cache.index(
    "std::string getVulkanShaderCacheKey(const shader::Source& source,"
)
helper_end = pipeline_cache.index("} // namespace", helper_start)
helper_body = pipeline_cache[helper_start:helper_end]
for fragment in (
    '"stage:" + std::to_string(static_cast<uint32_t>(stage))',
    "source.id != shader::INVALID_SHADER",
    'key += "static:" + bytesToAscii(source.id);',
    'key += "dynamic:" + std::to_string(spirv.size()) + ":"',
    "if (!spirv.empty())",
    "key.append(reinterpret_cast<const char*>(spirv.data()), spirv.size());",
):
    if fragment not in helper_body:
        raise SystemExit(
            f"Vulkan shader-module identity is not exact for dynamic payloads: {fragment}"
        )

if "std::unordered_map<std::string, VkShaderModule> moduleMap;" not in pipeline_header:
    raise SystemExit("Vulkan shader module cache is still keyed only by numeric shader ID")
for fragment in (
    "std::weak_ptr<gpu::Pipeline> owner;",
    "std::unordered_map<const gpu::Pipeline*, ShaderIdentityEntry> shaderIdentityMap;",
    "uint64_t nextShaderIdentity { 1 };",
    "std::weak_ptr<gpu::Pipeline> _pipelineOwner;",
    "_pipelineOwner = pipeline;",
    "Cache::getShaderIdentity(const gpu::PipelinePointer& pipeline)",
    "existing->second.owner.lock()",
    "getValidatedVulkanShaderSpirv(shaders[0]->getSource(), VK_SHADER_STAGE_VERTEX_BIT)",
    "getValidatedVulkanShaderSpirv(shaders[1]->getSource(), VK_SHADER_STAGE_FRAGMENT_BIT)",
    "shaderIdentityMap.emplace(pointer, ShaderIdentityEntry { pipeline, identity });",
):
    if fragment not in pipeline_header + pipeline_cache:
        raise SystemExit(
            f"Vulkan shader identity is recomputed on every draw: {fragment}"
        )

module_start = pipeline_cache.index("VkShaderModule Cache::getShaderModule")
module_end = pipeline_cache.index(
    "const Cache::PipelineLayout& Cache::getPipeline", module_start
)
module_body = pipeline_cache[module_start:module_end]
for fragment in (
    "VkShaderStageFlagBits stage",
    "getValidatedVulkanShaderSpirv(source, stage)",
    "getVulkanShaderCacheKey(source, stage, spirv)",
    "moduleMap.find(cacheKey)",
    "moduleMap[cacheKey] = result;",
):
    if fragment not in module_body:
        raise SystemExit(
            f"Vulkan module cache lost its fail-closed stage/payload contract: {fragment}"
        )

validator_start = pipeline_cache.index("bool hasVulkanShaderEntryPoint")
validator_end = pipeline_cache.index("} // namespace", validator_start)
validator_body = pipeline_cache[validator_start:validator_end]
for fragment in (
    "SPIRV_MAGIC = 0x07230203",
    "spirv.size() % sizeof(uint32_t) != 0",
    "OP_ENTRY_POINT = 15",
    "EXECUTION_MODEL_VERTEX = 0",
    "EXECUTION_MODEL_FRAGMENT = 4",
    "instructionWordCount == 0",
    "wordIndex + instructionWordCount > wordCount",
    "bool foundEntryPoint = false;",
    "foundEntryPoint = true;",
    "return foundEntryPoint;",
    '== "main"',
):
    if fragment not in validator_body:
        raise SystemExit(
            f"Vulkan SPIR-V preflight no longer validates stage/main: {fragment}"
        )

lookup_start = pipeline_cache.index(
    "const shader::Binary& getVulkanShaderSpirv"
)
lookup_end = pipeline_cache.index("uint32_t readSpirvWord", lookup_start)
lookup_body = pipeline_cache[lookup_start:lookup_end]
for fragment in (
    "dialect == source.dialectSources.end()",
    'throw std::runtime_error("Vulkan shader has no glsl450 dialect")',
    "variant == dialect->second.variantSources.end()",
    'throw std::runtime_error("Vulkan shader has no mono variant")',
):
    if fragment not in lookup_body:
        raise SystemExit(
            f"Vulkan shader payload lookup is not fail-closed: {fragment}"
        )
if ".find(shader::Dialect::glsl450)->second" in pipeline_cache or \
        ".find(shader::Variant::Mono)->second" in pipeline_cache:
    raise SystemExit("Vulkan shader lookup still dereferences a missing payload")

preflight_start = pipeline_cache.index(
    "const shader::Binary& getValidatedVulkanShaderSpirv"
)
preflight_end = pipeline_cache.index(
    "std::string getVulkanShaderCacheKey", preflight_start
)
preflight_body = pipeline_cache[preflight_start:preflight_end]
for fragment in (
    "getVulkanShaderSpirv(source)",
    "hasVulkanShaderEntryPoint(*spirv, stage)",
    "Vulkan shader rejected before pipeline allocation",
):
    if fragment not in preflight_body:
        raise SystemExit(f"Vulkan shader preflight lost: {fragment}")

if pipeline_cache.count(
    "getShaderModule(context, vertexShader, VK_SHADER_STAGE_VERTEX_BIT)"
) != 1:
    raise SystemExit("Vulkan vertex module is not validated against the vertex stage")
if pipeline_cache.count(
    "getShaderModule(context, fragmentShader, VK_SHADER_STAGE_FRAGMENT_BIT)"
) != 1:
    raise SystemExit("Vulkan fragment module is not validated against the fragment stage")

pipeline_start = pipeline_cache.index(
    "const Cache::PipelineLayout& Cache::getPipeline(const vks::Context& context)"
)
pipeline_body = pipeline_cache[pipeline_start:]
if "if (pipelineState.format)" not in pipeline_body:
    raise SystemExit("Vulkan pipeline creation no longer supports format-free draws")
if "gpu::acquire(pipelineState.format)" not in pipeline_body:
    raise SystemExit("Vulkan vertex input no longer acquires its guarded format")

draw_call_comment = (
    "Fullscreen/procedural draws may generate their geometry from gl_VertexID"
)
for fragment in (
    draw_call_comment,
    "if (vertexReflection.validInput(gpu::slot::attr::DrawCallInfo))",
    "auto drawCallInfoBinding = static_cast<uint32_t>(drawCallInfo);",
    "if (!pipelineState.format)",
    "drawCallInfoBinding = 0;",
    "const auto attribute = std::find_if(",
    "return description.location == drawCallInfo;",
    "DrawCallInfo vertex attribute conflicts with the reflected slot",
    "const auto binding = std::find_if(",
    "return description.binding == drawCallInfoBinding;",
    "DrawCallInfo vertex binding conflicts with the reflected slot",
    "const auto drawCallInfoStride = static_cast<uint32_t>(sizeof(uint16_t) * 2)",
):
    if fragment not in pipeline_body:
        raise SystemExit(
            f"format-free draws lost their reflected DrawCallInfo vertex descriptor: {fragment}"
        )
format_guard = pipeline_body.index("if (pipelineState.format)")
format_open = pipeline_body.index("{", format_guard)
depth = 0
format_close = None
for index in range(format_open, len(pipeline_body)):
    if pipeline_body[index] == "{":
        depth += 1
    elif pipeline_body[index] == "}":
        depth -= 1
        if depth == 0:
            format_close = index
            break
if format_close is None:
    raise SystemExit("optional Stream::Format block is syntactically incomplete")
if pipeline_body.index(draw_call_comment) < format_close:
    raise SystemExit("DrawCallInfo is again nested inside the optional Stream::Format path")

descriptor_binding_start = pipeline_body.index(
    "auto drawCallInfoBinding = static_cast<uint32_t>(drawCallInfo);"
)
descriptor_binding_end = pipeline_body.index("const auto attribute =", descriptor_binding_start)
descriptor_binding_body = pipeline_body[descriptor_binding_start:descriptor_binding_end]
if "#if defined(Q_OS_IOS)" not in descriptor_binding_body or "#endif" not in descriptor_binding_body:
    raise SystemExit("format-free DrawCallInfo binding compaction must remain iOS-only")
if "{ drawCallInfo, drawCallInfoBinding, VK_FORMAT_R16G16_SINT, 0 }" not in pipeline_body:
    raise SystemExit("DrawCallInfo shader location must remain stable while only its binding is compacted")

transform_start = backend.index("void VKBackend::updateTransform")
transform_end = backend.index("void VKBackend::updatePipeline", transform_start)
transform_body = backend[transform_start:transform_end]
for fragment in (
    "auto drawCallInfoBinding = static_cast<uint32_t>(gpu::Stream::DRAW_CALL_INFO);",
    "if (!_cache.pipelineState.format)",
    "drawCallInfoBinding = 0;",
):
    if fragment not in transform_body:
        raise SystemExit(
            f"format-free iOS DrawCallInfo runtime binding diverged from its descriptor: {fragment}"
        )
runtime_binding_start = transform_body.index(
    "auto drawCallInfoBinding = static_cast<uint32_t>(gpu::Stream::DRAW_CALL_INFO);"
)
runtime_binding_end = transform_body.index("if (batch._currentNamedCall.empty())", runtime_binding_start)
runtime_binding_body = transform_body[runtime_binding_start:runtime_binding_end]
if "#if defined(Q_OS_IOS)" not in runtime_binding_body or "#endif" not in runtime_binding_body:
    raise SystemExit("format-free DrawCallInfo runtime binding compaction must remain iOS-only")
if transform_body.count(
    "vkCmdBindVertexBuffers(_currentCommandBuffer, drawCallInfoBinding, 1,"
) != 2:
    raise SystemExit("both DrawCallInfo upload paths must use the compact iOS binding")

render_start = backend.index("void VKBackend::renderPassDraw")
render_end = backend.index("void VKBackend::recycle", render_start)
render_body = backend[render_start:render_end]
draw_call = "(this->*(call))(batch, *offset);"
restore_guard = (
    "if (!_cache.pipelineState.format && _input._bufferVBOs[0] != VK_NULL_HANDLE)"
)
restore_call = "vkCmdBindVertexBuffers(_currentCommandBuffer, 0, 1, &vkBuffer, &vkOffset);"
for fragment in (draw_call, restore_guard, restore_call):
    if fragment not in render_body:
        raise SystemExit(f"format-free binding 0 is not restored after its draw: {fragment}")
if not render_body.index(draw_call) < render_body.index(restore_guard) < render_body.index(restore_call):
    raise SystemExit("regular binding 0 must be restored only after the format-free draw")
restore_guard_position = render_body.index(restore_guard)
restore_platform_start = render_body.rfind(
    "#if defined(Q_OS_IOS)", render_body.index(draw_call), restore_guard_position
)
restore_platform_end = render_body.find("#endif", render_body.index(restore_call))
if restore_platform_start < 0 or restore_platform_end < 0:
    raise SystemExit("physical binding 0 restoration must remain iOS-only")
restore_start = render_body.index(restore_guard)
restore_end = render_body.index("#endif", restore_start)
restore_body = render_body[restore_start:restore_end]
if "_cache.pipelineState._bufferStrides" in restore_body or "_bufferStrideSet" in restore_body:
    raise SystemExit("restoring physical binding 0 must not pollute the format-free pipeline key")

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
    "iOS Vulkan pipeline contract valid: dynamic shader payloads are distinct, "
    "SPIR-V entry points are stage-checked, and format-free draws remain supported"
)
