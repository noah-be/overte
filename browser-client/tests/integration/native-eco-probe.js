// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted standalone experiment only. The only setting mutation is the valid
// ECO refresh enum, followed by restoration of the original valid enum.
(function () {
    'use strict';
    var marker = 'OVERTE_BROWSER_NATIVE_ECO ', originalProfile, changed = false, finished = false;
    var startup = Date.now(), timer, baseline, baselineRegime, eligibleAt;
    var targets = [20, 10, 5, 2, 30, 30];
    function number(value, min, max, integer) {
        if (typeof value !== 'number' || !isFinite(value) || value < min || value > max || (integer && Math.floor(value) !== value)) throw Error('Native numeric readback unavailable');
        return value;
    }
    function boolean(value) { if (typeof value !== 'boolean') throw Error('Native boolean readback unavailable'); return value; }
    function quality() {
        // Public native getters/properties only. Automatic LOD's changing angle
        // is not a configuration setter, and is reported separately below.
        return {
            performancePreset: number(Performance.getPerformancePreset(), 1, 4, true),
            renderMethod: number(Render.getRenderMethod(), 0, 1, true),
            shadowsEnabled: boolean(Render.getShadowsEnabled()), hazeEnabled: boolean(Render.getHazeEnabled()),
            bloomEnabled: boolean(Render.getBloomEnabled()), ambientOcclusionEnabled: boolean(Render.getAmbientOcclusionEnabled()),
            localLightingEnabled: boolean(Render.getLocalLightingEnabled()), proceduralMaterialsEnabled: boolean(Render.getProceduralMaterialsEnabled()),
            antialiasingMode: number(Render.getAntialiasingMode(), 0, 32, true),
            viewportResolutionScale: number(Render.getViewportResolutionScale(), 0.001, 100, false),
            verticalFieldOfView: number(Render.getVerticalFieldOfView(), 0.001, 179.999, false),
            cameraClippingEnabled: boolean(Render.getCameraClippingEnabled()),
            worldDetailQuality: number(LODManager.worldDetailQuality, 0, 2, true),
            automaticLODAdjust: boolean(LODManager.automaticLODAdjust)
        };
    }
    function sameQuality(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
    function snapshot(phase) {
        var regime = number(Performance.getRefreshRateRegime(), 0, 5, true);
        var version = String(About.buildVersion);
        if (version !== '2026.04.1') throw Error('The reviewed native release is required');
        return { phase: phase, at: Date.now(), nativeVersion: version, connected: !!location.isConnected,
            domainMatched: /^hifi:\/\/127\.0\.0\.2:45102(?:\/|$)/i.test(String(location.href)) || /^overte:\/\/127\.0\.0\.2:45102(?:\/|$)/i.test(String(location.href)),
            refreshRateProfile: number(Performance.getRefreshRateProfile(), 0, 2, true),
            regime: regime, targetHz: number(Performance.getActiveRefreshRate(), 1, 1000, true),
            quality: quality(), dynamicLOD: { angleDeg: number(LODManager.lodAngleDeg, 0, 180, false), targetFPS: number(LODManager.lodTargetFPS, 0.001, 1000, false) } };
    }
    function emit(record) { print(marker + JSON.stringify(record)); }
    function assertCurrent(record) {
        if (!record.connected || !record.domainMatched || record.regime > 3) throw Error('Native connection or steady refresh regime changed');
        if (baseline && !sameQuality(baseline.quality, record.quality)) throw Error('Ordinary native quality configuration changed');
    }
    function restore() {
        if (!changed) return;
        Performance.setRefreshRateProfile(originalProfile);
        changed = false;
        var record = snapshot('restored'); assertCurrent(record);
        if (record.refreshRateProfile !== originalProfile) throw Error('Original valid refresh profile was not restored');
        emit(record);
    }
    function fail() {
        if (finished) return;
        finished = true; if (timer) Script.clearInterval(timer);
        // Never print exception strings from native objects or arbitrary data.
        emit({ phase: 'error', at: Date.now(), error: 'Native ECO experiment failed its reviewed connection quality or API contract' });
        try { restore(); } catch (ignored) { emit({ phase: 'restoreError', at: Date.now(), error: 'Original valid native refresh profile could not be restored' }); }
    }
    function applyEco() {
        try {
            var before = snapshot('baselineEnd'); assertCurrent(before);
            if (before.refreshRateProfile !== originalProfile || before.regime !== baselineRegime) throw Error('Baseline refresh regime changed');
            emit(before);
            // Flag was admitted by the runner before process allocation. No
            // constructor CUSTOM profile or graphics/LOD setter is used.
            changed = true; Performance.setRefreshRateProfile(0);
            var after = snapshot('eco'); assertCurrent(after);
            if (!sameQuality(before.quality, after.quality) || after.refreshRateProfile !== 0 || after.targetHz !== targets[after.regime]) throw Error('ECO setter changed more than refresh scheduling');
            emit(after);
            Script.setTimeout(function () {
                try {
                    var end = snapshot('ecoEnd'); assertCurrent(end);
                    if (end.refreshRateProfile !== 0 || end.targetHz !== targets[end.regime] || end.regime !== baselineRegime) throw Error('ECO refresh regime changed');
                    emit(end); restore(); finished = true;
                } catch (ignored) { fail(); }
            }, 5000);
        } catch (ignored) { fail(); }
    }
    Script.scriptEnding.connect(function () { try { restore(); } catch (ignored) {} });
    timer = Script.setInterval(function () {
        if (finished) return;
        if (Date.now() - startup > 90000) { fail(); return; }
        try {
            if (!location.isConnected) { eligibleAt = undefined; return; }
            // Startup and shutdown cadence are not an eligible baseline.
            if (Performance.getRefreshRateRegime() > 3 || Performance.getPerformancePreset() < 1) { eligibleAt = undefined; return; }
            if (eligibleAt === undefined) eligibleAt = Date.now();
            // Give the ordinary startup preset and tiny isolated scene time to
            // settle. This does not certify equal actual rendered LOD/workload.
            if (Date.now() - eligibleAt < 10000) return;
            baseline = snapshot('baseline'); assertCurrent(baseline);
            originalProfile = baseline.refreshRateProfile; baselineRegime = baseline.regime;
            Script.clearInterval(timer); timer = undefined; emit(baseline);
            Script.setTimeout(applyEco, 5000);
        } catch (ignored) { fail(); }
    }, 250);
}());
