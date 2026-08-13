// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // Keep this profile identical to the visual serverless smoke. Performance
    // generations are comparable only when the renderer and fixture match.
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

    var MINIMUM_MEASUREMENT_MS = 20000;
    var MAXIMUM_MEASUREMENT_MS = 90000;
    var MINIMUM_SAMPLE_COUNT = 30;
    var deadline = Date.now() + 180000;
    var expectedNames = {
        "macOS smoke red cube": false,
        "macOS smoke cyan sphere": false,
        "macOS smoke label": false
    };
    var stage = "waiting";
    var completed = false;
    var measurementStartedAt = 0;
    var nextMeasurementCheckAt = 0;
    var rateSamples = [];

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

    function averageRate(name) {
        if (!rateSamples.length) {
            return 0;
        }
        var total = 0;
        rateSamples.forEach(function (sample) {
            total += sample[name];
        });
        return total / rateSamples.length;
    }

    function finish(success, detail) {
        if (completed) {
            return;
        }
        completed = true;
        print("OVERTE_MACOS_PERFORMANCE " + (success ? "passed " : "failed ") + detail);
        Script.stop();
    }

    function completeMeasurement() {
        FrameTimings.finish();
        var samples = FrameTimings.getValues().map(finiteNumber).filter(function (value) {
            return value > 0;
        });
        var sorted = samples.slice().sort(function (left, right) {
            return left - right;
        });
        var total = samples.reduce(function (sum, value) {
            return sum + value;
        }, 0);
        var metrics = {
            schema_version: 1,
            platform: "macos",
            renderer: "opengl-forward",
            fixture_entities: 3,
            duration_ms: Date.now() - measurementStartedAt,
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
            rates_hz: {
                render: averageRate("render"),
                present: averageRate("present"),
                new_frame: averageRate("new_frame"),
                dropped: averageRate("dropped"),
                simulation: averageRate("simulation")
            }
        };
        Test.saveObject(metrics, "macos-performance.json");
        finish(samples.length > 0, "samples=" + samples.length);
    }

    function startMeasurement() {
        stage = "measuring";
        measurementStartedAt = Date.now();
        nextMeasurementCheckAt = MINIMUM_MEASUREMENT_MS;
        FrameTimings.start();
        print("OVERTE_MACOS_PERFORMANCE measurement_started minimum_duration_ms=" +
            MINIMUM_MEASUREMENT_MS + " maximum_duration_ms=" + MAXIMUM_MEASUREMENT_MS +
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
        print("OVERTE_MACOS_PERFORMANCE warmup_snapshot=" + path);
        startMeasurement();
    });

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
                stage = "warmup";
                print("OVERTE_MACOS_PERFORMANCE fixture_entities=3");
                Window.takeSnapshot(false, false, 16 / 9, "macos-performance-warmup.png");
            }
        } else if (stage === "measuring") {
            var elapsedMs = Date.now() - measurementStartedAt;
            var seconds = elapsedMs / 1000;
            var halfAngle = seconds * 0.08;
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
            if (elapsedMs >= nextMeasurementCheckAt) {
                var sampleCount = FrameTimings.getValues().length;
                nextMeasurementCheckAt = elapsedMs + 1000;
                print("OVERTE_MACOS_PERFORMANCE measurement_progress elapsed_ms=" +
                    elapsedMs + " samples=" + sampleCount);
                if ((elapsedMs >= MINIMUM_MEASUREMENT_MS &&
                        sampleCount >= MINIMUM_SAMPLE_COUNT) ||
                        elapsedMs >= MAXIMUM_MEASUREMENT_MS) {
                    completeMeasurement();
                }
            }
        }
        if (Date.now() >= deadline) {
            finish(false, "startup_timeout");
        }
    }, 250);
}());
