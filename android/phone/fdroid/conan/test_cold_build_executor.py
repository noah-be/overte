import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
INNER = ROOT / "android/phone/fdroid/scripts/build-dependencies.sh"
OUTER = ROOT / "android/phone/fdroid/scripts/cold-build.sh"


class ColdBuildExecutorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inner = INNER.read_text(encoding="utf-8")
        cls.outer = OUTER.read_text(encoding="utf-8")

    def test_scripts_are_syntactically_executable(self):
        subprocess.run(["sh", "-n", str(INNER)], check=True)
        subprocess.run(["bash", "-n", str(OUTER)], check=True)

    def test_all_graph_builds_are_exact_and_source_forced(self):
        commands = re.findall(r"conan install .*?(?=\n\s*checkpoint)", self.inner, re.S)
        self.assertEqual(3, len(commands))
        for command in commands:
            self.assertIn("--lockfile=", command)
            self.assertIn("-pr:h", command)
            self.assertIn("-pr:b", command)
            self.assertIn("--no-remote", command)
            self.assertIn("--build='*'", command)
            self.assertNotIn("--build=missing", command)
            self.assertNotIn("-pr:b default", command)

    def test_network_and_cache_fail_closed_before_build(self):
        preflight = self.inner.split("preflight()", 1)[1].split("if [ \"$mode\" = --prepare ]", 1)[0]
        self.assertIn("/proc/net/route", preflight)
        self.assertIn("Conan cache is not empty", preflight)
        self.assertIn("stale binary output exists", preflight)
        self.assertIn("less than 80 GiB free", preflight)

    def test_outer_executor_pins_image_and_dual_network_isolation(self):
        self.assertIn("localhost/overte-sh001-fdroid-toolchain:three-gates", self.outer)
        self.assertIn("--network=none", self.outer)
        self.assertIn("source_closure_store.py\" verify", self.outer)
        self.assertIn("12884901888", self.outer)
        self.assertIn("--offline", self.outer)

    def test_resume_is_bound_to_the_same_protected_attempt(self):
        for binding in (
            "source_commit=",
            "source_closure_sha256=",
            "recipe_index_sha256=",
            "toolchain_image_id=",
            "gradle_complete_sha256=",
        ):
            self.assertIn(binding, self.outer)
        self.assertIn("--resume", self.outer)
        self.assertIn("OVERTE_RESUME=1", self.outer)
        self.assertIn("valid_checkpoint", self.inner)
        self.assertIn("result_sha256=", self.inner)
        self.assertIn("manifest_sha256=", self.inner)

    def test_exact_locks_exist(self):
        for name in (
            "bootstrap-linux-x86_64.lock",
            "host-tools-linux-x86_64.lock",
            "android-arm64-v8a-api26-16k.lock",
        ):
            self.assertTrue((ROOT / "android/phone/fdroid/locks" / name).is_file())


if __name__ == "__main__":
    unittest.main()
