// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;

import static org.junit.Assert.*;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.webkit.WebChromeClient;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.overte.web.EmbeddedWebHost;
import org.overte.web.EmbeddedWebView;
import org.qtproject.qt5.android.QtNative;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.Implementation;
import org.robolectric.annotation.Implements;
import org.robolectric.annotation.LooperMode;
import org.robolectric.Shadows;

/** Actual Phone Activity/Host dispatch; Qt/JNI and native WebView effects are explicit observation boundaries. */
@RunWith(RobolectricTestRunner.class)
@LooperMode(LooperMode.Mode.PAUSED)
@Config(sdk = 35, manifest = Config.NONE, instrumentedPackages = {"org.overte.web", "org.overte.phone", "org.qtproject.qt5.android"},
        shadows = {PhoneEmbeddedWebFocusRobolectricTest.QtOwner.class, PhoneEmbeddedWebFocusRobolectricTest.WebDispatch.class, PhoneEmbeddedWebFocusRobolectricTest.NativeLibraries.class})
public final class PhoneEmbeddedWebFocusRobolectricTest {
    @Implements(value = PhoneInterfaceActivity.class, isInAndroidSdk = false)
    public static class NativeLibraries extends org.robolectric.shadows.ShadowActivity {
        // Android OpenSSL/Qt native loading is not available on the host. The
        // production initializer and its package/source policies stay unchanged.
        @Implementation protected static void __staticInitializer__() { }
    }
    @Implements(QtNative.class)
    public static class QtOwner {
        static Activity owner;
        @Implementation protected static Activity activity() { return owner; }
    }
    // The class being shadowed is compiled from the real SHA-bound parent source,
    // including setInputFocused; no substitute API class is used for compilation.
    @Implements(value = EmbeddedWebView.class, isInAndroidSdk = false)
    public static class WebDispatch {
        static int foregrounds, inputs, detaches;
        static boolean foreground, focused;
        @Implementation protected static void initialize(EmbeddedWebHost owner) { }
        @Implementation protected static void setForeground(EmbeddedWebHost owner, boolean value) { foregrounds++; foreground = value; }
        @Implementation protected static void setInputFocused(EmbeddedWebHost owner, boolean value) { inputs++; focused = value; }
        @Implementation protected static void relayout(EmbeddedWebHost owner) { }
        @Implementation protected static void detach(EmbeddedWebHost owner) { detaches++; }
    }
    @org.junit.Rule public org.junit.rules.TemporaryFolder temporary = new org.junit.rules.TemporaryFolder();
    ActivityController<PhoneInterfaceActivity> controller;
    PhoneInterfaceActivity activity;
    PhoneEmbeddedWebHost host;
    @Before public void start() throws Exception {
        WebDispatch.foregrounds = WebDispatch.inputs = WebDispatch.detaches = 0;
        controller = Robolectric.buildActivity(PhoneInterfaceActivity.class);
        java.io.File fixture = temporary.newFile("focus-assets.zip");
        try (java.util.zip.ZipOutputStream output = new java.util.zip.ZipOutputStream(new java.io.FileOutputStream(fixture))) {
            output.putNextEntry(new java.util.zip.ZipEntry("assets/cache_assets.txt"));
            output.write("1\n".getBytes(java.nio.charset.StandardCharsets.UTF_8)); output.closeEntry();
        }
        Integer cookie = org.robolectric.util.ReflectionHelpers.callInstanceMethod(
            controller.get().getAssets(), "addAssetPath",
            org.robolectric.util.ReflectionHelpers.ClassParameter.from(String.class, fixture.getAbsolutePath()));
        assertTrue(cookie > 0);
        try (java.io.InputStream input = controller.get().getAssets().open("cache_assets.txt")) { assertEquals('1', input.read()); }
        controller.create().start().resume().visible();
        activity = controller.get(); QtOwner.owner = activity;
        Field field = PhoneInterfaceActivity.class.getDeclaredField("embeddedWebHost"); field.setAccessible(true);
        host = (PhoneEmbeddedWebHost) field.get(activity);
        // The real native-ready JNI boundary is not initialized by Robolectric.
        Field ready = PhoneEmbeddedWebHost.class.getDeclaredField("initialized"); ready.setAccessible(true); ready.setBoolean(host, true);
        controller.windowFocusChanged(true); WebDispatch.foregrounds = WebDispatch.inputs = 0;
    }
    @Test public void windowFocusInvalidatesInputWithoutMediaLifecycleDispatch() {
        int transitions = WebDispatch.foregrounds;
        controller.windowFocusChanged(false);
        assertTrue(host.isForeground()); assertFalse(WebDispatch.focused); assertEquals(1, WebDispatch.inputs);
        assertEquals(transitions, WebDispatch.foregrounds);
        controller.windowFocusChanged(true);
        assertTrue(WebDispatch.focused); assertEquals(transitions, WebDispatch.foregrounds);
    }
    @Test public void actualPauseAndDestroyRetainBackgroundAndDetachDispatch() {
        controller.pause(); assertFalse(host.isForeground()); assertFalse(WebDispatch.foreground);
        int paused = WebDispatch.foregrounds; assertTrue(paused > 0);
        controller.stop().destroy(); assertTrue(WebDispatch.foregrounds > paused); assertEquals(1, WebDispatch.detaches);
    }
    @Test public void focusWhilePausedCannotAuthorizeInput() {
        controller.pause(); int transitions = WebDispatch.foregrounds;
        controller.windowFocusChanged(true);
        assertFalse(host.isForeground()); assertFalse(WebDispatch.focused);
        assertEquals(transitions, WebDispatch.foregrounds);
    }
    @Test public void staleActivityCallbacksCannotDispatchOrConsumePicker() {
        QtOwner.owner = new Activity(); int f = WebDispatch.foregrounds, i = WebDispatch.inputs;
        host.windowFocus(); host.foreground(true);
        assertFalse(host.isForeground()); assertEquals(f, WebDispatch.foregrounds); assertEquals(i, WebDispatch.inputs);
        assertFalse(host.chooseFiles(value -> fail("stale picker"), picker()));
        assertFalse(host.fileResult(19, Activity.RESULT_OK, new Intent().setData(Uri.parse("content://fixture/item"))));
    }
    @Test public void pickerEntryAndReturnRequireActualFocusWithoutSuspendingMedia() {
        List<Uri[]> results = new ArrayList<>(); controller.windowFocusChanged(false);
        assertFalse(host.chooseFiles(results::add, picker())); assertTrue(host.isForeground());
        controller.windowFocusChanged(true); assertTrue(host.chooseFiles(results::add, picker()));
        int code = Shadows.shadowOf(activity).getNextStartedActivityForResult().requestCode;
        controller.windowFocusChanged(false); int transitions = WebDispatch.foregrounds;
        assertTrue(host.fileResult(code, Activity.RESULT_OK, new Intent().setData(Uri.parse("content://fixture/item"))));
        assertTrue(results.isEmpty()); assertEquals(transitions, WebDispatch.foregrounds);
        controller.windowFocusChanged(true); assertEquals(1, results.size()); assertEquals("content", results.get(0)[0].getScheme());
        host.windowFocus(); assertEquals(1, results.size());
    }
    @Test public void staleOwnerCannotDeliverAnActuallyPendingSelection() {
        List<Uri[]> results = new ArrayList<>(); assertTrue(host.chooseFiles(results::add, picker()));
        int code = Shadows.shadowOf(activity).getNextStartedActivityForResult().requestCode;
        QtOwner.owner = new Activity();
        assertFalse(host.fileResult(code, Activity.RESULT_OK, new Intent().setData(Uri.parse("content://fixture/stale"))));
        assertTrue(results.isEmpty()); host.detach(); assertEquals(1, results.size()); assertNull(results.get(0));
    }
    @Test public void resumedActivityRetainsMediaForegroundWithoutWindowFocus() {
        controller.windowFocusChanged(false); controller.pause(); assertFalse(host.isForeground());
        controller.resume(); assertTrue(host.isForeground()); assertTrue(WebDispatch.foreground);
    }
    static WebChromeClient.FileChooserParams picker() {
        return new WebChromeClient.FileChooserParams() {
            public int getMode() { return MODE_OPEN; }
            public String[] getAcceptTypes() { return new String[]{"image/png"}; }
            public boolean isCaptureEnabled() { return false; }
            public CharSequence getTitle() { return "Select file"; }
            public String getFilenameHint() { return null; }
            public Intent createIntent() { return new Intent(Intent.ACTION_OPEN_DOCUMENT); }
        };
    }
}
