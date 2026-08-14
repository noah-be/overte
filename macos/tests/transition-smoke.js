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
    Render.viewportResolutionScale = 1.0;
    Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples = 1;
    Scene.shouldRenderAvatars = false;

    var localScene = Script.resolvePath("fixtures/serverless-render.json");
    var stage = "initial_serverless";
    var stageDeadline = Date.now() + 180000;
    var finalRenderReadyAt = 0;
    var completed = false;
    var expectedNames = [
        "macOS smoke red cube",
        "macOS smoke cyan sphere",
        "macOS smoke label"
    ];
    var nonVisibleGeometryTypes = {
        Unknown: true,
        Empty: true,
        Sound: true,
        Script: true,
        Zone: true,
        Light: true,
        Material: true
    };

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        print("OVERTE_MACOS_TRANSITION " + (success ? "passed " : "failed ") + detail);
        Script.stop();
    }

    function sceneState() {
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        var found = {};
        var visibleGeometryCount = 0;
        expectedNames.forEach(function (name) { found[name] = false; });
        entities.forEach(function (entityID) {
            var properties = Entities.getEntityProperties(entityID, [
                "name", "type", "visible"
            ]);
            var name = properties.name;
            if (Object.prototype.hasOwnProperty.call(found, name)) {
                found[name] = true;
            }
            if (properties.visible !== false &&
                    !nonVisibleGeometryTypes[String(properties.type || "Unknown")]) {
                visibleGeometryCount += 1;
            }
        });
        return {
            entityCount: entities.length,
            fixtureComplete: expectedNames.every(function (name) { return found[name]; }),
            fixtureCount: expectedNames.filter(function (name) { return found[name]; }).length,
            visibleGeometryCount: visibleGeometryCount
        };
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!path) {
            finish(false, stage + "_snapshot_save_failed");
            return;
        }
        if (stage === "initial_snapshot") {
            print("OVERTE_MACOS_TRANSITION initial_snapshot=" + path);
            stage = "online";
            // A first public-domain model pipeline can need a little over
            // three minutes on Apple's hosted software OpenGL renderer.
            stageDeadline = Date.now() + 420000;
            AddressManager.handleLookupString("hifi://overte_hub");
        } else if (stage === "online_snapshot") {
            print("OVERTE_MACOS_TRANSITION online_snapshot=" + path);
            // The public Hub contains many shader variants.  The online image
            // above is already the rendering proof; stop queuing more Hub
            // entity frames while the connection/tree transition is handled.
            Scene.shouldRenderEntities = false;
            print("OVERTE_MACOS_TRANSITION online_rendering_paused");
            stage = "returning_serverless";
            stageDeadline = Date.now() + 180000;
            AddressManager.handleLookupString(localScene);
        } else if (stage === "final_snapshot") {
            finish(true, "serverless_online_serverless");
        }
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var state = sceneState();
        if (stage === "initial_serverless" && state.fixtureComplete) {
            print("OVERTE_MACOS_TRANSITION initial_fixture_entities=3");
            stage = "initial_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-initial.png");
        } else if (
            stage === "online" && AddressManager.isConnected &&
            state.entityCount > 0 && state.fixtureCount === 0 &&
            state.visibleGeometryCount > 0
        ) {
            print("OVERTE_MACOS_TRANSITION online_entities=" + state.entityCount +
                " visible_geometry=" + state.visibleGeometryCount);
            stage = "online_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-online.png");
        } else if (
            stage === "returning_serverless" && AddressManager.isConnected &&
            AddressManager.protocol === "file" && state.fixtureComplete
        ) {
            print("OVERTE_MACOS_TRANSITION returned_fixture_entities=3");
            Scene.shouldRenderEntities = true;
            finalRenderReadyAt = Date.now() + 1000;
            stage = "final_render";
            stageDeadline = Date.now() + 180000;
        } else if (stage === "final_render" && Date.now() >= finalRenderReadyAt) {
            stage = "final_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-final.png");
        }
        if (Date.now() >= stageDeadline) {
            finish(false, stage + "_timeout");
        }
    }, 250);
}());
