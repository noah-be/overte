package org.overte.phone;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.os.Build;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.Arrays;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

@RunWith(AndroidJUnit4.class)
public class EmulatorPackagingTest {
    @Test
    public void emulatorRunsX86_64PackageWithNativeInterface() throws Exception {
        Context target = InstrumentationRegistry.getInstrumentation().getTargetContext();

        assertEquals("org.overte.phone", target.getPackageName());
        assertTrue("The emulator must advertise x86_64 as a supported ABI",
                Arrays.asList(Build.SUPPORTED_ABIS).contains("x86_64"));

        try (ZipFile apk = new ZipFile(target.getApplicationInfo().sourceDir)) {
            ZipEntry nativeInterface = apk.getEntry("lib/x86_64/libphoneInterface.so");
            assertTrue("The installed APK must contain the x86_64 native interface",
                    nativeInterface != null && nativeInterface.getSize() > 0);
        }
    }
}
