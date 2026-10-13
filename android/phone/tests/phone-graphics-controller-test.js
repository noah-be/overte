"use strict";
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
const assert = require("node:assert/strict");
const path = require("node:path");
const { createScriptApi, runProductionScript, FakeSignal } = require("../../common/tests/javascript/support");
const source = path.resolve(__dirname, "../../../scripts/system/+android_phoneInterface/phoneGraphics.js");
const settingsSource = path.resolve(path.dirname(source), "../settings/Settings.qml");

function run(options = {}) {
    const Script = createScriptApi();
    const store = new Map(Object.entries(options.store || {}));
    const writes = [];
    const frames = [];
    const grids = {};
    const operations = [];
    const Render = { hazeEnabled: false, proceduralMaterialsEnabled: false,
        viewportResolutionScale: 0.65, getConfig(name) {
            if (!grids[name]) {
                grids[name] = new Proxy({}, { set(target, key, value) {
                    operations.push([name, key, value]); target[key] = value; return true;
                } });
            }
            return grids[name];
        } };
    let lights = false;
    Object.defineProperty(Render, "localLightingEnabled", {
        get() { return lights; }, set(value) { operations.push(["lights", value]); lights = value; }
    });
    const tablet = { fromQml: new FakeSignal(), screenChanged: new FakeSignal(),
        sendToQml(message) { frames.push(JSON.parse(JSON.stringify(message))); } };
    const execution = runProductionScript(source, { Script, Render,
        ANDROID_PHONE_INTERFACE: options.phone === undefined ? true : options.phone,
        PlatformInfo: { getComputer() { return JSON.stringify({ OS: options.os || "ANDROID" }); } },
        Tablet: { getTablet() { return tablet; } }, Settings: {
            getValue(key, fallback) { return store.has(key) ? store.get(key) : fallback; },
            setValue(key, value) { writes.push([key, value]); store.set(key, value); }
        } });
    return { Script, store, writes, frames, grids, operations, Render, tablet, execution };
}

for (const options of [{ os: "IOS" }, { os: "MACOS" }, { phone: false }]) {
    const fixture = run(options);
    assert.equal(fixture.operations.length, 0, "non-Phone products receive no renderer writes");
    assert.equal(fixture.Script.scriptEnding.listenerCount, 0);
}
const fixture = run();
const { tablet, Render, grids, frames, operations, writes } = fixture;
function update(key, value) { tablet.fromQml.emit({ type: "phone.graphics.update", key, value }); }
update("localLights", true);
assert.equal(operations.length, 0, "Home cannot update graphics");
tablet.screenChanged.emit("QML", "unrelated.qml");
update("mirrors", true);
assert.equal(operations.length, 0, "other apps cannot update graphics");
tablet.screenChanged.emit("QML", settingsSource);
update("localLights", true);
for (const view of ["RenderMainView", "RenderSecondView"]) {
    const grid = grids[view + ".RenderForwardTask.LightClustering"];
    assert.deepEqual([grid.dimX, grid.dimY, grid.dimZ], [14, 14, 14]);
}
assert.equal(operations.at(-1)[0], "lights", "grid restored before lights are enabled");
assert.equal(Render.localLightingEnabled, true);
update("mirrors", true);
for (const view of ["RenderMainView", "RenderSecondView"]) {
    for (let index = 0; index < 3; ++index) {
        assert.equal(grids[view + ".RenderMirrorView" + index + "Depth0"].enabled, true);
    }
}
update("haze", true);
update("proceduralMaterials", true);
update("resolutionScale", 0.7);
assert.equal(Render.hazeEnabled, true);
assert.equal(Render.proceduralMaterialsEnabled, true);
assert.equal(Render.viewportResolutionScale, 0.7);
const beforeInvalid = writes.length;
for (const value of [0.49, 0.71, NaN, Infinity, "0.6", null, true]) { update("resolutionScale", value); }
for (const value of ["true", 1, null, {}]) { update("haze", value); }
for (const key of ["__proto__", "constructor", "renderMethod", "targetFps"]) { update(key, true); }
assert.equal(writes.length, beforeInvalid, "invalid keys/types/budgets never persist");
assert.equal(Render.viewportResolutionScale, 0.7);
assert.equal(frames.at(-1).values.haze, true);
update("localLights", false);
assert.equal(Render.localLightingEnabled, false);
assert.equal(grids["RenderMainView.RenderForwardTask.LightClustering"].dimX, 1);
const reopened = run({ store: Object.fromEntries(fixture.store) });
assert.equal(reopened.Render.hazeEnabled, true, "user choices restore after native startup resets baseline");
assert.equal(reopened.Render.proceduralMaterialsEnabled, true);
assert.equal(reopened.Render.viewportResolutionScale, 0.7);
assert.equal(reopened.grids["RenderMainView.RenderMirrorView0Depth0"].enabled, true);
const malformed = run({ store: { "phone/graphics/haze": "yes", "phone/graphics/resolutionScale": 2 } });
assert.equal(malformed.operations.length, 0, "malformed saved values leave safe defaults unchanged");
fixture.Script.end();
assert.equal(tablet.fromQml.listenerCount, 0);
assert.equal(tablet.screenChanged.listenerCount, 0);
console.log("PASS: Phone graphics lifecycle, persisted choices, light grids/mirrors and bounded input");
