// Test-only current Activity/OS permission observation, no Qt or physical device.
package org.overte.pico;
public final class PicoInterfaceActivity {
    static volatile boolean granted = true, present = true, permissionFailure;
    private static final PicoInterfaceActivity INSTANCE = new PicoInterfaceActivity();
    static PicoInterfaceActivity getInstance() { return present ? INSTANCE : null; }
    public int checkSelfPermission(String permission) {
        if (permissionFailure) throw new SecurityException("PRIVATE_TEST_CANARY");
        return granted ? 0 : -1;
    }
}
