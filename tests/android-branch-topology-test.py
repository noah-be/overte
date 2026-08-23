#!/usr/bin/env python3
"""Self-tests for the Android branch topology policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECK = Path(__file__).with_name("android-branch-topology-check.py")
SPEC = importlib.util.spec_from_file_location("android_topology", CHECK)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def run(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def revision(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


class AndroidBranchTopologyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="android-topology-test-")
        self.repo = Path(self.temporary.name)
        run(self.repo, "init", "-q")
        run(self.repo, "config", "user.name", "Test")
        run(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "tests/device").mkdir(parents=True)
        (self.repo / "tests/device/core").write_text("v1\n")
        (self.repo / "android/common/device_tests").mkdir(parents=True)
        (self.repo / "android/common/device_tests/transport").write_text("v1\n")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "android main")
        self.android_main = revision(self.repo)
        run(self.repo, "checkout", "-qb", "android-vr")
        (self.repo / "android/vr/common").mkdir(parents=True)
        (self.repo / "android/vr/common/base").write_text("vr\n")
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", "android vr")
        self.android_vr = revision(self.repo)

    def tearDown(self):
        self.temporary.cleanup()

    def commit(self, path: str, content: str) -> str:
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
        run(self.repo, "add", ".")
        run(self.repo, "commit", "-qm", path)
        return revision(self.repo)

    def test_phone_adapter_change_is_allowed_from_android_main(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit("android/phone/device-tests/adapter.py", "adapter\n")
        self.assertEqual(
            [],
            MODULE.validate(
                self.repo, "android-phone", self.android_main, self.android_vr, head
            ),
        )

    def test_pico_adapter_change_is_allowed_from_android_vr(self):
        run(self.repo, "checkout", "-q", self.android_vr)
        head = self.commit("android/vr/pico/device-tests/adapter.py", "adapter\n")
        self.assertEqual(
            [],
            MODULE.validate(
                self.repo, "android-vr-pico", self.android_main, self.android_vr, head
            ),
        )

    def test_pico_without_android_vr_ancestry_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit("android/vr/pico/device-tests/adapter.py", "adapter\n")
        errors = MODULE.validate(
            self.repo, "android-vr-pico", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("current android-vr history" in error for error in errors))

    def test_shared_harness_change_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit("tests/device/core", "changed directly\n")
        errors = MODULE.validate(
            self.repo, "android-phone", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("tests/device differs" in error for error in errors))

    def test_shared_transport_change_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_vr)
        head = self.commit("android/common/device_tests/transport", "changed directly\n")
        errors = MODULE.validate(
            self.repo, "android-vr-pico", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("device_tests differs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
