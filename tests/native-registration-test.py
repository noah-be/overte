#!/usr/bin/env python3
"""Exercise native test discovery with real CMake, without product dependencies.

The production tests/CMakeLists.txt is copied unchanged into a temporary tree.
Child CMake files are stubs: this checks registration and failure propagation,
not compilation or execution of the native Overte tests themselves.
"""

from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest


TESTS = Path(__file__).resolve().parent


class NativeRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for command in ("cmake", "ctest"):
            if not shutil.which(command):
                raise RuntimeError(f"{command} is required for native registration tests")
        if shutil.which("ninja"):
            cls.generator = "Ninja"
        elif shutil.which("make"):
            cls.generator = "Unix Makefiles"
        else:
            raise RuntimeError("Ninja or make is required for native registration tests")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="overte-native-registration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.build = self.root / "build"
        self.fixture_tests = self.source / "tests"
        self.fixture_tests.mkdir(parents=True)
        (self.source / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.16)\n"
            "project(NativeRegistrationFixture NONE)\n"
            "enable_testing()\n"
            "add_subdirectory(tests)\n",
            encoding="utf-8",
        )
        shutil.copyfile(TESTS / "CMakeLists.txt", self.fixture_tests / "CMakeLists.txt")

        # Mirror every real direct child, including Python/JS/device-test folders.
        self.native_groups = set()
        for child in sorted(TESTS.iterdir()):
            if not child.is_dir():
                continue
            fixture = self.fixture_tests / child.name
            fixture.mkdir()
            if not (child / "CMakeLists.txt").is_file():
                continue
            if child.name == "shaders":
                body = "# Shader tests remain disabled.\n"
            elif child.name == "recording":
                body = (
                    "add_custom_target(recording-test\n"
                    '  COMMAND "${CMAKE_COMMAND}" -E touch "${CMAKE_BINARY_DIR}/recording.built")\n'
                )
            else:
                self.native_groups.add(child.name)
                body = (
                    'add_custom_target("${TEST_PROJ_NAME}-stub"\n'
                    '  COMMAND "${CMAKE_COMMAND}" -E touch "${CMAKE_BINARY_DIR}/${TEST_PROJ_NAME}.built")\n'
                    'add_test(NAME "${TEST_PROJ_NAME}-stub" COMMAND "${CMAKE_COMMAND}" -E true)\n'
                    'list(APPEND ALL_TEST_TARGETS "${TEST_PROJ_NAME}-stub")\n'
                    'set(ALL_TEST_TARGETS "${ALL_TEST_TARGETS}" PARENT_SCOPE)\n'
                )
            (fixture / "CMakeLists.txt").write_text(body, encoding="utf-8")

        self.assertTrue(self.native_groups, "The fixture must contain native test groups")
        # These can appear after ordinary host checks, regardless of checkout state.
        for name in ("__pycache__", "device", "javascript", "performance"):
            (self.fixture_tests / name).mkdir(exist_ok=True)
        # Preserve the existing explicit exclusions, even with CMake files present.
        for name in ("CMakeFiles", "mocha"):
            directory = self.fixture_tests / name
            directory.mkdir(exist_ok=True)
            (directory / "CMakeLists.txt").write_text(
                'message(FATAL_ERROR "Excluded directory must not be configured")\n',
                encoding="utf-8",
            )

    def run_command(self, *command, cwd=None):
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )

    def configure(self):
        return self.run_command(
            "cmake", "-S", str(self.source), "-B", str(self.build), "-G", self.generator
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_native_groups_are_discovered_and_built(self):
        self.assert_success(self.configure())
        discovery = self.run_command("ctest", "--show-only=json-v1", cwd=self.build)
        self.assert_success(discovery)
        names = {test["name"] for test in json.loads(discovery.stdout)["tests"]}
        self.assertEqual(names, {f"{name}-stub" for name in self.native_groups})
        self.assert_success(self.run_command("ctest", "--output-on-failure", cwd=self.build))
        self.assert_success(self.run_command("cmake", "--build", str(self.build), "--target", "all-tests"))
        built = {path.stem for path in self.build.glob("*.built")}
        self.assertEqual(built, self.native_groups)

        # The recording executable remains manually buildable, outside all-tests/CTest.
        self.assert_success(self.run_command("cmake", "--build", str(self.build), "--target", "recording-test"))
        self.assertTrue((self.build / "recording.built").is_file())

    def test_native_configuration_errors_are_not_hidden(self):
        child = self.fixture_tests / sorted(self.native_groups)[0] / "CMakeLists.txt"
        with child.open("a", encoding="utf-8") as handle:
            handle.write('message(FATAL_ERROR "Deliberate native configuration failure")\n')
        result = self.configure()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Deliberate native configuration failure", result.stdout)

    def test_native_build_errors_fail_all_tests_target(self):
        child = self.fixture_tests / sorted(self.native_groups)[0] / "CMakeLists.txt"
        body = child.read_text(encoding="utf-8")
        child.write_text(
            body.replace('-E touch "${CMAKE_BINARY_DIR}/${TEST_PROJ_NAME}.built"', "-E false"),
            encoding="utf-8",
        )
        self.assert_success(self.configure())
        result = self.run_command("cmake", "--build", str(self.build), "--target", "all-tests")
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_native_test_errors_fail_ctest(self):
        name = sorted(self.native_groups)[0]
        child = self.fixture_tests / name / "CMakeLists.txt"
        child.write_text(child.read_text(encoding="utf-8").replace("-E true", "-E false"), encoding="utf-8")
        self.assert_success(self.configure())
        result = self.run_command("ctest", "--output-on-failure", cwd=self.build)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"{name}-stub", result.stdout)


if __name__ == "__main__":
    unittest.main()
