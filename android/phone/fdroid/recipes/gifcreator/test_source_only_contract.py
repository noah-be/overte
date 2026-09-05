import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class GifCreatorSourceOnlyContractTest(unittest.TestCase):
    def test_canonical_commit_and_license_are_bound(self):
        data = (ROOT / "conandata.yml").read_text(encoding="utf-8")
        recipe = (ROOT / "conanfile.py").read_text(encoding="utf-8")
        self.assertIn("66fe8bf0c5bfdfccfb77f42007654d325e22c18d", data)
        self.assertIn("6e078da86e0e204d90c28dbf1c3bb40941ef452036d12835307ab602c688426c", data)
        self.assertIn('license = "Unlicense"', recipe)
        self.assertIn('"LICENSE"', recipe)

    def test_old_opaque_distribution_is_absent(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in ROOT.rglob("*")
            if path.is_file() and path.suffix != ".pyc"
        )
        self.assertNotRegex(text, re.compile(r"build-deps\.overte\.org", re.I))


if __name__ == "__main__":
    unittest.main()
