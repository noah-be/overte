// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    Render.renderMethod = 1;
    Render.shadowsEnabled = false;
    Render.hazeEnabled = false;
    Render.bloomEnabled = false;
    Render.ambientOcclusionEnabled = false;
    Render.localLightingEnabled = false;
    Render.proceduralMaterialsEnabled = false;
    Render.antialiasingMode = 0;
    Render.viewportResolutionScale = 0.5;

    var deadline = Date.now() + 600000;
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
        if (entities.length > 0 && !snapshotRequested) {
            snapshotRequested = true;
            print("OVERTE_MACOS_SMOKE online_entities=" + entities.length);
            Window.takeSnapshot(false, false, 16 / 9, "macos-online-smoke.png");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotRequested ? "snapshot_timeout" : "entity_timeout");
        }
    }, 250);
}());
