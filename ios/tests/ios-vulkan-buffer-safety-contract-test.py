#!/usr/bin/env python3
"""Protect physical-iOS GPU buffer bounds and no-rebuild isolation controls."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


backend = read("libraries/gpu-vk/src/gpu/vk/VKBackend.cpp")
backend_header = read("libraries/gpu-vk/src/gpu/vk/VKBackend.h")
background = read("libraries/render-utils/src/BackgroundStage.cpp")
cluster_grid = read("libraries/render-utils/src/LightClusterGrid.slh")
runtime = read("libraries/shared/src/shared/IOSRuntimeLogging.h")
example_path = ROOT / "ios/ci/overte-ios-render-diagnostics.example.json"
example = json.loads(example_path.read_text(encoding="utf-8"))

# Unnamed instanced draws must emulate OpenGL's constant DrawCallInfo rather
# than advancing from a single four-byte entry into allocator padding.
for token in (
    "replicatedInstances",
    "_unnamedDrawCallInfoOffsets",
    "_unnamedDrawCallInfoElementCounts",
    "_unnamedDrawCallInfoSourceIndices",
    "copiesPerInstance",
    "firstInstance + drawCommandInstanceCount",
    "firstInstance + effectiveInstances <= availableDrawCallInfoElements",
    "invalid=draw_call_info",
    "invalid=object_index",
):
    assert token in backend or token in backend_header, f"DrawCallInfo safety missing {token}"

update_transform = backend[backend.index("void VKBackend::updateTransform"):]
assert "_currentDraw * sizeof(gpu::Batch::DrawCallInfo)" not in update_transform, (
    "unnamed DrawCallInfo must use the replicated per-draw offset table"
)

# Cluster coordinates must be checked before the compact grid UBO is indexed.
fetch = cluster_grid[
    cluster_grid.index("<@func fetchClusterInfo"):
    cluster_grid.index("<@endfunc@>", cluster_grid.index("<@func fetchClusterInfo"))
]
assert fetch.index("greaterThanEqual(clusterPos") < fetch.index("clusterGrid_getCluster"), (
    "light-cluster bounds check must precede the grid read"
)

# Descriptor state changes include BufferView range changes and all reflected
# buffer bindings receive a validated real or zero fallback descriptor.
uniform_setter = backend[
    backend.index("void VKBackend::do_setUniformBuffer"):
    backend.index("void VKBackend::do_setResourceBuffer")
]
for token in (
    "currentBuffer.buffer == uniformBuffer.get()",
    "currentBuffer.offset == rangeStart",
    "currentBuffer.size == rangeSize",
    "releaseUniformBuffer(slot)",
):
    assert token in uniform_setter, f"uniform BufferView cache fix missing {token}"
for token in (
    "for (const auto& binding : bindingMap)",
    "fallback=uniform",
    "fallback=storage",
    "sourceRange <= sourceBytes - sourceOffset",
    "initDefaultBuffer",
):
    assert token in backend, f"descriptor range hardening missing {token}"

assert "setupKeyLightBatch" in background and "unsetKeyLightBatch" in background, (
    "forward skybox must bind and release its key-light UBO"
)

# Physical tests select stable shader names/pairs from a normal Documents JSON
# file, bypassing CFPreferences and unstable cache-local pipeline identities.
for token in (
    "overte-ios-render-diagnostics.json",
    "OVERTE_IOS_DIAGNOSTIC_CONFIG",
    "renderDiagnosticMode",
):
    assert token in runtime, f"direct diagnostic config missing {token}"
for key in (
    "skipBatchIds",
    "skipBatchNames",
    "skipPipelineIds",
    "skipVertexShaders",
    "skipFragmentShaders",
    "skipShaderPairs",
    "skipDrawCommands",
    "skipNamedCalls",
    "skipBatchCommands",
    "traceBatchNames",
    "traceVertexShaders",
    "traceFragmentShaders",
    "traceShaderPairs",
    "traceNamedCalls",
    "executeDrawOrdinalLimit",
    "forceZeroUniformBindings",
    "forceZeroStorageBindings",
    "forceFallbackTextureBindings",
    "forceFallbackTextureSources",
    "ignorePersistedQuarantine",
    "clearPersistedQuarantine",
    "persistSubmitCandidates",
):
    assert key in backend and key in example, f"no-rebuild selector missing {key}"

for token in (
    "OVERTE_IOS_VULKAN_TEXTURE",
    "batchCommandSelector",
    "_iosDrawOrdinal",
    "_iosTraceCurrentDraw",
):
    assert token in backend or token in backend_header, f"bounded physical trace missing {token}"

profiles = ROOT / "ios/ci/render-diagnostic-profiles"
for name in (
    "normal-trace.json",
    "trace-known-risk-paths.json",
    "isolate-particles.json",
    "isolate-translucent-models.json",
    "isolate-light-cluster-buffers.json",
    "diagnostics-off.json",
):
    payload = json.loads((profiles / name).read_text(encoding="utf-8"))
    assert payload.get("schemaVersion") == 1, f"invalid profile schema in {name}"

print("iOS Vulkan physical buffer safety and no-rebuild isolation contract valid")
