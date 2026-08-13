// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Keep the visual gate deterministic and tractable on GitHub's Intel
    // runner, which exposes Apple's software OpenGL renderer.
    Render.renderMethod = 1;
    Render.shadowsEnabled = false;
    Render.hazeEnabled = false;
    Render.bloomEnabled = false;
    Render.ambientOcclusionEnabled = false;
    Render.localLightingEnabled = false;
    Render.proceduralMaterialsEnabled = false;
    Render.antialiasingMode = 0;
    Render.viewportResolutionScale = 0.5;
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
    var snapshotRequested = false;
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
        finish(Boolean(path), "snapshot=" + path);
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        entities.forEach(function (entityID) {
            var name = Entities.getEntityProperties(entityID, ["name"]).name;
            if (Object.prototype.hasOwnProperty.call(expectedNames, name)) {
                expectedNames[name] = true;
            }
        });
        var fixtureComplete = Object.keys(expectedNames).every(function (name) {
            return expectedNames[name];
        });
        if (fixtureComplete && !snapshotRequested) {
            snapshotRequested = true;
            print("OVERTE_MACOS_SMOKE fixture_entities=3");
            Window.takeSnapshot(false, false, 16 / 9, "macos-serverless-smoke.png");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotRequested ? "snapshot_timeout" : "entity_timeout");
        }
    }, 250);
}());
