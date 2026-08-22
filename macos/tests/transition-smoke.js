// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Navigation is the input under test. Camera, avatar, scene visibility,
    // scripts, and renderer preferences remain on the production path.
    var localScene = Script.resolvePath("fixtures/serverless-render.json");
    var stage = "initial_serverless";
    var stageDeadline = Date.now() + 180000;
    var readyAt = 0;
    var presentBaseline = 0;
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
        var visibleModelCount = 0;
        var loadedVisibleModelCount = 0;
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
            if (properties.visible !== false && properties.type === "Model") {
                visibleModelCount += 1;
                if (Entities.isLoaded(entityID)) {
                    loadedVisibleModelCount += 1;
                }
            }
        });
        return {
            entityCount: entities.length,
            fixtureComplete: expectedNames.every(function (name) { return found[name]; }),
            fixtureCount: expectedNames.filter(function (name) { return found[name]; }).length,
            visibleGeometryCount: visibleGeometryCount,
            visibleModelCount: visibleModelCount,
            loadedVisibleModelCount: loadedVisibleModelCount
        };
    }

    function resourcesIdle() {
        Stats.forceUpdateStats();
        return Number(Stats.downloads) === 0 &&
            Number(Stats.downloadsPending) === 0 &&
            Number(Stats.processing) === 0 &&
            Number(Stats.processingPending) === 0 &&
            Number(Stats.texturePendingTransfers) === 0 &&
            Test.isTextureLoadingComplete();
    }

    function beginStableInterval(nextStage, timeout) {
        stage = nextStage;
        readyAt = Date.now() + 5000;
        presentBaseline = Number(Test.getPresentCount());
        stageDeadline = Date.now() + timeout;
    }

    function stableFrameReady() {
        return Date.now() >= readyAt &&
            Number(Test.getPresentCount()) > presentBaseline;
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!path) {
            finish(false, stage + "_snapshot_save_failed");
            return;
        }
        if (stage === "initial_snapshot") {
            print("OVERTE_MACOS_TRANSITION initial_snapshot=" + path);
            stage = "online";
            stageDeadline = Date.now() + 420000;
            readyAt = 0;
            AddressManager.handleLookupString("hifi://overte_hub");
        } else if (stage === "online_snapshot") {
            print("OVERTE_MACOS_TRANSITION online_snapshot=" + path);
            stage = "returning_serverless";
            stageDeadline = Date.now() + 180000;
            readyAt = 0;
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
        var importComplete = Test.isServerlessSceneImportComplete();
        if (stage === "initial_serverless" && state.fixtureComplete && importComplete) {
            print("OVERTE_MACOS_TRANSITION initial_fixture_entities=3");
            beginStableInterval("initial_settle", 180000);
        } else if (stage === "initial_settle" && (!state.fixtureComplete || !importComplete)) {
            stage = "initial_serverless";
        } else if (stage === "initial_settle" && stableFrameReady()) {
            stage = "initial_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-initial.png");
        } else if (
            stage === "online" && AddressManager.isConnected &&
            state.entityCount > 0 && state.fixtureCount === 0 &&
            state.loadedVisibleModelCount > 0 && resourcesIdle()
        ) {
            print("OVERTE_MACOS_TRANSITION online_entities=" + state.entityCount +
                " visible_geometry=" + state.visibleGeometryCount +
                " loaded_models=" + state.loadedVisibleModelCount);
            beginStableInterval("online_settle", 420000);
        } else if (stage === "online_settle" &&
                (!AddressManager.isConnected || state.fixtureCount !== 0 ||
                 state.loadedVisibleModelCount === 0 || !resourcesIdle())) {
            stage = "online";
            readyAt = 0;
        } else if (stage === "online_settle" && stableFrameReady()) {
            stage = "online_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-online.png");
        } else if (
            stage === "returning_serverless" && AddressManager.isConnected &&
            AddressManager.protocol === "file" && state.fixtureComplete && importComplete
        ) {
            print("OVERTE_MACOS_TRANSITION returned_fixture_entities=3");
            beginStableInterval("final_settle", 180000);
        } else if (stage === "final_settle" &&
                (!state.fixtureComplete || !importComplete)) {
            stage = "returning_serverless";
            readyAt = 0;
        } else if (stage === "final_settle" && stableFrameReady()) {
            stage = "final_snapshot";
            Window.takeSnapshot(false, false, 16 / 9, "macos-transition-final.png");
        }
        if (Date.now() >= stageDeadline) {
            finish(false, stage + "_timeout");
        }
    }, 250);
}());
