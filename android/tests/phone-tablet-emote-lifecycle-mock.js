"use strict";

const assert = require("assert");
const path = require("path");

function signal() {
    let handler = null;
    return {
        connect(callback) { assert.strictEqual(handler, null); handler = callback; },
        disconnect(callback) { assert.strictEqual(handler, callback); handler = null; },
        emit(...args) { assert(handler); handler(...args); },
        connected() { return handler !== null; }
    };
}

const buttonClicked = signal();
const screenChanged = signal();
const fromQml = signal();
const scriptEnding = signal();
const sentMessages = [];
const overrides = [];
const clearedTimers = [];
let restored = 0;
let loadedSource = "";
let removedButton = null;
let nextTimer = 1;

const button = { clicked: buttonClicked };
const tablet = {
    screenChanged,
    fromQml,
    addButton(properties) {
        assert.strictEqual(properties.text, "EMOTE");
        return button;
    },
    removeButton(candidate) { removedButton = candidate; },
    loadQMLSource(source) { loadedSource = source; },
    gotoHomeScreen() {},
    sendToQml(message) { sentMessages.push(message); }
};

global.Tablet = { getTablet() { return tablet; } };
global.AnimationCache = {
    prefetch() { return { state: 3 }; },
    getAnimation() { return { frames: new Array(60) }; }
};
global.MyAvatar = {
    overrideAnimation(...args) { overrides.push(args); },
    restoreAnimation() { restored += 1; }
};
global.Script = {
    resolvePath(relativePath) { return "resolved:" + relativePath; },
    scriptEnding,
    setTimeout() { return nextTimer++; },
    clearTimeout(timer) { clearedTimers.push(timer); }
};

require(path.resolve(__dirname,
    "../../scripts/system/+android_phoneInterface/phoneEmote.js"));

assert(buttonClicked.connected());
assert(screenChanged.connected());
assert(fromQml.connected());

buttonClicked.emit();
assert.strictEqual(loadedSource, "resolved:PhoneEmote.qml");
screenChanged.emit("QML", loadedSource);
fromQml.emit({ method: "phoneEmote.ready" });
assert.strictEqual(sentMessages.at(-1).active, "");

fromQml.emit({ method: "phoneEmote.play", name: "not-allowlisted" });
assert.strictEqual(overrides.length, 0);
assert.strictEqual(sentMessages.at(-1).status, "Unsupported emote");

fromQml.emit({ method: "phoneEmote.play", name: "Crying" });
assert.strictEqual(overrides.length, 1);
assert.strictEqual(overrides[0][4], 60);
assert.strictEqual(sentMessages.at(-1).active, "Crying");

fromQml.emit({ method: "phoneEmote.play", name: "Crying" });
assert.deepStrictEqual(clearedTimers, [1]);
assert.strictEqual(restored, 1);
assert.strictEqual(sentMessages.at(-1).active, "");

fromQml.emit({ method: "phoneEmote.play", name: "Love" });
assert.strictEqual(overrides.length, 2);
screenChanged.emit("Home", "");
assert.deepStrictEqual(clearedTimers, [1, 2]);
assert.strictEqual(restored, 2);

screenChanged.emit("QML", loadedSource);
fromQml.emit({ method: "phoneEmote.play", name: "Waving" });
assert.strictEqual(overrides.length, 3);
scriptEnding.emit();
assert.deepStrictEqual(clearedTimers, [1, 2, 3]);
assert.strictEqual(restored, 3);
assert.strictEqual(removedButton, button);
assert(!buttonClicked.connected());
assert(!screenChanged.connected());
assert(!fromQml.connected());

console.log("Phone Emote lifecycle mock checks passed.");
