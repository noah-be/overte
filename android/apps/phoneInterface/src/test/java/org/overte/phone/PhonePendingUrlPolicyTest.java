package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class PhonePendingUrlPolicyTest {
    @Test
    public void attemptRequiresBothPendingUrlAndResumedActivity() {
        assertFalse(PhonePendingUrlPolicy.canAttempt(null, false));
        assertFalse(PhonePendingUrlPolicy.canAttempt(null, true));
        assertFalse(PhonePendingUrlPolicy.canAttempt("hifi://pending", false));
        assertTrue(PhonePendingUrlPolicy.canAttempt("hifi://pending", true));
    }

    @Test
    public void failedAttemptRetriesOnlyWhileForegroundedAndBelowLimit() {
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.RETRY,
                PhonePendingUrlPolicy.afterFailedAttempt(true, 1, 300));
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.RETRY,
                PhonePendingUrlPolicy.afterFailedAttempt(true, 299, 300));
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.DROP,
                PhonePendingUrlPolicy.afterFailedAttempt(true, 300, 300));
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.DROP,
                PhonePendingUrlPolicy.afterFailedAttempt(true, 301, 300));
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.DROP,
                PhonePendingUrlPolicy.afterFailedAttempt(false, 1, 300));
    }

    @Test
    public void nonPositiveRetryBudgetCannotScheduleAnotherAttempt() {
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.DROP,
                PhonePendingUrlPolicy.afterFailedAttempt(true, 0, 0));
        assertEquals(PhonePendingUrlPolicy.FailedAttemptAction.DROP,
                PhonePendingUrlPolicy.afterFailedAttempt(true, 0, -1));
    }
}
