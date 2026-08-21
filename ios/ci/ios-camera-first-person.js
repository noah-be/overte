// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

// Preserve the production startup scripts that --defaultScriptsOverride would
// otherwise replace. The diagnostic changes only the camera mode.
Script.include("/~//defaultScripts.js");

(function () {
    "use strict";

    var attempts = 0;
    var reported = false;
    var timer = Script.setInterval(function () {
        Camera.mode = "first person look at";
        attempts += 1;
        if (!reported && Camera.mode === "first person look at") {
            print("OVERTE_IOS_CAMERA_DIAGNOSTIC mode=" + Camera.mode + " attempts=" + attempts);
            reported = true;
        }
        // The run has a much shorter hard deadline; this only bounds the
        // diagnostic if the app is left open manually after CI disconnects.
        if (attempts >= 3000) {
            Script.clearInterval(timer);
        }
    }, 100);
}());
