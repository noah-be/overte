#!/usr/bin/env python3
"""Reject ambiguous bindings rather than selecting an unrelated cached binary."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("package_folder", Path(__file__).with_name("package-folder.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageFolderTest(unittest.TestCase):
    def test_exact_directory_and_rejections(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            selected, unrelated = root / "selected package", root / "unrelated-cache"
            selected.mkdir(); unrelated.mkdir()
            generator = root / "draco-debug-armv8-data.cmake"
            line = f'set(draco_PACKAGE_FOLDER_DEBUG "{selected}")\n'
            generator.write_text(line)
            self.assertEqual(module.package_folder(generator, "draco"), selected)
            for invalid in (line + line, "", f'set(draco_PACKAGE_FOLDER_DEBUG "{unrelated}/../selected package")\n',
                            'set(draco_PACKAGE_FOLDER_DEBUG "${CACHE}/package")\n',
                            'set(draco_PACKAGE_FOLDER_DEBUG "relative/path")\n'):
                generator.write_text(invalid)
                with self.assertRaises(ValueError): module.package_folder(generator, "draco")
            generator.write_text(line)
            link = root / "linked-generator"
            link.symlink_to(generator)
            with self.assertRaises(ValueError): module.package_folder(link, "draco")
            with self.assertRaises(ValueError): module.package_folder(generator, "draco;execute")


if __name__ == "__main__":
    unittest.main()
