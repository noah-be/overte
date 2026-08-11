"use strict";

const assert = require("assert");
const path = require("path");

function signal() {
    const handlers = [];
    return {
        connect(callback) { handlers.push(callback); },
        disconnect(callback) {
            const index = handlers.indexOf(callback);
            assert.notStrictEqual(index, -1);
            handlers.splice(index, 1);
        },
        emit(...args) { handlers.slice().forEach((handler) => handler(...args)); },
        count() { return handlers.length; }
    };
}

function button() {
    return { clicked: signal(), entered: signal() };
}

const geometryChanged = signal();
const tabletShownChanged = signal();
const scriptEnding = signal();
const fragments = [];
const clearedTimers = [];
const timers = new Map();
let nextTimer = 1;
let vpadHidden = null;
let releases = 0;

function QmlFragment() {
    const fragment = {
        closed: false,
        buttons: [],
        addButton() {
            const result = button();
            this.buttons.push(result);
            return result;
        },
        setPosition() { if (this.closed) { throw new Error("destroyed"); } },
        setSize() { if (this.closed) { throw new Error("destroyed"); } },
        close() { this.closed = true; }
    };
    fragments.push(fragment);
    return fragment;
}

const tablet = {
    tabletShown: false,
    tabletShownChanged,
    showAndroidTablet() {},
    resizeAndroidTablet() {}
};

global.Audio = { muted: false };
global.Camera = { mode: "first person" };
global.MyAvatar = { cameraBoomLength: 0.5 };
global.DialogsManager = { showAddressBar() {} };
global.Window = { innerWidth: 1200, innerHeight: 600, geometryChanged };
global.Tablet = { getTablet() { return tablet; } };
global.QmlFragment = QmlFragment;
global.print = function () {};
global.Controller = {
    findDevice() { return 65535; },
    triggerHapticPulseOnDevice() {},
    setVPadHidden(value) { vpadHidden = value; },
    captureTouchEvents() {},
    releaseTouchEvents() { releases += 1; }
};
global.Script = {
    scriptEnding,
    setTimeout(callback) {
        const id = nextTimer++;
        timers.set(id, callback);
        return id;
    },
    clearTimeout(id) {
        assert(timers.delete(id));
        clearedTimers.push(id);
    }
};

require(path.resolve(__dirname,
    "../../../scripts/system/+android_phoneInterface/mobileActionBar.js"));

assert.strictEqual(fragments.length, 2);
assert.strictEqual(geometryChanged.count(), 2);
assert.strictEqual(tabletShownChanged.count(), 1);
assert.strictEqual(timers.size, 1);

// Simulate the QML object disappearing before the normal script teardown.
fragments[0].close();
geometryChanged.emit();
scriptEnding.emit();

assert.deepStrictEqual(clearedTimers, [1]);
assert.strictEqual(timers.size, 0);
assert.strictEqual(geometryChanged.count(), 0);
assert.strictEqual(tabletShownChanged.count(), 0);
assert(fragments.every((fragment) => fragment.closed));
assert.strictEqual(vpadHidden, false);
assert(releases >= 1);

console.log("Phone action-bar lifecycle mock checks passed.");
