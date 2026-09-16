"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { FakeSignal } = require("../support");

test("signal delivers arguments in connection order without duplicate listeners", () => {
    const signal = new FakeSignal();
    const calls = [];
    const first = (...args) => calls.push(["first", ...args]);
    signal.connect(first);
    signal.connect(first);
    signal.connect((...args) => calls.push(["second", ...args]));

    signal.emit("value", 7);

    assert.deepEqual(calls, [["first", "value", 7], ["second", "value", 7]]);
    assert.equal(signal.listenerCount, 2);
});

test("signal delivery remains stable when a listener disconnects itself", () => {
    const signal = new FakeSignal();
    const calls = [];
    function selfRemoving() {
        calls.push("self");
        signal.disconnect(selfRemoving);
    }
    signal.connect(selfRemoving);
    signal.connect(() => calls.push("other"));

    signal.emit();
    signal.emit();

    assert.deepEqual(calls, ["self", "other", "other"]);
});
