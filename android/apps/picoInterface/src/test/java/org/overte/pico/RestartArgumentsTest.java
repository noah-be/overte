package org.overte.pico;

import static org.junit.Assert.*;

import android.content.Context;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;

@RunWith(RobolectricTestRunner.class)
public class RestartArgumentsTest {
    private Context context;

    @Before
    public void setUp() {
        context = RuntimeEnvironment.getApplication();
        RestartArguments.clear(context);
    }

    @Test
    public void valuesAreConsumedExactlyOnce() {
        assertTrue(RestartArguments.store(context, "--url hifi://example"));
        assertEquals("--url hifi://example", RestartArguments.consume(context));
        assertNull(RestartArguments.consume(context));
    }

    @Test
    public void nullIsStoredAsEmptyAndClearIsIdempotent() {
        assertTrue(RestartArguments.store(context, null));
        assertEquals("", RestartArguments.consume(context));
        assertTrue(RestartArguments.clear(context));
        assertNull(RestartArguments.consume(context));
    }
}
