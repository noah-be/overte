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
    Scene.shouldRenderEntities = true;

    var localScene = Script.resolvePath("fixtures/serverless-render.json");
    var stage = "initial_serverless";
    var stageDeadline = Date.now() + 180000;
    var finalRenderReadyAt = 0;
    var onlineSnapshotSettleDeadline = 0;
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

    function returnToServerless(snapshotDetail) {
        print("OVERTE_MACOS_TRANSITION online_snapshot=" + snapshotDetail);
        // The public Hub contains many script-bearing entities. The PNG can
        // be complete while its Qt completion signal waits behind script
        // setup on Apple's software runner. Stop queuing Hub entity frames;
        // the shell remains authoritative and decodes the written PNG.
        Scene.shouldRenderEntities = false;
        print("OVERTE_MACOS_TRANSITION online_rendering_paused");
        stage = "returning_serverless";
        stageDeadline = Date.now() + 180000;
        AddressManager.handleLookupString(localScene);
    }

    function resetFixtureView() {
        // The Hub changes the avatar/camera pose. The local fixture is fixed
        // around (0, 1.6, -4), so both serverless captures must restore the
        // same first-person pose before proving its colored geometry.
        MyAvatar.position = { x: 0, y: 1.6, z: 0 };
        MyAvatar.orientation = Quat.IDENTITY;
        Camera.mode = "first person";
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!path) {
            finish(false, stage + "_snapshot_save_failed");
            return;
        }
        if (stage === "initial_warmup_snapshot") {
            print("OVERTE_MACOS_TRANSITION initial_warmup_snapshot=" + path);
            stage = "initial_render";
            finalRenderReadyAt = Date.now() + 5000;
        } else if (stage === "initial_snapshot") {
            print("OVERTE_MACOS_TRANSITION initial_snapshot=" + path);
            stage = "online";
            // A first public-domain model pipeline can need a little over
            // three minutes on Apple's hosted software OpenGL renderer.
            stageDeadline = Date.now() + 420000;
            AddressManager.handleLookupString("hifi://overte_hub");
        } else if (stage === "online_snapshot") {
            returnToServerless(path);
        } else if (stage === "final_warmup_snapshot") {
            print("OVERTE_MACOS_TRANSITION final_warmup_snapshot=" + path);
            stage = "final_render";
            finalRenderReadyAt = Date.now() + 5000;
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
            resetFixtureView();
            stage = "initial_warmup_snapshot";
            Window.takeSnapshot(false, false, 16 / 9,
                "macos-transition-initial-warmup.png");
        } else if (stage === "initial_render" && Date.now() >= finalRenderReadyAt) {
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
            onlineSnapshotSettleDeadline = Date.now() + 150000;
        } else if (stage === "online_snapshot" &&
                onlineSnapshotSettleDeadline !== 0 &&
                Date.now() >= onlineSnapshotSettleDeadline) {
            print("OVERTE_MACOS_TRANSITION online_snapshot_callback_deferred");
            returnToServerless("settle_elapsed");
        } else if (
            stage === "returning_serverless" && AddressManager.isConnected &&
            AddressManager.protocol === "file" && state.fixtureComplete
        ) {
            print("OVERTE_MACOS_TRANSITION returned_fixture_entities=3");
            Scene.shouldRenderEntities = true;
            resetFixtureView();
            stage = "final_warmup_snapshot";
            stageDeadline = Date.now() + 180000;
            Window.takeSnapshot(false, false, 16 / 9,
                "macos-transition-final-warmup.png");
        } else if (stage === "final_render" && Date.now() >= finalRenderReadyAt) {
            stage = "final_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-final.png");
        }
        if (Date.now() >= stageDeadline) {
            finish(false, stage + "_timeout");
        }
    }, 250);
}());
