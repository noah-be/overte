#!/usr/bin/env python3
"""Fail-closed contract for the remaining iOS Vulkan/GL migration boundary."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

for token in (
    "OVERTE_IOS_VULKAN_NATIVE_TARGETS gpu-vk vk",
    'OVERTE_IOS_VULKAN_LEGACY_GL_BRIDGE_TARGETS ""',
    "${OVERTE_IOS_VULKAN_LEGACY_GL_BRIDGE_TARGETS}",
    "${OVERTE_IOS_VULKAN_NATIVE_TARGETS}",
):
    if token not in cmake:
        raise SystemExit(f"hybrid graph classification missing {token!r}")

inventory = json.loads((ROOT / "ios/rendering-integration-inventory.json").read_text(encoding="utf-8"))
blocker = next(check for check in inventory["checks"] if check["id"] == "hybrid-opengl-dependency")
if blocker["status"] != "implemented":
    raise SystemExit("hybrid backend migration must be implemented after emptying the legacy list")
tasks = blocker.get("subtasks", [])
if len(tasks) < 5 or tasks[0]["id"] != "classify-cmake-targets" or tasks[0]["status"] != "implemented":
    raise SystemExit("migration plan must begin with the completed CMake classification")
implemented = [task for task in tasks if task["status"] == "implemented"]
pending = [task for task in tasks if task["status"] == "pending"]
if [task["id"] for task in implemented[:5]] != [
    "classify-cmake-targets",
    "separate-gpu-vk-external-texture-gl-interop",
    "separate-gpu-vk-gl-fence-interop",
    "separate-vulkan-display-quick-gl-copy",
    "remove-gpu-vk-gl-link",
]:
    raise SystemExit("implemented GL gates are not in the documented migration order")
if pending:
    raise SystemExit("hybrid backend inventory still has pending source tasks")

print(f"iOS Vulkan hybrid GL migration valid: {len(implemented)} completed, {len(pending)} pending source tasks")
