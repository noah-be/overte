// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const scriptPath = process.argv[2];
if (!scriptPath) {
    throw new Error("usage: node serverless-smoke-script-test.js serverless-smoke.js");
}
const source = fs.readFileSync(scriptPath, "utf8");

const clock = { now: 1000 };
const state = { fixtures: true, importComplete: false, presentCount: 20 };
const output = [];
const snapshots = [];
const names = {
    red: "macOS smoke red cube",
    cyan: "macOS smoke cyan sphere",
    label: "macOS smoke label"
};
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
    Render: { getConfig() { return {}; } },
    Scene: {},
    Script: script,
    Window: window,
    Test: {
        getPresentCount() { return state.presentCount; },
        isServerlessSceneImportComplete() { return state.importComplete; }
    },
    Entities: {
        findEntities() { return state.fixtures ? Object.keys(names) : []; },
        getEntityProperties(id) {
            return { name: names[id], color: { red: 1, green: 2, blue: 3 } };
        }
    },
    MyAvatar: { position: {} },
    print(message) { output.push(message); }
};

vm.runInNewContext(source, context, { filename: scriptPath });
assert.strictEqual(typeof script.interval, "function");
assert.strictEqual(typeof window.handler, "function");

script.interval();
assert.deepStrictEqual(snapshots, [],
    "fixture names alone must not race an unfinished serverless import");

state.importComplete = true;
script.interval();
assert.deepStrictEqual(snapshots, ["macos-serverless-warmup.png"]);
window.handler("/tmp/macos-serverless-warmup.png");

clock.now += 5000;
state.presentCount += 1;
script.interval();
assert.strictEqual(snapshots.length, 1,
    "one present must not certify the post-import scene");

state.importComplete = false;
script.interval();
assert(output.some((line) => line.includes("fixture_reset_during_cooldown")));
assert.strictEqual(snapshots.length, 1,
    "an invalidated import must restart the visual warmup");

state.fixtures = false;
state.importComplete = true;
script.interval();
assert.strictEqual(snapshots.length, 1,
    "remembered fixture names must not substitute for current entities");

state.fixtures = true;
script.interval();
assert.deepStrictEqual(snapshots, [
    "macos-serverless-warmup.png",
    "macos-serverless-warmup.png"
]);
window.handler("/tmp/macos-serverless-warmup.png");
clock.now += 4999;
state.presentCount += 2;
script.interval();
assert.strictEqual(snapshots.length, 2,
    "the final snapshot must retain the complete cooldown");
clock.now += 1;
script.interval();
assert.deepStrictEqual(snapshots, [
    "macos-serverless-warmup.png",
    "macos-serverless-warmup.png",
    "macos-serverless-smoke.png"
]);
window.handler("/tmp/macos-serverless-smoke.png");
assert.strictEqual(script.stopped, true);
assert(output.some((line) => line.includes("cooldown_complete presents=2")));
assert(output.some((line) => line.includes("OVERTE_MACOS_SMOKE passed snapshot=")));

console.log("macOS serverless smoke script contract valid");
