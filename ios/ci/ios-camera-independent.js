// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

// Preserve the production startup scripts while placing only the diagnostic
// camera at the authored tutorial viewpoint. This deliberately bypasses the
// avatar CharacterController so the preserved binary can distinguish a
// viewpoint/physics race from a renderer failure without another app build.
Settings.setValue(
    "iosCameraDiagnostic",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=script-start mode=independent"
);
console.warn("OVERTE_IOS_CAMERA_DIAGNOSTIC stage=script-start mode=independent");
ScriptDiscoveryService.loadOneScript("file:///~//defaultScripts.js");
Settings.setValue(
    "iosCameraDiagnostic",
    "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=defaults-launched mode=independent"
);
console.warn("OVERTE_IOS_CAMERA_DIAGNOSTIC stage=defaults-launched mode=independent");

(function () {
    "use strict";

    var targetPosition = { x: 1985.26, y: 1994.24, z: 1994.25 };
    var targetOrientation = { x: 0, y: -0.819884, z: 0, w: 0.572529 };
    var attempts = 0;
    var reported = false;
    function distanceSquared(a, b) {
        var dx = Number(a.x) - b.x;
        var dy = Number(a.y) - b.y;
        var dz = Number(a.z) - b.z;
        return dx * dx + dy * dy + dz * dz;
    }
    var timer = Script.setInterval(function () {
        Camera.mode = "independent";
        Camera.position = targetPosition;
        Camera.orientation = targetOrientation;
        attempts += 1;
        if (!reported && Camera.mode === "independent" &&
                distanceSquared(Camera.position, targetPosition) < 1) {
            var marker = "OVERTE_IOS_CAMERA_DIAGNOSTIC mode=independent" +
                " camera=viewpoint attempts=" + attempts;
            Settings.setValue("iosCameraDiagnostic", marker);
            console.warn(marker);
            reported = true;
        }
        if (attempts >= 3000) {
            Script.clearInterval(timer);
        }
    }, 100);
}());
