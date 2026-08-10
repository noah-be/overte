"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { createScriptApi, runProductionScript } = require("../support");

const source = path.resolve(__dirname, "../../../../scripts/system/places/portal.js");

function startPortal() {
    const Script = createScriptApi();
    Script.resolvePath = () => "/packaged/places/portal.js";
    let properties = { userData: "not-json", dimensions: { y: 2 } };
    const added = [];
    const deleted = [];
    const played = [];
    const Window = { location: "unchanged" };
    const Entities = {
        getEntityProperties: () => properties,
        addEntity(value) { added.push(value); return `child-${added.length}`; },
        deleteEntity(id) { deleted.push(id); }
    };
    const { result: constructor } = runProductionScript(source, {
        Audio: { playSound(...args) { played.push(args); return {}; } }, Entities,
        MyAvatar: { position: { x: 0, y: 0, z: 0 } }, Script,
        SoundCache: { getSound: () => ({}) }, Window
    });
    const portal = {};
    constructor.call(portal);
    return { Script, Window, added, deleted, played, portal, setProperties(value) { properties = value; } };
}

test("production portal fails closed for malformed and incomplete entity data", () => {
    const harness = startPortal();
    for (const properties of [
        { userData: "not-json", dimensions: { y: 2 } },
        { userData: JSON.stringify({ url: "hifi://x", name: "X" }), dimensions: { y: 2 } },
        { userData: JSON.stringify({ url: "bad\nurl", name: "X", placeID: "id" }), dimensions: { y: 2 } },
        { userData: JSON.stringify({ url: "hifi://x", name: "X", placeID: "id" }), dimensions: { y: Infinity } }
    ]) {
        harness.setProperties(properties);
        harness.portal.preload("portal");
        harness.portal.enterEntity("portal");
    }
    assert.equal(harness.added.length, 0);
    assert.equal(harness.played.length, 0);
    assert.equal(harness.Script.timers.size, 0);
    assert.equal(harness.Window.location, "unchanged");
});

test("production portal cancels navigation on unload and permits one active entry", () => {
    const harness = startPortal();
    harness.setProperties({
        userData: JSON.stringify({ url: "hifi://safe", name: "Safe", placeID: "id" }),
        dimensions: { y: 2 }
    });
    harness.portal.preload("portal");
    assert.equal(harness.added.length, 3);
    harness.portal.enterEntity("portal");
    harness.portal.enterEntity("portal");
    assert.equal(harness.played.length, 1);
    assert.equal(harness.Script.timers.size, 1);

    const timer = [...harness.Script.timers.keys()][0];
    harness.portal.unload();
    assert.equal(harness.Script.runTimer(timer), false);
    assert.equal(harness.Window.location, "unchanged");
    assert.deepEqual(harness.deleted, []);
});

test("production portal navigates only when its live timer completes", () => {
    const harness = startPortal();
    harness.setProperties({
        userData: JSON.stringify({ url: "hifi://safe", name: "Safe", placeID: "id" }),
        dimensions: { y: 2 }
    });
    harness.portal.preload("portal");
    harness.portal.enterEntity("portal");
    const timer = [...harness.Script.timers.keys()][0];
    harness.Script.runTimer(timer);
    assert.equal(harness.Window.location, "hifi://safe");
    assert.deepEqual(harness.deleted, ["portal"]);
});
