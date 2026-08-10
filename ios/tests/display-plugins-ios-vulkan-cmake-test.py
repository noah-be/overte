#!/usr/bin/env python3
"""Source contract for the narrowly-scoped iOS Vulkan OpenGL guard."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
path = ROOT / "libraries/display-plugins/CMakeLists.txt"
text = path.read_text(encoding="utf-8")

condition = 'if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")'
start = text.index(condition, text.index("link_hifi_libraries"))
otherwise = text.index("else()", start)
end = text.index("endif()", otherwise)
ios_branch = text[start:otherwise]
preserved_branch = text[otherwise:end]

if "target_opengl()" in ios_branch:
    raise SystemExit("iOS Vulkan branch still invokes target_opengl")
for token in ('set(OpenGL_GL_PREFERENCE "GLVND")', "target_opengl()"):
    if token not in preserved_branch:
        raise SystemExit(f"desktop/Android OpenGL branch no longer preserves {token!r}")

# These dependencies are deliberately retained until their GL-using source is
# separated; this patch must not pretend that the complete graph is GL-free.
for token in ("link_hifi_libraries", "gl", "${PLATFORM_GL_BACKEND}"):
    if token not in text:
        raise SystemExit(f"expected retained GL graph evidence {token!r}")

print("display-plugins iOS Vulkan CMake guard valid; other platforms and GL graph preserved")
