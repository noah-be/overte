// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Match the supported desktop scene path. The local avatar and default
    // client scripts are disabled by the runner before they can submit
    // unrelated skinned or overlay pipelines. The runner also disables
    // streamed entity scripts before EntityTreeRenderer creates its script
    // engines: public scripts can create unrelated local models and make the
    // hosted software renderer compile pipelines outside this test's scope.
    Render.renderMethod = 1;
    Render.shadowsEnabled = false;
    Render.hazeEnabled = false;
    Render.bloomEnabled = false;
    Render.ambientOcclusionEnabled = false;
    Render.localLightingEnabled = true;
    Render.proceduralMaterialsEnabled = false;
    Render.antialiasingMode = 0;
    Render.viewportResolutionScale = 1.0;
    Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples = 1;
    Scene.shouldRenderAvatars = false;

    // The hosted Intel runner exposes Apple's software OpenGL renderer.  A
    // public-domain model pipeline has been measured taking just over three
    // minutes per pipeline to compile there even though the process remains
    // CPU-active. A real Hub frame has required multiple serial pipelines, so
    // keep the in-app deadline below the external 1200-second supervisor.
    var deadline = Date.now() + 1140000;
    var snapshotStage = "waiting";
    var snapshotSettleDeadline = 0;
    var snapshotPendingReported = false;
    var visibleGeometryReadyAt = 0;
    var readyPresentBaseline = 0;
    var snapshotPath = "";
    var latestInventory = null;
    var completed = false;
    var diagnosticLightID = null;
    var representativeCameraFramed = false;

    function representativeModelID() {
        return String(Test.getMacOSRepresentativeEntityID() || "");
    }

    function frameRepresentativeModel() {
        if (representativeCameraFramed) {
            return true;
        }
        var entityID = representativeModelID();
        if (!entityID) {
            return false;
        }
        var properties = Entities.getEntityProperties(entityID, [
            "type", "visible", "position", "dimensions", "rotation"
        ]);
        if (String(properties.type) !== "Model" || properties.visible === false) {
            return false;
        }
        var position = plainVector(properties.position);
        var dimensions = plainVector(properties.dimensions);
        var distance = Math.max(6, dimensions.x * 2, dimensions.y * 2, dimensions.z * 2);
        var smallestAxis = dimensions.x <= dimensions.y && dimensions.x <= dimensions.z ?
            { x: 1, y: 0, z: 0 } : dimensions.y <= dimensions.z ?
            { x: 0, y: 1, z: 0 } : { x: 0, y: 0, z: 1 };
        var viewDirection = Vec3.multiplyQbyV(properties.rotation, smallestAxis);
        var target = {
            x: position.x,
            y: position.y + dimensions.y * 0.15,
            z: position.z
        };
        var cameraPosition = {
            x: target.x + finiteNumber(viewDirection.x) * distance,
            y: target.y + finiteNumber(viewDirection.y) * distance,
            z: target.z + finiteNumber(viewDirection.z) * distance
        };
        var cameraUp = Math.abs(finiteNumber(viewDirection.y)) > 0.9 ?
            { x: 1, y: 0, z: 0 } : { x: 0, y: 1, z: 0 };
        Camera.mode = "independent";
        Camera.position = cameraPosition;
        Camera.orientation = Quat.lookAt(cameraPosition, target, cameraUp);
        representativeCameraFramed = true;
        print("OVERTE_MACOS_SMOKE representative_camera=" + entityID +
            " distance=" + distance + " smallest_axis=" + JSON.stringify(smallestAxis));
        return true;
    }

    function ensureDiagnosticLight() {
        if (diagnosticLightID) {
            return;
        }
        var cameraPosition = Camera.position;
        diagnosticLightID = Entities.addEntity({
            type: "Light",
            name: "macOS online smoke camera light",
            position: {
                x: finiteNumber(cameraPosition.x),
                y: finiteNumber(cameraPosition.y) + 3,
                z: finiteNumber(cameraPosition.z)
            },
            dimensions: { x: 80, y: 80, z: 80 },
            color: { red: 255, green: 245, blue: 230 },
            intensity: 12,
            falloffRadius: 20,
            isSpotlight: false
        }, "local");
        print("OVERTE_MACOS_SMOKE diagnostic_light=" + diagnosticLightID);
    }

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
            typeCounts[type] = (typeCounts[type] || 0) + 1;
            if (visible && !nonVisibleGeometryTypes[type]) {
                visibleRenderableCount += 1;
            }
            if (visible && primitiveTypes[type]) {
                visiblePrimitiveCount += 1;
            }
            var loaded = visible && type === "Model" && Entities.isLoaded(entityID);
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
        // A successful snapshot can leave the app's main thread blocked in Qt
        // render synchronization after the script finishes. Persist the
        // sentinel only after that concrete proof exists. On failure, leave
        // the process to the outer bounded supervisor so it captures a macOS
        // sample before terminating the renderer instead of stopping early
        // with no stack evidence.
        if (success) {
            Test.saveObject({
                schema_version: 1,
                ready_for_external_validation: true,
                script_success: true
            }, "macos-online-smoke-completion.json");
        }
        if (diagnosticLightID) {
            Entities.deleteEntity(diagnosticLightID);
            diagnosticLightID = null;
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
        if (snapshotStage === "waiting" && latestInventory.visible_model_count > 0) {
            if (!frameRepresentativeModel()) {
                return;
            }
            ensureDiagnosticLight();
            var selectedModelID = representativeModelID();
            if (visibleGeometryReadyAt === 0 && selectedModelID &&
                    Entities.isLoaded(selectedModelID)) {
                // Apple's virtualized software renderer can present primitive
                // frames while the selected model is still downloading. Only
                // begin the render gate once that exact Hub model is loaded,
                // then require a newer completed frame containing its draw.
                visibleGeometryReadyAt = Date.now();
                readyPresentBaseline = finiteNumber(Test.getPresentCount());
                print("OVERTE_MACOS_SMOKE representative_model_loaded=" +
                    selectedModelID + " visible_geometry_ready count=" +
                    latestInventory.visible_renderable_count + " models=" +
                    latestInventory.visible_model_count + " loaded_models=" +
                    latestInventory.loaded_visible_model_count + " queues=" +
                    JSON.stringify(resources));
            }
        } else if (snapshotStage === "waiting") {
            visibleGeometryReadyAt = 0;
        }
        if (snapshotStage === "waiting" && visibleGeometryReadyAt !== 0 &&
                Date.now() >= visibleGeometryReadyAt &&
                finiteNumber(Test.getPresentCount()) > readyPresentBaseline) {
            // Record the complete nearby scene snapshot once. Polling stays
            // cheap above, while the final inventory correlates a streamed
            // primitive handoff with at least one visible domain primitive.
            latestInventory = inspectEntityInventory(entities, entities.length);
            latestInventory.resource_queues = resources;
            latestInventory.present_count = finiteNumber(Test.getPresentCount());
            saveEntityInventory(latestInventory);
            snapshotStage = "capturing";
            print("OVERTE_MACOS_SMOKE online_entities=" + entities.length);
            // One completed frame is the online rendering proof. Waiting for
            // a second capture lets unrelated late domain assets enqueue new
            // pipelines; Apple's virtualized software renderer may spend
            // minutes compiling those after the scene is already visible.
            Window.takeSnapshot(false, false, 16 / 9, "macos-online-smoke.png");
            // On Apple's software GL runner the PNG writer can complete while
            // the main-thread stillSnapshotTaken callback remains queued
            // behind active domain-script setup. The shell is authoritative:
            // after this bounded settle it requires and decodes the PNG before
            // accepting the run. A timely callback still finishes earlier.
            // A content-heavy public domain can keep Apple's virtualized
            // software renderer busy after the lightweight primitive handoff.
            // The preceding successful run produced the PNG inside this wider
            // budget even though its Qt callback remained queued.
            snapshotSettleDeadline = Date.now() + 300000;
        }
        if (snapshotStage === "capturing" && snapshotSettleDeadline !== 0 &&
                Date.now() >= snapshotSettleDeadline && !snapshotPendingReported) {
            snapshotPendingReported = true;
            print("OVERTE_MACOS_SMOKE snapshot_still_pending");
        }
        if (Date.now() >= deadline) {
            finish(false, snapshotStage === "waiting" ? "entity_timeout" :
                "snapshot_timeout");
        }
    }, 250);
}());
