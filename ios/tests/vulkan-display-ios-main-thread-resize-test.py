#!/usr/bin/env python3
"""Keep UIKit/CAMetalLayer resize work on the iOS GUI thread."""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
plugin_cpp = (
    ROOT
    / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp"
).read_text(encoding="utf-8")
plugin_h = (
    ROOT
    / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.h"
).read_text(encoding="utf-8")
window_cpp = (ROOT / "libraries/vk/src/vk/VKWindow.cpp").read_text(
    encoding="utf-8"
)
window_h = (ROOT / "libraries/vk/src/vk/VKWindow.h").read_text(encoding="utf-8")
vulkan_tools = (ROOT / "libraries/vk/src/vk/VulkanTools.h").read_text(
    encoding="utf-8"
)

for fragment in (
    "void queueIOSFramebufferResize();",
    "std::atomic<bool> _iosFramebufferResizeEnabled{ false };",
    "std::atomic<bool> _iosFramebufferResizeQueued{ false };",
):
    if fragment not in plugin_h:
        raise SystemExit(f"iOS Vulkan resize state contract missing: {fragment}")

activate_start = plugin_cpp.index("bool VulkanDisplayPlugin::activate()")
activate_end = plugin_cpp.index("void VulkanDisplayPlugin::deactivate()", activate_start)
activate = plugin_cpp[activate_start:activate_end]
for fragment in (
    "_iosFramebufferResizeEnabled.store(true",
    "#else\n        _vkWindow->moveToThread(presentThread.get());",
):
    if fragment not in activate:
        raise SystemExit(f"iOS VKWindow affinity contract missing: {fragment}")

deactivate_start = activate_end
deactivate_end = plugin_cpp.index(
    "bool VulkanDisplayPlugin::startStandBySession", deactivate_start
)
deactivate = plugin_cpp[deactivate_start:deactivate_end]
disable = deactivate.index("_iosFramebufferResizeEnabled.store(false")
release = deactivate.index("presentThread->setNewDisplayPlugin(nullptr)")
if disable > release:
    raise SystemExit("iOS framebuffer dispatch must stop before presentation shutdown")

present_start = plugin_cpp.index("void VulkanDisplayPlugin::present(")
present_end = plugin_cpp.index("void VulkanDisplayPlugin::queueIOSFramebufferResize", present_start)
present = plugin_cpp[present_start:present_end]
if present.index("queueIOSFramebufferResize();\n        return;") > present.index(
    "updateFrameData();"
):
    raise SystemExit("iOS resize dispatch must happen before frame acquisition/use")
for fragment in (
    "_vkWindow->_needsResizing.store(true, std::memory_order_release);",
    "queueIOSFramebufferResize();",
    "refreshRateController->clockEndTime();",
    "return;",
):
    if fragment not in present:
        raise SystemExit(f"iOS acquire-failure resize contract missing: {fragment}")

queue_start = present_end
queue_end = plugin_cpp.index("float VulkanDisplayPlugin::newFramePresentRate", queue_start)
queue = plugin_cpp[queue_start:queue_end]
for fragment in (
    "compare_exchange_strong",
    "QMetaObject::invokeMethod(this, [plugin, window]",
    "Qt::QueuedConnection",
    "_iosFramebufferResizeEnabled.load",
    "QPointer<VulkanDisplayPlugin> plugin(this);",
    "QPointer<VKWindow> window(_vkWindow);",
    "thread() != qApp->thread()",
    "window->thread() != qApp->thread()",
    "Q_ASSERT(QThread::currentThread() == qApp->thread());",
    "if (window->resizeFramebuffer())",
    "window->_needsResizing.store(false, std::memory_order_release);",
    "plugin->_iosFramebufferResizeQueued.store(false, std::memory_order_release);",
    "QCoreApplication::exit(1);",
):
    if fragment not in queue:
        raise SystemExit(f"iOS queued resize transaction missing: {fragment}")
if "Qt::BlockingQueuedConnection" in queue or "withOtherThreadContext" in queue:
    raise SystemExit("iOS resize dispatch must not block or borrow the GL context path")
if queue.index("window->resizeFramebuffer()") > queue.index(
    "window->_needsResizing.store(false, std::memory_order_release);"
):
    raise SystemExit("iOS resize flag cleared before the swapchain transaction finished")

if "#include <QtCore/QThread>" not in window_cpp:
    raise SystemExit("VKWindow GUI-thread assertions lack their direct QThread include")
for signature in (
    "void VKWindow::createSurface()",
    "void VKWindow::createSwapchain()",
    "bool VKWindow::resizeFramebuffer()",
):
    start = window_cpp.index(signature)
    body = window_cpp[start : start + 220]
    if "Q_ASSERT(QThread::currentThread() == qApp->thread());" not in body:
        raise SystemExit(f"{signature} no longer asserts iOS GUI-thread affinity")

for fragment in (
    "virtual bool resizeFramebuffer();",
    "void recreateDrawCommandBuffers();",
):
    if fragment not in window_h:
        raise SystemExit(f"VKWindow resize transaction API missing: {fragment}")

resize_start = window_cpp.index("bool VKWindow::resizeFramebuffer()")
resize_end = window_cpp.index("VKWindow::~VKWindow", resize_start)
resize = window_cpp[resize_start:resize_end]
for fragment in (
    "qsize.width() <= 0 || qsize.height() <= 0",
    "VK_CHECK_RESULT(vkDeviceWaitIdle",
    "_swapchain.create(",
    "recreateDrawCommandBuffers();",
    "setupDepthStencil();",
    "setupFramebuffers();",
    "return true;",
):
    if fragment not in resize:
        raise SystemExit(f"VKWindow resize transaction is incomplete: {fragment}")
if not (
    resize.index("VK_CHECK_RESULT(vkDeviceWaitIdle")
    < resize.index("_swapchain.create(")
    < resize.index("recreateDrawCommandBuffers();")
    < resize.index("setupDepthStencil();")
    < resize.index("setupFramebuffers();")
    < resize.index("return true;")
):
    raise SystemExit("VKWindow resize transaction ordering changed")

buffers_start = window_cpp.index("void VKWindow::recreateDrawCommandBuffers()")
buffers_end = window_cpp.index("void VKWindow::vulkanCleanup()", buffers_start)
buffers = window_cpp[buffers_start:buffers_end]
for fragment in (
    "vkDestroyFence(_context.device->logicalDevice, _previousFrameFence, nullptr);",
    "_previousFrameFence = VK_NULL_HANDLE;",
    "vkFreeCommandBuffers(",
    "_drawCommandBuffers.resize(_swapchain.imageCount);",
    "VK_CHECK_RESULT(vkAllocateCommandBuffers(",
    "_previousCommandBuffer = VK_NULL_HANDLE;",
):
    if fragment not in buffers:
        raise SystemExit(f"Swapchain command-buffer resize contract missing: {fragment}")

present_fence_start = plugin_cpp.index(
    "// Retire the previous frame as a fence/command-buffer pair"
)
present_fence_end = plugin_cpp.index(
    "_vkWindow->_previousFrameFence = frameFence;", present_fence_start
)
present_fence = plugin_cpp[present_fence_start:present_fence_end]
for fragment in (
    "&_vkWindow->_previousFrameFence",
    "vkResetCommandBuffer(_vkWindow->_previousCommandBuffer, 0)",
    "_vkWindow->_previousFrameFence = VK_NULL_HANDLE;",
    "_vkWindow->_previousCommandBuffer = VK_NULL_HANDLE;",
    "vkBackend->recyclePreviousFrame();",
    "VK_CHECK_RESULT(vkCreateFence",
    "VK_CHECK_RESULT(vkQueueSubmit",
    "vkDestroyFence(vkDevice, _vkWindow->_previousFrameFence, nullptr);",
):
    if fragment not in present_fence:
        raise SystemExit(f"Present fence lifetime contract missing: {fragment}")
if "vkWaitForFences(vkDevice, 1, &frameFence" in present_fence or \
        "vkDestroyFence(vkDevice, frameFence" in present_fence or \
        "vkResetCommandBuffer(commandBuffer" in present_fence:
    raise SystemExit("Present stores a fence handle after destroying that same handle")

metal_macro_start = vulkan_tools.index("#elif defined(VK_USE_PLATFORM_METAL_EXT)")
metal_macro_end = vulkan_tools.index("#else", metal_macro_start)
metal_macro = vulkan_tools[metal_macro_start:metal_macro_end]
if "throw std::runtime_error(message);" not in metal_macro:
    raise SystemExit("Release iOS Vulkan errors can still continue with partial state")

print("iOS Vulkan UIKit/CAMetalLayer resize contract valid")
