#!/usr/bin/env python3

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("qt_license_lock", HERE / "qt_license_lock.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class QtLicenseLockTests(unittest.TestCase):
    def make_tree(self, root: Path) -> Path:
        tree = root / "source"
        for identifier, destination in MODULE.EXPECTED_COMPONENTS.items():
            directory = tree / destination
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"LICENSE-{identifier}.txt").write_text(identifier, encoding="utf-8")
        third_party = tree / "qt5" / "qtbase" / "third_party"
        third_party.mkdir(parents=True, exist_ok=True)
        (third_party / "odd-name.txt").write_text("odd license", encoding="utf-8")
        (third_party / "extra.txt").write_text("extra license", encoding="utf-8")
        (third_party / "qt_attribution.json").write_text(
            '[{"LicenseFile":"odd-name.txt","Description":"bad\ncontrol"},'
            '{"LicenseFiles":["extra.txt", "../LICENSE-qtbase.txt"]}]',
            encoding="utf-8",
        )
        return tree

    def test_realistic_inventory_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self.make_tree(root)
            entries = MODULE.discover(tree)
            lock = root / "lock.tsv"
            lock.write_text(MODULE.serialize(entries), encoding="utf-8")
            self.assertEqual(entries, MODULE.verify(tree, lock))
            paths = {entry.path for entry in entries}
            self.assertIn("qtbase/third_party/odd-name.txt", paths)
            self.assertIn("qtbase/third_party/extra.txt", paths)

    def test_stale_hash_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self.make_tree(root)
            lock = root / "lock.tsv"
            lock.write_text(MODULE.serialize(MODULE.discover(tree)), encoding="utf-8")
            (tree / "qt5" / "qtsvg" / "LICENSE-qtsvg.txt").write_text(
                "changed", encoding="utf-8"
            )
            with self.assertRaisesRegex(MODULE.LicenseLockError, "changed="):
                MODULE.verify(tree, lock)

    def test_new_unlocked_license_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self.make_tree(root)
            lock = root / "lock.tsv"
            lock.write_text(MODULE.serialize(MODULE.discover(tree)), encoding="utf-8")
            (tree / "qt5" / "qtbase" / "COPYING.NEW").write_text("new", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.LicenseLockError, "missing="):
                MODULE.verify(tree, lock)

    def test_escaping_reference_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self.make_tree(root)
            attribution = tree / "qt5" / "qtbase" / "third_party" / "qt_attribution.json"
            attribution.write_text('{"LicenseFile":"../../../escape"}', encoding="utf-8")
            (tree / "escape").write_text("escape", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.LicenseLockError, "escapes Qt root"):
                MODULE.discover(tree)

    def test_attribution_without_license_field_is_still_locked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self.make_tree(root)
            attribution = tree / "qt5" / "qtbase" / "third_party" / "qt_attribution.json"
            attribution.write_text('{"Name":"no license"}', encoding="utf-8")
            entries = MODULE.discover(tree)
            self.assertIn(
                "qtbase/third_party/qt_attribution.json",
                {entry.path for entry in entries},
            )


if __name__ == "__main__":
    unittest.main()
