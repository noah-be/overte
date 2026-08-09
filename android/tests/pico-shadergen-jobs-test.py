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

    def test_native_compile_and_link_use_bounded_cmake_pools(self):
        self.assertIn('PROPERTY JOB_POOLS "pico_compile=$ENV{PICO_BUILD_JOBS}" pico_link=1', CMAKE_BOOTSTRAP)
        self.assertIn("set(CMAKE_JOB_POOL_COMPILE pico_compile)", CMAKE_BOOTSTRAP)
        self.assertIn("set(CMAKE_JOB_POOL_LINK pico_link)", CMAKE_BOOTSTRAP)

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
