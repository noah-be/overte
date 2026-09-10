#!/usr/bin/env python3
"""Source contract for iOS-only production entity gate telemetry."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PREFIX = "OVERTE_IOS_ENTITY_GATE"
CONTRACT = {
    "domainConnections": "libraries/networking/src/NodeList.cpp",
    "entityServers": "interface/src/Application.cpp",
    "entityQueries": "interface/src/Application_Entities.cpp",
    "entityPackets": "interface/src/octree/OctreePacketProcessor.cpp",
    "entityCommits": "libraries/shared/src/shared/IOSRuntimeLogging.h",
    "renderHandoffs": "libraries/shared/src/shared/IOSRuntimeLogging.h",
}

all_occurrences = []
for marker, relative_path in CONTRACT.items():
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    token = f'overte::ios::observeRender(overte::ios::RenderMetric::{marker});'
    if source.count(token) != 1:
        raise SystemExit(f"expected exactly one {token} in {relative_path}")
    position = source.index(token)
    guard = source.rfind("#if defined(Q_OS_IOS) || defined(OVERTE_IOS)", 0, position)
    end = source.find("#endif", position)
    if guard < 0 or end < 0 or source.find("#endif", guard, position) >= 0:
        raise SystemExit(f"marker {marker} is not enclosed by its iOS compile guard")
    # No raw log payload or endpoint identity is accepted as the transport.
    all_occurrences.append(token)

helper = (ROOT / "libraries/shared/src/shared/IOSRuntimeLogging.h").read_text(
    encoding="utf-8"
)
if 'os_log_info(OS_LOG_DEFAULT, "%{public}s", message);' not in helper:
    raise SystemExit("public logging must retain its closed event transport")
if "recordIOSRuntimeRenderableEntity" not in helper or "commitIOSRuntimeEntityEvidence" not in helper:
    raise SystemExit("tree and renderer evidence must be correlated across the commit boundary")

renderer = (ROOT / "libraries/entities-renderer/src/EntityTreeRenderer.cpp").read_text(
    encoding="utf-8"
)
if "recordIOSRuntimeRenderableEntity(entityID.toString())" not in renderer:
    raise SystemExit("render handoff must record the exact renderable entity")

document = (ROOT / "libraries/shared/src/shared/IOSRenderObservations.h").read_text(encoding="utf-8")
for marker in CONTRACT:
    if f"X({marker})" not in document:
        raise SystemExit(f"observation {marker} is absent from the bounded snapshot")

if len(all_occurrences) != 6:
    raise SystemExit("telemetry contract must contain exactly six gates")

consumer = (ROOT / "ios/render/WorldObservation.cpp").read_text()
assert 'renderObservations()' in consumer and 'result["renderProcess"]' in consumer
print("iOS entity observation source binding valid: six guarded counters; runtime acceptance unproved")
