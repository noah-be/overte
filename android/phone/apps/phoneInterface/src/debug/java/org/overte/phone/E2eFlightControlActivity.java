// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.phone;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/** Shell-restricted debug entry point for the process-only E2E flight override. */
public final class E2eFlightControlActivity extends Activity {
    static final String EXTRA_MODE = "org.overte.phone.e2e.FLIGHT_MODE";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        int mode = getIntent().getIntExtra(EXTRA_MODE, Integer.MIN_VALUE);
        if (PhoneE2eLaunchState.requestFlyingOverride(mode)) {
            Intent interfaceIntent = new Intent(this, PhoneInterfaceActivity.class);
            interfaceIntent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            startActivity(interfaceIntent);
        }
        finish();
    }
}
