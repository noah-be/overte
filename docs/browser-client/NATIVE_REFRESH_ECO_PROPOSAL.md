# Separate post-startup ECO experiment

Proposal only; no native or gateway code is activated here. The failed constructor CUSTOM5/CUSTOM3 experiment remains default off and is not replaced silently.

Current pinned primary sources establish two different operations:

- `PerformanceManager::setupPerformancePresetSettings` maps UNKNOWN to the platform-selected native graphics preset. That applies Render method/effects/scale, LOD and its default refresh profile. Constructor CUSTOM5 skips this path.
- `PerformanceScriptingInterface::setRefreshRateProfile` delegates only to RefreshRateManager. Numeric ECO0 is a declared, valid scripting enum value. CUSTOM3 is absent from that scripting enum and must not be sent as a workaround.
- ECO targets focus-active20, focus-inactive10, unfocus5, minimized2, startup30 and shutdown30 Hz. Those are targets, not measured cadence. Actual native QML draw/frame latency can change and must pass its existing bounds.

A causal next experiment can keep the ordinary private Interface.json payload exactly unchanged, including UNKNOWN/default platform selection. On an independently owned fresh native worker only, wait for actual domain permission approval plus a non-startup/non-shutdown refresh regime and a confirmed ordinary performance preset1–4. Read and retain the ordinary preset, Render method/shadow/haze/bloom/AO/viewport-scale values and LOD detail. Require the original refresh profile0–2 so restoration is possible. Then call **only** `Performance.setRefreshRateProfile(0)` once; immediately assert preset and all retained Render/LOD values are unchanged. Never call setPerformancePreset, native graphics setters or a browser quality/DPR setter. A missing getter, unexpected regime/preset or changed setting refuses the experiment.

First run this in the actual isolated gateway worker with opt-in diagnostics, exact source hashes and normal browser controls. Prove an actual cold Tablet Home frame inside the existing30-second bound, app input/frame continuity, actual two-way voice, pose/native agreement, leave/rejoin and owned-process cleanup. Measure native CPU over an equal-workload/source-bound baseline and verify browser quality/drawing-buffer dimensions stayed equal. Only an actual result can justify production enablement. If first-frame latency fails, a second distinct experiment may defer ECO until the first acknowledged real Tablet frame; that does not prove early/never-opened-worker savings and must be reported separately.

For a temporary readonly-test process that continues after its trusted script ends, restore only the captured original valid refresh profile0–2 during scriptEnding. A per-visitor worker deleted on session teardown needs no host-persistent setting restoration. No existing shared native observer or unrelated process is changed by this proposal.
