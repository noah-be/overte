// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.phone;

import android.app.Activity;
import java.io.File;

import org.overte.e2e.E2eLauncherActivityBase;

/** Shell-only entry point; this class does not exist in release APKs. */
public final class E2eLauncherActivity extends E2eLauncherActivityBase {
    @Override
    protected String[] additionalAssets() {
        return new String[] { "scripted_interactable.js" };
    }

    @Override
    protected String additionalAssetUrl(String asset, File directory) {
        return "qrc:/overte-e2e/scripted_interactable.js";
    }

    @Override
    protected Class<? extends Activity> interfaceActivity() {
        PhoneE2eLaunchState.begin();
        return PhoneInterfaceActivity.class;
    }
}
