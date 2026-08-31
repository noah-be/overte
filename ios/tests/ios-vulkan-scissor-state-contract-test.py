#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text(
    encoding="utf-8"
)
BACKEND_HEADER = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.h").read_text(
    encoding="utf-8"
)
WORKFLOW = (ROOT / ".github/workflows/ios-integrated.yml").read_text(
    encoding="utf-8"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


draw_start = BACKEND.index("void VKBackend::renderPassDraw")
draw_end = BACKEND.index("void VKBackend::recycle", draw_start)
draw = BACKEND[draw_start:draw_end]

require(
    "pipelineState->isScissorEnable()" in draw,
    "Vulkan draw execution must honor the shared scissor-enable state",
)
require(
    "if (useStateScissor)" in draw,
    "explicit scissor rectangles must only be used by scissor-enabled pipelines",
)
require(
    "scissor.extent.width = framebuffer->getWidth();" in draw
    and "scissor.extent.height = framebuffer->getHeight();" in draw,
    "scissor-disabled pipelines must cover the complete render target",
)
require(
    draw.index("pipelineState->isScissorEnable()") < draw.index("vkCmdSetScissor"),
    "the scissor-enable translation must happen before vkCmdSetScissor",
)
require(
    "scissor.offset.x = _currentScissorRect.x;" in draw
    and "scissor.extent.width = _currentScissorRect.z;" in draw,
    "scissor-enabled pipelines must retain their explicit rectangle",
)
require(
    "_iosScissorEnabledDraws" in BACKEND_HEADER
    and "_iosScissorDisabledDraws" in BACKEND_HEADER
    and "OVERTE_IOS_VULKAN_FRAME" in BACKEND,
    "physical-device logs must report compact scissor-path progress",
)
require(
    "std::chrono::seconds(5)" in BACKEND,
    "physical-device progress must be rate-limited to five-second intervals",
)
require(
    "*-OverteIOSClient-Release-device-unsigned-symbols.zip" in WORKFLOW,
    "device artifacts must preserve the matching dSYM for crash symbolication",
)

print("iOS Vulkan scissor state contract passed")
