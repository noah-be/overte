// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "../input/PreviewCamera.h"
#include <cassert>
#include <limits>
using overte::ios::PreviewCamera;
int main() {
    PreviewCamera camera;
    assert(!camera.rotate(std::numeric_limits<double>::infinity(), 0));
    assert(!camera.scale(std::numeric_limits<double>::quiet_NaN()));
    assert(!camera.scale(0) && !camera.scale(-1));
    assert(camera.yaw == 0 && camera.zoom == 1);
    for (int i = 0; i < 10000; ++i) { camera.rotate(1000, 1000); camera.scale(1000); }
    assert(std::abs(camera.yaw) <= 3.142f && camera.pitch == 0.35f && camera.zoom == 1.8f);
    camera.rotate(0, -1000);
    camera.scale(0.00001);
    assert(camera.pitch == -1.1f && camera.zoom == 0.55f);
    camera.reset();
    assert(camera.yaw == 0 && camera.pitch == -0.28f && camera.zoom == 1);
}
