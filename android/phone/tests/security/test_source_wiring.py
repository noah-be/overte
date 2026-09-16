"""Focused source-set contract check; does not evaluate Gradle or compile native code."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "security/redaction/java/org/overte/security/SafeDiagnostics.java"


class PhoneSecuritySourceWiringTests(unittest.TestCase):
    def test_product_includes_original_shared_sanitizer_once(self):
        module = ROOT / "android/phone/apps/phoneInterface"
        build = (module / "build.gradle").read_text()
        paths = re.findall(r"java\.srcDir '([^']+)'", build)
        matches = [p for p in paths if (module / p / "org/overte/security/SafeDiagnostics.java").resolve() == SOURCE]
        self.assertEqual(["../../../../security/redaction/java"], matches)
        self.assertTrue(SOURCE.is_file())
        self.assertFalse((module / "src/main/java/org/overte/security/SafeDiagnostics.java").exists())

    def test_shared_host_import_preserves_phone_boundary_and_selects_dependencies(self):
        module = ROOT / "android/common/tests/robolectric"
        build = (module / "build.gradle").read_text()
        self.assertIn("questJava, qtJava, sharedRedactionJava", build)
        self.assertIn("include 'org/overte/phone/PhoneInterfaceActivity.java'", build)
        for name in ("SecureAccountStore", "RedactingDiagnostics"):
            self.assertIn("include 'org/overte/phone/" + name + ".java'", build)
        self.assertIn("include 'org/overte/security/SafeDiagnostics.java'", build)
        self.assertIn("include 'org/overte/phone/RedactingDiagnosticsRobolectricTest.java'", build)
        self.assertEqual(SOURCE, (module / "../../../../security/redaction/java/org/overte/security/SafeDiagnostics.java").resolve())


if __name__ == "__main__": unittest.main()
