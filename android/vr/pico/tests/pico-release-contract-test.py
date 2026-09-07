#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[4]
TOOL = ROOT / "android/vr/pico/ci/pico4-release.py"
VALIDATOR = ROOT / "tools/release/validate-release-bundle.py"
BUILD = ROOT / "android/vr/pico/build.sh"
PREPARE = ROOT / "android/vr/pico/prepare-deps.sh"
SOURCE_GRAPH_COMPATIBILITY = (
    ROOT / "android/vr/pico/release/pico-source-graph-compatibility.py"
)
REVISION = "a" * 40


class PicoReleaseContractTests(unittest.TestCase):
    def run_tool(self, *arguments):
        return subprocess.run([str(TOOL), *arguments], text=True, capture_output=True, check=False)

    def test_derives_unambiguous_android_versions(self):
        result = self.run_tool("--tag", "pico4-v2.3.4-rc.5", "--revision", REVISION)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["version_name"], "2.3.4-rc.5")
        self.assertEqual(value["version_code"], 20304005)

    def test_rejects_mutable_or_non_rc_refs(self):
        for tag in ("main", "pico4-preview-5", "pico4-v1.2.3", "pico4-v1.2.3-rc.0"):
            with self.subTest(tag=tag):
                self.assertEqual(self.run_tool("--tag", tag, "--revision", REVISION).returncode, 2)

    def test_rejects_ref_tag_mismatch(self):
        result = self.run_tool("--tag", "pico4-v1.2.3-rc.1", "--revision", REVISION,
                               "--github-ref", "refs/heads/android-vr-pico")
        self.assertEqual(result.returncode, 2)

    def test_bundle_is_deterministic_and_checks_apk_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            apk = {"apk": "overte-pico4.apk", "sha256": "b" * 64,
                   "version_name": "1.2.3-rc.4", "version_code": "10203004",
                   "source_revision": REVISION}
            (directory / "apk.json").write_text(json.dumps(apk), encoding="utf-8")
            (directory / "deps").write_text(f"{'c' * 64}  dependency.tgz\n", encoding="utf-8")
            args = ("--tag", "pico4-v1.2.3-rc.4", "--revision", REVISION,
                    "--apk-manifest", str(directory / "apk.json"),
                    "--dependency-checksums", str(directory / "deps"))
            for name in ("one", "two"):
                result = self.run_tool(*args, "--output-dir", str(directory / name))
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((directory / "one/SHA256SUMS").read_bytes(),
                             (directory / "two/SHA256SUMS").read_bytes())
            legacy = json.loads((directory / "one/pico4-release-manifest.json").read_text())
            self.assertFalse(legacy["complete_release_bundle"])
            self.assertIn("only", legacy["inventory_scope"])
            apk["version_code"] = "7"
            (directory / "apk.json").write_text(json.dumps(apk), encoding="utf-8")
            self.assertEqual(self.run_tool(*args, "--output-dir", str(directory / "bad")).returncode, 2)

    def test_complete_mode_uses_common_bundle_contract(self):
        scratch = Path(os.environ.get("OVERTE_RELEASE_TEST_TMPDIR", tempfile.gettempdir()))
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            directory = Path(temporary)
            repository = directory / "source-repository"
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email",
                            "test@example.invalid"], check=True)
            (repository / "source.txt").write_text("source\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "source.txt"], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "source"], check=True)
            revision = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True,
                stdout=subprocess.PIPE, check=True,
            ).stdout.strip()
            source = directory / "source.tar"
            subprocess.run([
                "git", "-C", str(repository), "archive", "--format=tar",
                f"--output={source}", revision,
            ], check=True)
            apk = directory / "overte-pico4.apk"
            apk.write_bytes(b"synthetic APK")
            apk_digest = hashlib.sha256(apk.read_bytes()).hexdigest()
            manifest = directory / "apk.json"
            manifest.write_text(json.dumps({
                "apk": apk.name, "sha256": apk_digest,
                "version_name": "1.2.3-rc.4", "version_code": "10203004",
                "source_revision": revision,
            }), encoding="utf-8")
            dependencies = directory / "dependencies.sha256"
            dependencies.write_text(f"{'4' * 64}  dependency.tgz\n", encoding="utf-8")
            inventory = directory / "inventory.json"
            inventory.write_text(json.dumps({
                "schema": "org.overte.release-license-inventory.v1", "complete": True,
                "components": [{
                    "bom_ref": "pkg:conan/runtime@1.0", "name": "runtime",
                    "version": "1.0", "purl": "pkg:conan/runtime@1.0",
                    "source": "https://example.invalid/runtime", "sha256": "5" * 64,
                    "spdx_license": "Apache-2.0",
                    "categories": ["asset", "conan", "font", "native",
                                   "openssl", "qt", "script", "v8"],
                    "notice_files": ["licenses/runtime.txt"],
                }, {
                    "bom_ref": "pkg:maven/example@1.0", "name": "example",
                    "version": "1.0", "purl": "pkg:maven/example@1.0",
                    "source": "https://example.invalid/example", "sha256": "8" * 64,
                    "spdx_license": "Apache-2.0", "categories": ["gradle"],
                    "notice_files": ["licenses/example.txt"],
                }],
            }), encoding="utf-8")
            notices = directory / "notices.zip"
            with zipfile.ZipFile(notices, "w") as archive:
                archive.writestr("NOTICE.txt", "Synthetic notice\n")
                archive.writestr("licenses/runtime.txt", "Apache License 2.0\n")
                archive.writestr("licenses/example.txt", "Apache License 2.0\n")
            environment = directory / "environment.json"
            environment.write_text(json.dumps({
                "schema": "org.overte.release-build-environment.v1",
                "builder_id": "https://github.com/noah-be/overte/actions/runs/1",
                "runner_image": "ubuntu-24.04@sha256:" + "6" * 64,
                "toolchain": {"java": "17", "ndk": "27.3"},
                "actions": [{"name": "actions/checkout", "sha": "7" * 40}],
                "resolved_dependencies": [{
                    "bom_ref": "pkg:conan/runtime@1.0", "recipe_revision": "recipe-r1",
                    "package_revision": "package-r1",
                }],
            }), encoding="utf-8")
            legacy = directory / "legacy"
            bundle = directory / "complete"
            result = self.run_tool(
                "--tag", "pico4-v1.2.3-rc.4", "--revision", revision,
                "--apk-manifest", str(manifest), "--dependency-checksums", str(dependencies),
                "--output-dir", str(legacy), "--complete-bundle-output-dir", str(bundle),
                "--apk", str(apk), "--dependency-inventory", str(inventory),
                "--notice-bundle", str(notices), "--source-archive", str(source),
                "--build-environment", str(environment), "--repository", str(repository),
            )
            self.assertEqual(0, result.returncode, result.stderr)
            validate = subprocess.run([
                str(VALIDATOR), str(bundle), "--product", "pico4",
                "--source-revision", revision,
            ], text=True, capture_output=True, check=False)
            self.assertEqual(0, validate.returncode, validate.stderr)

    def test_complete_mode_rejects_partial_evidence(self):
        result = self.run_tool(
            "--tag", "pico4-v1.2.3-rc.4", "--revision", REVISION,
            "--dependency-inventory", "inventory.json",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("requires --complete-bundle-output-dir", result.stderr)


class PicoSourceGraphCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.graph = self.directory / "graph"
        self.graph.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def adapter(self, body=None):
        path = self.directory / "adapter.py"
        if body is None:
            body = """#!/usr/bin/env python3
import json
import os
import sys

assert sys.argv[1:] == [
    "--graph-root", os.environ["PICO_SOURCE_GRAPH_ROOT"],
    "--pico-root", os.environ["PICO_TEST_EXPECTED_ROOT"],
]
assert os.environ["PICO_SOURCE_GRAPH_MODE"] == "1"
assert os.environ["PICO_SOURCE_GRAPH_VERIFIED"] == "1"
assert os.environ["PICO_LEGACY_DEPENDENCY_PATHS"] == "forbidden"
assert os.environ["PICO_CONAN_REMOTE_POLICY"] == "forbid"
assert os.environ["PICO_CONAN_BUILD_POLICY"] == "source-only"
assert os.environ["PICO_OPENSSL_POLICY"] == "3-only"
assert "CONAN_USER_HOME" not in os.environ
assert "PICO_PREBUILT_RESTORE_ONLY" not in os.environ
assert "PICO_QT_FALLBACK_PATCH" not in os.environ
with open(os.environ["PICO_TEST_RECORD"], "w", encoding="utf-8") as stream:
    json.dump({"graph_root": sys.argv[2], "isolated_home": os.environ["CONAN_HOME"]}, stream)
"""
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_boundary(self, graph=None, adapter=None):
        return subprocess.run([
            str(SOURCE_GRAPH_COMPATIBILITY),
            "--graph-root", str(graph or self.graph),
            "--adapter", str(adapter or self.adapter()),
        ], text=True, capture_output=True, check=False)

    def run_build_boundary(self, graph=None, adapter=None, extra_env=None):
        environment = os.environ.copy()
        environment.update({
            "PICO_SOURCE_GRAPH_ROOT": str(graph or self.graph),
            "PICO_SHARED_GRAPH_ADAPTER": str(adapter or self.adapter()),
            "PICO_TEST_EXPECTED_ROOT": str(ROOT / "android/vr/pico"),
            "PICO_TEST_RECORD": str(self.directory / "adapter-result.json"),
            "CONAN_USER_HOME": "/must/not/reach/adapter",
            "PICO_PREBUILT_RESTORE_ONLY": "1",
            "PICO_QT_FALLBACK_PATCH": "/must/not/reach/adapter.patch",
        })
        environment.update(extra_env or {})
        return subprocess.run(
            [str(BUILD), "deps", "--source-graph"],
            text=True, capture_output=True, env=environment, check=False,
        )

    def test_external_adapter_cannot_replace_the_bound_consumer(self):
        result = self.run_build_boundary()
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("Use the in-tree Pico source-input adapter", result.stderr)
        self.assertFalse((self.directory / "adapter-result.json").exists())

    def test_source_graph_mode_requires_both_explicit_inputs(self):
        environment = os.environ.copy()
        environment.pop("PICO_SOURCE_GRAPH_ROOT", None)
        environment.pop("PICO_SHARED_GRAPH_ADAPTER", None)
        missing_root = subprocess.run(
            [str(BUILD), "deps", "--source-graph"], text=True,
            capture_output=True, env=environment, check=False,
        )
        self.assertEqual(2, missing_root.returncode)
        self.assertIn("PICO_SOURCE_INPUTS_REJECTED", missing_root.stderr)
        environment["PICO_SOURCE_GRAPH_ROOT"] = str(self.graph)
        missing_adapter = subprocess.run(
            [str(BUILD), "deps", "--source-graph"], text=True,
            capture_output=True, env=environment, check=False,
        )
        self.assertEqual(2, missing_adapter.returncode)
        self.assertIn("PICO_SOURCE_INPUTS_REJECTED", missing_adapter.stderr)

    def test_historical_prebuilt_and_openssl_11_payloads_fail_closed(self):
        fixtures = (
            "pico4-qt-conan.tgz",
            ".prebuilt-runtime",
            "lib/libssl.so.1.1",
            "openssl-1.1.1q/source.tar.gz",
        )
        for relative in fixtures:
            with self.subTest(relative=relative):
                path = self.graph / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"forbidden fixture")
                result = self.run_boundary()
                self.assertEqual(2, result.returncode)
                self.assertIn("PICO_SOURCE_GRAPH_COMPATIBILITY=FAIL", result.stderr)
                path.unlink()

    def test_adapter_cannot_restore_legacy_or_resolve_dependencies(self):
        forbidden = (
            "curl artifact",
            "wget artifact",
            "git clone source destination",
            "conan install .",
            "--build=missing",
            "-pr:h default",
            "https://artifactory.overte.org/example",
            "pico4-runtime.tgz",
        )
        for text in forbidden:
            with self.subTest(text=text):
                adapter = self.adapter(f"#!/usr/bin/env bash\n# {text}\nexit 0\n")
                result = self.run_boundary(adapter=adapter)
                self.assertEqual(2, result.returncode)
                self.assertIn("adapter contains forbidden", result.stderr)

    def test_relative_or_escaping_inputs_are_rejected(self):
        relative = subprocess.run([
            str(SOURCE_GRAPH_COMPATIBILITY), "--graph-root", "relative",
            "--adapter", str(self.adapter()),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(2, relative.returncode)
        self.assertIn("must be absolute", relative.stderr)

        outside = self.directory / "outside"
        outside.write_text("outside", encoding="utf-8")
        (self.graph / "escape").symlink_to(outside)
        escaping = self.run_boundary()
        self.assertEqual(2, escaping.returncode)
        self.assertIn("escapes its root", escaping.stderr)

    def test_prepare_defaults_to_read_only_in_tree_consumer(self):
        source = PREPARE.read_text(encoding="utf-8")
        self.assertIn('exec python3 "$script_dir/release/pico-source-inputs.py"', source)
        self.assertNotIn('runtime_dir=', source)
        self.assertNotIn('make ', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
