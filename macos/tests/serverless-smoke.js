// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Observe the production render path. The test supplies only a known URL;
    // it does not change the camera, avatar, scene visibility, or renderer.
    var deadline = Date.now() + 340000;
    var loggedNames = {
        "macOS smoke red cube": false,
        "macOS smoke cyan sphere": false,
        "macOS smoke label": false
    };
    var snapshotStage = "waiting";
    var cooldownStartedAt = 0;
    var cooldownPresentCount = 0;
    var completed = false;

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        print("OVERTE_MACOS_SMOKE " + (success ? "passed " : "failed ") + detail);
        Script.stop();
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!path) {
            finish(false, "snapshot_save_failed");
            return;
        }
        if (snapshotStage === "capturing") {
            finish(true, "snapshot=" + path);
        }
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var currentNames = {
            "macOS smoke red cube": false,
            "macOS smoke cyan sphere": false,
            "macOS smoke label": false
        };
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        entities.forEach(function (entityID) {
            var properties = Entities.getEntityProperties(entityID, ["name", "color", "textColor"]);
            var name = properties.name;
            if (Object.prototype.hasOwnProperty.call(currentNames, name)) {
                if (!loggedNames[name]) {
                    print("OVERTE_MACOS_SMOKE fixture_color=" + name + " " +
                        JSON.stringify(properties.color || properties.textColor));
                    loggedNames[name] = true;
                }
                currentNames[name] = true;
            }
        });
        var fixtureComplete = Object.keys(currentNames).every(function (name) {
            return currentNames[name];
        });
        var importComplete = Test.isServerlessSceneImportComplete();
        if (fixtureComplete && importComplete && snapshotStage === "waiting") {
            snapshotStage = "cooldown";
            cooldownStartedAt = Date.now();
            cooldownPresentCount = Test.getPresentCount();
            print("OVERTE_MACOS_SMOKE fixture_entities=3");
        } else if (snapshotStage === "cooldown" && (!fixtureComplete || !importComplete)) {
            snapshotStage = "waiting";
            cooldownStartedAt = 0;
            print("OVERTE_MACOS_SMOKE fixture_reset_during_cooldown");
        } else if (snapshotStage === "cooldown" && importComplete &&
                Date.now() - cooldownStartedAt >= 5000 &&
                Test.getPresentCount() >= cooldownPresentCount + 2) {
            snapshotStage = "capturing";
            print("OVERTE_MACOS_SMOKE cooldown_complete presents=" +
                (Test.getPresentCount() - cooldownPresentCount));
            Window.takeSnapshot(false, false, 16 / 9, "macos-serverless-smoke.png");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ? "entity_timeout" : "snapshot_timeout");
        }
    }, 250);
}());
