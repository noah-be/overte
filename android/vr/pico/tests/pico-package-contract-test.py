#!/usr/bin/env python3
"""Device-free packaging and platform contracts for the Pico 4 APK."""

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[4]
ANDROID = ROOT / "android"
APP = ANDROID / "vr/pico/apps/picoInterface"
GRADLE = (APP / "build.gradle").read_text(encoding="utf-8")
CMAKE = (APP / "CMakeLists.txt").read_text(encoding="utf-8")
PLUGIN_CMAKE = (APP / "openxr/CMakeLists.txt").read_text(encoding="utf-8")
MANIFEST = ET.parse(APP / "src/main/AndroidManifest.xml").getroot()
NS = "{http://schemas.android.com/apk/res/android}"


class PicoPackageContractTests(unittest.TestCase):
    def test_apk_targets_supported_pico_architecture_and_api(self):
        self.assertRegex(GRADLE, r"compileSdk\s+36\b")
        self.assertRegex(GRADLE, r"minSdk\s+26\b")
        self.assertRegex(GRADLE, r"targetSdk\s+35\b")
        self.assertRegex(GRADLE, r"abiFilters\s+'arm64-v8a'")
        self.assertIn("JavaVersion.VERSION_17", GRADLE)

    def test_manifest_declares_vr_and_required_graphics_capabilities(self):
        features = {item.attrib.get(NS + "name"): item for item in MANIFEST.findall("uses-feature")}
        gl_feature = next(item for item in MANIFEST.findall("uses-feature") if NS + "glEsVersion" in item.attrib)
        self.assertEqual(gl_feature.attrib[NS + "glEsVersion"], "0x00030002")
        self.assertEqual(gl_feature.attrib[NS + "required"], "true")
        head_tracking = features["android.hardware.vr.headtracking"]
        self.assertEqual(head_tracking.attrib[NS + "version"], "1")
        self.assertEqual(head_tracking.attrib[NS + "required"], "true")
        metadata = MANIFEST.find("application/meta-data[@android:name='pvr.app.type']",
                                 {"android": NS[1:-1]})
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.attrib[NS + "value"], "vr")

    def test_runtime_permissions_are_minimal_and_expected(self):
        permissions = {item.attrib[NS + "name"] for item in MANIFEST.findall("uses-permission")}
        self.assertEqual(permissions, {
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.RECORD_AUDIO",
            "android.permission.MODIFY_AUDIO_SETTINGS",
            "android.permission.VIBRATE",
        })

    def test_openxr_plugin_is_built_and_packaged_under_android_scan_name(self):
        self.assertIn('set(DIR "openxr")', CMAKE)
        self.assertIn('"${CMAKE_CURRENT_SOURCE_DIR}/openxr"', CMAKE)
        self.assertIn("set(TARGET_NAME openxr)", PLUGIN_CMAKE)
        self.assertIn("setup_hifi_plugin(", PLUGIN_CMAKE)
        self.assertIn("libplugins_libopenxr.so", GRADLE)
        self.assertIn("exclude { picoPatchedQtPlatform.exists() }", GRADLE)
        self.assertIn("delete picoQtRuntimeDir.map { it.file('arm64-v8a/libopenxr.so') }", GRADLE)

    def test_native_build_uses_pico_bootstrap_and_disables_breakpad(self):
        self.assertIn("-DHIFI_ANDROID_APP=picoInterface", GRADLE)
        self.assertIn("-DCMAKE_PROJECT_INCLUDE_BEFORE=", GRADLE)
        self.assertIn("common/cmake/pico-bootstrap.cmake", GRADLE)
        self.assertIn("-DUSE_BREAKPAD=OFF", GRADLE)


if __name__ == "__main__":
    unittest.main()
