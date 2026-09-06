"""Actual recipe methods with filesystem/config and generator/run boundaries."""
import importlib.util
import pathlib
import shlex
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from conan.errors import ConanInvalidConfiguration
from conan.tools.env import Environment

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("openssl_android_recipe", HERE / "conanfile.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
RECIPE = MODULE.OpenSSLAndroidConan


class AndroidEnvironment(unittest.TestCase):
    def fixture(self, root):
        ndk = root / "ndk with spaces"
        binaries = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
        binaries.mkdir(parents=True)
        (ndk / "source.properties").write_text("Pkg.Revision = 27.3.13750724\n")
        for name in ("clang", "llvm-ar", "aarch64-linux-android26-clang"):
            path = binaries / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        values = {"tools.android:ndk_path": str(ndk)}
        recipe = types.SimpleNamespace(
            conf=types.SimpleNamespace(get=lambda key, **kwargs: values.get(key)),
            settings_build=types.SimpleNamespace(os="Linux", arch="x86_64"))
        recipe._android_ndk = lambda: RECIPE._android_ndk(recipe)
        return recipe, values, ndk, binaries

    def test_real_environment_keeps_compiler_and_binds_configured_ndk(self):
        with tempfile.TemporaryDirectory() as temporary:
            recipe, _, ndk, binaries = self.fixture(pathlib.Path(temporary))
            environment = Environment()
            environment.define("CC", "original-toolchain-cc")
            environment.define("LDFLAGS", "-Wl,-z,max-page-size=16384")
            toolchain = Mock(environment=lambda: environment)
            with patch.object(MODULE, "AutotoolsToolchain", return_value=toolchain):
                RECIPE.generate(recipe)
            toolchain.generate.assert_called_once_with(environment)
            # Real Conan Environment application, not a replacement env model.
            with patch.dict("os.environ", {"PATH": "/usr/bin", "ANDROID_NDK_ROOT": "/foreign", "CROSS_SYSROOT": "/foreign", "CROSS_COMPILE": "bad-"}, clear=True):
                with environment.vars(Mock()).apply():
                    import os
                    self.assertEqual(str(ndk), os.environ["ANDROID_NDK_ROOT"])
                    self.assertEqual(str(binaries), os.environ["PATH"].split(":")[0])
                    self.assertEqual("original-toolchain-cc", os.environ["CC"])
                    self.assertIn("16384", os.environ["LDFLAGS"])
                    self.assertFalse(os.environ.get("CROSS_SYSROOT"))
                    self.assertFalse(os.environ.get("CROSS_COMPILE"))

    def test_missing_relative_wrong_host_or_missing_compiler_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            recipe, values, ndk, binaries = self.fixture(pathlib.Path(temporary))
            for invalid in (None, "relative", str(ndk / "missing")):
                values["tools.android:ndk_path"] = invalid
                with self.assertRaises(ConanInvalidConfiguration):
                    RECIPE._android_ndk(recipe)
            values["tools.android:ndk_path"] = str(ndk)
            recipe.settings_build.os = "Macos"
            with self.assertRaises(ConanInvalidConfiguration):
                RECIPE._android_ndk(recipe)
            recipe.settings_build.os = "Linux"
            (binaries / "aarch64-linux-android26-clang").chmod(0o644)
            with self.assertRaises(ConanInvalidConfiguration):
                RECIPE._android_ndk(recipe)

    def test_actual_build_pins_api_provider_and_same_environment(self):
        recipe = types.SimpleNamespace(source_folder="/source with spaces", run=Mock(),
                                       _required_tool=lambda key: "/absolute tools/" + ("perl" if "perl" in key else "make"))
        with patch.object(MODULE, "build_jobs", return_value=3):
            RECIPE.build(recipe)
        configure, make = recipe.run.call_args_list
        command = shlex.split(configure.args[0])
        self.assertEqual(command[:3], ["/absolute tools/perl", "/source with spaces/Configure", "android-arm64"])
        self.assertIn("-D__ANDROID_API__=26", command)
        for option in ("shared", "no-module", "no-fips", "no-tests"):
            self.assertIn(option, command)
        self.assertEqual(configure.kwargs, {"env": "conanbuild"})
        self.assertEqual(make.kwargs, {"env": "conanbuild"})
        self.assertEqual(shlex.split(make.args[0]), ["/absolute tools/make", "-j3"])


if __name__ == "__main__":
    unittest.main()
