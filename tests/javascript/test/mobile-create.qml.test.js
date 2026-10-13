"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

test("real native Create QML supports pointer editing and narrow tablet layout", t => {
    const source = path.resolve(__dirname, "../../../scripts/system/create/tests/qml/tst_native_create.qml");
    const result = spawnSync("qmltestrunner", ["-input", source], {
        env: { ...process.env, QT_QPA_PLATFORM: "offscreen", QT_QUICK_BACKEND: "software" },
        encoding: "utf8", timeout: 60000
    });
    if (result.error && result.error.code === "ENOENT") { t.skip("Qt Quick Test runner unavailable"); return; }
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /5 passed, 0 failed/);
});
