// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
/* Read-only physical iOS acceptance observations. No audio source or input override. */
(function () {
    "use strict";
    var run = OVERTE_ACCEPTANCE_RUN;
    if (!run || !/^output-[0-9a-f]{32}$/.test(run.id)) { throw new Error("acceptance-invalid-run"); }
    var sequence = 0, frameCount = 0, lastFrame = 0;
    var stats = Render.getConfig("Stats");
    function rendered() { frameCount++; lastFrame = Date.now(); }
    if (!stats || !stats.newStats) { throw new Error("acceptance-render-stats-unavailable"); }
    stats.newStats.connect(rendered);
    function vector(value) { return { x: Number(value.x), y: Number(value.y), z: Number(value.z) }; }
    function observe() {
        var now = Date.now();
        try {
            var native = Test.acousticTest({ schemaVersion: 1, commandId: run.id + "-status", action: "status" });
            if (!native || !native.ok || !native.physicalDevice || native.prepared || native.measurementMode
                    || native.sourceEnabled || native.sourceClockActive) {
                throw new Error("acceptance-unexpected-native-state");
            }
            var ids = Entities.findEntities(MyAvatar.position, 10000).map(String).sort();
            if (ids.length > 10000) { throw new Error("acceptance-scene-observation-unbounded"); }
            var markers = [];
            ids.forEach(function (id) {
                var name = String(Entities.getEntityProperties(id, ["name"]).name);
                if (/^OVERTE_E2E_DOMAIN_(FLOOR|NORTH|EAST|ORIGIN)$/.test(name)) { markers.push(name); }
            });
            var tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
            Test.saveObject({ schemaVersion: 1, runId: run.id, sampleSequence: ++sequence,
                sampleEpochMs: now, buildVersion: String(About.buildVersion),
                nativeAudio: native, render: { frameCount: frameCount, lastFrameEpochMs: lastFrame,
                    drawCalls: Number(stats.frameDrawcallCount), triangles: Number(stats.frameTriangleCount) },
                scene: { protocol: String(location.protocol), connected: Boolean(location.isConnected),
                    domainId: String(location.domainID), hostname: String(location.hostname),
                    entityIds: ids, entityCount: ids.length, domainMarkers: markers.sort() },
                avatar: { position: vector(MyAvatar.position), feetPosition: vector(MyAvatar.feetPosition),
                    cameraOrientation: vector(Quat.safeEulerAngles(Camera.orientation)) },
                window: { width: Number(Window.innerWidth), height: Number(Window.innerHeight),
                    hasFocus: Boolean(Window.hasFocus()) },
                nativeUi: Tablet.touchUiRuntimeMetrics,
                tablet: { shown: Boolean(tablet.tabletShown || HMD.showTablet) }
            }, "acceptance-observation.json");
            Test.saveObject({ schemaVersion: 1, runId: run.id, observedEpochMs: now,
                iosForeground: native.iosForeground }, "output-foreground.json");
        } catch (error) {
            Test.saveObject({ schemaVersion: 1, runId: run.id, sampleEpochMs: now,
                error: "acceptance-observation-failed" }, "acceptance-observation.json");
        }
    }
    var timer = Script.setInterval(observe, 1000);
    Script.scriptEnding.connect(function () {
        Script.clearInterval(timer);
        stats.newStats.disconnect(rendered);
    });
    // Keep the observer bounded even if its owning host is lost.
    Script.setTimeout(function () { Script.stop(); }, 4200000);
    observe();
}());
