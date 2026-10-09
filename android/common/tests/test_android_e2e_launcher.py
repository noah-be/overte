#!/usr/bin/env python3
"""Static safety contracts for the debug-only Android E2E launch path."""

from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[3]
BASE = (REPOSITORY / "android/common/device_tests/e2e_android/src/main/java/"
        "org/overte/e2e/E2eLauncherActivityBase.java")


class AndroidE2ELauncherTest(unittest.TestCase):
    def test_launcher_accepts_no_external_arguments_and_uses_fixed_assets(self):
        source = BASE.read_text(encoding="utf-8")
        for prohibited in ("getIntent()", "getStringExtra", "getData()", "EXTRA_"):
            self.assertNotIn(prohibited, source)
        for required in (
            'PROBE_ASSET = "overte_e2e_probe.js"',
            'SCENE_ASSET = "scene.json"',
            'CONTROL_MARKER = "android-control.json"',
            'CONTROL_COMMAND = "android-control-command.json"',
            'android-debug-file-v1',
            'writeAtomically(CONTROL_MARKER, CONTROL_CONTRACT, launchDirectory)',
            'writeAtomically(CONTROL_COMMAND, EMPTY_CONTROL_COMMAND, launchDirectory)',
            'putExtra("applicationArguments", arguments)',
            'new File(getFilesDir(), DIRECTORY)',
            'new File(launchDirectory, "overte-probe.json")',
            'SPAWN_VIEWPOINT = "/0,0,4/0,0,0,1"',
            'appendQueryParameter("location", SPAWN_VIEWPOINT)',
        ):
            self.assertIn(required, source)
        self.assertNotIn("getExternalFilesDir", source)
        self.assertTrue((REPOSITORY / "tests/device/probe/overte_e2e_probe.js").is_file())
        self.assertTrue((REPOSITORY / "tests/device/fixture/scene.json").is_file())

    def test_phone_packages_and_copies_the_referenced_entity_script(self):
        phone = REPOSITORY / "android/phone/apps/phoneInterface"
        launcher = (phone / "src/debug/java/org/overte/phone/E2eLauncherActivity.java").read_text()
        gradle = (phone / "build.gradle").read_text()
        self.assertIn('return new String[] { "scripted_interactable.js" };', launcher)
        self.assertIn('for (String asset : additionalAssets())', BASE.read_text())
        self.assertIn('e2eEntityScriptAsset = file(', gradle)
        self.assertIn('inputs.files(e2eProbeAsset, e2eSceneAsset, e2eEntityScriptAsset)', gradle)
        self.assertIn('from e2eEntityScriptAsset', gradle)
        self.assertIn('bindAdditionalAssetReferences(scene, launchDirectory)', BASE.read_text())
        self.assertIn('Uri.fromFile(new File(directory, asset))', BASE.read_text())
        self.assertIn('entity.put("script", additionalAssetUrl(asset, directory))', BASE.read_text())
        self.assertIn('"qrc:/overte-e2e/scripted_interactable.js"', launcher)
        cmake = (REPOSITORY / "interface/CMakeLists.txt").read_text()
        self.assertIn('HIFI_ANDROID_APP STREQUAL "phoneInterface" AND OVERTE_E2E_VOICE_TESTS', cmake)
        self.assertIn('"${CMAKE_SOURCE_DIR}/tests/device/fixture/scripted_interactable.js"', cmake)
        scene = (REPOSITORY / "tests/device/fixture/scene.json").read_text()
        self.assertIn('scripted_interactable.js', scene)


if __name__ == "__main__":
    unittest.main()
