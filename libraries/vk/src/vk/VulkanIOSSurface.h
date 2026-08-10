// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

class QWindow;

// Kept as void* so this header remains valid C++ and UIKit/QuartzCore stay in
// the Objective-C++ translation unit. The returned object is a CAMetalLayer
// owned by the native UIView.
void* overteIOSMetalLayerForWindow(QWindow* window);
