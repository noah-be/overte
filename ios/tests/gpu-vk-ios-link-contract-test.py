#!/usr/bin/env python3
"""Prove gpu-vk drops only its direct iOS GL link after source gating."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
text = (ROOT / "libraries/gpu-vk/CMakeLists.txt").read_text(encoding="utf-8")
start = text.index("if(IOS)")
other = text.index("else()", start)
end = text.index("endif()", other)
ios_branch = text[start:other]
other_branch = text[other:end]

if "link_hifi_libraries(shared shaders vk gpu render-utils)" not in ios_branch:
    raise SystemExit("iOS gpu-vk native link set is missing")
if " vk gl gpu " in ios_branch:
    raise SystemExit("iOS gpu-vk still directly links gl")
if "link_hifi_libraries(shared shaders vk gl gpu render-utils)" not in other_branch:
    raise SystemExit("non-iOS gpu-vk GL link was not preserved")

print("gpu-vk iOS link contract valid: direct gl removed; non-iOS preserved")
