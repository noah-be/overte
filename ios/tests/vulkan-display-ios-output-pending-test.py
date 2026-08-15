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

start = SOURCE.index("void VulkanDisplayPlugin::present(")
end = SOURCE.index("void VulkanDisplayPlugin::queueIOSFramebufferResize", start)
present = SOURCE[start:end]

for fragment in (
    "const auto outputTexture = vkBackend->_outputTexture;",
    "const bool outputReady = outputTexture &&",
    "!outputTexture->attachments.empty()",
    "outputTexture->attachments[0].image != VK_NULL_HANDLE",
    "outputTexture->_gpuObject.getWidth() > 0",
    "outputTexture->_gpuObject.getHeight() > 0",
    'qCWarning(displayPlugins) << "OVERTE_IOS_VULKAN_OUTPUT_PENDING";',
    'qCInfo(displayPlugins) << "OVERTE_IOS_VULKAN_OUTPUT_READY";',
    "if (outputReady)",
    "vkCmdBlitImage(",
    "VkClearColorValue clearColor{};",
    "clearColor.float32[3] = 1.0f;",
    "vkCmdClearColorImage(",
    "cmdEndLabel(commandBuffer);",
    "VK_CHECK_RESULT(vkEndCommandBuffer(commandBuffer));",
    "static const VkPipelineStageFlags waitFlags{ VK_PIPELINE_STAGE_TRANSFER_BIT };",
    "VK_CHECK_RESULT(vkQueueSubmit",
    "_vkWindow->_swapchain.queuePresent(",
):
    if fragment not in present:
        raise SystemExit(f"Vulkan pending-output contract missing: {fragment}")

if "vkBackend->_outputTexture->_gpuObject" in present or \
        "vkBackend->_outputTexture->attachments" in present:
    raise SystemExit("Vulkan present still dereferences the nullable backend output directly")

destination_transition = present.index(
    "_vkWindow->_swapchain.images[currentImageIndex],\n"
    "                0,\n"
    "                VK_ACCESS_TRANSFER_WRITE_BIT"
)
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
    destination_transition < min(blit, clear)
    and max(blit, clear) < present_transition < command_end < submit < queue_present
):
    raise SystemExit("pending and ready frames no longer share a complete submit/present transaction")

if "bool _iosOutputPendingReported{ false };" not in HEADER:
    raise SystemExit("pending-output telemetry is no longer bounded to state transitions")

print("iOS Vulkan startup output contract valid: pending frames clear and submit safely")
