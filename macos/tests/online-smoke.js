// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Match the supported desktop scene path. The local avatar is disabled by
    // the runner before it can submit its expensive skinned pipelines.
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

    var deadline = Date.now() + 180000;
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
                    Window.takeSnapshot(false, false, 16 / 9, "macos-online-smoke.png");
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
        if (entities.length > 0 && snapshotStage === "waiting") {
            snapshotStage = "warmup";
            print("OVERTE_MACOS_SMOKE online_entities=" + entities.length);
            Window.takeSnapshot(false, false, 16 / 9, "macos-online-warmup.png");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ? "entity_timeout" : "snapshot_timeout");
        }
    }, 250);
}());
