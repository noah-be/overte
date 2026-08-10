#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let properties = { userData: "not-json", dimensions: { y: 2 } };
let added = 0;
let deleted = 0;
let played = 0;
let nextTimer = 1;
const timers = new Map();
const windowObject = { location: "unchanged" };
const context = {
    Script: {
        resolvePath() { return "/packaged/places/portal.js"; },
        setTimeout(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
        clearTimeout(id) { assert(timers.delete(id), "cleared timer must be active"); }
    },
    SoundCache: { getSound() { return {}; } },
    Entities: {
        getEntityProperties() { return properties; },
        addEntity() { added += 1; return `child-${added}`; },
        deleteEntity() { deleted += 1; }
    },
    MyAvatar: { position: { x: 0, y: 0, z: 0 } },
    Audio: { playSound() { played += 1; return {}; } },
    Window: windowObject,
    Math,
    JSON,
    isFinite
};

const source = fs.readFileSync(path.resolve(__dirname, "../../scripts/system/places/portal.js"), "utf8");
const constructor = vm.runInNewContext(source, context, { filename: "portal.js" });
const portal = {};
constructor.call(portal);

assert.doesNotThrow(() => portal.preload("portal"), "invalid JSON fails closed");
assert.strictEqual(added, 0, "invalid portal creates no child entities");
portal.enterEntity("portal");
assert.strictEqual(played, 0, "invalid portal cannot start teleport audio");
assert.strictEqual(timers.size, 0, "invalid portal cannot schedule teleport");

properties = {
    userData: JSON.stringify({ url: "hifi://example", name: "Example", placeID: "place" }),
    dimensions: { y: 2 }
};
portal.preload("portal");
assert.strictEqual(added, 3, "valid portal creates text, particles, and sound");
portal.enterEntity("portal");
portal.enterEntity("portal");
assert.strictEqual(played, 1, "repeated entry cannot duplicate teleport audio");
assert.strictEqual(timers.size, 1, "repeated entry owns one teleport timer");
portal.unload();
assert.strictEqual(timers.size, 0, "unload cancels pending teleport");
assert.strictEqual(windowObject.location, "unchanged", "cancelled teleport does not navigate");
assert.strictEqual(deleted, 0, "cancelled teleport does not delete through its callback");

portal.preload("portal");
portal.enterEntity("portal");
assert.strictEqual(timers.size, 1, "valid portal schedules one new teleport");
const callback = timers.values().next().value;
timers.clear();
callback();
assert.strictEqual(windowObject.location, "hifi://example", "valid teleport preserves navigation");
assert.strictEqual(deleted, 1, "completed teleport deletes its portal entity");

console.log("Phone Places portal lifecycle mock checks passed.");
