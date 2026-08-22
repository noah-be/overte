#!/usr/bin/env python3
"""Protect the reusable no-rebuild iOS entity-rendering diagnostics."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


shared = read("libraries/shared/src/shared/IOSRuntimeLogging.h")
application = read("interface/src/Application.cpp")
renderer = read("libraries/entities-renderer/src/RenderableEntityItem.cpp")
cull = read("libraries/render/src/render/CullTask.cpp")
backend = read("libraries/gpu-vk/src/gpu/vk/VKBackend.cpp")
pipeline = read("libraries/gpu-vk/src/gpu/vk/VKPipelineCache.cpp")
display = read("libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp")
smoke = read("ios/ci/interface-world-simulator-smoke.sh")
runtime = read(".github/workflows/ios-world-candidate-runtime.yml")
camera_script = read("ios/ci/ios-camera-first-person.js")
independent_camera_script = read("ios/ci/ios-camera-independent.js")

for token in (
    "OVERTE_IOS_RENDER_DIAGNOSTIC",
    "IOSRuntimeEntityEvidenceSnapshot",
    "recordIOSRuntimeSceneEntity",
    "recordIOSRuntimeDrawnEntity",
):
    assert token in shared, f"shared forensic state missing {token}"

for token in ("stage=import", "stage=camera", "getNearClip()", "getFarClip()"):
    assert token in application, f"camera/import forensics missing {token}"
for token in ("stage=scene_applied", "stage=render_enter"):
    assert token in renderer, f"scene/render transition missing {token}"
for token in ("stage=cpu_cull", '== "cpu-cull-off"'):
    assert token in cull, f"CPU culling diagnostic missing {token}"
for token in (
    "stage=gpu_draw",
    "DrawForward::run",
    "world_origin=",
    "clip_origin=",
    "bound_inputs=",
    "draw_infos=",
    "scissor=",
    '== "reset-format"',
    '== "full-scissor"',
    "for (const auto& binding : bindingMap)",
    "sets.reserve(bindingMap.size())",
    "OVERTE_IOS_VULKAN_DESCRIPTOR fallback=texture",
    "OVERTE_IOS_VULKAN_DESCRIPTOR coverage=",
    "missingDescriptorBindings",
    "OVERTE_IOS_VULKAN_DRAW_BUFFER",
    "range_valid=",
    "object_valid=",
):
    assert token in backend, f"Vulkan draw diagnostic missing {token}"

assert "for (size_t i = 0; i < _resource._textures.size(); i++)" not in backend, (
    "descriptor writes must cover every reflected texture binding"
)

for token in (
    "ios/vulkanPendingPipelines",
    "ios/vulkanQuarantinedPipelines",
    "OVERTE_IOS_VULKAN_ISOLATION recovered_unretired_submit",
    "OVERTE_IOS_VULKAN_PIPELINE_USE",
    "OVERTE_IOS_VULKAN_BATCH_USE",
    "action=skip_pipeline",
    "action=skip_batch",
    "persistIOSDiagnosticSubmit",
    "retireIOSDiagnosticSubmit",
):
    assert token in backend, f"persistent physical-iPad pipeline isolation missing {token}"

execute_frame = backend.index("void VKBackend::executeFrame")
clear_candidates = backend.index("_iosCurrentUntrustedPipelines.clear()", execute_frame)
render_batches = backend.index("for (const auto& batchPtr : frame->batches)", execute_frame)
assert clear_candidates < render_batches, "each encoded frame must start with an empty candidate set"

render_draw = backend.index("void VKBackend::renderPassDraw")
quarantine_decision = backend.index("const bool quarantinePipeline", render_draw)
draw_dispatch = backend.index("(this->*(call))(batch, *offset)", quarantine_decision)
assert quarantine_decision < draw_dispatch, "pipeline quarantine must run before draw dispatch"

fence_wait = display.index("vkWaitForFences")
retire_submit = display.index("retireIOSDiagnosticSubmit", fence_wait)
destroy_fence = display.index("vkDestroyFence", fence_wait)
assert fence_wait < retire_submit < destroy_fence, "only a successful fence may mark candidates healthy"

persist_submit = display.index("persistIOSDiagnosticSubmit")
queue_submit = display.index("vkQueueSubmit", persist_submit)
assert persist_submit < queue_submit, "candidate persistence must precede GPU submission"
for token in (
    '== "gpu-cull-off"',
    '== "depth-off"',
    "_ios-diagnostic:",
    "diagnostic_mode=",
):
    assert token in pipeline, f"Vulkan pipeline A/B diagnostic missing {token}"

for mode in (
    "trace",
    "cpu-cull-off",
    "gpu-cull-off",
    "depth-off",
    "full-scissor",
    "reset-format",
    "camera-first-person",
    "camera-independent",
):
    assert mode in smoke and mode in runtime, f"no-rebuild mode is not routed: {mode}"

for token in (
    "SIMCTL_CHILD_OVERTE_IOS_RENDER_DIAGNOSTIC",
    "SIMCTL_CHILD_MTL_CAPTURE_ENABLED=1",
    "SIMCTL_CHILD_MVK_CONFIG_AUTO_GPU_CAPTURE_SCOPE=3",
    "SIMCTL_CHILD_MVK_CONFIG_AUTO_GPU_CAPTURE_OUTPUT_FILE",
    "OVERTE_IOS_ENTITY_TRACE",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC",
    "phase=gpu-trace-triggered",
    "phase=gpu-trace-collected",
    "--defaultScriptsOverride",
    "ios-camera-first-person.js",
):
    assert token in smoke, f"simulator forensic harness missing {token}"

assert 'Camera.mode = "first person look at"' in camera_script
assert 'ScriptDiscoveryService.loadOneScript("file:///~//defaultScripts.js")' in camera_script
assert "Script.include(" not in camera_script
assert "Script.load(" not in camera_script
assert "MyAvatar.position = targetPosition" in camera_script
assert "MyAvatar.orientation = targetOrientation" in camera_script
assert "stage=avatar-reset" in camera_script
assert "function distanceSquared(a, b)" in camera_script
assert "Vec3.distance" not in camera_script
assert 'Settings.setValue("iosCameraDiagnostic", marker)' in camera_script
assert "refresh_camera_diagnostic_state" in smoke
assert "refresh_camera_file_log" in smoke
assert "firstRun" not in camera_script

assert 'Camera.mode = "independent"' in independent_camera_script
assert "Camera.position = targetPosition" in independent_camera_script
assert "Camera.orientation = targetOrientation" in independent_camera_script
assert 'ScriptDiscoveryService.loadOneScript("file:///~//defaultScripts.js")' in independent_camera_script
assert "function distanceSquared(a, b)" in independent_camera_script
assert "Vec3.distance" not in independent_camera_script
assert "camera=viewpoint" in independent_camera_script

gate_ready = smoke.index('live_log "phase=runtime-gates-ready')
capture_call = smoke.index("\ntrigger_gpu_trace\n", gate_ready)
assert gate_ready < capture_call, "Metal capture must start only after the world gates"

for token in (
    "render_diagnostic:",
    "gpu_trace:",
    "OVERTE_IOS_WORLD_RENDER_DIAGNOSTIC:",
    "OVERTE_IOS_WORLD_GPU_TRACE:",
):
    assert token in runtime, f"runtime-only workflow missing {token}"

print("PASS reusable iOS entity-rendering forensic and A/B contract")
