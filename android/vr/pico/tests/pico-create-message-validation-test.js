#!/usr/bin/env node
// Device-free regression tests for the Pico Create QML message boundary.

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const repositoryRoot = path.resolve(__dirname, "../../../..");
const validate = require(path.join(repositoryRoot,
    "scripts/system/create/modules/picoQmlMessageValidation.js"));
const editSource = fs.readFileSync(path.join(repositoryRoot, "scripts/system/create/edit.js"), "utf8");

assert.strictEqual(validate(null), null);
assert.strictEqual(validate({}), null);
assert.strictEqual(validate({ method: 4 }), null);
assert.strictEqual(validate({ method: "" }), null);
assert.strictEqual(validate({ method: "picoRequestSelection", params: null }), null);
assert.strictEqual(validate({ method: "picoRequestSelection", params: [] }), null);
assert.deepStrictEqual(validate({ method: "picoRequestSelection" }), {
    method: "picoRequestSelection",
    params: {}
});
assert.deepStrictEqual(validate({ method: "picoNumericFocus", params: { focused: true } }), {
    method: "picoNumericFocus",
    params: { focused: true }
});

assert(editSource.includes("message = validatePicoQmlMessage(message);"));
assert(editSource.includes("Object.prototype.hasOwnProperty.call(buttonHandlers, message.params.buttonName)"));
assert(editSource.indexOf("Object.prototype.hasOwnProperty.call(buttonHandlers, message.params.buttonName)") <
    editSource.indexOf("buttonHandlers[message.params.buttonName]();"));

console.log("PASS Pico Create QML message validation");
