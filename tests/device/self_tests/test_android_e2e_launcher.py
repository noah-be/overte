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
            'android-debug-file-v1',
            'writeAtomically(CONTROL_MARKER, CONTROL_CONTRACT, launchDirectory)',
            '"android-control-command.json"',
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


if __name__ == "__main__":
    unittest.main()
