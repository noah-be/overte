#!/usr/bin/env python3
"""Host diagnostic parsers/control fixtures; no local privileged host probes."""

from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import sandbox
import sandbox_host as H


def context():
    return {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": "noah-l-frank/overte",
            "GITHUB_REPOSITORY_ID": "1319052603", "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": H.WORKFLOW,
            "RUNNER_ENVIRONMENT": "github-hosted", "ImageOS": "ubuntu24", "ImageVersion": "20261012.1.0", "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKFLOW_SHA": "a" * 40,
            "SUDO_UID": "1001", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}


def protection_result():
    flags = {"parent_proc_hidden", "protected_read_hidden", "protected_write_hidden", "command_files_hidden", "scope_hidden",
             "source_readonly", "git_readonly", "venv_readonly", "policy_readonly", "loopback", "only_loopback_interface",
             "no_ipv4_default_route", "credential_environment_absent", "path_socket_hidden", "abstract_socket_hidden",
             "home_writable", "temp_writable", "build_writable", "sudo_denied", "venv_aliases", "protected_descriptors_absent", "readonly_mount_flags", "git_pristine"}
    return {"exit_code": 0, "reason": None, "live_before_cleanup": 0,
            "cleanup": {"kernel_populated": 0, "subtree_kill": True}, "observation": {
                "process": {"NoNewPrivs": "1", **{key: "0000000000000000" for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}},
                "namespaces": {key: value + 100 for key, value in outside().items()}, "uid_map": "1002 1002 1\n",
                **dict.fromkeys(flags, True)}}


def outside():
    return dict(zip(("user", "mnt", "pid", "net", "ipc", "uts"), range(1, 7)))


class ContextTests(unittest.TestCase):
    def test_source_manual_main_and_actual_host_root_are_all_required(self):
        self.assertEqual(H.host_context(context(), effective_uid=0), 1001)
        with self.assertRaises(H.Unavailable):
            H.host_context(context(), effective_uid=1001)
        for key, value in (("GITHUB_EVENT_NAME", "pull_request"), ("GITHUB_REF", "refs/heads/ci/example"),
                           ("GITHUB_REPOSITORY", "overte-org/overte"), ("RUNNER_ENVIRONMENT", "self-hosted"),
                           ("ImageOS", "ubuntu22"), ("SUDO_UID", "0"), ("GITHUB_SHA", "HEAD"), ("GITHUB_WORKFLOW_SHA", "b" * 40)):
            with self.subTest(key=key), self.assertRaises(H.Unavailable):
                H.host_context({**context(), key: value}, effective_uid=0)

    def test_local_main_fails_without_any_provisioning_or_workload_start(self):
        with (patch.object(H.os, "geteuid", return_value=1001), patch.object(H.subprocess, "Popen") as process,
              patch.object(H.os, "mkdir") as mkdir, patch.object(H.sys, "stdout", new_callable=io.StringIO) as output):
            code = H.main([])
        self.assertEqual(code, 1)
        process.assert_not_called()
        mkdir.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "unavailable")
        self.assertFalse(report["production_qualified"])

    def test_fixed_account_requires_actual_distinct_uid_and_no_sudo_grants(self):
        account = SimpleNamespace(pw_uid=2001, pw_gid=2001, pw_shell="/usr/sbin/nologin")
        denied = SimpleNamespace(returncode=1, stdout=b"", stderr=b"User overte-ci-qualification is not allowed to run sudo on host.\n")
        with (patch.object(H.pwd, "getpwnam", return_value=account), patch.object(H.os, "getgrouplist", return_value=[2001]),
              patch.object(H.grp, "getgrgid", return_value=SimpleNamespace(gr_name="qualification")), patch.object(H, "command", return_value=denied)):
            self.assertEqual(H.verify_account(1001), (2001, 2001))
            with self.assertRaises(H.Unavailable):
                H.verify_account(2001)
            with patch.object(H, "command", return_value=SimpleNamespace(returncode=0, stdout=b"sudo grant", stderr=b"")), self.assertRaises(H.Unavailable):
                H.verify_account(1001)
            with patch.object(H, "command", return_value=SimpleNamespace(returncode=1, stdout=b"", stderr=b"policy plugin error")), self.assertRaises(H.Unavailable):
                H.verify_account(1001)

    def test_privileged_groups_are_not_hidden_by_sudo_command_failure(self):
        account = SimpleNamespace(pw_uid=2001, pw_gid=2001, pw_shell="/usr/sbin/nologin")
        with (patch.object(H.pwd, "getpwnam", return_value=account), patch.object(H.os, "getgrouplist", return_value=[2001]),
              patch.object(H.grp, "getgrgid", return_value=SimpleNamespace(gr_name="docker")), patch.object(H, "command") as query):
            with self.assertRaises(H.Unavailable):
                H.verify_account(1001)
            query.assert_not_called()


class KernelObservationTests(unittest.TestCase):
    def test_delegation_requires_actual_manager_and_kernel_membership_agreement(self):
        props = "ControlGroup=/system.slice/overte-shared-qualification-123-1.service\nDelegate=yes\n"
        member = "0::/system.slice/overte-shared-qualification-123-1.service\n"
        self.assertEqual(str(H.delegation_path(props, member)), "/sys/fs/cgroup/system.slice/overte-shared-qualification-123-1.service")
        for properties, membership in ((props.replace("yes", "no"), member), (props, "0::/other.service\n"),
                                       (props.replace("/system.slice", "/../system.slice"), member), (props + "Delegate=yes\n", member),
                                       ('{"Delegate":true}', member), ("ControlGroup=/\nDelegate=yes\n", "0::/\n")):
            with self.subTest(properties=properties), self.assertRaises(H.Unavailable):
                H.delegation_path(properties, membership)

    def test_actual_delegation_moves_only_controller_into_its_own_child(self):
        unit = "overte-shared-qualification-123-1.service"
        delegated = "/sys/fs/cgroup/system.slice/" + unit
        membership = "0::/system.slice/" + unit
        facts = SimpleNamespace(returncode=0, stdout=("ControlGroup=/system.slice/" + unit + "\nDelegate=yes\n").encode())
        writes = []
        def read(path, **_kwargs):
            if str(path) == "/proc/self/mountinfo":
                return "28 21 0:25 / /sys/fs/cgroup rw,nosuid,nodev,noexec - cgroup2 cgroup rw\n"
            self.assertEqual(str(path), "/proc/self/cgroup")
            return membership + ("/diagnostic-controller" if writes else "") + "\n"
        def write(descriptor, payload):
            writes.append((descriptor, payload))
            return len(payload)
        with (patch.dict(H.os.environ, context(), clear=True), patch.object(H, "command", return_value=facts) as query,
              patch.object(H.Path, "read_text", read), patch.object(H.Path, "lstat", return_value=SimpleNamespace(st_mode=0o40755, st_uid=0)),
              patch.object(H.Path, "mkdir") as mkdir, patch.object(H.os, "open", return_value=77) as opened,
              patch.object(H.os, "write", side_effect=write), patch.object(H.os, "close"), patch.object(H.os, "getpid", return_value=54321)):
            self.assertEqual(H.prepare_delegation(), Path(delegated))
        self.assertEqual(writes, [(77, b"54321\n")])
        mkdir.assert_called_once_with(mode=0o700)
        self.assertEqual(opened.call_args.args[0], Path(delegated) / "diagnostic-controller/cgroup.procs")
        self.assertIn(unit, query.call_args.args[0])

    def test_unverified_delegation_never_creates_or_moves_a_process(self):
        facts = SimpleNamespace(returncode=0, stdout=b"ControlGroup=/system.slice/unit.service\nDelegate=yes\n")
        with (patch.dict(H.os.environ, context(), clear=True), patch.object(H, "command", return_value=facts),
              patch.object(H.Path, "read_text", return_value="0::/unrelated.service\n"), patch.object(H.Path, "mkdir") as mkdir,
              patch.object(H.os, "open") as opened, self.assertRaises(H.Unavailable)):
            H.prepare_delegation()
        mkdir.assert_not_called()
        opened.assert_not_called()

    def test_actual_fixed_cgroup2_mount_is_required_before_scope_creation(self):
        good = "28 21 0:25 / /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime - cgroup2 cgroup rw\n"
        H.cgroup_mount(good)
        for value in ("", good + good, good.replace("cgroup2", "tmpfs"), good.replace("/ /sys", "/delegated /sys"),
                      good.replace("rw,nosuid", "ro,nosuid")):
            with self.subTest(value=value), self.assertRaises(H.Unavailable):
                H.cgroup_mount(value)

    def test_scope_json_or_incomplete_file_cannot_be_interpreted_as_kernel_events(self):
        self.assertEqual(H.scope_events(b"populated 0\nfrozen 0\n"), {"populated": 0, "frozen": 0})
        for value in (b'{"populated":0}', b"populated 0\n", b"populated 0\nfrozen 0\npopulated 1\n", b"populated 9\nfrozen 0\n", b"x" * 4097):
            with self.subTest(value=value[:40]), self.assertRaises(H.Unavailable):
                H.scope_events(value)

    def test_control_file_wrong_owner_or_writable_group_fails(self):
        scope = object.__new__(H.OwnedScope)
        scope.directory, scope.leaf_directory, scope.fds = 7, 8, []
        for owner, mode in ((2001, 0o100644), (0, 0o100666)):
            with (patch.object(H.os, "open", return_value=99), patch.object(H.os, "fstat", return_value=SimpleNamespace(st_uid=owner, st_mode=mode)),
                  self.assertRaises(H.Unavailable)):
                scope.open("cgroup.events", os.O_RDONLY)

    def test_attach_checks_actual_host_uid_then_membership_before_release(self):
        scope = object.__new__(H.OwnedScope)
        scope.uid, scope.gid, scope.procs = 2001, 2001, 77
        child = SimpleNamespace(pid=999999)
        with (patch.object(H.Path, "read_text", return_value="Uid:\t2001\t2001\t2001\t2001\nGid:\t2001\t2001\t2001\t2001\nGroups:\t\n"),
              patch.object(scope, "populated", side_effect=[0, 1]), patch.object(scope, "members", return_value={child.pid}), patch.object(H.os, "write") as write):
            scope.attach(child)
        write.assert_called_once_with(77, b"999999\n")
        with patch.object(H.Path, "read_text", return_value="Uid:\t0\t0\t0\t0\n"), patch.object(scope, "populated", return_value=0), patch.object(H.os, "write") as write:
            with self.assertRaises(H.Unavailable):
                scope.attach(child)
            write.assert_not_called()
        for status in ("Uid:\t2001\t2001\t2001\t2001\nGid:\t0\t0\t0\t0\nGroups:\t\n",
                       "Uid:\t2001\t2001\t2001\t2001\nGid:\t2001\t2001\t2001\t2001\nGroups:\t2001 27\n"):
            with (patch.object(H.Path, "read_text", return_value=status), patch.object(scope, "populated", return_value=0),
                  patch.object(H.os, "write") as write, self.assertRaises(H.Unavailable)):
                scope.attach(child)
            write.assert_not_called()

    def test_kill_wait_observes_recursive_populated_zero_not_bwrap_exit(self):
        scope = object.__new__(H.OwnedScope)
        scope.kill_fd = 7
        with patch.object(H.os, "write") as write, patch.object(scope, "populated", side_effect=[1, 1, 0]), patch.object(H.time, "sleep"):
            self.assertEqual(scope.kill_and_wait(), {"kernel_populated": 0, "subtree_kill": True})
        write.assert_called_once_with(7, b"1\n")
        with patch.object(H.os, "write"), patch.object(scope, "populated", return_value=1), patch.object(H.time, "monotonic", side_effect=[0, 4]), self.assertRaises(H.Unavailable):
            scope.kill_and_wait()


class BootstrapTests(unittest.TestCase):
    def test_closed_gate_never_executes_a_workload(self):
        reader, writer = os.pipe()
        os.close(writer)
        with (patch.object(H.os, "getuid", return_value=2001), patch.object(H.os, "geteuid", return_value=2001),
              patch.object(H, "trusted_cleanup_canaries") as canaries, patch.object(H.os, "execve") as execute):
            with self.assertRaises(H.Unavailable):
                H.bootstrap(reader, "/never-read-candidate-plan", "fork-exit")
        canaries.assert_not_called()
        execute.assert_not_called()

    def test_root_bootstrap_never_accepts_a_generic_privileged_command(self):
        with patch.object(H.os, "getuid", return_value=0), patch.object(H.os, "execve") as execute:
            with self.assertRaises(H.Unavailable):
                H.bootstrap(99, "/candidate.json")
        execute.assert_not_called()

    def test_release_executes_only_fixed_bwrap_from_explicit_vector(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            plan.write_text('["/usr/bin/bwrap","--unshare-pid","--","/usr/bin/true"]')
            reader, writer = os.pipe()
            os.write(writer, b"1")
            os.close(writer)
            with patch.object(H.os, "getuid", return_value=2001), patch.object(H.os, "geteuid", return_value=2001), patch.object(H.os, "execve") as execute:
                H.bootstrap(reader, str(plan))
            execute.assert_called_once_with("/usr/bin/bwrap", json.loads(plan.read_text()), {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})

    def test_trusted_cleanup_canaries_start_only_after_release_and_before_fixed_exec(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            plan.write_text('["/usr/bin/bwrap","--unshare-pid","--","/usr/bin/true"]')
            reader, writer = os.pipe()
            os.write(writer, b"1")
            os.close(writer)
            events = []
            with (patch.object(H.os, "getuid", return_value=2001), patch.object(H.os, "geteuid", return_value=2001),
                  patch.object(H, "trusted_cleanup_canaries", side_effect=lambda count: events.append(("controls", count))),
                  patch.object(H.os, "execve", side_effect=lambda *_: events.append(("exec", None)))):
                H.bootstrap(reader, str(plan), "fork-exit")
            self.assertEqual(events, [("controls", 3), ("exec", None)])

    def test_fixed_control_parent_requires_each_readiness_acknowledgement(self):
        with patch.object(H.os, "fork", return_value=999999) as fork, patch.object(H.os, "read", side_effect=[b"1", b"11"]):
            H.trusted_cleanup_canaries(3)
        self.assertEqual(fork.call_count, 3)
        with patch.object(H.os, "fork", return_value=999999), patch.object(H.os, "read", return_value=b""):
            with self.assertRaisesRegex(H.Unavailable, "did not become ready"):
                H.trusted_cleanup_canaries(1)

    def test_fixed_control_child_detaches_closes_streams_and_outlives_case_deadline(self):
        events = []
        with (patch.object(H.os, "pipe2", return_value=(77, 78)), patch.object(H.os, "fork", return_value=0),
              patch.object(H.os, "setsid", side_effect=lambda: events.append("detached")),
              patch.object(H.os, "close", side_effect=lambda fd: events.append(("close", fd))),
              patch.object(H.os, "write", side_effect=lambda fd, data: events.append(("ready", fd, data))),
              patch.object(H.time, "sleep", side_effect=lambda seconds: events.append(("lifetime", seconds))),
              patch.object(H.os, "_exit", side_effect=SystemExit), self.assertRaises(SystemExit)):
            H.trusted_cleanup_canaries(1)
        readiness = events.index(("ready", 78, b"1"))
        self.assertLess(events.index("detached"), readiness)
        for descriptor in (0, 1, 2):
            self.assertLess(events.index(("close", descriptor)), readiness)
        self.assertIn(("lifetime", 60), events)


class SupervisorFixtures(unittest.TestCase):
    def run_fixture(self, *, reject_attachment=False, case="protections", live=1, members=None, events=None):
        events = [] if events is None else events
        class Scope:
            empty = False
            def attach(self, _process):
                events.append("attach")
                if reject_attachment:
                    raise H.Unavailable("fixture attachment failed")
            def populated(self):
                events.append("kernel-populated")
                return 0 if self.empty else live
            def members(self):
                events.append("kernel-members")
                return members if members is not None else {1000001, 1000002, 1000003}
            def kill_and_wait(self):
                events.append("kernel-kill-empty")
                self.empty = True
                return {"kernel_populated": 0, "subtree_kill": True}
        scope = Scope()
        class Process:
            pid = 999999
            returncode = 0
            def poll(self):
                return 0
            def wait(self, timeout):
                events.append("initial-command-reaped")
                if self.gate is not None:
                    os.close(self.gate)
                    self.gate = None
                return 0
            def kill(self):
                events.append("kill-bootstrap")
        process = Process()
        def start(_argv, **kwargs):
            self.assertEqual(kwargs["user"], 2001)
            self.assertEqual(kwargs["group"], 2001)
            self.assertEqual(kwargs["extra_groups"], ())
            self.assertTrue(kwargs["close_fds"])
            process.gate = os.dup(kwargs["pass_fds"][0])
            reader, writer = os.pipe()
            os.write(writer, json.dumps({"descendants_started": 3 if case == "fork-exit" else 1}).encode() + b"\n")
            os.close(writer)
            process.stdout = os.fdopen(reader, "rb")
            return process
        actual_write = os.write
        def write(descriptor, data):
            if data == b"1":
                events.append("release")
            return actual_write(descriptor, data)
        with patch.object(H.subprocess, "Popen", side_effect=start), patch.object(H.os, "write", side_effect=write):
            if reject_attachment:
                with self.assertRaises(H.Unavailable):
                    H.supervise(scope, "/fixed-public-plan", 2001, 2001, timeout=2, case=case)
                result = None
            else:
                result = H.supervise(scope, "/fixed-public-plan", 2001, 2001, timeout=2, case=case)
        return events, result

    def test_fake_kernel_control_orders_attachment_before_release_and_cleanup(self):
        events, result = self.run_fixture()
        self.assertLess(events.index("attach"), events.index("release"))
        self.assertLess(events.index("release"), events.index("kernel-kill-empty"))
        self.assertEqual(result["cleanup"]["kernel_populated"], 0)
        self.assertEqual(result["observation"], {"descendants_started": 1})

    def test_failed_attachment_never_releases_candidate(self):
        events, _ = self.run_fixture(reject_attachment=True)
        self.assertNotIn("release", events)
        self.assertIn("kernel-kill-empty", events)

    def test_detached_members_are_observed_after_initial_wait_and_before_kill(self):
        for case, count in (("daemon", 1), ("fork-exit", 3)):
            events, result = self.run_fixture(case=case, members=set(range(1000001, 1000001 + count)))
            self.assertLess(events.index("initial-command-reaped"), events.index("kernel-populated"))
            self.assertLess(events.index("kernel-populated"), events.index("kernel-members"))
            self.assertLess(events.index("kernel-members"), events.index("kernel-kill-empty"))
            self.assertEqual(result["live_before_cleanup"], 1)
            self.assertEqual(result["trusted_cleanup_canaries"], {"initial_command_reaped": True, "kernel_populated": 1,
                "kernel_member_count": count, "minimum_canaries": count})
            H.validate_case(case, result, outside())

    def test_exited_empty_or_unreaped_initial_process_cannot_claim_detached_kill_coverage(self):
        for case in ("daemon", "fork-exit"):
            for live, members in ((0, {1000001, 1000002, 1000003}), (1, set()), (1, {999999})):
                events = []
                with self.subTest(case=case, live=live, members=members), self.assertRaisesRegex(H.Unavailable, "survived the initial command"):
                    self.run_fixture(case=case, live=live, members=members, events=events)
                self.assertIn("kernel-kill-empty", events)


class ProtectedRuntimeTests(unittest.TestCase):
    def result(self):
        binding = {"source": "a" * 40, "run_id": 12, "run_attempt": 1,
                   "snapshot": "sha256:" + "b" * 64, "projection": "sha256:" + "c" * 64}
        value = {"exit_code": 0, "reason": None, "cleanup": {"kernel_populated": 0, "subtree_kill": True},
            "observation": {"schema": 1, "authority": "none", "measurement": "protected-boundary-profile", "reusable": False,
                "runtime_compatibility": "unqualified", "identity": {"binding": binding, "environment": sandbox._ENVIRONMENT,
                    "prefix": "/opt/overte-ci/venv", "files": {str(n): "a" * 64 for n in range(8)}},
                "process": {"status": {"NoNewPrivs": "1", "Uid": "2001 2001 2001 2001", "Gid": "2001 2001 2001 2001",
                    **dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000")}}}}
        return value, binding

    def test_runtime_binding_rejects_wrong_source_attempt_snapshot_profile_and_privilege(self):
        value, binding = self.result()
        baseline = H.validate_runtime(value, binding, sandbox._ENVIRONMENT, 2001, 2001)
        for key, replacement in (("source", "d" * 40), ("run_id", 13), ("run_attempt", 2),
                                 ("snapshot", "sha256:" + "e" * 64), ("projection", "sha256:" + "f" * 64)):
            altered = deepcopy(value)
            altered["observation"]["identity"]["binding"][key] = replacement
            with self.subTest(key=key), self.assertRaises(H.Unavailable):
                H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)
        for key, replacement in (("Uid", "0 0 0 0"), ("Gid", "0 0 0 0"), ("NoNewPrivs", "0"), ("CapEff", "0000000000000001")):
            altered = deepcopy(value)
            altered["observation"]["process"]["status"][key] = replacement
            with self.subTest(key=key), self.assertRaises(H.Unavailable):
                H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)
        changed = deepcopy(value)
        changed["observation"]["identity"]["files"]["0"] = "f" * 64
        self.assertNotEqual(H.validate_runtime(changed, binding, sandbox._ENVIRONMENT, 2001, 2001), baseline)
        for key, replacement in (("reusable", True), ("runtime_compatibility", "qualified")):
            altered = deepcopy(value)
            altered["observation"][key] = replacement
            with self.subTest(key=key), self.assertRaises(H.Unavailable):
                H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)

    def test_runtime_probe_cannot_start_while_any_authenticated_scope_is_live(self):
        value, binding = self.result()
        for live in (1, None):
            scope = SimpleNamespace(populated=lambda: live)
            calls = []
            with self.subTest(live=live), self.assertRaises(H.Unavailable):
                H.runtime_probe({"earlier-work": scope}, lambda args: calls.append(args), binding, sandbox._ENVIRONMENT, 2001, 2001)
            self.assertEqual(calls, [])
        captured = []
        result = H.runtime_probe({"earlier-work": SimpleNamespace(populated=lambda: 0)},
            lambda args: captured.append(args) or value, binding, sandbox._ENVIRONMENT, 2001, 2001)
        self.assertTrue(result.startswith("sha256:"))
        self.assertEqual(captured[0][-2:], ["/overte-policy/tools/test-evidence/sandbox_probe.py", "--boundary-diagnostic"])

    def test_failed_timeout_missing_probe_or_incomplete_cleanup_is_rejected(self):
        original, binding = self.result()
        for key, replacement in (("exit_code", 1), ("reason", "timeout"), ("observation", None),
                                 ("cleanup", {"kernel_populated": 1, "subtree_kill": True})):
            with self.subTest(key=key), self.assertRaises(H.Unavailable):
                H.validate_runtime({**original, key: replacement}, binding, sandbox._ENVIRONMENT, 2001, 2001)
        altered = deepcopy(original)
        altered["observation"]["identity"]["environment"]["GH_TOKEN"] = "public-unit-fixture"
        with self.assertRaises(H.Unavailable):
            H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)

    def test_verified_source_then_guardian_then_execution_then_cleanup_then_postverification(self):
        events = []
        source = SimpleNamespace(verify_snapshot=lambda *_: events.append("snapshot"),
            verify_projection=lambda *_: events.append("projection"), build_plan=lambda *_: {"argv": ["/usr/bin/bwrap"]})
        layout = SimpleNamespace(candidate=Path("/candidate"), policy_source=Path("/policy"), protected=Path("/protected"))
        guardian = SimpleNamespace(finish=lambda: events.append("guardian-empty"), close=lambda: events.append("close"))
        with tempfile.TemporaryDirectory() as temporary:
            with (patch.object(H.os, "geteuid", return_value=0),
                  patch.object(H, "Guardian", side_effect=lambda *_: events.append("guardian-ready") or guardian),
                  patch.object(H, "supervise", side_effect=lambda *_a, **_k: events.append("work") or {"fixture": True})):
                result = H.protected_launch(source, layout, {}, {}, object(), {}, Path(temporary) / "plan", [], 2001, 2001, case="probe")
        self.assertEqual(result, {"fixture": True})
        self.assertEqual(events, ["snapshot", "projection", "guardian-ready", "work", "guardian-empty", "snapshot", "projection", "close"])

    def test_failed_guardian_prevents_postverification_and_always_cleans(self):
        events = []
        source = SimpleNamespace(verify_snapshot=lambda *_: events.append("snapshot"),
            verify_projection=lambda *_: events.append("projection"), build_plan=lambda *_: {"argv": ["/usr/bin/bwrap"]})
        layout = SimpleNamespace(candidate=Path("/candidate"), policy_source=Path("/policy"), protected=Path("/protected"))
        def failed():
            raise H.Unavailable("guardian missing")
        guardian = SimpleNamespace(finish=failed, close=lambda: events.append("close"))
        with tempfile.TemporaryDirectory() as temporary:
            with (patch.object(H.os, "geteuid", return_value=0), patch.object(H, "Guardian", return_value=guardian),
                  patch.object(H, "supervise", return_value={}), self.assertRaises(H.Unavailable)):
                H.protected_launch(source, layout, {}, {}, object(), {}, Path(temporary) / "plan", [], 2001, 2001, case="probe")
        self.assertEqual(events, ["snapshot", "projection", "close"])


class ImmutableQualificationSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-fixed-qualification-source-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        names = {*sandbox.contract()["sources"], "tools/test-evidence/sandbox_host.py",
                 "tools/test-evidence/sandbox_host_fixture.py", "tools/test-evidence/workflows/shared-sandbox-host-diagnostic.yml",
                 ".github/workflows/shared-sandbox-host-diagnostic.yml"}
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(H.ROOT / name, path)
        self.git("init", "-q", "--initial-branch=main")
        self.git("add", ".")
        self.git("commit", "-qm", "Record immutable qualification controls")
        self.revision = self.git("rev-parse", "HEAD").strip().decode()

    def git(self, *arguments):
        result = H.command(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
            "-c", "user.name=Source fixture", "-c", "user.email=fixture@example.invalid", *arguments], cwd=self.root)
        result.check_returncode()
        return result.stdout

    def test_actual_manual_sparse_checkout_materializes_every_verified_control(self):
        workflow = (self.root / ".github/workflows/shared-sandbox-host-diagnostic.yml").read_text()
        block = workflow.split("          sparse-checkout: |\n", 1)[1].split("      - name:", 1)[0]
        patterns = [line.strip() for line in block.splitlines() if line.strip()]
        unrelated = self.root / ".github/unrelated.json"
        unrelated.write_text("{}\n")
        self.git("add", "--all")
        self.git("commit", "-qm", "Add unrelated sparse checkout control")
        revision = self.git("rev-parse", "HEAD").strip().decode()
        self.git("sparse-checkout", "set", "--no-cone", *patterns)
        self.assertFalse(unrelated.exists())
        H.verify_qualification_source(sandbox, revision, root=self.root)

    def test_actual_source_read_works_with_shallow_metadata_and_ignores_candidate_configuration(self):
        (self.root / ".git/shallow").write_text(self.revision + "\n")
        (self.root / ".git/config").write_text("malformed ignored configuration\n")
        H.verify_qualification_source(sandbox, self.revision, root=self.root)

    def test_dirty_loaded_control_missing_source_or_alias_cannot_pass_source_binding(self):
        path = self.root / "tools/test-evidence/sandbox_host.py"
        original = path.read_bytes()
        path.write_bytes(original + b"\n# unexpected loaded control\n")
        with self.assertRaises(H.Unavailable):
            H.verify_qualification_source(sandbox, self.revision, root=self.root)
        path.unlink()
        path.symlink_to(H.ROOT / "tools/test-evidence/sandbox_host.py")
        with self.assertRaises(sandbox.SandboxUnavailable):
            H.verify_qualification_source(sandbox, self.revision, root=self.root)
        path.unlink()
        self.git("add", "--all")
        self.git("commit", "-qm", "Remove fixed source")
        revision = self.git("rev-parse", "HEAD").strip().decode()
        with self.assertRaises(H.Unavailable):
            H.verify_qualification_source(sandbox, revision, root=self.root)

    def test_executable_control_mode_is_not_the_reviewed_ordinary_source(self):
        (self.root / "tools/test-evidence/sandbox_host.py").chmod(0o755)
        self.git("add", "--all")
        self.git("commit", "-qm", "Change fixed source mode")
        revision = self.git("rev-parse", "HEAD").strip().decode()
        with self.assertRaises(H.Unavailable):
            H.verify_qualification_source(sandbox, revision, root=self.root)

    def test_fixed_hosted_snapshot_and_isolated_probe_import_are_real_source_operations(self):
        candidate, projection = self.root / "candidate", self.root / "projection"
        candidate.mkdir(mode=0o755)
        projection.mkdir(mode=0o755)
        snapshot, inventory = H.diagnostic_snapshot(sandbox, self.root / "original", candidate, projection)
        sandbox.verify_snapshot(candidate, snapshot)
        sandbox.verify_projection(projection, inventory)
        self.assertTrue((candidate / "build").is_dir())
        self.assertEqual(list((candidate / "build").iterdir()), [])
        # Import the actual projected bytes under -I without invoking a probe.
        # The runtime ROOT must remain the finite projection, not '/' or the
        # candidate checkout. No privileged operation or environment capture.
        imported = H.command(["/usr/bin/python3", "-I", "-B", "-c",
            "import runpy,sys;v=runpy.run_path(sys.argv[1],run_name='offline_import');print(v['runtime'].ROOT)",
            str(projection / "tools/test-evidence/sandbox_probe.py")])
        self.assertEqual(imported.returncode, 0)
        self.assertEqual(imported.stdout.strip().decode(), str(projection))
        sandbox.verify_projection(projection, inventory)


class GuardianTests(unittest.TestCase):
    def test_failed_guardian_fork_closes_controls_and_kills_without_releasing_work(self):
        protected = SimpleNamespace(lstat=lambda: SimpleNamespace(st_mode=0o40700, st_uid=0), is_absolute=lambda: True)
        class Directory:
            def lstat(self):
                return protected.lstat()
            def is_absolute(self):
                return True
            def resolve(self, **_kwargs):
                return self
            def __truediv__(self, _name):
                return Path("/never-opened-unit-fixture")
        scope = SimpleNamespace(directory=7, kill_and_wait=lambda: events.append("kernel-kill"))
        events = []
        with (patch.object(H.os, "geteuid", return_value=0), patch.object(H.os, "fstat", return_value=SimpleNamespace(st_dev=9, st_ino=10)),
              patch.object(H.os, "open", return_value=11), patch.object(H.os, "pipe2", side_effect=[(12, 13), (14, 15)]),
              patch.object(H.os, "fork", side_effect=OSError("unit fixture unavailable")),
              patch.object(H.os, "close", side_effect=lambda fd: events.append(fd)), self.assertRaises(H.Unavailable)):
            H.Guardian(scope, Directory(), {})
        self.assertEqual(events, [11, 12, 13, 14, 15, "kernel-kill"])

    def test_pipe_eof_release_and_deadline_always_kill_before_protected_report(self):
        for payload, expected in ((b"", "controller-eof"), (b"done", "released"), (b"forged", "deadline"), (None, "deadline")):
            events = []
            scope = SimpleNamespace(directory=77, kill_and_wait=lambda: events.append("kernel-kill-empty") or {"kernel_populated": 0, "subtree_kill": True})
            def write(_fd, data):
                events.append("protected-report")
                value = json.loads(data)
                self.assertEqual(value["trigger"], expected)
                self.assertEqual(value["scope"], [9, 10])
                self.assertEqual(value["binding"], {"attempt": 1})
            with (patch.object(H.select, "select", return_value=([11], [], []) if payload is not None else ([], [], [])),
                  patch.object(H.os, "read", return_value=payload), patch.object(H.os, "write", side_effect=write),
                  patch.object(H.os, "fstat", return_value=SimpleNamespace(st_dev=9, st_ino=10))):
                H._guardian_loop(scope, 11, 12, {"attempt": 1})
            self.assertEqual(events, ["kernel-kill-empty", "protected-report"])

    def test_kernel_kill_failure_cannot_write_a_successful_guardian_report(self):
        scope = SimpleNamespace(kill_and_wait=lambda: (_ for _ in ()).throw(H.Unavailable("still populated")))
        with (patch.object(H.select, "select", return_value=([11], [], [])), patch.object(H.os, "read", return_value=b""),
              patch.object(H.os, "write") as write, self.assertRaises(H.Unavailable)):
            H._guardian_loop(scope, 11, 12, {})
        write.assert_not_called()

    def guardian(self, *, trigger="released", live=0, owner=0, mode=0o100600):
        value = {"trigger": trigger, "cleanup": {"kernel_populated": 0, "subtree_kill": True}, "scope": [9, 10], "binding": {"attempt": 1}}
        guardian = object.__new__(H.Guardian)
        guardian.writer, guardian.pid, guardian.identity, guardian.binding = None, 123, [9, 10], {"attempt": 1}
        guardian.scope = SimpleNamespace(populated=lambda: live)
        guardian.path = SimpleNamespace(lstat=lambda: SimpleNamespace(st_uid=owner, st_mode=mode, st_size=1000, st_nlink=1),
                                       read_bytes=lambda: json.dumps(value).encode())
        return guardian

    def test_missing_wrong_scope_mutable_or_foreign_proof_cannot_be_accepted(self):
        with patch.object(H, "_wait_child", return_value=0):
            self.assertEqual(self.guardian().finish()["scope"], [9, 10])
            for kwargs in ({"trigger": "deadline"}, {"live": 1}, {"owner": 2001}, {"mode": 0o100666}):
                with self.subTest(kwargs=kwargs), self.assertRaises(H.Unavailable):
                    self.guardian(**kwargs).finish()
            for key, replacement in (("identity", [9, 11]), ("binding", {"attempt": 2})):
                guardian = self.guardian()
                setattr(guardian, key, replacement)
                with self.subTest(key=key), self.assertRaises(H.Unavailable):
                    guardian.finish()
        with patch.object(H, "_wait_child", return_value=1), self.assertRaises(H.Unavailable):
            self.guardian().finish()

    def test_actual_controller_sigkill_and_live_scope_are_required_for_eof_proof(self):
        for live, status in ((1, H.signal.SIGKILL), (0, H.signal.SIGKILL), (1, 0)):
            events = []
            scope = SimpleNamespace(populated=lambda: live, members=lambda: {44})
            guardian = SimpleNamespace(relinquish_writer=lambda: events.append("sole-writer-in-worker"),
                finish=lambda reason: events.append(reason) or {"trigger": reason}, close=lambda: events.append("close"))
            with (patch.object(H.os, "pipe2", return_value=(11, 12)), patch.object(H.os, "fork", return_value=456),
                  patch.object(H.os, "close"), patch.object(H.select, "select", return_value=([11], [], [])),
                  patch.object(H.os, "read", return_value=b"1"), patch.object(H.os, "kill", side_effect=lambda *_: events.append("sigkill")),
                  patch.object(H, "_wait_child", return_value=status)):
                if live == 1 and status == H.signal.SIGKILL:
                    result = H.controller_death(scope, guardian, Path("/fixed-plan"), 2001, 2001)
                    self.assertTrue(result["controller_sigkill_observed"])
                    self.assertEqual(events, ["sole-writer-in-worker", "sigkill", "controller-eof", "close"])
                else:
                    with self.assertRaises(H.Unavailable):
                        H.controller_death(scope, guardian, Path("/fixed-plan"), 2001, 2001)
                    self.assertNotIn("controller-eof", events)
                    self.assertEqual(events[-1], "close")


class FixedResultTests(unittest.TestCase):
    def test_manual_workflow_matches_template_without_pr_trigger_or_success_skip(self):
        template = (H.ROOT / "tools/test-evidence/workflows/shared-sandbox-host-diagnostic.yml").read_text()
        self.assertIn("workflow_dispatch: null", template)
        self.assertNotIn("pull_request:", template)
        self.assertNotIn("workflow_call:", template)
        self.assertIn("--property=Delegate=yes", template)
        for property in ("KillMode=control-group", "TimeoutStopSec=10s", "SendSIGKILL=yes", "RuntimeMaxSec=120s"):
            self.assertIn("--property=" + property, template)
        self.assertIn('test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"', template)
        self.assertIn('GITHUB_WORKFLOW_SHA="$GITHUB_WORKFLOW_SHA"', template)
        self.assertIn("--wait --pipe --collect --quiet --service-type=exec", template)
        self.assertIn("Reject unsupported source context", template)
        self.assertIn("QUALIFY_GITHUB_ENV=", template)
        self.assertNotIn("continue-on-error", template)
        self.assertEqual((H.ROOT / ".github/workflows/shared-sandbox-host-diagnostic.yml").read_text(), template)
    def test_parser_fixture_pass_is_not_production_qualification(self):
        H.validate_case("protections", protection_result(), outside())
        with self.assertRaises(sandbox.SandboxUnavailable):
            sandbox.execute(protection_result(), qualified=True)
        with self.assertRaises(sandbox.SandboxUnavailable):
            sandbox.capture_after_execution({"kernel_populated": 0}, qualified=True)

    def test_success_exit_does_not_hide_mount_network_credentials_or_namespace_failure(self):
        for flag in ("git_readonly", "command_files_hidden", "path_socket_hidden", "protected_descriptors_absent", "loopback", "venv_aliases", "readonly_mount_flags"):
            failed = protection_result()
            failed["observation"][flag] = False
            with self.subTest(flag=flag), self.assertRaises(H.Unavailable):
                H.validate_case("protections", failed, outside())
        failed = protection_result()
        failed["observation"]["process"]["NoNewPrivs"] = "0"
        with self.assertRaises(H.Unavailable):
            H.validate_case("protections", failed, outside())
        failed = protection_result()
        failed["observation"]["namespaces"]["pid"] = outside()["pid"]
        with self.assertRaises(H.Unavailable):
            H.validate_case("protections", failed, outside())

    def test_daemon_exit_or_forged_scope_claim_does_not_replace_kernel_cleanup(self):
        for cleanup in ({}, {"kernel_populated": 1, "subtree_kill": True}, {"descendants_empty": True}):
            value = {"exit_code": 0, "reason": None, "cleanup": cleanup, "observation": {"descendants_started": 1}}
            with self.subTest(cleanup=cleanup), self.assertRaises(H.Unavailable):
                H.validate_case("daemon", value, outside())

    def test_missing_or_empty_kernel_survivor_observation_cannot_pass_detached_cases(self):
        for case, count in (("daemon", 1), ("fork-exit", 3)):
            valid = {"exit_code": 0, "reason": None, "live_before_cleanup": 1,
                "cleanup": {"kernel_populated": 0, "subtree_kill": True}, "observation": {"descendants_started": count},
                "trusted_cleanup_canaries": {"initial_command_reaped": True, "kernel_populated": 1,
                                      "kernel_member_count": count, "minimum_canaries": count}}
            H.validate_case(case, valid, outside())
            for key, value in (("live_before_cleanup", None), ("live_before_cleanup", 0), ("trusted_cleanup_canaries", None)):
                altered = {**valid, key: value}
                with self.subTest(case=case, key=key, value=value), self.assertRaises(H.Unavailable):
                    H.validate_case(case, altered, outside())
            for key in ("live_before_cleanup", "trusted_cleanup_canaries"):
                altered = {name: value for name, value in valid.items() if name != key}
                with self.subTest(case=case, missing=key), self.assertRaises(H.Unavailable):
                    H.validate_case(case, altered, outside())
            for key, value in (("initial_command_reaped", False), ("kernel_populated", 0), ("kernel_member_count", 0)):
                altered = {**valid, "trusted_cleanup_canaries": {**valid["trusted_cleanup_canaries"], key: value}}
                with self.subTest(case=case, key=key), self.assertRaises(H.Unavailable):
                    H.validate_case(case, altered, outside())

    def test_timeout_requires_actual_contained_work_before_kernel_kill(self):
        value = {"exit_code": -9, "reason": "timeout", "live_before_cleanup": 1,
                 "cleanup": {"kernel_populated": 0, "subtree_kill": True}, "observation": {"descendants_started": 1}}
        H.validate_case("timeout", value, outside())
        for field, replacement in (("observation", None), ("live_before_cleanup", 0), ("exit_code", 0), ("reason", None)):
            with self.subTest(field=field), self.assertRaises(H.Unavailable):
                H.validate_case("timeout", {**value, field: replacement}, outside())

    def test_unsupported_host_is_failure_not_a_skipped_success(self):
        with patch.object(H, "run_host", side_effect=H.Unavailable("kernel scope cannot be authenticated")), patch.object(H.sys, "stdout", new_callable=io.StringIO) as output:
            self.assertEqual(H.main([]), 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
