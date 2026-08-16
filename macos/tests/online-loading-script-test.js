// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(process.argv[2], "utf8");
function createHarness(runnerClass, targetMode) {
    targetMode = targetMode || "public";
    const clock = { now: 1000, presentCount: 10 };
    const addressManager = { isConnected: true, protocol: "file", domainID: "" };
    const entities = {
        ids: ["red", "cyan", "label"],
        properties: {
            red: { name: "macOS smoke red cube", type: "Shape", visible: true },
            cyan: { name: "macOS smoke cyan sphere", type: "Shape", visible: true },
            label: { name: "macOS smoke label", type: "Text", visible: true },
            online: { name: "online primitive", type: "Shape", visible: true },
            sentinel: { name: "overte-macos-benchmark-v1", type: "Box", visible: true }
        }
    };
    const test = { beginCount: 0, entityTreeReady: false };
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
            cache_mode: "cold", concurrency: 10, run_index: 1, location_label: "hub",
            runner_class: runnerClass, navigation_id: "c10-p1-cold",
            location_sha256: "b".repeat(64), target_mode: targetMode,
            expected_domain_id: targetMode === "controlled" ?
                "12345678-1234-4234-9234-123456789abc" : "",
            expected_sentinel_name: targetMode === "controlled" ?
                "overte-macos-benchmark-v1" : ""
        },
        Date: { now: () => clock.now },
        Render: { getConfig() { return forwardConfig; } },
        Performance: { setRefreshRateProfile(value) { assert.strictEqual(value, 2); } },
        Scene: {},
        Stats: stats,
        Rates: { present: 60, newFrame: 59 },
        AddressManager: addressManager,
        Test: {
            isTextureLoadingComplete() { return true; },
            getPresentCount() { return clock.presentCount; },
            beginOnlineLoadingNavigation() { test.beginCount += 1; return true; },
            isOnlineLoadingEntityTreeReady() { return test.entityTreeReady; },
            recordOnlineLoadingVisible(visibleCount) { return visibleCount > 0; },
            saveObject(value, name) { saved.push({ value, name }); }
        },
        Script: script,
        Window: windowObject,
        Entities: {
            findEntities() { return entities.ids; },
            getEntityProperties(id) { return entities.properties[id] || {}; }
        },
        MyAvatar: { position: {} },
        print(message) { output.push(message); }
    };
    vm.runInNewContext(source, context, { filename: process.argv[2] });
    return { addressManager, clock, entities, output, saved, script, test, windowObject };
}

const hardware = createHarness("hardware");
assert.strictEqual(typeof hardware.script.interval, "function");
hardware.script.interval();
assert.strictEqual(hardware.test.beginCount, 0);
assert(!hardware.output.some((line) => line.includes("visible_candidate_ms=")));
hardware.clock.now += 500;
hardware.clock.presentCount += 1;
hardware.script.interval();
assert.strictEqual(hardware.test.beginCount, 1);
assert(hardware.output.some((line) => line.includes("started navigation_id=c10-p1-cold")));
hardware.clock.now += 500;
hardware.script.interval();
assert(!hardware.output.some((line) => line.includes("visible_candidate_ms=")));
hardware.addressManager.protocol = "hifi";
hardware.test.entityTreeReady = true;
hardware.entities.ids = ["online"];
hardware.clock.now += 500;
hardware.script.interval();
assert(hardware.output.some((line) => line.includes("visible_candidate_ms=1000")));
hardware.clock.now += 500;
hardware.clock.presentCount += 1;
hardware.script.interval();
assert(hardware.output.some((line) => line.includes("first_visible_ms=1500")));
assert.strictEqual(hardware.script.stopped, false);
assert.strictEqual(hardware.saved.length, 1);
assert.strictEqual(hardware.saved[0].name, "macos-online-loading-checkpoint.json");
assert.strictEqual(hardware.saved[0].value.evidence_stage, "first_visible_checkpoint");
assert.strictEqual(hardware.saved[0].value.reason, "first_visible_checkpoint");
assert.strictEqual(hardware.saved[0].value.first_visible_ms, 1500);
assert.strictEqual(hardware.saved[0].value.success, false);
const checkpointSampleCount = hardware.saved[0].value.queue_samples.length;
hardware.clock.now += 2000;
hardware.clock.presentCount += 1;
hardware.script.interval();
assert.strictEqual(hardware.windowObject.snapshotName, "macos-online-loading.png");
hardware.windowObject.snapshotHandler("/tmp/macos-online-loading.png");
hardware.clock.now += 3000;
hardware.clock.presentCount += 1;
hardware.script.interval();
assert.strictEqual(hardware.script.stopped, true);
assert.strictEqual(hardware.saved.length, 2);
assert.strictEqual(hardware.saved[1].name, "macos-online-loading.json");
assert.strictEqual(hardware.saved[1].value.runner_class, "hardware");
assert.strictEqual(hardware.saved[1].value.completed_idle, true);
assert.strictEqual(hardware.saved[1].value.completed_snapshot, true);
assert.strictEqual(hardware.saved[1].value.sustained_idle_ms, 6500);
assert.strictEqual(hardware.saved[1].value.navigation_id, "c10-p1-cold");
assert.strictEqual(hardware.saved[1].value.schema_version, 3);
assert.strictEqual(hardware.saved[1].value.target_mode, "public");
assert.strictEqual(hardware.saved[1].value.target_verified, false);
assert.strictEqual(hardware.saved[1].value.evidence_stage, "final");
assert(hardware.saved[1].value.queue_samples.length > checkpointSampleCount);
assert(hardware.output.some((line) => line.includes("OVERTE_MACOS_ONLINE_LOADING passed")));

const incompleteBaseline = createHarness("hardware");
incompleteBaseline.entities.ids = ["red", "cyan"];
incompleteBaseline.script.interval();
incompleteBaseline.clock.now += 500;
incompleteBaseline.clock.presentCount += 1;
incompleteBaseline.script.interval();
assert.strictEqual(incompleteBaseline.test.beginCount, 0);
assert(!incompleteBaseline.output.some((line) => line.includes("started navigation_id=")));

const diagnostic = createHarness("diagnostic");
diagnostic.script.interval();
diagnostic.clock.now += 500;
diagnostic.clock.presentCount += 1;
diagnostic.script.interval();
diagnostic.addressManager.protocol = "hifi";
diagnostic.test.entityTreeReady = true;
diagnostic.entities.ids = ["online"];
diagnostic.clock.now += 500;
diagnostic.script.interval();
diagnostic.clock.now += 500;
diagnostic.clock.presentCount += 1;
diagnostic.script.interval();
diagnostic.clock.now += 30000;
diagnostic.script.interval();
assert.strictEqual(diagnostic.script.stopped, true);
assert.strictEqual(diagnostic.saved.length, 2);
assert.strictEqual(diagnostic.saved[0].name, "macos-online-loading-checkpoint.json");
assert.strictEqual(diagnostic.saved[0].value.reason, "first_visible_checkpoint");
assert.strictEqual(diagnostic.saved[1].name, "macos-online-loading.json");
assert.strictEqual(diagnostic.saved[1].value.runner_class, "diagnostic");
assert.strictEqual(diagnostic.saved[1].value.success, false);
assert.strictEqual(diagnostic.saved[1].value.completed_snapshot, false);
assert.strictEqual(diagnostic.saved[1].value.reason, "diagnostic_observation_complete");
assert(diagnostic.output.some((line) => line.includes("diagnostic_observation_complete")));

const controlled = createHarness("hardware", "controlled");
controlled.script.interval();
controlled.clock.now += 500;
controlled.clock.presentCount += 1;
controlled.script.interval();
controlled.addressManager.protocol = "hifi";
controlled.addressManager.domainID = "{12345678-1234-4234-9234-123456789abc}";
controlled.test.entityTreeReady = true;
controlled.entities.ids = ["online", "sentinel"];
controlled.clock.now += 500;
controlled.script.interval();
assert(controlled.output.some((line) => line.includes("controlled_target_verified")));
controlled.clock.now += 500;
controlled.clock.presentCount += 1;
controlled.script.interval();
assert.strictEqual(controlled.saved[0].value.target_mode, "controlled");
assert.strictEqual(controlled.saved[0].value.target_verified, true);

const wrongDomain = createHarness("hardware", "controlled");
wrongDomain.script.interval();
wrongDomain.clock.now += 500;
wrongDomain.clock.presentCount += 1;
wrongDomain.script.interval();
wrongDomain.addressManager.protocol = "hifi";
wrongDomain.addressManager.domainID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
wrongDomain.test.entityTreeReady = true;
wrongDomain.entities.ids = ["online", "sentinel"];
wrongDomain.clock.now += 500;
wrongDomain.script.interval();
assert.strictEqual(wrongDomain.script.stopped, true);
assert.strictEqual(wrongDomain.saved[0].value.reason, "controlled_domain_mismatch");
assert.strictEqual(wrongDomain.saved[0].value.target_verified, false);

console.log("macOS online loading script contract valid");
