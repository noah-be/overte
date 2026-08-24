// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Observe the bundled tutorial exactly as a normal first launch does.  The
    // test never changes the camera, avatar, scene, lighting, or renderer.
    // The bundled world exercises substantially more production shader
    // variants than the deterministic fixture. Hosted x86_64 software OpenGL
    // was still completing draws with every expected entity/model loaded at
    // the former thirty-minute deadline (run 32682143125). Run 32688580808
    // then measured consecutive active draws of 11, 9, and 6 minutes after
    // all content loaded. Keep a finite total budget while independently
    // failing a genuinely motionless load sooner.
    var deadline = Date.now() + 3300000;
    var nextProgressAt = Date.now();
    var readyAt = 0;
    var readyPresentBaseline = 0;
    var snapshotStage = "waiting";
    var snapshotPendingAt = 0;
    var snapshotPendingReported = false;
    var lastProgressAt = Date.now();
    var bestEntityCount = 0;
    var bestLoadedModelCount = 0;
    var bestOutstandingWork = Number.MAX_VALUE;
    var bestPresentCount = 0;
    var completed = false;
    var expectedEntityCount = 40;
    var expectedModelNames = [
        "Seagull",
        "LOGO",
        "Bowl",
        "Dome Glass",
        "trees",
        "Dome",
        "Temple",
        "Planters",
        "STAND-ANGLE_CONTROLS",
        "STAND-ANGLE_TABLET-TOOLBAR",
        "STAND-ANGLE_APPLICATIONS",
        "STAND-ANGLE_AVATAR",
        "STAND-ANGLE_CONFIG-WIZARD",
        "AVATAR_VIEWER_PLATFORM",
        "QUICK TEST AREA",
        "TELEPORTER"
    ];
    var expectedLandmarkNames = [
        "MainDomeZone",
        "IN-WORLD PORTAL",
        "QUICK SETUP",
        "Avatar_Viewer_Sign"
    ];

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

    function queueState() {
        Stats.forceUpdateStats();
        return {
            downloads: finiteNumber(Stats.downloads),
            downloads_pending: finiteNumber(Stats.downloadsPending),
            processing: finiteNumber(Stats.processing),
            processing_pending: finiteNumber(Stats.processingPending),
            texture_pending_mb: finiteNumber(Stats.texturePendingTransfers)
        };
    }

    function resourceQueuesEmpty(resources) {
        return resources.downloads === 0 &&
            resources.downloads_pending === 0 &&
            resources.processing === 0 &&
            resources.processing_pending === 0 &&
            resources.texture_pending_mb === 0;
    }

    function resourcesIdle(resources) {
        return resourceQueuesEmpty(resources) && Test.isTextureLoadingComplete();
    }

    function inspectTutorial(entities) {
        var expectedModels = {};
        var expectedLandmarks = {};
        var typeCounts = {};
        var visibleModelCount = 0;
        var loadedVisibleModelCount = 0;
        expectedModelNames.forEach(function (name) {
            expectedModels[name] = { found: false, loaded: false };
        });
        expectedLandmarkNames.forEach(function (name) {
            expectedLandmarks[name] = false;
        });
        var records = entities.map(function (entityID) {
            var properties = Entities.getEntityProperties(entityID, [
                "name", "type", "visible", "position", "dimensions"
            ]);
            var name = String(properties.name || "");
            var type = String(properties.type || "Unknown");
            var visible = properties.visible !== false;
            var loaded = visible && type === "Model" && Entities.isLoaded(entityID);
            typeCounts[type] = (typeCounts[type] || 0) + 1;
            if (visible && type === "Model") {
                visibleModelCount += 1;
                if (loaded) {
                    loadedVisibleModelCount += 1;
                }
            }
            if (Object.prototype.hasOwnProperty.call(expectedModels, name)) {
                expectedModels[name].found = true;
                expectedModels[name].loaded = expectedModels[name].loaded || loaded;
            }
            if (Object.prototype.hasOwnProperty.call(expectedLandmarks, name)) {
                expectedLandmarks[name] = true;
            }
            return {
                id: String(entityID),
                name: name,
                type: type,
                visible: visible,
                loaded: loaded,
                position: plainVector(properties.position),
                dimensions: plainVector(properties.dimensions)
            };
        });
        var foundExpectedModels = expectedModelNames.filter(function (name) {
            return expectedModels[name].found;
        }).length;
        var loadedExpectedModels = expectedModelNames.filter(function (name) {
            return expectedModels[name].loaded;
        }).length;
        var foundLandmarks = expectedLandmarkNames.filter(function (name) {
            return expectedLandmarks[name];
        }).length;
        return {
            schema_version: 1,
            entity_count: entities.length,
            expected_entity_count: expectedEntityCount,
            expected_model_count: expectedModelNames.length,
            found_expected_model_count: foundExpectedModels,
            loaded_expected_model_count: loadedExpectedModels,
            expected_landmark_count: expectedLandmarkNames.length,
            found_expected_landmark_count: foundLandmarks,
            visible_model_count: visibleModelCount,
            loaded_visible_model_count: loadedVisibleModelCount,
            type_counts: typeCounts,
            expected_models: expectedModels,
            expected_landmarks: expectedLandmarks,
            entities: records
        };
    }

    function tutorialContentLoaded(inventory, resources) {
        return Test.isServerlessSceneImportComplete() &&
            inventory.entity_count >= expectedEntityCount &&
            inventory.found_expected_model_count === expectedModelNames.length &&
            inventory.loaded_expected_model_count === expectedModelNames.length &&
            inventory.found_expected_landmark_count === expectedLandmarkNames.length &&
            resourceQueuesEmpty(resources);
    }

    function tutorialReady(inventory, resources) {
        return tutorialContentLoaded(inventory, resources) && resourcesIdle(resources);
    }

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        print("OVERTE_MACOS_TUTORIAL " + (success ? "passed " : "failed ") + detail);
        if (success) {
            Test.saveObject({
                schema_version: 1,
                ready_for_external_validation: true,
                script_success: true
            }, "macos-tutorial-smoke-completion.json");
        }
        Script.stop();
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!path) {
            finish(false, "snapshot_save_failed");
            return;
        }
        if (snapshotStage === "capturing") {
            print("OVERTE_MACOS_TUTORIAL snapshot_complete=" + path);
            finish(true, "snapshot=" + path);
        }
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        var inventory = inspectTutorial(entities);
        var resources = queueState();
        var ready = tutorialReady(inventory, resources);
        var presentCount = finiteNumber(Test.getPresentCount());
        var outstandingWork = resources.downloads + resources.downloads_pending +
            resources.processing + resources.processing_pending +
            resources.texture_pending_mb;

        if (inventory.entity_count > bestEntityCount ||
                inventory.loaded_expected_model_count > bestLoadedModelCount ||
                outstandingWork < bestOutstandingWork ||
                presentCount > bestPresentCount) {
            lastProgressAt = Date.now();
            bestEntityCount = Math.max(bestEntityCount, inventory.entity_count);
            bestLoadedModelCount = Math.max(bestLoadedModelCount,
                inventory.loaded_expected_model_count);
            bestOutstandingWork = Math.min(bestOutstandingWork, outstandingWork);
            bestPresentCount = Math.max(bestPresentCount, presentCount);
        }

        if (Date.now() >= nextProgressAt) {
            print("OVERTE_MACOS_TUTORIAL progress entities=" + inventory.entity_count +
                " expected_models=" + inventory.found_expected_model_count +
                " loaded_expected_models=" + inventory.loaded_expected_model_count +
                " landmarks=" + inventory.found_expected_landmark_count +
                " presents=" + presentCount +
                " queues=" + JSON.stringify(resources));
            nextProgressAt = Date.now() + 30000;
        }

        if (snapshotStage === "waiting" && ready && readyAt === 0) {
            readyAt = Date.now() + 5000;
            readyPresentBaseline = presentCount;
            print("OVERTE_MACOS_TUTORIAL full_scene_ready entities=" +
                inventory.entity_count + " loaded_models=" +
                inventory.loaded_expected_model_count);
        } else if (snapshotStage === "waiting" && !ready) {
            readyAt = 0;
        }

        if (snapshotStage === "waiting" && ready && readyAt !== 0 &&
                Date.now() >= readyAt &&
                presentCount > readyPresentBaseline) {
            inventory.resource_queues = resources;
            inventory.present_count = presentCount;
            Test.saveObject(inventory, "macos-tutorial-entities.json");
            snapshotStage = "capturing";
            snapshotPendingAt = Date.now() + 300000;
            print("OVERTE_MACOS_TUTORIAL capture entities=" + inventory.entity_count +
                " presents=" + inventory.present_count);
            Window.takeSnapshot(false, false, 16 / 9, "macos-tutorial-smoke.png");
        }

        if (snapshotStage === "capturing" && !snapshotPendingReported &&
                Date.now() >= snapshotPendingAt) {
            snapshotPendingReported = true;
            print("OVERTE_MACOS_TUTORIAL snapshot_still_pending");
        }
        // A software-rendered first frame consists of multiple sequential GL
        // draws. Run 32688580808 showed that all 40 entities, all 16 expected
        // models, all landmarks, and every raw queue were ready while those
        // draws kept 160-200% process CPU busy for more than 25 minutes. Once
        // that observable content-loaded state is reached, allow at most 45
        // minutes since real progress; incomplete content retains the faster
        // 20-minute stall bound. Readiness and capture criteria are unchanged.
        var firstFrameRenderPending = snapshotStage === "waiting" &&
            tutorialContentLoaded(inventory, resources);
        var progressStallLimit = firstFrameRenderPending ? 2700000 : 1200000;
        if (snapshotStage === "waiting" &&
                Date.now() - lastProgressAt >= progressStallLimit) {
            if (firstFrameRenderPending) {
                finish(false, "tutorial_first_frame_stalled");
            } else {
                finish(false, "tutorial_progress_stalled");
            }
            return;
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ?
                "tutorial_timeout" : "snapshot_timeout");
        }
    }, 250);
}());
