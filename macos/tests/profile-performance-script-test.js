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
const fixtureMode = process.env.OVERTE_TEST_FIXTURE_MODE || "full";
const expectedStressEntities = fixtureMode === "diagnostic-lite" ? 13 : 50;
const settleMilliseconds = fixtureMode === "diagnostic-lite" ? 5000 : 10000;
const minimumSamples = fixtureMode === "diagnostic-lite" ? 15 : 90;
const output = [];
const saved = [];
const deleted = [];
let nextEntity = 10;
const forwardConfig = {};
const frameTimings = {
    values: [],
    active: false,
    start() { this.active = true; },
    finish() { this.active = false; },
    getValues() { return this.values.slice(); }
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
    stillSnapshotTaken: { connect(callback) { windowObject.snapshotHandler = callback; } },
    takeSnapshot(_notify, _includeAnimated, _aspect, name) { this.snapshotName = name; }
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
const context = {
    OVERTE_MACOS_PERFORMANCE_CASE: {
        fixture_version: "lit-grid-v1",
        fixture_mode: fixtureMode,
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
    LODManager: {},
    Stats: stats,
    FrameTimings: frameTimings,
    Test: {
        startTracing() { return true; },
        stopTracing(path) { assert.strictEqual(path, "/tmp/profile-trace.json.gz"); return true; },
        saveObject(value, name) { saved.push({ value, name }); }
    },
    Script: script,
    Window: windowObject,
    Entities: {
        findEntities() { return Object.keys(baseNames); },
        getEntityProperties(id) { return { name: baseNames[id] }; },
        addEntity(_properties, scope) { assert.strictEqual(scope, "local"); return ++nextEntity; },
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
assert.strictEqual(windowObject.snapshotName, "macos-profile.png");
windowObject.snapshotHandler("/tmp/macos-profile.png");
assert.strictEqual(frameTimings.active, true);
frameTimings.values = Array(Math.max(120, minimumSamples)).fill(9000);
clock.now += 30000;
script.interval();

assert.strictEqual(script.stopped, true);
assert.strictEqual(saved.length, 1);
assert.strictEqual(saved[0].name, "macos-profile.json");
assert.strictEqual(saved[0].value.schema_version, 2);
assert.strictEqual(saved[0].value.measurement_complete, true);
assert.strictEqual(saved[0].value.fixture_mode, fixtureMode);
assert.strictEqual(saved[0].value.profile_id, "forward-compat");
assert.strictEqual(saved[0].value.stress_entities, expectedStressEntities);
assert.strictEqual(saved[0].value.rates_hz.present.p50, 59);
assert.strictEqual(saved[0].value.stats.drawcalls.p50, 120);
assert.strictEqual(deleted.length, expectedStressEntities);
assert(output.some((line) => line.includes("OVERTE_MACOS_PROFILE passed id=forward-compat")));

console.log("macOS profile performance script contract valid");
