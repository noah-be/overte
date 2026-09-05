#!/usr/bin/env python3

import ast
import hashlib
import importlib.util
import json
import os
import shlex
import sys
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path


HERE = Path(__file__).resolve().parent
RECIPE = HERE / "conanfile.py"
CONANDATA = HERE / "conandata.yml"
ORIGIN = HERE / "recipe-origin.lock.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_recipe():
    spec = importlib.util.spec_from_file_location("overte_qt_recipe", RECIPE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DummyRecipe:
    _composition_contract = {
        "status": "COMPOSED_SOURCE_AND_LICENSE_LOCKED_ATTRIBUTION_SCANNER_PENDING",
        "manifest_sha256": "62f963f5db37f1381264585ba527cd2f8943c6ed3058c41079484a3fbb0720a4",
        "license_lock_sha256": "73112c92373d338b14a8f1e88691d6d3e185f75ec8abe6cb0dee2fec55336474",
        "component_count": 17,
    }

    _sha256 = staticmethod(sha256)


class SourceOnlyQtRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_recipe()

    def make_composition(self, root: Path) -> Path:
        qt = root / "qt5" / "qtbase"
        qt.mkdir(parents=True)
        payload = qt / "payload.txt"
        payload.write_text("locked", encoding="utf-8")
        lock = root / "TREE_LOCK.tsv"
        lock.write_text(
            f"path\tmode\tsha256\nqtbase/payload.txt\t100644\t{sha256(payload)}\n",
            encoding="utf-8",
        )
        composition = dict(DummyRecipe._composition_contract)
        composition.update({"tree_entries": 1, "tree_lock_sha256": sha256(lock)})
        (root / "COMPOSITION.json").write_text(
            json.dumps(composition), encoding="utf-8"
        )
        return root

    def test_vendored_recipe_has_no_fetch_or_recursive_git_path(self):
        text = RECIPE.read_text(encoding="utf-8")
        ast.parse(text)
        for forbidden in (
            "conan.tools.scm import Version, Git",
            "git clone",
            "submodule update",
            "qt5.git",
            "qtwebengine/src/3rdparty",
        ):
            self.assertNotIn(forbidden, text)
        conandata = CONANDATA.read_text(encoding="utf-8")
        self.assertIn("Fix-error-uintptr_t", conandata)
        self.assertNotIn("qtwebengine", conandata.casefold())
        self.assertNotIn("http://", conandata)
        self.assertNotIn("https://", conandata)

    def test_selected_module_allowlist_excludes_webengine(self):
        modules = self.module.QtConan._composed_modules
        self.assertEqual(14, len(modules))
        self.assertNotIn("qtwebengine", modules)
        self.assertIn("qttools", modules)
        self.assertIn("qtwebview", modules)

    def make_sync_source(self, root):
        recipe = DummyRecipe()
        recipe.source_folder = str(root)
        recipe.version = "5.15.18-2026.01.04"
        recipe._composed_modules = self.module.QtConan._composed_modules
        for name in {"qtbase"} | recipe._composed_modules:
            directory = root / "qt5" / name
            directory.mkdir(parents=True)
            (directory / "sync.profile").write_text("# test profile\n")
        script = root / "qt5/qtbase/bin/syncqt.pl"
        script.parent.mkdir()
        script.write_text("# test boundary\n")
        recipe.run = Mock()
        return recipe

    def test_archive_headers_generated_for_all_frozen_modules(self):
        with tempfile.TemporaryDirectory(prefix="qt sync fixture ") as temporary:
            root = Path(temporary)
            recipe = self.make_sync_source(root)
            def generated(command):
                args = shlex.split(command)
                self.assertEqual(args[:1], ["perl"])
                self.assertEqual(args[2:6], ["-quiet", "-version", "5.15.18", "-outdir"])
                self.assertEqual(args[6], args[7])
                if Path(args[6]).name == "qtbase":
                    header = Path(args[6]) / "include/QtCore/qglobal.h"
                    header.parent.mkdir(parents=True)
                    header.write_text("# test generated header\n")
            recipe.run.side_effect = generated
            self.module.QtConan._sync_source_headers(recipe)
            self.assertEqual(recipe.run.call_count, 15)
            self.assertFalse(any((root / "qt5").rglob(".git")))

    def test_missing_sync_profile_or_generated_header_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recipe = self.make_sync_source(root)
            with self.assertRaisesRegex(self.module.ConanInvalidConfiguration, "did not generate"):
                self.module.QtConan._sync_source_headers(recipe)
            (root / "qt5/qttools/sync.profile").unlink()
            recipe.run.reset_mock()
            with self.assertRaisesRegex(self.module.ConanInvalidConfiguration, "profile is missing"):
                self.module.QtConan._sync_source_headers(recipe)
            recipe.run.assert_not_called()

    def test_real_source_calls_sync_after_verified_copy_and_patches(self):
        source = RECIPE.read_text().split("    def source(self):", 1)[1].split("    def generate", 1)[0]
        self.assertLess(source.index("_verify_composed_source"), source.index("shutil.copytree"))
        self.assertLess(source.index("apply_conandata_patches"), source.index("self._sync_source_headers()"))

    def test_vendored_inputs_match_the_origin_lock(self):
        origin = json.loads(ORIGIN.read_text(encoding="utf-8"))
        self.assertEqual(
            origin["qtmodules_sha256"],
            sha256(HERE / "qtmodules5.15.18-2026.01.04.conf"),
        )
        self.assertEqual(
            origin["vendored_patch_sha256"],
            sha256(
                HERE
                / "patches/Fix-error-uintptr_t-does-not-name-a-type-in-QtDeclarative.patch"
            ),
        )
        self.assertEqual(
            "a37c17acf0835de484280c6a7756bc9e7470757a", origin["commit"]
        )

    def test_exact_composition_and_tree_lock_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_composition(Path(temporary))
            result = self.module.QtConan._verify_composed_source(DummyRecipe(), root)
            self.assertEqual(root / "qt5", result)

    def test_tampered_tree_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_composition(Path(temporary))
            (root / "qt5" / "qtbase" / "payload.txt").write_text(
                "tampered", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                self.module.ConanInvalidConfiguration, "differs from its lock"
            ):
                self.module.QtConan._verify_composed_source(DummyRecipe(), root)

    def test_tree_lock_and_composition_tampering_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_composition(Path(temporary))
            with (root / "TREE_LOCK.tsv").open("a", encoding="utf-8") as stream:
                stream.write("extra\t100644\t" + "0" * 64 + "\n")
            with self.assertRaisesRegex(
                self.module.ConanInvalidConfiguration, "tree-lock digest mismatch"
            ):
                self.module.QtConan._verify_composed_source(DummyRecipe(), root)


if __name__ == "__main__":
    unittest.main()
