#!/usr/bin/env python3
"""Device-free contracts for bounded Android Phone build parallelism."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SHADERGEN = ROOT / "tools/shadergen.py"
BUILD = (ROOT / "android/build-phone.sh").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "android/cmake-pico-bootstrap.cmake").read_text(encoding="utf-8")


class PhoneBuildParallelismTests(unittest.TestCase):
    def run_shadergen(self, env=None, *extra):
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

    def test_shader_worker_argument_and_environment_are_bounded(self):
        explicit = self.run_shadergen(None, "--jobs", "3", "--verbose")
        inherited = self.run_shadergen({"SHADERGEN_JOBS": "2"}, "--verbose")
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(inherited.returncode, 0, inherited.stderr)
        self.assertIn("Using 3 shader worker(s)", explicit.stdout)
        self.assertIn("Using 2 shader worker(s)", inherited.stdout)

    def test_invalid_shader_worker_count_is_rejected(self):
        result = self.run_shadergen(None, "--jobs", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs must be positive", result.stderr)

    def test_phone_limit_reaches_gradle_cmake_ninja_and_shaders(self):
        self.assertIn('PICO_BUILD_JOBS="$jobs" CMAKE_BUILD_PARALLEL_LEVEL="$jobs"', BUILD)
        self.assertIn('SHADERGEN_JOBS="$jobs"', BUILD)
        self.assertIn('TMPDIR="$build_tmp"', BUILD)
        self.assertIn('-Djava.io.tmpdir=$build_tmp', BUILD)
        self.assertIn('--max-workers="$jobs"', BUILD)
        self.assertIn('PROPERTY JOB_POOLS "android_compile=$ENV{PICO_BUILD_JOBS}" android_link=1', BOOTSTRAP)
        self.assertIn("set(CMAKE_JOB_POOL_COMPILE android_compile)", BOOTSTRAP)
        self.assertIn("set(CMAKE_JOB_POOL_LINK android_link)", BOOTSTRAP)

    def test_phone_dependency_lookup_honors_isolated_conan_home(self):
        self.assertIn('${CONAN_HOME:-${HOME}/.conan2}/p', BUILD)

    def test_invalid_phone_limit_fails_before_building(self):
        variables = os.environ.copy()
        variables["PHONE_BUILD_JOBS"] = "0"
        result = subprocess.run(
            [str(ROOT / "android/build-phone.sh"), "--help"],
            text=True, capture_output=True, env=variables, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("PHONE_BUILD_JOBS must be a positive integer", result.stderr)

    def test_stacktrace_option_is_forwarded_and_unknown_options_fail(self):
        self.assertIn('if [[ "$option" == "--stacktrace" ]]', BUILD)
        self.assertIn('build) build "$command_option" ;;', BUILD)
        self.assertIn('fail "unsupported build option: $option"', BUILD)


if __name__ == "__main__":
    unittest.main(verbosity=2)
