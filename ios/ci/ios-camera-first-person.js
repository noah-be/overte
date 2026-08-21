// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

// Preserve the production startup scripts that --defaultScriptsOverride would
// otherwise replace. The diagnostic changes only the camera mode.
Settings.setValue(
    "iosCameraDiagnostic",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=script-start"
);
console.warn("OVERTE_IOS_CAMERA_DIAGNOSTIC stage=script-start");
// The iOS V8 Script object does not expose include() or load().  Interface
// explicitly registers ScriptDiscoveryService as a global object, and its
// single-argument loadOneScript() entry point starts the production defaults in
// their normal independent script engine without stopping this camera probe.
ScriptDiscoveryService.loadOneScript("file:///~//defaultScripts.js");
Settings.setValue(
    "iosCameraDiagnostic",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=defaults-launched"
);
console.warn("OVERTE_IOS_CAMERA_DIAGNOSTIC stage=defaults-launched");

(function () {
    "use strict";

    var attempts = 0;
    var reported = false;
    var timer = Script.setInterval(function () {
        Camera.mode = "first person look at";
        attempts += 1;
        if (!reported && Camera.mode === "first person look at") {
            var marker = "OVERTE_IOS_CAMERA_DIAGNOSTIC mode=" + Camera.mode + " attempts=" + attempts;
            Settings.setValue("iosCameraDiagnostic", marker);
            console.warn(marker);
            reported = true;
        }
        // The run has a much shorter hard deadline; this only bounds the
        // diagnostic if the app is left open manually after CI disconnects.
        if (attempts >= 3000) {
            Script.clearInterval(timer);
        }
    }, 100);
}());
