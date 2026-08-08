#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const buttons = [];
let hidden = 0;
let home = "hifi://valid-home";
const lookups = [];
const windowObject = { location: "unchanged" };
const tablet = {
    hideAndroidTablet() { hidden += 1; },
    addButton(properties) {
        const button = {
            properties,
            clicked: { connect(callback) { button.click = callback; } }
        };
        buttons.push(button);
        return button;
    },
    removeButton() {}
};
const context = {
    Tablet: { getTablet() { return tablet; } },
    Script: { scriptEnding: { connect() {} } },
    Window: windowObject,
    location: { handleLookupString(value) { lookups.push(value); } },
    LocationBookmarks: { getHomeLocationAddress() { return home; } }
};

const source = fs.readFileSync(path.resolve(__dirname, "../../scripts/system/quickGoto.js"), "utf8");
vm.runInNewContext(source, context, { filename: "quickGoto.js" });
assert.strictEqual(buttons.length, 2, "Tutorial and Home buttons are registered");
const tutorial = buttons.find((button) => button.properties.text === "Tutorial");
const homeButton = buttons.find((button) => button.properties.text === "Home");

tutorial.click();
assert.strictEqual(windowObject.location, "file:///~/serverless/tutorial.json",
    "Tutorial opens packaged fallback content");
homeButton.click();
assert.deepStrictEqual(lookups, ["hifi://valid-home"], "valid Home uses address lookup");

home = `hifi://${"x".repeat(4096)}`;
windowObject.location = "unchanged";
homeButton.click();
assert.strictEqual(windowObject.location, "file:///~/serverless/tutorial.json",
    "overlong Home falls back to packaged content");
assert.deepStrictEqual(lookups, ["hifi://valid-home"], "overlong Home never reaches lookup");

home = "hifi://bad\naddress";
homeButton.click();
assert.deepStrictEqual(lookups, ["hifi://valid-home"], "control characters never reach lookup");
assert.strictEqual(hidden, 4, "every world action closes the screen-space tablet");

console.log("Phone Quick Goto contract mock checks passed.");
