import json
import re
import shutil
import subprocess
import sys
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
        commands = re.findall(r"^  conan_install (?:linux|android) .*?(?=\n\s*checkpoint)", self.inner, re.S | re.M)
        self.assertEqual(3, len(commands))
        for command in commands:
            self.assertIn("--lockfile=", command)
            self.assertIn("-pr:h", command)
            self.assertIn("-pr:b", command)
            self.assertIn("--no-remote", command)
            self.assertIn("--build='*'", command)
            self.assertNotIn("--build=missing", command)
            self.assertNotIn("-pr:b default", command)

    def test_foreign_archive_owner_does_not_strip_executable_permissions(self):
        # Exercise the tarfile behavior used by Conan in the real namespace
        # type. The unfiltered control reproduces the NASM 2.15.05 failure.
        self.assertIn("'tools.files.unzip:filter=data'", self.inner)
        if not shutil.which('unshare'):
            self.skipTest('Linux user namespaces unavailable')
        prefix = ['unshare', '--user', '--map-root-user', '--net']
        probe = subprocess.run(prefix + [sys.executable, '-c', 'pass'], capture_output=True)
        if probe.returncode:
            self.skipTest('host forbids user/network namespaces; build preflight rejects this host')
        script = r'''
import io, os, pathlib, subprocess, tarfile, tempfile
os.umask(0o022)
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    archive = root / 'source.tar.xz'
    with tarfile.open(archive, 'w:xz') as tar:
        item = tarfile.TarInfo('configure')
        body = b'#!/bin/sh\nprintf executable\n'
        item.size, item.mode, item.uid, item.gid = len(body), 0o775, 802, 900
        tar.addfile(item, io.BytesIO(body))
    for name, filter_ in [('control', lambda member, _: member), ('fixed', 'data')]:
        dest = root / name
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter=filter_)
        executable = dest / 'configure'
        if name == 'control':
            assert not (executable.stat().st_mode & 0o111), 'control no longer reproduces the failure'
        else:
            assert executable.stat().st_mode & 0o100
            assert subprocess.check_output([str(executable)]) == b'executable'
'''
        subprocess.run(prefix + [sys.executable, '-c', script], check=True, timeout=20)

    def test_network_and_cache_fail_closed_before_build(self):
        preflight = self.inner.split("preflight()", 1)[1].split("if [ \"$mode\" = --prepare ]", 1)[0]
        self.assertIn("/proc/net/route", preflight)
        self.assertIn("Conan cache is not empty", preflight)
        self.assertIn("stale binary output exists", preflight)
        self.assertIn("invalid available-space reading", preflight)

    def test_outer_executor_pins_image_and_dual_network_isolation(self):
        self.assertIn("localhost/overte-sh001-fdroid-toolchain:three-gates", self.outer)
        self.assertIn("--network=none", self.outer)
        self.assertIn("source_closure_store.py\" verify", self.outer)
        self.assertIn("12884901888", self.outer)
        self.assertIn("--offline", self.outer)

    def test_user_authorized_no_additional_start_reserve(self):
        manifest = json.loads((ROOT / "android/phone/fdroid/manifests/recipe-source.lock.json").read_text())
        # Locate the actual original admission expressions, not a replacement
        # arithmetic implementation. No executor, container or build is launched.
        inner = next(line.strip() for line in self.inner.splitlines()
                     if line.strip().startswith('[ "$available" -ge '))
        outer = next(line.strip() for line in self.outer.splitlines()
                     if line.strip().startswith('(( available >= '))
        self.assertEqual(0, manifest["cold_build"]["minimum_free_bytes"])
        for shell, expression in (("sh", inner), ("bash", outer)):
            for available in (-1, 0, 1, 50000000000, 59999999999, 60000000000):
                with self.subTest(shell=shell, available=available):
                    result = subprocess.run(
                        [shell, "-c", 'available="$1"\n' + expression, "floor-test", str(available)],
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(0 if available >= 0 else 1, result.returncode)
                    if available < 0:
                        self.assertIn("invalid available-space reading", result.stderr)

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
