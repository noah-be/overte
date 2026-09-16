# SPDX-License-Identifier: Apache-2.0
"""Phone build-source wiring and original Shared profile resolver; no native build."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class RetainedProfileBindingTests(unittest.TestCase):
    def test_original_cpp14_profile_resolver(self):
        with tempfile.TemporaryDirectory(prefix="phone-profile-contract-") as temporary:
            binary = Path(temporary) / "profile"
            subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                            str(ROOT / "tests/device/contracts/profile-test.cpp"), "-o", str(binary)],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_phone_product_define_reaches_original_registry_and_selectors(self):
        module = ROOT / "android/phone/apps/phoneInterface"
        gradle = (module / "build.gradle").read_text()
        self.assertIn("'-DHIFI_ANDROID_APP=phoneInterface'", gradle)
        self.assertIn("path file('../../../../CMakeLists.txt')", gradle)
        self.assertEqual((module / "../../../../CMakeLists.txt").resolve(), ROOT / "CMakeLists.txt")
        cmake = (ROOT / "CMakeLists.txt").read_text()
        definition = r'add_definitions(-DHIFI_ANDROID_APP=\"${HIFI_ANDROID_APP}\")'
        self.assertIn(definition, cmake)
        self.assertLess(cmake.index(definition), cmake.index('add_subdirectory(android/phone/apps/${HIFI_ANDROID_APP})'))
        for path in ("libraries/shared/src/Preferences.h", "libraries/shared/src/shared/FileUtils.cpp"):
            source = (ROOT / path).read_text()
            self.assertIn("ConfiguredCapabilityProfile.h", source)
            self.assertIn("configuredProduct()", source)
        registry = (ROOT / "libraries/shared/src/Preferences.cpp").read_text()
        self.assertIn("if (!preference->isProfileAllowed()) { return; }", registry)


if __name__ == "__main__":
    unittest.main()
