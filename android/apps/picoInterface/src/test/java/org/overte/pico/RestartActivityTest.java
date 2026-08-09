package org.overte.pico;

import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

import android.content.Context;
import android.content.Intent;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;

@RunWith(RobolectricTestRunner.class)
public class RestartActivityTest {
    private Context context;

    @Before
    public void setUp() {
        context = RuntimeEnvironment.getApplication();
        RestartArguments.clear(context);
    }

    @Test
    public void forwardsStoredArgumentsAndFinishes() {
        RestartArguments.store(context, "--display=OpenXR --url hifi://test");
        RestartActivity activity = Robolectric.buildActivity(RestartActivity.class).create().get();
        Intent started = shadowOf(activity).getNextStartedActivity();
        assertEquals(PicoInterfaceActivity.class.getName(), started.getComponent().getClassName());
        assertEquals("--display=OpenXR --url hifi://test",
            started.getStringExtra("applicationArguments"));
        assertTrue(activity.isFinishing());
        assertNull(RestartArguments.consume(context));
    }

    @Test
    public void omitsEmptyArguments() {
        RestartArguments.store(context, "");
        RestartActivity activity = Robolectric.buildActivity(RestartActivity.class).create().get();
        Intent started = shadowOf(activity).getNextStartedActivity();
        assertFalse(started.hasExtra("applicationArguments"));
    }
}
