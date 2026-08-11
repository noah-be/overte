"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { createScriptApi, createTabletApi, runProductionScript } = require("../support");

const source = path.resolve(__dirname,
    "../../../../../scripts/system/+android_phoneInterface/mobileTabletApps.js");

function start() {
    const Script = createScriptApi();
    Script.resolvePath = (value) => `resolved:${value}`;
    const Tablet = createTabletApi();
    runProductionScript(source, { Script, Tablet });
    return { Script, tablet: Tablet.getTablet("com.highfidelity.interface.tablet.system") };
}

test("production tablet router registers and routes the first-party app buttons", () => {
    const { tablet } = start();
    assert.deepEqual(tablet.buttons.map((button) => button.properties.text),
        ["AUDIO", "SETTINGS", "MENU"]);

    tablet.buttons[0].click();
    tablet.buttons[1].click();
    tablet.buttons[2].click();

    assert.equal(tablet.navigation[0].type, "qml");
    assert.equal(tablet.navigation[0].args[0], "hifi/audio/Audio.qml");
    assert.equal(tablet.navigation[1].args[0], "resolved:../settings/Settings.qml");
    assert.equal(tablet.navigation[2].type, "menu");

    tablet.screenChanged.emit("QML", "hifi/audio/Audio.qml");
    tablet.buttons[0].click();
    assert.equal(tablet.navigation.at(-1).type, "home");
});

test("production settings bridge accepts only allowlisted routes from Settings", () => {
    const { tablet } = start();
    const settings = "resolved:../settings/Settings.qml";
    const before = tablet.navigation.length;

    tablet.fromQml.emit({ type: "switchApp", appUrl: "hifi/audio/Audio.qml" });
    tablet.screenChanged.emit("QML", "unrelated.qml");
    tablet.fromQml.emit({ type: "switchApp", appUrl: "hifi/audio/Audio.qml" });
    assert.equal(tablet.navigation.length, before);

    tablet.screenChanged.emit("QML", settings);
    tablet.fromQml.emit({ type: "switchApp", appUrl: "hifi/dialogs/GeneralPreferencesDialog.qml" });
    assert.equal(tablet.navigation.at(-1).args[0], "hifi/tablet/TabletGeneralPreferences.qml");

    const acceptedCount = tablet.navigation.length;
    for (const appUrl of [
        "https://evil.invalid/x.qml", "file:///tmp/x.qml", "__proto__", "constructor",
        "hifi/audio/Audio.qml\nfile:///tmp/x.qml"
    ]) {
        tablet.fromQml.emit({ type: "switchApp", appUrl });
    }
    tablet.fromQml.emit(null);
    tablet.fromQml.emit({ type: "switchApp", appUrl: 7 });
    assert.equal(tablet.navigation.length, acceptedCount);
});

test("production tablet router disconnects handlers and removes buttons on shutdown", () => {
    const { Script, tablet } = start();
    const registered = [...tablet.buttons];

    Script.end();

    assert.equal(tablet.buttons.length, 0);
    assert.deepEqual(tablet.removedButtons, registered);
    assert.equal(tablet.screenChanged.listenerCount, 0);
    assert.equal(tablet.fromQml.listenerCount, 0);
    for (const button of registered) {
        assert.equal(button.clicked.listenerCount, 0);
    }
});
