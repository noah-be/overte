package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.SystemClock;

import androidx.lifecycle.Lifecycle;
import androidx.test.core.app.ActivityScenario;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.rule.GrantPermissionRule;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry;
import androidx.test.runner.lifecycle.Stage;

import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.concurrent.atomic.AtomicReference;

/** Exercises the real launcher-to-Qt boundary without intercepting its Intent. */
@RunWith(AndroidJUnit4.class)
public final class PhoneColdLaunchInstrumentedTest {
    private static final long STARTUP_TIMEOUT_MS = 30_000;
    private static final long STABILITY_WINDOW_MS = 2_000;

    @Rule
    public final GrantPermissionRule microphonePermission =
            GrantPermissionRule.grant(Manifest.permission.RECORD_AUDIO);

    @Test
    public void launcherStartsAndKeepsRealNativeActivityResumed() {
        Context context = ApplicationProvider.getApplicationContext();
        Intent intent = new Intent(Intent.ACTION_MAIN)
                .setClass(context, PermissionsActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);

        try (ActivityScenario<PermissionsActivity> launcher = ActivityScenario.launch(intent)) {
            PhoneInterfaceActivity first = waitForResumedInterface(STARTUP_TIMEOUT_MS);
            assertNotNull("PhoneInterfaceActivity did not reach RESUMED", first);
            assertEquals(context.getPackageName(), first.getPackageName());
            assertFalse(first.isFinishing());
            assertEquals(Lifecycle.State.DESTROYED, launcher.getState());

            SystemClock.sleep(STABILITY_WINDOW_MS);
            PhoneInterfaceActivity stable = waitForResumedInterface(1_000);
            assertNotNull("PhoneInterfaceActivity did not survive the stability window", stable);
            assertFalse(stable.isFinishing());
        }
    }

    private static PhoneInterfaceActivity waitForResumedInterface(long timeoutMs) {
        long deadline = SystemClock.uptimeMillis() + timeoutMs;
        do {
            AtomicReference<PhoneInterfaceActivity> result = new AtomicReference<>();
            InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
                for (Activity activity : ActivityLifecycleMonitorRegistry.getInstance()
                        .getActivitiesInStage(Stage.RESUMED)) {
                    if (activity instanceof PhoneInterfaceActivity) {
                        result.set((PhoneInterfaceActivity) activity);
                        break;
                    }
                }
            });
            if (result.get() != null) {
                return result.get();
            }
            SystemClock.sleep(100);
        } while (SystemClock.uptimeMillis() < deadline);
        return null;
    }
}
