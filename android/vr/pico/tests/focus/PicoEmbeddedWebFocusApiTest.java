// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.pico;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebChromeClient;
import java.lang.reflect.Method;
import java.util.ArrayList;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.qtproject.qt5.android.bindings.QtActivity;
import org.qtproject.qt5.android.QtNative;
import org.overte.web.EmbeddedWebView;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.Implementation;
import org.robolectric.annotation.Implements;
import org.robolectric.annotation.RealObject;
import org.robolectric.shadow.api.Shadow;
import org.robolectric.util.ReflectionHelpers;
import static org.robolectric.util.ReflectionHelpers.ClassParameter.from;
import static org.junit.Assert.*;

/** Execute production Activity/host and shared public Java callers; native engines are boundaries. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk={26,35}, manifest=Config.NONE,
    instrumentedPackages={"org.overte.pico","org.overte.web","org.qtproject.qt5.android.bindings"},
    shadows={PicoEmbeddedWebFocusApiTest.NativeBootstrap.class,
             PicoEmbeddedWebFocusApiTest.HostNativeBoundary.class,
             PicoEmbeddedWebFocusApiTest.QtLifecycleBoundary.class,
             PicoEmbeddedWebFocusApiTest.SharedNativeBoundary.class,
             PicoEmbeddedWebFocusApiTest.AudioNativeBoundary.class})
public final class PicoEmbeddedWebFocusApiTest {
    @Implements(value=PicoInterfaceActivity.class, isInAndroidSdk=false)
    public static final class NativeBootstrap extends QtLifecycleBoundary {
        @RealObject PicoInterfaceActivity activity;
        @Implementation protected static void __staticInitializer__() {
            // Native Qt/OpenXR library loading is outside Robolectric. Keep the
            // actual production ownership policy, not a substituted Activity API.
            ReflectionHelpers.setStaticField(PicoInterfaceActivity.class,"INSTANCE",
                new PicoActivityInstancePolicy<PicoInterfaceActivity>());
        }
        @Implementation protected void onCreate(Bundle state) {
            Shadow.directlyOn(activity, Activity.class,"onCreate",from(Bundle.class,state));
            PicoActivityInstancePolicy<PicoInterfaceActivity> policy=
                ReflectionHelpers.getStaticField(PicoInterfaceActivity.class,"INSTANCE");
            policy.register(activity);
            QtNative.setActivity(activity,null);
            PicoEmbeddedWebHost host=new PicoEmbeddedWebHost(activity);
            ReflectionHelpers.setField(activity,"embeddedWeb",host);
            host.initialize();
        }
        @Implementation protected void releaseOpenXRActivity() { }
    }
    @Implements(value=QtActivity.class, isInAndroidSdk=false)
    public static class QtLifecycleBoundary extends org.robolectric.shadows.ShadowActivity {
        @RealObject QtActivity activity;
        @Implementation protected void onResume() { Shadow.directlyOn(activity,Activity.class,"onResume"); }
        @Implementation protected void onPause() { Shadow.directlyOn(activity,Activity.class,"onPause"); }
        @Implementation protected void onDestroy() { Shadow.directlyOn(activity,Activity.class,"onDestroy"); }
        @Implementation protected void onWindowFocusChanged(boolean focused) {
            Shadow.directlyOn(activity,Activity.class,"onWindowFocusChanged",from(boolean.class,focused));
        }
    }
    @Implements(value=PicoEmbeddedWebHost.class, isInAndroidSdk=false)
    public static final class HostNativeBoundary {
        @Implementation protected static void nativePrepareWeb(String directory) { }
    }
    @Implements(value=EmbeddedWebView.class, isInAndroidSdk=false)
    public static final class SharedNativeBoundary {
        static int transitions; static boolean foreground;
        @Implementation protected static void nativeInitialize() { }
        @Implementation protected static void nativeForeground(boolean active) {
            ++transitions;foreground=active;
        }
    }
    @Implements(value=PicoAudioLifecycle.class, isInAndroidSdk=false)
    public static final class AudioNativeBoundary {
        @Implementation protected static void foreground(boolean active) { }
        @Implementation protected static boolean begin(boolean permission) { return false; }
        @Implementation protected static boolean mayCapture() { return false; }
        @Implementation protected static void revoke() { }
        @Implementation protected static void invalidate() { }
        @Implementation protected static void failed() { }
        @Implementation protected static void stopCompleted(boolean success) { }
    }
    private ActivityController<PicoInterfaceActivity> create() {
        return Robolectric.buildActivity(PicoInterfaceActivity.class).create().start().resume().visible();
    }
    private PicoEmbeddedWebHost host(PicoInterfaceActivity activity) {
        return ReflectionHelpers.getField(activity,"embeddedWeb");
    }
    private Object ticket() { return ReflectionHelpers.callInstanceMethod(
        ReflectionHelpers.getStaticField(EmbeddedWebView.class,"INPUT"),"capture"); }
    private boolean permits(Object ticket,PicoEmbeddedWebHost host) throws Exception {
        Object gate=ReflectionHelpers.getStaticField(EmbeddedWebView.class,"INPUT");
        Method method=gate.getClass().getDeclaredMethod("permits",ticket.getClass(),Object.class);
        method.setAccessible(true);return (Boolean)method.invoke(gate,ticket,host);
    }
    @Test
    public void real_activity_focus_loss_revokes_input_without_foreground_transition() throws Exception {
        ActivityController<PicoInterfaceActivity> c=create();PicoInterfaceActivity activity=c.get();
        c.windowFocusChanged(true);assertTrue(activity.hasWindowFocus());
        PicoEmbeddedWebHost host=host(activity);assertTrue(host.isForeground());
        Object before=ticket();assertNotNull(before);
        int transitions=SharedNativeBoundary.transitions;
        c.windowFocusChanged(false);
        assertFalse(activity.hasWindowFocus());assertTrue(host.isForeground());
        assertEquals(transitions,SharedNativeBoundary.transitions);
        assertTrue(SharedNativeBoundary.foreground);assertNull(ticket());assertFalse(permits(before,host));
        c.windowFocusChanged(true);
        assertTrue(host.isForeground());assertNotNull(ticket());assertFalse(permits(before,host));
        assertEquals(transitions,SharedNativeBoundary.transitions);
        c.pause();assertFalse(host.isForeground());assertFalse(SharedNativeBoundary.foreground);assertNull(ticket());
        c.resume();assertTrue(host.isForeground());assertTrue(SharedNativeBoundary.foreground);
        c.pause().stop().destroy();assertFalse(host.isForeground());
    }
    @Test
    public void resume_without_focus_and_stale_owner_cannot_admit_input_or_picker() {
        ActivityController<PicoInterfaceActivity> c=create();c.windowFocusChanged(false);
        PicoEmbeddedWebHost old=host(c.get());assertTrue(old.isForeground());assertNull(ticket());
        assertFalse(old.openExternal(Uri.parse("https://example.invalid/")));
        assertFalse(old.chooseFiles(values->{throw new AssertionError("unfocused chooser admitted");},new Choice()));
        ActivityController<PicoInterfaceActivity> replacement=create();replacement.windowFocusChanged(true);
        PicoEmbeddedWebHost current=host(replacement.get());assertTrue(current.isForeground());assertNotNull(ticket());
        int transitions=SharedNativeBoundary.transitions;
        old.foreground(true);old.windowFocus();
        assertFalse(old.isForeground());assertEquals(transitions,SharedNativeBoundary.transitions);
        assertFalse(old.chooseFiles(values->{throw new AssertionError("stale chooser admitted");},new Choice()));
        old.detach();assertTrue(current.isForeground());assertNotNull(ticket());
        replacement.pause().stop().destroy();
    }
    @Test
    public void native_picker_result_waits_for_actual_focus_and_same_resumed_owner() {
        ActivityController<PicoInterfaceActivity> c=create();c.windowFocusChanged(true);
        PicoInterfaceActivity activity=c.get();PicoEmbeddedWebHost host=host(activity);
        ArrayList<Uri[]> delivered=new ArrayList<>();assertTrue(host.chooseFiles(delivered::add,new Choice()));
        org.robolectric.shadows.ShadowActivity.IntentForResult started=
            Shadows.shadowOf(activity).getNextStartedActivityForResult();
        assertNotNull(started);assertEquals(Intent.ACTION_OPEN_DOCUMENT,started.intent.getAction());
        c.windowFocusChanged(false);
        Uri selected=Uri.parse("content://provider/selected-model.glb");
        activity.onActivityResult(started.requestCode,Activity.RESULT_OK,new Intent().setData(selected));
        assertTrue(delivered.isEmpty());assertTrue(host.isForeground());
        c.pause();c.windowFocusChanged(true);assertTrue(delivered.isEmpty());assertFalse(host.isForeground());
        c.resume();assertEquals(1,delivered.size());assertArrayEquals(new Uri[]{selected},delivered.get(0));
        host.windowFocus();assertEquals(1,delivered.size());
        assertFalse(host.fileResult(started.requestCode,Activity.RESULT_OK,new Intent().setData(selected)));
        c.pause().stop().destroy();
    }
    @Test
    public void replaced_owner_never_delivers_retained_picker_data_to_the_new_activity() {
        ActivityController<PicoInterfaceActivity> first=create();first.windowFocusChanged(true);
        PicoEmbeddedWebHost old=host(first.get());ArrayList<Uri[]> delivered=new ArrayList<>();
        assertTrue(old.chooseFiles(delivered::add,new Choice()));
        org.robolectric.shadows.ShadowActivity.IntentForResult started=
            Shadows.shadowOf(first.get()).getNextStartedActivityForResult();
        ActivityController<PicoInterfaceActivity> next=create();next.windowFocusChanged(true);
        PicoEmbeddedWebHost current=host(next.get());assertFalse(old.isForeground());
        Uri selected=Uri.parse("content://provider/obsolete-selection.glb");
        first.get().onActivityResult(started.requestCode,Activity.RESULT_OK,new Intent().setData(selected));
        old.windowFocus();old.foreground(true);assertTrue(delivered.isEmpty());
        assertTrue(current.isForeground());Object ticket=ticket();assertNotNull(ticket);
        old.detach();assertEquals(1,delivered.size());assertNull(delivered.get(0));
        assertTrue(current.isForeground());assertNotNull(ticket());
        assertFalse(old.fileResult(started.requestCode,Activity.RESULT_OK,new Intent().setData(selected)));
        next.pause().stop().destroy();
    }
    @Test
    public void qt_owner_change_denies_positive_calls_but_pause_still_reaches_current_common_host() {
        ActivityController<PicoInterfaceActivity> first=create();first.windowFocusChanged(true);
        PicoEmbeddedWebHost old=host(first.get());ArrayList<Uri[]> delivered=new ArrayList<>();
        assertTrue(old.chooseFiles(delivered::add,new Choice()));
        org.robolectric.shadows.ShadowActivity.IntentForResult started=
            Shadows.shadowOf(first.get()).getNextStartedActivityForResult();
        // Qt can replace its Activity before Pico's registry/common host changes.
        // Use the real Qt setter rather than a substitute ownership API.
        Activity successor=Robolectric.buildActivity(Activity.class).create().get();
        QtNative.setActivity(successor,null);
        assertSame(first.get(),PicoInterfaceActivity.getInstance());
        assertFalse(old.isForeground());
        assertFalse(old.chooseFiles(values->{throw new AssertionError("obsolete Qt owner admitted");},new Choice()));
        assertFalse(old.openExternal(Uri.parse("https://example.invalid/")));
        first.windowFocusChanged(true);assertNull(ticket());
        first.get().onActivityResult(started.requestCode,Activity.RESULT_OK,
            new Intent().setData(Uri.parse("content://provider/old-qt-owner.glb")));
        assertTrue(delivered.isEmpty());
        int transitions=SharedNativeBoundary.transitions;
        first.pause();assertEquals(transitions+1,SharedNativeBoundary.transitions);
        assertFalse(SharedNativeBoundary.foreground);assertNull(ticket());
        first.resume();assertFalse(SharedNativeBoundary.foreground);assertTrue(delivered.isEmpty());
        first.pause().stop().destroy();
        assertEquals(1,delivered.size());assertNull(delivered.get(0));
        assertFalse(SharedNativeBoundary.foreground);
    }
    private static final class Choice extends WebChromeClient.FileChooserParams {
        @Override public int getMode(){return MODE_OPEN;}
        @Override public String[] getAcceptTypes(){return new String[]{".glb"};}
        @Override public boolean isCaptureEnabled(){return false;}
        @Override public CharSequence getTitle(){return "Choose a model";}
        @Override public String getFilenameHint(){return null;}
        @Override public Intent createIntent(){return new Intent(Intent.ACTION_OPEN_DOCUMENT);}
    }
}
