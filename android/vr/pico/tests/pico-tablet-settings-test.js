// Device-free behavior tests for Pico tablet setting sanitization.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const repository = path.resolve(__dirname, "../../../..");
const sanitize = require(path.resolve(__dirname,
    "../../../../scripts/system/libraries/picoTabletSettings.js"));

function production(relativePath) {
    return fs.readFileSync(path.join(repository, relativePath), "utf8");
}

assert.deepStrictEqual(sanitize(1.25, -0.52, -18),
    { forward: 1.25, up: -0.52, tilt: -18 });
assert.deepStrictEqual(sanitize("1.5", "-0.5", "10"),
    { forward: 1.5, up: -0.5, tilt: 10 });
assert.deepStrictEqual(sanitize(NaN, Infinity, -Infinity),
    { forward: 1.25, up: -0.52, tilt: -18 });
assert.deepStrictEqual(sanitize(-100, 100, 100),
    { forward: 0.4, up: 0.3, tilt: 30 });
assert.deepStrictEqual(sanitize(100, -100, -100),
    { forward: 2.0, up: -1.3, tilt: -45 });

const settings = production("scripts/system/settings/Settings.qml");
const baseConfiguration = production(
    "scripts/system/settings/qml/SettingsTouchConfiguration.qml");
const phoneProfile = production(
    "interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml");
const picoConfiguration = production(
    "scripts/system/settings/qml/+android_picoInterface/SettingsTouchConfiguration.qml");
const picoSettingNumber = production(
    "scripts/system/settings/qml/+android_picoInterface/SettingNumber.qml");
const picoGeneralPreferencesPolicy = production(
    "interface/resources/qml/hifi/tablet/+android_picoInterface/TabletGeneralPreferencesPolicy.qml");
const questConfiguration = production(
    "scripts/system/settings/qml/+android_questInterface/SettingsTouchConfiguration.qml");
const fileUtils = production("libraries/shared/src/shared/FileUtils.cpp");

assert.match(baseConfiguration, /showPicoInteractionSettings:\s*false/);
assert.match(phoneProfile, /picoResolutionSettingsAvailable:\s*false/);
assert.doesNotMatch(phoneProfile, /showPicoInteractionSettings/);
assert.match(questConfiguration, /showPicoInteractionSettings:\s*false/);
assert.match(picoConfiguration, /showPicoInteractionSettings:\s*true/);
assert.match(picoConfiguration, /HifiControls\.TouchUiMetrics\s*\{/);
assert.match(picoSettingNumber,
    /^import QtQuick 2\.15\nimport QtQuick\.Controls 2\.15\n/);
assert.match(picoSettingNumber, /RegularExpressionValidator/);
assert.match(picoGeneralPreferencesPolicy,
    /"VR Movement":\s*"settings\.hmd-preferences"/);
assert.match(picoGeneralPreferencesPolicy,
    /import "\.\.\/\.\.\/controlsUit" as HifiControls/);
assert.ok(
    picoGeneralPreferencesPolicy.indexOf('categories.push("VR Movement")') <
        picoGeneralPreferencesPolicy.indexOf('categories.push("User Interface")'),
    "Pico's contract-bearing VR section must be in the initial tablet viewport");
assert.doesNotMatch(picoGeneralPreferencesPolicy,
    /"HMD":\s*"settings\.hmd-preferences"/);
assert.match(fileUtils, /extraSelectors << "android_" HIFI_ANDROID_APP/);
assert.match(settings, /requiresPicoInteractionSettings:\s*true/);
assert.match(settings, /active:\s*touchConfiguration\.showPicoInteractionSettings/);
assert.doesNotMatch(settings, /deferTabletCreationUntilOpen/);

const graphicsSettings = production("scripts/system/settings/qml/pages/GraphicsSettings.qml");
assert.ok(
    graphicsSettings.indexOf('objectName: "settings.vr-render-resolution"') <
        graphicsSettings.indexOf("// Graphics Presets"),
    "Pico's VR resolution control must be in the initial graphics viewport");

process.stdout.write("PASS Pico tablet settings and immutable capability selection\n");
