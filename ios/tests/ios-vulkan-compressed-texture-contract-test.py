#!/usr/bin/env python3
"""Fail closed when MoltenVK rejects an individual compressed texture format."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text()
SHARED = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKShared.cpp").read_text()
SETUP = (ROOT / "interface/src/Application_Setup.cpp").read_text()
TEXTURE_CACHE = (ROOT / "libraries/material-networking/src/material-networking/TextureCache.cpp").read_text()

assert "vkGetPhysicalDeviceImageFormatProperties(" in BACKEND
assert "VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT" in BACKEND
assert "textureCompressionBC == VK_TRUE &&" in BACKEND
assert "textureCompressionETC2 == VK_TRUE &&" in BACKEND
assert "if (format.getDimension() == gpu::TILE4x4)" in BACKEND
assert "!supportedTextureFormat(texture->getTexelFormat())" in BACKEND
assert "OVERTE_IOS_VULKAN_TEXTURE_REJECTED" in BACKEND
assert "unsupported network asset to reach vkCreateImage" in BACKEND
assert "VK_FORMAT_BC1_RGB_SRGB_BLOCK" in SHARED
assert "IOS_TEXTURE_BUDGET_MB { 256 }" in SETUP
assert "OVERTE_IOS_RESOURCE_LIMIT textureBudgetMB" in SETUP
assert "IOS_UNCOMPRESSED_MAX_PIXELS { 1024ULL * 1024ULL }" in TEXTURE_CACHE
assert "_lowestRequestedMipLevel = std::max(_lowestRequestedMipLevel, minimumMip)" in TEXTURE_CACHE
assert "OVERTE_IOS_TEXTURE_FALLBACK" in TEXTURE_CACHE

print("iOS Vulkan compressed textures use exact checks and bounded uncompressed fallback residency")
