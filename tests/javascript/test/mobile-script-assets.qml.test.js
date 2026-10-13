"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

test("native Scripts/Assets execute models, routes, keyboard, files and request lifecycle", t => {
    const qt5 = process.env.OVERTE_QT5_ROOT || path.join(os.homedir(), ".local/overte-qt5/root");
    const kit = fs.existsSync(path.join(qt5, "usr/lib64/pkgconfig/Qt5QuickTest.pc"));
    const available = ["Qt5QuickTest", "Qt6QuickTest"].some(name =>
        spawnSync("pkg-config", ["--exists", name]).status === 0);
    if (!kit && !available) { t.skip("Qt QuickTest/Widgets compiler prerequisites unavailable"); return; }
    const file = path.resolve(__dirname, "../../device/contracts/script_assets/test_script_assets_qml.py");
    const result = spawnSync("python3", [file], { encoding: "utf8", timeout: 120000 });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /13 passed, 0 failed/);
});
