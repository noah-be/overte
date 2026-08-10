#!/usr/bin/env python3
"""Source contract for fail-closed desktop GL external textures on iOS."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
cmake = (ROOT / "libraries/gpu-vk/CMakeLists.txt").read_text(encoding="utf-8")
backend = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.cpp").read_text(encoding="utf-8")

macro = "OVERTE_IOS_VULKAN_DISABLE_EXTERNAL_GL_INTEROP"
if "if(IOS)" not in cmake or "target_compile_definitions(${TARGET_NAME} PUBLIC" not in cmake or f"{macro}=1" not in cmake:
    raise SystemExit("gpu-vk does not enable the external GL interop gate for iOS")
if backend.count(f"#if defined({macro})") < 2:
    raise SystemExit("external creation paths are not both gated")
for diagnostic in (
    "External GL textures are disabled on iOS Vulkan",
    "Refusing to create a desktop GL external texture on iOS Vulkan",
):
    if diagnostic not in backend:
        raise SystemExit(f"missing fail-closed diagnostic {diagnostic!r}")

texture_header = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKTexture.h").read_text(encoding="utf-8")
texture_source = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKTexture.cpp").read_text(encoding="utf-8")
backend_header = (ROOT / "libraries/gpu-vk/src/gpu/vk/VKBackend.h").read_text(encoding="utf-8")
negative_guard = f"#if !defined({macro})"
for name, text in (("texture header", texture_header), ("texture source", texture_source), ("backend header", backend_header), ("backend source", backend)):
    if negative_guard not in text:
        raise SystemExit(f"{name} does not compile-exclude desktop GL interop")

print("iOS Vulkan external texture gate valid: desktop GL class, types, and GLsync cleanup excluded")
