// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

package org.overte.pico;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.text.TextUtils;

/** Non-exported entry point that consumes the app-private restart handoff. */
public final class RestartActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        final String applicationArguments = RestartArguments.consume(this);
        final Intent interfaceIntent = new Intent(this, PicoInterfaceActivity.class);
        if (!TextUtils.isEmpty(applicationArguments)) {
            interfaceIntent.putExtra("applicationArguments", applicationArguments);
        }
        startActivity(interfaceIntent);
        finish();
    }
}
