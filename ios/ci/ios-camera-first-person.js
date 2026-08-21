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

    var targetPosition = { x: 1985.26, y: 1994.24, z: 1994.25 };
    var targetOrientation = { x: 0, y: -0.819884, z: 0, w: 0.572529 };
    var attempts = 0;
    var reported = false;
    var observedTarget = false;
    var resetReported = false;
    var timer = Script.setInterval(function () {
        var before = MyAvatar.position;
        var beforeError = Vec3.distance(before, targetPosition);
        if (beforeError < 1) {
            observedTarget = true;
        } else if (observedTarget && !resetReported) {
            console.warn(
                "OVERTE_IOS_CAMERA_DIAGNOSTIC stage=avatar-reset" +
                " x=" + before.x + " y=" + before.y + " z=" + before.z
            );
            resetReported = true;
        }

        // The authored root viewpoint is applied briefly and then overwritten
        // by a later iOS startup/physics update.  Keep this A/B probe at that
        // exact tutorial viewpoint so the preserved binary can prove whether
        // the origin reset alone hides otherwise healthy world rendering.
        MyAvatar.position = targetPosition;
        MyAvatar.orientation = targetOrientation;
        Camera.mode = "first person look at";
        attempts += 1;
        var positionError = Vec3.distance(MyAvatar.position, targetPosition);
        if (!reported && Camera.mode === "first person look at" && positionError < 1) {
            var marker = "OVERTE_IOS_CAMERA_DIAGNOSTIC mode=" + Camera.mode +
                " avatar=viewpoint attempts=" + attempts;
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
