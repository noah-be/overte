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

function createRun() {
    const clock = { now: 1000 };
    const operations = [];
    const saved = [];
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
        Render: { getConfig() { return {}; } },
        Scene: {},
        Test: {
            saveObject(value, name) {
                operations.push("save:" + name);
                saved.push({ value, name });
            }
        },
        Script: script,
        Window: windowObject,
        Entities: {
            findEntities() { return ["primitive"]; },
            getEntityProperties() {
                return {
                    type: "Box",
                    visible: true,
                    position: { x: 1, y: 2, z: 3 },
                    dimensions: { x: 1, y: 1, z: 1 }
                };
            }
        },
        MyAvatar: { position: {} },
        print() {}
    };
    vm.runInNewContext(source, context, { filename: scriptPath });
    assert.strictEqual(typeof script.interval, "function");
    assert.strictEqual(typeof windowObject.snapshotHandler, "function");

    function requestSnapshot() {
        script.interval();
        clock.now += 1000;
        script.interval();
        assert.strictEqual(windowObject.snapshotName, "macos-online-smoke.png");
    }

    return { clock, operations, requestSnapshot, saved, script, windowObject };
}

{
    const run = createRun();
    run.requestSnapshot();
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
    run.requestSnapshot();
    run.windowObject.snapshotHandler("");
    const completion = run.saved.find((entry) =>
        entry.name === "macos-online-smoke-completion.json");
    assert(completion);
    assert.strictEqual(completion.value.ready_for_external_validation, false);
    assert.strictEqual(completion.value.script_success, false);
    assert.strictEqual(run.script.stopped, true);
}

{
    const run = createRun();
    run.requestSnapshot();
    run.clock.now += 300000;
    run.script.interval();
    const completion = run.saved.find((entry) =>
        entry.name === "macos-online-smoke-completion.json");
    assert(completion, "deferred callback must leave durable validation evidence");
    assert.strictEqual(completion.value.ready_for_external_validation, true);
}

console.log("macOS online smoke script contract valid");
