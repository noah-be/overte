// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Keep the visual gate deterministic and tractable on GitHub's Intel
    // runner, which exposes Apple's software OpenGL renderer.
    // The local avatar is suppressed before scene submission. Keep the normal
    // desktop forward path at native resolution so this smoke also covers the
    // final color/resampling path without a test-only downscale.
    Render.renderMethod = 1;
    Render.shadowsEnabled = false;
    Render.hazeEnabled = false;
    Render.bloomEnabled = false;
    Render.ambientOcclusionEnabled = false;
    Render.localLightingEnabled = false;
    Render.proceduralMaterialsEnabled = false;
    Render.antialiasingMode = 0;
    Render.viewportResolutionScale = 1.0;
    Scene.shouldRenderAvatars = false;

    // The GitHub Intel runner exposes Apple's software OpenGL renderer.  Its
    // first scene frame can spend several minutes compiling the complete
    // shader set before the queued snapshot reaches the present thread.
    var deadline = Date.now() + 180000;
    var expectedNames = {
        "macOS smoke red cube": false,
        "macOS smoke cyan sphere": false,
        "macOS smoke label": false
    };
    var snapshotStage = "waiting";
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
        if (snapshotStage === "warmup") {
            snapshotStage = "cooldown";
            print("OVERTE_MACOS_SMOKE warmup_snapshot=" + path);
            Script.setTimeout(function () {
                if (!completed) {
                    snapshotStage = "final";
                    Window.takeSnapshot(false, false, 16 / 9, "macos-serverless-smoke.png");
                }
            }, 5000);
        } else if (snapshotStage === "final") {
            finish(true, "snapshot=" + path);
        }
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        entities.forEach(function (entityID) {
            var properties = Entities.getEntityProperties(entityID, ["name", "color", "textColor"]);
            var name = properties.name;
            if (Object.prototype.hasOwnProperty.call(expectedNames, name)) {
                if (!expectedNames[name]) {
                    print("OVERTE_MACOS_SMOKE fixture_color=" + name + " " +
                        JSON.stringify(properties.color || properties.textColor));
                }
                expectedNames[name] = true;
            }
        });
        var fixtureComplete = Object.keys(expectedNames).every(function (name) {
            return expectedNames[name];
        });
        if (fixtureComplete && snapshotStage === "waiting") {
            snapshotStage = "warmup";
            print("OVERTE_MACOS_SMOKE fixture_entities=3");
            Window.takeSnapshot(false, false, 16 / 9, "macos-serverless-warmup.png");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ? "entity_timeout" : "snapshot_timeout");
        }
    }, 250);
}());
