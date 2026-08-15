// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    if (typeof OVERTE_MACOS_ONLINE_LOADING_CASE !== "object") {
        throw new Error("missing validated online loading case");
    }

    var testCase = OVERTE_MACOS_ONLINE_LOADING_CASE;
    var diagnosticOnly = testCase.runner_class === "diagnostic";
    var startedAt = Date.now();
    var deadline = startedAt + (diagnosticOnly ? 70000 : 360000);
    var measurementDeadline = 0;
    var firstEntitiesMs = null;
    var firstVisibleMs = null;
    var snapshotRequestedMs = null;
    var snapshotCompletedMs = null;
    var idleStartedAt = 0;
    var sustainedIdleMs = null;
    var completed = false;
    var snapshotRequested = false;
    var samples = [];
    var maxEntityCount = 0;

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
    Performance.setRefreshRateProfile(2);
    Scene.shouldRenderAvatars = false;
    Stats.expanded = true;

    function finiteNumber(value) {
        value = Number(value);
        return isFinite(value) ? value : 0;
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

    function queuesEmpty(state) {
        return state.downloads === 0 && state.downloads_pending === 0 &&
            state.processing === 0 && state.processing_pending === 0 &&
            state.texture_pending_mb === 0 && Test.isTextureLoadingComplete();
    }

    function inspectVisible(entities) {
        var ignored = { Unknown: true, Empty: true, Sound: true, Script: true, Zone: true,
            Light: true, Material: true };
        var visible = 0;
        entities.slice(0, 512).forEach(function (id) {
            var properties = Entities.getEntityProperties(id, ["type", "visible"]);
            var type = String(properties.type || "Unknown");
            if (properties.visible !== false && !ignored[type]) {
                visible += 1;
            }
        });
        return visible;
    }

    function publish(success, reason) {
        if (completed) {
            return;
        }
        completed = true;
        var result = {
            schema_version: 1,
            platform: "macos",
            cache_mode: testCase.cache_mode,
            concurrency: testCase.concurrency,
            run_index: testCase.run_index,
            location_label: testCase.location_label,
            runner_class: testCase.runner_class,
            duration_ms: Date.now() - startedAt,
            first_entities_ms: firstEntitiesMs,
            first_visible_ms: firstVisibleMs,
            snapshot_requested_ms: snapshotRequestedMs,
            snapshot_completed_ms: snapshotCompletedMs,
            sustained_idle_ms: sustainedIdleMs,
            max_entity_count: maxEntityCount,
            queue_sample_interval_ms: 500,
            queue_samples: samples,
            completed_idle: sustainedIdleMs !== null,
            completed_snapshot: snapshotCompletedMs !== null,
            success: success,
            reason: reason
        };
        Test.saveObject(result, "macos-online-loading.json");
        print("OVERTE_MACOS_ONLINE_LOADING " + (success ? "passed " : "failed ") +
            "cache=" + testCase.cache_mode + " run=" + testCase.run_index +
            " reason=" + reason + " entities=" + maxEntityCount);
        Script.stop();
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (!snapshotRequested || snapshotCompletedMs !== null) {
            return;
        }
        if (!path) {
            publish(false, "snapshot_save_failed");
            return;
        }
        snapshotCompletedMs = Date.now() - startedAt;
        print("OVERTE_MACOS_ONLINE_LOADING snapshot_complete_ms=" + snapshotCompletedMs);
    });

    print("OVERTE_MACOS_ONLINE_LOADING started cache=" + testCase.cache_mode +
        " concurrency=" + testCase.concurrency + " run=" + testCase.run_index);

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        var now = Date.now();
        var elapsed = now - startedAt;
        var state = queueState();
        var entities = Entities.findEntities(MyAvatar.position, 16384);
        maxEntityCount = Math.max(maxEntityCount, entities.length);
        var visible = inspectVisible(entities);
        samples.push({
            elapsed_ms: elapsed,
            downloads: state.downloads,
            downloads_pending: state.downloads_pending,
            processing: state.processing,
            processing_pending: state.processing_pending,
            texture_pending_mb: state.texture_pending_mb,
            entity_count: entities.length,
            visible_count: visible,
            present_hz: finiteNumber(Rates.present),
            new_frame_hz: finiteNumber(Rates.newFrame)
        });
        if (samples.length > 720) {
            samples.shift();
        }
        if (firstEntitiesMs === null && entities.length > 0) {
            firstEntitiesMs = elapsed;
            print("OVERTE_MACOS_ONLINE_LOADING first_entities_ms=" + firstEntitiesMs +
                " count=" + entities.length);
        }
        if (firstVisibleMs === null && visible > 0) {
            firstVisibleMs = elapsed;
            measurementDeadline = now + (diagnosticOnly ? 30000 : 180000);
            print("OVERTE_MACOS_ONLINE_LOADING first_visible_ms=" + firstVisibleMs +
                " count=" + visible);
        }
        if (firstVisibleMs !== null && !snapshotRequested && elapsed - firstVisibleMs >= 2000) {
            snapshotRequested = true;
            snapshotRequestedMs = elapsed;
            Window.takeSnapshot(false, false, 16 / 9, "macos-online-loading.png");
        }
        if (firstVisibleMs !== null && queuesEmpty(state)) {
            if (idleStartedAt === 0) {
                idleStartedAt = now;
            } else if (sustainedIdleMs === null && now - idleStartedAt >= 5000) {
                sustainedIdleMs = elapsed;
                print("OVERTE_MACOS_ONLINE_LOADING sustained_idle_ms=" + sustainedIdleMs);
            }
        } else {
            idleStartedAt = 0;
        }
        if (sustainedIdleMs !== null && snapshotCompletedMs !== null) {
            publish(true, "visible_and_idle");
        } else if (diagnosticOnly && measurementDeadline !== 0 && now >= measurementDeadline) {
            publish(false, "diagnostic_observation_complete");
        } else if (measurementDeadline !== 0 && now >= measurementDeadline) {
            publish(snapshotCompletedMs !== null, "bounded_measurement_complete");
        } else if (now >= deadline) {
            publish(false, firstVisibleMs === null ? "visible_timeout" : "overall_timeout");
        }
    }, 500);
}());
