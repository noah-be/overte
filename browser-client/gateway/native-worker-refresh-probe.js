// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Optional trusted diagnostic appended AFTER native-worker-refresh-readback.js
// to an owned fresh native script. No entity/account/audio/graphics mutation.
(function () {
    'use strict';
    var samples = 0, timer = Script.setInterval(function () {
        try {
            var value = readNativeWorkerRefresh(Performance);
            value.at = Date.now();
            print('OVERTE_BROWSER_WORKER_REFRESH ' + JSON.stringify(value));
        } catch (error) {
            print('OVERTE_BROWSER_WORKER_REFRESH ' + JSON.stringify({ at: Date.now(), unavailable: true }));
        }
        samples++;
        if (samples >= 6) { Script.clearInterval(timer); }
    }, 1000);
    Script.scriptEnding.connect(function () { Script.clearInterval(timer); });
}());
