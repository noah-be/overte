"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { createScriptApi } = require("../support");

test("script timers are deterministic and one-shot timers remove themselves", () => {
    const Script = createScriptApi();
    const calls = [];
    const timeout = Script.setTimeout(() => calls.push("timeout"), 25);
    const interval = Script.setInterval(() => calls.push("interval"), 10);

    assert.equal(Script.timers.get(timeout).delay, 25);
    assert.equal(Script.runTimer(timeout), true);
    assert.equal(Script.runTimer(timeout), false);
    assert.equal(Script.runTimer(interval), true);
    assert.equal(Script.runTimer(interval), true);
    Script.clearInterval(interval);

    assert.deepEqual(calls, ["timeout", "interval", "interval"]);
    assert.deepEqual(Script.clearedTimers, [interval]);
});

test("ending signal supports production-style cleanup", () => {
    const Script = createScriptApi();
    const timer = Script.setTimeout(() => assert.fail("cleared timer ran"), 1);
    Script.scriptEnding.connect(() => Script.clearTimeout(timer));

    Script.end();

    assert.equal(Script.runTimer(timer), false);
    assert.equal(Script.resolvePath("icons/a.svg"), "icons/a.svg");
});
