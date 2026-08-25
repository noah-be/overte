#!/usr/bin/env python3
"""Static safety contracts for the debug-only Android E2E launch path."""

from __future__ import annotations

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[3]
ANDROID_NAME = "{http://schemas.android.com/apk/res/android}"
BASE = (REPOSITORY / "android/common/device_tests/e2e_android/src/main/java/"
        "org/overte/e2e/E2eLauncherActivityBase.java")


class AndroidE2ELauncherTest(unittest.TestCase):
    def test_launchers_exist_only_in_debug_source_sets_and_require_shell_permission(self):
        for relative in (
            "android/phone/apps/phoneInterface",
            "android/vr/pico/apps/picoInterface",
        ):
            application = REPOSITORY / relative
            manifest = application / "src/debug/AndroidManifest.xml"
            activity_source = list((application / "src/debug/java").rglob(
                "E2eLauncherActivity.java"))
            self.assertEqual(1, len(activity_source), relative)
            self.assertFalse(list((application / "src/main").rglob(
                "E2eLauncherActivity.java")), relative)

            activity = ET.parse(manifest).getroot().find("application/activity")
            self.assertIsNotNone(activity, relative)
            self.assertEqual("true", activity.attrib[ANDROID_NAME + "exported"])
            self.assertEqual("android.permission.DUMP",
                             activity.attrib[ANDROID_NAME + "permission"])
            self.assertEqual("true", activity.attrib[ANDROID_NAME + "noHistory"])

    def test_launcher_accepts_no_external_arguments_and_uses_fixed_assets(self):
        source = BASE.read_text(encoding="utf-8")
        for prohibited in ("getIntent()", "getStringExtra", "getData()", "EXTRA_"):
            self.assertNotIn(prohibited, source)
        for required in (
            'PROBE_ASSET = "overte_e2e_probe.js"',
            'SCENE_ASSET = "scene.json"',
            'putExtra("applicationArguments", arguments)',
            'new File(getFilesDir(), DIRECTORY)',
            'new File(launchDirectory, "overte-probe.json")',
            'SPAWN_VIEWPOINT = "/0,2,4/0,0,0,1"',
            'appendQueryParameter("location", SPAWN_VIEWPOINT)',
        ):
            self.assertIn(required, source)
        self.assertNotIn("getExternalFilesDir", source)
        self.assertTrue((REPOSITORY / "tests/device/probe/overte_e2e_probe.js").is_file())
        self.assertTrue((REPOSITORY / "tests/device/fixture/scene.json").is_file())

    def test_gradle_packages_probe_and_scene_only_for_debug_variants(self):
        for relative in (
            "android/phone/apps/phoneInterface/build.gradle",
            "android/vr/pico/apps/picoInterface/build.gradle",
        ):
            source = (REPOSITORY / relative).read_text(encoding="utf-8")
            self.assertIn("device_tests/e2e_android/src/main/java", source)
            self.assertGreaterEqual(source.count("variant.buildType.name == 'debug'"), 2)
            self.assertIn("e2eProbeAsset", source)
            self.assertIn("e2eSceneAsset", source)
            self.assertIn("variant.mergeAssets.inputs.files(e2eProbeAsset, e2eSceneAsset)",
                          source)

    def test_native_result_path_is_relative_and_atomic(self):
        save_object = (REPOSITORY /
            "interface/src/scripting/TestScriptingInterface.cpp").read_text(encoding="utf-8")
        self.assertIn("QSaveFile", save_object)
        self.assertIn("QFileInfo(filename).fileName()", save_object)
        self.assertIn("file.commit()", save_object)
        for relative in (
            "interface/src/Application_Setup.cpp",
            "android/vr/pico/apps/picoInterface/overrides/Application_Setup.cpp",
        ):
            source = (REPOSITORY / relative).read_text(encoding="utf-8")
            self.assertIn("FileUtils::computeDocumentPath(path)", source)
            self.assertIn("QDir().mkpath(path)", source)


if __name__ == "__main__":
    unittest.main()
