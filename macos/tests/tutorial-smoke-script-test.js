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

const clock = { now: 1000 };
const state = {
    importComplete: false,
    modelsLoaded: false,
    queuesIdle: false,
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
        isTextureLoadingComplete() { return state.queuesIdle; },
        saveObject(value, name) { saved[name] = value; }
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

script.interval();
assert.deepStrictEqual(snapshots, [], "entity names must not bypass import readiness");

state.importComplete = true;
state.queuesIdle = true;
script.interval();
assert.deepStrictEqual(snapshots, [], "unloaded tutorial models must block capture");

state.modelsLoaded = true;
script.interval();
assert.deepStrictEqual(snapshots, [], "readiness must begin a stable interval");

clock.now += 5000;
script.interval();
assert.deepStrictEqual(snapshots, [], "a new completed frame is required");

state.presentCount += 1;
script.interval();
assert.deepStrictEqual(snapshots, ["macos-tutorial-smoke.png"]);
assert(saved["macos-tutorial-entities.json"], "capture must persist entity evidence");
assert.strictEqual(saved["macos-tutorial-entities.json"].entity_count, 40);
assert.strictEqual(saved["macos-tutorial-entities.json"].loaded_expected_model_count, 16);

window.handler("/tmp/macos-tutorial-smoke.png");
assert.strictEqual(script.stopped, true);
assert(saved["macos-tutorial-smoke-completion.json"],
    "snapshot callback must persist durable completion evidence");
assert(output.some((line) => line.includes("OVERTE_MACOS_TUTORIAL passed snapshot=")));

console.log("macOS bundled tutorial smoke script contract valid");
