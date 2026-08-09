"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { runProductionScript } = require("../support");

const source = path.resolve(__dirname, "../../../../scripts/+android_phoneInterface/defaultScripts.js");
const expected = [
    "system/request-service.js",
    "system/progress.js",
    "system/+android_interface/touchscreenvirtualpad.js",
    "system/+android_phoneInterface/mobileActionBar.js",
    "system/+android_phoneInterface/mobileTabletApps.js",
    "system/+android_phoneInterface/phoneEmote.js",
    "system/bubble.js",
    "system/pal.js",
    "system/avatarapp.js",
    "system/places/places.js",
    "system/quickGoto.js"
];

function start() {
    const calls = [];
    const Script = {
        require(value) { calls.push(["require", value]); },
        include(value) { calls.push(["include", value]); }
    };
    const LODManager = { automaticLODAdjust: true, lodAngleDeg: 99 };
    const execution = runProductionScript(source, { Script, LODManager });
    return { ...execution, calls, LODManager };
}

test("phone bootstrap loads the control dependency before its minimal production set", () => {
    const state = start();
    assert.deepEqual(state.calls[0], ["require", "/~/system/+android_interface/androidControls.js"]);
    assert.deepEqual(state.calls.slice(1), expected.map((file) => ["include", file]));
    assert.equal(state.context.ANDROID_PHONE_INTERFACE, true);
    assert.deepEqual(Array.from(state.context.PHONE_DEFAULT_SCRIPTS), expected);
});

test("phone bootstrap applies conservative mobile LOD defaults", () => {
    const state = start();
    assert.equal(state.LODManager.automaticLODAdjust, false);
    assert.equal(state.LODManager.lodAngleDeg, 0.248);
});

test("explicit bootstrap restart retains deterministic script ordering", () => {
    const state = start();
    state.context.startPhoneDefaults();
    assert.deepEqual(state.calls.slice(1 + expected.length),
        expected.map((file) => ["include", file]));
});
