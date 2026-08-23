// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const scriptPath = process.argv[2];
if (!scriptPath) {
    throw new Error("usage: node online-smoke-script-test.js online-smoke.js");
}
const source = fs.readFileSync(scriptPath, "utf8");
for (const forbiddenMutation of [
    "Render.renderMethod", "Render.shadowsEnabled", "Scene.shouldRenderAvatars",
    "Camera.mode =", "Camera.position =", "Camera.orientation =",
    "Entities.addEntity", "Entities.deleteEntity"
]) {
    assert(!source.includes(forbiddenMutation),
        "online smoke must not mutate production state: " + forbiddenMutation);
}

function createRun() {
    const clock = { now: 1000 };
    const operations = [];
    const saved = [];
    let modelLoaded = true;
    let texturesComplete = true;
    let entityIDs = ["model"];
    const script = {
        stopped: false,
        interval: null,
        setInterval(callback) { this.interval = callback; },
        stop() { operations.push("stop"); this.stopped = true; }
    };
    const windowObject = {
        snapshotHandler: null,
        snapshotName: null,
        stillSnapshotTaken: { connect(callback) { windowObject.snapshotHandler = callback; } },
        takeSnapshot(_notify, _animated, _aspect, name) {
            operations.push("snapshot:" + name);
            this.snapshotName = name;
        }
    };
    const context = {
        Date: { now: () => clock.now },
        Test: {
            getPresentCount() { return clock.now; },
            isTextureLoadingComplete() { return texturesComplete; },
            saveObject(value, name) {
                operations.push("save:" + name);
                saved.push({ value, name });
            }
        },
        Script: script,
        Stats: {
            downloads: 0,
            downloadsPending: 0,
            processing: 0,
            processingPending: 0,
            texturePendingTransfers: 0,
            forceUpdateStats() {}
        },
        Window: windowObject,
        Entities: {
            findEntities() { return entityIDs; },
            isLoaded() { return modelLoaded; },
            getEntityProperties() {
                return {
                    type: "Model",
                    visible: true,
                    position: { x: 1, y: 2, z: 3 },
                    dimensions: { x: 1, y: 0.25, z: 3 },
                    rotation: { x: 0, y: 0, z: 0, w: 1 }
                };
            }
        },
        MyAvatar: { position: { x: 10, y: 20, z: 30 } },
        print() {}
    };
    vm.runInNewContext(source, context, { filename: scriptPath });
    assert.strictEqual(typeof script.interval, "function");
    assert.strictEqual(typeof windowObject.snapshotHandler, "function");

    function requestSnapshot() {
        script.interval();
        clock.now += 5000;
        script.interval();
        assert.strictEqual(windowObject.snapshotName, "macos-online-smoke.png");
    }

    return {
        clock,
        operations,
        requestSnapshot,
        saved,
        script,
        windowObject,
        setModelLoaded(value) { modelLoaded = value; },
        setEntityIDs(value) { entityIDs = value; },
        setTexturesComplete(value) { texturesComplete = value; }
    };
}

{
    const run = createRun();
    run.setModelLoaded(false);
    run.script.interval();
    run.clock.now += 300000;
    run.script.interval();
    assert.strictEqual(run.windowObject.snapshotName, null,
        "an unloaded production Hub model must never produce a screenshot");
    run.setModelLoaded(true);
    run.script.interval();
    run.clock.now += 5000;
    run.script.interval();
    assert.strictEqual(run.windowObject.snapshotName, "macos-online-smoke.png");
}

{
    const run = createRun();
    run.requestSnapshot();
    assert(!run.operations.some((operation) => operation.startsWith("add:")));
    run.windowObject.snapshotHandler("/tmp/macos-online-smoke.png");
    const completion = run.saved.find((entry) =>
        entry.name === "macos-online-smoke-completion.json");
    assert(completion);
    assert.strictEqual(completion.value.schema_version, 1);
    assert.strictEqual(completion.value.ready_for_external_validation, true);
    assert.strictEqual(completion.value.script_success, true);
    assert(run.operations.indexOf("save:macos-online-smoke-completion.json") <
        run.operations.indexOf("stop"));
    assert.strictEqual(run.script.stopped, true);
    run.script.interval();
    assert.strictEqual(run.saved.filter((entry) =>
        entry.name === "macos-online-smoke-completion.json").length, 1);
}

{
    const run = createRun();
    run.setTexturesComplete(false);
    run.script.interval();
    run.clock.now += 5000;
    run.script.interval();
    assert.strictEqual(run.windowObject.snapshotName, null,
        "a production scene with pending textures must never produce a screenshot");
}

{
    const run = createRun();
    run.requestSnapshot();
    run.windowObject.snapshotHandler("");
    const completion = run.saved.find((entry) =>
        entry.name === "macos-online-smoke-completion.json");
    assert.strictEqual(completion, undefined,
        "failed snapshots must leave the process available for supervisor sampling");
    assert.strictEqual(run.script.stopped, true);
}

{
    const run = createRun();
    run.requestSnapshot();
    run.clock.now += 300000;
    run.script.interval();
    const completion = run.saved.find((entry) =>
        entry.name === "macos-online-smoke-completion.json");
    assert.strictEqual(completion, undefined,
        "a pending callback is not successful completion evidence");
    assert.strictEqual(run.script.stopped, false);
    run.clock.now += 1600000;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true);
    assert.strictEqual(run.saved.some((entry) =>
        entry.name === "macos-online-smoke-completion.json"), false,
    "timeout failures must be sampled by the outer supervisor");
}

{
    const run = createRun();
    run.setEntityIDs([]);
    run.script.interval();
    run.clock.now += 600000;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true,
        "an empty entity stream must fail before the full Hub deadline");
}

{
    const run = createRun();
    run.setModelLoaded(false);
    run.script.interval();
    run.clock.now += 600000;
    run.script.interval();
    assert.strictEqual(run.script.stopped, true,
        "stalled asset loading must fail before the full Hub deadline");
}

console.log("macOS online smoke script contract valid");
