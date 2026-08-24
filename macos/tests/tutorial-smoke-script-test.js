// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const scriptPath = process.argv[2];
if (!scriptPath) {
    throw new Error("usage: node tutorial-smoke-script-test.js tutorial-smoke.js");
}
const source = fs.readFileSync(scriptPath, "utf8");
const expectedModels = [
    "Seagull", "LOGO", "Bowl", "Dome Glass", "trees", "Dome", "Temple",
    "Planters", "STAND-ANGLE_CONTROLS", "STAND-ANGLE_TABLET-TOOLBAR",
    "STAND-ANGLE_APPLICATIONS", "STAND-ANGLE_AVATAR",
    "STAND-ANGLE_CONFIG-WIZARD", "AVATAR_VIEWER_PLATFORM",
    "QUICK TEST AREA", "TELEPORTER"
];
const landmarks = [
    "MainDomeZone", "IN-WORLD PORTAL", "QUICK SETUP", "Avatar_Viewer_Sign"
];
const records = [];
expectedModels.forEach((name, index) => records.push({
    id: `model-${index}`, name, type: "Model", visible: true
}));
landmarks.forEach((name, index) => records.push({
    id: `landmark-${index}`, name, type: index === 0 ? "Zone" : "Text", visible: true
}));
while (records.length < 40) {
    records.push({
        id: `filler-${records.length}`,
        name: `filler-${records.length}`,
        type: "Shape",
        visible: true
    });
}

function createRun() {
    const clock = { now: 1000 };
    const state = {
        importComplete: false,
        modelsLoaded: false,
        queuesIdle: false,
        texturesComplete: true,
        presentCount: 10
    };
    const output = [];
    const snapshots = [];
    const saved = {};
    const script = {
        interval: null,
        stopped: false,
        setInterval(callback) { this.interval = callback; },
        stop() { this.stopped = true; }
    };
    const window = {
        handler: null,
        stillSnapshotTaken: {
            connect(callback) { window.handler = callback; }
        },
        takeSnapshot(_notify, _animated, _aspect, name) { snapshots.push(name); }
    };
    const context = {
        Date: { now: () => clock.now },
        isFinite,
        JSON,
        Script: script,
        Window: window,
        MyAvatar: { position: {} },
        Stats: {
            downloads: 1,
            downloadsPending: 0,
            processing: 0,
            processingPending: 0,
            texturePendingTransfers: 0,
            forceUpdateStats() {
                this.downloads = state.queuesIdle ? 0 : 1;
            }
        },
        Test: {
            getPresentCount() { return state.presentCount; },
            isServerlessSceneImportComplete() { return state.importComplete; },
            isTextureLoadingComplete() {
                return state.queuesIdle && state.texturesComplete;
            },
            getResourceQueueStatus() {
                return { texture_transfers: 0, texture_transfer_bytes: 0 };
            },
            saveObject(value, name) { saved[name] = value; }
        },
        Render: {
            getConfig(name) {
                assert.strictEqual(name, "Stats");
                return {
                    textureResourceGPUMemSize: 100,
                    textureResourcePopulatedGPUMemSize: 80
                };
            }
        },
        Entities: {
            findEntities() { return records.map((record) => record.id); },
            getEntityProperties(id) {
                const record = records.find((candidate) => candidate.id === id);
                return {
                    name: record.name,
                    type: record.type,
                    visible: record.visible,
                    position: { x: 1, y: 2, z: 3 },
                    dimensions: { x: 1, y: 1, z: 1 }
                };
            },
            isLoaded(id) {
                return state.modelsLoaded && id.startsWith("model-");
            }
        },
        print(message) { output.push(message); }
    };

    vm.runInNewContext(source, context, { filename: scriptPath });
    assert.strictEqual(typeof script.interval, "function");
    assert.strictEqual(typeof window.handler, "function");
    return { clock, output, saved, script, snapshots, state, window };
}

{
    const run = createRun();
    run.state.importComplete = true;
    run.state.modelsLoaded = true;
    run.state.queuesIdle = true;
    run.state.texturesComplete = false;
    run.script.interval();
    run.clock.now += 119999;
    run.script.interval();
    assert.strictEqual(run.script.stopped, false,
        "a changing or briefly delayed texture signal must retain a bounded grace");
    run.clock.now += 1;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true,
        "unchanged texture accounting must fail before the 55-minute deadline");
    assert(run.output.some((line) =>
        line.includes("tutorial_texture_readiness_stalled")));
}

{
    const run = createRun();
    run.script.interval();
    assert.deepStrictEqual(run.snapshots, [],
        "entity names must not bypass import readiness");

    run.state.importComplete = true;
    run.state.queuesIdle = true;
    run.script.interval();
    assert.deepStrictEqual(run.snapshots, [],
        "unloaded tutorial models must block capture");

    run.state.modelsLoaded = true;
    run.script.interval();
    assert.deepStrictEqual(run.snapshots, [],
        "readiness must begin a stable interval");

    run.clock.now += 5000;
    run.script.interval();
    assert.deepStrictEqual(run.snapshots, [], "a new completed frame is required");

    run.state.presentCount += 1;
    run.script.interval();
    assert.deepStrictEqual(run.snapshots, ["macos-tutorial-smoke.png"]);
    assert(run.saved["macos-tutorial-entities.json"],
        "capture must persist entity evidence");
    assert.strictEqual(run.saved["macos-tutorial-entities.json"].entity_count, 40);
    assert.strictEqual(
        run.saved["macos-tutorial-entities.json"].loaded_expected_model_count, 16);

    run.window.handler("/tmp/macos-tutorial-smoke.png");
    assert.strictEqual(run.script.stopped, true);
    assert(run.saved["macos-tutorial-smoke-completion.json"],
        "snapshot callback must persist durable completion evidence");
    assert(run.output.some((line) =>
        line.includes("OVERTE_MACOS_TUTORIAL passed snapshot=")));
}

{
    const run = createRun();
    run.script.interval();
    run.clock.now += 1200000;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true,
        "a tutorial with no entity, asset, or present progress must fail in twenty minutes");
    assert(run.output.some((line) =>
        line.includes("OVERTE_MACOS_TUTORIAL failed tutorial_progress_stalled")));
}

{
    const run = createRun();
    run.state.importComplete = true;
    run.state.modelsLoaded = true;
    run.state.queuesIdle = true;
    run.script.interval();
    run.clock.now += 1200000;
    run.script.interval();
    assert.strictEqual(run.script.stopped, false,
        "fully loaded content needs the measured first software-frame grace");
    run.clock.now += 1499999;
    run.script.interval();
    assert.strictEqual(run.script.stopped, false,
        "the first-frame grace must cover the observed sequential production draws");
    run.clock.now += 1;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true,
        "a genuinely stalled tutorial first frame must retain a finite bound");
    assert(run.output.some((line) =>
        line.includes("OVERTE_MACOS_TUTORIAL failed tutorial_first_frame_stalled")));
}

{
    const run = createRun();
    run.script.interval();
    run.clock.now += 1199999;
    run.state.presentCount += 1;
    run.script.interval();
    run.clock.now += 1199999;
    run.script.interval();
    assert.strictEqual(run.script.stopped, false,
        "a completed production frame must reset the tutorial progress clock");
    run.clock.now += 1;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true,
        "the reset progress clock must retain its finite twenty-minute bound");
}

console.log("macOS bundled tutorial smoke script contract valid");
