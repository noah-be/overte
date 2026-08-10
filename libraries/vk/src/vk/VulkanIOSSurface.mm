// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "VulkanIOSSurface.h"

#include <QWindow>
#include <QuartzCore/CAMetalLayer.h>
#include <UIKit/UIView.h>

void* overteIOSMetalLayerForWindow(QWindow* window) {
    if (!window) {
        return nullptr;
    }

    // On Qt for iOS, QWindow::winId() is the native UIView. A VulkanSurface
    // requests a CAMetalLayer from the platform plugin; do not replace the
    // layer here because Qt owns its lifetime and geometry updates.
    UIView* view = (__bridge UIView*)reinterpret_cast<void*>(window->winId());
    if (!view || ![view.layer isKindOfClass:[CAMetalLayer class]]) {
        return nullptr;
    }
    return (__bridge void*)(CAMetalLayer*)view.layer;
}
