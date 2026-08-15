// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const scriptPath = process.argv[2];
if (!scriptPath) {
    throw new Error("usage: node performance-script-test.js performance-smoke.js");
}
const source = fs.readFileSync(scriptPath, "utf8");

function createRun() {
    const clock = { now: 1000 };
    const present = { count: 100 };
    const output = [];
    const saved = [];
    const frameTimings = {
        active: false,
        finished: false,
        values: [],
        start() { this.active = true; },
        finish() { this.active = false; this.finished = true; },
        getValues() { return this.values.slice(); }
    };
    const script = {
        stopped: false,
        interval: null,
        setInterval(callback) { this.interval = callback; },
        stop() { this.stopped = true; }
    };
    const window = {
        snapshotHandler: null,
        snapshotName: null,
        snapshotNames: [],
        stillSnapshotTaken: {
            connect(callback) { window.snapshotHandler = callback; }
        },
        takeSnapshot(_notify, _includeAnimated, _aspect, name) {
            this.snapshotName = name;
            this.snapshotNames.push(name);
        }
    };
    const names = {
        red: "macOS smoke red cube",
        cyan: "macOS smoke cyan sphere",
        label: "macOS smoke label"
    };
    const context = {
        Date: { now: () => clock.now },
        Render: {
            getConfig() { return {}; }
        },
        Scene: {},
        FrameTimings: frameTimings,
        Test: {
            getPresentCount() { return present.count; },
            saveObject(value, name) { saved.push({ value, name }); }
        },
        Script: script,
        Window: window,
        Entities: {
            findEntities() { return Object.keys(names); },
            getEntityProperties(id) { return { name: names[id] }; }
        },
        MyAvatar: {
            position: {},
            setOrientationVar() {}
        },
        Quat: { normalize(value) { return value; } },
        Rates: { render: 1, present: 1, newFrame: 1, dropped: 0, simulation: 1 },
        print(message) { output.push(message); }
    };
    vm.runInNewContext(source, context, { filename: scriptPath });
    assert.strictEqual(typeof script.interval, "function");
    assert.strictEqual(typeof window.snapshotHandler, "function");

    function startMeasurement() {
        script.interval();
        assert.strictEqual(window.snapshotName, null,
            "fixture discovery must not capture the pre-handoff frame");
        clock.now += 4999;
        script.interval();
        assert.strictEqual(window.snapshotName, null,
            "warmup must retain the complete settling window");
        clock.now += 1;
        script.interval();
        assert.strictEqual(window.snapshotName, "macos-performance-warmup.png");
        window.snapshotHandler("/tmp/macos-performance-warmup.png");
        assert.strictEqual(frameTimings.active, false,
            "the shader-warmup snapshot must not start performance sampling");
        assert.deepStrictEqual(window.snapshotNames, ["macos-performance-warmup.png"]);
        clock.now += 4999;
        script.interval();
        assert.deepStrictEqual(window.snapshotNames, ["macos-performance-warmup.png"],
            "the final snapshot must wait for the complete cooldown");
        assert.strictEqual(frameTimings.active, false);
        clock.now += 1;
        script.interval();
        assert.deepStrictEqual(window.snapshotNames, ["macos-performance-warmup.png"],
            "elapsed cooldown alone must not substitute for new display presents");
        present.count += 1;
        script.interval();
        assert.deepStrictEqual(window.snapshotNames, ["macos-performance-warmup.png"],
            "one post-warmup present is insufficient");
        present.count += 1;
        script.interval();
        assert.deepStrictEqual(window.snapshotNames, [
            "macos-performance-warmup.png",
            "macos-performance.png"
        ]);
        assert.strictEqual(frameTimings.active, false,
            "requesting the final snapshot must not start sampling before it is saved");
        window.snapshotHandler("/tmp/macos-performance.png");
        assert.strictEqual(frameTimings.active, true);
        return clock.now;
    }

    function tick(now) {
        clock.now = now;
        script.interval();
    }

    return { clock, frameTimings, output, present, saved, script, startMeasurement, tick };
}

{
    const run = createRun();
    const startedAt = run.startMeasurement();
    run.frameTimings.values = Array(14).fill(1000);
    run.tick(startedAt + 20000);
    assert.strictEqual(run.script.stopped, false, "20 seconds alone must not end a short sample");
    run.frameTimings.values = Array(29).fill(1000);
    run.tick(startedAt + 40000);
    assert.strictEqual(run.script.stopped, false, "29 samples must not satisfy the gate");
    run.frameTimings.values = Array(30).fill(1000);
    run.tick(startedAt + 41000);
    assert.strictEqual(run.script.stopped, true);
    assert.strictEqual(run.saved.length, 1);
    assert.strictEqual(run.saved[0].name, "macos-performance.json");
    assert.strictEqual(run.saved[0].value.sample_count, 30);
    assert(run.output.some((line) => line.includes("fixture_settled_ms=5000")));
    assert(run.output.some((line) => line.includes("warmup_cooldown_ms=5000")));
    assert(run.output.some((line) => line.includes("presents=2")));
    assert(run.output.some((line) => line.includes("final_snapshot=/tmp/macos-performance.png")));
    assert(run.output.some((line) => line.includes("OVERTE_MACOS_PERFORMANCE passed samples=30")));
}

{
    const run = createRun();
    const startedAt = run.startMeasurement();
    run.frameTimings.values = Array(14).fill(1000);
    run.tick(startedAt + 90000);
    assert.strictEqual(run.script.stopped, true, "the hard measurement ceiling must stop the script");
    assert.strictEqual(run.saved[0].value.sample_count, 14);
    assert(run.output.some((line) => line.includes("OVERTE_MACOS_PERFORMANCE failed samples=14")));
}

console.log("macOS performance script contract valid");
