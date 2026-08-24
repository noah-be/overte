#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text()
TEXTURE = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKTexture.cpp").read_text()
HEADER = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKTexture.h").read_text()
OVERLAY = (ROOT / "interface/src/ui/ApplicationOverlay.cpp").read_text()
OVERLAY_HEADER = (ROOT / "interface/src/ui/ApplicationOverlay.h").read_text()
PROFILE = (
    ROOT / "ios/ci/render-diagnostic-profiles/physical-ipad-touch-ui.json"
).read_text()
DOCUMENTATION = (ROOT / "ios/ci/IPAD_RENDER_DIAGNOSTICS.md").read_text()

# Until the incomplete variable-allocation implementation is repaired, iOS
# keeps its known-good strict uploader but bounds ordinary world assets.
assert "#define FORCE_STRICT_TEXTURE 1" in BACKEND
assert '"iosResourceTextureMaxDimension", 512, 64, 16384' in TEXTURE
assert "TextureUsageType::RESOURCE" in TEXTURE
assert "completeMipAvailable" in TEXTURE
assert "_sourceMipOffset" in HEADER and "_sourceMipOffset" in TEXTURE
assert "Stop at the first gap" in TEXTURE

# A single physical-device run must expose both Vulkan residency and the iOS
# footprint used by Jetsam, and its quality cap must remain runtime-configurable.
assert "OVERTE_IOS_TEXTURE_MEMORY stage=created" in TEXTURE
assert "process_footprint_bytes=" in TEXTURE
assert "iosStrictTextureResidentBytes" in TEXTURE
assert "iosTextureTraceEvery" in TEXTURE
assert "iosRuntimeDiagnosticInt" in TEXTURE
assert "Backend::textureResidentCount.increment();" in TEXTURE
assert "Backend::textureResidentCount.decrement();" in TEXTURE
assert "Backend::textureResidentGPUMemSize.update(0, _residentBytes);" in TEXTURE
assert "Backend::textureResidentGPUMemSize.update(_residentBytes, 0);" in TEXTURE
assert "_residencyAccounted = true;" in TEXTURE
assert "if (_residencyAccounted)" in TEXTURE
assert '"iosResourceTextureMaxDimension": 512' in PROFILE
assert "256 for a low-memory isolation run" in DOCUMENTATION
assert "no new IPA is needed" in DOCUMENTATION

# Synchronous uploads must release their file-backed references. RGB expansion
# writes to each face's destination offset but reads from that face's byte zero.
assert "_transferData.mips.clear()" in TEXTURE
assert "_transferData.mips.shrink_to_fit()" in TEXTURE
assert "size_t sourcePos = i * 3;" in TEXTURE
assert "size_t destPos = face.offset + i * 4;" in TEXTURE

# Screen-space software QML must reuse a bounded set of CPU/GPU textures.  A
# new 1366x967 strict Vulkan image on every 15 Hz UI frame eventually stalls
# MoltenVK on a physical iPad even though ordinary per-frame recycling runs.
assert "IOS_QML_TEXTURE_RING_SIZE { 4 }" in OVERLAY_HEADER
assert "_iosQmlTextureRing[_iosQmlTextureRingIndex]" in OVERLAY
assert "_iosQmlTextureRingIndex + 1" in OVERLAY
assert "refreshIOSSoftwareTexture" in HEADER and "refreshIOSSoftwareTexture" in TEXTURE
assert "_iosSoftwareStagingBuffer" in HEADER and "_iosSoftwareStagingMemory" in HEADER
assert "if (_iosSoftwareStagingBuffer == VK_NULL_HANDLE)" in TEXTURE
assert "recycler.trashVkBuffer(_iosSoftwareStagingBuffer)" in TEXTURE
assert "recycler.trashVkDeviceMemory(_iosSoftwareStagingMemory)" in TEXTURE
assert 'texture->source() == "ApplicationOverlayIOSSoftware"' in BACKEND
assert "texture->getStamp() != object->_storageStamp" in BACKEND
assert "VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL" in TEXTURE

print("iOS Vulkan resource textures have bounded uploads, footprint telemetry, and public residency stats")
