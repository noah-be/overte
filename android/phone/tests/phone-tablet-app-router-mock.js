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

const fromQml = signal();
const screenChanged = signal();
const scriptEnding = signal();
const loadedSources = [];
const removedButtons = [];
const buttons = [];
const tablet = {
    fromQml,
    screenChanged,
    addButton(properties) {
        const button = { clicked: signal(), properties };
        buttons.push(button);
        return button;
    },
    removeButton(button) { removedButtons.push(button); },
    loadQMLSource(source) { loadedSources.push(source); },
    gotoMenuScreen() {},
    gotoHomeScreen() {}
};

global.Tablet = { getTablet() { return tablet; } };
global.Script = {
    resolvePath(relativePath) { return "resolved:" + relativePath; },
    scriptEnding
};

require(path.resolve(__dirname,
    "../../../scripts/system/+android_phoneInterface/mobileTabletApps.js"));

const settingsSource = "resolved:../settings/Settings.qml";

const acceptedRoutes = [
    ["hifi/tablet/TabletGeneralPreferences.qml", "hifi/tablet/TabletGeneralPreferences.qml"],
    ["hifi/dialogs/GeneralPreferencesDialog.qml", "hifi/tablet/TabletGeneralPreferences.qml"],
    ["hifi/audio/Audio.qml", "hifi/audio/Audio.qml"],
    ["hifi/dialogs/security/Security.qml", "hifi/dialogs/security/Security.qml"],
    ["hifi/dialogs/security/EntityScriptQMLAllowlist.qml",
        "hifi/dialogs/security/EntityScriptQMLAllowlist.qml"],
    ["hifi/dialogs/security/ScriptSecurity.qml", "hifi/dialogs/security/ScriptSecurity.qml"]
];

// Even allowlisted messages from Home or an unrelated QML app are ignored.
fromQml.emit({ type: "switchApp", appUrl: "hifi/audio/Audio.qml" });
screenChanged.emit("QML", "unrelated.qml");
fromQml.emit({ type: "switchApp", appUrl: "hifi/audio/Audio.qml" });
assert.strictEqual(loadedSources.length, 0);

acceptedRoutes.forEach(([request, expected]) => {
    screenChanged.emit("QML", settingsSource);
    fromQml.emit({ type: "switchApp", appUrl: request });
    assert.strictEqual(loadedSources.at(-1), expected);
});
assert.strictEqual(loadedSources.length, acceptedRoutes.length);
assert.strictEqual(buttons[1].properties.semanticId, "app.settings",
    "the real Phone Settings button carries the semantic contract ID");

[
    "hifi/tablet/TabletGeneralPreferences.qml",
    "hifi/audio/Audio.qml",
    "hifi/dialogs/security/Security.qml"
].forEach((source) => {
    screenChanged.emit("QML", source);
    fromQml.emit({ type: "settings.back" });
    assert.strictEqual(loadedSources.at(-1), settingsSource);
});
const afterSemanticBack = loadedSources.length;
screenChanged.emit("QML", "unrelated.qml");
fromQml.emit({ type: "settings.back" });
assert.strictEqual(loadedSources.length, afterSemanticBack,
    "semantic Back is accepted only from allowlisted Settings children");

[
    null,
    {},
    { type: "other", appUrl: "hifi/audio/Audio.qml" },
    { type: "switchApp" },
    { type: "switchApp", appUrl: 1 },
    { type: "switchApp", appUrl: "https://example.invalid/app.qml" },
    { type: "switchApp", appUrl: "file:///tmp/app.qml" },
    { type: "switchApp", appUrl: "hifi/tablet/ControllerSettings.qml" },
    { type: "switchApp", appUrl: "__proto__" },
    { type: "switchApp", appUrl: "constructor" }
].forEach((message) => fromQml.emit(message));
assert.strictEqual(loadedSources.length, afterSemanticBack);

screenChanged.emit("Home", "");
fromQml.emit({ type: "switchApp", appUrl: "hifi/audio/Audio.qml" });
assert.strictEqual(loadedSources.length, afterSemanticBack);

scriptEnding.emit();
assert.strictEqual(removedButtons.length, 3);
assert(!fromQml.connected());
assert(!screenChanged.connected());
buttons.forEach((button) => assert(!button.clicked.connected()));

console.log("Phone tablet app-router lifecycle mock checks passed.");
