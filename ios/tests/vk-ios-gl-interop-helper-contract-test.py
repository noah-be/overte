#!/usr/bin/env python3
"""Keep desktop GL/Vulkan interop queries out of the iOS MoltenVK build."""

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/vk/src/vk/Helpers.cpp").read_text(encoding="utf-8")


def require(pattern: str, message: str) -> None:
    if not re.search(pattern, SOURCE, re.MULTILINE | re.DOTALL):
        raise SystemExit(message)


require(
    r"#if !defined\(Q_OS_IOS\)\s+#include <gl/Config\.h>\s+#endif",
    "iOS must not include the desktop GL loader for Vulkan interop helpers",
)
require(
    r"UuidSet vks::util::gl::getUuids\(\) \{\s*#if defined\(Q_OS_IOS\)\s*return \{\};\s*#else"
    r"[\s\S]*GL_DRIVER_UUID_EXT[\s\S]*GL_NUM_DEVICE_UUIDS_EXT[\s\S]*#endif\s*\}",
    "iOS UUID discovery must fail closed while desktop keeps its extension queries",
)
require(
    r"contextSupported\(QOpenGLContext\*\) \{\s*#if defined\(Q_OS_IOS\)\s*return false;\s*#else"
    r"[\s\S]*GL_EXT_memory_object[\s\S]*GL_EXT_semaphore[\s\S]*#endif\s*\}",
    "iOS external GL interop must report unsupported while desktop retains capability checks",
)

ios_uuid_branch = SOURCE.split("UuidSet vks::util::gl::getUuids() {", 1)[1].split("#else", 1)[0]
for forbidden in ("glGet", "GL_DRIVER_UUID_EXT", "GL_NUM_DEVICE_UUIDS_EXT"):
    if forbidden in ios_uuid_branch:
        raise SystemExit(f"iOS UUID fallback retained desktop GL token {forbidden!r}")

for token in ("loadPipelineCacheData", "savePipelineCacheData"):
    if token not in SOURCE:
        raise SystemExit(f"Vulkan pipeline-cache support unexpectedly lost {token!r}")

print("vk iOS GL interop helpers valid: UUIDs empty and external GL unsupported")
