#!/usr/bin/env python3
"""Contract for fail-closed KTX1 frame-file capture on iOS Vulkan."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("#if !defined(Q_OS_IOS)\nstatic ktx::StoragePointer textureToKtxVulkan" in SOURCE,
        "KTX GL-format mapper must not compile on iOS")
require("void VulkanDisplayPlugin::captureFrame(const std::string& filename) const {\n#if defined(Q_OS_IOS)" in SOURCE,
        "captureFrame lacks an iOS fail-closed branch")
require("Q_UNUSED(filename)" in SOURCE and "loggedUnsupportedCapture" in SOURCE,
        "iOS capture gate must be harmless and emit at most one warning")
require("#else\n    withOtherThreadContext([&] {" in SOURCE,
        "non-iOS frame capture changed unexpectedly")
require("gpu::writeFrame(filename, _currentFrame, captureLambda);" in SOURCE,
        "non-iOS KTX frame writer changed unexpectedly")
require("QImage VulkanDisplayPlugin::getScreenshot" in SOURCE,
        "ordinary screenshot path must remain available")

print("iOS Vulkan KTX capture gate valid: diagnostic capture fails closed; presentation/screenshots preserved")
