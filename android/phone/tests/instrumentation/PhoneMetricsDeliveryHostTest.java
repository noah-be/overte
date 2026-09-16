package org.overte.phone;

public final class PhoneMetricsDeliveryHostTest {
    private static int checks;
    private static void check(boolean ok) {
        checks++;
        if (!ok) {
            throw new AssertionError("metrics delivery check " + checks);
        }
    }
    private static PhoneTouchUiMetricsPolicy.Snapshot snapshot(int ime) {
        return PhoneTouchUiMetricsPolicy.normalize(
                1600, 2560, 0, 24, 0, 96, ime,
                2.0f, 1.0f, false, false, true);
    }
    public static void main(String[] args) {
        PhoneTouchUiMetricsPolicy.Delivery delivery = new PhoneTouchUiMetricsPolicy.Delivery();
        PhoneTouchUiMetricsPolicy.Snapshot closed = snapshot(0);
        PhoneTouchUiMetricsPolicy.Snapshot open = snapshot(720);
        check(delivery.pending() == null);
        check(delivery.offer(closed));
        check(delivery.pending().equals(closed));
        delivery.accepted(closed);
        check(delivery.pending() == null);
        check(delivery.offer(open));
        check(delivery.pending().keyboardVisible);
        // IME closed again before the native runtime accepted the open event.
        check(delivery.offer(closed));
        check(delivery.pending() == null);
        check(!delivery.offer(closed));
        check(delivery.offer(open));
        check(!delivery.offer(snapshot(720))); // no unnecessary retry reset
        delivery.accepted(open);
        check(delivery.pending() == null);
        check(delivery.offer(closed));
        delivery.dropPending(); // bounded attempt expired
        check(delivery.pending() == null);
        check(delivery.offer(closed)); // later layout retries the current state
        delivery.accepted(closed);
        PhoneTouchUiMetricsPolicy.Snapshot invalid = PhoneTouchUiMetricsPolicy.normalize(
                0, 0, 0, 0, 0, 0, 0, 1, 1, false, false, false);
        check(!delivery.offer(invalid));
        check(delivery.pending() == null);
        System.out.println("Phone metrics delivery: " + checks + " assertions PASS");
    }
}
