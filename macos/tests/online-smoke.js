// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // This script is deliberately observational. It must not change the
    // camera, scene contents, avatar visibility, or rendering preferences.
    // The captured image is evidence of the production Hub path, not a scene
    // assembled for the test.
    // Leave room for bounded directory retries followed by full Hub asset
    // loading and production draws on Apple's hosted software renderer.
    var deadline = Date.now() + 1800000;
    var nextProgressAt = Date.now();
    var snapshotStage = "waiting";
    var snapshotSettleDeadline = 0;
    var snapshotPendingReported = false;
    var fullSceneReadyAt = 0;
    var readyPresentBaseline = 0;
    var snapshotPath = "";
    var latestInventory = null;
    var connectionDeadline = Date.now() + 600000;
    var noEntityDeadline = 0;
    var lastAssetProgressAt = 0;
    var bestLoadedModelCount = 0;
    var bestOutstandingWork = Number.MAX_VALUE;
    var bestPresentCount = 0;
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

    function inspectEntityInventory(entities, captureLimit) {
        var nonVisibleGeometryTypes = {
            Unknown: true,
            Empty: true,
            Sound: true,
            Script: true,
            Zone: true,
            Light: true,
            Material: true
        };
        var typeCounts = {};
        var visibleRenderableCount = 0;
        var visiblePrimitiveCount = 0;
        var visibleModelCount = 0;
        var loadedVisibleModelCount = 0;
        var primitiveTypes = { Box: true, Sphere: true, Shape: true };
        var records = entities.slice(0, captureLimit).map(function (entityID) {
            var properties = Entities.getEntityProperties(entityID, [
                "type", "visible", "position", "dimensions"
            ]);
            var type = String(properties.type || "Unknown");
            var visible = properties.visible !== false;
            var loaded = visible && type === "Model" && Entities.isLoaded(entityID);
            typeCounts[type] = (typeCounts[type] || 0) + 1;
            if (visible && !nonVisibleGeometryTypes[type]) {
                visibleRenderableCount += 1;
            }
            if (visible && primitiveTypes[type]) {
                visiblePrimitiveCount += 1;
            }
            if (visible && type === "Model") {
                visibleModelCount += 1;
                if (loaded) {
                    loadedVisibleModelCount += 1;
                }
            }
            return {
                id: String(entityID),
                type: type,
                visible: visible,
                loaded: loaded,
                position: plainVector(properties.position),
                dimensions: plainVector(properties.dimensions)
            };
        });
        return {
            schema_version: 1,
            entity_count: entities.length,
            captured_count: records.length,
            visible_renderable_count: visibleRenderableCount,
            visible_primitive_count: visiblePrimitiveCount,
            visible_model_count: visibleModelCount,
            loaded_visible_model_count: loadedVisibleModelCount,
            type_counts: typeCounts,
            entities: records
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

    function resourcesIdle(resources) {
        return resources.downloads === 0 &&
            resources.downloads_pending === 0 &&
            resources.processing === 0 &&
            resources.processing_pending === 0 &&
            resources.texture_pending_mb === 0 &&
            Test.isTextureLoadingComplete();
    }

    function saveEntityInventory(inventory) {
        Test.saveObject(inventory, "macos-online-entities.json");
        print("OVERTE_MACOS_SMOKE online_inventory captured=" + inventory.captured_count +
            " visible_renderable=" + inventory.visible_renderable_count +
            " visible_primitive=" + inventory.visible_primitive_count +
            " types=" + JSON.stringify(inventory.type_counts));
    }

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        print("OVERTE_MACOS_SMOKE " + (success ? "passed " : "failed ") + detail);
        // Persist success only after the snapshot callback proves that the PNG
        // was written. Failure remains available to the external supervisor
        // for a correlated macOS process sample.
        if (success) {
            Test.saveObject({
                schema_version: 1,
                ready_for_external_validation: true,
                script_success: true
            }, "macos-online-smoke-completion.json");
        }
        Script.stop();
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!path) {
            finish(false, "snapshot_save_failed");
            return;
        }
        if (snapshotStage === "capturing") {
            snapshotPath = path;
            print("OVERTE_MACOS_SMOKE snapshot_complete=" + path);
            finish(true, "snapshot=" + snapshotPath);
        }
    });

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        latestInventory = inspectEntityInventory(entities, 64);
        var resources = queueState();
        var presentCount = finiteNumber(Test.getPresentCount());
        var resourcesAreIdle = resourcesIdle(resources);
        var productionSceneReady = latestInventory.loaded_visible_model_count > 0 &&
            resourcesAreIdle;
        var outstandingWork = resources.downloads + resources.downloads_pending +
            resources.processing + resources.processing_pending + resources.texture_pending_mb;
        var hubConnected = AddressManager.isConnected &&
            AddressManager.protocol === "hifi";

        if (hubConnected && noEntityDeadline === 0) {
            noEntityDeadline = Date.now() + 600000;
        }

        if (latestInventory.entity_count > 0) {
            if (lastAssetProgressAt === 0 ||
                    latestInventory.loaded_visible_model_count > bestLoadedModelCount ||
                    outstandingWork < bestOutstandingWork ||
                    presentCount > bestPresentCount) {
                lastAssetProgressAt = Date.now();
                bestLoadedModelCount = Math.max(bestLoadedModelCount,
                    latestInventory.loaded_visible_model_count);
                bestOutstandingWork = Math.min(bestOutstandingWork, outstandingWork);
                bestPresentCount = Math.max(bestPresentCount, presentCount);
            }
        }

        if (Date.now() >= nextProgressAt) {
            print("OVERTE_MACOS_SMOKE online_progress entities=" +
                latestInventory.entity_count + " renderables=" +
                latestInventory.visible_renderable_count + " models=" +
                latestInventory.visible_model_count + " loaded_models=" +
                latestInventory.loaded_visible_model_count + " presents=" +
                presentCount + " queues=" +
                JSON.stringify(resources));
            nextProgressAt = Date.now() + 30000;
        }

        if (snapshotStage === "waiting" && productionSceneReady) {
            if (fullSceneReadyAt === 0) {
                // Require a stable fully loaded interval and then a newer
                // presented frame. Neither condition changes application state.
                fullSceneReadyAt = Date.now() + 5000;
                readyPresentBaseline = presentCount;
                print("OVERTE_MACOS_SMOKE full_scene_ready count=" +
                    latestInventory.visible_renderable_count + " models=" +
                    latestInventory.visible_model_count + " loaded_models=" +
                    latestInventory.loaded_visible_model_count + " queues=" +
                    JSON.stringify(resources));
            }
        } else if (snapshotStage === "waiting") {
            fullSceneReadyAt = 0;
        }

        if (snapshotStage === "waiting" && fullSceneReadyAt !== 0 &&
                Date.now() >= fullSceneReadyAt &&
                presentCount > readyPresentBaseline) {
            latestInventory = inspectEntityInventory(entities, entities.length);
            latestInventory.resource_queues = resources;
            latestInventory.present_count = presentCount;
            saveEntityInventory(latestInventory);
            snapshotStage = "capturing";
            print("OVERTE_MACOS_SMOKE online_entities=" + entities.length);
            Window.takeSnapshot(false, false, 16 / 9, "macos-online-smoke.png");
            snapshotSettleDeadline = Date.now() + 300000;
        }

        if (snapshotStage === "capturing" && snapshotSettleDeadline !== 0 &&
                Date.now() >= snapshotSettleDeadline && !snapshotPendingReported) {
            snapshotPendingReported = true;
            print("OVERTE_MACOS_SMOKE snapshot_still_pending");
        }
        if (snapshotStage === "waiting" && !hubConnected &&
                Date.now() >= connectionDeadline) {
            finish(false, "connection_stalled");
            return;
        }
        if (snapshotStage === "waiting" && hubConnected &&
                latestInventory.entity_count === 0 && noEntityDeadline !== 0 &&
                Date.now() >= noEntityDeadline) {
            finish(false, "entity_stream_stalled");
            return;
        }
        // Apple's hosted x86_64 software OpenGL driver can spend substantially
        // longer than the ordinary asset-stall window compiling the first
        // production model frame. Run 32684847557 proved 100%+ process CPU,
        // empty resource queues, and completed draws for almost 19 minutes
        // after the last asset counter changed. Preserve the fast ten-minute
        // failure for connection/assets and bound only this observable first-
        // frame state to twenty minutes. A present is progress and resets the
        // clock; visual readiness and screenshot validation remain unchanged.
        var firstFrameRenderPending = resourcesAreIdle &&
            latestInventory.visible_model_count > 0 &&
            latestInventory.loaded_visible_model_count === 0;
        var assetStallLimit = firstFrameRenderPending ? 1200000 : 600000;
        if (snapshotStage === "waiting" && lastAssetProgressAt !== 0 &&
                Date.now() - lastAssetProgressAt >= assetStallLimit) {
            if (firstFrameRenderPending) {
                finish(false, "first_frame_render_stalled");
            } else {
                finish(false, "asset_loading_stalled");
            }
            return;
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ? "entity_timeout" :
                "snapshot_timeout");
        }
    }, 250);
}());
