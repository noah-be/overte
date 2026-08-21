// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

// Preserve the production startup scripts that --defaultScriptsOverride would
// otherwise replace. The diagnostic changes only the camera mode.
Settings.setValue(
    "iosCameraDiagnostic",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=script-start"
);
console.warn("OVERTE_IOS_CAMERA_DIAGNOSTIC stage=script-start");
Script.include("/~//defaultScripts.js");
Settings.setValue(
    "iosCameraDiagnostic",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=defaults-loaded"
);
console.warn("OVERTE_IOS_CAMERA_DIAGNOSTIC stage=defaults-loaded");

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
