#!/usr/bin/env python3
"""Keep startup frames valid before the Vulkan output framebuffer exists."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp"
).read_text(encoding="utf-8")
HEADER = (
    ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.h"
).read_text(encoding="utf-8")
FRAMEBUFFER_CACHE = (
    ROOT / "libraries/render-utils/src/FramebufferCache.cpp"
).read_text(encoding="utf-8")
BACKEND = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text(encoding="utf-8")
BACKEND_HEADER = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.h").read_text(encoding="utf-8")
TONE_PROGRAM = (ROOT / "libraries/render-utils/src/render-utils/toneMapping.slp").read_text(encoding="utf-8")
TONE_SHADER = (ROOT / "libraries/render-utils/src/toneMapping.slf").read_text(encoding="utf-8")
TONE_TASK = (ROOT / "libraries/render-utils/src/ToneMapAndResampleTask.cpp").read_text(encoding="utf-8")

assert "batch.setInputFormat({});" in SOURCE

if "VERTEX gpu::vertex::DrawUnitQuadTexcoord" not in TONE_PROGRAM or \
        "DrawViewportQuadTransformTexcoord" in TONE_PROGRAM:
    raise SystemExit("tone mapping must not require format-free DrawCallInfo vertex input")
for fragment in ("_texcoordTransform", "transformedTexCoord"):
    if fragment not in TONE_SHADER:
        raise SystemExit(f"tone mapping lost uniform texcoord transform: {fragment}")
if "evalSubregionTexcoordTransformCoefficients" not in TONE_TASK:
    raise SystemExit("tone mapping must preserve viewport subregion coordinates")

start = SOURCE.index("void VulkanDisplayPlugin::present(")
end = SOURCE.index("void VulkanDisplayPlugin::queueIOSFramebufferResize", start)
present = SOURCE[start:end]

for fragment in (
    "vkBackend->finishPresentRendering();",
    "auto outputTexture = vkBackend->_outputTexture;",
    "const bool outputReady = !solidGreenProbe &&",
    "sourceImage != VK_NULL_HANDLE",
    "sourceWidth > 0 && sourceHeight > 0",
    'qCWarning(displayPlugins) << "OVERTE_IOS_VULKAN_OUTPUT_PENDING";',
    'qCInfo(displayPlugins) << "OVERTE_IOS_VULKAN_OUTPUT_READY";',
    "if (outputReady)",
    "vkCmdCopyImage(",
    "vkCmdBlitImage(",
    "VkClearColorValue clearColor{};",
    "clearColor.float32[3] = 1.0f;",
    "vkCmdClearColorImage(",
    "cmdEndLabel(commandBuffer);",
    "VK_CHECK_RESULT(vkEndCommandBuffer(commandBuffer));",
    "static const VkPipelineStageFlags waitFlags{ VK_PIPELINE_STAGE_TRANSFER_BIT };",
    "VK_CHECK_RESULT(vkQueueSubmit",
    "_vkWindow->_swapchain.queuePresent(",
    "const auto presentResult = _vkWindow->_swapchain.queuePresent(",
    "presentResult == VK_ERROR_OUT_OF_DATE_KHR",
    "presentResult == VK_SUBOPTIMAL_KHR",
    "VK_CHECK_RESULT(presentResult);",
    '"OVERTE_IOS_VULKAN_PRESENT acquired image=%u extent=%ux%u result=%d"',
    '"OVERTE_IOS_VULKAN_PRESENT probe=%{public}s output_ready=%d source=%ux%u target=%ux%u"',
    '"OVERTE_IOS_VULKAN_PRESENT source_barrier_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT source_barrier_complete"',
    '"OVERTE_IOS_VULKAN_PRESENT destination_barrier_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT destination_barrier_complete"',
    '"OVERTE_IOS_VULKAN_PRESENT transfer_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT transfer_complete"',
    '"OVERTE_IOS_VULKAN_PRESENT transfer_mode=%{public}s source_format=%d target_format=%d"',
    '"OVERTE_IOS_VULKAN_PRESENT present_barrier_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT present_barrier_complete"',
    '"OVERTE_IOS_VULKAN_PRESENT restore_barrier_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT restore_barrier_complete"',
    '"OVERTE_IOS_VULKAN_PRESENT command_buffer_end_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT command_buffer_end_complete"',
    '"OVERTE_IOS_VULKAN_PRESENT queue_submit_begin"',
    '"OVERTE_IOS_VULKAN_PRESENT submitted image=%u"',
    '"OVERTE_IOS_VULKAN_PRESENT presented image=%u result=%d"',
    '"OVERTE_IOS_VULKAN_PRESENT frame_retired"',
):
    if fragment not in present:
        raise SystemExit(f"Vulkan pending-output contract missing: {fragment}")

if "const bool traceIOSPresentCommands = outputReady && !_iosPresentOutputReady;" not in present:
    raise SystemExit("ready-output commands are not traced on their first state transition")

finish_present = BACKEND.split(
    "void VKBackend::finishPresentRendering", 1
)[1].split("}", 1)[0]
if "resetRenderPass();" not in finish_present:
    raise SystemExit("iOS present transfer must close the compositor render pass")

if "compositeLayers();" in present or "setPresentOutputFramebuffer" in present:
    raise SystemExit("iOS present must use the renderer's final CompositeHUD output directly")

for probe in ("swapchain-green", "tone-input", "frame", "resample", "composite"):
    if f'"{probe}"' not in present:
        raise SystemExit(f"missing reusable iOS presentation boundary probe: {probe}")
for fragment in (
    "vkBackend->_toneMappingInputTexture",
    "vkBackend->_resampleOutputTexture",
    "vkBackend->_compositeHUDOutputTexture",
    "vkBackend->resolvePresentFramebuffer(_currentFrame->framebuffer)",
    "sourceImage",
    "sourceLayout",
    "sourceAccess",
    "sourceStage",
):
    if fragment not in present:
        raise SystemExit(f"incomplete reusable iOS boundary probe: {fragment}")
for fragment in (
    '_resource._textures[0].texture',
    '_toneMappingInputTexture = syncGPUObject',
    '_resampleOutputTexture = _outputTexture',
    '_compositeHUDOutputTexture = _outputTexture',
):
    if fragment not in BACKEND:
        raise SystemExit(f"backend does not preserve diagnostic boundary: {fragment}")
for fragment in (
    'VKTexture* _toneMappingInputTexture',
    'VKFramebuffer* _resampleOutputTexture',
    'VKFramebuffer* _compositeHUDOutputTexture',
):
    if fragment not in BACKEND_HEADER:
        raise SystemExit(f"backend diagnostic boundary is not retained: {fragment}")

if "const auto colorFormat = gpu::Element::COLOR_SBGRA_32;" not in SOURCE:
    raise SystemExit("iOS composite framebuffer must match the BGRA swapchain format")

if "sourceFormat == _vkWindow->_swapchain.colorFormat" not in present:
    raise SystemExit("iOS output copy must require identical Vulkan formats")

if "#if defined(Q_OS_IOS)" not in FRAMEBUFFER_CACHE or \
        "gpu::Element::COLOR_SBGRA_32" not in FRAMEBUFFER_CACHE:
    raise SystemExit("iOS final framebuffer must match the native BGRA swapchain format")

for fragment in (
    '"OVERTE_IOS_VULKAN_PRESENT resize_complete extent=%ux%u images=%u"',
    '"OVERTE_IOS_VULKAN_FATAL present_exception=%{public}s"',
    '"OVERTE_IOS_VULKAN_FATAL present_exception=unknown"',
):
    if fragment not in SOURCE:
        raise SystemExit(f"Vulkan iOS lifecycle telemetry missing: {fragment}")

if "vkBackend->_outputTexture->_gpuObject" in present or \
        "vkBackend->_outputTexture->attachments" in present:
    raise SystemExit("Vulkan present still dereferences the nullable backend output directly")

destination_transition = present.index(
    "_vkWindow->_swapchain.images[currentImageIndex],\n"
    "                0,\n"
    "                VK_ACCESS_TRANSFER_WRITE_BIT"
)
copy = present.index("vkCmdCopyImage(")
blit = present.index("vkCmdBlitImage(")
clear = present.index("vkCmdClearColorImage(")
present_transition = present.index(
    "VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,\n"
    "                VK_IMAGE_LAYOUT_PRESENT_SRC_KHR"
)
command_end = present.index("VK_CHECK_RESULT(vkEndCommandBuffer(commandBuffer));")
submit = present.index("VK_CHECK_RESULT(vkQueueSubmit")
queue_present = present.index("_vkWindow->_swapchain.queuePresent(")
if not (
    destination_transition < min(copy, blit, clear)
    and max(copy, blit, clear) < present_transition < command_end < submit < queue_present
):
    raise SystemExit("pending and ready frames no longer share a complete submit/present transaction")

if "bool _iosOutputPendingReported{ false };" not in HEADER:
    raise SystemExit("pending-output telemetry is no longer bounded to state transitions")

print("iOS Vulkan startup output contract valid: pending frames clear and submit safely")
