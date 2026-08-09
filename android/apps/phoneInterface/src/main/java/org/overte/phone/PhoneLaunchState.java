package org.overte.phone;

/** Framework-independent state for the permission launcher hand-off. */
final class PhoneLaunchState {
    private String pendingUrl;
    private boolean interfaceLaunched;

    PhoneLaunchState(String pendingUrl, boolean interfaceLaunched) {
        this.pendingUrl = PhoneDeepLinkNormalizer.normalize(pendingUrl);
        this.interfaceLaunched = interfaceLaunched;
    }

    String pendingUrl() {
        return pendingUrl;
    }

    boolean interfaceLaunched() {
        return interfaceLaunched;
    }

    void replacePendingUrl(String pendingUrl) {
        this.pendingUrl = PhoneDeepLinkNormalizer.normalize(pendingUrl);
    }

    /** Returns true exactly once, when the native interface should be started. */
    boolean beginInterfaceLaunch() {
        if (interfaceLaunched) {
            return false;
        }
        interfaceLaunched = true;
        return true;
    }
}
