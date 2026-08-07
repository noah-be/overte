package org.overte.phone;

import android.content.Intent;
import android.net.Uri;

/** Validates and canonicalizes URLs accepted from exported Android intents. */
final class PhoneDeepLink {
    static final int MAX_URL_LENGTH = PhoneDeepLinkNormalizer.MAX_URL_LENGTH;
    static final String EXTRA_URL = "org.overte.phone.extra.DEEP_LINK_URL";

    private PhoneDeepLink() {
    }

    static String fromIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_VIEW.equals(intent.getAction())) {
            return null;
        }
        return normalize(intent.getData());
    }

    static String fromInternalExtra(Intent intent) {
        if (intent == null) {
            return null;
        }
        String value = intent.getStringExtra(EXTRA_URL);
        return value == null ? null : normalize(Uri.parse(value));
    }

    static String normalize(Uri destination) {
        return destination == null
            ? null
            : PhoneDeepLinkNormalizer.normalize(destination.toString());
    }
}
