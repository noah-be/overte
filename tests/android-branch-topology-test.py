#!/usr/bin/env python3
"""Self-tests for the Android branch topology policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


CHECK = Path(__file__).with_name("android-branch-topology-check.py")
WORKFLOW = CHECK.parents[1] / ".github/workflows/android-branch-topology.yml"
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

    def test_quest_is_not_an_active_android_target(self):
        self.assertEqual(
            ["unsupported Android target branch: android-vr-quest"],
            MODULE.validate(
                self.repo,
                "android-vr-quest",
                self.android_main,
                self.android_vr,
                self.android_vr,
            ),
        )
        self.assertNotIn(
            "android-vr-quest",
            WORKFLOW.read_text(encoding="utf-8"),
        )

    def test_shared_harness_change_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit("tests/device/core", "changed directly\n")
        errors = MODULE.validate(
            self.repo, "android-phone", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("tests/device differs" in error for error in errors))

    def test_phone_flat_touch_policy_is_allowed(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit(
            "tests/device/policies/android-phone-flat-touch.json", "{}\n"
        )
        self.assertEqual(
            [],
            MODULE.validate(
                self.repo, "android-phone", self.android_main, self.android_vr, head
            ),
        )

    def test_other_phone_policy_change_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit("tests/device/policies/android-phone-other.json", "{}\n")
        errors = MODULE.validate(
            self.repo, "android-phone", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("tests/device differs" in error for error in errors))

    def test_phone_flat_touch_policy_change_is_rejected_on_vr(self):
        run(self.repo, "checkout", "-q", self.android_main)
        head = self.commit(
            "tests/device/policies/android-phone-flat-touch.json", "{}\n"
        )
        errors = MODULE.validate(
            self.repo, "android-vr", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("tests/device differs" in error for error in errors))

    def test_phone_flat_touch_policy_change_is_rejected_on_pico(self):
        run(self.repo, "checkout", "-q", self.android_vr)
        head = self.commit(
            "tests/device/policies/android-phone-flat-touch.json", "{}\n"
        )
        errors = MODULE.validate(
            self.repo, "android-vr-pico", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("tests/device differs" in error for error in errors))

    def test_pico_owned_phase_c_test_fixtures_are_allowed(self):
        for path in (
            "tests/device/jenkins/test_conan_cache_manager.py",
            "tests/device/jenkins/test_local_lab.py",
            "tests/device/self_tests/test_pico_openxr_adapter_session.py",
        ):
            with self.subTest(path=path):
                run(self.repo, "checkout", "-q", self.android_vr)
                head = self.commit(path, "pico-owned fixture\n")
                self.assertEqual(
                    [],
                    MODULE.validate(
                        self.repo,
                        "android-vr-pico",
                        self.android_main,
                        self.android_vr,
                        head,
                    ),
                )

    def test_other_pico_tests_device_change_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_vr)
        head = self.commit(
            "tests/device/jenkins/test_unplanned_pico_change.py", "not owned\n"
        )
        errors = MODULE.validate(
            self.repo, "android-vr-pico", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("tests/device differs" in error for error in errors))

    def test_shared_transport_change_is_rejected(self):
        run(self.repo, "checkout", "-q", self.android_vr)
        head = self.commit("android/common/device_tests/transport", "changed directly\n")
        errors = MODULE.validate(
            self.repo, "android-vr-pico", self.android_main, self.android_vr, head
        )
        self.assertTrue(any("device_tests differs" in error for error in errors))

    def test_workflow_uses_targeted_history_fetch(self):
        source = WORKFLOW.read_text()
        self.assertNotIn("actions/checkout", source)
        self.assertIn("git init -q .", source)
        self.assertIn("git sparse-checkout init --cone", source)
        self.assertIn(".github/workflows", source)
        self.assertIn("android/common/device_tests", source)
        self.assertIn("--depth=2", source)
        self.assertIn("refs/pull/$PULL_NUMBER/merge", source)
        self.assertIn("--filter=blob:none", source)
        self.assertIn("--unshallow", source)
        self.assertIn('for branch in android-main android-vr "$TARGET_BRANCH"', source)

    def test_targeted_fetch_connects_a_shallow_pull_request_merge(self):
        run(self.repo, "branch", "android-main", self.android_main)
        run(self.repo, "checkout", "-qb", "android-vr-pico", self.android_vr)
        self.commit("android/vr/pico/base", "pico\n")
        run(self.repo, "checkout", "-qb", "topic")
        self.commit("docs/topic", "roadmap\n")
        run(self.repo, "checkout", "-q", "android-vr-pico")
        run(self.repo, "merge", "-q", "--no-ff", "-m", "pull request", "topic")
        pull_request_merge = revision(self.repo)

        with tempfile.TemporaryDirectory(prefix="android-topology-fetch-") as root:
            remote = Path(root) / "remote.git"
            shallow = Path(root) / "shallow"
            subprocess.run(
                ["git", "clone", "-q", "--bare", str(self.repo), str(remote)],
                check=True,
            )
            run(remote, "config", "uploadpack.allowFilter", "true")
            run(remote, "update-ref", "refs/pull/1/merge", pull_request_merge)

            shallow.mkdir()
            run(shallow, "init", "-q")
            run(shallow, "remote", "add", "origin", remote.resolve().as_uri())
            run(shallow, "sparse-checkout", "init", "--cone")
            run(
                shallow,
                "sparse-checkout",
                "set",
                ".github/workflows",
                "tests",
                "android/common/device_tests",
            )
            run(
                shallow,
                "fetch",
                "-q",
                "--no-tags",
                "--depth=2",
                "--filter=blob:none",
                "origin",
                "+refs/pull/1/merge:refs/remotes/origin/pull-request-merge",
            )
            run(
                shallow,
                "fetch",
                "-q",
                "--no-tags",
                "--filter=blob:none",
                "--unshallow",
                "origin",
                "+refs/heads/android-main:refs/remotes/origin/android-main",
                "+refs/heads/android-vr:refs/remotes/origin/android-vr",
                "+refs/heads/android-vr-pico:refs/remotes/origin/android-vr-pico",
            )
            run(
                shallow,
                "checkout",
                "-q",
                "--detach",
                "refs/remotes/origin/pull-request-merge",
            )

            self.assertEqual(
                "false",
                subprocess.check_output(
                    ["git", "-C", str(shallow), "rev-parse",
                     "--is-shallow-repository"],
                    text=True,
                ).strip(),
            )
            self.assertTrue((shallow / "tests/device/core").is_file())
            self.assertTrue(
                (shallow / "android/common/device_tests/transport").is_file()
            )
            self.assertEqual(
                [],
                MODULE.validate(
                    shallow,
                    "android-vr-pico",
                    "origin/android-main",
                    "origin/android-vr",
                    "HEAD",
                ),
            )


if __name__ == "__main__":
    unittest.main()
