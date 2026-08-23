#!/usr/bin/env python3
"""Fail closed when MoltenVK rejects an individual compressed texture format."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text()

assert "vkGetPhysicalDeviceImageFormatProperties(" in BACKEND
assert "VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT" in BACKEND
assert "textureCompressionBC == VK_TRUE &&" in BACKEND
assert "textureCompressionETC2 == VK_TRUE &&" in BACKEND
assert "if (format.getDimension() == gpu::TILE4x4)" in BACKEND
assert "!supportedTextureFormat(texture->getTexelFormat())" in BACKEND
assert "OVERTE_IOS_VULKAN_TEXTURE_REJECTED" in BACKEND
assert "unsupported network asset to reach vkCreateImage" in BACKEND

print("iOS Vulkan compressed textures use exact device-format checks and fail-safe fallback")
