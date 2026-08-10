#!/usr/bin/env python3
"""Contract for target-owned GL compatibility debt and acceptance gates."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = json.loads((ROOT / "ios/rendering-integration-inventory.json").read_text())
SURFACE = (ROOT / "libraries/qml/src/qml/OffscreenSurface.cpp").read_text()
QML_CMAKE = (ROOT / "libraries/qml/CMakeLists.txt").read_text()
VK_CMAKE = (ROOT / "libraries/vk/CMakeLists.txt").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


owners = {item["target"]: item for item in INVENTORY["target_owned_compatibility_dependencies"]}
require(set(owners) == {"qml", "vk"}, "compatibility ownership must name qml and vk")
require("link_hifi_libraries(shared networking gl)" in QML_CMAKE,
        "qml no longer owns the documented GL producer dependency")
require("link_hifi_libraries(shared shaders gl)" in VK_CMAKE,
        "vk no longer owns the documented compatibility-context dependency")
require("#include <gl/OffscreenGLCanvas.h>" not in SURFACE,
        "backend-neutral OffscreenSurface forwarding retains an unused concrete canvas include")

gates = {gate["id"]: gate for gate in INVENTORY["acceptance_gates"]}
require(gates["source-contracts"]["status"] == "implemented",
        "source gate must be locally implemented")
require(gates["iphoneos-full-graph-link"]["status"] == "unverified",
        "iphoneos link must remain external evidence")
require(gates["ipad-entity-render-handoff"]["status"] == "unverified",
        "device render handoff must remain external evidence")
require("OVERTE_IOS_ENTITY_GATE stage=render_handoff" in gates["ipad-entity-render-handoff"]["evidence"],
        "device acceptance lacks the production render marker")

print("rendering ownership/acceptance valid: qml+vk debt owned; link/device gates stay external")
