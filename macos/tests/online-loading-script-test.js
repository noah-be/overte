// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(process.argv[2], "utf8");
const clock = { now: 1000 };
const output = [];
const saved = [];
const forwardConfig = {};
const script = { stopped: false, interval: null,
    setInterval(callback) { this.interval = callback; }, stop() { this.stopped = true; } };
const windowObject = { snapshotHandler: null, snapshotName: null,
    stillSnapshotTaken: { connect(callback) { windowObject.snapshotHandler = callback; } },
    takeSnapshot(_notify, _includeAnimated, _aspect, name) { this.snapshotName = name; } };
const stats = {
    downloads: 0, downloadsPending: 0, processing: 0, processingPending: 0,
    texturePendingTransfers: 0, forceUpdateStats() {}
};
const context = {
    OVERTE_MACOS_ONLINE_LOADING_CASE: {
        cache_mode: "cold", concurrency: 10, run_index: 1, location_label: "hub"
    },
    Date: { now: () => clock.now },
    Render: { getConfig() { return forwardConfig; } },
    Performance: { setRefreshRateProfile(value) { assert.strictEqual(value, 2); } },
    Scene: {},
    Stats: stats,
    Rates: { present: 60, newFrame: 59 },
    Test: {
        isTextureLoadingComplete() { return true; },
        saveObject(value, name) { saved.push({ value, name }); }
    },
    Script: script,
    Window: windowObject,
    Entities: {
        findEntities() { return ["shape"]; },
        getEntityProperties() { return { type: "Shape", visible: true }; }
    },
    MyAvatar: { position: {} },
    print(message) { output.push(message); }
};

vm.runInNewContext(source, context, { filename: process.argv[2] });
assert.strictEqual(typeof script.interval, "function");
script.interval();
assert(output.some((line) => line.includes("first_visible_ms=0")));
clock.now += 2000;
script.interval();
assert.strictEqual(windowObject.snapshotName, "macos-online-loading.png");
windowObject.snapshotHandler("/tmp/macos-online-loading.png");
clock.now += 3000;
script.interval();
assert.strictEqual(script.stopped, true);
assert.strictEqual(saved.length, 1);
assert.strictEqual(saved[0].name, "macos-online-loading.json");
assert.strictEqual(saved[0].value.completed_idle, true);
assert.strictEqual(saved[0].value.completed_snapshot, true);
assert.strictEqual(saved[0].value.sustained_idle_ms, 5000);
assert(output.some((line) => line.includes("OVERTE_MACOS_ONLINE_LOADING passed")));

console.log("macOS online loading script contract valid");
