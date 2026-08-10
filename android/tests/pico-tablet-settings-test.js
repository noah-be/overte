// Device-free behavior tests for Pico tablet setting sanitization.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const path = require("path");
const sanitize = require(path.resolve(__dirname,
    "../../scripts/system/libraries/picoTabletSettings.js"));

assert.deepStrictEqual(sanitize(1.25, -0.52, -18),
    { forward: 1.25, up: -0.52, tilt: -18 });
assert.deepStrictEqual(sanitize("1.5", "-0.5", "10"),
    { forward: 1.5, up: -0.5, tilt: 10 });
assert.deepStrictEqual(sanitize(NaN, Infinity, -Infinity),
    { forward: 1.25, up: -0.52, tilt: -18 });
assert.deepStrictEqual(sanitize(-100, 100, 100),
    { forward: 0.4, up: 0.3, tilt: 30 });
assert.deepStrictEqual(sanitize(100, -100, -100),
    { forward: 2.0, up: -1.3, tilt: -45 });

process.stdout.write("PASS Pico tablet setting sanitization\n");
