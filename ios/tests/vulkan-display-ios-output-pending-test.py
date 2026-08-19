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

start = SOURCE.index("void VulkanDisplayPlugin::present(")
end = SOURCE.index("void VulkanDisplayPlugin::queueIOSFramebufferResize", start)
present = SOURCE[start:end]

for fragment in (
    "compositeLayers();",
    "vkBackend->setPresentOutputFramebuffer(_compositeFramebuffer);",
    "const auto outputTexture = vkBackend->_outputTexture;",
    "const bool outputReady = outputTexture &&",
    "!outputTexture->attachments.empty()",
    "outputTexture->attachments[0].image != VK_NULL_HANDLE",
    "outputTexture->_gpuObject.getWidth() > 0",
    "outputTexture->_gpuObject.getHeight() > 0",
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
    '"OVERTE_IOS_VULKAN_PRESENT output_ready=%d source=%ux%u target=%ux%u"',
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

if present.index("compositeLayers();") > present.index("const auto outputTexture = vkBackend->_outputTexture;"):
    raise SystemExit("iOS present selects its output before composing the frame")

if "outputTexture->attachments[0].format" not in present or \
        "sourceFormat == _vkWindow->_swapchain.colorFormat" not in present:
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
