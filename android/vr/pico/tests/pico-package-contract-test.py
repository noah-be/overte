#!/usr/bin/env python3
"""Device-free packaging and platform contracts for the Pico 4 APK."""

import json
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
        self.assertIn("exclude { androidPatchedQtPlatform.exists() }", GRADLE)
        self.assertIn("delete picoQtRuntimeDir.map { it.file('arm64-v8a/libopenxr.so') }", GRADLE)

    def test_native_build_uses_pico_bootstrap_and_disables_breakpad(self):
        self.assertIn("-DHIFI_ANDROID_APP=picoInterface", GRADLE)
        self.assertIn("-DCMAKE_PROJECT_INCLUDE_BEFORE=", GRADLE)
        self.assertIn("common/cmake/pico-bootstrap.cmake", GRADLE)
        self.assertIn("-DUSE_BREAKPAD=OFF", GRADLE)

    def test_runtime_overrides_are_owned_by_shared_android(self):
        build_script = (ANDROID / "vr/pico/build.sh").read_text(encoding="utf-8")
        self.assertIn("../../../../common/runtime-overrides/arm64-v8a", GRADLE)
        self.assertIn('../../common/runtime-overrides/arm64-v8a', build_script)
        self.assertIn('legacy_runtime_dir', build_script)
        self.assertIn('cp -a "$legacy_runtime_dir/." "$shared_runtime_dir/"', build_script)

    def test_pico_conan_recipe_inherits_the_repository_recipe(self):
        recipe_path = ANDROID / "common/conan/conanfile-pico.py"
        recipe = recipe_path.read_text(encoding="utf-8")
        expected_upstream = recipe_path.resolve().parents[3] / "conanfile.py"

        self.assertEqual(expected_upstream, ROOT / "conanfile.py")
        self.assertTrue(expected_upstream.is_file())
        self.assertIn(
            'Path(__file__).resolve().parents[3] / "conanfile.py"',
            recipe,
        )

    def test_e2e_launcher_exists_only_in_the_debug_source_set(self):
        debug_manifest = APP / "src/debug/AndroidManifest.xml"
        activity_sources = list(
            (APP / "src/debug/java").rglob("E2eLauncherActivity.java")
        )
        self.assertEqual(1, len(activity_sources))
        self.assertFalse(list((APP / "src/main").rglob("E2eLauncherActivity.java")))

        activity = ET.parse(debug_manifest).getroot().find(
            "application/activity[@android:name='.E2eLauncherActivity']",
            {"android": NS[1:-1]},
        )
        self.assertIsNotNone(activity)
        self.assertEqual("true", activity.attrib[NS + "exported"])
        self.assertEqual("android.permission.DUMP", activity.attrib[NS + "permission"])
        self.assertEqual("true", activity.attrib[NS + "noHistory"])
        launcher = activity_sources[0].read_text(encoding="utf-8")
        self.assertIn("extends E2eLauncherActivityBase", launcher)

    def test_e2e_uses_factory_minimum_brightness_without_global_settings(self):
        debug_java = APP / "src/debug/java/org/overte/pico"
        e2e_activity = debug_java / "E2ePicoInterfaceActivity.java"
        self.assertTrue(e2e_activity.is_file())
        self.assertFalse(
            list((APP / "src/main").rglob("E2ePicoInterfaceActivity.java"))
        )

        source = e2e_activity.read_text(encoding="utf-8")
        self.assertIn("extends PicoInterfaceActivity", source)
        self.assertIn("1.0f / 255.0f", source)
        self.assertIn(
            "attributes.screenBrightness = MINIMUM_SCREEN_BRIGHTNESS", source
        )
        self.assertIn("getWindow().setAttributes(attributes)", source)
        for prohibited in ("Settings.System", "settings put", "screen_off_timeout"):
            self.assertNotIn(prohibited, source)

        launcher = (debug_java / "E2eLauncherActivity.java").read_text(
            encoding="utf-8"
        )
        self.assertIn("return E2ePicoInterfaceActivity.class", launcher)

        debug_manifest = ET.parse(APP / "src/debug/AndroidManifest.xml").getroot()
        activities = {
            item.attrib[NS + "name"]: item
            for item in debug_manifest.findall("application/activity")
        }
        e2e_entry = activities[".E2ePicoInterfaceActivity"]
        self.assertEqual("false", e2e_entry.attrib[NS + "exported"])
        self.assertEqual("singleTask", e2e_entry.attrib[NS + "launchMode"])
        self.assertIsNotNone(
            e2e_entry.find("meta-data[@android:name='android.app.lib_name']", {
                "android": NS[1:-1],
            })
        )

    def test_e2e_assets_and_native_layer_are_debug_only(self):
        self.assertIn("device_tests/e2e_android/src/main/java", GRADLE)
        self.assertGreaterEqual(GRADLE.count("variant.buildType.name == 'debug'"), 2)
        self.assertIn("e2eProbeAsset", GRADLE)
        self.assertIn("e2eSceneAsset", GRADLE)
        self.assertIn(
            "variant.mergeAssets.inputs.files(e2eProbeAsset, e2eSceneAsset)",
            GRADLE,
        )
        self.assertIn("arguments '-DOVERTE_PICO_E2E_OPENXR_INPUT=ON'", GRADLE)
        self.assertIn("arguments '-DOVERTE_PICO_E2E_OPENXR_INPUT=OFF'", GRADLE)

    def test_e2e_result_path_is_relative_atomic_and_app_private(self):
        save_object = (
            ROOT / "interface/src/scripting/TestScriptingInterface.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("QSaveFile", save_object)
        self.assertIn("QFileInfo(filename).fileName()", save_object)
        self.assertIn("file.commit()", save_object)
        for relative in (
            "interface/src/Application_Setup.cpp",
            "android/vr/pico/apps/picoInterface/overrides/Application_Setup.cpp",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("FileUtils::computeDocumentPath(path)", source)
            self.assertIn("QDir().mkpath(path)", source)

    def test_movement_override_is_native_runtime_only_and_nonpersistent(self):
        pico_setup = (
            APP / "overrides/Application_Setup.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("picoE2eInputMappingOverrideActive", pico_setup)
        self.assertIn(
            "/data/user/0/org.overte.pico/files/overte-e2e/overte_e2e_probe.js",
            pico_setup,
        )
        self.assertIn("#if defined(OVERTE_E2E_OPENXR_INPUT_V1)", pico_setup)
        self.assertIn("setE2eAdvancedMovementControlsOverride", pico_setup)
        self.assertIn("setE2eFlyingEnabledOverride", pico_setup)

        avatar_header = (ROOT / "interface/src/avatar/MyAvatar.h").read_text(
            encoding="utf-8"
        )
        self.assertIn("_e2eAdvancedMovementControlsOverride.get() ||", avatar_header)
        self.assertIn("_e2eAdvancedMovementControlsOverride.set(enabled)", avatar_header)
        declaration = avatar_header.split(
            "void setE2eAdvancedMovementControlsOverride", 1
        )[1].split("}", 1)[0]
        self.assertNotIn("Q_INVOKABLE", declaration)
        self.assertNotIn("_useAdvancedMovementControls.set", declaration)
        self.assertIn("_e2eFlyingEnabledOverride.set(enabled)", avatar_header)
        flying_declaration = avatar_header.split(
            "void setE2eFlyingEnabledOverride", 1
        )[1].split("}", 1)[0]
        self.assertNotIn("Q_INVOKABLE", flying_declaration)
        self.assertNotIn("_flyingHMDSetting.set", flying_declaration)
        self.assertIn("if(OVERTE_PICO_E2E_OPENXR_INPUT)", CMAKE)
        self.assertIn(
            "target_compile_definitions(interface PRIVATE OVERTE_E2E_OPENXR_INPUT_V1=1)",
            CMAKE,
        )
        avatar_source = (ROOT / "interface/src/avatar/MyAvatar.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "if (!useAdvancedMovementControls() && qApp->isHMDMode())",
            avatar_source,
        )
        self.assertIn("if (e2eFlyingEnabledOverride())", avatar_source)
        self.assertIn("getFlyingEnabled())))", avatar_source)
        self.assertNotIn(
            "setFlyingHMDPref(true)",
            pico_setup,
        )

        openxr_mapping = json.loads(
            (ROOT / "interface/resources/controllers/openxr.json").read_text(
                encoding="utf-8")
        )["channels"]
        self.assertIn(
            {"from": "OpenXR.RightSecondary",
             "to": "Standard.RightSecondaryThumb"},
            openxr_mapping,
        )
        standard_mapping = json.loads(
            (ROOT / "interface/resources/controllers/standard.json").read_text(
                encoding="utf-8")
        )["channels"]
        self.assertTrue(any(
            route.get("from") == "Standard.RightSecondaryThumb"
            and route.get("to") == "Actions.Up"
            and "Application.RightHandDominant" in route.get("when", [])
            for route in standard_mapping
        ))


if __name__ == "__main__":
    unittest.main()
