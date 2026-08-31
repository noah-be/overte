#!/usr/bin/env python3
"""Guard the MoltenVK logical-device boundary used by the iOS client."""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
context = (ROOT / "libraries/vk/src/vk/Context.cpp").read_text(encoding="utf-8")
device_source = (ROOT / "libraries/vk/src/vk/VulkanDevice.cpp").read_text(encoding="utf-8")
device_header = (ROOT / "libraries/vk/src/vk/VulkanDevice.h").read_text(encoding="utf-8")

device_interop_gate = """#if !defined(Q_OS_IOS)
    // The desktop GL interoperability path exports Vulkan memory and
    // semaphores as POSIX file descriptors."""
if device_interop_gate not in context:
    raise SystemExit("iOS does not explicitly exclude desktop FD device interoperability")

require_start = context.index("requireDeviceExtensions({")
require_last_extension = context.index("VK_KHR_EXTERNAL_SEMAPHORE_EXTENSION_NAME});", require_start)
require_end = context.index("#endif", require_last_extension)
require_block = context[require_start:require_end]
for extension in (
    "VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME",
    "VK_KHR_EXTERNAL_SEMAPHORE_FD_EXTENSION_NAME",
    "VK_KHR_EXTERNAL_MEMORY_EXTENSION_NAME",
    "VK_KHR_EXTERNAL_SEMAPHORE_EXTENSION_NAME",
):
    if extension not in require_block:
        raise SystemExit(f"desktop interoperability lost required extension {extension}")

instance_gate = """#if !defined(Q_OS_IOS)
    instanceExtensions.insert(VK_KHR_EXTERNAL_MEMORY_CAPABILITIES_EXTENSION_NAME);
    instanceExtensions.insert(VK_KHR_EXTERNAL_SEMAPHORE_CAPABILITIES_EXTENSION_NAME);
#endif"""
if instance_gate not in context:
    raise SystemExit("iOS does not exclude unused external-memory instance capabilities")

fd_loader_gate = """#if !defined(Q_OS_IOS)
    gpu::vk::vkGetMemoryFdKHR = reinterpret_cast<PFN_vkGetMemoryFdKHR>"""
if fd_loader_gate not in context or "#else\n    gpu::vk::vkGetMemoryFdKHR = nullptr;" not in context:
    raise SystemExit("iOS external-memory function pointer does not fail closed")

for token in (
    "const VkResult result = device->createLogicalDevice(",
    "if (result != VK_SUCCESS)",
    "device.reset();",
    'throw std::runtime_error("Could not create Vulkan logical device: "',
    "device->logicalDevice == VK_NULL_HANDLE",
    'throw std::runtime_error("No Vulkan physical device is available")',
):
    if token not in context:
        raise SystemExit(f"Vulkan context is missing fail-closed token {token!r}")

if "VkDevice logicalDevice{ VK_NULL_HANDLE };" not in device_header:
    raise SystemExit("Vulkan logical device handle is not initialized to null")

missing_extension = 'std::cerr << "Enabled device extension'
missing_start = device_source.index(missing_extension)
missing_end = device_source.index("}", missing_start)
if "return VK_ERROR_EXTENSION_NOT_PRESENT;" not in device_source[missing_start:missing_end]:
    raise SystemExit("unsupported Vulkan device extensions are still passed to vkCreateDevice")

print("iOS Vulkan device contract valid: desktop FD interop excluded and logical-device failures stop before queue access")
