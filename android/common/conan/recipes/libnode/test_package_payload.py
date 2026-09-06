"""The shared Node package must not flatten host/build archives into its payload."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SPEC = importlib.util.spec_from_file_location("libnode_package", Path(__file__).with_name("conanfile.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PackagePayload(unittest.TestCase):
    def fixture(self, root, final_output=True):
        source, package = root / "source", root / "package"
        output = source / "out/Debug"
        for name in ("obj.host", "obj.target"):
            (output / name).mkdir(parents=True)
            (output / name / "libv8.a").write_bytes(b"!<thin>\n" + name.encode())
            (output / name / "libnode.so").write_bytes(name.encode())
        if final_output:
            (output / "libnode.so").write_bytes(b"finished target DSO\x00")
        for name in ("libplatform", "cppgc"):
            folder = source / "deps/v8/include" / name
            folder.mkdir(parents=True)
            (folder / "public.h").write_text(name)
        recipe = SimpleNamespace(source_folder=str(source), package_folder=str(package),
                                 settings=SimpleNamespace(build_type="Debug"), output=Mock(), run=Mock())
        return recipe, package

    def test_only_final_target_dso_and_public_headers_are_packaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            recipe, package = self.fixture(Path(temporary))
            MODULE.LibnodeAndroidConan.package(recipe)
            self.assertEqual(sorted(path.name for path in (package / "lib").iterdir()), ["libnode.so"])
            self.assertEqual((package / "lib/libnode.so").read_bytes(), b"finished target DSO\x00")
            for name in ("libplatform", "cppgc"):
                self.assertEqual((package / "include" / name / "public.h").read_text(), name)

    def test_missing_final_dso_cannot_fall_back_to_host_or_partial_target_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            recipe, _ = self.fixture(Path(temporary), final_output=False)
            with self.assertRaises(FileNotFoundError):
                MODULE.LibnodeAndroidConan.package(recipe)


if __name__ == "__main__":
    unittest.main()
