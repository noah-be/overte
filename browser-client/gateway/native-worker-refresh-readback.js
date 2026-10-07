// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Trusted optional read-only diagnostic. This does not set Performance/Render/
// Settings, expose device labels or replace normal native protocol timers.
var readNativeWorkerRefresh = function (api) {
    'use strict';
    if (!api || typeof api.getPerformancePreset !== 'function' || typeof api.getRefreshRateProfile !== 'function'
        || typeof api.getActiveRefreshRate !== 'function' || typeof api.getRefreshRateRegime !== 'function'
        || typeof api.getCustomRefreshRate !== 'function') {
        throw Error('Native worker refresh-rate readback is unavailable');
    }
    function integer(value, minimum, maximum) {
        if (typeof value !== 'number' || !isFinite(value) || Math.floor(value) !== value || value < minimum || value > maximum) {
            throw Error('Native worker refresh-rate readback is invalid');
        }
        return value;
    }
    var preset = integer(api.getPerformancePreset(), 0, 5), profile = integer(api.getRefreshRateProfile(), 0, 3);
    var regime = integer(api.getRefreshRateRegime(), 0, 5), target = integer(api.getActiveRefreshRate(), 1, 1000);
    var custom = [], expected = [10, 10, 10, 2, 10, 30], exact = true;
    for (var index = 0; index < 6; index++) {
        custom.push(integer(api.getCustomRefreshRate(index), 1, 1000));
        if (custom[index] !== expected[index]) exact = false;
    }
    return { performancePreset: preset, refreshRateProfile: profile, regime: regime, targetHz: target,
        customHz: custom, applied: preset === 5 && profile === 3 && exact && target === custom[regime],
        scope: 'Requested native worker refresh target; actual frame cadence and CPU cost require independent measurement' };
};
