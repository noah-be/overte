import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "common/tests/project-module-inventory-test.py"
SPEC = importlib.util.spec_from_file_location("project_inventory", MODULE_PATH)
inventory_validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory_validator
assert SPEC.loader is not None
SPEC.loader.exec_module(inventory_validator)


class ProjectInventoryTest(unittest.TestCase):
    def test_real_inventory_covers_every_gradle_module(self):
        inventory_validator.main(ROOT.parent)

    def test_missing_module_is_rejected_before_evidence_can_mask_it(self):
        original = inventory_validator.EXPECTED_MODULES
        try:
            inventory_validator.EXPECTED_MODULES = set(original) | {"unreviewedModule"}
            with self.assertRaisesRegex(ValueError, "module inventory mismatch"):
                inventory_validator.main(ROOT.parent)
        finally:
            inventory_validator.EXPECTED_MODULES = original

    @staticmethod
    def security_fixture(manifest_body, **overrides):
        module = {
            "sdk": {"compile": 35, "min": 26, "target": 35},
            "permissions": ["android.permission.INTERNET"],
            "exportedComponents": ["activity:.Launcher"],
        }
        module.update(overrides)
        build = "compileSdk 35\ndefaultConfig { minSdk 26; targetSdk 35 }"
        manifest = ET.fromstring(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
            '<uses-permission android:name="android.permission.INTERNET"/>'
            '<application>' + manifest_body + '</application></manifest>')
        return module, build, manifest

    def test_silent_permission_expansion_is_rejected(self):
        module, build, manifest = self.security_fixture(
            '<activity android:name=".Launcher" android:exported="true"/>')
        ET.SubElement(manifest, "uses-permission", {
            inventory_validator.ANDROID_NS + "name": "android.permission.CAMERA"})
        with self.assertRaisesRegex(ValueError, "permission allowlist changed"):
            inventory_validator.validate_application_security(
                "fixture", module, build, manifest)

    def test_silent_exported_component_expansion_is_rejected(self):
        module, build, manifest = self.security_fixture(
            '<activity android:name=".Launcher" android:exported="true"/>'
            '<receiver android:name=".Unexpected" android:exported="true"/>')
        with self.assertRaisesRegex(ValueError, "exported component surface changed"):
            inventory_validator.validate_application_security(
                "fixture", module, build, manifest)

    def test_sdk_baseline_change_is_rejected(self):
        module, _, manifest = self.security_fixture(
            '<activity android:name=".Launcher" android:exported="true"/>')
        changed_build = "compileSdk 35\ndefaultConfig { minSdk 24; targetSdk 35 }"
        with self.assertRaisesRegex(ValueError, "SDK baseline changed"):
            inventory_validator.validate_application_security(
                "fixture", module, changed_build, manifest)

    def test_modern_intent_filter_requires_explicit_exported(self):
        module, build, manifest = self.security_fixture(
            '<activity android:name=".Launcher"><intent-filter>'
            '<action android:name="android.intent.action.MAIN"/>'
            '</intent-filter></activity>')
        with self.assertRaisesRegex(ValueError, "must explicitly declare exported"):
            inventory_validator.validate_application_security(
                "fixture", module, build, manifest)

    def test_sensitive_launch_arguments_cannot_be_logged(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "Launcher.java"
            source.write_text(
                'class Launcher { void start() { System.out.println("args=" + mArgs); } }',
                encoding="utf-8")
            policy = {"source": "Launcher.java", "identifiers": ["mArgs"]}
            with self.assertRaisesRegex(ValueError, "logs sensitive launch argument"):
                inventory_validator.validate_sensitive_argument_logging(
                    "fixture", policy, Path(temporary))


if __name__ == "__main__":
    unittest.main()
