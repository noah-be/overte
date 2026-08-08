// Device-free behavior tests for Pico Create QML message validation.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const path = require("path");
const validate = require(path.resolve(__dirname,
    "../../scripts/system/create/modules/picoPropertiesValidation.js"));

function validProperties() {
    return {
        name: "Box",
        position: { x: 1, y: 2, z: 3 },
        rotation: { x: 10, y: 20, z: 30 },
        dimensions: { x: 0.5, y: 1, z: 2 },
        color: { red: 12, green: 128, blue: 300 },
        visible: true,
        dynamic: false,
        collisionless: false,
        script: "must-not-pass"
    };
}

const result = validate(validProperties());
assert.deepStrictEqual(result.position, { x: 1, y: 2, z: 3 });
assert.deepStrictEqual(result.dimensions, { x: 0.5, y: 1, z: 2 });
assert.deepStrictEqual(result.color, { red: 12, green: 128, blue: 255 });
assert.strictEqual(result.script, undefined, "unexpected entity fields must be removed");

for (const field of ["position", "rotation", "dimensions"]) {
    const candidate = validProperties();
    candidate[field].x = Infinity;
    assert.strictEqual(validate(candidate), null, `${field} must reject infinity`);
}
const badColor = validProperties();
badColor.color.red = NaN;
assert.strictEqual(validate(badColor), null, "color must reject NaN");
const smallDimensions = validProperties();
smallDimensions.dimensions = { x: -1, y: 0, z: 0.0001 };
assert.deepStrictEqual(validate(smallDimensions).dimensions,
    { x: 0.001, y: 0.001, z: 0.001 });
const wrongBoolean = validProperties();
wrongBoolean.dynamic = "false";
assert.strictEqual(validate(wrongBoolean), null, "boolean strings must be rejected");

process.stdout.write("PASS Pico Create property message validation\n");
