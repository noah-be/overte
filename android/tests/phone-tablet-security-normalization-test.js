"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../interface/resources/qml/hifi/dialogs/security/SecuritySettings.js"), "utf8");
const context = {};
vm.createContext(context);
vm.runInContext(source, context);

assert.strictEqual(context.normalizeAllowlist(undefined), "");
assert.strictEqual(context.normalizeAllowlist(null), "");
assert.strictEqual(context.normalizeAllowlist(42), "");
assert.strictEqual(context.normalizeAllowlist(""), "");
assert.strictEqual(context.normalizeAllowlist("  https://one.invalid,\n hifi://two  "),
    "https://one.invalid\nhifi://two");
assert.strictEqual(context.normalizeAllowlist("https://one.invalid https://one.invalid"),
    "https://one.invalid");
assert.strictEqual(context.normalizeAllowlist("constructor,__proto__,constructor"),
    "constructor\n__proto__");

console.log("Phone Security allowlist normalization checks passed.");
