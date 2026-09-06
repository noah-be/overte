import importlib.util
import json
import os
import shutil
import subprocess
import sys
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
            self.assertEqual(51, len([name for name in names if name.endswith("/es")]))
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
            # Exercise the precise ORIGINAL Conan guard that failed in retry02,
            # using the original NASM class, not a replacement recipe/model.
            from conan.errors import ConanException
            from conan.internal.cache.conan_reference_layout import RecipeLayout
            from conan.internal.source import retrieve_exports_sources
            nasm_source = INDEX.parent / "nasm/2.15.05/export/conanfile.py"
            spec = importlib.util.spec_from_file_location("original_nasm_recipe", nasm_source)
            nasm_module = importlib.util.module_from_spec(spec)
            previous_bytecode = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                spec.loader.exec_module(nasm_module)
            finally:
                sys.dont_write_bytecode = previous_bytecode
            nasm = nasm_module.NASMConan()
            reference = "nasm/2.15.05"
            folder = home / "p" / expected[reference]["cache_folder"]
            self.assertTrue((folder / "es/patches/2.15.05-0001-disable-newly-integrated-dependency-tracking.patch").is_file())
            self.assertIsNone(retrieve_exports_sources(None, RecipeLayout(reference, str(folder)),
                                                        nasm, reference, []))
            with self.assertRaisesRegex(ConanException, "sources not found in local cache"):
                retrieve_exports_sources(None, RecipeLayout(reference, str(root / "missing")),
                                         nasm, reference, [])
            subprocess.run(["conan", "cache", "check-integrity", "*#*"],
                           env={**os.environ, "CONAN_HOME": str(home)}, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)

    def test_consistently_incomplete_ledger_and_tampered_export_fail_frozen_manifest(self):
        for tamper in (False, True):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temporary:
                store = Path(temporary) / "store"
                shutil.copytree(INDEX.parent, store)
                document = MODULE.load_json(store / "index.json")
                relative = "export_sources/patches/2.15.05-0001-disable-newly-integrated-dependency-tracking.patch"
                patch_path = store / "nasm/2.15.05" / relative
                if tamper:
                    patch_path.write_text("test-only substituted patch\n")
                    document["recipes"]["nasm/2.15.05"]["files"][relative] = MODULE.sha256_file(patch_path)
                else:
                    patch_path.unlink()
                    del document["recipes"]["nasm/2.15.05"]["files"][relative]
                (store / "index.json").write_text(json.dumps(document))
                with self.assertRaisesRegex(MODULE.RecipeStoreError, "Conan export manifest (byte|file set) mismatch"):
                    MODULE.validate(store / "index.json")

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
