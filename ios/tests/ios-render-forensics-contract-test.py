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
smoke = read("ios/ci/interface-world-simulator-smoke.sh")
runtime = read(".github/workflows/ios-world-candidate-runtime.yml")
camera_script = read("ios/ci/ios-camera-first-person.js")

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
):
    assert token in backend, f"Vulkan draw diagnostic missing {token}"
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
assert 'Script.load("/~//defaultScripts.js")' in camera_script
assert "Script.include(" not in camera_script
assert 'Settings.setValue("iosCameraDiagnostic", marker)' in camera_script
assert "refresh_camera_diagnostic_state" in smoke
assert "refresh_camera_file_log" in smoke
assert "firstRun" not in camera_script

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
