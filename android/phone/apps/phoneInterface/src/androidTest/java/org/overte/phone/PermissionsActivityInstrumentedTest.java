package org.overte.phone;

import static androidx.test.espresso.intent.Intents.intended;
import static androidx.test.espresso.intent.Intents.intending;
import static androidx.test.espresso.intent.matcher.IntentMatchers.hasComponent;
import static androidx.test.espresso.intent.matcher.IntentMatchers.hasExtra;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.anything;
import static org.hamcrest.Matchers.not;

import android.Manifest;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

import androidx.test.core.app.ActivityScenario;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.espresso.intent.Intents;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.rule.GrantPermissionRule;

import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public final class PermissionsActivityInstrumentedTest {
    @Rule
    public final GrantPermissionRule microphonePermission =
            GrantPermissionRule.grant(Manifest.permission.RECORD_AUDIO);

    @Before
    public void initializeIntentCapture() {
        Intents.init();
        intending(hasComponent(PhoneInterfaceActivity.class.getName())).respondWith(
                new Instrumentation.ActivityResult(Activity.RESULT_OK, null));
    }

    @After
    public void releaseIntentCapture() {
        Intents.release();
    }

    @Test
    public void coldDeepLinkLaunchesNativeActivityWithCanonicalInternalExtra() {
        try (ActivityScenario<PermissionsActivity> ignored = launch(
                new Intent(Intent.ACTION_VIEW, Uri.parse("overte://example.com/a%20b")))) {
            intended(allOf(
                    hasComponent(PhoneInterfaceActivity.class.getName()),
                    hasExtra(PhoneDeepLink.EXTRA_URL, "hifi://example.com/a%20b")));
        }
    }

    @Test
    public void ordinaryLauncherIntentDoesNotInventADeepLinkExtra() {
        try (ActivityScenario<PermissionsActivity> ignored = launch(
                new Intent(Intent.ACTION_MAIN))) {
            intended(allOf(
                    hasComponent(PhoneInterfaceActivity.class.getName()),
                    not(hasExtra(PhoneDeepLink.EXTRA_URL, anything()))));
        }
    }

    @Test
    public void unsupportedExternalSchemeDoesNotReachNativeActivity() {
        try (ActivityScenario<PermissionsActivity> ignored = launch(
                new Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com")))) {
            intended(allOf(
                    hasComponent(PhoneInterfaceActivity.class.getName()),
                    not(hasExtra(PhoneDeepLink.EXTRA_URL, anything()))));
        }
    }

    private static ActivityScenario<PermissionsActivity> launch(Intent input) {
        Context context = ApplicationProvider.getApplicationContext();
        input.setClass(context, PermissionsActivity.class);
        input.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return ActivityScenario.launch(input);
    }
}
