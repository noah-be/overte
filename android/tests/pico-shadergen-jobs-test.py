#!/usr/bin/env python3
"""Regression tests for bounded Pico shader build parallelism."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SHADERGEN = ROOT / "tools/shadergen.py"
BUILD_SCRIPT = (ROOT / "android/build-pico.sh").read_text(encoding="utf-8")
CMAKE_BOOTSTRAP = (ROOT / "android/cmake-pico-bootstrap.cmake").read_text(encoding="utf-8")
PICO_CONAN_PROFILE = (ROOT / "android/conan/profiles/pico4-arm64").read_text(encoding="utf-8")
PICO_CONAN_RECIPE = (ROOT / "android/conan/conanfile-pico.py").read_text(encoding="utf-8")
PHONE_QT_BUILD = (ROOT / "android/build-phone-qt-16k.sh").read_text(encoding="utf-8")
PHONE_PREBUILT = (ROOT / "android/phone-prebuilt-16k-deps.sh").read_text(encoding="utf-8")


class ShadergenJobTests(unittest.TestCase):
    def run_empty(self, env=None, *extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / "commands.txt"
            commands.write_text("", encoding="utf-8")
            variables = os.environ.copy()
            variables.update(env or {})
            return subprocess.run([
                sys.executable, str(SHADERGEN), "--commands", str(commands),
                "--build-dir", str(root), "--source-dir", str(ROOT), *extra,
            ], text=True, capture_output=True, env=variables, check=False)

    def test_explicit_worker_limit_is_used(self):
        result = self.run_empty(None, "--jobs", "3", "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using 3 shader worker(s)", result.stdout)

    def test_environment_worker_limit_is_used(self):
        result = self.run_empty({"SHADERGEN_JOBS": "2"}, "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using 2 shader worker(s)", result.stdout)

    def test_non_positive_worker_limit_is_rejected(self):
        result = self.run_empty(None, "--jobs", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs must be positive", result.stderr)

    def test_pico_build_forwards_its_job_limit(self):
        self.assertIn('PICO_BUILD_JOBS="$jobs" CMAKE_BUILD_PARALLEL_LEVEL="$jobs"', BUILD_SCRIPT)
        self.assertIn('SHADERGEN_JOBS="${PICO_SHADER_JOBS:-$jobs}"', BUILD_SCRIPT)

    def test_conan_source_builds_use_the_same_worker_limit(self):
        self.assertEqual(BUILD_SCRIPT.count('-c "tools.build:jobs=$jobs"'), 4)

    def test_restored_qt_package_prevents_a_source_rebuild(self):
        self.assertIn("*/qt*/p/lib/libQt5Core_arm64-v8a.so", BUILD_SCRIPT)

    def test_legacy_mapbox_gl_native_provider_is_disabled(self):
        self.assertIn("-no-feature-geoservices_mapboxgl", PICO_CONAN_PROFILE)

    def test_qt_recipe_uses_reproducible_remote_revision(self):
        self.assertIn("#4fc772a2dbcd84731eb6ff9904e6e358", PICO_CONAN_RECIPE)
        self.assertNotIn("#d59ba2a04fe9ede772b05b0bb0865eb0", PICO_CONAN_RECIPE)

    def test_phone_qt_paths_use_the_same_reproducible_revision(self):
        revision = "#4fc772a2dbcd84731eb6ff9904e6e358"
        legacy = "#d59ba2a04fe9ede772b05b0bb0865eb0"
        for subject in (PHONE_QT_BUILD, PHONE_PREBUILT):
            self.assertIn(revision, subject)
            self.assertNotIn(legacy, subject)

    def test_pico_dependencies_always_provision_pinned_perl_module(self):
        self.assertNotIn("if ! perl -MEnglish -e 1", BUILD_SCRIPT)
        self.assertIn("pico-host-tools/perl", BUILD_SCRIPT)
        self.assertIn("f857b95e26385272525a7519267c8c63648d692608b7633b46d267c38092ccb3", BUILD_SCRIPT)

    def test_native_compile_and_link_use_bounded_cmake_pools(self):
        self.assertIn('PROPERTY JOB_POOLS "android_compile=$ENV{PICO_BUILD_JOBS}" android_link=1', CMAKE_BOOTSTRAP)
        self.assertIn("set(CMAKE_JOB_POOL_COMPILE android_compile)", CMAKE_BOOTSTRAP)
        self.assertIn("set(CMAKE_JOB_POOL_LINK android_link)", CMAKE_BOOTSTRAP)

    def test_release_variant_reuses_checksum_pinned_dependency_configuration(self):
        gradle = (ROOT / "android/apps/picoInterface/build.gradle").read_text(encoding="utf-8")
        self.assertIn("-DCMAKE_MAP_IMPORTED_CONFIG_RELWITHDEBINFO=Debug", gradle)
        self.assertIn("RelWithDebInfo/plugins/libopenxr.so", gradle)
        pico_cmake = (ROOT / "android/apps/picoInterface/CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("IMPORTED_LOCATION_RELWITHDEBINFO", pico_cmake)
        self.assertIn("AUTOMOC_EXECUTABLE", pico_cmake)
        self.assertIn("AUTORCC_EXECUTABLE", pico_cmake)
        self.assertIn("AUTOUIC_EXECUTABLE", pico_cmake)

    def test_pico_build_rejects_invalid_worker_limit_before_building(self):
        variables = os.environ.copy()
        variables["PICO_BUILD_JOBS"] = "0"
        result = subprocess.run(
            [str(ROOT / "android/build-pico.sh"), "--help"],
            text=True, capture_output=True, env=variables, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("PICO_BUILD_JOBS must be a positive integer", result.stderr)

    def test_pico_build_exposes_gradle_stacktraces_for_ci_diagnosis(self):
        self.assertIn('if [[ "$option" == "--stacktrace" ]]', BUILD_SCRIPT)
        self.assertIn('build) build "$command_option" debug ;;', BUILD_SCRIPT)
        self.assertIn('release) build "$command_option" release ;;', BUILD_SCRIPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
