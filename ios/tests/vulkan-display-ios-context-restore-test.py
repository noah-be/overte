#!/usr/bin/env python3
"""Contract for iOS Vulkan screenshot synchronization without GL restore."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp").read_text()
QML_RENDER = (ROOT / "libraries/qml/src/qml/impl/RenderEventHandler.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("_canvas.setThreadContext();" in QML_RENDER,
        "QML thread-local GL context registration moved; re-audit restore ownership")
require("#if !defined(Q_OS_IOS)\n#include <gl/Context.h>\n#include <gl/OffscreenGLCanvas.h>\n#endif" in SOURCE,
        "iOS must not parse VulkanDisplayPlugin's legacy GL context helpers")
body = SOURCE.split("void VulkanDisplayPlugin::withOtherThreadContext", 1)[1].split("\n}\n", 1)[0]
require("presentThread->withOtherThreadContext(f);" in body,
        "Present-thread synchronization was removed")
require("#if !defined(Q_OS_IOS)" in body and "OffscreenGLCanvas::restoreThreadContext()" in body,
        "GL restore must be retained only for non-iOS")
require(SOURCE.count("withOtherThreadContext([&] {") >= 2,
        "Vulkan screenshot download synchronization changed unexpectedly")

print("iOS Vulkan context restore valid: screenshot synchronization retained; unrelated GL restore excluded")
