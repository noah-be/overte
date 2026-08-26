#!/usr/bin/env python3
"""Host tests for the Pico APK verifier using synthetic APK archives."""

import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[4]
VERIFIER = ROOT / "android/vr/pico/ci/verify-pico-apk.py"
REQUIRED_LIBRARIES = (
    "libc++_shared.so",
    "libopenxr_loader.so",
    "libpicoInterface.so",
    "libpicoOpenXR.so",
    "libplugins_libopenxr.so",
)
E2E_LAYER_LIBRARY = "libXrApiLayer_overte_e2e_input.so"
E2E_LAYER_MANIFEST = "assets/openxr/1/api_layers/explicit.d/overte_e2e_input.json"
E2E_BUILD_MARKER = b"OVERTE_E2E_OPENXR_INPUT_V1"


class PicoApkVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.aapt = self._tool(
            "aapt",
            "printf \"package: name='${MOCK_PACKAGE:-org.overte.pico}' versionCode='7' versionName='0.4.0'\\n\"\n"
            "printf \"sdkVersion:'26'\\ntargetSdkVersion:'35'\\n\"\n",
        )
        self.apksigner = self._tool(
            "apksigner",
            "test \"${MOCK_SIGNED:-1}\" = 1\n"
            "printf 'Number of signers: %s\\n' \"${MOCK_SIGNERS:-1}\"\n"
            "printf 'Signer #1 certificate SHA-256 digest: %064d\\n' 0\n",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _tool(self, name, body):
        path = self.directory / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _apk(self, *, abi="arm64-v8a", omit=None, extra=None, e2e_layer=False,
             layer_library=None, layer_manifest=None, stale_activation=False):
        apk = self.directory / "pico.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"synthetic")
            for library in REQUIRED_LIBRARIES:
                if library != omit:
                    contents = b"elf"
                    if library == "libplugins_libopenxr.so" and (
                            e2e_layer or stale_activation):
                        contents += E2E_BUILD_MARKER
                    archive.writestr(f"lib/{abi}/{library}", contents)
            if extra:
                archive.writestr(extra, b"unexpected")
            if e2e_layer or layer_library is not None:
                archive.writestr(
                    f"lib/{abi}/{E2E_LAYER_LIBRARY}",
                    b"elf" if layer_library is None else layer_library,
                )
            if e2e_layer or layer_manifest is not None:
                manifest = {
                    "file_format_version": "1.0.0",
                    "api_layer": {
                        "name": "XR_APILAYER_OVERTE_e2e_input",
                        "library_path": E2E_LAYER_LIBRARY,
                        "api_version": "1.0",
                        "implementation_version": "1",
                        "description": "Overte E2E-only bounded OpenXR input layer",
                    },
                }
                archive.writestr(
                    E2E_LAYER_MANIFEST,
                    json.dumps(manifest).encode() if layer_manifest is None else layer_manifest,
                )
        return apk

    def _run(self, apk, env=None, extra_args=()):
        import os
        variables = os.environ.copy()
        variables.update(env or {})
        return subprocess.run(
            [str(VERIFIER), str(apk), "--aapt", str(self.aapt), "--apksigner", str(self.apksigner), *extra_args],
            text=True, capture_output=True, env=variables, check=False,
        )

    def test_accepts_expected_pico_apk_and_emits_manifest(self):
        result = self._run(self._apk())
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["package"], "org.overte.pico")
        self.assertEqual(manifest["abi"], "arm64-v8a")
        self.assertTrue(manifest["signature_verified"])
        self.assertFalse(manifest["e2e_input_layer"])
        self.assertRegex(manifest["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(manifest["signer_certificate_sha256"], r"^[0-9a-f]{64}$")

    def test_records_valid_source_revision(self):
        revision = "a" * 40
        result = self._run(self._apk(), extra_args=("--source-revision", revision))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["source_revision"], revision)

    def test_rejects_ambiguous_source_revision(self):
        result = self._run(self._apk(), extra_args=("--source-revision", "main"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("40-character Git commit", result.stderr)

    def test_rejects_wrong_package(self):
        result = self._run(self._apk(), {"MOCK_PACKAGE": "example.wrong"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected package", result.stderr)

    def test_rejects_missing_required_library(self):
        result = self._run(self._apk(omit="libpicoInterface.so"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("required Pico native libraries", result.stderr)

    def test_rejects_non_arm64_library(self):
        result = self._run(self._apk(extra="lib/x86_64/libunexpected.so"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected only arm64-v8a", result.stderr)

    def test_rejects_failed_signature_verification(self):
        result = self._run(self._apk(), {"MOCK_SIGNED": "0"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("command failed", result.stderr)

    def test_rejects_unexpected_signer_count(self):
        result = self._run(self._apk(), {"MOCK_SIGNERS": "2"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("exactly one APK signer", result.stderr)

    def test_enforces_release_version_and_signer(self):
        good = self._run(self._apk(), extra_args=(
            "--expected-version-code", "7", "--expected-version-name", "0.4.0",
            "--expected-signer-sha256", "0" * 64,
        ))
        self.assertEqual(good.returncode, 0, good.stderr)
        bad_version = self._run(self._apk(), extra_args=("--expected-version-code", "8"))
        self.assertEqual(bad_version.returncode, 2)
        bad_signer = self._run(self._apk(), extra_args=("--expected-signer-sha256", "f" * 64))
        self.assertEqual(bad_signer.returncode, 2)

    def test_debug_requires_complete_e2e_input_layer(self):
        result = self._run(
            self._apk(e2e_layer=True), extra_args=("--expect-e2e-input-layer",),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["e2e_input_layer"])

        missing = self._run(self._apk(), extra_args=("--expect-e2e-input-layer",))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("missing the required", missing.stderr)

    def test_release_mechanically_forbids_e2e_input_layer(self):
        clean = self._run(self._apk(), extra_args=("--forbid-e2e-input-layer",))
        self.assertEqual(clean.returncode, 0, clean.stderr)
        contaminated = self._run(
            self._apk(e2e_layer=True), extra_args=("--forbid-e2e-input-layer",),
        )
        self.assertEqual(contaminated.returncode, 2)
        self.assertIn("release APK must not contain", contaminated.stderr)

        stale = self._run(
            self._apk(stale_activation=True),
            extra_args=("--forbid-e2e-input-layer",),
        )
        self.assertEqual(stale.returncode, 2)
        self.assertIn("activation marker and layer package must match", stale.stderr)

    def test_rejects_incomplete_or_wrong_layer_package(self):
        library_only = self._run(self._apk(layer_library=b"elf"))
        self.assertEqual(library_only.returncode, 2)
        self.assertIn("must be packaged together", library_only.stderr)

        wrong_manifest = json.dumps({
            "file_format_version": "1.0.0",
            "api_layer": {
                "name": "XR_APILAYER_WRONG",
                "library_path": E2E_LAYER_LIBRARY,
                "api_version": "1.0",
                "implementation_version": "1",
            },
        }).encode()
        wrong = self._run(self._apk(e2e_layer=True, layer_manifest=wrong_manifest))
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("does not match the test contract", wrong.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
