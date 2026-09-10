#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SPEC = importlib.util.spec_from_file_location("fdroid_profile_doctor", HERE / "doctor.py")
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


class DoctorContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Path(self.temporary.name)
        for relative in (
            "android/common/cmake/overte-android-toolchain.cmake",
            "android/phone/fdroid/conan/bootstrap.conanfile.py",
            "android/phone/fdroid/manifests/base-toolchain.lock.json",
            "android/phone/fdroid/profiles/input-map.json",
            "android/phone/fdroid/profiles/linux-x86_64-bootstrap",
            "android/phone/fdroid/profiles/linux-x86_64-hosttools",
            "android/phone/fdroid/profiles/android-arm64-v8a-api26-16k",
        ):
            source = ROOT / relative
            target = self.fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

    def tearDown(self):
        self.temporary.cleanup()

    def load_map(self):
        path = self.fixture / "android/phone/fdroid/profiles/input-map.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def write_map(self, value):
        path, _ = self.load_map()
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def rehash(self, relative):
        path, document = self.load_map()
        for entry in document["neutral_inputs"]:
            if entry["path"] == relative:
                entry["sha256"] = DOCTOR.file_digest(self.fixture / relative)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def test_real_contract_is_equivalent(self):
        result = DOCTOR.inspect(ROOT)
        self.assertTrue(result["equivalent"])
        self.assertEqual(result["consumers"]["phone"], result["consumers"]["pico"])

    def test_stale_input_digest_fails(self):
        path, document = self.load_map()
        document["neutral_inputs"][0]["sha256"] = "0" * 64
        self.write_map(document)
        with self.assertRaisesRegex(DOCTOR.ContractError, "input digest mismatch"):
            DOCTOR.inspect(self.fixture)

    def test_product_named_implementation_input_fails(self):
        path, document = self.load_map()
        source = self.fixture / document["neutral_inputs"][-1]["path"]
        product_path = self.fixture / "android/phone/fdroid/profiles/pico-target"
        product_path.write_bytes(source.read_bytes())
        document["neutral_inputs"][-1]["path"] = "android/phone/fdroid/profiles/pico-target"
        document["neutral_inputs"][-1]["sha256"] = DOCTOR.file_digest(product_path)
        self.write_map(document)
        with self.assertRaisesRegex(DOCTOR.ContractError, "product-named"):
            DOCTOR.inspect(self.fixture)

    def test_default_profile_fails_even_when_rehashed(self):
        relative = "android/phone/fdroid/profiles/linux-x86_64-bootstrap"
        target = self.fixture / relative
        target.write_text(target.read_text(encoding="utf-8") + "# default\n", encoding="utf-8")
        self.rehash(relative)
        with self.assertRaisesRegex(DOCTOR.ContractError, "forbidden implicit input"):
            DOCTOR.inspect(self.fixture)

    def test_cache_restore_fails_even_when_rehashed(self):
        relative = "android/phone/fdroid/conan/bootstrap.conanfile.py"
        target = self.fixture / relative
        target.write_text(target.read_text(encoding="utf-8") + "# cache restore\n", encoding="utf-8")
        self.rehash(relative)
        with self.assertRaisesRegex(DOCTOR.ContractError, "forbidden implicit input"):
            DOCTOR.inspect(self.fixture)

    def test_package_manager_fails_even_when_rehashed(self):
        relative = "android/phone/fdroid/profiles/linux-x86_64-hosttools"
        target = self.fixture / relative
        target.write_text(target.read_text(encoding="utf-8") + "# apt-get install cmake\n", encoding="utf-8")
        self.rehash(relative)
        with self.assertRaisesRegex(DOCTOR.ContractError, "forbidden implicit input"):
            DOCTOR.inspect(self.fixture)

    def test_modified_baseline_fails_even_with_new_identity(self):
        path = self.fixture / "android/phone/fdroid/manifests/base-toolchain.lock.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["baseline"]["android"]["minimum_api"] = 27
        document["identity_sha256"] = DOCTOR.canonical_digest(document["baseline"])
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        self.rehash("android/phone/fdroid/manifests/base-toolchain.lock.json")
        with self.assertRaisesRegex(DOCTOR.ContractError, "fixed SH-010 baseline"):
            DOCTOR.inspect(self.fixture)

    def test_runtime_rejects_nonempty_conan_home(self):
        cache = self.fixture / "cache"
        cache.mkdir()
        (cache / "unexpected").write_text("binary", encoding="utf-8")
        (self.fixture / "sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin").mkdir(parents=True)
        (self.fixture / "sdk/platforms/android-36").mkdir(parents=True)
        (self.fixture / "sdk/build-tools/36.0.0").mkdir(parents=True)
        (self.fixture / "sdk/platform-tools").mkdir(parents=True)
        (self.fixture / "jdk/bin").mkdir(parents=True)
        baseline = copy.deepcopy(DOCTOR.EXPECTED_BASELINE)
        environment = {
            "ANDROID_SDK_ROOT": str(self.fixture / "sdk"),
            "ANDROID_NDK_HOME": str(self.fixture / "sdk/ndk/27.3.13750724"),
            "JAVA_HOME": str(self.fixture / "jdk"),
            "CONAN_HOME": str(cache),
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            environment_path = [os.path.expandvars(entry) for entry in baseline["allowed_path_entries"]]
            os.environ["PATH"] = os.pathsep.join(environment_path)
            with self.assertRaisesRegex(DOCTOR.ContractError, "CONAN_HOME is not empty"):
                DOCTOR.runtime_preflight(baseline)

    def test_runtime_requires_explicit_tool_roots(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DOCTOR.ContractError, "required runtime inputs are absent"):
                DOCTOR.runtime_preflight(copy.deepcopy(DOCTOR.EXPECTED_BASELINE))

    def test_runtime_rejects_implicit_path_entry(self):
        (self.fixture / "sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin").mkdir(parents=True)
        (self.fixture / "sdk/platforms/android-36").mkdir(parents=True)
        (self.fixture / "sdk/build-tools/36.0.0").mkdir(parents=True)
        (self.fixture / "sdk/platform-tools").mkdir(parents=True)
        (self.fixture / "jdk/bin").mkdir(parents=True)
        cache = self.fixture / "empty-cache"
        cache.mkdir()
        baseline = copy.deepcopy(DOCTOR.EXPECTED_BASELINE)
        environment = {
            "ANDROID_SDK_ROOT": str(self.fixture / "sdk"),
            "ANDROID_NDK_HOME": str(self.fixture / "sdk/ndk/27.3.13750724"),
            "JAVA_HOME": str(self.fixture / "jdk"),
            "CONAN_HOME": str(cache),
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            allowed = [os.path.expandvars(entry) for entry in baseline["allowed_path_entries"]]
            os.environ["PATH"] = os.pathsep.join(allowed + ["/usr/local/bin"])
            with self.assertRaisesRegex(DOCTOR.ContractError, "PATH differs"):
                DOCTOR.runtime_preflight(baseline)


if __name__ == "__main__":
    unittest.main()
