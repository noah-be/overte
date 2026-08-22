#!/usr/bin/env python3
"""Source contract for the fail-closed iOS full-client renderer selection."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
text = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

bootstrap_return = text.index("if(OVERTE_IOS_BOOTSTRAP_ONLY)")
backend_default = text.index('set(_overte_default_rendering_backend "Vulkan")')
if bootstrap_return >= backend_default:
    raise SystemExit("backend requirement must remain after the bootstrap-only early return")

required = (
    "if(IOS)",
    'set(_overte_default_rendering_backend "Vulkan")',
    'set(_overte_default_rendering_backend "OpenGL")',
    'set(OVERTE_RENDERING_BACKEND "${_overte_default_rendering_backend}" CACHE STRING',
    'if(IOS AND NOT OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")',
    "OpenGL is not a supported iOS renderer",
)
for token in required:
    if token not in text:
        raise SystemExit(f"iOS rendering backend contract missing {token!r}")

if text.count('set(_overte_default_rendering_backend "OpenGL")') != 1:
    raise SystemExit("non-iOS OpenGL default was not preserved exactly once")

print("iOS rendering backend contract valid: Vulkan default and fail-closed requirement")
