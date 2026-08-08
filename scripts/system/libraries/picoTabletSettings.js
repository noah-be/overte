// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

function bounded(value, fallback, minimum, maximum) {
    value = Number(value);
    if (!isFinite(value)) {
        return fallback;
    }
    return Math.max(minimum, Math.min(maximum, value));
}

module.exports = function (forward, up, tilt) {
    return {
        forward: bounded(forward, 1.25, 0.4, 2.0),
        up: bounded(up, -0.52, -1.3, 0.3),
        tilt: bounded(tilt, -18, -45, 30)
    };
};
