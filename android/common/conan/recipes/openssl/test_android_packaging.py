"""Exercise installed Android provider files through the real package method."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from conan.tools.files import copy


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("openssl_android_packaging", HERE / "conanfile.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AndroidPackaging(unittest.TestCase):
    def fixture(self, root, missing=None):
        package = root / "package with spaces"
        source = root / "source"
        source.mkdir()
        (source / "LICENSE.txt").write_text("source license\n")
        payloads = {"crypto": b"installed Android crypto\x00", "ssl": b"installed Android TLS\x00"}

        def install(command, **kwargs):
            self.assertIn("install_sw DESTDIR=", command)
            self.assertEqual(kwargs, {"env": "conanbuild"})
            (package / "lib").mkdir(parents=True)
            (package / "bin").mkdir()
            (package / "bin/openssl").write_bytes(b"unneeded executable")
            for name, payload in payloads.items():
                if name != missing:
                    (package / "lib" / f"lib{name}.so").write_bytes(payload)

        recipe = SimpleNamespace(package_folder=str(package), source_folder=str(source),
                                 output=Mock(), run=install, _required_tool=lambda key: "/tools/make")
        return recipe, package, payloads

    def test_installed_provider_reaches_existing_phone_staging_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recipe, package, payloads = self.fixture(root)
            MODULE.OpenSSLAndroidConan.package(recipe)
            staging = root / "conanlibs/Debug"
            # Use the same real Conan copy operation as the root consumer.
            copy(recipe, "*.so*", str(package / "lib"), str(staging), False)
            for name, payload in payloads.items():
                self.assertEqual((staging / f"lib{name}.so.3").read_bytes(), payload)
                self.assertEqual((staging / f"lib{name}.so").read_bytes(), payload)
            self.assertEqual((package / "licenses/LICENSE.txt").read_text(), "source license\n")
            self.assertFalse((package / "bin").exists())

    def test_missing_installed_provider_fails_packaging(self):
        for missing in ("crypto", "ssl"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                recipe, _, _ = self.fixture(Path(temporary), missing=missing)
                with self.assertRaises(FileNotFoundError):
                    MODULE.OpenSSLAndroidConan.package(recipe)


if __name__ == "__main__":
    unittest.main()
