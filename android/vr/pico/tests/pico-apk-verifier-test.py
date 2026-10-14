#!/usr/bin/env python3
"""Host tests for the Pico APK verifier using synthetic APK archives."""

import json
import importlib.util
import os
import shutil
import sys
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



def network_test_parent():
    """Preview is a test-only dependency, never an APK-verifier product option."""
    if (ROOT / "android/common/web/network_policy.py").is_file():
        return ROOT
    selected = os.environ.get("OVERTE_PICO_NETWORK_TEST_PARENT")
    expected = os.environ.get("OVERTE_PICO_NETWORK_TEST_PARENT_REVISION")
    if not selected or not expected:
        raise RuntimeError("normal network parent is pending; explicitly bind the test preview")
    parent = Path(selected).resolve()
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=parent, text=True).strip()
    if actual != expected or subprocess.check_output(
            ["git", "status", "--porcelain", "--", "android/common/web"], cwd=parent):
        raise RuntimeError("network test preview source mismatch")
    return parent


def verifier_module():
    spec = importlib.util.spec_from_file_location("pico_apk_verifier", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WEB_ROOT = network_test_parent() / "android/common/web"
    return module


NETWORK_NAME = "overte_embedded_web_network_security_config"
NETWORK_FILE = "res/xml/" + NETWORK_NAME + ".xml"
NETWORK_MANIFEST = """<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="org.overte.pico" android:versionCode="7" android:versionName="0.4.0"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>
    <application android:usesCleartextTraffic="true" android:networkSecurityConfig="@xml/overte_embedded_web_network_security_config">
    <meta-data android:name="org.overte.web.NETWORK_CAPABILITY" android:value="overte.android.embedded-web.http-https.v1"/>
    </application></manifest>"""


class PicoApkVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.parent = network_test_parent()
        self.network_config = (self.parent / "android/common/web/res/xml" / (NETWORK_NAME + ".xml")).read_text()
        self.aapt2 = self._tool("aapt2", "if test \"$2\" = xmltree; then\n" +
            "printf 'E: network-security-config (line=1)\\n    E: base-config (line=2)\\n      A: cleartextTrafficPermitted=true\\n        E: trust-anchors (line=3)\\n            E: certificates (line=4)\\n              A: src=\"system\" (Raw: \"system\")\\n'\n" +
            "else printf '  resource 0x7f010000 xml/" + NETWORK_NAME + "\\n    () (file) " + NETWORK_FILE + " type=XML\\n'; fi\n")
        self.analyzer = self.directory / "apkanalyzer-stub"
        self.analyzer.write_text("#!/usr/bin/env python3\nimport sys\n" +
            "print(" + repr(NETWORK_MANIFEST) + " if sys.argv[1] == 'manifest' else " + repr(self.network_config) + ")\n")
        self.analyzer.chmod(0o755)
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
            archive.writestr(NETWORK_FILE, self.network_config)
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
        # Run the actual CLI implementation; only the unpropagated parent path
        # is injected in this explicit host test process. Product CLI has no override.
        driver = ("import importlib.util,sys;from pathlib import Path;"
                  "s=importlib.util.spec_from_file_location('verifier',sys.argv[1]);"
                  "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                  "m.WEB_ROOT=Path(sys.argv[2])/'android/common/web';"
                  "sys.argv=sys.argv[2:];"
                  "exec(\"try: m.main()\\nexcept m.VerificationError as e: print('error: '+str(e),file=sys.stderr);sys.exit(2)\")")
        return subprocess.run(
            [sys.executable, "-c", driver, str(VERIFIER), str(self.parent), str(apk),
             "--aapt", str(self.aapt), "--apksigner", str(self.apksigner),
             "--aapt2", str(self.aapt2), "--apkanalyzer", str(self.analyzer), *extra_args],
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

    def test_rejected_payloads_and_tool_errors_are_not_echoed(self):
        canary = "private-fixture-not-a-real-secret"
        bad_tool = self._tool("failing-tool", "printf '" + canary + "' >&2\nexit 1\n")
        cases = [
            self._run(self._apk(extra="../" + canary)),
            self._run(self._apk(extra="lib/" + canary + "/anything.so")),
            self._run(self._apk(), {"MOCK_PACKAGE": canary}),
            self._run(self._apk(), extra_args=("--apksigner", str(bad_tool))),
            self._run(self._apk(), extra_args=("--unknown-option", canary)),
            self._run(self.directory / canary),
        ]
        for result in cases:
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(canary, result.stdout + result.stderr)
            self.assertNotIn(str(self.directory), result.stdout + result.stderr)

    def test_duplicate_layer_fields_and_symlink_entries_fail_closed(self):
        duplicate = self._run(self._apk(e2e_layer=True,
            layer_manifest=b'{"file_format_version":"1.0.0","file_format_version":"1.0.0","api_layer":{}}'))
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn('duplicate E2E manifest field', duplicate.stderr)
        apk = self._apk()
        with zipfile.ZipFile(apk, 'a') as archive:
            link = zipfile.ZipInfo('assets/unsafe-link')
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, 'private-fixture')
        result = self._run(apk)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('private-fixture', result.stderr)



class PicoBinaryNetworkTests(unittest.TestCase):
    """Actual SDK binary resource decoding; no app/native build or device effect."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pico-network-resource-test-")
        self.directory = Path(self.temporary.name)
        self.module = verifier_module()
        sdk = Path(os.environ.get("ANDROID_SDK_ROOT", str(Path.home() / "Android/Sdk")))
        self.aapt2 = sdk / "build-tools/36.0.0/aapt2"
        self.aapt = sdk / "build-tools/36.0.0/aapt"
        self.analyzer = sdk / "cmdline-tools/latest/bin/apkanalyzer"
        self.android = sdk / "platforms/android-36/android.jar"
        for path in (self.aapt, self.aapt2, self.analyzer, self.android):
            self.assertTrue(path.is_file(), "Actual SDK resource/decoder prerequisite missing")
        self.config = (self.module.WEB_ROOT / "res/xml" / (NETWORK_NAME + ".xml")).read_text()

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, manifest=NETWORK_MANIFEST, configs=None, optimize=False):
        res = self.directory / "res"
        for name, text in (configs or {"xml/" + NETWORK_NAME + ".xml": self.config}).items():
            path = res / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        source = self.directory / "AndroidManifest.xml"
        source.write_text(manifest)
        compiled = self.directory / "compiled.zip"
        apk = self.directory / "resource-only.zip"
        subprocess.run([str(self.aapt2), "compile", "--dir", str(res), "-o", str(compiled)],
                       check=True, capture_output=True, timeout=30)
        subprocess.run([str(self.aapt2), "link", "-I", str(self.android), "--manifest", str(source),
                        "-o", str(apk), str(compiled)], check=True, capture_output=True, timeout=30)
        if optimize:
            optimized = self.directory / "optimized-resource-only.zip"
            subprocess.run([str(self.aapt2), "optimize", "--shorten-resource-paths", "-o", str(optimized), str(apk)],
                           check=True, capture_output=True, timeout=30)
            apk = optimized
        return apk

    def verify(self, apk):
        from types import SimpleNamespace
        return self.module.verify_network_policy(SimpleNamespace(
            apk=apk, aapt2=str(self.aapt2), apkanalyzer=str(self.analyzer)))

    def test_actual_binary_policy_and_optimized_paths_bind_all_consumed_bytes(self):
        result = self.verify(self.fixture(optimize=True))
        self.assertEqual(result["capability"]["androidCleartextScope"], "application")
        self.assertFalse(result["physical_http_or_tls_qualified"])
        configs = set(result["packaged_xml_sha256"]) - {"AndroidManifest.xml"}
        self.assertEqual(configs, set(result["decoded_xml_sha256"]))
        self.assertEqual(len(configs), 1)
        self.assertNotEqual(configs, {NETWORK_FILE})
        self.assertGreater(len(result["decoder_inputs_sha256"]), 2)
        self.assertEqual(len(result["source_inputs_sha256"]), 4)
        for digest in [*result["packaged_xml_sha256"].values(), result["resource_inventory_sha256"]]:
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_actual_qualifier_override_cannot_add_user_ca(self):
        configs = {"xml/" + NETWORK_NAME + ".xml": self.config,
                   "xml-v28/" + NETWORK_NAME + ".xml": self.config.replace('src="system"', 'src="user"')}
        with self.assertRaisesRegex(self.module.VerificationError, "network capability"):
            self.verify(self.fixture(configs=configs))

    def test_actual_duplicate_marker_fails_closed(self):
        marker = '<meta-data android:name="org.overte.web.NETWORK_CAPABILITY" android:value="overte.android.embedded-web.http-https.v1"/>'
        with self.assertRaisesRegex(self.module.VerificationError, "network capability"):
            self.verify(self.fixture(manifest=NETWORK_MANIFEST.replace(marker, marker + marker)))

    def test_actual_wrong_resource_id_fails_closed(self):
        configs = {"xml/" + NETWORK_NAME + ".xml": self.config, "xml/other.xml": self.config}
        with self.assertRaisesRegex(self.module.VerificationError, "network capability"):
            self.verify(self.fixture(manifest=NETWORK_MANIFEST.replace('@xml/' + NETWORK_NAME, '@xml/other'), configs=configs))

    def test_actual_missing_marker_fails_closed(self):
        manifest = NETWORK_MANIFEST.replace('org.overte.web.NETWORK_CAPABILITY', 'unrelated.marker')
        with self.assertRaisesRegex(self.module.VerificationError, "network capability"):
            self.verify(self.fixture(manifest=manifest))

    def test_parent_execution_uses_bound_source_bytes_not_cached_code(self):
        import py_compile
        import importlib.util
        parent = self.directory / "explicit-parent-cache-boundary"
        for relative in ("network_policy.py", "network-capability.json",
                         "res/xml/" + NETWORK_NAME + ".xml"):
            destination = parent / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((self.module.WEB_ROOT / relative).read_bytes())
        helper = parent / "network_policy.py"
        original = helper.read_bytes()
        # A real timestamp/size-valid pyc from different code must not replace
        # the source bytes bound by this verifier's receipt.
        stale = b"raise RuntimeError('unexpected cached policy execution')\n"
        helper.write_bytes(stale + b" " * (len(original) - len(stale)))
        stamp = helper.stat()
        py_compile.compile(str(helper), doraise=True)
        helper.write_bytes(original)
        os.utime(helper, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        cached = importlib.util.cache_from_source(str(helper))
        self.assertTrue(Path(cached).is_file())
        self.module.WEB_ROOT = parent
        result = self.verify(self.fixture())
        import hashlib
        self.assertEqual(result["source_inputs_sha256"][str(helper)], hashlib.sha256(original).hexdigest())
        self.assertEqual(result["capability"]["androidCleartextScope"], "application")


    def test_actual_artifact_mutation_is_rejected_by_full_verifier(self):
        import argparse
        from unittest.mock import patch
        apk = self.fixture()
        with zipfile.ZipFile(apk, "a") as archive:
            for name in REQUIRED_LIBRARIES:
                archive.writestr("lib/arm64-v8a/" + name, b"explicit host native boundary")
        signer = self.directory / "apksigner-stub"
        signer.write_text("#!/bin/sh\nprintf 'Number of signers: 1\\nSigner #1 certificate SHA-256 digest: %064d\\n' 0\n")
        signer.chmod(0o755)
        parser = argparse.ArgumentParser()
        self.module.add_candidate_arguments(parser)
        args = parser.parse_args([str(apk), "--aapt", str(self.aapt), "--aapt2", str(self.aapt2),
                                  "--apkanalyzer", str(self.analyzer), "--apksigner", str(signer)])
        verified = self.module.verify_candidate(args)
        self.assertEqual(verified["network_capability"]["capability"]["androidCleartextScope"], "application")
        actual = self.module.verify_network_policy
        def mutate(arguments):
            result = actual(arguments)
            with zipfile.ZipFile(apk, "a") as archive:
                archive.writestr("late-change.txt", b"changed")
            return result
        with patch.object(self.module, "verify_network_policy", side_effect=mutate):
            with self.assertRaisesRegex(self.module.VerificationError, "candidate bytes changed"):
                self.module.verify_candidate(args)

    def test_tree_duplicates_and_unknown_decoder_tokens_fail_closed(self):
        for text in ('E: network-security-config (line=1)\n  A: src="system"\n  A: src="user"',
                     'E: network-security-config (line=1)\n  A: src="system" (Raw: "user")',
                     'E: network-security-config (line=1)\nUNKNOWN: ignored',
                     'E: network-security-config (line=1)\nE: unrelated (line=2)'):
            with self.subTest(text=text):
                with self.assertRaises(self.module.VerificationError):
                    self.module.network_xml_from_aapt2(text)


    def test_decoder_must_deliver_every_selected_configuration(self):
        from unittest.mock import patch
        configs = {"xml/" + NETWORK_NAME + ".xml": self.config,
                   "xml-v28/" + NETWORK_NAME + ".xml": self.config}
        apk = self.fixture(configs=configs)
        real = self.module.run_tool
        decoded = []
        def decode(command):
            if "--file" in command:
                decoded.append(command[command.index("--file") + 1])
                if len(decoded) == 2:
                    self.module.fail("command failed")
            return real(command)
        with patch.object(self.module, "run_tool", side_effect=decode):
            with self.assertRaisesRegex(self.module.VerificationError, "command failed"):
                self.verify(apk)
        self.assertEqual(len(decoded), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
