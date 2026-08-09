"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { createScriptApi, createTabletApi, runProductionScript } = require("../support");

const source = path.resolve(__dirname, "../../../../scripts/system/quickGoto.js");
const fallback = "file:///~/serverless/tutorial.json";

function start(home) {
    const Script = createScriptApi();
    const Tablet = createTabletApi();
    const Window = { location: "unchanged" };
    const lookups = [];
    const location = { handleLookupString(value) { lookups.push(value); } };
    const LocationBookmarks = { getHomeLocationAddress() { return home.value; } };
    runProductionScript(source, { LocationBookmarks, Script, Tablet, Window, location });
    return {
        Script, Window, lookups,
        tablet: Tablet.getTablet("com.highfidelity.interface.tablet.system")
    };
}

test("production quick-goto routes Tutorial and a valid trimmed Home", () => {
    const home = { value: "  hifi://welcome  " };
    const { Window, lookups, tablet } = start(home);
    const tutorial = tablet.buttons.find((button) => button.properties.text === "Tutorial");
    const homeButton = tablet.buttons.find((button) => button.properties.text === "Home");

    tutorial.click();
    assert.equal(Window.location, fallback);
    homeButton.click();
    assert.deepEqual(lookups, ["hifi://welcome"]);
    assert.equal(tablet.presentationCalls.filter((call) => call.action === "hide").length, 2);
});

test("production quick-goto fails closed for malformed persisted destinations", () => {
    const home = { value: "hifi://bad\nfile:///tmp/evil" };
    const { Window, lookups, tablet } = start(home);
    const homeButton = tablet.buttons.find((button) => button.properties.text === "Home");

    for (const invalid of [home.value, `hifi://${"x".repeat(4097)}`, "   ", null, 42]) {
        home.value = invalid;
        Window.location = "unchanged";
        homeButton.click();
        assert.equal(Window.location, fallback);
    }
    assert.deepEqual(lookups, []);
});

test("production quick-goto removes both buttons on script shutdown", () => {
    const home = { value: "hifi://welcome" };
    const { Script, tablet } = start(home);
    const registered = [...tablet.buttons];
    Script.end();
    assert.equal(tablet.buttons.length, 0);
    assert.deepEqual(tablet.removedButtons, registered);
});
