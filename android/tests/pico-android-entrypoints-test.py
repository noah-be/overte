#!/usr/bin/env python3
"""Device-free security contracts for Pico Android entry points."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
JAVA = ROOT / "android/apps/picoInterface/src/main/java/org/overte/pico"
MANIFEST = ROOT / "android/apps/picoInterface/src/main/AndroidManifest.xml"
WINDOW = ROOT / "interface/src/scripting/WindowScriptingInterface.cpp"
ANDROID = "{http://schemas.android.com/apk/res/android}"


class AndroidEntrypointsTest(unittest.TestCase):
    def test_internal_qt_activity_is_not_exported(self):
        root = ET.parse(MANIFEST).getroot()
        activities = {
            item.attrib[ANDROID + "name"]: item
            for item in root.findall("./application/activity")
        }
        self.assertEqual(
            activities[".PicoInterfaceActivity"].attrib[ANDROID + "exported"],
            "false",
        )
        self.assertEqual(
            activities[".PermissionsActivity"].attrib[ANDROID + "exported"],
            "true",
        )
        self.assertEqual(
            activities[".RestartActivity"].attrib[ANDROID + "exported"],
            "false",
        )

    def test_exported_launcher_does_not_accept_argument_strings(self):
        permissions = (JAVA / "PermissionsActivity.java").read_text(encoding="utf-8")
        self.assertNotIn('getStringExtra("args")', permissions)
        self.assertNotIn("RestartArguments", permissions)
        self.assertNotIn("getIntent()", permissions)

    def test_permission_activity_preserves_launch_state_only(self):
        permissions = (JAVA / "PermissionsActivity.java").read_text(encoding="utf-8")
        self.assertIn("onSaveInstanceState(Bundle outState)", permissions)
        self.assertNotIn("applicationArguments", permissions)
        self.assertGreaterEqual(permissions.count("if (interfaceLaunched)"), 2)
        self.assertIn("interfaceLaunched = true", permissions)

    def test_restart_arguments_are_private_and_not_logged(self):
        activity = (JAVA / "PicoInterfaceActivity.java").read_text(encoding="utf-8")
        storage = (JAVA / "RestartArguments.java").read_text(encoding="utf-8")
        restart = (JAVA / "RestartActivity.java").read_text(encoding="utf-8")
        self.assertIn("RestartArguments.store(activity, applicationArguments)", activity)
        self.assertIn("new Intent(activity, RestartActivity.class)", activity)
        self.assertNotIn('putExtra("args", applicationArguments)', activity)
        self.assertNotIn('"Scheduling application restart with arguments:', activity)
        self.assertIn("Context.MODE_PRIVATE", storage)
        self.assertIn(".remove(KEY_ARGUMENTS)", storage)
        self.assertIn(".remove(KEY_ARGUMENTS).commit() ? arguments : null", storage)
        self.assertIn("static boolean clear(Context context)", storage)
        self.assertIn("RestartArguments.consume(this)", restart)
        self.assertIn("new Intent(this, PicoInterfaceActivity.class)", restart)

    def test_restart_scheduling_failure_clears_private_handoff(self):
        activity = (JAVA / "PicoInterfaceActivity.java").read_text(encoding="utf-8")
        schedule = activity.index("public static void scheduleRestart")
        finish = activity.index("activity.finishAffinity()", schedule)
        body = activity[schedule:finish]
        self.assertIn("if (alarmManager == null)", body)
        self.assertIn("catch (RuntimeException exception)", body)
        self.assertGreaterEqual(body.count("RestartArguments.clear(activity)"), 2)
        catch = body.index("catch (RuntimeException exception)")
        clear = body.index("RestartArguments.clear(activity)", catch)
        failed_return = body.index("return;", clear)
        self.assertLess(catch, clear)
        self.assertLess(clear, failed_return)

    def test_qt_activity_releases_static_android_resources(self):
        activity = (JAVA / "PicoInterfaceActivity.java").read_text(encoding="utf-8")
        webview = (JAVA / "OffscreenWebView.java").read_text(encoding="utf-8")
        self.assertIn("protected void onDestroy()", activity)
        self.assertIn("OffscreenWebView.destroyAll()", activity)
        self.assertIn("AndroidAudioInput.stop()", activity)
        self.assertIn("releaseOpenXRActivity()", activity)
        self.assertIn("instance = null", activity)
        self.assertIn("private static volatile PicoInterfaceActivity instance", activity)
        destroy = activity.index("protected void onDestroy()")
        clear = activity.index("instance = null", destroy)
        web_cleanup = activity.index("OffscreenWebView.destroyAll()", destroy)
        audio_cleanup = activity.index("AndroidAudioInput.stop()", destroy)
        xr_cleanup = activity.index("releaseOpenXRActivity()", destroy)
        self.assertLess(clear, web_cleanup)
        self.assertLess(clear, audio_cleanup)
        self.assertLess(clear, xr_cleanup)
        self.assertIn("public static void destroyAll()", webview)
        self.assertIn("new ArrayList<>(INSTANCES.keySet())", webview)

    def test_native_restart_owns_activity_across_jni_call(self):
        source = WINDOW.read_text(encoding="utf-8")
        restart = source.index("void WindowScriptingInterface::restartApplication")
        acquire_symbol = source.index("overtePicoOpenXRAcquireActivity", restart)
        attach = source.index("AttachCurrentThread", acquire_symbol)
        acquire = source.index("acquireActivityFunction(env)", attach)
        call = source.index("CallStaticVoidMethod", acquire)
        release = source.index("DeleteGlobalRef(activity)", call)
        detach = source.index("DetachCurrentThread", release)
        self.assertLess(acquire_symbol, attach)
        self.assertLess(attach, acquire)
        self.assertLess(acquire, call)
        self.assertLess(call, release)
        self.assertLess(release, detach)
        self.assertNotIn("overtePicoOpenXRActivity\"", source)


if __name__ == "__main__":
    unittest.main()
