// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    if (typeof OVERTE_MACOS_PERFORMANCE_CASE !== "object") {
        throw new Error("missing validated macOS performance case");
    }

    var testCase = OVERTE_MACOS_PERFORMANCE_CASE;
    var profile = testCase.profile;
    var diagnosticLite = testCase.fixture_mode === "diagnostic-lite";
    var localEntities = [];
    var MINIMUM_MEASUREMENT_MS = diagnosticLite ? 20000 : 30000;
    var MAXIMUM_MEASUREMENT_MS = diagnosticLite ? 60000 : 90000;
    var MINIMUM_SAMPLE_COUNT = diagnosticLite ? 15 : 90;
    var SETTLE_MS = diagnosticLite ? 5000 : 10000;
    var scriptStartedAt = Date.now();
    var deadline = scriptStartedAt + 360000;
    var expectedNames = {
        "macOS smoke red cube": false,
        "macOS smoke cyan sphere": false,
        "macOS smoke label": false
    };
    var stage = "waiting";
    var completed = false;
    var settleStartedAt = 0;
    var measurementStartedAt = 0;
    var nextProgressAt = 0;
    var rateSamples = [];
    var statsSamples = [];
    var tracing = false;

    function finiteNumber(value) {
        value = Number(value);
        return isFinite(value) ? value : 0;
    }

    function percentile(sorted, fraction) {
        if (!sorted.length) {
            return 0;
        }
        return sorted[Math.max(0, Math.ceil(sorted.length * fraction) - 1)];
    }

    function summarize(values) {
        var finite = values.map(finiteNumber).filter(function (value) { return value >= 0; });
        var sorted = finite.slice().sort(function (left, right) { return left - right; });
        var total = finite.reduce(function (sum, value) { return sum + value; }, 0);
        return {
            count: finite.length,
            mean: finite.length ? total / finite.length : 0,
            min: finite.length ? sorted[0] : 0,
            p10: percentile(sorted, 0.10),
            p50: percentile(sorted, 0.50),
            p95: percentile(sorted, 0.95),
            max: finite.length ? sorted[sorted.length - 1] : 0
        };
    }

    function safePlatformJSON(method, fallback) {
        try {
            return JSON.parse(method());
        } catch (error) {
            return fallback;
        }
    }

    function applyProfile() {
        Render.renderMethod = profile.render_method;
        Render.shadowsEnabled = profile.shadows;
        Render.hazeEnabled = profile.haze;
        Render.bloomEnabled = profile.bloom;
        Render.ambientOcclusionEnabled = profile.ambient_occlusion;
        Render.localLightingEnabled = profile.local_lighting;
        Render.proceduralMaterialsEnabled = profile.procedural_materials;
        Render.antialiasingMode = profile.antialiasing;
        Render.viewportResolutionScale = profile.viewport_scale;
        Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples =
            profile.forward_samples;
        Scene.shouldRenderAvatars = false;
        Performance.setRefreshRateProfile(2);
        LODManager.automaticLODAdjust = false;
        LODManager.lodAngleDeg = 0.248;
        Stats.expanded = true;
        print("OVERTE_MACOS_PROFILE applied id=" + profile.id +
            " method=" + profile.render_method + " scale=" + profile.viewport_scale +
            " msaa=" + profile.forward_samples);
    }

    function addEntity(properties) {
        var id = Entities.addEntity(properties, "local");
        localEntities.push(id);
        return id;
    }

    function createStressScene() {
        var rows = diagnosticLite ? 3 : 5;
        var columns = diagnosticLite ? 4 : 9;
        var row;
        var column;
        var materialParent = null;
        if (!diagnosticLite) {
            addEntity({
                type: "Zone",
                name: "macOS profile zone",
                position: { x: 0, y: 2, z: -12 },
                dimensions: { x: 40, y: 20, z: 40 },
                keyLightMode: "enabled",
                keyLight: {
                    color: { red: 255, green: 244, blue: 225 },
                    intensity: 1.0,
                    direction: { x: -0.35, y: -0.8, z: -0.45 },
                    castShadows: true,
                    shadowMaxDistance: 40
                },
                ambientLightMode: "enabled",
                ambientLight: {
                    ambientColor: { red: 75, green: 85, blue: 110 },
                    ambientIntensity: 0.45
                },
                hazeMode: "enabled",
                haze: { hazeRange: 120, hazeColor: { red: 95, green: 115, blue: 145 } },
                bloomMode: "enabled",
                bloom: { bloomIntensity: 0.4, bloomThreshold: 0.65, bloomSize: 0.5 }
            });
        }
        addEntity({
            type: "Shape",
            shape: "Cube",
            name: "macOS profile ground",
            position: { x: 0, y: -0.35, z: -13 },
            dimensions: { x: 20, y: 0.25, z: 24 },
            color: { red: 82, green: 88, blue: 98 },
            unlit: diagnosticLite,
            collisionless: true
        });
        for (row = 0; row < rows; row += 1) {
            for (column = 0; column < columns; column += 1) {
                var shapeID = addEntity({
                    type: "Shape",
                    shape: (row + column) % 2 === 0 ? "Sphere" : "Cube",
                    name: "macOS profile object " + row + "-" + column,
                    position: {
                        x: (column - 4) * 1.65,
                        y: 0.55 + row * 0.75,
                        z: -7.0 - row * 2.6 - Math.abs(column - 4) * 0.15
                    },
                    dimensions: { x: 0.9, y: 0.9, z: 0.9 },
                    color: {
                        red: 45 + ((column * 37) % 190),
                        green: 45 + ((row * 43 + column * 11) % 190),
                        blue: 45 + ((row * 29 + column * 23) % 190)
                    },
                    unlit: diagnosticLite,
                    collisionless: true,
                    canCastShadow: true
                });
                if (!diagnosticLite && row === 1 && column === 4) {
                    materialParent = shapeID;
                }
            }
        }
        if (!diagnosticLite) {
            addEntity({
                type: "Material",
                name: "macOS profile emissive PBR material",
                parentID: materialParent,
                parentMaterialName: "0",
                materialURL: "materialData",
                priority: 1,
                materialData: JSON.stringify({
                    materialVersion: 1,
                    materials: [{
                        name: "0",
                        model: "hifi_pbr",
                        albedo: [0.12, 0.35, 1.0],
                        metallic: 0.7,
                        roughness: 0.18,
                        emissive: [2.0, 0.35, 0.10]
                    }]
                })
            });
            addEntity({
                type: "Light",
                name: "macOS profile point light red",
                position: { x: -3.5, y: 2.5, z: -8.5 },
                dimensions: { x: 9, y: 9, z: 9 },
                color: { red: 255, green: 80, blue: 55 },
                intensity: 7,
                falloffRadius: 1.5,
                isSpotlight: false
            });
            addEntity({
                type: "Light",
                name: "macOS profile point light cyan",
                position: { x: 3.5, y: 3.0, z: -11 },
                dimensions: { x: 10, y: 10, z: 10 },
                color: { red: 40, green: 190, blue: 255 },
                intensity: 8,
                falloffRadius: 1.5,
                isSpotlight: false
            });
        }
        print("OVERTE_MACOS_PROFILE stress_entities=" + localEntities.length +
            " fixture_mode=" + testCase.fixture_mode);
    }

    function cleanup() {
        localEntities.forEach(function (id) { Entities.deleteEntity(id); });
        localEntities = [];
    }

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        if (tracing) {
            Test.stopTracing(testCase.trace_path);
            tracing = false;
        }
        print("OVERTE_MACOS_PROFILE " + (success ? "passed " : "failed ") +
            "id=" + profile.id + " run=" + testCase.run_index + " " + detail);
        cleanup();
        Script.stop();
    }

    function completeMeasurement() {
        FrameTimings.finish();
        var samples = FrameTimings.getValues().map(finiteNumber).filter(function (value) {
            return value > 0;
        });
        var sorted = samples.slice().sort(function (left, right) { return left - right; });
        var total = samples.reduce(function (sum, value) { return sum + value; }, 0);
        var rateNames = ["render", "present", "new_frame", "dropped", "simulation"];
        var rates = {};
        rateNames.forEach(function (name) {
            rates[name] = summarize(rateSamples.map(function (sample) { return sample[name]; }));
        });
        var stats = {};
        ["gpuFrameTime", "batchFrameTime", "engineFrameTime", "drawcalls", "triangles",
            "itemRendered", "shadowRendered", "gpuTextureMemory", "gpuTextureResidentMemory",
            "gpuTextureFramebufferMemory", "texturePendingTransfers"].forEach(function (name) {
            stats[name] = summarize(statsSamples.map(function (sample) { return sample[name]; }));
        });
        var metrics = {
            schema_version: 2,
            platform: "macos",
            fixture_version: testCase.fixture_version,
            fixture_mode: testCase.fixture_mode,
            profile_id: profile.id,
            run_index: testCase.run_index,
            quality_score: profile.quality_score,
            requested_profile: profile,
            actual_profile: {
                render_method: Render.renderMethod,
                shadows: Render.shadowsEnabled,
                haze: Render.hazeEnabled,
                bloom: Render.bloomEnabled,
                ambient_occlusion: Render.ambientOcclusionEnabled,
                local_lighting: Render.localLightingEnabled,
                procedural_materials: Render.proceduralMaterialsEnabled,
                antialiasing: Render.antialiasingMode,
                viewport_scale: Render.viewportResolutionScale,
                forward_samples: Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples
            },
            platform_info: {
                platform: safePlatformJSON(function () { return PlatformInfo.getPlatform(); }, {}),
                computer: safePlatformJSON(function () { return PlatformInfo.getComputer(); }, {}),
                cpu: safePlatformJSON(function () { return PlatformInfo.getCPU(PlatformInfo.getPrimaryCPU()); }, {}),
                gpu: safePlatformJSON(function () { return PlatformInfo.getGPU(PlatformInfo.getPrimaryGPU()); }, {}),
                display: safePlatformJSON(function () { return PlatformInfo.getDisplay(PlatformInfo.getPrimaryDisplay()); }, {}),
                tier: finiteNumber(PlatformInfo.getTierProfiled()),
                deferred_capable: Boolean(PlatformInfo.isRenderMethodDeferredCapable())
            },
            stress_entities: localEntities.length,
            warmup_to_snapshot_ms: measurementStartedAt - scriptStartedAt,
            duration_ms: Date.now() - measurementStartedAt,
            measurement_complete: samples.length >= MINIMUM_SAMPLE_COUNT,
            sample_count: samples.length,
            frame_time_unit: "microseconds",
            samples_us: samples,
            mean_frame_ms: samples.length ? total / samples.length / 1000 : 0,
            min_frame_ms: samples.length ? sorted[0] / 1000 : 0,
            p50_frame_ms: percentile(sorted, 0.50) / 1000,
            p90_frame_ms: percentile(sorted, 0.90) / 1000,
            p95_frame_ms: percentile(sorted, 0.95) / 1000,
            p99_frame_ms: percentile(sorted, 0.99) / 1000,
            max_frame_ms: samples.length ? sorted[sorted.length - 1] / 1000 : 0,
            over_16_67_ms: samples.filter(function (value) { return value > 16667; }).length,
            over_33_33_ms: samples.filter(function (value) { return value > 33333; }).length,
            rates_hz: rates,
            stats: stats
        };
        Test.saveObject(metrics, "macos-profile.json");
        finish(metrics.measurement_complete, "samples=" + samples.length);
    }

    function startMeasurement() {
        stage = "measuring";
        measurementStartedAt = Date.now();
        nextProgressAt = MINIMUM_MEASUREMENT_MS;
        tracing = Test.startTracing();
        FrameTimings.start();
        print("OVERTE_MACOS_PROFILE measurement_started id=" + profile.id +
            " minimum_duration_ms=" + MINIMUM_MEASUREMENT_MS +
            " minimum_samples=" + MINIMUM_SAMPLE_COUNT);
    }

    Window.stillSnapshotTaken.connect(function (path) {
        if (stage !== "warmup") {
            return;
        }
        if (!path) {
            finish(false, "snapshot_save_failed");
            return;
        }
        print("OVERTE_MACOS_PROFILE warmup_snapshot=" + path);
        startMeasurement();
    });

    if (Script.scriptEnding && Script.scriptEnding.connect) {
        Script.scriptEnding.connect(cleanup);
    }
    applyProfile();

    Script.setInterval(function () {
        if (completed) {
            return;
        }
        if (stage === "waiting") {
            var entities = Entities.findEntities(MyAvatar.position, 16384);
            entities.forEach(function (entityID) {
                var name = Entities.getEntityProperties(entityID, ["name"]).name;
                if (Object.prototype.hasOwnProperty.call(expectedNames, name)) {
                    expectedNames[name] = true;
                }
            });
            if (Object.keys(expectedNames).every(function (name) { return expectedNames[name]; })) {
                createStressScene();
                stage = "settling";
                settleStartedAt = Date.now();
            }
        } else if (stage === "settling" && Date.now() - settleStartedAt >= SETTLE_MS) {
            stage = "warmup";
            Window.takeSnapshot(false, false, 16 / 9, "macos-profile.png");
        } else if (stage === "measuring") {
            var elapsedMs = Date.now() - measurementStartedAt;
            var seconds = elapsedMs / 1000;
            Stats.forceUpdateStats();
            var halfAngle = Math.sin(seconds * 0.20) * 0.18;
            MyAvatar.setOrientationVar(Quat.normalize({
                x: 0,
                y: -Math.sin(halfAngle),
                z: 0,
                w: Math.cos(halfAngle)
            }));
            rateSamples.push({
                render: finiteNumber(Rates.render),
                present: finiteNumber(Rates.present),
                new_frame: finiteNumber(Rates.newFrame),
                dropped: finiteNumber(Rates.dropped),
                simulation: finiteNumber(Rates.simulation)
            });
            statsSamples.push({
                gpuFrameTime: finiteNumber(Stats.gpuFrameTime),
                batchFrameTime: finiteNumber(Stats.batchFrameTime),
                engineFrameTime: finiteNumber(Stats.engineFrameTime),
                drawcalls: finiteNumber(Stats.drawcalls),
                triangles: finiteNumber(Stats.triangles),
                itemRendered: finiteNumber(Stats.itemRendered),
                shadowRendered: finiteNumber(Stats.shadowRendered),
                gpuTextureMemory: finiteNumber(Stats.gpuTextureMemory),
                gpuTextureResidentMemory: finiteNumber(Stats.gpuTextureResidentMemory),
                gpuTextureFramebufferMemory: finiteNumber(Stats.gpuTextureFramebufferMemory),
                texturePendingTransfers: finiteNumber(Stats.texturePendingTransfers)
            });
            if (elapsedMs >= nextProgressAt) {
                var sampleCount = FrameTimings.getValues().length;
                nextProgressAt = elapsedMs + 5000;
                print("OVERTE_MACOS_PROFILE measurement_progress id=" + profile.id +
                    " elapsed_ms=" + elapsedMs + " samples=" + sampleCount +
                    " present_hz=" + finiteNumber(Rates.present));
                if ((elapsedMs >= MINIMUM_MEASUREMENT_MS &&
                        sampleCount >= MINIMUM_SAMPLE_COUNT) ||
                        elapsedMs >= MAXIMUM_MEASUREMENT_MS) {
                    completeMeasurement();
                }
            }
        }
        if (Date.now() >= deadline) {
            finish(false, "profile_timeout stage=" + stage);
        }
    }, 250);
}());
