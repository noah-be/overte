#!/usr/bin/env python3
"""Offline sandbox policy/control fixtures; none qualify real OS isolation."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import tracemalloc
import zlib
from unittest.mock import patch

import sandbox as S
import sandbox_probe as PROBE


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-sandbox-controls-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in S._POLICY_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(S.ROOT / name, path)
        for name in S.runtime._requirement_inventory(S.ROOT)[1]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(S.ROOT / name, path)

    def layout(self):
        paths = []
        for name in ("candidate", "scratch", "policy-source", "venv", "protected"):
            path = self.root / name
            path.mkdir()
            paths.append(path)
        (paths[0] / ".git").mkdir()
        return S.Layout(*paths)


class PolicyTests(Fixture):
    def test_shipped_policy_is_disabled_and_no_host_is_qualified(self):
        policy = S.load_policy(self.root)
        self.assertIs(policy["enabled"], False)
        self.assertEqual(policy["qualified_hosts"], [])

    def test_protected_capability_does_not_enable_legacy_execution_or_qualified_json(self):
        for capability in (False, 1, 'true', True):
            with self.subTest(capability=capability), patch.object(S, 'ACTIVATION_READY', capability):
                if capability is True:
                    S.require_protected_execution(self.root)
                else:
                    with self.assertRaises(S.SandboxUnavailable): S.require_protected_execution(self.root)
                self.assertFalse(S.load_policy(self.root)['enabled'])
                for call in (S.execute, S.capture_after_execution):
                    with self.assertRaises(S.SandboxUnavailable): call(qualified=True)
        policy = S.load_policy(self.root)
        policy['enabled'] = True
        (self.root / S.POLICY).write_text(json.dumps(policy))
        with patch.object(S, 'ACTIVATION_READY', True), self.assertRaises(S.SandboxUnavailable):
            S.require_protected_execution(self.root)

    def test_unknown_boolean_missing_or_supplied_qualification_cannot_enable_policy(self):
        original = S.load_policy(self.root)
        for field, value in (("enabled", True), ("qualified_hosts", [{"passed": True}]),
                             ("schema", True), ("extra", True), ("requirements", [])):
            with self.subTest(field=field):
                policy = {**original, field: value}
                (self.root / S.POLICY).write_text(json.dumps(policy))
                with self.assertRaises(S.SandboxUnavailable):
                    S.load_policy(self.root)

    def test_duplicate_json_fields_are_rejected(self):
        path = self.root / S.POLICY
        path.write_text(path.read_text().replace('"enabled": false', '"enabled": false, "enabled": false'))
        with self.assertRaises(S.SandboxUnavailable):
            S.load_policy(self.root)

    def test_contract_binds_actual_probe_and_supervisor_bytes(self):
        previous = S.contract(self.root)
        for relative in ("tools/test-evidence/sandbox_probe.py", "tools/test-evidence/sandbox.py"):
            with self.subTest(relative=relative):
                path = self.root / relative
                path.write_text(path.read_text() + "\n# reviewed control change\n")
                current = S.contract(self.root)
                self.assertNotEqual(previous["digest"], current["digest"])
                self.assertEqual(current["qualification"], "unavailable")
                previous = current

    def test_policy_source_alias_cannot_replace_reviewed_bytes(self):
        path = self.root / "tools/test-evidence/sandbox_probe.py"
        data = path.read_bytes()
        path.unlink()
        other = self.root / "outside-probe.py"
        other.write_bytes(data)
        path.symlink_to(other)
        with self.assertRaises(S.SandboxUnavailable):
            S.contract(self.root)

    def test_recursive_requirements_and_actual_runtime_source_are_bound(self):
        previous = S.contract(self.root)
        for name in ("tools/sbom/requirements-validation.txt", "tools/test-evidence/runtime.py"):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text(path.read_text() + "\n# dependency review\n")
                current = S.contract(self.root)
                self.assertNotEqual(current["digest"], previous["digest"])
                previous = current

    def test_no_candidate_json_boolean_policy_or_probe_can_authorize_execution(self):
        for data in ({}, {"enabled": True, "qualified": True, "descendants_empty": True},
                     {"populated": 0, "NoNewPrivs": 1, "runtime": {"passed": True}}):
            with self.subTest(data=data), patch.object(S.subprocess, "Popen") as spawn:
                with self.assertRaises(S.SandboxUnavailable):
                    S.execute(data, sandboxed=True, allow_fallback=True)
                spawn.assert_not_called()


class FixedPlanTests(Fixture):
    def test_working_directory_is_explicit_and_bound_in_the_exact_environment(self):
        layout = self.layout()
        command = ["/opt/overte-ci/venv/bin/python", "tests/example.py"]
        plan = S.build_plan(layout, command, root=self.root)
        args = plan["argv"]
        self.assertEqual(S._ENVIRONMENT["PWD"], "/work")
        self.assertIn(["--setenv", "PWD", "/work"], [args[i:i+3] for i in range(len(args))])
        self.assertEqual(args[args.index("--chdir") + 1], "/work")
        with self.assertRaises(S.SandboxUnavailable):
            S.build_plan(layout, command, root=self.root, environment={"PWD": "/outside"})

    def test_source_git_venv_and_policy_are_readonly_protected_reports_are_absent(self):
        layout = self.layout()
        plan = S.build_plan(layout, ["/opt/overte-ci/venv/bin/python", "tests/example.py"], root=self.root)
        args = plan["argv"]
        self.assertIs(plan["launchable"], False)
        self.assertIn(["--ro-bind", str(layout.candidate), "/work"], [args[i:i+3] for i in range(len(args))])
        self.assertIn(["--bind", str(layout.scratch), "/work/build"], [args[i:i+3] for i in range(len(args))])
        self.assertNotIn(str(layout.protected), args)
        self.assertNotIn("--bind-try", args)
        self.assertNotIn("--share-net", args)
        self.assertNotIn("--unshare-user-try", args)
        self.assertNotIn("--disable-userns", args)
        self.assertEqual(args[-3:], ["--", "/opt/overte-ci/venv/bin/python", "tests/example.py"])
        for name in ("user", "pid", "net", "ipc", "uts"):
            self.assertIn("--unshare-" + name, args)
        self.assertIn("--new-session", args)
        self.assertIn("--clearenv", args)
        self.assertIn("--cap-drop", args)
        self.assertIn("parent-owned-kernel-scope-and-confirmed-empty-descendants", plan["unresolved"])

    def test_unknown_sensitive_environment_is_rejected_and_known_variants_preserved(self):
        layout = self.layout()
        for name in ("GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "GITHUB_OUTPUT", "LD_PRELOAD", "NODE_OPTIONS", "JAVA_HOME", "PATH"):
            with self.subTest(name=name), self.assertRaises(S.SandboxUnavailable):
                S.build_plan(layout, ["/usr/bin/node", "test.js"], root=self.root, environment={name: "private"})
        env = {"OVERTE_CREDENTIAL_QT_MAJOR": "5", "ImageOS": "ubuntu24", "ImageVersion": "20261012.1.0",
               "RUNNER_ENVIRONMENT": "github-hosted"}
        args = S.build_plan(layout, ["/usr/bin/node", "test.js"], root=self.root, environment=env)["argv"]
        for name, value in env.items():
            self.assertIn(["--setenv", name, value], [args[i:i+3] for i in range(len(args))])
        with self.assertRaises(S.SandboxUnavailable):
            S.build_plan(layout, ["/usr/bin/node"], root=self.root, environment={"OVERTE_CREDENTIAL_QT_MAJOR": "7"})

    def test_writable_directory_must_not_overlap_candidate_or_control(self):
        layout = self.layout()
        for name in ("candidate", "protected", "venv", "policy_source"):
            with self.subTest(name=name), self.assertRaises(S.SandboxUnavailable):
                changed = S.Layout(layout.candidate, getattr(layout, name), layout.policy_source, layout.venv, layout.protected)
                S.build_plan(changed, ["/usr/bin/node"], root=self.root)

    def test_symlink_directory_and_gitfile_are_not_a_pristine_private_checkout(self):
        layout = self.layout()
        (layout.candidate / ".git").rmdir()
        (layout.candidate / ".git").write_text("gitdir: /private/runner-metadata\n")
        with self.assertRaises(S.SandboxUnavailable):
            S.build_plan(layout, ["/usr/bin/node"], root=self.root)
        (layout.candidate / ".git").unlink()
        (layout.candidate / ".git").symlink_to(layout.protected, target_is_directory=True)
        with self.assertRaises(S.SandboxUnavailable):
            S.build_plan(layout, ["/usr/bin/node"], root=self.root)

    def test_arbitrary_entrypoints_flags_and_source_projection_git_metadata_rejected(self):
        layout = self.layout()
        for command in (["/bin/sh", "-c", "candidate"], ["--share-net"], ["/usr/bin/node\0bad"], [], [True]):
            with self.subTest(command=command), self.assertRaises(S.SandboxUnavailable):
                S.build_plan(layout, command, root=self.root)
        (layout.policy_source / ".git").mkdir()
        with self.assertRaises(S.SandboxUnavailable):
            S.build_plan(layout, ["/usr/bin/node"], root=self.root)

    def test_versioned_setup_toolchain_mounts_and_node_path_are_preserved_in_plan(self):
        layout = self.layout()
        node = Path("/opt/hostedtoolcache/node/22.20.0/x64")
        java = Path("/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/17.0.16-8/x64")
        selected = S.Layout(layout.candidate, layout.scratch, layout.policy_source, layout.venv, layout.protected, (node, java))
        # Pure argv fixture: these synthetic directories are NOT installed or
        # executed, and this is NOT actual hosted toolchain qualification.
        original = S._directory
        with patch.object(S, "_directory", side_effect=lambda value: Path(value) if Path(value) in {node, java} else original(value)):
            args = S.build_plan(selected, [str(node / "bin/node"), "test.js"], root=self.root)["argv"]
        self.assertIn(["--ro-bind", str(node), str(node)], [args[i:i+3] for i in range(len(args))])
        self.assertIn(["--ro-bind", str(java), str(java)], [args[i:i+3] for i in range(len(args))])
        expected = "/opt/overte-ci/venv/bin:" + str(node / "bin") + ":" + str(java / "bin") + ":/usr/bin:/bin"
        self.assertIn(["--setenv", "PATH", expected], [args[i:i+3] for i in range(len(args))])
        broad = S.Layout(layout.candidate, layout.scratch, layout.policy_source, layout.venv, layout.protected, (Path("/usr"),))
        with self.assertRaises(S.SandboxUnavailable):
            S.build_plan(broad, ["/usr/bin/node"], root=self.root)


class GitFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.repository = self.root / "git-source"
        self.repository.mkdir()
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Sandbox source fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repository / "test.py").write_text("raise RuntimeError('candidate must not execute')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Record immutable source")
        self.revision = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.check_output(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
                                       cwd=self.repository, stderr=subprocess.DEVNULL, text=True).strip()


class ImmutableGitTests(GitFixture):
    def test_raw_identity_does_not_execute_candidate_fsmonitor_filter_or_hooks(self):
        marker = self.root / "unexpected-helper"
        hook = self.root / "unsafe-helper"
        hook.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\nexit 1\n")
        hook.chmod(0o755)
        self.git("config", "core.fsmonitor", str(hook))
        self.git("config", "filter.candidate.clean", str(hook))
        self.git("config", "core.hooksPath", str(hook))
        before = S.pristine_git_identity(self.repository, self.revision)
        self.assertEqual(before["commit"], self.revision)
        self.assertEqual(before["tree"], self.git("rev-parse", "HEAD^{tree}"))
        self.assertFalse(marker.exists())

    def test_replace_refs_cannot_substitute_original_commit_body(self):
        original = S.pristine_git_identity(self.repository, self.revision)
        (self.repository / "new.py").write_text("new source\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Different candidate")
        other = self.git("rev-parse", "HEAD")
        self.git("replace", self.revision, other)
        self.assertEqual(S.pristine_git_identity(self.repository, self.revision), original)

    def test_candidate_git_config_is_never_parsed_by_protected_object_reader(self):
        original = S.pristine_git_identity(self.repository, self.revision)
        (self.repository / ".git/config").write_text("invalid Git configuration that must never be parsed\n")
        self.assertEqual(S.pristine_git_identity(self.repository, self.revision), original)

    def test_public_git_commit_identity_uses_protected_stdin_without_object_writes(self):
        actual = S._git
        with patch.object(S, "_git", wraps=actual) as reader:
            observed = S.pristine_git_identity(self.repository, self.revision)
        hashing = [call for call in reader.call_args_list if "hash-object" in call.args]
        self.assertEqual(len(hashing), 1)
        self.assertEqual(hashing[0].args, (self.repository, "hash-object", "-t", "commit", "--stdin"))
        self.assertEqual(hashing[0].kwargs["input_bytes"], actual(self.repository, "cat-file", "commit", self.revision))
        self.assertEqual(observed["commit"], self.revision)

    def test_malformed_or_different_public_object_identity_is_rejected(self):
        actual = S._git
        for value in (b"private-invalid-output", b"0" * 40, b"a" * 40):
            with self.subTest(value=value):
                def query(candidate, *args, **kwargs):
                    return value if args[0] == "hash-object" else actual(candidate, *args, **kwargs)
                with patch.object(S, "_git", side_effect=query), self.assertRaises(S.SandboxUnavailable):
                    S.pristine_git_identity(self.repository, self.revision)

    def test_external_partial_or_grafted_git_objects_are_unsupported(self):
        for name in ("objects/info/alternates", "objects/info/http-alternates", "info/grafts", "shallow", "objects/pack/pack-x.promisor"):
            with self.subTest(name=name):
                path = self.repository / ".git" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("external\n")
                with self.assertRaises(S.SandboxUnavailable):
                    S.pristine_git_identity(self.repository, self.revision)
                path.unlink()

    def test_revision_is_never_a_ref_option_or_shell_command(self):
        for revision in ("HEAD", "--help", "$(private)", "0" * 40):
            with self.subTest(revision=revision), self.assertRaises(S.SandboxUnavailable):
                S.pristine_git_identity(self.repository, revision)

    def test_large_commit_metadata_rejected_before_payload_read(self):
        with patch.object(S, "_git", return_value=b"1000001\n") as reader:
            with self.assertRaises(S.SandboxUnavailable):
                S.pristine_git_identity(self.repository, self.revision)
        reader.assert_called_once_with(self.repository, "cat-file", "-s", self.revision)


class SnapshotTests(GitFixture):
    def setUp(self):
        super().setUp()
        for name in S.PROJECTION_FILES:
            path = self.repository / "policy" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"public-readonly-canary\n" if name == "readonly-canary" else (S.ROOT / name).read_bytes())
        self.git("add", ".")
        self.git("commit", "-qm", "Record trusted policy projection")
        self.revision = self.git("rev-parse", "HEAD")
        self.snapshot = self.root / "materialized"
        self.snapshot.mkdir(mode=0o755)

    def make_snapshot(self):
        return S.materialize_snapshot(self.repository, self.revision, self.snapshot)

    def test_raw_snapshot_preserves_pristine_history_and_ignores_dirty_source(self):
        previous = self.git("rev-parse", "HEAD^")
        (self.repository / "ordinary.txt").write_text("untracked import shadow")
        (self.repository / ".git/config").write_text("malformed candidate configuration")
        identity = self.make_snapshot()
        S.verify_snapshot(self.snapshot, identity)
        self.assertEqual(identity["identity"]["commit"], self.revision)
        self.assertEqual(S.pristine_git_identity(self.snapshot, previous)["commit"], previous)
        self.assertFalse((self.snapshot / "ordinary.txt").exists())
        self.assertTrue((self.snapshot / ".git/index").is_file())
        self.assertFalse((self.snapshot / ".git/hooks").exists())
        self.assertEqual((self.snapshot / ".git/HEAD").read_text().strip(), self.revision)
        self.assertIn(".git/objects/pack", identity["files"])
        self.assertIn("policy/tools/test-evidence/runtime.py", identity["files"])
        status = subprocess.check_output(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                                          "status", "--porcelain", "--untracked-files=all"], cwd=self.snapshot,
                                         env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                                              "GIT_OPTIONAL_LOCKS": "0"})
        self.assertEqual(status, b"")
        S.verify_snapshot(self.snapshot, identity)

    def test_changed_materialized_code_is_rejected(self):
        identity = self.make_snapshot()
        path = self.snapshot / "policy/tools/test-evidence/runtime.py"
        path.chmod(0o644)
        path.write_text("changed runtime")
        path.chmod(0o444)
        with self.assertRaisesRegex(S.SandboxUnavailable, "inventory changed"):
            S.verify_snapshot(self.snapshot, identity)

    def test_unknown_empty_directory_or_import_shadow_is_not_invisible(self):
        identity = self.make_snapshot()
        for name, directory in (("json", True), ("json.py", False)):
            path = self.snapshot / name
            if directory:
                path.mkdir(mode=0o755)
            else:
                path.write_text("shadow")
                path.chmod(0o444)
            with self.subTest(name=name), self.assertRaises(S.SandboxUnavailable):
                S.verify_snapshot(self.snapshot, identity)
            path.rmdir() if directory else path.unlink()

    def test_snapshot_metadata_tamper_or_missing_object_is_rejected(self):
        identity = self.make_snapshot()
        path = self.snapshot / ".git/HEAD"
        path.chmod(0o644)
        path.write_text("ref: refs/heads/candidate\n")
        path.chmod(0o444)
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(self.snapshot, identity)

    def test_symlink_hardlink_and_writable_mode_are_rejected(self):
        identity = self.make_snapshot()
        path = self.snapshot / "alias"
        path.symlink_to(".git/HEAD")
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(self.snapshot, identity)
        path.unlink()
        os.link(self.snapshot / ".git/HEAD", path)
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(self.snapshot, identity)
        path.unlink()
        (self.snapshot / ".git/HEAD").chmod(0o644)
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(self.snapshot, identity)

    def test_tracked_symlink_or_submodule_never_enters_snapshot(self):
        for mode, oid in (("120000", ""), ("160000", self.revision)):
            # hash-object of empty stdin is a valid ordinary blob; update-index
            # writes only test metadata and does not execute any child source.
            if mode == "120000":
                oid = subprocess.check_output(["/usr/bin/git", "hash-object", "-w", "--stdin"],
                    cwd=self.repository, input=b"outside").decode().strip()
            self.git("update-index", "--add", "--cacheinfo", mode + "," + oid + ",unsupported")
            self.git("commit", "-qm", "Record unsupported source kind")
            self.revision = self.git("rev-parse", "HEAD")
            with self.subTest(mode=mode), self.assertRaises(S.SandboxUnavailable):
                self.make_snapshot()
            shutil.rmtree(self.snapshot)
            self.snapshot.mkdir(mode=0o755)
            self.git("update-index", "--force-remove", "unsupported")

    def test_private_projection_has_no_git_or_unrelated_sources_and_is_sealed(self):
        identity = self.make_snapshot()
        destination = self.root / "projection"
        destination.mkdir(mode=0o755)
        projection = S.project_policy(self.snapshot, destination, identity)
        self.assertEqual(set(projection), S._PROJECTION_INVENTORY)
        self.assertFalse((destination / ".git").exists())
        self.assertFalse((destination / "fixture.py").exists())
        sealed = S.bind_projection(destination, projection, {"binding": {"run_attempt": 1}})
        S.verify_projection(destination, sealed)
        with self.assertRaises(S.SandboxUnavailable):
            S.bind_projection(destination, sealed, {})
        (destination / "unexpected").mkdir(mode=0o755)
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_projection(destination, sealed)

    def test_candidate_policy_code_cannot_replace_trusted_projection(self):
        path = self.repository / "policy/tools/test-evidence/runtime.py"
        path.write_text("raise RuntimeError('candidate policy')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Alter candidate policy")
        self.revision = self.git("rev-parse", "HEAD")
        identity = self.make_snapshot()
        destination = self.root / "projection"
        destination.mkdir(mode=0o755)
        with self.assertRaisesRegex(S.SandboxUnavailable, "candidate cannot supply"):
            S.project_policy(self.snapshot, destination, identity)

    def test_raw_reader_enforces_output_bound_while_reading(self):
        with self.assertRaisesRegex(S.SandboxUnavailable, "exceeds bound"):
            S._git(self.repository, "cat-file", "commit", self.revision, limit=8)

    def test_final_tree_rename_deletion_and_executable_mode_preserve_exact_git_semantics(self):
        self.git("mv", "test.py", "renamed.py")
        (self.repository / "renamed.py").chmod(0o755)
        self.git("add", "--all")
        self.git("commit", "-qm", "Rename immutable executable fixture")
        self.revision = self.git("rev-parse", "HEAD")
        identity = self.make_snapshot()
        self.assertFalse((self.snapshot / "test.py").exists())
        self.assertEqual(identity["files"]["renamed.py"]["mode"], 0o555)
        self.assertEqual((self.snapshot / "renamed.py").read_bytes(), (self.repository / "renamed.py").read_bytes())
        S.verify_snapshot(self.snapshot, identity)

    def test_candidate_alias_or_nonempty_destination_never_overwrites_sources(self):
        marker = self.snapshot / "keep"
        marker.write_text("existing protected data")
        with self.assertRaises(S.SandboxUnavailable):
            self.make_snapshot()
        self.assertEqual(marker.read_text(), "existing protected data")

    def test_tracked_build_inputs_cannot_be_hidden_by_writable_mount(self):
        (self.repository / "build").mkdir()
        (self.repository / "build/input.py").write_text("tracked build input")
        self.git("add", ".")
        self.git("commit", "-qm", "Record colliding source input")
        self.revision = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(S.SandboxUnavailable, "hide tracked"):
            self.make_snapshot()


class StreamedCandidateTests(GitFixture):
    def snapshot(self, name="candidate", context=()):
        destination = self.root / name
        destination.mkdir(mode=0o755)
        value = S.materialize_candidate_snapshot(self.repository, self.revision, destination, context_revisions=context)
        S.verify_snapshot(destination, value)
        return destination, value

    def commit(self, message="Record streamed source"):
        self.git("add", "--all")
        self.git("commit", "-qm", message)
        self.revision = self.git("rev-parse", "HEAD")
        return self.revision

    def status(self, destination, *arguments):
        return subprocess.check_output(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", *arguments],
            cwd=destination, stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_OPTIONAL_LOCKS": "0"}).decode().strip()

    def test_actual_execution_identity_preserves_private_index_and_rejects_changed_source(self):
        import execution
        destination, value = self.snapshot()
        index = destination / ".git/index"
        original = index.read_bytes()
        self.assertEqual(index.stat().st_mode & 0o777, 0o444)
        environment = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
                       "GIT_CONFIG_NOSYSTEM": "1", "GIT_OPTIONAL_LOCKS": "1"}
        # Exercise the production identity reader, rather than this class's
        # status helper, which already suppresses optional Git index writes.
        with patch.dict(os.environ, environment, clear=True):
            for _ in range(3):
                self.assertEqual(execution.checkout_identity(destination),
                    (self.revision, value["identity"]["tree"]))
                self.assertEqual(index.stat().st_mode & 0o777, 0o444)
                self.assertEqual(index.read_bytes(), original)
                S.verify_snapshot(destination, value)
            changed = destination / "test.py"
            changed.chmod(0o644)
            changed.write_bytes(changed.read_bytes() + b"\n# changed candidate\n")
            changed.chmod(0o444)
            with self.assertRaises(execution.ExecutionError):
                execution.checkout_identity(destination)
            with self.assertRaises(S.SandboxUnavailable):
                S.verify_snapshot(destination, value)
        self.assertEqual(index.stat().st_mode & 0o777, 0o444)
        self.assertEqual(index.read_bytes(), original)

    def test_large_blob_exceeding_actual_33554792_byte_source_stays_streamed(self):
        path = self.repository / "large.bin"
        remaining = 33_554_793
        with path.open("wb") as output:
            while remaining:
                block = b"x" * min(65536, remaining)
                output.write(block)
                remaining -= len(block)
        self.commit()
        tracemalloc.start()
        try:
            destination, value = self.snapshot()
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 8 * 1024 ** 2, "Python buffered a large candidate blob")
        self.assertEqual((destination / "large.bin").stat().st_size, 33_554_793)
        self.assertEqual(S._file_hash(destination / "large.bin"), S._file_hash(path))
        self.assertEqual(self.status(destination, "status", "--porcelain"), "")
        self.assertEqual(value["profile"], "streamed-candidate-source-v1")

    def test_repeated_blobs_and_subtrees_are_read_from_git_once(self):
        for directory in ("first", "second"):
            (self.repository / directory).mkdir()
            (self.repository / directory / "shared.py").write_text("raise RuntimeError('never execute')\n")
        self.commit()
        actual = S.os.write
        queries = []
        def write(descriptor, data):
            if len(data) == 41 and data.endswith(b"\n"):
                queries.append(data[:-1])
            return actual(descriptor, data)
        with patch.object(S.os, "write", side_effect=write):
            destination, value = self.snapshot()
        self.assertEqual(len(queries), value["objects"])
        self.assertEqual(len(queries), len(set(queries)))
        self.assertEqual((destination / "first/shared.py").read_bytes(), (destination / "second/shared.py").read_bytes())
        self.assertEqual((destination / "first/shared.py").stat().st_nlink, 1)

    def test_complete_stream_does_not_reopen_the_original_object_store_for_hash_verification(self):
        (self.repository / ".gitmodules").write_text("# Public metadata; no submodule checkout.\n")
        self.commit()
        original = S._StreamedObjects.verify
        source_objects = self.repository / ".git/objects"
        closed_objects = self.root / "closed-original-objects"
        expected = (self.repository / "test.py").read_bytes()

        def verify(reader, *arguments):
            # Independent verification must need only the bounded private
            # stream, even when the original packed store is no longer usable.
            source_objects.rename(closed_objects)
            try:
                return original(reader, *arguments)
            finally:
                closed_objects.rename(source_objects)

        with patch.object(S._StreamedObjects, "verify", verify):
            destination, value = self.snapshot()
        self.assertEqual((destination / "test.py").read_bytes(), expected)
        self.assertEqual(value["identity"]["commit"], self.revision)
        self.assertEqual(self.status(destination, "status", "--porcelain"), "")

    def test_real_object_count_above_legacy_4096_limit_materializes_completely(self):
        folder = self.repository / "many"
        folder.mkdir()
        for number in range(4100):
            (folder / str(number)).write_text(str(number))
        self.commit()
        destination, value = self.snapshot()
        self.assertGreater(value["objects"], 4096)
        self.assertEqual(len(list((destination / "many").iterdir())), 4100)
        self.assertEqual(self.status(destination, "status", "--porcelain"), "")

    def test_missing_ancestry_is_truthfully_shallow_not_fabricated_or_walked(self):
        parent = self.revision
        (self.repository / "new.py").write_text("new source")
        self.commit()
        # The root commit/complete tree is available, but its parent object is
        # deliberately absent. The snapshot must not fetch or infer its data.
        (self.repository / ".git/objects" / parent[:2] / parent[2:]).unlink()
        destination, value = self.snapshot()
        self.assertEqual(value["identity"]["parents"], [parent])
        self.assertEqual(value["git_context"]["shallow"], [self.revision])
        self.assertEqual(self.status(destination, "rev-parse", "--is-shallow-repository"), "true")
        self.assertEqual(self.status(destination, "log", "--format=%H"), self.revision)
        self.assertIn("parent " + parent, self.status(destination, "cat-file", "commit", self.revision))
        with self.assertRaises(subprocess.CalledProcessError):
            self.status(destination, "cat-file", "-e", parent)
        with self.assertRaises(S.SandboxUnavailable):
            S.pristine_git_identity(destination, self.revision)
        with self.assertRaises(S.SandboxUnavailable):
            self.snapshot("missing-context", (parent,))

    def test_same_file_tree_different_explicit_history_has_different_context_identity(self):
        oldest = self.revision
        self.git("commit", "--allow-empty", "-qm", "Second unchanged program")
        parent = self.git("rev-parse", "HEAD")
        self.git("commit", "--allow-empty", "-qm", "Third unchanged program")
        self.revision = self.git("rev-parse", "HEAD")
        first, shallow = self.snapshot()
        second, expanded = self.snapshot("expanded", (parent,))
        self.assertEqual(shallow["identity"]["tree"], expanded["identity"]["tree"])
        self.assertNotEqual(shallow["digest"], expanded["digest"])
        self.assertEqual(expanded["git_context"]["shallow"], [parent])
        self.assertEqual(self.status(second, "log", "--format=%H").splitlines(), [self.revision, parent])
        complete, full = self.snapshot("complete", (parent, oldest))
        self.assertEqual(full["git_context"]["shallow"], [])
        self.assertEqual(self.status(complete, "rev-parse", "--is-shallow-repository"), "false")
        self.assertEqual(len(self.status(complete, "log", "--format=%H").splitlines()), 3)

    def test_source_shallow_configuration_and_dirty_worktree_do_not_change_raw_context(self):
        (self.repository / "new").write_text("source")
        self.commit()
        (self.repository / ".git/shallow").write_text(self.revision + "\n")
        (self.repository / ".git/config").write_text("malformed ignored configuration")
        (self.repository / "test.py").write_text("dirty bytes must never execute")
        destination, value = self.snapshot()
        self.assertNotEqual((destination / "test.py").read_bytes(), (self.repository / "test.py").read_bytes())
        self.assertEqual(value["git_context"]["shallow"], [self.revision])

    def test_sparse_source_checkout_still_materializes_complete_candidate_tree(self):
        (self.repository / "other").mkdir()
        (self.repository / "other/retained.py").write_text("complete immutable inventory")
        self.commit()
        self.git("sparse-checkout", "init", "--no-cone")
        self.git("sparse-checkout", "set", "--no-cone", "/test.py")
        self.assertFalse((self.repository / "other/retained.py").exists())
        destination, _value = self.snapshot()
        self.assertEqual((destination / "other/retained.py").read_text(), "complete immutable inventory")

    def test_actual_corrupt_blob_identity_is_rejected_before_a_snapshot_returns(self):
        oid = self.git("rev-parse", "HEAD:test.py")
        path = self.repository / ".git/objects" / oid[:2] / oid[2:]
        path.chmod(0o644)
        path.write_bytes(zlib.compress(b"blob 4\0evil"))
        with self.assertRaisesRegex(S.SandboxUnavailable, "hash differs"):
            self.snapshot()

    def test_copy_corruption_cannot_become_its_own_trusted_inventory_baseline(self):
        blob = self.git("rev-parse", "HEAD:test.py")
        for number, relative in enumerate(("test.py", ".git/objects/" + blob[:2] + "/" + blob[2:])):
            actual = S._files
            corrupted = []
            def inspect(root, **kwargs):
                if not corrupted:
                    path = root / relative
                    body = path.read_bytes()
                    path.chmod(0o644)
                    path.write_bytes(bytes([body[0] ^ 1]) + body[1:])
                    path.chmod(0o444)
                    corrupted.append(True)
                return actual(root, **kwargs)
            with patch.object(S, "_files", side_effect=inspect), self.subTest(relative=relative):
                with self.assertRaisesRegex(S.SandboxUnavailable, "verified object stream"):
                    self.snapshot("copy-corruption-" + str(number))
            self.assertEqual(corrupted, [True])

    def test_extra_import_namespace_alias_metadata_and_file_mode_are_not_ignored(self):
        destination, value = self.snapshot()
        for name, kind in (("json.py", "file"), ("json", "directory"), ("alias", "symlink"), (".git/refs/topic", "file")):
            path = destination / name
            if kind == "file":
                path.write_text(self.revision + "\n" if name.startswith(".git/") else "shadow")
                path.chmod(0o444)
            elif kind == "directory":
                path.mkdir(mode=0o755)
            else:
                path.symlink_to("test.py")
            with self.subTest(name=name), self.assertRaises(S.SandboxUnavailable):
                S.verify_snapshot(destination, value)
            path.rmdir() if kind == "directory" else path.unlink()
        (destination / "test.py").chmod(0o555)
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(destination, value)

    def test_final_rename_and_executable_mode_still_match_pristine_git_status(self):
        self.git("mv", "test.py", "renamed.py")
        (self.repository / "renamed.py").chmod(0o755)
        self.commit()
        destination, value = self.snapshot()
        self.assertFalse((destination / "test.py").exists())
        self.assertEqual(value["files"]["renamed.py"]["mode"], 0o555)
        self.assertEqual(self.status(destination, "status", "--porcelain"), "")

    def test_existing_finite_trusted_projection_validator_supports_streamed_snapshot(self):
        for name in S.PROJECTION_FILES:
            path = self.repository / "policy" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"public-readonly-canary\n" if name == "readonly-canary" else (S.ROOT / name).read_bytes())
        self.commit()
        destination, value = self.snapshot()
        projection = self.root / "projection"
        projection.mkdir(mode=0o755)
        inventory = S.project_policy(destination, projection, value)
        S.verify_projection(projection, inventory)
        self.assertEqual((projection / "tools/test-evidence/runtime.py").read_bytes(), (S.ROOT / "tools/test-evidence/runtime.py").read_bytes())

    def test_symlink_gitlink_and_tracked_build_collisions_fail_closed(self):
        for kind in ("symlink", "gitlink", "build"):
            if kind == "symlink":
                (self.repository / "link").symlink_to("test.py")
            elif kind == "gitlink":
                self.git("update-index", "--add", "--cacheinfo", "160000," + self.revision + ",link")
            else:
                (self.repository / "build").mkdir()
                (self.repository / "build/reader.py").write_text("tracked")
            if kind == "gitlink":
                self.git("commit", "-qm", "Record gitlink")
                self.revision = self.git("rev-parse", "HEAD")
            else:
                self.commit()
            with self.subTest(kind=kind), self.assertRaises(S.SandboxUnavailable):
                self.snapshot(kind)
            if kind != "build":
                (self.repository / "link").unlink(missing_ok=True)
                self.git("update-index", "--force-remove", "link")

    def test_declared_object_memory_time_and_count_limits_fail_and_reap_git(self):
        for name, maximum in (("_STREAMED_BLOB", 1), ("_STREAMED_BYTES", 1), ("_STREAMED_OBJECTS", 1), ("_STREAMED_SECONDS", 0)):
            processes = []
            actual = S.subprocess.Popen
            def start(*args, **kwargs):
                process = actual(*args, **kwargs)
                processes.append(process)
                return process
            with patch.object(S, name, maximum), patch.object(S.subprocess, "Popen", side_effect=start):
                with self.subTest(name=name), self.assertRaises(S.SandboxUnavailable):
                    self.snapshot(name)
            self.assertTrue(processes)
            self.assertTrue(all(process.poll() is not None for process in processes))
        with patch.object(S.resource, "prlimit", side_effect=PermissionError("unit fixture denied")), self.assertRaises(OSError):
            self.snapshot("limits-unavailable")

    def test_context_cannot_claim_omitted_parent_or_reorder_raw_merge_parents(self):
        base = self.revision
        self.git("checkout", "-qb", "other")
        (self.repository / "other.py").write_text("other")
        other = self.commit()
        self.git("checkout", "-q", "main")
        (self.repository / "main.py").write_text("main")
        head = self.commit()
        self.git("merge", "--no-ff", "-qm", "Merge fixed source", "other")
        self.revision = self.git("rev-parse", "HEAD")
        destination, value = self.snapshot(context=(head, other))
        self.assertEqual(value["identity"]["parents"], [head, other])
        altered = json.loads(json.dumps(value))
        altered["git_context"]["shallow"] = []
        altered["digest"] = "sha256:" + S.hashlib.sha256(S._canonical({k:v for k,v in altered.items() if k != "digest"})).hexdigest()
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(destination, altered)
        altered = json.loads(json.dumps(value))
        altered["identity"]["parents"].reverse()
        altered["git_context"]["commits"][self.revision]["parents"].reverse()
        altered["digest"] = "sha256:" + S.hashlib.sha256(S._canonical({k:v for k,v in altered.items() if k != "digest"})).hexdigest()
        with self.assertRaises(S.SandboxUnavailable):
            S.verify_snapshot(destination, altered)


class SupervisorControlTests(unittest.TestCase):
    def test_actions_commands_ansi_carriage_returns_and_invalid_utf8_are_encoded(self):
        value = b"::set-output name=passed::true\r\n::error::fake\x1b[2K\xff"
        encoded = S.safe_diagnostic(value)
        self.assertEqual(len(encoded.splitlines()), 1)
        self.assertTrue(encoded.startswith("candidate-output: "))
        self.assertNotIn("\x1b", encoded)
        self.assertNotIn("\r", encoded)
        self.assertNotIn("\n", encoded)

    def test_actual_zero_exit_is_still_not_reusable_or_cleanup_proof(self):
        result = S._diagnostic_process([sys.executable, "-c", "print('fixture')"], timeout=2)
        self.assertEqual(result["exit_code"], 0)
        self.assertIs(result["reusable"], False)
        self.assertIsNone(result["descendants_empty"])
        self.assertIsNone(result["post_runtime"])

    def test_actual_failure_timeout_and_output_flood_do_not_become_passes(self):
        failed = S._diagnostic_process([sys.executable, "-c", "raise SystemExit(7)"], timeout=2)
        self.assertEqual(failed["exit_code"], 7)
        timed = S._diagnostic_process([sys.executable, "-c", "import time;time.sleep(10)"], timeout=0.1)
        self.assertEqual(timed["reason"], "timeout")
        self.assertNotEqual(timed["exit_code"], 0)
        flood = S._diagnostic_process([sys.executable, "-c", "print('x'*100000)"], timeout=2, limit=256)
        self.assertEqual(flood["reason"], "output-limit")
        for result in (failed, timed, flood):
            self.assertFalse(result["reusable"])
            self.assertIsNone(result["post_runtime"])

    def test_process_environment_and_extra_descriptors_are_not_inherited(self):
        with tempfile.TemporaryFile() as private:
            os.set_inheritable(private.fileno(), True)
            script = "import os;assert 'ACTIONS_RUNTIME_TOKEN' not in os.environ;\ntry: os.fstat(" + str(private.fileno()) + ")\nexcept OSError: pass\nelse: raise SystemExit(9)"
            with patch.dict(os.environ, {"ACTIONS_RUNTIME_TOKEN": "fixture-only-not-a-token"}):
                result = S._diagnostic_process([sys.executable, "-c", script], timeout=2)
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["reusable"])

    def test_missing_tool_fails_explicitly_without_raw_path_or_fallback(self):
        with self.assertRaises(S.SandboxUnavailable) as raised:
            S._diagnostic_process(["/missing/private-selector"], timeout=1)
        self.assertNotIn("private-selector", str(raised.exception))

    def test_even_empty_scope_parser_fixtures_cannot_enable_a_post_probe(self):
        self.assertEqual(S.parse_scope_events(b"populated 0\nfrozen 0\n"), {"populated": 0, "frozen": 0})
        for source in (b"", b"populated 0\n", b"populated 0\npopulated 1\nfrozen 0\n", b"populated 2\nfrozen 0\n",
                       b"populated 0\nfrozen 0\nunknown 0\n", b"x" * 4097):
            with self.subTest(source=source[:40]), self.assertRaises(S.SandboxUnavailable):
                S.parse_scope_events(source)
        with patch.object(PROBE, "measure_local_process") as probe:
            for claim in ({"populated": 0, "frozen": 0}, {"descendants_empty": True}, {"exit_code": 0}):
                with self.assertRaises(S.SandboxUnavailable):
                    S.capture_after_execution(claim, probe=probe)
            probe.assert_not_called()


class ProbeTests(Fixture):
    def prepare_proc(self):
        directory = self.root / "proc/self"
        directory.mkdir(parents=True)
        status = "Uid:\t1000\t1000\t1000\t1000\nGid:\t1000\t1000\t1000\t1000\nNoNewPrivs:\t1\n"
        status += "".join(name + ":\t0000000000000000\n" for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
        (directory / "status").write_text(status)
        for name in ("uid_map", "gid_map"):
            (directory / name).write_text("0 2001 1\n")
        return directory

    def test_observation_reports_actual_fixture_values_without_claiming_protection(self):
        directory = self.prepare_proc()
        observation = PROBE.process_observation(directory.parent)
        self.assertEqual(observation["identity_maps"]["uid_map"], [[0, 2001, 1]])
        (directory / "status").write_text((directory / "status").read_text().replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"))
        self.assertEqual(PROBE.process_observation(directory.parent)["status"]["NoNewPrivs"], "0")

    def test_missing_duplicate_or_malformed_process_metadata_rejected(self):
        directory = self.prepare_proc()
        original = (directory / "status").read_text()
        for status in (original.replace("NoNewPrivs:\t1\n", ""), original + "NoNewPrivs:\t1\n", original.replace("0000000000000000", "unknown", 1)):
            (directory / "status").write_text(status)
            with self.assertRaises(ValueError):
                PROBE.process_observation(directory.parent)

    def test_capture_calls_actual_runtime_probe_preserving_exact_values_as_diagnostic_only(self):
        actual = {"fixture": "measured effective interpreter, tools and variants"}
        with patch.object(PROBE, "process_observation", return_value={}), patch.object(PROBE.runtime, "capture_host_environment", return_value=actual) as capture:
            result = PROBE.measure_local_process()
        capture.assert_called_once_with()
        self.assertIs(result["environment"], actual)
        self.assertEqual(result["measurement"], "local-process")
        self.assertEqual(result["authority"], "none")
        self.assertFalse(result["reusable"])

    def test_unsupported_runtime_is_unavailable_never_matching_unknown(self):
        with patch.object(PROBE, "process_observation", return_value={}), patch.object(PROBE.runtime, "capture_host_environment", side_effect=PROBE.runtime.RuntimeIdentityError("unavailable")):
            result = PROBE.measure_local_process()
        self.assertIsNone(result["environment"])
        self.assertEqual(result["unavailable"], "runtime-identity-unavailable")
        self.assertFalse(result["reusable"])


if __name__ == "__main__":
    unittest.main()
