"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const { createScriptApi, createTabletApi, runProductionScript } = require("../support");

const source = path.resolve(__dirname,
    "../../../../../scripts/system/+android_phoneInterface/mobileTabletApps.js");

const implementation = path.resolve(__dirname,
    "../../../../../scripts/system/tablet-ui/mobileTabletApps.js");
const settingsSource = path.resolve(path.dirname(implementation), "../settings/Settings.qml");

function start() {
    const Script = createScriptApi();
    const Tablet = createTabletApi();
    const execution = runProductionScript(source, { Script, Tablet });
    assert.deepEqual(execution.loadedFiles, [source, implementation],
        "the startup wrapper must execute the real implementation in this VM");
    return { Script, tablet: Tablet.getTablet("com.highfidelity.interface.tablet.system") };
}

test("production tablet router registers and routes the first-party app buttons", () => {
    const { tablet } = start();
    assert.deepEqual(tablet.buttons.map((button) => button.properties.text),
        ["AUDIO", "SETTINGS", "MENU"]);

    assert.equal(tablet.buttons[1].properties.semanticId, "app.settings");
    tablet.buttons[0].click();
    tablet.buttons[1].click();
    tablet.buttons[2].click();

    assert.equal(tablet.navigation[0].type, "qml");
    assert.equal(tablet.navigation[0].args[0], "hifi/audio/Audio.qml");
    assert.equal(tablet.navigation[1].args[0], settingsSource);
    assert.equal(tablet.navigation[2].type, "menu");

    tablet.screenChanged.emit("QML", "hifi/audio/Audio.qml");
    tablet.buttons[0].click();
    assert.equal(tablet.navigation.at(-1).type, "home");
});

test("production settings bridge accepts only allowlisted routes from Settings", () => {
    const { tablet } = start();
    const settings = settingsSource;
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
    tablet.fromQml.emit({ type: "other", appUrl: "hifi/audio/Audio.qml" });
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

test("production settings Back returns only from an allowlisted child surface", () => {
    const { Script, tablet } = start();
    for (const child of ["hifi/tablet/TabletGeneralPreferences.qml", "hifi/audio/Audio.qml",
        "hifi/dialogs/security/Security.qml"]) {
        tablet.screenChanged.emit("QML", child);
        tablet.fromQml.emit({ type: "settings.back" });
        assert.equal(tablet.navigation.at(-1).args[0], settingsSource);
    }
    const acceptedCount = tablet.navigation.length;
    for (const origin of ["unrelated.qml", "__proto__", "constructor", settingsSource]) {
        tablet.screenChanged.emit("QML", origin);
        tablet.fromQml.emit({ type: "settings.back" });
    }
    tablet.screenChanged.emit("Closed", "hifi/tablet/TabletGeneralPreferences.qml");
    tablet.fromQml.emit({ type: "settings.back" });
    tablet.screenChanged.emit("Home", "");
    tablet.fromQml.emit({ type: "settings.back" });
    assert.equal(tablet.navigation.length, acceptedCount);
    Script.end();
});
