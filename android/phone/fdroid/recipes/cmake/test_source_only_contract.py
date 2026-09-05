import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CMakeSourceOnlyContractTest(unittest.TestCase):
    def test_only_source_archives_are_bound(self):
        data = (ROOT / "conandata.yml").read_text(encoding="utf-8")
        self.assertIn("cmake-3.31.12.tar.gz", data)
        self.assertIn("cmake-4.4.0.tar.gz", data)
        self.assertNotRegex(data, re.compile(r"linux-(?:x86_64|aarch64)\.tar"))

    def test_recipe_bootstraps_without_package_manager_or_binary_download(self):
        recipe = (ROOT / "conanfile.py").read_text(encoding="utf-8")
        self.assertIn("bootstrap", recipe)
        self.assertIn("--no-system-libs", recipe)
        self.assertNotRegex(
            recipe,
            re.compile(r"(?i)(sudo|apt(?:-get)?|dnf|yum|pacman|wget|curl)"),
        )


if __name__ == "__main__":
    unittest.main()
