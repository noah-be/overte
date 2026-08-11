package org.overte.phone;

/** Pure decision logic for the optional microphone permission hand-off. */
final class PhonePermissionFlow {
    static final int RECORD_AUDIO_REQUEST = 20;

    private PhonePermissionFlow() {
    }

    static boolean shouldLaunchInterfaceAfterResult(int requestCode) {
        // Voice is optional. Both grant and denial continue into the client,
        // but callbacks belonging to another request must be ignored.
        return requestCode == RECORD_AUDIO_REQUEST;
    }
}
