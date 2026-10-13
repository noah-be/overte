"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
test("real native chat QML supports touch, keyboard, history and tablet lifecycle", () => {
    const file = path.resolve(__dirname, "../../device/contracts/chat/test_chat_qml.py");
    const result = spawnSync("python3", [file], { encoding: "utf8", timeout: 65000 });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /7 passed, 0 failed/);
});
