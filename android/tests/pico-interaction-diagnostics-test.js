// Device-free behavior test for pico4ObjectInteraction.js.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const dispatcherSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerDispatcher.js"), "utf8");
const farGrabSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerModules/farGrabEntity.js"), "utf8");
assert.ok(dispatcherSource.includes(
    "_this.activitySlots.hasOwnProperty(activitySlot)"),
"dispatcher must test ownership on the slot table");
assert.ok(!dispatcherSource.includes("activitySlot.hasOwnProperty(activitySlot)"),
    "dispatcher must not test ownership on a slot-name string");
assert.ok(farGrabSource.includes("if (manipulationPose && manipulationPose.valid)"),
    "off-hand rotation must be guarded by a current valid pose");
assert.ok(!farGrabSource.includes("Quat.multiply(pose.rotation"),
    "far grab must not consume the old unguarded pose variable");

let updateCallback;
let endingCallback;
const logs = [];
const values = Object.create(null);
const poses = {
    left: { valid: true, translation: { x: 0, y: 1, z: 0 } },
    right: { valid: true, translation: { x: 0, y: 1, z: 0 } }
};

global.Controller = {
    Standard: {
        LeftHand: "left", RightHand: "right",
        LT: "lt", RT: "rt", LTClick: "ltClick", RTClick: "rtClick",
        LeftGrip: "leftGrip", RightGrip: "rightGrip",
        LX: "lx", LY: "ly", RX: "rx", RY: "ry"
    },
    getPoseValue: input => poses[input],
    getValue: input => values[input] || 0
};
global.HMD = { mounted: true, isHandControllerAvailable: () => true };
global.MyAvatar = {};
global.Script = {
    update: {
        connect: callback => { updateCallback = callback; },
        disconnect: callback => assert.strictEqual(callback, updateCallback)
    },
    scriptEnding: { connect: callback => { endingCallback = callback; } }
};
global.console = { info: message => logs.push(message) };

require(path.resolve(__dirname,
    "../../scripts/developer/debugging/pico4ObjectInteraction.js"));

assert.ok(updateCallback, "diagnostic must sample on Script.update");
updateCallback();
values.lt = 0.96;
values.ltClick = 1;
updateCallback();
values.lt = 0;
values.ltClick = 0;
updateCallback();
poses.left = { valid: false, translation: { x: 0, y: 0, z: 0 } };
updateCallback();
poses.left = { valid: true, translation: { x: 0, y: 1, z: 0 } };
updateCallback();
endingCallback();

const summaryLine = logs.find(line => line.startsWith("PICO4_INTERACTION summary "));
assert.ok(summaryLine, "diagnostic must emit its final summary");
const summary = JSON.parse(summaryLine.slice("PICO4_INTERACTION summary ".length));
assert.strictEqual(summary.samples, 5);
assert.strictEqual(summary.triggerTransitions[0], 2);
assert.strictEqual(summary.triggerClickTransitions[0], 2);
assert.strictEqual(summary.trackingTransitions[0], 2);
assert.strictEqual(summary.invalidPose[0], 1);
assert.ok(logs.some(line => line === "PICO4_INTERACTION tracking left valid=false"));
assert.ok(logs.some(line => line === "PICO4_INTERACTION tracking left valid=true"));

process.stdout.write("PASS Pico interaction transition diagnostics\n");
