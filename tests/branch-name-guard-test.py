#!/usr/bin/env python3
"""Exercise installed branch guards in disposable Git repositories only."""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools/branch-policy/install.py"


class BranchNameGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-branch-guard-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_TERMINAL_PROMPT="0", PYTHONDONTWRITEBYTECODE="1")
        self.repo = self.new_repository("clone")

    def command(self, arguments, *, cwd=None, input=None):
        return subprocess.run(arguments, cwd=cwd or self.root, env=self.env,
                              input=input, text=True, capture_output=True, timeout=30)

    def git(self, *arguments, repo=None, input=None):
        return self.command(["git", "-C", str(repo or self.repo), *arguments], input=input)

    def require_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def new_repository(self, name, *, object_format=None, bare=False):
        path = self.root / name
        arguments = ["git", "init", "--initial-branch=main"]
        if object_format:
            arguments.append("--object-format=" + object_format)
        if bare:
            arguments.append("--bare")
        arguments.append(str(path))
        self.require_success(self.command(arguments))
        if not bare:
            self.require_success(self.git("config", "user.name", "Branch guard fixture", repo=path))
            self.require_success(self.git("config", "user.email", "fixture@example.invalid", repo=path))
            self.require_success(self.git("config", "commit.gpgsign", "false", repo=path))
            (path / "tracked.txt").write_text("initial\n")
            self.require_success(self.git("add", "tracked.txt", repo=path))
            self.require_success(self.git("commit", "-m", "Initial fixture", repo=path))
        return path

    def install(self, *, repo=None, installer=INSTALLER):
        return self.command([sys.executable, str(installer), "install",
                             "--repository", str(repo or self.repo)])

    def status(self, *, repo=None):
        result = self.command([sys.executable, str(INSTALLER), "status",
                               "--repository", str(repo or self.repo)])
        return result, json.loads(result.stdout)

    def exists(self, name, *, repo=None):
        return self.git("show-ref", "--verify", "--quiet", name, repo=repo).returncode == 0

    def add_remote(self, *, repo=None, name="remote.git", object_format=None):
        remote = self.new_repository(name, bare=True, object_format=object_format)
        self.require_success(self.git("remote", "add", "fixture", str(remote), repo=repo))
        return remote

    def copy_reviewed_source(self):
        source = self.root / "reviewed-source"
        for relative in ("tools/branch-policy/install.py", "tools/branch-policy/guard.py",
                         "tools/branch-policy/check.py", ".github/branch-policy.json"):
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        return source

    def test_branch_switch_and_worktree_creation_reject_invalid_names(self):
        self.require_success(self.install())
        for args, ref in (
            (("branch", "bad-branch"), "bad-branch"),
            (("switch", "-c", "fix/unknown-scope/example"), "fix/unknown-scope/example"),
            (("worktree", "add", "-b", "task/ios/missing-number", str(self.root / "invalid-worktree")),
             "task/ios/missing-number"),
        ):
            with self.subTest(command=args):
                result = self.git(*args)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(self.exists("refs/heads/" + ref))
        self.assertEqual(self.require_success(self.git("branch", "--show-current")), "main")
        self.require_success(self.git("switch", "-c", "fix/android-phone/valid-name"))

    def test_existing_invalid_branch_updates_and_deletion_stay_usable(self):
        self.require_success(self.git("branch", "legacy-invalid"))
        self.require_success(self.install())
        self.require_success(self.git("commit", "--allow-empty", "-m", "New fixture commit"))
        head = self.require_success(self.git("rev-parse", "HEAD"))
        # Unconditional update-ref supplies a zero old value too. It must not be
        # mistaken for creating a new name when that ref already exists.
        self.require_success(self.git("update-ref", "refs/heads/legacy-invalid", head))
        self.assertEqual(self.require_success(self.git("rev-parse", "legacy-invalid")), head)
        self.require_success(self.git("branch", "-f", "legacy-invalid", "HEAD^"))
        self.require_success(self.git("branch", "-D", "legacy-invalid"))
        self.assertFalse(self.exists("refs/heads/legacy-invalid"))

    def test_symbolic_branch_creation_and_existing_dangling_alias_updates(self):
        existing = "refs/heads/legacy-symbolic"
        missing_target = "refs/heads/fix/main/not-created"
        self.require_success(self.git("symbolic-ref", existing, missing_target))
        self.require_success(self.install())
        valid = "refs/heads/fix/main/symbolic-alias"
        self.require_success(self.git("symbolic-ref", valid, "refs/heads/main"))
        self.assertEqual(self.require_success(self.git("symbolic-ref", valid)), "refs/heads/main")
        invalid = "refs/heads/invalid-symbolic"
        self.assertNotEqual(self.git("symbolic-ref", invalid, "refs/heads/main").returncode, 0)
        self.assertNotEqual(self.git("symbolic-ref", "--quiet", invalid).returncode, 0)
        # A dangling symbolic ref exists even when show-ref cannot resolve it.
        # Updating that pre-existing name must not be treated as its creation.
        self.require_success(self.git("symbolic-ref", existing, "refs/heads/main"))
        self.require_success(self.git("symbolic-ref", existing, missing_target))
        self.assertEqual(self.require_success(self.git("symbolic-ref", existing)), missing_target)
        self.require_success(self.git("symbolic-ref", "--delete", existing))
        self.assertNotEqual(self.git("symbolic-ref", "--quiet", existing).returncode, 0)

    def test_atomic_transaction_rejects_every_new_ref_when_one_name_is_invalid(self):
        self.require_success(self.install())
        head = self.require_success(self.git("rev-parse", "HEAD"))
        transaction = ("start\ncreate refs/heads/fix/main/valid-batch " + head
                       + "\ncreate refs/heads/invalid-batch " + head + "\nprepare\ncommit\n")
        result = self.git("update-ref", "--stdin", input=transaction)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.exists("refs/heads/fix/main/valid-batch"))
        self.assertFalse(self.exists("refs/heads/invalid-batch"))

    def test_old_linked_worktree_uses_installed_payload_without_candidate_code(self):
        linked = self.root / "old-linked"
        self.require_success(self.git("worktree", "add", "-b", "fix/main/old-linked", str(linked)))
        self.require_success(self.install())
        self.assertFalse((linked / "tools/branch-policy").exists())
        for folder in (self.repo, linked):
            with self.subTest(worktree=folder.name):
                result = self.git("branch", "invalid-from-" + folder.name, repo=folder)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.exists("refs/heads/invalid-from-" + folder.name))
        # A checkout cannot replace the reviewed implementation by adding files
        # where a repository-relative hook might otherwise import them.
        candidate = linked / "tools/branch-policy"
        candidate.mkdir(parents=True)
        sentinel = self.root / "candidate-executed"
        for name in ("guard.py", "check.py"):
            (candidate / name).write_text("from pathlib import Path\nPath(" + repr(str(sentinel))
                                         + ").write_text('executed')\n")
        self.require_success(self.git("branch", "fix/main/valid-from-linked", repo=linked))
        self.assertNotEqual(self.git("branch", "invalid-candidate", repo=linked).returncode, 0)
        self.assertFalse(sentinel.exists())
        result, state = self.status(repo=linked)
        self.require_success(result)
        self.assertIs(state["installed"], True)

    def test_fetch_tracking_tags_and_detached_head_are_not_branch_creations(self):
        remote = self.add_remote()
        self.require_success(self.git("push", "fixture", "HEAD:refs/heads/legacy-remote"))
        self.require_success(self.install())
        self.require_success(self.git("fetch", "fixture"))
        self.assertTrue(self.exists("refs/remotes/fixture/legacy-remote"))
        self.require_success(self.git("tag", "fixture-tag"))
        self.require_success(self.git("switch", "--detach"))
        self.require_success(self.git("commit", "--allow-empty", "-m", "Detached fixture commit"))
        self.assertTrue(self.exists("refs/tags/fixture-tag"))
        self.assertTrue(self.exists("refs/heads/legacy-remote", repo=remote))

    def test_pre_push_validates_remote_destination_including_sha_sources_and_deletions(self):
        remote = self.add_remote()
        self.require_success(self.install())
        self.require_success(self.git("push", "fixture", "HEAD:refs/heads/fix/main/valid-destination"))
        for source in ("HEAD", self.require_success(self.git("rev-parse", "HEAD"))):
            result = self.git("push", "fixture", source + ":refs/heads/invalid-destination")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.exists("refs/heads/invalid-destination", repo=remote))
        head = self.require_success(self.git("rev-parse", "HEAD"))
        self.require_success(self.git("update-ref", "refs/heads/legacy-delete", head, repo=remote))
        self.require_success(self.git("push", "fixture", ":refs/heads/legacy-delete"))
        self.assertFalse(self.exists("refs/heads/legacy-delete", repo=remote))

    def test_native_rename_and_copy_cannot_publish_invalid_destinations(self):
        remote = self.add_remote()
        self.require_success(self.install())
        for option, source, invalid in (("-m", "fix/main/rename-source", "invalid-renamed"),
                                        ("-c", "main", "invalid-copied")):
            if option == "-m":
                self.require_success(self.git("branch", source))
            result = self.git("branch", option, source, invalid)
            if result.returncode == 0:
                # Git's files backend currently bypasses creation transactions
                # for rename/copy. The destination push guard is still required.
                self.assertTrue(self.exists("refs/heads/" + invalid))
                self.assertNotEqual(self.git("push", "fixture", invalid).returncode, 0)
            else:
                # Permit Git versions/backends that enforce the creation hook.
                self.assertTrue(self.exists("refs/heads/" + source))
                self.assertFalse(self.exists("refs/heads/" + invalid))
            self.assertFalse(self.exists("refs/heads/" + invalid, repo=remote))

    def test_unrelated_existing_hooks_are_preserved_when_installation_refuses(self):
        for hook_name in ("reference-transaction", "pre-push"):
            repo = self.new_repository("existing-" + hook_name)
            hook = repo / ".git/hooks" / hook_name
            original = b"#!/bin/sh\n# Existing owner-managed hook.\nexit 0\n"
            hook.write_bytes(original)
            hook.chmod(0o755)
            before = {p.name: p.read_bytes() for p in hook.parent.iterdir() if p.is_file()}
            result = self.install(repo=repo)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in hook.parent.iterdir() if p.is_file()}, before)
            self.assertFalse((repo / ".git/overte-branch-name-guard").exists())

    def test_custom_hooks_path_is_preserved_and_refused(self):
        self.require_success(self.git("config", "core.hooksPath", "owner-hooks"))
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.require_success(self.git("config", "--get", "core.hooksPath")), "owner-hooks")
        self.assertFalse((self.repo / ".git/overte-branch-name-guard").exists())

    def test_custom_hooks_path_in_another_linked_worktree_is_refused(self):
        linked = self.root / "custom-linked"
        self.require_success(self.git("worktree", "add", "-b", "fix/main/custom-linked", str(linked)))
        self.require_success(self.git("config", "extensions.worktreeConfig", "true"))
        self.require_success(self.git("config", "--worktree", "core.hooksPath", "linked-owner-hooks", repo=linked))
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.require_success(self.git("config", "--get", "core.hooksPath", repo=linked)),
                         "linked-owner-hooks")
        self.assertFalse((self.repo / ".git/overte-branch-name-guard").exists())

    def test_missing_prunable_worktree_is_reported_without_pruning_metadata(self):
        linked = self.root / "missing-linked"
        self.require_success(self.git("worktree", "add", "-b", "fix/main/missing-linked", str(linked)))
        shutil.rmtree(linked)
        before = self.require_success(self.git("worktree", "list", "--porcelain", "-z"))
        self.assertIn("worktree " + str(linked), before)
        self.assertIn("prunable", before)
        self.require_success(self.install())
        result, state = self.status()
        self.require_success(result)
        self.assertIs(state["installed"], True)
        self.assertEqual(state["unavailable_prunable_worktrees"], [str(linked)])
        self.assertEqual(state["unavailable_prunable_count"], 1)
        self.assertEqual(state["checked_worktrees"], [str(self.repo)])
        self.assertEqual(self.require_success(self.git("worktree", "list", "--porcelain", "-z")), before)
        self.assertTrue(self.exists("refs/heads/fix/main/missing-linked"))
        self.assertNotEqual(self.git("branch", "invalid-after-missing-worktree").returncode, 0)
        self.require_success(self.git("branch", "fix/main/after-missing-worktree"))

    def test_idempotent_install_and_reviewed_payload_update(self):
        result, state = self.status()
        self.assertEqual(result.returncode, 1)
        self.assertIs(state["installed"], False)
        source = self.copy_reviewed_source()
        installer = source / "tools/branch-policy/install.py"
        self.require_success(self.install(installer=installer))
        self.require_success(self.install(installer=installer))
        guard = source / "tools/branch-policy/guard.py"
        guard.write_text(guard.read_text() + "\n# Reviewed payload update fixture.\n")
        self.require_success(self.install(installer=installer))
        result, state = self.status()
        self.require_success(result)
        self.assertIs(state["installed"], True)
        self.assertNotEqual(self.git("branch", "invalid-after-update").returncode, 0)
        self.require_success(self.git("branch", "fix/main/after-update"))

    def test_running_push_keeps_its_policy_version_during_installer_update(self):
        remote = self.add_remote()
        source = self.copy_reviewed_source()
        installer = source / "tools/branch-policy/install.py"
        guard = source / "tools/branch-policy/guard.py"
        started, release = self.root / "guard-started", self.root / "guard-release"
        # Pause an actual temporary push after its guard code loads, then install
        # a different reviewed policy before that invocation imports the checker.
        barrier = ("if __name__ == '__main__' and sys.argv[1:2] == ['pre-push']:\n"
                   "    import time\n"
                   f"    Path({str(started)!r}).touch()\n"
                   "    deadline = time.monotonic() + 15\n"
                   f"    while not Path({str(release)!r}).exists():\n"
                   "        if time.monotonic() >= deadline:\n"
                   "            raise SystemExit('Fixture barrier timed out')\n"
                   "        time.sleep(0.01)\n\n")
        main_marker = 'if __name__ == "__main__":'
        self.assertIn(main_marker, guard.read_text())
        guard.write_text(guard.read_text().replace(main_marker, barrier + main_marker))
        self.require_success(self.install(installer=installer))
        destination = "refs/heads/fix/main/version-snapshot"
        process = subprocess.Popen(["git", "-C", str(self.repo), "push", "fixture", "HEAD:" + destination],
                                   cwd=self.root, env=self.env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not started.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(started.exists(), "The temporary push never reached its installed guard")
            checker = source / "tools/branch-policy/check.py"
            checker.write_text(checker.read_text() + "\n"
                               "_fixture_original_validate = validate_branch_name\n"
                               "def validate_branch_name(branches, name, *args, **kwargs):\n"
                               "    if name == 'fix/main/version-snapshot':\n"
                               "        raise ValueError('Updated fixture policy rejects this name')\n"
                               "    return _fixture_original_validate(branches, name, *args, **kwargs)\n")
            self.require_success(self.install(installer=installer))
        finally:
            release.touch()
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertTrue(self.exists(destination, repo=remote))
        old_remote_head = self.require_success(self.git("rev-parse", destination, repo=remote))
        self.require_success(self.git("commit", "--allow-empty", "-m", "Next fixture update"))
        result = self.git("push", "fixture", "HEAD:" + destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Updated fixture policy rejects this name", result.stderr)
        self.assertEqual(self.require_success(self.git("rev-parse", destination, repo=remote)), old_remote_head)

    def test_sha256_creation_and_push_destination_validation(self):
        repo = self.new_repository("sha256", object_format="sha256")
        remote = self.add_remote(repo=repo, name="sha256-remote.git", object_format="sha256")
        self.require_success(self.install(repo=repo))
        self.assertEqual(len(self.require_success(self.git("rev-parse", "HEAD", repo=repo))), 64)
        self.require_success(self.git("branch", "fix/main/sha256", repo=repo))
        self.assertNotEqual(self.git("branch", "invalid-sha256", repo=repo).returncode, 0)
        self.assertNotEqual(self.git("push", "fixture", "HEAD:refs/heads/invalid-sha256", repo=repo).returncode, 0)
        self.assertFalse(self.exists("refs/heads/invalid-sha256", repo=remote))

    def test_documented_user_control_bypasses_are_limited_to_disposable_repositories(self):
        remote = self.add_remote()
        self.require_success(self.install())
        self.require_success(self.git("-c", "core.hooksPath=" + os.devnull, "branch", "invalid-explicit-bypass"))
        self.assertTrue(self.exists("refs/heads/invalid-explicit-bypass"))
        self.require_success(self.git("push", "--no-verify", "fixture", "HEAD:refs/heads/invalid-explicit-bypass"))
        self.assertTrue(self.exists("refs/heads/invalid-explicit-bypass", repo=remote))


if __name__ == "__main__":
    unittest.main(verbosity=2)
