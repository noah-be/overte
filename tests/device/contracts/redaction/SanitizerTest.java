// SPDX-License-Identifier: Apache-2.0
import org.overte.security.SafeDiagnostics;
public final class SanitizerTest {
    private static void check(boolean value) { if (!value) { throw new AssertionError("redaction contract"); } }
    public static void main(String[] args) {
        String[] raw = {null,"","canary-secret-7824","Bearer canary-secret-7824",
            "https://private.invalid/?token=canary-secret-7824","Y2FuYXJ5LXNlY3JldC03ODI0",
            "%63%61%6e%61%72%79-secret-7824","canary-","secret-","7824","F2C: ca L2C: 24",
            "user=canary-user","session=canary-session","device=canary-device",
            "OVT_AUTH_FAILED canary-secret-7824","OVT_AUTH_FAILED\n","OVT_AUTH_FAILED\0secret",
            "{broken","NSError private.invalid","file:///private/canary-user"};
        for (String value : raw) { for (int sink=0;sink<7;sink++) {
            check(SafeDiagnostics.sanitize(value).equals("OVT_REDACTED"));
        } }
        for (SafeDiagnostics.Event event : SafeDiagnostics.Event.values()) {
            check(SafeDiagnostics.sanitize(SafeDiagnostics.event(event)).equals(SafeDiagnostics.event(event)));
        }
        check(SafeDiagnostics.event(null).equals("OVT_REDACTED"));
        System.out.println("PX-16 Java closed-event adapter conformance PASS");
    }
}
