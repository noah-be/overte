import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("recipe_export_store.py")
ROOT = SCRIPT.parents[4]
INDEX = ROOT / "android/phone/fdroid/manifests/recipe-exports/index.json"
SPEC = importlib.util.spec_from_file_location("recipe_export_store", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecipeExportStoreTest(unittest.TestCase):
    def test_committed_directory_store_is_complete_and_source_only(self):
        index, pkglist = MODULE.validate(INDEX)
        self.assertEqual(51, len(index["recipes"]))
        self.assertEqual(set(index["recipes"]), set(pkglist))
        self.assertFalse((INDEX.parent.parent / "recipe-exports.tgz").exists())

    def test_external_transport_is_deterministic_and_recipe_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.tgz"
            second = root / "second.tgz"
            first_sha = MODULE.create_transport(INDEX, first, ROOT)
            second_sha = MODULE.create_transport(INDEX, second, ROOT)
            self.assertEqual(first_sha, second_sha)
            with MODULE.tarfile.open(first, "r:gz") as archive:
                names = [member.name for member in archive.getmembers()]
            self.assertIn("pkglist.json", names)
            self.assertEqual(51, len([name for name in names if name.endswith("/e/conanfile.py")]))
            self.assertFalse([name for name in names if "p" in Path(name).parts or "s" in Path(name).parts])
            self.assertFalse(any(name.endswith((".a", ".apk", ".dex", ".jar", ".o", ".so")) for name in names))

    def test_transport_inside_scanned_tree_is_rejected(self):
        with self.assertRaisesRegex(MODULE.RecipeStoreError, "outside scanned"):
            MODULE.create_transport(INDEX, ROOT / "forbidden.tgz", ROOT)

    def test_attempt_local_empty_cache_restore_has_exact_rrevs_and_no_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "conan-home"
            home.mkdir()
            subprocess.run(
                ["conan", "remote", "remove", "conancenter"],
                env={**os.environ, "CONAN_HOME": str(home)}, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            transport = root / "recipe-transport.tgz"
            MODULE.restore(INDEX, home, transport, ROOT)
            result = MODULE._conan_json(home, "list", "*#*").get("Local Cache", {})
            expected = json.loads(INDEX.read_text(encoding="utf-8"))["recipes"]
            self.assertEqual(set(expected), set(result))
            self.assertFalse(list((home / "p").glob("*/p")))
            self.assertEqual([], MODULE._conan_json(home, "remote", "list"))

    def test_nonempty_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "conan-home"
            home.mkdir()
            subprocess.run(
                ["conan", "remote", "remove", "conancenter"],
                env={**os.environ, "CONAN_HOME": str(home)}, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            # A syntactically valid recipe proves that any pre-existing recipe,
            # not merely a binary package, blocks the cold attempt.
            recipe = Path(temporary) / "conanfile.py"
            recipe.write_text("from conan import ConanFile\nclass Foreign(ConanFile):\n name='foreign'\n version='1.0'\n", encoding="utf-8")
            subprocess.run(
                ["conan", "export", str(recipe.parent)], env={**os.environ, "CONAN_HOME": str(home)},
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            with self.assertRaisesRegex(MODULE.RecipeStoreError, "not empty"):
                MODULE.restore(INDEX, home, Path(temporary) / "transport.tgz", ROOT)


if __name__ == "__main__":
    unittest.main()
