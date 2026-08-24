// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

(function () {
    "use strict";

    // This profile is intentionally diagnostic-only. It verifies startup,
    // networking, entity loading, scripting, and a basic rendered frame on a
    // QEMU guest without pretending to provide production-quality evidence.
    Render.renderMethod = 1;
    Render.shadowsEnabled = false;
    Render.hazeEnabled = false;
    Render.bloomEnabled = false;
    Render.ambientOcclusionEnabled = false;
    Render.localLightingEnabled = false;
    Render.proceduralMaterialsEnabled = false;
    Render.antialiasingMode = 0;
    Render.viewportResolutionScale = 0.25;
    Render.getConfig("RenderMainView.PreparePrimaryBufferForward").numSamples = 1;

    Performance.setRefreshRateProfile(2);
    LODManager.automaticLODAdjust = false;
    LODManager.lodAngleDeg = 0.5;

    print("OVERTE_QEMU_DIAGNOSTIC low_power_profile_applied " +
        "forward=true scale=0.25 shadows=false ao=false bloom=false msaa=1");
}());
