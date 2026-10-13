// SPDX-License-Identifier: Apache-2.0
// Execute the Pico startup profile and the shared native Emote at its product seams.
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = path.resolve(__dirname, "../../../..");

function signal() {
    const slots = new Set();
    return {
        connect: fn => slots.add(fn),
        disconnect: fn => slots.delete(fn),
        emit: (...args) => [...slots].forEach(fn => fn(...args)),
        get count() { return slots.size; }
    };
}

function startup(relative, debug) {
    const calls = [];
    const values = new Map();
    const context = {
        Settings: { getValue: key => values.get(key), setValue: (key, value) => values.set(key, value) },
        MyAvatar: { vrWalkSpeed: 4 },
        Window: { interstitialModeEnabled: false },
        Menu: {
            menuExists: () => true, menuItemExists: () => false, addMenuItem: () => {},
            isOptionChecked: () => debug, menuItemEvent: signal()
        },
        Script: {
            // FileResourceRequest selects startup content at the logical scripts root URL.
            resolvePath: name => path.resolve(root, "scripts", name),
            include: name => calls.push(["include", name]),
            load: name => calls.push(["load", name]),
            scriptEnding: signal()
        },
        print: () => {}
    };
    vm.runInNewContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    return { calls, values, avatar: context.MyAvatar };
}

for (const debug of [false, true]) {
    const legacy = startup("scripts/+android_questInterface/defaultScripts.js", debug);
    const pico = startup("scripts/+android_picoInterface/defaultScripts.js", debug);
    const emotes = pico.calls.filter(([, name]) => name.endsWith("/phoneEmote.js"));
    assert.strictEqual(emotes.length, 1, "One normal Emote engine must be loaded");
    assert.strictEqual(emotes[0][0], "load", "Emote cleanup belongs to its own script engine");
    assert.ok(fs.existsSync(path.resolve(root, "scripts", emotes[0][1])),
        "Emote uses bundled shared content");
    const separateApps = ["system/snapshot.js", "communityScripts/armored-chat/armored_chat.js",
        "communityScripts/chatBubbles/chatBubbles.js", "communityScripts/notificationCore/notificationCore.js"];
    for (const app of separateApps) {
        const loaded = pico.calls.filter(([, name]) => name === app);
        assert.strictEqual(loaded.length, 1, "One normal engine for " + app);
        assert.strictEqual(loaded[0][0], "load", "Each app owns its subscriptions and cleanup");
        assert.ok(fs.existsSync(path.resolve(root, "scripts", app)), "Each app is bundled locally");
    }
    assert.deepStrictEqual(pico.calls.filter(([, name]) => !name.endsWith("/phoneEmote.js") && !separateApps.includes(name)), legacy.calls,
        "Keep all existing VR entry points and startup order");
    assert.deepStrictEqual(pico.values, legacy.values, "Preserve reviewed Pico startup settings");
    assert.deepStrictEqual(pico.avatar, legacy.avatar, "Preserve movement/avatar defaults");
}

const clicked = signal();
const screenChanged = signal();
const fromQml = signal();
const scriptEnding = signal();
const states = [];
const overrides = [];
const timers = new Map();
const resources = new Map();
let restoreCount = 0;
let removed = 0;
let timerId = 0;
let source = "";
const button = { clicked };
const tablet = {
    screenChanged, fromQml,
    addButton: properties => { assert.strictEqual(properties.text, "EMOTE"); return button; },
    removeButton: value => { assert.strictEqual(value, button); removed++; },
    sendToQml: state => states.push(state),
    loadQMLSource: value => { source = value; screenChanged.emit("QML", value); },
    gotoHomeScreen: () => screenChanged.emit("Home", "")
};
const emoteDirectory = path.join(root, "scripts/system/+android_phoneInterface");
vm.runInNewContext(fs.readFileSync(path.join(emoteDirectory, "phoneEmote.js"), "utf8"), {
    Tablet: { getTablet: () => tablet },
    AnimationCache: {
        prefetch: url => {
            assert.ok(fs.existsSync(url), "Each animation is packaged locally");
            const resource = { state: 3 };
            resources.set(url, resource);
            return resource;
        },
        getAnimation: () => ({ frames: [0, 1, 2, 3, 4, 5] })
    },
    MyAvatar: {
        overrideAnimation: (...args) => overrides.push(args),
        restoreAnimation: () => restoreCount++
    },
    Script: {
        resolvePath: name => path.resolve(emoteDirectory, name), scriptEnding,
        setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
        clearTimeout: id => timers.delete(id)
    }
});
assert.strictEqual(resources.size, 12, "Ten emotes include three bundled sitting variants");
fromQml.emit({ method: "phoneEmote.play", name: "Waving" });
assert.strictEqual(overrides.length, 0, "Ignore messages from another tablet screen");
clicked.emit();
assert.ok(fs.existsSync(source), "Native QML is bundled and has no web dependency");
fromQml.emit({ method: "phoneEmote.ready" });
assert.strictEqual(states.at(-1).active, "");
fromQml.emit({ method: "phoneEmote.play", name: "untrusted-url.fbx" });
assert.strictEqual(overrides.length, 0);
for (const resource of resources.values()) resource.state = 2;
fromQml.emit({ method: "phoneEmote.play", name: "Waving" });
assert.strictEqual(overrides.length, 0, "Wait for loaded animation data");
assert.strictEqual(states.at(-1).status, "Animation is still loading");
for (const resource of resources.values()) resource.state = 3;
fromQml.emit({ method: "phoneEmote.play", name: "Waving" });
assert.strictEqual(states.at(-1).active, "Waving");
assert.strictEqual(timers.size, 1);
fromQml.emit({ method: "phoneEmote.play", name: "Waving" });
assert.strictEqual(states.at(-1).active, "");
assert.strictEqual(timers.size, 0, "Second controller click stops the active emote");
fromQml.emit({ method: "phoneEmote.play", name: "Dancing" });
screenChanged.emit("QML", "other-app.qml");
assert.strictEqual(timers.size, 0, "Leaving Emote restores normal avatar animation");
clicked.emit();
fromQml.emit({ method: "phoneEmote.play", name: "Clapping" });
assert.strictEqual(timers.size, 1);
scriptEnding.emit();
assert.strictEqual(timers.size, 0, "Script reload cannot retain playback callbacks");
assert.strictEqual(removed, 1);
assert.ok(restoreCount >= 3);
assert.strictEqual(clicked.count + screenChanged.count + fromQml.count, 0);
console.log("PASS Pico startup preserves VR defaults and exposes native Emote playback/cleanup");
