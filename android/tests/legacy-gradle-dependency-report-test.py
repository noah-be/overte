#!/usr/bin/env python3
"""Hermetic tests for the legacy Gradle dependency-report harness."""

import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

SCRIPT = Path(__file__).parent / "legacy-gradle/run_dependency_report.py"
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("legacy_report", SCRIPT)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class LegacyGradleReportTest(unittest.TestCase):
    def test_official_distribution_identity_is_immutable(self):
        self.assertEqual("https://services.gradle.org/distributions/gradle-6.5-bin.zip", report.GRADLE_URL)
        self.assertEqual("23e7d37e9bb4f8dabb8a3ea7fdee9dd0428b9b1a71d298aefd65b11dccea220f", report.GRADLE_SHA256)

    def test_offline_missing_distribution_never_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            downloader = mock.Mock()
            with self.assertRaisesRegex(report.HarnessError, "unavailable offline"):
                report.ensure_distribution(Path(directory), False, downloader)
            downloader.assert_not_called()

    def test_checksum_mismatch_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            def bad_download(_url, destination):
                destination.write_bytes(b"wrong")
            with self.assertRaisesRegex(report.HarnessError, "checksum mismatch"):
                report.ensure_distribution(cache, True, bad_download)
            self.assertFalse((cache / "downloads/gradle-6.5-bin.zip").exists())

    def test_zip_rejects_escape_and_symlink(self):
        for name, attributes in (("../escape", 0), ("gradle-6.5/link", 0o120777 << 16)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "bad.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    item = zipfile.ZipInfo(name)
                    item.external_attr = attributes
                    output.writestr(item, "x")
                with self.assertRaises(report.HarnessError):
                    report.safe_zip_extract(archive, Path(directory) / "out")

    def test_zip_preserves_executable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "gradle.zip"
            with zipfile.ZipFile(archive, "w") as output:
                item = zipfile.ZipInfo("gradle-6.5/bin/gradle")
                item.create_system = 3
                item.external_attr = (0o100755 << 16)
                output.writestr(item, "#!/bin/sh\n")
            destination = Path(directory) / "out"
            report.safe_zip_extract(archive, destination)
            executable = destination / "gradle-6.5/bin/gradle"
            self.assertTrue(executable.is_file())
            self.assertTrue(executable.stat().st_mode & 0o111)

    def test_tar_rejects_links_and_parent_escape(self):
        for name, link in (("../escape", False), ("source/link", True)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "bad.tar"
                with tarfile.open(archive, "w") as output:
                    item = tarfile.TarInfo(name)
                    item.type = tarfile.SYMTYPE if link else tarfile.REGTYPE
                    item.linkname = "target" if link else ""
                    item.size = 0
                    output.addfile(item, io.BytesIO())
                with self.assertRaises(report.HarnessError):
                    report.safe_tar_extract(archive, Path(directory) / "out")

    def test_java_gate_requires_complete_java_8(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "bin").mkdir()
            for executable in ("java", "javac"):
                path = home / "bin" / executable
                path.write_text("#!/bin/sh\n", encoding="utf-8")
                path.chmod(0o755)
            def fake(command, _env, _cwd, _timeout):
                return subprocess.CompletedProcess(command, 0, "", 'openjdk version "17"')
            with self.assertRaisesRegex(report.HarnessError, "not Java 8"):
                report.gate_java(home, fake)

    def test_gradle_gate_requires_pinned_version_and_java(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / "bin/gradle").write_text("", encoding="utf-8")
            result = lambda command, env, cwd, timeout: subprocess.CompletedProcess(command, 0, "Gradle 8.13\nJVM: 1.8", "")
            with self.assertRaisesRegex(report.HarnessError, "toolchain gate"):
                report.gate_gradle(root, root, result)

    def test_sanitizer_replaces_longest_private_path_first(self):
        self.assertEqual("<source>/file <cache>", report.sanitize(
            "/private/cache/source/file /private/cache",
            {Path("/private/cache"): "<cache>", Path("/private/cache/source"): "<source>"}))

    def test_cli_requires_explicit_network_boundary(self):
        with self.assertRaises(SystemExit):
            report.main(["toolchain"])

    def test_report_contract_owns_exact_modules_and_pico_exclusion(self):
        self.assertEqual(("qt", "oculus", "interface", "questInterface", "framePlayer", "questFramePlayer"),
                         report.REPORTED_MODULES)
        self.assertEqual("picoInterface", report.EXCLUDED_MODULES[0]["name"])

    def test_unresolved_dependencies_are_structured_and_deduplicated(self):
        output = """> Task :interface:dependencies
debugCompileClasspath - Resolved configuration for compilation
+--- com.google.vr:sdk-base:1.80.0 FAILED
+--- com.google.vr:sdk-base:1.80.0 FAILED
releaseCompileClasspath - Resolved configuration for compilation
\\--- project :qt FAILED
"""
        self.assertEqual([
            {"module": "interface", "configuration": "debugCompileClasspath",
             "dependency": "com.google.vr:sdk-base:1.80.0"},
            {"module": "interface", "configuration": "releaseCompileClasspath",
             "dependency": "project :qt"},
        ], report.unresolved_dependencies(output))

    def test_unresolved_dependencies_ignore_failure_prose_without_tree_context(self):
        self.assertEqual([], report.unresolved_dependencies(
            "Could not resolve com.example:missing:1\nBUILD FAILED\n"
            "> Task :interface:dependencies\ncom.example:missing:1 FAILED\n"))

    def test_resolve_uses_isolated_offline_command_and_transactional_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation, java = root / "gradle", root / "java"
            (installation / "bin").mkdir(parents=True)
            (installation / "bin/gradle").write_text("", encoding="utf-8")
            cache, output = root / "cache", root / "reports"
            commands = []
            isolated_configuration = []
            def fake_runner(command, env, cwd, _timeout):
                commands.append(command)
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")
                isolated_configuration.append((
                    cwd,
                    (cwd / "local.properties").read_text(encoding="utf-8"),
                    env["ANDROID_NDK_HOME"]))
                return subprocess.CompletedProcess(command, 0, "dependency graph\n", "")
            def fake_snapshot(staging, _revision, _runner):
                source = staging / "source"
                (source / "android").mkdir(parents=True)
                return source
            sdk = root / "sdk"
            sdk.mkdir()
            ndk = root / "ndk"
            ndk.mkdir()
            with mock.patch.dict("os.environ", {
                    "ANDROID_HOME": str(sdk),
                    "OVERTE_LEGACY_NDK_HOME": str(ndk)}, clear=False), \
                    mock.patch.object(report, "source_snapshot", fake_snapshot):
                self.assertTrue(report.resolve(cache, installation, java, output, False, fake_runner))
            gradle = commands[-1]
            self.assertIn("--offline", gradle)
            self.assertIn("--no-daemon", gradle)
            self.assertIn("--stacktrace", gradle)
            self.assertIn("--project-cache-dir", gradle)
            self.assertIn("-PVERSION_CODE=1", gradle)
            self.assertIn("-PRELEASE_NUMBER=1.0", gradle)
            self.assertIn("-PSUPPRESS_PICO_INTERFACE", gradle)
            self.assertEqual([f":{name}:dependencies" for name in report.REPORTED_MODULES], gradle[-6:])
            self.assertEqual(1, len(isolated_configuration))
            isolated_cwd, local_properties, configured_ndk = isolated_configuration[0]
            self.assertNotEqual(report.ANDROID_ROOT, isolated_cwd)
            self.assertIn(f"sdk.dir={sdk}", local_properties)
            self.assertIn(f"ndk.dir={ndk}", local_properties)
            self.assertEqual(str(ndk), configured_ndk)
            current = output / "current"
            self.assertTrue((current / ".complete").is_file())
            result = __import__("json").loads((current / "result.json").read_text())
            self.assertTrue(result["resolutionSucceeded"])
            self.assertTrue(result["gradleCommandSucceeded"])
            self.assertEqual([], result["unresolvedDependencies"])
            self.assertFalse(result["artifactsVerified"])
            self.assertFalse(result["sbom"])

    def test_unresolved_marker_cannot_leave_stale_complete_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation, java = root / "gradle", root / "java"
            (installation / "bin").mkdir(parents=True)
            (installation / "bin/gradle").write_text("", encoding="utf-8")
            output = root / "reports"
            old = output / "current"
            old.mkdir(parents=True)
            (old / ".overte-legacy-gradle-report").write_text("1\n")
            (old / ".complete").write_text("stale\n")
            def fake_runner(command, _env, _cwd, _timeout):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, "b" * 40 + "\n", "")
                return subprocess.CompletedProcess(command, 0, "module -> FAILED\n", "")
            def fake_snapshot(staging, _revision, _runner):
                source = staging / "source"
                (source / "android").mkdir(parents=True)
                return source
            sdk = root / "sdk"
            sdk.mkdir()
            ndk = root / "ndk"
            ndk.mkdir()
            with mock.patch.dict("os.environ", {
                    "ANDROID_HOME": str(sdk),
                    "OVERTE_LEGACY_NDK_HOME": str(ndk)}, clear=False), \
                    mock.patch.object(report, "source_snapshot", fake_snapshot):
                self.assertFalse(report.resolve(root / "cache", installation, java, output, True, fake_runner))
            self.assertFalse((output / "current/.complete").exists())
            result = __import__("json").loads((output / "current/result.json").read_text())
            self.assertTrue(result["gradleCommandSucceeded"])

    def test_nonzero_gradle_command_is_distinct_from_unresolved_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation, java = root / "gradle", root / "java"
            (installation / "bin").mkdir(parents=True)
            (installation / "bin/gradle").write_text("", encoding="utf-8")
            output = root / "reports"
            def fake_runner(command, _env, _cwd, _timeout):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, "c" * 40 + "\n", "")
                return subprocess.CompletedProcess(command, 7, "", "BUILD FAILED\n")
            def fake_snapshot(staging, _revision, _runner):
                source = staging / "source"
                (source / "android").mkdir(parents=True)
                return source
            sdk, ndk = root / "sdk", root / "ndk"
            sdk.mkdir()
            ndk.mkdir()
            with mock.patch.dict("os.environ", {
                    "ANDROID_HOME": str(sdk),
                    "OVERTE_LEGACY_NDK_HOME": str(ndk)}, clear=False), \
                    mock.patch.object(report, "source_snapshot", fake_snapshot):
                self.assertFalse(report.resolve(
                    root / "cache", installation, java, output, True, fake_runner))
            result = __import__("json").loads((output / "current/result.json").read_text())
            self.assertFalse(result["gradleCommandSucceeded"])
            self.assertEqual([], result["unresolvedDependencies"])

    def test_report_refuses_foreign_and_symlinked_current(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "reports"
                output.mkdir()
                if symlink:
                    target = root / "target"
                    target.mkdir()
                    (output / "current").symlink_to(target, target_is_directory=True)
                else:
                    (output / "current").mkdir()
                with self.assertRaises(report.HarnessError):
                    report.resolve(root / "cache", root / "gradle", root / "java", output, False)

    def test_missing_sdk_publishes_red_precondition_and_removes_stale_green(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "reports"
            current = output / "current"
            current.mkdir(parents=True)
            (current / ".overte-legacy-gradle-report").write_text("1\n")
            (current / ".complete").write_text("stale\n")
            with mock.patch.dict("os.environ", {"ANDROID_HOME": "", "ANDROID_SDK_ROOT": ""}):
                self.assertFalse(report.resolve(root / "cache", root / "gradle", root / "java",
                                                output, False, mock.Mock()))
            result = __import__("json").loads((current / "result.json").read_text())
            self.assertEqual("precondition_failed", result["status"])
            self.assertFalse(result["dependencyResolutionAttempted"])
            self.assertFalse(result["resolvedGraph"])
            self.assertFalse((current / ".complete").exists())

    def test_missing_ndk_publishes_red_precondition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = root / "sdk"
            sdk.mkdir()
            output = root / "reports"
            with mock.patch.dict("os.environ", {
                    "ANDROID_HOME": str(sdk),
                    "ANDROID_SDK_ROOT": "",
                    "OVERTE_LEGACY_NDK_HOME": ""}):
                self.assertFalse(report.resolve(
                    root / "cache", root / "gradle", root / "java",
                    output, False, mock.Mock()))
            result = __import__("json").loads(
                (output / "current/result.json").read_text())
            self.assertEqual("precondition_failed", result["status"])
            self.assertEqual("android_ndk", result["precondition"])
            self.assertFalse(result["dependencyResolutionAttempted"])


if __name__ == "__main__":
    unittest.main()
