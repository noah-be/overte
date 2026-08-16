// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const scriptPath = process.argv[2];
if (!scriptPath) {
    throw new Error("usage: node profile-performance-script-test.js profile-performance-smoke.js");
}

const source = fs.readFileSync(scriptPath, "utf8");
const clock = { now: 1000 };
const present = { count: 100 };
const fixtureMode = process.env.OVERTE_TEST_FIXTURE_MODE || "full";
const expectedStressEntities = fixtureMode === "diagnostic-lite" ? 13 : 52;
const settleMilliseconds = fixtureMode === "diagnostic-lite" ? 5000 : 10000;
const minimumSamples = fixtureMode === "diagnostic-lite" ? 15 : 90;
const output = [];
const saved = [];
const deleted = [];
const created = [];
let nextEntity = 10;
const forwardConfig = {};
const frameTimings = {
    values: [],
    active: false,
    start() { this.active = true; },
    finish() { this.active = false; },
    getValues() { return this.values.slice(); }
};
const resourceQueue = {
    loading: 0, pending: 0, processing: 0, processing_pending: 0,
    texture_transfers: 0, texture_transfer_bytes: 0, idle: true
};
const script = {
    stopped: false,
    interval: null,
    endingHandler: null,
    setInterval(callback) { this.interval = callback; },
    stop() { this.stopped = true; },
    scriptEnding: { connect(callback) { script.endingHandler = callback; } }
};
const windowObject = {
    snapshotHandler: null,
    snapshotName: null,
    snapshotNames: [],
    stillSnapshotTaken: { connect(callback) { windowObject.snapshotHandler = callback; } },
    takeSnapshot(_notify, _includeAnimated, _aspect, name) {
        this.snapshotName = name;
        this.snapshotNames.push(name);
    }
};
const baseNames = {
    red: "macOS smoke red cube",
    cyan: "macOS smoke cyan sphere",
    label: "macOS smoke label"
};
const stats = {
    forceUpdateStats() {},
    gpuFrameTime: 4,
    batchFrameTime: 3,
    engineFrameTime: 5,
    drawcalls: 120,
    triangles: 4000,
    itemRendered: 52,
    shadowRendered: 20,
    gpuTextureMemory: 64,
    gpuTextureResidentMemory: 32,
    gpuTextureFramebufferMemory: 16,
    texturePendingTransfers: 0
};
const performance = {
    refreshRateProfile: -1,
    setRefreshRateProfile(value) { this.refreshRateProfile = value; }
};
const lodManager = {
    presentTime: 14,
    engineRunTime: 8,
    batchTime: 7,
    gpuTime: NaN
};
const context = {
    OVERTE_MACOS_PERFORMANCE_CASE: {
        fixture_version: "lit-grid-v2",
        fixture_mode: fixtureMode,
        fixture_features: fixtureMode === "diagnostic-lite" ?
            ["semantic-red-cyan", "unlit-grid"] : [
                "ambient-occlusion-geometry", "antialiasing-edge-target",
                "bloom-emissive-material", "directional-shadow", "haze-zone",
                "lit-pbr-material", "local-point-lights", "procedural-material",
                "semantic-red-cyan"
            ],
        fixture_sha256: "a".repeat(64),
        procedural_shader_url: "file:///tmp/profile-procedural.fs",
        run_index: 2,
        trace_path: "/tmp/profile-trace.json.gz",
        profile: {
            id: "forward-compat",
            quality_score: 35,
            render_method: 1,
            shadows: false,
            haze: false,
            bloom: false,
            ambient_occlusion: false,
            local_lighting: true,
            procedural_materials: false,
            antialiasing: 0,
            viewport_scale: 1,
            forward_samples: 1
        }
    },
    Date: { now: () => clock.now },
    Render: { getConfig() { return forwardConfig; } },
    Scene: {},
    Performance: performance,
    LODManager: lodManager,
    Stats: stats,
    FrameTimings: frameTimings,
    Test: {
        getPresentCount() { return present.count; },
        getResourceQueueStatus() { return Object.assign({}, resourceQueue); },
        startTracing() { return true; },
        stopTracing(path) { assert.strictEqual(path, "/tmp/profile-trace.json.gz"); return true; },
        saveObject(value, name) { saved.push({ value, name }); }
    },
    Script: script,
    Window: windowObject,
    Entities: {
        findEntities() { return Object.keys(baseNames); },
        getEntityProperties(id) { return { name: baseNames[id] }; },
        addEntity(properties, scope) {
            assert.strictEqual(scope, "local");
            created.push(properties);
            return ++nextEntity;
        },
        deleteEntity(id) { deleted.push(id); }
    },
    MyAvatar: { position: {}, setOrientationVar() {} },
    Quat: { normalize(value) { return value; } },
    Rates: { render: 60, present: 59, newFrame: 59, dropped: 0, simulation: 60 },
    PlatformInfo: {
        getPlatform() { return '{"name":"macOS"}'; },
        getComputer() { return '{"model":"Mac"}'; },
        getCPU() { return '{"model":"CPU"}'; },
        getGPU() { return '{"model":"GPU"}'; },
        getDisplay() { return '{"width":1380}'; },
        getPrimaryCPU() { return 0; },
        getPrimaryGPU() { return 0; },
        getPrimaryDisplay() { return 0; },
        getTierProfiled() { return 2; },
        isRenderMethodDeferredCapable() { return true; }
    },
    print(message) { output.push(message); }
};

vm.runInNewContext(source, context, { filename: scriptPath });
assert.strictEqual(context.Render.renderMethod, 1);
assert.strictEqual(performance.refreshRateProfile, 2);
assert.strictEqual(context.LODManager.automaticLODAdjust, false);
assert.strictEqual(forwardConfig.numSamples, 1);
assert.strictEqual(typeof script.interval, "function");

script.interval();
assert(output.some((line) => line.includes("stress_entities=" + expectedStressEntities)));
clock.now += settleMilliseconds;
script.interval();
assert.strictEqual(windowObject.snapshotName, "macos-profile-warmup.png");
windowObject.snapshotHandler("/tmp/macos-profile-warmup.png");
assert.strictEqual(frameTimings.active, false,
    "the shader-warmup image must not start performance sampling");
if (fixtureMode === "full") {
    clock.now += 1000;
    resourceQueue.texture_transfers = 1;
    resourceQueue.texture_transfer_bytes = 4096;
    resourceQueue.idle = false;
    script.interval();
    resourceQueue.texture_transfers = 0;
    resourceQueue.texture_transfer_bytes = 0;
    resourceQueue.idle = true;
    script.interval();
    clock.now += 1999;
    script.interval();
    assert.deepStrictEqual(windowObject.snapshotNames, ["macos-profile-warmup.png"],
        "post-warmup resource idle must remain continuous for the full interval");
    clock.now += 1;
    script.interval();
}
clock.now += 4999;
script.interval();
assert.deepStrictEqual(windowObject.snapshotNames, ["macos-profile-warmup.png"],
    "the final image must wait for the complete cooldown");
clock.now += 1;
script.interval();
assert.deepStrictEqual(windowObject.snapshotNames, ["macos-profile-warmup.png"],
    "elapsed cooldown alone must not substitute for new display presents");
const requiredPresents = fixtureMode === "diagnostic-lite" ? 1 : 2;
for (let index = 1; index < requiredPresents; index += 1) {
    present.count += 1;
    script.interval();
    assert.deepStrictEqual(windowObject.snapshotNames, ["macos-profile-warmup.png"],
        "the final image must wait for every required display present");
}
present.count += 1;
script.interval();
assert.deepStrictEqual(windowObject.snapshotNames, [
    "macos-profile-warmup.png",
    "macos-profile.png"
]);
assert.strictEqual(frameTimings.active, false,
    "requesting the final image must not start sampling before it is saved");
windowObject.snapshotHandler("/tmp/macos-profile.png");
assert.strictEqual(frameTimings.active, true);
frameTimings.values = Array(Math.max(120, minimumSamples)).fill(9000);
const measurementSteps = fixtureMode === "diagnostic-lite" ? [5000, 5000, 10000] : [10000, 10000, 10000];
clock.now += measurementSteps[0];
script.interval();
lodManager.presentTime = 15;
lodManager.engineRunTime = 9;
lodManager.batchTime = 8;
lodManager.gpuTime = 0;
clock.now += measurementSteps[1];
script.interval();
lodManager.presentTime = 16;
lodManager.engineRunTime = 10;
lodManager.batchTime = 9;
lodManager.gpuTime = 7;
clock.now += measurementSteps[2];
script.interval();

assert.strictEqual(script.stopped, true);
assert.strictEqual(saved.length, 1);
assert.strictEqual(saved[0].name, "macos-profile.json");
assert.strictEqual(saved[0].value.schema_version, 4);
assert.strictEqual(saved[0].value.measurement_complete, true);
assert.strictEqual(saved[0].value.fixture_mode, fixtureMode);
assert.strictEqual(saved[0].value.fixture_sha256, "a".repeat(64));
assert.strictEqual(saved[0].value.fixture_present_delta, requiredPresents);
assert.strictEqual(saved[0].value.resource_idle_required, fixtureMode === "full");
assert.strictEqual(saved[0].value.resource_idle_observed, fixtureMode === "full");
assert(fixtureMode !== "full" || saved[0].value.resource_idle_ms >= 2000);
if (fixtureMode === "diagnostic-lite") {
    assert.strictEqual(saved[0].value.resource_idle_ms, 0);
}
assert.strictEqual(saved[0].value.resource_queue_status.idle, true);
assert(saved[0].value.fixture_features.includes("semantic-red-cyan"));
if (fixtureMode === "full") {
    const procedural = created.find((item) =>
        item.name === "macOS profile procedural material target");
    const antialiasing = created.find((item) =>
        item.name === "macOS profile antialiasing edge target");
    assert(procedural && procedural.userData.includes("profile-procedural.fs"));
    assert(antialiasing && antialiasing.dimensions.y === 0.08);
}
assert.strictEqual(saved[0].value.profile_id, "forward-compat");
assert.strictEqual(saved[0].value.stress_entities, expectedStressEntities);
assert.strictEqual(saved[0].value.rates_hz.present.p50, 59);
assert.strictEqual(saved[0].value.stats.drawcalls.p50, 120);
assert.strictEqual(saved[0].value.lod_timings_ms.raw_samples.length, 3);
assert.strictEqual(saved[0].value.lod_timings_ms.present_ms.min, 14);
assert.strictEqual(saved[0].value.lod_timings_ms.present_ms.p50, 15);
assert.strictEqual(saved[0].value.lod_timings_ms.present_ms.max, 16);
assert.strictEqual(saved[0].value.lod_timings_ms.gpu_ms.invalid_count, 1);
assert.strictEqual(saved[0].value.lod_timings_ms.gpu_ms.zero_count, 1);
assert.strictEqual(saved[0].value.lod_timings_ms.gpu_ms.positive_count, 1);
assert.strictEqual(saved[0].value.lod_timings_ms.gpu_ms.raw_samples, undefined);
assert.strictEqual(saved[0].value.lod_timings_ms.raw_samples[0].gpu_ms, null);
assert.strictEqual(saved[0].value.lod_timings_ms.raw_samples[1].gpu_ms, 0);
assert.strictEqual(saved[0].value.lod_timings_ms.raw_samples[2].gpu_ms, 7);
assert.strictEqual(deleted.length, expectedStressEntities);
assert(output.some((line) => line.includes("warmup_snapshot=/tmp/macos-profile-warmup.png")));
assert(output.some((line) => line.includes("fixture_present_delta=" + requiredPresents)));
assert(output.some((line) => line.includes("final_snapshot=/tmp/macos-profile.png")));
assert(output.some((line) => line.includes("OVERTE_MACOS_PROFILE passed id=forward-compat")));

console.log("macOS profile performance script contract valid");
