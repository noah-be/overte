#!/usr/bin/env python3
"""Source contract for the Qt iOS CAMetalLayer to Vulkan surface handoff."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

cmake = (ROOT / "libraries/vk/CMakeLists.txt").read_text(encoding="utf-8")
for token in ("if(IOS)", "enable_language(OBJCXX)", "src/vk/VulkanIOSSurface.mm"):
    if token not in cmake:
        raise SystemExit(f"vk CMake missing iOS surface token {token!r}")

window = (ROOT / "libraries/vk/src/vk/VKWindow.cpp").read_text(encoding="utf-8")
ios_start = window.index("#elif defined(Q_OS_IOS)", window.index("void VKWindow::createSurface()"))
linux_start = window.index("#else", ios_start)
ios_branch = window[ios_start:linux_start]
for token in ("QSurface::VulkanSurface", "create();", "overteIOSMetalLayerForWindow(this)", "_swapchain.initSurface(metalLayer)"):
    if token not in ios_branch:
        raise SystemExit(f"iOS createSurface branch missing {token!r}")
if "QX11Info" in ios_branch:
    raise SystemExit("iOS createSurface branch must not reference QX11Info")
if "_swapchain.initSurface(QX11Info::connection(), winId())" not in window[linux_start:]:
    raise SystemExit("existing X11 surface branch was not preserved")

swapchain = (ROOT / "libraries/vk/src/vk/VulkanSwapChain.cpp").read_text(encoding="utf-8")
surface_start = swapchain.index("void VulkanSwapChain::initSurface")
surface_end = swapchain.index("void VulkanSwapChain::setContext", surface_start)
surface_body = swapchain[surface_start:surface_end]
for token in (
    "assert(_context && _context->instance)",
    "vkCreateMetalSurfaceEXT(_context->instance",
    "vkCreateXcbSurfaceKHR(_context->instance",
):
    if token not in surface_body:
        raise SystemExit(f"Vulkan swapchain surface creation missing {token!r}")
for stale in (
    "SurfaceKHR(instance", "SurfaceMVK(instance", "vkGetInstanceProcAddr(instance",
    "fpCreateHeadlessSurfaceEXT(instance",
):
    if stale in swapchain:
        raise SystemExit(f"Vulkan swapchain retained stale context access {stale!r}")

config = (ROOT / "libraries/vk/src/vk/Config.h").read_text(encoding="utf-8")
if "#ifndef VK_USE_PLATFORM_METAL_EXT\n#define VK_USE_PLATFORM_METAL_EXT\n#endif" not in config:
    raise SystemExit("the iOS Metal platform define must tolerate the owning CMake definition")

bridge = (ROOT / "libraries/vk/src/vk/VulkanIOSSurface.mm").read_text(encoding="utf-8")
for token in ("QWindow::winId()", "CAMetalLayer", "isKindOfClass", "Qt owns its lifetime"):
    if token not in bridge:
        raise SystemExit(f"Objective-C++ bridge missing {token!r}")

print("iOS Vulkan surface contract valid: CAMetalLayer branch isolated; X11 preserved")
