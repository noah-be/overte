"use strict";
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
/* globals ANDROID_PHONE_INTERFACE, PlatformInfo, Render, Script, Settings, Tablet */

(function () {
    // The touch startup selector is also used by iOS. Never apply Phone's
    // renderer policy there, or when this script is loaded on another product.
    if (typeof ANDROID_PHONE_INTERFACE === "undefined" || ANDROID_PHONE_INTERFACE !== true ||
            typeof PlatformInfo === "undefined") { return; }
    try {
        if (JSON.parse(PlatformInfo.getComputer()).OS !== "ANDROID") { return; }
    } catch (error) { return; }

    var PREFIX = "phone/graphics/";
    var SOURCE = Script.resolvePath("../settings/Settings.qml");
    var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    var currentSource = "";
    var booleanKeys = ["haze", "localLights", "proceduralMaterials", "mirrors"];
    var views = ["RenderMainView", "RenderSecondView"];
    var state = { haze: false, localLights: false, proceduralMaterials: false,
        mirrors: false, resolutionScale: 0.65 };

    function validScale(value) {
        return typeof value === "number" && isFinite(value) && value >= 0.5 && value <= 0.7;
    }

    function config(name) { return Render.getConfig(name); }

    function setLocalLights(enabled) {
        // Restore the normal grid before admitting light content. One cell can
        // overflow the renderer's uint8 light counts in a populated world.
        if (!enabled) { Render.localLightingEnabled = false; }
        views.forEach(function (view) {
            var grid = config(view + ".RenderForwardTask.LightClustering");
            if (grid) { grid.dimX = grid.dimY = grid.dimZ = enabled ? 14 : 1; }
        });
        Render.localLightingEnabled = enabled;
    }

    function setMirrors(enabled) {
        views.forEach(function (view) {
            for (var index = 0; index < 3; ++index) {
                var mirror = config(view + ".RenderMirrorView" + index + "Depth0");
                if (mirror) { mirror.enabled = enabled; }
            }
        });
    }

    function apply(key, value) {
        switch (key) {
        case "haze": Render.hazeEnabled = value; break;
        case "localLights": setLocalLights(value); break;
        case "proceduralMaterials": Render.proceduralMaterialsEnabled = value; break;
        case "mirrors": setMirrors(value); break;
        case "resolutionScale": Render.viewportResolutionScale = value; break;
        }
        state[key] = value;
    }

    function sendState() {
        if (currentSource === SOURCE) {
            tablet.sendToQml({ type: "phone.graphics.state", values: state });
        }
    }

    function fromQml(message) {
        if (currentSource !== SOURCE || !message || typeof message !== "object") { return; }
        if (message.type === "phone.graphics.ready") { sendState(); return; }
        if (message.type !== "phone.graphics.update") { return; }
        var key = message.key;
        if (typeof key !== "string" || (booleanKeys.indexOf(key) < 0 && key !== "resolutionScale")) {
            return;
        }
        var value = message.value;
        if (key === "resolutionScale" ? !validScale(value) : typeof value !== "boolean") {
            sendState(); return;
        }
        apply(key, value);
        Settings.setValue(PREFIX + key, value);
        sendState();
    }

    function screenChanged(type, source) {
        currentSource = type === "QML" ? source : "";
        sendState();
    }

    // Native startup applies the safe renderer baseline before starting scripts.
    // Restore only explicitly saved choices; leave debug A/B overrides intact
    // when a preference has never been chosen by the user.
    booleanKeys.forEach(function (key) {
        var value = Settings.getValue(PREFIX + key, null);
        if (typeof value === "boolean") { apply(key, value); }
    });
    var scale = Settings.getValue(PREFIX + "resolutionScale", null);
    if (validScale(scale)) { apply("resolutionScale", scale); }
    state.haze = Render.hazeEnabled;
    state.localLights = Render.localLightingEnabled;
    state.proceduralMaterials = Render.proceduralMaterialsEnabled;
    state.resolutionScale = Render.viewportResolutionScale;
    tablet.fromQml.connect(fromQml);
    tablet.screenChanged.connect(screenChanged);
    Script.scriptEnding.connect(function () {
        tablet.fromQml.disconnect(fromQml);
        tablet.screenChanged.disconnect(screenChanged);
    });
}());
