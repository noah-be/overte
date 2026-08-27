// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.os.Bundle;
import android.view.WindowManager;

/** Debug-only Pico interface with the factory-tool minimum display brightness. */
public final class E2ePicoInterfaceActivity extends PicoInterfaceActivity {
    static final float MINIMUM_SCREEN_BRIGHTNESS = 1.0f / 255.0f;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        WindowManager.LayoutParams attributes = getWindow().getAttributes();
        attributes.screenBrightness = MINIMUM_SCREEN_BRIGHTNESS;
        getWindow().setAttributes(attributes);
        super.onCreate(savedInstanceState);
    }
}
