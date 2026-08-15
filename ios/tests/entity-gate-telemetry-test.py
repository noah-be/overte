#!/usr/bin/env python3
"""Source contract for iOS-only production entity gate telemetry."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PREFIX = "OVERTE_IOS_ENTITY_GATE"
CONTRACT = {
    "domain_list_connected": "libraries/networking/src/NodeList.cpp",
    "entity_server_active": "interface/src/Application.cpp",
    "entity_query_sent": "interface/src/Application_Entities.cpp",
    "entity_data_received": "interface/src/octree/OctreePacketProcessor.cpp",
    "entity_tree_nonempty": "libraries/shared/src/shared/IOSRuntimeLogging.h",
    "render_handoff": "libraries/shared/src/shared/IOSRuntimeLogging.h",
}

all_occurrences = []
for marker, relative_path in CONTRACT.items():
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    token = f'"{PREFIX} {marker}"'
    if source.count(token) != 1:
        raise SystemExit(f"expected exactly one {token} in {relative_path}")
    position = source.index(token)
    guard = source.rfind("#if defined(Q_OS_IOS) || defined(OVERTE_IOS)", 0, position)
    end = source.find("#endif", position)
    if guard < 0 or end < 0 or source.find("#endif", guard, position) >= 0:
        raise SystemExit(f"marker {marker} is not enclosed by its iOS compile guard")
    call = source.rfind("logIOSRuntimeMarker(", 0, position)
    if call < guard:
        raise SystemExit(f"marker {marker} is not emitted through Apple unified logging")
    all_occurrences.append(token)

helper = (ROOT / "libraries/shared/src/shared/IOSRuntimeLogging.h").read_text(
    encoding="utf-8"
)
if 'os_log_info(OS_LOG_DEFAULT, "%{public}s", utf8.constData())' not in helper:
    raise SystemExit("iOS runtime marker helper must mirror markers to unified logging")
if "recordIOSRuntimeRenderableEntity" not in helper or "commitIOSRuntimeEntityEvidence" not in helper:
    raise SystemExit("tree and renderer evidence must be correlated across the commit boundary")

renderer = (ROOT / "libraries/entities-renderer/src/EntityTreeRenderer.cpp").read_text(
    encoding="utf-8"
)
if "recordIOSRuntimeRenderableEntity(entityID.toString())" not in renderer:
    raise SystemExit("render handoff must record the exact renderable entity")

document = (ROOT / "docs/ios/ENTITY_INTEGRATION.md").read_text(encoding="utf-8")
for marker in CONTRACT:
    if f"`{marker}`" not in document:
        raise SystemExit(f"marker {marker} is not documented")

if len(all_occurrences) != 6:
    raise SystemExit("telemetry contract must contain exactly six gates")

print("iOS entity telemetry valid: 6 guarded production markers documented")
