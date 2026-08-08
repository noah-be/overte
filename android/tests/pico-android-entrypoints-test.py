#!/usr/bin/env python3
"""Device-free security contracts for Pico Android entry points."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
JAVA = ROOT / "android/apps/picoInterface/src/main/java/org/overte/pico"
MANIFEST = ROOT / "android/apps/picoInterface/src/main/AndroidManifest.xml"
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

    def test_exported_launcher_does_not_accept_argument_strings(self):
        permissions = (JAVA / "PermissionsActivity.java").read_text(encoding="utf-8")
        self.assertNotIn('getStringExtra("args")', permissions)
        self.assertIn("RestartArguments.consume(this)", permissions)

    def test_permission_activity_preserves_one_shot_restart_state(self):
        permissions = (JAVA / "PermissionsActivity.java").read_text(encoding="utf-8")
        self.assertIn("onSaveInstanceState(Bundle outState)", permissions)
        self.assertIn("outState.putString(STATE_ARGUMENTS, applicationArguments)", permissions)
        self.assertIn("savedInstanceState.getString(STATE_ARGUMENTS)", permissions)
        self.assertGreaterEqual(permissions.count("if (interfaceLaunched)"), 2)
        self.assertIn("interfaceLaunched = true", permissions)

    def test_restart_arguments_are_private_and_not_logged(self):
        activity = (JAVA / "PicoInterfaceActivity.java").read_text(encoding="utf-8")
        storage = (JAVA / "RestartArguments.java").read_text(encoding="utf-8")
        self.assertIn("RestartArguments.store(activity, applicationArguments)", activity)
        self.assertNotIn('putExtra("args", applicationArguments)', activity)
        self.assertNotIn('"Scheduling application restart with arguments:', activity)
        self.assertIn("Context.MODE_PRIVATE", storage)
        self.assertIn(".remove(KEY_ARGUMENTS)", storage)


if __name__ == "__main__":
    unittest.main()
