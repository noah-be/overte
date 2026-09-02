#!/usr/bin/env python3
"""Hardware-free contracts for the Conan cache isolation helper."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANAGER_PATH = HERE / "conan_cache_manager.py"
SPEC = importlib.util.spec_from_file_location("overte_conan_cache_manager", MANAGER_PATH)
MANAGER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MANAGER)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class ConanCacheManagerTest(unittest.TestCase):
    def prepare(self, root: Path, role: str, environment: Path,
                *extra: str) -> int:
        return MANAGER.main([
            "prepare", "--root", str(root), "--role", role,
            *extra, "--env-file", str(environment),
        ])

    def test_roles_get_distinct_private_writable_homes_and_safe_env_files(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-test-") as name:
            temporary = Path(name)
            root = temporary / "managed"
            phone_env = temporary / "phone.env"
            pico_env = temporary / "pico.env"
            self.assertEqual(0, self.prepare(root, "android-phone", phone_env))
            self.assertEqual(0, self.prepare(root, "android-pico", pico_env))

            phone = root / "homes/android-phone"
            pico = root / "homes/android-pico"
            self.assertNotEqual(phone, pico)
            for path in (root, root / "homes", phone, pico):
                self.assertEqual(0o700, mode(path))
            for path in (phone_env, pico_env):
                self.assertEqual(0o600, mode(path))
            self.assertIn(f"CONAN_HOME={phone}", phone_env.read_text(encoding="utf-8"))
            self.assertIn(
                f"PHONE_SHARED_CONAN_HOME={phone}", phone_env.read_text(encoding="utf-8"))
            self.assertIn(f"CONAN_HOME={pico}", pico_env.read_text(encoding="utf-8"))
            self.assertNotIn("PHONE_SHARED_CONAN_HOME", pico_env.read_text(encoding="utf-8"))
            self.assertNotIn("serial", str(phone))
            self.assertNotIn("serial", str(pico))

    def test_run_exports_conan_home_to_unchanged_child_build(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-run-test-") as name:
            temporary = Path(name)
            result_file = temporary / "child-environment"
            result = subprocess.run([
                sys.executable, str(MANAGER_PATH), "run",
                "--root", str(temporary / "managed"),
                "--role", "android-phone", "--",
                sys.executable, "-c",
                "import os,pathlib; pathlib.Path(os.environ['RESULT']).write_text("
                "os.environ['CONAN_HOME'] + '\\n' + os.environ['PHONE_SHARED_CONAN_HOME'])",
            ], env={**os.environ, "RESULT": str(result_file),
                    "PHONE_SHARED_CONAN_HOME": str(temporary / "wrong")}, text=True,
               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            values = result_file.read_text(encoding="utf-8").splitlines()
            expected = str(temporary / "managed/homes/android-phone")
            self.assertEqual([expected, expected], values)

    def test_phone_and_pico_can_run_together_but_same_role_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-lock-test-") as name:
            temporary = Path(name)
            root = temporary / "managed"
            entered = temporary / "entered"
            release = temporary / "release"
            environment = {**os.environ, "ENTERED": str(entered), "RELEASE": str(release)}
            first = subprocess.Popen([
                sys.executable, str(MANAGER_PATH), "run", "--root", str(root),
                "--role", "android-phone", "--", sys.executable, "-c",
                "import os,pathlib,time; p=pathlib.Path(os.environ['ENTERED']); p.touch(); "
                "r=pathlib.Path(os.environ['RELEASE']); "
                "exec(\"while not r.exists():\\n time.sleep(0.02)\")",
            ], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while not entered.exists() and first.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(entered.exists(), "first role never acquired its cache")

                same_role = subprocess.run([
                    sys.executable, str(MANAGER_PATH), "prepare", "--root", str(root),
                    "--role", "android-phone", "--env-file", str(temporary / "same.env"),
                ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertEqual(2, same_role.returncode)
                self.assertIn("already in use", same_role.stderr)

                other_role = subprocess.run([
                    sys.executable, str(MANAGER_PATH), "run", "--root", str(root),
                    "--role", "android-pico", "--", sys.executable, "-c", "pass",
                ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertEqual(0, other_role.returncode, other_role.stderr)
            finally:
                release.touch()
                first_stdout, first_stderr = first.communicate(timeout=5)
            self.assertEqual(0, first.returncode, first_stdout + first_stderr)

    def test_read_only_seed_is_reflink_copied_under_explicit_lock(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-seed-test-") as name:
            temporary = Path(name)
            seed = temporary / "immutable-seed"
            package = seed / "p/recipe/p/package"
            package.mkdir(parents=True)
            payload = package / "artifact.bin"
            payload.write_bytes(b"seed-data")
            for base, directories, files in os.walk(seed, topdown=False):
                for filename in files:
                    (Path(base) / filename).chmod(0o400)
                for directory in directories:
                    (Path(base) / directory).chmod(0o500)
            seed.chmod(0o500)
            seed_lock = temporary / "seed.lock"
            environment = temporary / "phone.env"

            self.assertEqual(0, self.prepare(
                temporary / "managed", "android-phone", environment,
                "--seed", str(seed), "--seed-lock", str(seed_lock)))
            copied = temporary / "managed/homes/android-phone/p/recipe/p/package/artifact.bin"
            self.assertEqual(b"seed-data", copied.read_bytes())
            self.assertEqual(0o600, mode(copied))
            self.assertEqual(0o700, mode(copied.parent))
            self.assertEqual(0o400, mode(payload))
            self.assertEqual(0o500, mode(seed))
            self.assertEqual(0o600, mode(seed_lock))
            source = MANAGER_PATH.read_text(encoding="utf-8")
            self.assertIn('"--reflink=auto"', source)

    def test_busy_seed_lock_and_writable_seed_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-seed-lock-test-") as name:
            temporary = Path(name)
            seed = temporary / "seed"
            seed.mkdir(mode=0o500)
            lock = temporary / "seed.lock"
            root = temporary / "managed"
            arguments = (
                "--seed", str(seed), "--seed-lock", str(lock),
            )
            with MANAGER.FileLock(lock, shared=False, label="seed"):
                with self.assertRaisesRegex(MANAGER.CacheError, "already in use"):
                    self.prepare(root, "android-phone", temporary / "busy.env", *arguments)

            seed.chmod(0o755)
            with self.assertRaisesRegex(MANAGER.CacheError, "recursively read-only"):
                self.prepare(root, "android-phone", temporary / "writable.env", *arguments)

    def test_unmarked_data_and_default_conan_home_are_never_adopted(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-adopt-test-") as name:
            root = Path(name) / "existing"
            root.mkdir(mode=0o755)
            existing = root / "keep.txt"
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(MANAGER.CacheError, "unmarked"):
                self.prepare(root, "android-phone", Path(name) / "unsafe.env")
            self.assertEqual("keep", existing.read_text(encoding="utf-8"))
            self.assertEqual(0o755, mode(root))

        default_child = Path.home() / ".conan2/overte-managed-test"
        with self.assertRaisesRegex(MANAGER.CacheError, "default Conan cache"):
            MANAGER.CacheManager(default_child)

    def test_private_selector_is_rejected_without_echoing_it(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-privacy-test-") as name:
            selector = "private-target-7f93a"
            unsafe_root = Path(name) / f"cache-{selector}"
            environment = {**os.environ, "OVERTE_DEVICE_TARGET_SELECTOR": selector}
            result = subprocess.run([
                sys.executable, str(MANAGER_PATH), "prepare", "--root", str(unsafe_root),
                "--role", "android-phone", "--env-file", str(Path(name) / "cache.env"),
            ], env=environment, text=True, stdout=subprocess.PIPE,
               stderr=subprocess.PIPE, check=False)
            self.assertEqual(2, result.returncode)
            self.assertNotIn(selector, result.stdout + result.stderr)
            self.assertFalse(unsafe_root.exists())

    def test_ancestor_symlinks_are_rejected_for_every_managed_path(self):
        with tempfile.TemporaryDirectory(prefix="overte-cache-symlink-test-") as name:
            temporary = Path(name)
            real_parent = temporary / "real-parent"
            real_parent.mkdir(mode=0o700)
            linked_parent = temporary / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)

            with self.subTest("managed root"):
                with self.assertRaisesRegex(MANAGER.CacheError, "symbolic-link components"):
                    MANAGER.CacheManager(linked_parent / "managed").initialize()
                self.assertFalse((real_parent / "managed").exists())

            safe_root = temporary / "safe-root"
            MANAGER.CacheManager(safe_root).initialize()
            with self.subTest("environment output"):
                with self.assertRaisesRegex(MANAGER.CacheError, "symbolic-link components"):
                    self.prepare(safe_root, "android-phone", linked_parent / "phone.env")
                self.assertFalse((real_parent / "phone.env").exists())

            seed_parent = temporary / "seed-parent"
            seed_parent.mkdir(mode=0o700)
            seed = seed_parent / "immutable"
            seed.mkdir(mode=0o500)
            seed_link = temporary / "seed-link"
            seed_link.symlink_to(seed_parent, target_is_directory=True)
            with self.subTest("seed"):
                with self.assertRaisesRegex(MANAGER.CacheError, "symbolic-link components"):
                    self.prepare(
                        safe_root, "android-pico", temporary / "pico.env",
                        "--seed", str(seed_link / "immutable"),
                        "--seed-lock", str(temporary / "seed.lock"),
                    )

            lock_parent = temporary / "lock-parent"
            lock_parent.mkdir(mode=0o700)
            lock_link = temporary / "lock-link"
            lock_link.symlink_to(lock_parent, target_is_directory=True)
            with self.subTest("seed lock"):
                with self.assertRaisesRegex(MANAGER.CacheError, "symbolic-link components"):
                    self.prepare(
                        safe_root, "android-pico", temporary / "pico.env",
                        "--seed", str(seed),
                        "--seed-lock", str(lock_link / "seed.lock"),
                    )
                self.assertFalse((lock_parent / "seed.lock").exists())

            fake_home_target = temporary / "home-target"
            fake_home_target.mkdir(mode=0o700)
            fake_home_link = temporary / "home-link"
            fake_home_link.symlink_to(fake_home_target, target_is_directory=True)
            with self.subTest("default cache"):
                with patch.object(MANAGER.Path, "home", return_value=fake_home_link):
                    with self.assertRaisesRegex(
                            MANAGER.CacheError, "default Conan cache.*symbolic-link"):
                        MANAGER.CacheManager(temporary / "otherwise-safe")

    def test_android_conan_entrypoints_inherit_conan_home(self):
        pico = (ROOT / "android/vr/pico/build.sh").read_text(encoding="utf-8")
        phone_entry = (ROOT / "android/phone/build.sh").read_text(encoding="utf-8")
        phone = (ROOT / "android/phone/build-phone-qt-16k.sh").read_text(encoding="utf-8")
        non_qt = (ROOT / "android/phone/prepare-phone-16k-conan-deps.sh").read_text(
            encoding="utf-8")
        for source in (pico, phone, non_qt):
            self.assertIn('conan_home="${CONAN_HOME:-${HOME}/.conan2}"', source)
        self.assertIn('${CONAN_HOME:-${HOME}/.conan2}/p', phone_entry)
        self.assertIn('PHONE_SHARED_CONAN_HOME:-${HOME}/.conan2', phone_entry)
        self.assertNotIn("env -i", pico)
        self.assertNotIn("unset CONAN_HOME", pico + phone_entry + phone + non_qt)


if __name__ == "__main__":
    unittest.main()
