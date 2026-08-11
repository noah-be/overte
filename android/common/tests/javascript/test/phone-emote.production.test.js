"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { createScriptApi, createTabletApi, runProductionScript } = require("../support");

const source = path.resolve(__dirname,
    "../../../../../scripts/system/+android_phoneInterface/phoneEmote.js");

function start({ resourceState = 3, frames = 120 } = {}) {
    const Script = createScriptApi();
    Script.resolvePath = (value) => `asset:${value}`;
    const Tablet = createTabletApi();
    const avatarCalls = [];
    const MyAvatar = {
        overrideAnimation(...args) { avatarCalls.push(["override", ...args]); },
        restoreAnimation() { avatarCalls.push(["restore"]); }
    };
    const AnimationCache = {
        prefetch() { return { state: resourceState }; },
        getAnimation() { return { frames: { length: frames } }; }
    };
    runProductionScript(source, { AnimationCache, MyAvatar, Script, Tablet });
    return {
        AnimationCache, MyAvatar, Script, avatarCalls,
        tablet: Tablet.getTablet("com.highfidelity.interface.tablet.system")
    };
}

function openApp(tablet) {
    const button = tablet.buttons[0];
    button.click();
    const appSource = tablet.navigation.at(-1).args[0];
    tablet.screenChanged.emit("QML", appSource);
    return button;
}

test("production emote app plays an allowlisted animation and completes it", () => {
    const { Script, avatarCalls, tablet } = start();
    openApp(tablet);
    tablet.fromQml.emit({ method: "phoneEmote.ready" });
    tablet.fromQml.emit({ method: "phoneEmote.play", name: "Waving" });

    assert.equal(avatarCalls[0][0], "override");
    assert.match(avatarCalls[0][1], /Waving[.]fbx$/);
    assert.equal(tablet.qmlMessages.at(-1).active, "Waving");
    const timer = [...Script.timers.keys()][0];
    assert.equal(Script.timers.get(timer).delay, 2000);

    Script.runTimer(timer);
    assert.equal(avatarCalls.at(-1)[0], "restore");
    assert.equal(tablet.qmlMessages.at(-1).active, "");
    assert.equal(tablet.qmlMessages.at(-1).status, "Choose an emote");
});

test("production emote app rejects unknown and unavailable animations", () => {
    const unavailable = start({ resourceState: 1 });
    openApp(unavailable.tablet);
    unavailable.tablet.fromQml.emit({ method: "phoneEmote.play", name: "Waving" });
    assert.equal(unavailable.tablet.qmlMessages.at(-1).status, "Animation is still loading");
    assert.equal(unavailable.avatarCalls.length, 0);

    unavailable.tablet.fromQml.emit({ method: "phoneEmote.play", name: "../../evil" });
    assert.equal(unavailable.tablet.qmlMessages.at(-1).status, "Unsupported emote");
    assert.equal(unavailable.Script.timers.size, 0);
});

test("production emote app stops playback when closed and cleans up on shutdown", () => {
    const { Script, avatarCalls, tablet } = start();
    const button = openApp(tablet);
    tablet.fromQml.emit({ method: "phoneEmote.play", name: "Crying" });
    tablet.screenChanged.emit("Home", "");

    assert.equal(avatarCalls.at(-1)[0], "restore");
    assert.equal(Script.timers.size, 0);
    Script.end();
    assert.equal(tablet.buttons.length, 0);
    assert.equal(button.clicked.listenerCount, 0);
    assert.equal(tablet.fromQml.listenerCount, 0);
});
