// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Match the supported desktop scene path. The local avatar and client
    // entity scripts are disabled by the runner before they can submit
    // unrelated skinned or overlay pipelines; domain entities remain enabled.
    Render.renderMethod = 1;
    Render.shadowsEnabled = false;
    Render.hazeEnabled = false;
    Render.bloomEnabled = false;
    Render.ambientOcclusionEnabled = false;
    Render.localLightingEnabled = false;
    Render.proceduralMaterialsEnabled = false;
    Render.antialiasingMode = 0;
    Render.viewportResolutionScale = 1.0;
    Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples = 1;
    Scene.shouldRenderAvatars = false;

    var deadline = Date.now() + 180000;
    var snapshotStage = "waiting";
    var completed = false;

    function finiteNumber(value) {
        value = Number(value);
        return isFinite(value) ? value : 0;
    }

    function plainVector(value) {
        value = value || {};
        return {
            x: finiteNumber(value.x),
            y: finiteNumber(value.y),
            z: finiteNumber(value.z)
        };
    }

    function saveEntityInventory(entities) {
        var nonRenderingTypes = {
            Unknown: true,
            Empty: true,
            Sound: true,
            Script: true
        };
        var typeCounts = {};
        var visibleRenderableCount = 0;
        var records = entities.slice(0, 64).map(function (entityID) {
            var properties = Entities.getEntityProperties(entityID, [
                "type", "visible", "position", "dimensions"
            ]);
            var type = String(properties.type || "Unknown");
            var visible = properties.visible !== false;
            typeCounts[type] = (typeCounts[type] || 0) + 1;
            if (visible && !nonRenderingTypes[type]) {
                visibleRenderableCount += 1;
            }
            return {
                id: String(entityID),
                type: type,
                visible: visible,
                position: plainVector(properties.position),
                dimensions: plainVector(properties.dimensions)
            };
        });
        Test.saveObject({
            schema_version: 1,
            entity_count: entities.length,
            captured_count: records.length,
            visible_renderable_count: visibleRenderableCount,
            type_counts: typeCounts,
            entities: records
        }, "macos-online-entities.json");
        print("OVERTE_MACOS_SMOKE online_inventory captured=" + records.length +
            " visible_renderable=" + visibleRenderableCount +
            " types=" + JSON.stringify(typeCounts));
    }

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
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        if (entities.length > 0 && snapshotStage === "waiting") {
            snapshotStage = "capturing";
            print("OVERTE_MACOS_SMOKE online_entities=" + entities.length);
            saveEntityInventory(entities);
            // One completed frame is the online rendering proof. Waiting for
            // a second capture lets unrelated late domain assets enqueue new
            // pipelines; Apple's virtualized software renderer may spend
            // minutes compiling those after the scene is already visible.
            Window.takeSnapshot(false, false, 16 / 9, "macos-online-smoke.png");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ? "entity_timeout" : "snapshot_timeout");
        }
    }, 250);
}());
