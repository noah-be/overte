import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("toolchain_probe.py")
SPEC = importlib.util.spec_from_file_location("toolchain_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ToolchainProbeTest(unittest.TestCase):
    def test_exact_versions_pass(self):
        expected = {"gcc": "15.3.0", "java_major": "17"}
        MODULE.validate_versions(expected, dict(expected))

    def test_wrong_gcc_fails(self):
        with self.assertRaisesRegex(MODULE.ToolchainError, "wrong gcc"):
            MODULE.validate_versions({"gcc": "15.3.0"}, {"gcc": "16.0.0"})

    def test_wrong_java_fails(self):
        with self.assertRaisesRegex(MODULE.ToolchainError, "wrong java"):
            MODULE.validate_versions({"java_major": "17"}, {"java_major": "25"})

    def test_missing_version_fails(self):
        with self.assertRaisesRegex(MODULE.ToolchainError, "got None"):
            MODULE.validate_versions({"ninja": "1.13.2"}, {})


if __name__ == "__main__":
    unittest.main()
