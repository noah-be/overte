"""Prevent Android image-decoder security updates from regressing or leaking to Pico."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[4]
FDROID = ROOT / "android/phone/fdroid"


def class_value(path, name):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing {name} in {path}")


class ImageDependencyVersionsTest(unittest.TestCase):
    def test_all_phone_lock_contexts_exclude_vulnerable_decoder_versions(self):
        refs = []
        for path in (FDROID / "locks").glob("*.lock"):
            lock = json.loads(path.read_text())
            for role in ("requires", "build_requires"):
                refs.extend(value.split("#")[0] for value in lock[role])
        for expected in ("libpng/1.6.58", "openexr/3.2.12", "libdeflate/1.25"):
            self.assertIn(expected, refs)
        self.assertNotIn("libpng/1.6.44", refs)
        self.assertNotIn("openexr/3.1.9", refs)

    def test_phone_override_preserves_pico_default(self):
        self.assertEqual("openexr/3.2.12", class_value(
            FDROID / "conan/target.conanfile.py", "openexr_ref"))
        self.assertEqual("openexr/3.1.9", class_value(
            ROOT / "android/common/conan/conanfile-pico.py", "openexr_ref"))

    def test_new_sources_remain_hash_pinned_and_license_bound(self):
        closure = json.loads((FDROID / "manifests/source-closure.lock.json").read_text())
        nodes = {node["reference"]: node for node in closure["nodes"]}
        for ref in ("libpng/1.6.58", "openexr/3.2.12", "libdeflate/1.25"):
            source, = nodes[ref]["sources"]
            self.assertTrue(source["canonical_url"].startswith("https://"))
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(source["license"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual("none", source["fdroid_exception"])


if __name__ == "__main__":
    unittest.main()
