"""Verify owning-profile selection and closed failures for native product checks."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("product_control_plane",
    Path(__file__).resolve().parents[1] / "run_control_plane_tests.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ENTRY = "android/phone/tests/phone-e2e-runtime-regressions.py"
DECLARATION = {"name": "phone-e2e-runtime-regressions",
               "entrypoint": ENTRY, "interpreter": "python"}


class ProductContractRegistration(unittest.TestCase):
    def select(self, platform, entries, present=True, profile="full"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/platform-profile.json").write_text(json.dumps(
                {"schema": 1, "platform": platform, "suites": entries}))
            if present:
                (root / ENTRY).parent.mkdir(parents=True)
                (root / ENTRY).write_text("# owned product entry point\n")
            with patch.object(MODULE, "REPOSITORY", root):
                return MODULE.commands(profile)

    def test_shared_and_unclaimed_android_keep_portable_groups(self):
        for platform in ("shared", "android"):
            checks = self.select(platform, [])
            self.assertNotIn("phone-native-runtime", [name for name, *_ in checks])
            self.assertIn("phone-voice-buffer", [name for name, *_ in checks])
            self.assertIn("python-self-tests", [name for name, *_ in checks])

    def test_declared_product_is_executed_with_native_inputs(self):
        checks = self.select("android", [DECLARATION])
        selected = [command for name, command, _ in checks if name == "phone-native-runtime"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][0], sys.executable)
        self.assertTrue(selected[0][1].endswith(ENTRY))
        self.assertEqual(selected[0][-1], "--execute")

    def test_missing_declared_entry_point_fails_instead_of_skipping(self):
        with self.assertRaises(ValueError):
            self.select("android", [DECLARATION], present=False)

    def test_wrong_owner_path_and_interpreter_fail_closed(self):
        for platform, change in (("shared", {}),
                                 ("android", {"entrypoint": "../foreign.py"}),
                                 ("android", {"interpreter": "bash"})):
            with self.subTest(platform=platform, change=change):
                with self.assertRaises(ValueError):
                    self.select(platform, [{**DECLARATION, **change}])

    def test_quick_gate_retains_dependency_light_selection(self):
        checks = self.select("android", [DECLARATION], profile="quick")
        self.assertNotIn("phone-native-runtime", [name for name, *_ in checks])
        self.assertIn("python-voice-roundtrip", [name for name, *_ in checks])


if __name__ == "__main__":
    unittest.main()
