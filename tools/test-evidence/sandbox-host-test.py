#!/usr/bin/env python3
"""Host diagnostic parsers/control fixtures; no local privileged host probes."""

from copy import deepcopy
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import sandbox
import sandbox_host as H
import sandbox_host_fixture as FIXTURE
import sandbox_shared as SHARED


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

    def test_generic_failure_categories_expose_no_message_path_command_or_output(self):
        secret='PRIVATE-fixture-secret-::error::-command-env-output'
        cases=[(FileNotFoundError(2,secret,'/private/'+secret),'FileNotFoundError',2),
            (PermissionError(13,secret,'/private/'+secret),'PermissionError',13),
            (OSError(999999,secret),'OSError',None),(ValueError(secret),'ValueError',None),
            (KeyError(secret),'KeyError',None),
            (subprocess.CalledProcessError(1,[secret],output=secret,stderr=secret),'CalledProcessError',None),
            (subprocess.TimeoutExpired([secret],5,output=secret,stderr=secret),'TimeoutExpired',None)]
        for error,kind,number in cases:
            with self.subTest(kind=kind),patch.object(H,'run_host',side_effect=error), \
                    patch.object(H.sys,'stdout',new_callable=io.StringIO) as output:
                self.assertEqual(H.main([]),1)
            raw=output.getvalue();report=json.loads(raw)
            self.assertEqual(report['status'],'unavailable')
            self.assertEqual(report['authority'],'none');self.assertIs(report['production_qualified'],False)
            self.assertEqual(report['error'],'required host diagnostic operation failed')
            item=report['failure']['chain'][0]
            self.assertEqual((item['exception_class'],item['errno']),(kind,number))
            self.assertEqual(item['source'],'tools/test-evidence/sandbox_host.py')
            self.assertEqual(item['stage'],'profile-entry')
            self.assertNotIn(secret,raw);self.assertNotIn('/private/',raw)
            self.assertLess(len(raw),5000)

    def test_failure_chain_and_public_input_hints_are_closed_and_bounded(self):
        class SecretSubclassOfValueError(ValueError):pass
        error=SecretSubclassOfValueError('private data')
        for _ in range(6):
            outer=KeyError('private data');outer.__context__=error;error=outer
        summary=H.failure_summary(error)
        self.assertEqual(len(summary['chain']),4);self.assertTrue(summary['chain_truncated'])
        self.assertNotIn('private',json.dumps(summary));self.assertNotIn('SecretSubclass',json.dumps(summary))
        self.assertEqual(H.failure_summary(SecretSubclassOfValueError())['chain'][0]['exception_class'],'ValueError')
        for filename,label in (('/usr/lib/jvm/private-leaf','system-jvm'),
                ('/opt/overte-ci/venv/private-leaf','prepared-venv'),('/private/unknown',None),
                ('/usr/lib/jvm-shadow/private',None),('/opt/hostedtoolcache/Python/3.12.15/x64/private','prepared-python')):
            item=H.failure_summary(FileNotFoundError(2,'private message',filename))['chain'][0]
            self.assertEqual(item.get('input_root'),label)
            self.assertNotIn('private',json.dumps(item))

    def test_script_entrypoint_and_shared_import_have_one_unavailable_class(self):
        # Exercise the real script entrypoint, but substitute its complete
        # shared workload with a fixed refusal. No host operation can start.
        source=H.ROOT/'tools/test-evidence/sandbox_host.py'
        script=('import runpy,sys,types\n'
            'shared=types.ModuleType("sandbox_shared")\n'
            'def refused():\n'
            ' import sandbox_host\n'
            ' raise sandbox_host.Unavailable("fixed public fixture refusal")\n'
            'shared.run_host=refused\n'
            'sys.modules["sandbox_shared"]=shared\n'
            'sys.argv=['+repr(str(source))+',"--profile","shared-host"]\n'
            'runpy.run_path('+repr(str(source))+',run_name="__main__")\n')
        result=subprocess.run([sys.executable,'-I','-c',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1)
        report=json.loads(result.stdout)
        self.assertEqual(report['error'],'fixed public fixture refusal')
        self.assertEqual(report['failure']['chain'][0]['exception_class'],'Unavailable')
        self.assertEqual(report['status'],'unavailable');self.assertFalse(report['production_qualified'])

    def test_foreign_loaded_controller_is_not_replaced_or_executed(self):
        foreign=SimpleNamespace(private='untrusted module fixture')
        with patch.dict(sys.modules,{'sandbox_host':foreign}), \
                patch.object(SHARED,'run_host',side_effect=AssertionError('foreign controller reached workload')), \
                patch.object(H.sys,'stdout',new_callable=io.StringIO) as output:
            self.assertEqual(H.main(['--profile','shared-host']),1)
            self.assertIs(sys.modules['sandbox_host'],foreign)
        report=json.loads(output.getvalue())
        self.assertEqual(report['status'],'unavailable');self.assertFalse(report['production_qualified'])
        self.assertEqual(report['failure']['chain'][0]['stage'],'trusted-module-identity')
        self.assertNotIn('untrusted module fixture',output.getvalue())

    def test_actual_prepared_alias_failure_has_public_source_stage_without_secret_path(self):
        original=Path.lstat
        def trusted_stat(path,*args,**kwargs):
            value=original(path,*args,**kwargs)
            return SimpleNamespace(st_mode=value.st_mode,st_uid=0,st_size=value.st_size)
        with tempfile.TemporaryDirectory(prefix='private-fixture-') as temporary:
            root=Path(temporary);(root/'private-link').symlink_to(root/'private-missing')
            with (patch.object(SHARED,'VENV',root),patch.object(Path,'lstat',trusted_stat),
                  patch.object(SHARED,'run_host',side_effect=lambda:SHARED.prepared_identity(())),
                  patch.object(H.sys,'stdout',new_callable=io.StringIO) as output):
                self.assertEqual(H.main(['--profile','shared-host']),1)
            raw=output.getvalue();item=json.loads(raw)['failure']['chain'][0]
            self.assertEqual(item['exception_class'],'FileNotFoundError')
            self.assertEqual(item['errno'],2)
            self.assertEqual(item['stage'],'prepared-input-identity')
            self.assertEqual(item['source'],'tools/test-evidence/sandbox_shared.py')
            self.assertGreater(item['line'],0)
            self.assertNotIn('private-',raw);self.assertNotIn(temporary,raw)

    def test_fixed_account_requires_actual_distinct_uid_and_no_sudo_grants(self):
        account = SimpleNamespace(pw_uid=2001, pw_gid=2001, pw_shell="/usr/sbin/nologin")
        denied = SimpleNamespace(returncode=1, stdout=b"User overte-ci-qualification is not allowed to run sudo on host.\n", stderr=b"")
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


class PublicBootstrapTests(unittest.TestCase):
    """Real ordinary files; root ownership is modeled, never provisioned locally."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-private-bootstrap-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.private = Path(self.temporary.name)
        self.source = self.private / "sandbox_host.py"
        self.body = Path(H.__file__).read_bytes()
        self.source.write_bytes(self.body)
        self.source.chmod(0o600)
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)
        actual_lstat, actual_fstat = Path.lstat, os.fstat
        public_tmp = actual_lstat(Path("/tmp"))

        def root_owned(info):
            # Model only the fixed public parent, even when the test itself
            # runs inside a candidate capsule whose private /tmp is 0755.
            mode = (stat.S_IFMT(info.st_mode) | 0o1777
                    if (info.st_dev, info.st_ino) == (public_tmp.st_dev, public_tmp.st_ino)
                    else info.st_mode)
            return os.stat_result((mode, *info[1:4], 0, *info[5:]))

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(H, "__file__", str(self.source)))
        self.stack.enter_context(patch.object(H, "_BOOTSTRAP_DIRECTORY", None))
        self.stack.enter_context(patch.object(H.os, "geteuid", return_value=0))
        self.stack.enter_context(patch.object(H.Path, "lstat", lambda path, *a, **k: root_owned(actual_lstat(path, *a, **k))))
        self.stack.enter_context(patch.object(H.os, "fstat", side_effect=lambda fd: root_owned(actual_fstat(fd))))
        self.addCleanup(lambda: H._BOOTSTRAP_DIRECTORY.cleanup() if H._BOOTSTRAP_DIRECTORY is not None else None)

    def test_exact_readonly_copy_is_outside_private_checkout_and_reused_once(self):
        temporary = tempfile.TemporaryDirectory
        with patch.object(H.tempfile, "TemporaryDirectory", wraps=temporary) as create:
            first, second = H.public_bootstrap(), H.public_bootstrap()
        self.assertEqual(first, second)
        self.assertEqual(first.read_bytes(), self.body)
        self.assertEqual(first.stat().st_mode & 0o777, 0o444)
        self.assertEqual(first.parent.stat().st_mode & 0o777, 0o755)
        self.assertEqual(first.parent.parent, Path("/tmp"))
        self.assertFalse(first.is_relative_to(self.private))
        create.assert_called_once_with(prefix="overte-sandbox-bootstrap-", dir="/tmp")

    def test_unprivileged_copied_bootstrap_reaches_closed_gate_without_original_path(self):
        if os.getuid() == 0:
            self.skipTest("the ordinary-process fixture must not run as root")
        copied = H.public_bootstrap()
        # The private source models a runner-only checkout; removing that exact
        # path proves the child imports no source/neighbor from that checkout.
        self.source.rename(self.private / "unavailable-original.py")
        reader, writer = os.pipe()
        os.close(writer)
        try:
            result = H.subprocess.run(["/usr/bin/python3", "-I", str(copied), "--bootstrap", str(reader),
                                       "/never-read-plan", "protections"], pass_fds=(reader,),
                                      stdin=H.subprocess.DEVNULL, stdout=H.subprocess.PIPE, stderr=H.subprocess.PIPE,
                                      env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, timeout=5)
        finally:
            os.close(reader)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"parent did not release the attached bootstrap", result.stderr)
        self.assertNotIn(b"can't open file", result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_nonroot_provisioning_cannot_create_a_copy(self):
        with patch.object(H.os, "geteuid", return_value=2001), patch.object(H.tempfile, "TemporaryDirectory") as create:
            with self.assertRaisesRegex(H.Unavailable, "actual trusted root"):
                H.public_bootstrap()
        create.assert_not_called()

    def test_untrusted_or_nontraversable_storage_is_rejected(self):
        actual_lstat = Path.lstat
        for path, mode, owner in (("/", 0o777, 0), ("/tmp", 0o755, 0), ("/tmp", 0o1777, 2001)):
            def changed(candidate, *args, **kwargs):
                info = actual_lstat(candidate, *args, **kwargs)
                return os.stat_result((0o040000 | mode, *info[1:4], owner, *info[5:])) if str(candidate) == path else info
            with (self.subTest(path=path, mode=mode, owner=owner), patch.object(H.Path, "lstat", changed),
                  patch.object(H.tempfile, "TemporaryDirectory") as create, self.assertRaises(H.Unavailable)):
                H.public_bootstrap()
            create.assert_not_called()
        copied = H.public_bootstrap()
        def foreign_base(path, *args, **kwargs):
            info = actual_lstat(path, *args, **kwargs)
            return os.stat_result((*info[:4], 2001, *info[5:])) if path == copied.parent else info
        with patch.object(H.Path, "lstat", foreign_base), self.assertRaises(H.Unavailable):
            H.public_bootstrap()

    def test_copy_bytes_and_original_source_changes_are_both_rejected(self):
        for alter_original in (False, True):
            with self.subTest(original=alter_original):
                copied = H.public_bootstrap()
                target = self.source if alter_original else copied
                target.chmod(0o600)
                target.write_bytes(self.body[:-1] + b"!")
                target.chmod(0o600 if alter_original else 0o444)
                with self.assertRaisesRegex(H.Unavailable, "differs from the verified controller"):
                    H.public_bootstrap()
                target.chmod(0o600)
                target.write_bytes(self.body)
                target.chmod(0o600 if alter_original else 0o444)

    def test_writable_copy_directory_and_hardlinked_copy_are_rejected(self):
        copied = H.public_bootstrap()
        for target, mode in ((copied, 0o644), (copied.parent, 0o777)):
            with self.subTest(target=target):
                original = target.stat().st_mode & 0o777
                target.chmod(mode)
                with self.assertRaises(H.Unavailable):
                    H.public_bootstrap()
                target.chmod(original)
        alias = copied.parent / "hardlink.py"
        os.link(copied, alias)
        with self.assertRaisesRegex(H.Unavailable, "unsafe metadata"):
            H.public_bootstrap()

    def test_nonroot_copy_owner_is_rejected(self):
        H.public_bootstrap()
        actual_fstat = os.fstat
        with patch.object(H.os, "fstat", side_effect=lambda fd: os.stat_result((*actual_fstat(fd)[:4], 2001, *actual_fstat(fd)[5:]))):
            with self.assertRaisesRegex(H.Unavailable, "unsafe metadata"):
                H.public_bootstrap()

    def test_symlinked_copy_never_reads_or_overwrites_its_target(self):
        copied = H.public_bootstrap()
        copied.unlink()
        copied.symlink_to(self.source)
        with self.assertRaises(OSError):
            H.public_bootstrap()
        self.assertEqual(self.source.read_bytes(), self.body)

    def test_exclusive_creation_rejects_preexisting_alias(self):
        actual_open = os.open
        def conflict(path, flags, *args, **kwargs):
            if flags & os.O_EXCL:
                Path(path).symlink_to(self.source)
            return actual_open(path, flags, *args, **kwargs)
        with patch.object(H.os, "open", side_effect=conflict), self.assertRaises(FileExistsError):
            H.public_bootstrap()
        self.assertIsNone(H._BOOTSTRAP_DIRECTORY)
        self.assertEqual(self.source.read_bytes(), self.body)

    def test_oversized_original_is_rejected_before_copy(self):
        self.source.write_bytes(b"x" * 1_000_001)
        with patch.object(H.tempfile, "TemporaryDirectory") as create, self.assertRaisesRegex(H.Unavailable, "bounded ordinary file"):
            H.public_bootstrap()
        create.assert_not_called()

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
            self.assertEqual(_argv[:4], ["/usr/bin/python3", "-I", "/fixed-public-bootstrap.py", "--bootstrap"])
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
        with (patch.object(H, "public_bootstrap", return_value=Path("/fixed-public-bootstrap.py")),
              patch.object(H.subprocess, "Popen", side_effect=start), patch.object(H.os, "write", side_effect=write)):
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

    def test_every_fixed_case_uses_same_public_bootstrap_and_retains_attachment_gate(self):
        for case in H._BOOTSTRAP_CASES:
            with self.subTest(case=case):
                events, result = self.run_fixture(case=case)
                self.assertLess(events.index("attach"), events.index("release"))
                self.assertLess(events.index("release"), events.index("kernel-kill-empty"))
                self.assertEqual(result["cleanup"], {"kernel_populated": 0, "subtree_kill": True})

    def test_actual_supervisor_suite_mode_never_parses_candidate_stdout_as_proof(self):
        with patch.object(H.json, "loads", side_effect=AssertionError("candidate JSON must not be interpreted")):
            events, result = self.run_fixture(case="suite")
        self.assertIsNone(result["observation"])
        self.assertIn(b"descendants_started", result["diagnostic"])
        self.assertEqual(result["cleanup"], {"kernel_populated": 0, "subtree_kill": True})

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
            with self.subTest(key=key), self.assertRaises(H.Unavailable) as caught:
                H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)
            details = json.loads(str(caught.exception).split(": ", 1)[1])
            self.assertEqual(details["failed"], ["binding"])
            self.assertEqual(details["binding_fields"], [key])
        for key, replacement in (("Uid", "0 0 0 0"), ("Gid", "0 0 0 0"), ("NoNewPrivs", "0"), ("CapEff", "0000000000000001")):
            altered = deepcopy(value)
            altered["observation"]["process"]["status"][key] = replacement
            with self.subTest(key=key), self.assertRaises(H.Unavailable) as caught:
                H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)
            self.assertEqual(json.loads(str(caught.exception).split(": ", 1)[1])["failed"], [key])
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

    def test_failed_probe_retains_only_bounded_escaped_output_and_never_qualifies(self):
        result, binding = self.result()
        result.update(exit_code=1, diagnostic=b"discarded-prefix" + b"x" * 9000 + b"\n::error::probe\x1b[31m")
        with self.assertRaises(H.Unavailable) as caught:
            H.validate_runtime(result, binding, sandbox._ENVIRONMENT, 2001, 2001)
        message = str(caught.exception)
        self.assertNotIn("\n", message)
        self.assertNotIn("\x1b", message)
        detail = json.loads(message.split(": ", 1)[1])
        self.assertEqual(detail["exit_code"], 1)
        self.assertEqual(detail["cleanup"], {"kernel_populated": 0, "subtree_kill": True})
        self.assertTrue(detail["protected_probe_tail"].startswith("candidate-output: "))
        tail = json.loads(detail["protected_probe_tail"].removeprefix("candidate-output: "))
        self.assertEqual(len(tail.encode()), 8192)
        self.assertNotIn("discarded-prefix", tail)
        self.assertTrue(tail.endswith("\n::error::probe\x1b[31m"))

    def test_implicit_bwrap_pwd_is_explicitly_expected_and_never_ignored(self):
        value, binding = self.result()
        expected = dict(sandbox._ENVIRONMENT)
        self.assertEqual(expected["PWD"], "/work")
        previous = {key: item for key, item in expected.items() if key != "PWD"}
        with self.assertRaises(H.Unavailable) as caught:
            H.validate_runtime(value, binding, previous, 2001, 2001)
        details = json.loads(str(caught.exception).split(": ", 1)[1])
        self.assertEqual(details["failed"], ["environment"])
        self.assertEqual(details["environment_keys"]["extra"], ["PWD"])
        self.assertTrue(H.validate_runtime(value, binding, expected, 2001, 2001).startswith("sha256:"))
        for mutation in (None, "/outside"):
            altered = deepcopy(value)
            environment = altered["observation"]["identity"]["environment"]
            if mutation is None: environment.pop("PWD")
            else: environment["PWD"] = mutation
            with self.subTest(mutation=mutation), self.assertRaises(H.Unavailable) as caught:
                H.validate_runtime(altered, binding, expected, 2001, 2001)
            details = json.loads(str(caught.exception).split(": ", 1)[1])
            self.assertEqual(details["failed"], ["environment"])
            self.assertEqual(details["environment_keys"]["missing" if mutation is None else "different"], ["PWD"])

    def test_identity_failure_names_prefix_file_count_or_digest_without_raw_probe_values(self):
        original, binding = self.result()
        cases = (("prefix", "/private-unexpected-prefix", ["prefix"], 8),
                 ("files", {str(n): "a" * 64 for n in range(7)}, ["file_count"], 7),
                 ("files", {**original["observation"]["identity"]["files"], "0": "private-invalid-digest"}, ["file_digests"], 8))
        for key, replacement, failed, count in cases:
            altered = deepcopy(original)
            altered["observation"]["identity"][key] = replacement
            with self.subTest(field=key, failed=failed), self.assertRaises(H.Unavailable) as caught:
                H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)
            message = str(caught.exception)
            details = json.loads(message.split(": ", 1)[1])
            self.assertEqual(details["failed"], failed)
            self.assertEqual(details["file_count"], count)
            self.assertNotIn("private-unexpected-prefix", message)
            self.assertNotIn("private-invalid-digest", message)

    def test_environment_failure_diagnostics_are_bounded_and_never_print_values(self):
        original, binding = self.result()
        altered = deepcopy(original)
        environment = altered["observation"]["identity"]["environment"]
        environment.update({"EXTRA_" + str(i): "TEST_ONLY_SECRET_VALUE\n::error::hidden" for i in range(50)})
        environment["::error::odd-key\n"] = "TEST_ONLY_SECRET_VALUE"
        with self.assertRaises(H.Unavailable) as caught:
            H.validate_runtime(altered, binding, sandbox._ENVIRONMENT, 2001, 2001)
        message = str(caught.exception)
        details = json.loads(message.split(": ", 1)[1])
        self.assertEqual(details["failed"], ["environment"])
        self.assertEqual(len(details["environment_keys"]["extra"]), 16)
        self.assertEqual(details["environment_keys"]["actual_count"], len(environment))
        self.assertTrue(any(name.startswith("sha256:") for name in details["environment_keys"]["extra"]))
        self.assertNotIn("TEST_ONLY_SECRET_VALUE", message)
        self.assertNotIn("::error::", message)
        self.assertNotIn("\n", message)
        self.assertLess(len(message), 4096)

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
                 "tools/test-evidence/sandbox_host_fixture.py", "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml",
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


class ProtectionFixtureTests(unittest.TestCase):
    def test_readonly_requires_a_failed_write_and_exact_path_kernel_mount_evidence(self):
        path = "/fixed-canary"
        # The four actual unprivileged kernel observations: DAC may return
        # EACCES before a read-only mount returns EROFS for a writable canary.
        matrix = ((0o444, True, FIXTURE.errno.EACCES, True),
                  (0o666, True, FIXTURE.errno.EROFS, True),
                  (0o444, False, FIXTURE.errno.EACCES, False),
                  (0o666, False, None, False))
        for mode, readonly_mount, error, expected in matrix:
            flags = FIXTURE.os.ST_RDONLY if readonly_mount else 0
            failure = OSError(error, "fixed failure") if error is not None else None
            with (self.subTest(mode=oct(mode), readonly_mount=readonly_mount),
                  patch.object(FIXTURE.os, "open", return_value=17, side_effect=failure) as opening,
                  patch.object(FIXTURE.os, "statvfs", return_value=SimpleNamespace(f_flag=flags)) as mount,
                  patch.object(FIXTURE.os, "close") as closing):
                self.assertIs(FIXTURE.readonly(path), expected)
                opening.assert_called_once_with(path, FIXTURE.os.O_WRONLY | FIXTURE.os.O_CLOEXEC)
                if error is None:
                    mount.assert_not_called()
                    closing.assert_called_once_with(17)
                else:
                    mount.assert_called_once_with(path)
                    closing.assert_not_called()

    def test_readonly_rejects_other_write_errors_and_unavailable_kernel_evidence(self):
        path = "/fixed-canary"
        for error in (FIXTURE.errno.EPERM, FIXTURE.errno.ENOENT, FIXTURE.errno.EIO, FIXTURE.errno.ELOOP):
            with (self.subTest(error=error), patch.object(FIXTURE.os, "open", side_effect=OSError(error, "fixed failure")),
                  patch.object(FIXTURE.os, "statvfs") as mount):
                self.assertIs(FIXTURE.readonly(path), False)
                mount.assert_not_called()
        for error in (FIXTURE.errno.EACCES, FIXTURE.errno.EROFS):
            with (self.subTest(error=error), patch.object(FIXTURE.os, "open", side_effect=OSError(error, "fixed failure")),
                  patch.object(FIXTURE.os, "statvfs", side_effect=OSError(FIXTURE.errno.EIO, "unavailable")) as mount):
                self.assertIs(FIXTURE.readonly(path), False)
                mount.assert_called_once_with(path)


class FixedResultTests(unittest.TestCase):
    def test_prepared_java_alias_is_resolved_then_confined_before_freezing(self):
        import yaml
        paths = ('.github/workflows/shared-sandbox-host-diagnostic.yml',
                 'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml',
                 'tools/repository-checks/workflows/producers/protected-project-tests.yml')
        for relative in paths:
            workflow = yaml.safe_load((H.ROOT / relative).read_text())
            steps = [step for job in workflow['jobs'].values() for step in job.get('steps', [])]
            scripts = [step['run'] for step in steps if "<<'PYROOTS'" in step.get('run', '')
                       and 'test -n "$JAVA_HOME"' in step['run']]
            self.assertEqual(len(scripts), 1)
            script = scripts[0]
            resolver = 'JAVA_HOME="$(readlink -e -- "$JAVA_HOME")"'
            self.assertLess(script.index(resolver), script.index("<<'PYROOTS'"))
            self.assertLess(script.index("\nPYROOTS"), script.index('chown -hR'))
            # Execute the actual shell resolver against a real cache alias.
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / 'system-jdk'
                target.mkdir()
                alias = Path(temporary) / 'cache-x64'
                alias.symlink_to(target, target_is_directory=True)
                result = subprocess.run(['bash', '-eu', '-c', resolver + '\nprintf "%s" "$JAVA_HOME"'],
                    env={'PATH': '/usr/bin:/bin', 'JAVA_HOME': str(alias)}, capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout, str(target))
            body = script.split("<<'PYROOTS'\n", 1)[1].split('\nPYROOTS', 1)[0]
            python = '/opt/hostedtoolcache/Python/3.12.15/x64'
            node = '/opt/hostedtoolcache/node/22.23.3/x64'
            # Fake only filesystem presence; execute the production allowlist.
            cases = {'/usr/lib/jvm/temurin-17-jdk-amd64': True,
                     '/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/17.0.20-1/x64': True,
                     '/usr/lib/jvm/unknown': False, '/tmp/system-jdk': False,
                     '/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/21.0.1-1/x64': False,
                     '/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/17.0.20-1/arm64': False,
                     python: False, '/usr': False}
            for java, accepted in cases.items():
                with (self.subTest(workflow=relative, java=java),
                      patch.object(sys, 'argv', ['-', python, node, java]),
                      patch.object(Path, 'is_dir', return_value=True),
                      patch.object(Path, 'is_symlink', return_value=False),
                      patch.object(Path, 'resolve', lambda self, strict=False: self)):
                    if accepted:
                        exec(compile(body, relative, 'exec'), {})
                    else:
                        with self.assertRaises(AssertionError):
                            exec(compile(body, relative, 'exec'), {})

    def test_manual_workflow_matches_template_without_pr_trigger_or_success_skip(self):
        template = (H.ROOT / "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml").read_text()
        self.assertIn("options: [boundary, shared-host, ci37]", template)
        self.assertIn("default: boundary", template)
        self.assertNotIn("pull_request:", template)
        self.assertNotIn("workflow_call:", template)
        self.assertIn("--property=Delegate=yes", template)
        for property in ("KillMode=control-group", "TimeoutStopSec=10s", "SendSIGKILL=yes"):
            self.assertIn("--property=" + property, template)
        self.assertIn("lifetime=120", template)
        self.assertIn("lifetime=2400", template)
        self.assertIn('--property="RuntimeMaxSec=${lifetime}s"', template)
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

    def test_boundary_flag_diagnostics_report_only_fixed_names_and_shape(self):
        prefix = "one or more real boundary attacks succeeded or prerequisites failed: "
        untrusted = "private-observation-token::error::/unexpected/path"
        cases = []
        for value in (False, 1, untrusted):
            observation = protection_result()["observation"]
            observation["git_pristine"] = value
            cases.append((observation, {"failed": ["git_pristine"], "missing": [], "extra": False}))
        observation = protection_result()["observation"]
        del observation["readonly_mount_flags"]
        cases.append((observation, {"failed": [], "missing": ["readonly_mount_flags"], "extra": False}))
        observation = protection_result()["observation"]
        observation[untrusted] = {untrusted: untrusted}
        cases.append((observation, {"failed": [], "missing": [], "extra": True}))
        observation = protection_result()["observation"]
        observation["git_readonly"] = False
        del observation["venv_aliases"]
        observation[untrusted] = untrusted
        cases.append((observation, {"failed": ["git_readonly"], "missing": ["venv_aliases"], "extra": True}))
        for observation, expected in cases:
            failed = protection_result()
            failed["observation"] = observation
            with self.subTest(expected=expected), self.assertRaises(H.Unavailable) as caught:
                H.validate_case("protections", failed, outside())
            self.assertEqual(str(caught.exception), prefix + json.dumps(expected, sort_keys=True))
            self.assertNotIn(untrusted, str(caught.exception))

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



class SharedHostCompatibilityTests(unittest.TestCase):
    """Only fake suite commands/control facts; never root/bwrap/Qt workloads."""
    def test_current_registry_uses_actual_controller_commands_and_device_deadline(self):
        registry = SHARED.inputs.load_registry(H.ROOT / ".github/test-suites.json")
        calls = []
        def fake(command, timeout, cancelled):
            calls.append((command, timeout))
            return 0, "", ""
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "suites.xml"
            observed = SHARED.run_suites(SimpleNamespace(run_command=fake), registry, [], report=report)
            self.assertTrue(report.is_file())
        self.assertEqual([entry["name"] for entry in observed], list(registry["suites"]))
        self.assertEqual(len(calls), len(registry["suites"]))
        for (name, entry), (command, timeout) in zip(registry["suites"].items(), calls):
            expected = entry["command"] + (["--timeout-seconds", "900"] if name == "device-control-plane-full" else [])
            self.assertEqual(command, expected)
            self.assertEqual(timeout, 900 if name == "device-control-plane-full" else 240)
        self.assertIn("--require-qml", registry["suites"]["device-control-plane-full"]["command"])
        self.assertFalse(any(any("browser-client/" in argument for argument in command) for command, _ in calls))

    def test_failed_or_cancelled_actual_controller_result_cannot_pass(self):
        registry = {"suites": {"one": {"layer": "quick", "command": ["python", "fake.py"]}}}
        for failed, cancelled in ((True, []), (False, [15])):
            with self.subTest(failed=failed, cancelled=cancelled), tempfile.TemporaryDirectory() as temporary:
                batch = SimpleNamespace(run_command=lambda *_: (1 if failed else 0, "candidate-output: \"::error::fake\"", ""))
                with self.assertRaises(H.Unavailable):
                    SHARED.run_suites(batch, registry, cancelled, report=Path(temporary) / "suite.xml")

    def test_whole_batch_checks_surround_full_probes_and_actual_suite_execution(self):
        for mismatch in (None, "after", "prepared", "policy", "suite"):
            events = []
            batch = SimpleNamespace(candidate=Path("/fixture"), snapshot={}, policy=Path("/policy"), projection={},
                                    protected=Path("/protected"), prepared=((), None, None, Path("/usr/lib/jvm/fake")),
                                    empty=lambda: events.append("kernel-empty"))
            def probe(_):
                events.append("probe")
                return {"real-E": len(events) if mismatch == "after" else 1}
            batch.probe = probe
            def suites(*_a, **_k):
                events.append("actual-run-suites")
                if mismatch == "suite": raise H.Unavailable("suite failed")
                return [{"name": "fake", "status": "passed"}]
            with (patch.object(sandbox, "verify_snapshot", side_effect=lambda *_: events.append("verify-source")),
                  patch.object(sandbox, "_files", return_value={"changed": True} if mismatch == "policy" else {}),
                  patch.object(SHARED, "prepared_identity", return_value={"different": 1} if mismatch == "prepared" else {}),
                  patch.object(SHARED, "run_suites", side_effect=suites)):
                if mismatch is None:
                    SHARED.check_batch(batch, {}, [], {})
                    self.assertEqual(events, ["verify-source", "probe", "actual-run-suites", "kernel-empty", "probe", "verify-source"])
                else:
                    with self.assertRaises(H.Unavailable):SHARED.check_batch(batch, {}, [], {})
                    if mismatch == "suite": self.assertEqual(events.count("probe"), 1)
                    if mismatch == "policy":self.assertNotIn("actual-run-suites", events)

    def test_failure_summary_survives_private_log_removal_and_cannot_emit_action_commands(self):
        registry = {"suites": {"actual-suite": {"layer": "host", "command": ["python", "fake.py"]}}}
        batch = SimpleNamespace(run_command=lambda *_: (1, sandbox.safe_diagnostic(b"::error::fixture\n\x1b[31m"), "timeout"))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(H.Unavailable) as caught:
                SHARED.run_suites(batch, registry, [], report=Path(temporary) / "suites.xml")
        message = str(caught.exception)
        self.assertIn("actual-suite", message)
        self.assertIn("timeout", message)
        self.assertIn("fixture", message)
        self.assertNotIn("\n", message)
        self.assertNotIn("\x1b", message)
        self.assertLess(len(message), 16_000)
        probe = {"exit_code": 1, "reason": None, "cleanup": {"kernel_populated": 0, "subtree_kill": True},
                 "diagnostic": b"runtime.RuntimeIdentityError: required Qt dependency unavailable\n"}
        with self.assertRaises(H.Unavailable) as caught:SHARED.validate_probe(probe, {}, 2001, 2001)
        self.assertIn("required Qt dependency unavailable", str(caught.exception))
        self.assertNotIn("\n", str(caught.exception))

    def test_live_scope_blocks_next_launch_and_protected_post_probe(self):
        batch = object.__new__(SHARED.Batch)
        batch.scopes = [SimpleNamespace(populated=lambda: 1)]
        with self.assertRaises(H.Unavailable):batch.empty()
        with patch.object(batch, "launch") as launch, self.assertRaises(H.Unavailable):batch.probe([])
        launch.assert_not_called()

    def test_candidate_output_is_encoded_before_existing_runner_can_print_it(self):
        batch = object.__new__(SHARED.Batch)
        with patch.object(batch, "launch", return_value={"exit_code": 1, "reason": "timeout", "diagnostic": b"::error::untrusted\n\x1b[31m"}):
            code, output, message = batch.run_command(["python", "fake.py"], 240, [])
        self.assertEqual((code, message), (1, "timeout"))
        self.assertTrue(output.startswith("candidate-output: "))
        self.assertNotIn("\n", output)
        self.assertNotIn("\x1b", output)

    def test_shared_plan_uses_only_prepared_tools_exact_safe_work_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("source", "scratch", "policy", "venv", "protected")]
            for path in paths:path.mkdir()
            (paths[0] / ".git").mkdir()
            layout = sandbox.Layout(*paths)
            prepared = ((), Path("/opt/hostedtoolcache/Python/3.12.12/x64"),
                        Path("/opt/hostedtoolcache/node/22.20.0/x64"), Path("/usr/lib/jvm/temurin-17-jdk-amd64"))
            # This fixture checks the command/mount plan, not the local JDK's
            # ownership. Real temporary certificate aliases are covered below.
            with patch.object(SHARED, "prepared_external_inputs", return_value=()) as external:
                plan = SHARED.shared_plan(layout, ["python", "tests/fake.py", "--require-qml"], prepared, {})
            external.assert_called_once_with(prepared)
            args = plan["argv"]
            self.assertEqual(args[-3:], ["/opt/overte-ci/venv/bin/python", "tests/fake.py", "--require-qml"])
            triples = [args[i + 1:i + 3] for i, value in enumerate(args) if value == "--setenv"]
            self.assertIn(["GIT_CONFIG_COUNT", "3"], triples)
            self.assertIn(["GIT_CONFIG_KEY_2", "safe.directory"], triples)
            self.assertIn(["GIT_CONFIG_VALUE_2", "/work"], triples)
            self.assertFalse(any("TOKEN" in key or key in {"GITHUB_OUTPUT", "GITHUB_ENV"} for key, _ in triples))
            for flag in ("--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--cap-drop", "--clearenv"):
                self.assertIn(flag, args)
            with self.assertRaises(H.Unavailable):SHARED.shared_plan(layout, ["npm", "test"], prepared, {})

    def test_private_controller_log_is_bounded_without_turning_failed_tests_green(self):
        output = io.BytesIO()
        log = SHARED.BoundedLog(output)
        log.write("x" * 4_000_100)
        log.write("::error::discarded")
        self.assertEqual(len(output.getvalue()), 4_000_000)
        self.assertEqual(log.remaining, 0)

    def test_unknown_full_E_has_no_local_process_or_incomplete_fallback(self):
        result = {"exit_code": 0, "reason": None, "cleanup": {"kernel_populated": 0, "subtree_kill": True},
                  "observation": {"schema": 1, "authority": "none", "measurement": SHARED.PROFILE,
                                  "binding": {}, "environment": {"unknown": True}, "process": {}, "mounts": {}, "namespaces": {}, "reusable": False}}
        binding = {"prepared": {}, "outside_namespaces": {"user": 1}}
        result["observation"]["binding"] = binding
        result["observation"]["mounts"] = {name: ["ro"] for name in ("/usr", "/work", "/overte-policy", str(SHARED.VENV))}
        result["observation"]["mounts"]["/work/build"] = ["rw"]
        result["observation"]["namespaces"] = {"user": 2}
        for field in ("environment", "binding", "cleanup", "reason"):
            with self.subTest(field=field):
                changed = deepcopy(result)
                if field == "environment":changed["observation"][field] = None
                elif field == "binding":changed["observation"][field] = {"foreign": True}
                elif field == "cleanup":changed[field]["kernel_populated"] = 1
                else:changed[field] = "timeout"
                with self.assertRaises((H.Unavailable, SHARED.inputs.InputError)):
                    SHARED.validate_probe(changed, binding, 2001, 2001)
        with self.assertRaises(H.Unavailable):SHARED.validate_probe(result, binding, 2001, 2001)

    def test_protected_probe_calls_complete_runtime_and_never_falls_back_to_unknown_E(self):
        import sandbox_probe as probe
        binding = {"profile": SHARED.PROFILE, "prepared": {"/opt/overte-ci/venv": "fixed"}}
        paths = ("/usr", "/work", "/overte-policy", "/opt/overte-ci/venv", "/work/build")
        mounts = "\n".join(f"1 0 0:1 / {path} {'rw' if path.endswith('/build') else 'ro'} - tmpfs tmpfs rw" for path in paths)
        error = probe.runtime.RuntimeIdentityError("required host Python dependencies are missing")
        with (patch.object(probe.Path, "read_bytes", return_value=json.dumps({"shared_host": binding}).encode()),
              patch.object(probe.Path, "read_text", return_value=mounts),
              patch.object(probe.socket, "if_nameindex", return_value=[(1, "lo")]),
              patch.object(probe.socket, "socket"), patch.object(probe.fcntl, "ioctl", return_value=b"\0" * 16 + b"\1\0"),
              patch.object(probe, "process_observation", return_value={"fixture": "not real process proof"}),
              patch.object(probe.os, "stat", return_value=SimpleNamespace(st_ino=123)),
              patch.object(probe.runtime, "capture_isolated_host_environment", side_effect=error) as capture):
            with self.assertRaises(probe.runtime.RuntimeIdentityError):probe.measure_shared_host()
            capture.assert_called_once_with(binding['prepared'])
            capture.side_effect = None
            capture.return_value = {"fixture": "fake complete-runtime call only, no actual E qualification"}
            result = probe.measure_shared_host()
            self.assertFalse(result["reusable"])
            self.assertEqual(result["authority"], "none")
            self.assertEqual(result["environment"], capture.return_value)
            self.assertEqual(result["binding"], binding)
            with patch.object(probe.socket, "if_nameindex", return_value=[(1, "lo"), (2, "eth0")]), self.assertRaises(ValueError):
                probe.measure_shared_host()
            with patch.object(probe.Path, "read_text", return_value=mounts.replace("/work ro", "/work rw")), self.assertRaises(ValueError):
                probe.measure_shared_host()

    def test_prepared_symlink_cannot_escape_readonly_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "escape").symlink_to("/tmp")
            with patch.object(SHARED, "VENV", root):
                # No local root assumptions: protection of a prepared directory
                # is itself mandatory before any alias/content claim.
                with self.assertRaises(H.Unavailable):SHARED.prepared_identity(())

    def test_sudo_successful_zero_rights_listing_is_denial_but_grants_errors_or_extras_are_not(self):
        account = SimpleNamespace(pw_uid=2001, pw_gid=2001, pw_shell="/usr/sbin/nologin")
        denial = b"User overte-ci-qualification is not allowed to run sudo on host.\n"
        cases = [(0, denial, b"", True), (1, denial, b"", True), (2, denial, b"", False),
                 (0, b"User overte-ci-qualification may run the following commands on host:\n (ALL) ALL\n", b"", False),
                 (0, denial, b"policy plugin error", False), (1, b"", denial, False),
                 (0, denial + b"extra policy\n", b"", False), (0, b"header\n" + denial, b"", False),
                 (0, denial.replace(b"qualification", b"foreign"), b"", False), (0, b"", b"", False)]
        with (patch.object(H.pwd, "getpwnam", return_value=account), patch.object(H.os, "getgrouplist", return_value=[2001]),
              patch.object(H.grp, "getgrgid", return_value=SimpleNamespace(gr_name="qualification"))):
            for code, out, err, accepted in cases:
                with self.subTest(code=code, out=out, err=err), patch.object(H, "command", return_value=SimpleNamespace(returncode=code, stdout=out, stderr=err)):
                    if accepted:self.assertEqual(H.verify_account(1001), (2001, 2001))
                    else:
                        with self.assertRaises(H.Unavailable):H.verify_account(1001)

    def test_failed_sudo_policy_prints_only_bounded_public_classification(self):
        account = SimpleNamespace(pw_uid=2001, pw_gid=2001, pw_shell="/usr/sbin/nologin")
        private = b"PRIVATE-HOST and /private/command may run the following commands"
        with (patch.object(H.pwd, "getpwnam", return_value=account), patch.object(H.os, "getgrouplist", return_value=[2001]),
              patch.object(H.grp, "getgrgid", return_value=SimpleNamespace(gr_name="qualification")),
              patch.object(H, "command", return_value=SimpleNamespace(returncode=0, stdout=private, stderr=b""))):
            with self.assertRaises(H.Unavailable) as caught:H.verify_account(1001)
        message = str(caught.exception)
        self.assertIn('"exit_code": 0', message)
        self.assertIn('"grant_marker": true', message)
        self.assertNotIn("PRIVATE-HOST", message)
        self.assertNotIn("/private", message)

    def test_launch_has_fresh_scratch_guardian_before_work_and_cleanup_on_failure(self):
        for failure in (None, "work", "proof"):
            events, scratch_paths = [], []
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                candidate, policy = base / "source", base / "policy"
                candidate.mkdir();policy.mkdir()
                prepared = ((), Path("/python"), Path("/node"), Path("/java"))
                batch = SHARED.Batch(base, candidate, policy, {}, {}, {}, prepared, Path("/delegated"), 2001, 2001, {})
                scope = SimpleNamespace(populated=lambda: 0, kill_and_wait=lambda: events.append("kill-empty"),
                                        close=lambda: events.append("close-scope"))
                guardian = SimpleNamespace(finish=lambda: events.append("proof") or {},
                                           close=lambda: events.append("close-guardian"))
                def plan(layout, *_):
                    scratch_paths.append(layout.scratch)
                    return {"argv": ["/usr/bin/bwrap", "--", "fake-only"]}
                def work(*_a, **_k):
                    events.append("work")
                    if failure == "work":raise H.Unavailable("failed workload")
                    return {"exit_code": 0}
                def guard(*_a, **_k):
                    events.append("guardian-ready")
                    if failure == "proof":
                        guardian.finish=lambda: (_ for _ in ()).throw(H.Unavailable("no proof"))
                    return guardian
                with (patch.object(SHARED.os, "chown"), patch.object(SHARED, "shared_plan", side_effect=plan),
                      patch.object(H, "OwnedScope", return_value=scope), patch.object(H, "Guardian", side_effect=guard),
                      patch.object(H, "supervise", side_effect=work)):
                    if failure:
                        with self.assertRaises(H.Unavailable):batch.launch(["python", "fake.py"], 900, [])
                    else:
                        batch.launch(["python", "fake.py"], 900, [])
                        batch.launch(["python", "fake.py"], 900, [])
                        self.assertNotEqual(scratch_paths[0], scratch_paths[1])
                    self.assertTrue(all(not path.exists() for path in scratch_paths))
                    self.assertEqual(events[0:2], ["guardian-ready", "work"])
                    self.assertEqual(events[-3:], ["close-guardian", "kill-empty", "close-scope"])
                    self.assertEqual(batch.scopes, [])

    def test_cleanup_failure_retains_original_safe_error_and_still_kills_owned_scope(self):
        events=[]
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);candidate=base/'source';policy=base/'policy'
            candidate.mkdir();policy.mkdir()
            batch=SHARED.Batch(base,candidate,policy,{},{},{},((),None,None,None),Path('/unused'),2001,2001,{})
            def close():events.append('scope-close');raise PermissionError(13,'private cleanup','/private/secret')
            scope=SimpleNamespace(populated=lambda:0,kill_and_wait=lambda:events.append('kill-empty'),close=close)
            guardian=SimpleNamespace(finish=lambda:{},close=lambda:events.append('guardian-close'))
            with (patch.object(SHARED.os,'chown'),patch.object(SHARED,'shared_plan',return_value={'argv':['fake-only']}),
                  patch.object(H,'OwnedScope',return_value=scope),patch.object(H,'Guardian',return_value=guardian),
                  patch.object(H,'supervise',side_effect=KeyError('private original suite failure')),
                  patch.object(SHARED,'run_host',side_effect=lambda:batch.launch(['python','fake.py'],900,[])),
                  patch.object(H.sys,'stdout',new_callable=io.StringIO) as output):
                self.assertEqual(H.main(['--profile','shared-host']),1)
            raw=output.getvalue();report=json.loads(raw)
            self.assertEqual(report['status'],'unavailable');self.assertFalse(report['production_qualified'])
            self.assertEqual(events,['guardian-close','kill-empty','scope-close'])
            self.assertEqual([row['exception_class'] for row in report['failure']['chain']],['PermissionError','KeyError'])
            self.assertTrue(all(row['source']=='tools/test-evidence/sandbox_shared.py' for row in report['failure']['chain']))
            self.assertNotEqual(*[row['line'] for row in report['failure']['chain']])
            self.assertNotIn('private',raw);self.assertNotIn('/private',raw)

    def test_manual_profile_is_finite_and_pr_production_paths_remain_denied(self):
        template = (H.ROOT / ".github/workflows/shared-sandbox-host-diagnostic.yml").read_text()
        self.assertIn("options: [boundary, shared-host, ci37]", template)
        self.assertIn("fetch-depth: 2", template)
        self.assertIn("node-version: '22'", template)
        self.assertIn("python-version: '3.12'", template)
        self.assertIn("java-version: '17'", template)
        self.assertNotIn("workflow_call:", template)
        self.assertNotIn("pull_request:", template)
        with patch.object(sandbox,'ACTIVATION_READY',True):
            for call in (sandbox.execute, sandbox.capture_after_execution):
                with self.assertRaises(sandbox.SandboxUnavailable):call()

    def test_manual_result_cannot_gain_production_authority_from_source_capabilities(self):
        import producer_workflow as producer
        before={'fixture':'recorded E without tool probes'}
        original_stat=Path.stat
        original_os_stat=os.stat
        tools={'/usr/bin/bwrap','/usr/bin/unshare','/usr/bin/python3','/usr/bin/sudo'}
        def fixed_tool(path,*args,**kwargs):
            return SimpleNamespace(st_mode=0o100755,st_uid=0) if str(path) in tools else original_stat(path,*args,**kwargs)
        def namespace_stat(path,*args,**kwargs):
            return SimpleNamespace(st_ino=1) if str(path).startswith('/proc/self/ns/') else original_os_stat(path,*args,**kwargs)
        batch=SimpleNamespace(protected=Path('/unwritten-protected'),proofs=['fake cleanup proof'])
        patches=[patch.object(producer,'PRODUCTION_READY',True),patch.object(sandbox,'ACTIVATION_READY',True),
              patch.object(producer.attested,'ISOLATED_ADMISSION_READY',True),
              patch.dict(os.environ,context(),clear=True),patch.object(H,'host_context',return_value=1001),
              patch.object(Path,'read_text',return_value='ID=ubuntu\nVERSION_ID="24.04"\n'),
              patch.object(Path,'stat',fixed_tool),patch.object(H,'verify_account',return_value=(2001,2001)),
              patch.object(SHARED,'verify_source',return_value=[]),patch.object(SHARED,'prepared_tools',return_value=((),None,None,None)),
              patch.object(SHARED,'prepared_identity',return_value={}),patch.object(H,'prepare_delegation'),
              patch.object(SHARED.inputs,'load_registry',return_value={'suites':{}}),patch.object(SHARED.signal,'signal'),
              patch.object(SHARED,'materialize_source',return_value={'digest':'fixture snapshot','git_context':{}}),
              patch.object(SHARED,'project_policy',return_value={}),patch.object(sandbox,'_write_source'),
              patch.object(sandbox,'_files',return_value={}),patch.object(SHARED,'Batch',return_value=batch),
              patch.object(SHARED.os,'stat',side_effect=namespace_stat),
              patch.object(SHARED,'check_batch',return_value=([],before,before)),
              patch.object(SHARED.execution,'_write_receipt')]
        with ExitStack() as stack:
            mocks=[stack.enter_context(item) for item in patches]
            result=SHARED.run_host()
        self.assertEqual(result['status'],'shared-host-diagnostic-passed')
        self.assertEqual(result['authority'],'none')
        self.assertIs(result['production_qualified'],False)
        self.assertIs(result['reusable'],False)
        mocks[-1].assert_called_once()


class SharedHostSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.names = SHARED.sources()
        for name in self.names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(H.ROOT / name, path)
        # Only these private fixture files are rewritten below/by the negative
        # source test. Original snapshot bytes and every other copied mode stay
        # immutable when the caller supplies a read-only source checkout.
        for name in ('tests/platform-profile.json', 'tools/test-evidence/sandbox_shared.py'):
            (self.root / name).chmod(0o644)
        # This immutable fixture is the shared-main manual source. Never inherit
        # Android/child setup merely from the branch running these unit tests.
        profile = (json.dumps({'schema': 1, 'platform': 'shared', 'suites': []}, indent=2) + "\n").encode()
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(profile)).encode() + b'\0' + profile).hexdigest(),
                         'd63537504c20204de9d35d9be61da72a56df59c3')
        (self.root / 'tests/platform-profile.json').write_bytes(profile)
        self.git("init", "-q", "--initial-branch=main")
        self.git("add", ".")
        self.git("commit", "-qm", "Record protected shared-host controls")
        self.revision = self.git("rev-parse", "HEAD").strip().decode()
    def git(self, *arguments):
        result = H.command(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                            "-c", "user.name=Source fixture", "-c", "user.email=fixture@example.invalid", *arguments], cwd=self.root)
        result.check_returncode()
        return result.stdout
    def test_actual_shallow_source_and_finite_projection_exclude_candidate_shadow_imports(self):
        (self.root / ".git/shallow").write_text(self.revision + "\n")
        (self.root / "json.py").write_text("raise RuntimeError('candidate shadow must never execute')\n")
        projection = self.root / "projected"
        projection.mkdir()
        with patch.object(SHARED, "ROOT", self.root):
            self.assertEqual(SHARED.verify_source(self.revision), self.names)
            expected = SHARED.project_policy(projection, self.names, trusted_source=self.revision)
        self.assertNotIn("json.py", expected)
        for required in (*runtime_files(), "tools/test-evidence/sandbox_shared.py", "tests/requirements-host.txt"):
            self.assertIn(required, expected)
        self.assertFalse((projection / ".git").exists())
        (projection / "json.py").write_text("unexpected import\n")
        (projection / "json.py").chmod(0o444)
        self.assertNotEqual(sandbox._files(projection), expected)
    def test_shared_source_materializes_exact_ordered_parents_and_truthful_depth2_boundary(self):
        original = self.revision
        (self.root / "ordinary-source").write_text("source fixture\n")
        self.git("add", "ordinary-source")
        self.git("commit", "-qm", "Record fixture source")
        first = self.git("rev-parse", "HEAD").strip().decode()
        original_tree = self.git("rev-parse", original + "^{tree}").strip().decode()
        other = self.git("commit-tree", original_tree, "-p", original, "-m", "Record other fixture parent").strip().decode()
        first_tree = self.git("rev-parse", first + "^{tree}").strip().decode()
        merged = self.git("commit-tree", first_tree, "-p", first, "-p", other, "-m", "Record ordered fixture merge").strip().decode()
        (self.root / ".git/shallow").write_text(first + "\n" + other + "\n")
        destination = self.root.parent / (self.root.name + "-snapshot")
        destination.mkdir()
        self.addCleanup(shutil.rmtree, destination)
        with patch.object(SHARED, "ROOT", self.root):
            SHARED.verify_source(merged)
            expected = SHARED.materialize_source(merged, destination)
        sandbox.verify_snapshot(destination, expected)
        self.assertEqual(list(expected["git_context"]["commits"]), [merged, first, other])
        self.assertEqual(expected["identity"]["parents"], [first, other])
        self.assertEqual(expected["git_context"]["shallow"], sorted([first, other]))
        self.assertEqual((destination / ".git/shallow").read_text(), "".join(value + "\n" for value in sorted([first, other])))
        self.assertEqual((destination / "ordinary-source").read_text(), "source fixture\n")
        self.assertNotIn(original, expected["git_context"]["commits"])
        self.assertFalse((destination / ".git/objects" / original[:2] / original[2:]).exists())
        observed = H.command(["/usr/bin/git", "--no-optional-locks", "rev-list", "--count", "HEAD"], cwd=destination)
        observed.check_returncode()
        self.assertEqual(observed.stdout.strip(), b"3")

    def test_readonly_source_retains_modes_and_rejects_changed_private_controls(self):
        with tempfile.TemporaryDirectory(prefix='shared-host-readonly-source-') as temporary:
            source = Path(temporary)
            for name in self.names:
                original = H.ROOT / name
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original.read_bytes())
                path.chmod(0o555 if original.stat().st_mode & 0o111 else 0o444)
            before = {name: ((source / name).read_bytes(), (source / name).stat().st_mode & 0o777)
                      for name in self.names}
            case = SharedHostSourceTests('test_modified_loaded_control_or_missing_executable_source_is_rejected')
            self.addCleanup(case.doCleanups)
            with patch.object(H, 'ROOT', source):
                case.setUp()
                rewritten = {'tests/platform-profile.json', 'tools/test-evidence/sandbox_shared.py'}
                for name in self.names:
                    expected = 0o644 if name in rewritten else before[name][1]
                    self.assertEqual((case.root / name).stat().st_mode & 0o777, expected, name)
                with patch.object(SHARED, 'ROOT', case.root):
                    self.assertEqual(SHARED.verify_source(case.revision), case.names)
                case.test_modified_loaded_control_or_missing_executable_source_is_rejected()
            self.assertEqual({name: ((source / name).read_bytes(), (source / name).stat().st_mode & 0o777)
                              for name in self.names}, before)

    def test_modified_loaded_control_or_missing_executable_source_is_rejected(self):
        path = self.root / "tools/test-evidence/sandbox_shared.py"
        path.write_bytes(path.read_bytes() + b"\n# altered loaded source\n")
        with patch.object(SHARED, "ROOT", self.root), self.assertRaises(H.Unavailable):SHARED.verify_source(self.revision)
        self.git("checkout", "--", "tools/test-evidence/sandbox_shared.py")
        self.git("update-index", "--chmod=-x", "tests/run-project-tests.py")
        self.git("commit", "-qm", "Remove required controller executable mode")
        revision = self.git("rev-parse", "HEAD").strip().decode()
        with patch.object(SHARED, "ROOT", self.root), self.assertRaises(H.Unavailable):SHARED.verify_source(revision)


def runtime_files():
    return SHARED.runtime._TRUSTED_EXECUTION_FILES


class ProtectedSelectedProducerTests(unittest.TestCase):
    """Fake commands/API facts only; no hosted/runtime qualification is claimed."""
    def setUp(self):
        import producer_workflow
        self.producer = producer_workflow

    def test_producer_cli_failure_remains_fatal_and_reports_only_closed_source_facts(self):
        source = H.ROOT / 'tools/test-evidence/producer_workflow.py'
        secret = 'PRIVATE-fixture-::error::-command-env-output'
        script = ('import runpy,sys\n'
            'sys.path.insert(0,' + repr(str(source.parent)) + ')\n'
            'import sandbox\n'
            'def refused(root):\n'
            ' try:\n'
            '  raise FileNotFoundError(2,' + repr(secret) + ',' + repr('/private/' + secret) + ')\n'
            ' except FileNotFoundError as inner:\n'
            '  raise ValueError(' + repr(secret) + ') from inner\n'
            'sandbox.require_protected_execution=refused\n'
            'sys.argv=[' + repr(str(source)) + ',"shared","--candidate","/unused-fixture"]\n'
            'runpy.run_path(' + repr(str(source)) + ',run_name="__main__")\n')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', script],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        prefix = 'Protected shared producer failed closed: '
        self.assertTrue(result.stderr.startswith(prefix), result.stderr)
        report = json.loads(result.stderr[len(prefix):])
        self.assertEqual(report['chain'][0]['exception_class'], 'ValueError')
        self.assertEqual(report['chain'][0]['source'], 'tools/test-evidence/producer_workflow.py')
        self.assertEqual(report['chain'][0]['stage'], 'protected-source-admission')
        self.assertEqual(report['chain'][1]['exception_class'], 'FileNotFoundError')
        self.assertEqual(report['chain'][1]['errno'], 2)
        self.assertNotIn(secret, result.stderr)
        self.assertNotIn('/private/', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('::error::', result.stderr)
        self.assertLess(len(result.stderr), 5000)

    def test_producer_api_failure_reports_the_fixed_boundary_without_request_data(self):
        api = self.producer.producer_api
        secret = 'PRIVATE-fixture-::error::-endpoint'
        with patch.object(api.subprocess, 'Popen') as process:
            try:
                api.GitHubReadOnly().json('/private/' + secret)
            except api.ApiError as error:
                report = H.failure_summary(error)
            else:
                self.fail('unreviewed endpoint was accepted')
        process.assert_not_called()
        self.assertEqual(report['chain'][0]['source'], 'tools/test-evidence/producer_api.py')
        self.assertEqual(report['chain'][0]['stage'], 'github-get-boundary')
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn('/private/', json.dumps(report))

    def test_selected_subset_uses_existing_runner_once_with_real_device_timeout_rule(self):
        registry = SHARED.inputs.load_registry(H.ROOT / '.github/test-suites.json')
        names = ['device-control-plane-full', 'branch-policy']
        calls = []
        batch = SimpleNamespace(run_command=lambda command, timeout, cancelled: calls.append((command, timeout)) or (0, '', ''))
        with tempfile.TemporaryDirectory() as temporary:
            statuses = SHARED.run_suites(batch, registry, [], report=Path(temporary)/'suites.xml', names=names)
        expected = [name for name in registry['suites'] if name in names]
        self.assertEqual([row['name'] for row in statuses], expected)
        self.assertEqual(len(calls), 2)
        device = next((command, timeout) for command, timeout in calls if '--require-qml' in command)
        self.assertEqual(device[1], 900)
        self.assertEqual(device[0][-2:], ['--timeout-seconds', '900'])
        for invalid in ([], ['unknown'], ['branch-policy','branch-policy']):
            calls.clear()
            with tempfile.TemporaryDirectory() as temporary, self.assertRaises((H.Unavailable, SHARED.execution.ExecutionError)):
                SHARED.run_suites(batch, registry, [], report=Path(temporary)/'bad.xml', names=invalid)
            self.assertEqual(calls, [])

    def test_runtime_admission_precedes_suite_start_and_post_failure_has_no_retry(self):
        events=[]
        batch=SimpleNamespace(candidate=Path('/fixture'),snapshot={},policy=Path('/policy'),projection={},
            protected=Path('/protected'), prepared=((),None,None,Path('/usr/lib/jvm/fake')),
            empty=lambda:events.append('empty'), probe=lambda _:events.append('probe') or {'E':1})
        with (patch.object(sandbox,'verify_snapshot'), patch.object(sandbox,'_files',return_value={}),
              patch.object(SHARED,'prepared_identity',return_value={}),
              patch.object(SHARED,'run_suites',side_effect=lambda *a,**k:events.append('suite') or [])):
            def admit(_):events.append('admit');raise self.producer.PreExecutionUnavailable('unqualified E')
            with self.assertRaises(self.producer.PreExecutionUnavailable):SHARED.check_batch(batch,{},[],{},admit=admit)
            self.assertEqual(events,['probe','admit'])
        events.clear()
        with (patch.object(sandbox,'verify_snapshot'),patch.object(sandbox,'_files',return_value={}),
              patch.object(SHARED,'run_suites',side_effect=H.Unavailable('actual timeout')) as run):
            with self.assertRaises(H.Unavailable):SHARED.check_batch(batch,{},[],{},admit=lambda _:events.append('admit'))
            self.assertEqual(run.call_count,1)
            self.assertEqual(events,['probe','admit'])

    def test_schema_context_is_reconstructed_from_immutable_api_commits(self):
        binding={'merge_sha':'a'*40,'merge_tree':'d'*40,'merge_parents':['b'*40,'c'*40]}
        facts={'a'*40:('d'*40,['b'*40,'c'*40]),'b'*40:('e'*40,['f'*40]),'c'*40:('e'*40,['b'*40])}
        adapter=SimpleNamespace(_commit=lambda oid:facts[oid])
        observed=self.producer.expected_git_context(adapter,binding)
        self.assertEqual(observed['shallow'],['b'*40])
        self.assertEqual(list(observed['commits']),['a'*40,'b'*40,'c'*40])
        facts['a'*40]=('d'*40,['c'*40,'b'*40])
        with self.assertRaises(H.Unavailable):self.producer.expected_git_context(adapter,binding)

    def test_native_source_context_rejects_other_workflow_attempt_target_and_repo(self):
        environment={**context(),'GITHUB_EVENT_NAME':'pull_request','GITHUB_BASE_REF':'main',
            'GITHUB_HEAD_REF':'fix/main/example','GITHUB_REF':'refs/pull/17/merge',
            'GITHUB_WORKFLOW_REF':'noah-l-frank/overte/.github/workflows/repository-checks.yml@refs/pull/17/merge'}
        self.assertEqual(self.producer._native(environment),(17,123))
        for target in self.producer.source_admission.TARGET_PROFILES:
            with self.subTest(target=target):
                self.assertEqual(self.producer._native({**environment,'GITHUB_BASE_REF':target}),(17,123))
        for key,value in (('GITHUB_REPOSITORY','overte-org/overte'),('GITHUB_REPOSITORY_ID','1'),
                ('GITHUB_BASE_REF','unknown-target'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_RUN_ATTEMPT','2'),
                ('GITHUB_WORKFLOW_REF','other/workflow'),('GITHUB_WORKFLOW_SHA','b'*40)):
            with self.subTest(key=key),self.assertRaises(H.Unavailable):self.producer._native({**environment,key:value})

    def test_event_payload_cannot_replace_fresh_api_base_head_or_pr_identity(self):
        repository={'id':1319052603,'full_name':'noah-l-frank/overte'}
        binding={'pull_request':17,'base_ref':'main','head_ref':'fix/main/example','base_sha':'a'*40,'head_sha':'b'*40}
        event={'repository':repository,'number':17,'pull_request':{'number':17,
            'base':{'repo':repository,'ref':'main','sha':'a'*40},'head':{'repo':repository,'ref':'fix/main/example','sha':'b'*40}}}
        self.producer._event_binding(event,binding)
        for side,key,value in (('base','sha','7'*40),('head','sha','8'*40),('base','ref','apple-ios'),
                               ('head','repo',{'id':1,'full_name':'contributor/fork'})):
            changed=deepcopy(event);changed['pull_request'][side][key]=value
            with self.subTest(side=side,key=key),self.assertRaises(H.Unavailable):self.producer._event_binding(changed,binding)
        event['pull_request']['number']=18
        with self.assertRaises(H.Unavailable):self.producer._event_binding(event,binding)

    def test_disabled_descriptor_uses_no_api_and_no_cli_flag_can_enable_production(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'native-output';output.touch(mode=0o600)
            with (patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}),
                  patch.object(self.producer,'PRODUCTION_READY',False),
                  patch.object(self.producer.producer_api,'Adapter',side_effect=AssertionError('no API'))):
                self.assertEqual(self.producer.main(['descriptor','--candidate',temporary]),0)
                self.assertEqual(output.read_text(),'protected_full=false\n')
                for role in ('shared','publish'):
                    with self.assertRaises(H.Unavailable):self.producer.main([role,'--candidate',temporary])

    def production_policy(self,root):
        for name in (sandbox.POLICY,self.producer.attested.POLICY):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((H.ROOT/name).read_bytes())
        path=root/self.producer.attested.POLICY
        policy=json.loads(path.read_text())
        policy['enabled']=True
        policy['flags'].update(git_process_overrides='maintenance-disabled-safe-work',LC_ALL='C.UTF-8')
        path.write_text(json.dumps(policy))

    def test_protected_policy_admission_precedes_descriptor_setup_and_native_api(self):
        p=self.producer
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.production_policy(root)
            output=root/'output';output.touch()
            with (patch.object(p,'ROOT',root),patch.object(p,'PRODUCTION_READY',True),
                  patch.object(sandbox,'ACTIVATION_READY',True),patch.object(p.attested,'ISOLATED_ADMISSION_READY',True),
                  patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)},clear=True),
                  patch.object(p.producer_api,'Adapter',side_effect=AssertionError('no API before admission')),
                  patch.object(p.shared,'prepared_tools',side_effect=AssertionError('no setup before admission'))):
                p.protected_admission()
                for field,value in (('enabled',False),('git_process_overrides','maintenance-disabled'),('LC_ALL','')):
                    self.production_policy(root)
                    path=root/p.attested.POLICY;policy=json.loads(path.read_text())
                    (policy if field=='enabled' else policy['flags'])[field]=value
                    path.write_text(json.dumps(policy));output.write_text('')
                    with self.subTest(field=field):
                        self.assertEqual(p.main(['descriptor','--candidate',temporary]),0)
                        self.assertEqual(output.read_text(),'protected_full=false\n')
                        with self.assertRaises(p.PreExecutionUnavailable):p.shared_execution(root,{},os.environ,None)
                self.production_policy(root)
                for module,name in ((p,'PRODUCTION_READY'),(sandbox,'ACTIVATION_READY'),(p.attested,'ISOLATED_ADMISSION_READY')):
                    with self.subTest(name=name),patch.object(module,name,False),self.assertRaises(p.PreExecutionUnavailable):
                        p.protected_admission()

    def test_enabled_source_capabilities_cannot_admit_foreign_native_invocation(self):
        p=self.producer
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.production_policy(root)
            candidate=root/'candidate';candidate.mkdir()
            event=root/'event.json';event.write_text(json.dumps({'pull_request':{'head':{'repo':{'id':1319052603}}}}))
            environment={**context(),'GITHUB_EVENT_PATH':str(event),'GITHUB_WORKSPACE':str(root),
                'GITHUB_EVENT_NAME':'pull_request','GITHUB_BASE_REF':'main','GITHUB_HEAD_REF':'fix/main/example',
                'GITHUB_REF':'refs/pull/17/merge','GITHUB_REPOSITORY':'overte-org/overte',
                'GITHUB_WORKFLOW_REF':'noah-l-frank/overte/.github/workflows/repository-checks.yml@refs/pull/17/merge'}
            with (patch.object(p,'ROOT',root),patch.object(p,'PRODUCTION_READY',True),
                  patch.object(sandbox,'ACTIVATION_READY',True),patch.object(p.attested,'ISOLATED_ADMISSION_READY',True),
                  patch.dict(os.environ,environment,clear=True),patch.object(p.producer_api,'Adapter',return_value=SimpleNamespace(
                      current=lambda *_:self.fail('foreign context reached native API'))),
                  patch.object(p,'_host_policy',side_effect=AssertionError('no candidate reader')),
                  self.assertRaises(H.Unavailable)):
                p.main(['descriptor','--candidate',str(candidate)])

    def test_receipt_timestamp_uses_whole_utc_seconds_without_renewing_time(self):
        from datetime import datetime,timezone
        self.assertEqual(self.producer.utc_seconds(datetime(2026,10,16,10,11,12,999999,tzinfo=timezone.utc)),
                         '2026-10-16T10:11:12Z')

    def api_fixture(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('protected_native_api_fixture',Path(__file__).with_name('producer-api-test.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        case=module.AdapterTests();case.setUp()
        case.runs[100].update(status='in_progress',conclusion=None)
        for job in case.jobs[100]:
            if job['name']==self.producer.SHARED_JOB:job.update(status='in_progress',conclusion=None,completed_at=None)
        context={'run_id':100,'binding':case.binding,'policy':case.policy}
        return case,context

    def test_actual_readonly_adapter_binds_active_native_owner_and_first_attempt(self):
        case,context=self.api_fixture()
        observed=self.producer.current_run(context,case.adapter,'shared')
        self.assertEqual(observed.owners['shared-host'].job_id,120)
        self.assertIsNone(observed.final_publisher)
        self.assertEqual(observed.publisher.conclusion,'success')
        self.assertTrue(case.api.calls)
        for mutation in ('attempt','source','duplicate','head','missing','app'):
            case,context=self.api_fixture()
            if mutation=='attempt':case.runs[100]['run_attempt']=2
            elif mutation=='source':case.runs[100]['referenced_workflows'][0]['sha']='7'*40
            elif mutation=='duplicate':case.jobs[100].append(deepcopy(case.jobs[100][1]))
            elif mutation=='head':case.runs[100]['head_sha']='7'*40
            elif mutation=='missing':case.jobs[100]=[job for job in case.jobs[100] if job['name']!=self.producer.SHARED_JOB]
            else:
                old=case.api.mutate
                case.api.mutate=lambda endpoint,value: {**value,'app':{'id':1}} if '/check-runs/' in endpoint else old(endpoint,value)
            with self.subTest(mutation=mutation),self.assertRaises((H.Unavailable,self.producer.protocol.ProtocolError)):
                self.producer.current_run(context,case.adapter,'shared')

    def test_final_builder_matches_independent_protocol_and_rejects_failed_or_altered_receipts(self):
        from dataclasses import replace
        from datetime import datetime,timezone
        import importlib.util
        spec=importlib.util.spec_from_file_location('protected_protocol_fixture',Path(__file__).with_name('producer-test.py'))
        fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
        p=self.producer
        def fixture():
            case=fixtures.MaterializedGitContextTests().fixture()
            run=replace(case.run,status='in_progress',conclusion=None,final_publisher=replace(case.run.final_publisher,
                job=replace(case.run.final_publisher.job,status='in_progress',conclusion=None,completed_at=None)))
            context={'binding':case.binding,'plan':case.plan,'registry':case.registry,'git_context':case.context.git_context,
                'candidate':Path('/unexecuted-fixture'),'policy':SimpleNamespace(producer=case.policy)}
            return case,run,context
        case,run,context=fixture()
        now=datetime(2026,10,15,10,4,tzinfo=timezone.utc)
        with (patch.object(p.inputs,'full_tree',return_value=case.tree),
              patch.object(p.attested,'validate_environment') as admit):
            value=p.publication(context,case.descriptor,case.receipt,run,now,'2026-10-16T10:00:00Z')
        self.assertEqual(admit.call_args.args[0],case.environment)
        self.assertTrue(case.verify(value)['verified'])
        self.assertEqual(value['results']['shared-host']['receipt'],case.receipt)
        for mutation in ('legacy','failure','cancelled','hash','context','missing','source'):
            case,run,context=fixture()
            if mutation=='legacy':case.receipt['schema']=1;del case.receipt['git_context']
            elif mutation in {'failure','cancelled'}:
                run=replace(run,owners={'shared-host':replace(run.owners['shared-host'],conclusion=mutation)})
            elif mutation=='hash':run=replace(run,final_publisher=replace(run.final_publisher,receipt_sha256='0'*64))
            elif mutation=='context':context['git_context']={**context['git_context'],'shallow':[]}
            elif mutation=='missing':run=replace(run,owners={})
            else:case.receipt['candidate_commit']='7'*40
            with (self.subTest(mutation=mutation),patch.object(p.inputs,'full_tree',return_value=case.tree),
                  patch.object(p.attested,'validate_environment'),self.assertRaises((H.Unavailable,p.execution.ExecutionError))):
                p.publication(context,case.descriptor,case.receipt,run,now,'2026-10-16T10:00:00Z')

    def test_prospective_template_retains_quick_path_and_has_one_protected_owner(self):
        import yaml
        p=self.producer
        old=yaml.safe_load((H.ROOT/'tools/repository-checks/workflows/host/project-tests.yml').read_text())
        new=yaml.safe_load((H.ROOT/p.TEMPLATE).read_text())
        self.assertEqual(set(new['jobs']),set(old['jobs'])|{'producer-publication'})
        for name in ('tool-dependencies','package-checks','project-results'):
            expected=deepcopy(old['jobs'][name])
            for step in expected['steps']:
                if step.get('with',{}).get('path')=='trusted':
                    step['with']['sparse-checkout-cone-mode']=False
                    step['with']['sparse-checkout']=step['with']['sparse-checkout'].replace(
                        'tools/sbom\n','tools/sbom\ntools/branch-policy/check.py\ntools/native-tests/check.py\n')
                if 'run' in step:
                    step['run']=step['run'].replace('python3 trusted/tools/repository-checks/',
                        'python3 -B trusted/tools/repository-checks/')
            self.assertEqual(new['jobs'][name],expected)
        steps={row['name']:row for row in new['jobs']['project-tests']['steps']}
        original=deepcopy(steps['Install QML and portable C++ contract prerequisites'])
        original['run']=original['run'].replace('  cmake ninja-build \\\n','')
        original['run']=original['run'].split('for tool in bash cmake ctest',1)[0]
        self.assertEqual(original,next(row for row in old['jobs']['project-tests']['steps']
            if row['name']=='Install QML and portable C++ contract prerequisites'))
        self.assertEqual(steps['Run independently selected host contracts']['if'],"steps.protected.outputs.protected_executed != 'true'")
        root=steps['Execute the selected protected shared owner']
        self.assertEqual(root['if'],"needs.route.outputs.protected_full == 'true' && steps.protected-source.outputs.admitted == 'true'")
        for required in ('--wait --pipe','--property=Delegate=yes','--property=KillMode=control-group',
                         '/usr/bin/env -i','producer_workflow.py" shared'):
            self.assertIn(required,root['run'])
        self.assertEqual(new['jobs']['producer-publication']['name'],
            'Publish final producer ${{ needs.project-tests.outputs.receipt_sha256 }}')
        active=(H.ROOT/'.github/workflows/project-tests.yml').read_bytes()
        packages=p._host_policy().package_policy()
        generation=packages.validate_wiring(H.ROOT)
        installed={'protected-producer-metadata-ci-v1','protected-producer-seven-target-ci-v1'}
        canonical=(H.ROOT/p.TEMPLATE).read_bytes()
        identity=hashlib.sha1(b'blob '+str(len(canonical)).encode()+b'\0'+canonical).hexdigest()
        approved=[row for row in packages.workflow_generations() if row['name'] in installed
                  and row['workflows']['.github/workflows/project-tests.yml']['sha']==identity]
        self.assertTrue(approved,'canonical producer must belong to an exact complete reviewed generation')
        self.assertTrue(all(set(row['workflows'])==set(packages.METADATA_WORKFLOW_PATHS) for row in approved))
        if active==canonical:
            self.assertIn(generation,{row['name'] for row in approved})
        else:
            self.assertNotEqual(active,canonical)

class SharedHostPreparedExternalInputsTests(unittest.TestCase):
    """Real temporary aliases and bytes with fake protected-root ownership."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.java = self.base / 'jdk'
        self.venv = self.base / 'venv'
        self.target = self.base / 'etc/ssl/certs/adoptium/cacerts'
        self.alias = self.java / 'lib/security/cacerts'
        self.venv.mkdir()
        self.alias.parent.mkdir(parents=True)
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'fixed fake certificate-store bytes')
        self.alias.symlink_to(self.target)
        self.prepared = ((), self.base / 'python', self.base / 'node', self.java)
        self.foreign = set()
        original = Path.lstat
        def protected(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == self.base or self.base in path.parents or path in self.base.parents:
                values = list(info)
                values[4] = 1001 if path in self.foreign else 0
                values[5] = 0
                if path in self.base.parents:
                    values[0] &= ~0o022
                return os.stat_result(values)
            return info
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(Path, 'lstat', protected))
        self.patches.enter_context(patch.object(SHARED, 'VENV', self.venv))
        self.patches.enter_context(patch.object(SHARED, '_TEMURIN17_HOME', self.java))
        self.patches.enter_context(patch.object(SHARED, '_TEMURIN17_CACERTS', self.target))

    def identity(self):
        return SHARED.prepared_identity((self.java,), external_inputs=SHARED.prepared_external_inputs(self.prepared))

    def freeze_parent(self, *, unsafe_ancestor=False):
        original = os.fstat
        target = self.java.parent.stat()
        def protected(descriptor):
            info = original(descriptor)
            values = list(info)
            is_target = (info.st_dev, info.st_ino) == (target.st_dev, target.st_ino)
            values[4] = 1001 if is_target and self.base in self.foreign else 0
            if not is_target:
                values[0] &= ~0o022
                if unsafe_ancestor:
                    values[0] |= 0o022
            return os.stat_result(values)
        with patch.object(SHARED.os, 'geteuid', return_value=0), patch.object(SHARED.os, 'fstat', protected):
            SHARED.freeze_prepared_java_parent(self.java)

    def test_fixed_java_parent_is_frozen_before_certificate_admission(self):
        # The actual hosted-image builder applies chmod -R 777 /usr/lib/jvm.
        # Trusted provisioning has already frozen the selected JDK itself.
        self.base.chmod(0o777)
        before = self.java.stat()
        with self.assertRaisesRegex(H.Unavailable, 'parent is aliased or mutable'):
            SHARED.prepared_external_inputs(self.prepared)
        self.freeze_parent()
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o755)
        self.assertEqual(self.java.stat(), before)
        self.assertEqual(SHARED.prepared_external_inputs(self.prepared), (self.target,))

    def test_java_parent_freeze_changes_no_already_protected_directory(self):
        self.base.chmod(0o750)
        with patch.object(SHARED.os, 'fchmod') as chmod:
            self.freeze_parent()
        chmod.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o750)

    def test_java_parent_freeze_rejects_foreign_ownership_without_repair(self):
        self.base.chmod(0o777)
        self.foreign.add(self.base)
        with patch.object(SHARED.os, 'fchmod') as chmod, self.assertRaises(H.Unavailable):
            self.freeze_parent()
        chmod.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o777)

    def test_java_parent_freeze_rejects_nonroot_and_unfrozen_jdk(self):
        with patch.object(SHARED.os, 'geteuid', return_value=1001), \
                patch.object(SHARED.os, 'fchmod') as chmod, self.assertRaises(H.Unavailable):
            SHARED.freeze_prepared_java_parent(self.java)
        chmod.assert_not_called()
        self.java.chmod(0o777)
        with patch.object(SHARED.os, 'fchmod') as chmod, self.assertRaises(H.Unavailable):
            self.freeze_parent()
        chmod.assert_not_called()

    def test_unselected_or_absent_java_parent_is_never_opened_or_mutated(self):
        with patch.object(SHARED.os, 'open') as opened, patch.object(SHARED.os, 'fchmod') as chmod:
            SHARED.freeze_prepared_java_parent(None)
            SHARED.freeze_prepared_java_parent(self.base / 'other-jdk')
        opened.assert_not_called()
        chmod.assert_not_called()

    def test_java_parent_freeze_rejects_mutable_ancestors_without_repair(self):
        self.base.chmod(0o777)
        with patch.object(SHARED.os, 'fchmod') as chmod, self.assertRaises(H.Unavailable):
            self.freeze_parent(unsafe_ancestor=True)
        chmod.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o777)

    def test_java_parent_freeze_rejects_an_aliased_parent_without_repair(self):
        actual = self.base / 'actual-parent'
        (actual / 'jdk').mkdir(parents=True)
        alias = self.base / 'parent-alias'
        alias.symlink_to(actual, target_is_directory=True)
        selected = alias / 'jdk'
        with patch.object(self, 'java', selected), patch.object(SHARED, '_TEMURIN17_HOME', selected), \
                patch.object(SHARED.os, 'fchmod') as chmod, self.assertRaises(H.Unavailable):
            self.freeze_parent()
        chmod.assert_not_called()

    def test_java_parent_replacement_is_rejected_before_and_after_mode_change(self):
        original_stat, original_chmod = os.stat, os.fchmod
        for phase in ('before', 'after'):
            self.base.chmod(0o777)
            reads = []
            def replaced(path, *args, **kwargs):
                info = original_stat(path, *args, **kwargs)
                if kwargs.get('dir_fd') is not None and path == self.base.name:
                    reads.append(path)
                    if phase == 'before' or len(reads) == 2:
                        values = list(info)
                        values[1] += 1
                        return os.stat_result(values)
                return info
            with self.subTest(phase=phase), patch.object(SHARED.os, 'stat', replaced), \
                    patch.object(SHARED.os, 'fchmod', wraps=original_chmod) as chmod, \
                    self.assertRaisesRegex(H.Unavailable, 'parent changed'):
                self.freeze_parent()
            self.assertEqual(chmod.call_count, 0 if phase == 'before' else 1)

    def test_generic_identity_still_rejects_external_java_alias(self):
        with self.assertRaisesRegex(H.Unavailable, 'prepared tool alias escapes readonly mounts'):
            SHARED.prepared_identity((self.java,))

    def test_exact_reference_adds_the_certificate_identity_only_with_explicit_admission(self):
        self.assertEqual(SHARED.prepared_external_inputs(self.prepared), (self.target,))
        observed = self.identity()
        self.assertEqual(set(observed), {str(self.venv), str(self.java), str(self.target)})
        self.assertTrue(all(value.startswith('sha256:') for value in observed.values()))
        before = deepcopy(observed)
        self.target.write_bytes(b'changed fake certificate-store bytes')
        changed = self.identity()
        self.assertNotEqual(changed[str(self.target)], before[str(self.target)])
        self.assertEqual(changed[str(self.java)], before[str(self.java)])
        self.target.chmod(0o444)
        self.assertNotEqual(self.identity()[str(self.target)], changed[str(self.target)])

    def test_direct_call_cannot_forge_an_unbound_or_arbitrary_external_input(self):
        for selected in ([self.target], (self.target, self.target), (self.base / 'other',)):
            with self.subTest(selected=selected), self.assertRaises(H.Unavailable):
                SHARED.prepared_identity((self.java,), external_inputs=selected)
        with self.assertRaises(H.Unavailable):
            SHARED.prepared_identity((), external_inputs=(self.target,))
        unknown = self.java / 'lib/security/unknown'
        unknown.symlink_to(self.target)
        with self.assertRaisesRegex(H.Unavailable, 'prepared tool alias escapes readonly mounts'):
            self.identity()

    def test_other_alias_target_is_rejected_even_with_a_forged_fixed_tuple(self):
        other = self.base / 'other-store'
        other.write_bytes(b'other')
        self.alias.unlink()
        self.alias.symlink_to(other)
        self.assertEqual(SHARED.prepared_external_inputs(self.prepared), ())
        with self.assertRaises(H.Unavailable):self.identity()
        with self.assertRaises(H.Unavailable):
            SHARED.prepared_identity((self.java,), external_inputs=(self.target,))

    def test_mutable_or_foreign_leaf_alias_or_parent_is_rejected(self):
        for path in (self.target, self.target.parent, self.alias.parent):
            with self.subTest(path=path, change='mode'):
                original = path.stat().st_mode
                path.chmod(0o666 if path == self.target else 0o775)
                try:
                    with self.assertRaises(H.Unavailable):self.identity()
                finally:path.chmod(original)
        for path in (self.target, self.alias, self.target.parent, self.alias.parent):
            with self.subTest(path=path, change='owner'):
                self.foreign.add(path)
                try:
                    with self.assertRaises(H.Unavailable):self.identity()
                finally:self.foreign.remove(path)

    def test_symlink_or_directory_certificate_leaf_is_rejected(self):
        self.target.unlink()
        other = self.base / 'other-store'
        other.write_bytes(b'other')
        self.target.symlink_to(other)
        with self.assertRaises(H.Unavailable):self.identity()
        self.target.unlink()
        self.target.mkdir()
        with self.assertRaises(H.Unavailable):self.identity()

    def test_certificate_modes_cannot_grant_write_execute_or_special_permissions(self):
        for mode in (0o664, 0o600, 0o755, 0o4755):
            with self.subTest(mode=oct(mode)):
                self.target.chmod(mode)
                with self.assertRaises(H.Unavailable):self.identity()

    def test_aliased_parent_and_oversized_or_empty_leaf_are_rejected(self):
        for size in (0, SHARED._CACERTS_MAX_BYTES + 1):
            with self.subTest(size=size):
                with self.target.open('wb') as output:output.truncate(size)
                with self.assertRaises(H.Unavailable):self.identity()
        self.target.write_bytes(b'bounded')
        parent = self.target.parent
        moved = parent.with_name('moved-store')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(H.Unavailable):self.identity()

    def test_no_java_or_unreferenced_leaf_adds_no_external_identity_or_mount(self):
        no_java = (*self.prepared[:3], None)
        self.assertEqual(SHARED.prepared_external_inputs(no_java), ())
        self.target.chmod(0o666)
        self.assertEqual(set(SHARED.prepared_identity(())), {str(self.venv)})
        with patch.object(SHARED.sandbox, 'build_plan', return_value={'argv': ['bwrap', '--', 'fixed']}):
            no_java_plan = SHARED.shared_plan(None, ['python', 'fixture.py'], no_java, {})
        self.assertNotIn(str(self.target), no_java_plan['argv'])
        self.target.chmod(0o644)
        self.alias.unlink()
        self.alias.write_bytes(b'ordinary bundled store')
        self.assertEqual(SHARED.prepared_external_inputs(self.prepared), ())
        self.assertNotIn(str(self.target), self.identity())

    def test_plan_binds_only_the_exact_referenced_readonly_leaf(self):
        with patch.object(SHARED.sandbox, 'build_plan', return_value={'argv': ['bwrap', '--', 'fixed']}):
            plan = SHARED.shared_plan(None, ['python', 'fixture.py'], self.prepared, {})
        args = plan['argv']
        mounts = [args[index + 1:index + 3] for index, value in enumerate(args) if value == '--ro-bind']
        self.assertEqual(mounts, [[str(self.target), str(self.target)]])
        self.assertNotIn('/etc', args)
        self.assertNotIn(str(self.target.parent), args)

    def test_protected_probe_requires_the_bound_leaf_mount_to_be_readonly(self):
        import sandbox_probe as probe
        binding = {'profile': SHARED.PROFILE, 'prepared': {str(self.target): 'fake-fixed-digest'}}
        paths = ('/usr', '/work', '/overte-policy', '/opt/overte-ci/venv', '/work/build')
        base_mounts = '\n'.join(f'1 0 0:1 / {path} {"rw" if path.endswith("/build") else "ro"} - tmpfs tmpfs rw' for path in paths)
        for flags in (None, 'rw', 'ro'):
            mounts = base_mounts + ('' if flags is None else f'\n1 0 0:1 / {self.target} {flags} - tmpfs tmpfs rw')
            with (self.subTest(flags=flags),
                  patch.object(probe.Path, 'read_bytes', return_value=json.dumps({'shared_host': binding}).encode()),
                  patch.object(probe.Path, 'read_text', return_value=mounts),
                  patch.object(probe.socket, 'if_nameindex', return_value=[(1, 'lo')]),
                  patch.object(probe.socket, 'socket'), patch.object(probe.fcntl, 'ioctl', return_value=b'\0' * 16 + b'\1\0'),
                  patch.object(probe, 'process_observation', return_value={}),
                  patch.object(probe.os, 'stat', return_value=SimpleNamespace(st_ino=123)),
                  patch.object(probe.runtime, 'capture_isolated_host_environment', return_value={'fake': 'not E proof'}) as capture):
                if flags == 'ro':
                    self.assertEqual(probe.measure_shared_host()['binding'], binding)
                    capture.assert_called_once_with(binding['prepared'])
                else:
                    with self.assertRaisesRegex(ValueError, 'not read-only'):probe.measure_shared_host()
                    capture.assert_not_called()

    def test_parent_probe_validation_rejects_missing_or_writable_bound_leaf(self):
        binding = {'prepared': {str(self.target): 'fake-fixed-digest'}, 'outside_namespaces': {'user': 1}}
        environment = {'schema': SHARED.inputs.ISOLATED_FULL_SCHEMA, 'profile': SHARED.inputs.ISOLATED_FULL_PROFILE,
            'prepared': {'roots': binding['prepared']},
            'python': {'version': '3.12.15'}, 'tools': {'node': {'version': 'v22.20.0'}},
            'system_packages': {'fake': True}, 'trusted_execution': {'fake': True},
            'qt': {'modules': dict.fromkeys(SHARED.runtime._QT_MODULES)},
            'glm': {'header_digest': 'fake', 'configuration_digest': 'fake'},
            'flags': {'git_process_overrides': 'maintenance-disabled-safe-work'}}
        mounts = {name: ['ro'] for name in ('/usr', '/work', '/overte-policy', str(self.venv))}
        mounts['/work/build'] = ['rw']
        status = {'NoNewPrivs': '1', 'Uid': '2001 2001 2001 2001', 'Gid': '2001 2001 2001 2001',
                  **dict.fromkeys(('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'), '0000000000000000')}
        result = {'exit_code': 0, 'reason': None, 'cleanup': {'kernel_populated': 0, 'subtree_kill': True},
            'observation': {'schema': 1, 'authority': 'none', 'measurement': SHARED.PROFILE, 'binding': binding,
                'environment': environment, 'process': {'status': status}, 'mounts': mounts,
                'namespaces': {'user': 2}, 'reusable': False}}
        for flags in (None, ['rw'], ['ro']):
            changed = deepcopy(result)
            if flags is not None:changed['observation']['mounts'][str(self.target)] = flags
            with self.subTest(flags=flags), patch.object(SHARED.inputs, '_environment', return_value=environment) as admission:
                if flags == ['ro']:
                    self.assertEqual(SHARED.validate_probe(changed, binding, 2001, 2001), environment)
                    admission.assert_called_once_with(environment)
                else:
                    with self.assertRaisesRegex(H.Unavailable, 'mount protection is incomplete'):
                        SHARED.validate_probe(changed, binding, 2001, 2001)
                    admission.assert_not_called()
        changed = deepcopy(result)
        changed['observation']['mounts'][str(self.target)] = ['ro']
        changed['observation']['environment']['prepared']['roots'] = {'different': 'fake-digest'}
        with (patch.object(SHARED.inputs, '_environment', return_value=changed['observation']['environment']),
              self.assertRaisesRegex(H.Unavailable, 'environment is incomplete')):
            SHARED.validate_probe(changed, binding, 2001, 2001)



class ProtectedSuitePairTests(unittest.TestCase):
    """Offline process-control fixtures, not cgroup/native qualification."""

    def pair_fixture(self, folder, modes=('normal', 'normal'), fail_attach=None):
        import signal
        real_popen = subprocess.Popen
        folder = Path(folder)
        script = folder / 'bootstrap.py'
        script.write_text(
            "import json,os,signal,sys,time\nfrom pathlib import Path\n"
            "gate=int(sys.argv[2]); value=json.loads(Path(sys.argv[3]).read_text())\n"
            "assert os.read(gate,1)==b'1'; os.close(gate)\n"
            "root=Path(value['root']); slot=value['slot']\n"
            "(root/('ready-'+str(slot))).write_text('ready')\n"
            "end=time.monotonic()+3\n"
            "while not (root/('ready-'+str(1-slot))).exists():\n"
            " if time.monotonic()>end: raise RuntimeError('other owner never launched')\n"
            " time.sleep(.01)\n"
            "mode=value['mode']\n"
            "if mode=='output': print('x'*1000001,flush=True)\n"
            "elif mode=='cancel': os.kill(value['parent'],signal.SIGUSR1); time.sleep(60)\n"
            "elif mode=='block': time.sleep(60)\n"
            "else: print('owner-'+str(slot),flush=True)\n")
        events, processes, plans = [], [], []
        class Scope:
            def __init__(self, slot):
                self.path=folder/('scope-'+str(slot));self.slot=slot;self.process=None;self.kills=0
            def attach(self, process):
                self.process=process
                # A child cannot pass its release pipe before authenticated attach.
                if (folder/('ready-'+str(self.slot))).exists():
                    raise AssertionError('workload ran before scope attachment')
                events.append(('attach',self.slot))
                if self.slot==fail_attach:
                    raise H.Unavailable('fixture attachment denied')
            def kill_and_wait(self):
                self.kills+=1
                if self.process is not None and self.process.poll() is None:
                    try: os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                return {'kernel_populated':0,'subtree_kill':True}
        scopes=[Scope(0),Scope(1)]
        for slot,mode in enumerate(modes):
            plan=folder/('plan-'+str(slot)+'.json')
            plan.write_text(json.dumps({'root':str(folder),'slot':slot,'mode':mode,'parent':os.getpid()}))
            plans.append((scopes[slot],plan))
        def popen(argv,**kwargs):
            self.assertEqual(kwargs['user'],1234)
            self.assertEqual(kwargs['group'],1234)
            self.assertEqual(kwargs['extra_groups'],())
            self.assertTrue(kwargs['close_fds'])
            self.assertTrue(kwargs['start_new_session'])
            self.assertEqual(len(kwargs['pass_fds']),1)
            self.assertEqual(argv[-1],'suite')
            # Only the offline unit fixture removes credential switching.
            # Production arguments, fixed bootstrap role and attach order are
            # asserted above; this mock is not kernel ownership evidence.
            kwargs.pop('user');kwargs.pop('group');kwargs.pop('extra_groups')
            process=real_popen(argv,**kwargs);processes.append(process);return process
        return script,scopes,plans,events,processes,popen

    @unittest.skipUnless(sys.platform=='linux','Linux suite process control')
    def test_two_real_gated_processes_overlap_before_either_can_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            script,scopes,plans,events,processes,popen=self.pair_fixture(folder)
            with patch.object(H,'public_bootstrap',return_value=script),patch.object(H.subprocess,'Popen',side_effect=popen):
                results=H.supervise_pair(plans,1234,1234,timeout=5,cancelled=[])
            self.assertEqual(events,[('attach',0),('attach',1)])
            self.assertEqual([r['exit_code'] for r in results],[0,0])
            self.assertEqual([r['reason'] for r in results],[None,None])
            self.assertIn(b'owner-0',results[0]['diagnostic'])
            self.assertIn(b'owner-1',results[1]['diagnostic'])
            self.assertTrue(all(scope.kills>=2 for scope in scopes))
            self.assertTrue(all(process.poll() is not None for process in processes))

    @unittest.skipUnless(sys.platform=='linux','Linux suite process control')
    def test_second_owner_attachment_failure_cleans_both_started_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            script,scopes,plans,events,processes,popen=self.pair_fixture(folder,fail_attach=1)
            with patch.object(H,'public_bootstrap',return_value=script),patch.object(H.subprocess,'Popen',side_effect=popen):
                with self.assertRaisesRegex(H.Unavailable,'attachment denied'):
                    H.supervise_pair(plans,1234,1234,timeout=5,cancelled=[])
            self.assertEqual(len(processes),2)
            self.assertEqual(events,[('attach',0),('attach',1)])
            self.assertFalse((Path(folder)/'ready-1').exists())
            self.assertTrue(all(scope.kills for scope in scopes))
            self.assertTrue(all(process.poll() is not None for process in processes))

    @unittest.skipUnless(sys.platform=='linux','Linux suite process control')
    def test_one_timeout_keeps_the_other_actual_success_and_cleans_both(self):
        with tempfile.TemporaryDirectory() as folder:
            script,scopes,plans,events,processes,popen=self.pair_fixture(folder,('block','normal'))
            with patch.object(H,'public_bootstrap',return_value=script),patch.object(H.subprocess,'Popen',side_effect=popen):
                results=H.supervise_pair(plans,1234,1234,timeout=1,cancelled=[])
            self.assertEqual(results[0]['reason'],'timeout')
            self.assertNotEqual(results[0]['exit_code'],0)
            self.assertEqual(results[1]['reason'],None)
            self.assertEqual(results[1]['exit_code'],0)
            self.assertTrue(all(scope.kills for scope in scopes))
            self.assertTrue(all(process.poll() is not None for process in processes))

    @unittest.skipUnless(sys.platform=='linux','Linux suite process control')
    def test_pair_cancellation_and_output_overflow_never_mask_work_or_cleanup(self):
        import signal
        for modes,overflow in ((('cancel','block'),False),(('output','block'),True)):
            with self.subTest(modes=modes),tempfile.TemporaryDirectory() as folder:
                script,scopes,plans,events,processes,popen=self.pair_fixture(folder,modes)
                cancelled=[]
                old=signal.signal(signal.SIGUSR1,lambda *_:cancelled.append(signal.SIGTERM))
                try:
                    with patch.object(H,'public_bootstrap',return_value=script),patch.object(H.subprocess,'Popen',side_effect=popen):
                        if overflow:
                            with self.assertRaisesRegex(H.Unavailable,'output exceeded'):
                                H.supervise_pair(plans,1234,1234,timeout=5,cancelled=cancelled)
                        else:
                            results=H.supervise_pair(plans,1234,1234,timeout=5,cancelled=cancelled)
                            self.assertEqual([r['reason'] for r in results],['cancelled','cancelled'])
                finally:
                    signal.signal(signal.SIGUSR1,old)
                self.assertTrue(all(scope.kills for scope in scopes))
                self.assertTrue(all(process.poll() is not None for process in processes))

    def test_fixed_pair_keeps_registry_junit_order_commands_and_either_failure(self):
        runner=SHARED.execution._runner()
        from unittest.mock import Mock
        for failed_slot in (None,0,1):
            with self.subTest(failed_slot=failed_slot),tempfile.TemporaryDirectory() as folder:
                serial=[]
                suites=[runner.Suite('test-evidence','quick',('python','tools/test-evidence/test.py')),
                        runner.Suite('middle','quick',('python','private-fixture.py')),
                        runner.Suite('host-selection','quick',('python','tests/host-selection-test.py'))]
                def serial_run(args,items,cancelled,result_callback):
                    self.assertIsNone(args.junit);self.assertFalse(args.fail_fast)
                    self.assertEqual(args.timeout,240);self.assertEqual(args.host_timeout,900)
                    serial.extend(x.name for x in items)
                    for item in items:result_callback(dict(name=item.name,status='passed',message='',output='actual',time=.1))
                    return 0
                values=[{'exit_code':1 if slot==failed_slot else 0,'reason':None,'diagnostic':b'actual output',
                         'duration':.5+slot,'cleanup':{'kernel_populated':0,'subtree_kill':True}} for slot in (0,1)]
                batch=SimpleNamespace(run_pair=Mock(return_value=values))
                controller=SimpleNamespace(run_suites=serial_run,write_junit=runner.write_junit)
                report=Path(folder)/'results.xml'
                code,observed=SHARED._run_pair_suites(controller,batch,suites,[],report)
                batch.run_pair.assert_called_once_with([list(suites[0].command),list(suites[2].command)],240,[])
                self.assertEqual(serial,['middle'])
                self.assertEqual([x['name'] for x in observed],[x.name for x in suites])
                self.assertEqual(code,0 if failed_slot is None else 1)
                import xml.etree.ElementTree as ET
                tree=ET.parse(report).getroot()
                self.assertEqual([x.get('name') for x in tree.findall('testcase')],[x.name for x in suites])
                self.assertEqual(tree.get('tests'),'3');self.assertEqual(tree.get('skipped'),'0')
                self.assertEqual(tree.get('failures'),'0' if failed_slot is None else '1')
                suites[0]=runner.Suite('test-evidence','quick',('python','wrong-fixture.py'))
                batch.run_pair.reset_mock()
                with self.assertRaises(H.Unavailable):
                    SHARED._run_pair_suites(controller,batch,suites,[],report)
                batch.run_pair.assert_not_called()



class ProtectedPairScopeCleanupTests(unittest.TestCase):
    """Actual Batch contexts with offline kernel/guardian error fixtures."""

    def fixture(self, folder, *, primary_stage=None, primary=None, failures=None):
        failures = {} if failures is None else failures
        base = Path(folder)
        batch = SHARED.Batch(base, base/'candidate', base/'policy', {}, {},
            {'fixture':'cleanup-only'}, ((), None, None, None), base/'delegated', 1234, 1234, {})
        events, scopes = [], []
        class TrackedScopes(list):
            def remove(self, scope):
                events.append(('remove', scope.slot))
                super().remove(scope)
        batch.scopes = TrackedScopes()
        def record(operation, slot):
            events.append((operation, slot))
            if (operation, slot) in failures:
                raise failures[(operation, slot)]
        class Scope:
            def __init__(self):
                self.slot = len(scopes)
                self.path = base/('scope-'+str(self.slot))
                scopes.append(self)
            def populated(self): return 0
            def kill_and_wait(self):
                record('kill', self.slot)
                return {'kernel_populated':0,'subtree_kill':True}
            def close(self): record('close', self.slot)
        def scope(uid, gid, delegated):
            self.assertEqual((uid, gid, delegated), (1234, 1234, base/'delegated'))
            return Scope()
        class Guardian:
            def __init__(self, owner, protected, binding, lifetime):
                self.owner = owner
                events.append(('guardian-init', owner.slot))
                if primary_stage=='guardian-init' and owner.slot==1:
                    raise primary
            def finish(self):
                events.append(('guardian-finish', self.owner.slot))
                if primary_stage=='guardian-finish' and self.owner.slot==0:
                    raise primary
                return {'fixture':'protected-parent-result-only'}
            def close(self): record('guardian-close', self.owner.slot)
        def supervise(*args, **kwargs):
            events.append(('supervise', -1))
            if primary_stage=='supervise':
                raise primary
            return [{'exit_code':0,'reason':None,'diagnostic':b'unit fixture',
                     'duration':.1,'cleanup':{'kernel_populated':0,'subtree_kill':True}} for _ in range(2)]
        patches = ExitStack()
        patches.enter_context(patch.object(SHARED.os, 'chown'))
        patches.enter_context(patch.object(SHARED, 'shared_plan', return_value={'argv':['unit-fixture']}))
        patches.enter_context(patch.object(SHARED.host, 'OwnedScope', side_effect=scope))
        patches.enter_context(patch.object(SHARED.host, 'Guardian', side_effect=Guardian))
        patches.enter_context(patch.object(SHARED.host, 'supervise_pair', side_effect=supervise))
        return batch, events, scopes, patches

    def test_actual_batch_context_cleans_both_scopes_and_preserves_primary_failure(self):
        for stage in ('supervise','guardian-finish','guardian-init'):
            for operation in ('guardian-close','kill','close'):
                with self.subTest(stage=stage, operation=operation), tempfile.TemporaryDirectory() as folder:
                    primary = H.Unavailable('fixed primary pair fixture failure')
                    failures = {(operation, slot): H.Unavailable('later cleanup fixture failure')
                                for slot in (0, 1)}
                    batch, events, scopes, patches = self.fixture(folder,
                        primary_stage=stage, primary=primary, failures=failures)
                    with patches, self.assertRaises(H.Unavailable) as caught:
                        batch.run_pair([['python','first.py'],['python','second.py']], 240, [])
                    self.assertIs(caught.exception, primary)
                    self.assertEqual(len(scopes), 2)
                    self.assertEqual(batch.scopes, [])
                    self.assertFalse(list(Path(folder).glob('suite-*')))
                    for slot in (0, 1):
                        self.assertIn(('kill', slot), events)
                        self.assertIn(('close', slot), events)
                        self.assertIn(('remove', slot), events)
                        if not (stage=='guardian-init' and slot==1):
                            self.assertIn(('guardian-close', slot), events)
                    if stage=='guardian-init':
                        self.assertNotIn(('supervise', -1), events)

    def test_successful_pair_body_rethrows_first_cleanup_failure_after_all_attempts(self):
        operations=('guardian-close','kill','close')
        for first_operation in operations:
            with self.subTest(first=first_operation), tempfile.TemporaryDirectory() as folder:
                first = H.Unavailable('fixed first cleanup fixture failure')
                index = operations.index(first_operation)
                failures = {(operation, slot): H.Unavailable('later cleanup fixture failure')
                            for slot in (0, 1) for operation in operations[index:]}
                # ExitStack unwinds the second scope first. Every later error,
                # including the first scope's cleanup errors, must preserve it.
                failures[(first_operation, 1)] = first
                batch, events, scopes, patches = self.fixture(folder, failures=failures)
                with patches, self.assertRaises(H.Unavailable) as caught:
                    batch.run_pair([['python','first.py'],['python','second.py']], 240, [])
                self.assertIs(caught.exception, first)
                self.assertEqual(batch.scopes, [])
                self.assertFalse(list(Path(folder).glob('suite-*')))
                self.assertIn(('supervise', -1), events)
                self.assertEqual(len(batch.proofs), 2)
                for slot in (0, 1):
                    for operation in ('guardian-close','kill','close','remove'):
                        self.assertIn((operation, slot), events)

    def test_successful_pair_inside_unrelated_exception_handler_keeps_cleanup_failure(self):
        for operation in ('guardian-close','kill','close'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as folder:
                first = H.Unavailable('fixed cleanup failure inside unrelated handler')
                failures = {(operation, 1): first,
                            (operation, 0): H.Unavailable('later first-scope cleanup failure')}
                batch, events, scopes, patches = self.fixture(folder, failures=failures)
                try:
                    raise LookupError('unrelated already-handled caller exception')
                except LookupError as unrelated:
                    with patches, self.assertRaises(H.Unavailable) as caught:
                        batch.run_pair([['python','first.py'],['python','second.py']], 240, [])
                    self.assertIs(caught.exception, first)
                    self.assertIsNot(caught.exception, unrelated)
                self.assertEqual(batch.scopes, [])
                self.assertFalse(list(Path(folder).glob('suite-*')))
                self.assertEqual(len(batch.proofs), 2)
                for slot in (0, 1):
                    for cleanup in ('guardian-close','kill','close','remove'):
                        self.assertIn((cleanup, slot), events)



class PairBoundaryDiagnosticTests(unittest.TestCase):
    """Fixed observer/lease regressions; mocked kernel is never native proof."""

    def observer_fixture(self, folder, *, empty_slot=None, status=H.signal.SIGKILL, trigger="controller-eof", lease_failure_slot=None):
        events = []
        class Scope:
            def __init__(self, slot):
                self.slot, self.path = slot, Path(folder) / ("scope-" + str(slot))
                self.live = slot != empty_slot
            def populated(self):
                events.append(("kernel-live", self.slot))
                return int(self.live)
            def members(self):
                return {40 + self.slot} if self.live else set()
        scopes = [Scope(0), Scope(1)]
        class Guardian:
            def __init__(self, scope, protected, binding, *, lifetime):
                self.scope, self.binding = scope, binding
                self.identity = [9, 10 + scope.slot]
                events.append(("guardian-ready", scope.slot))
                self.closed_writer = False
            def relinquish_writer(self):
                self.closed_writer = True
                events.append(("lease-close", self.scope.slot))
                if self.scope.slot == lease_failure_slot:
                    raise H.Unavailable("fixed lease-close failure")
            def finish(self, expected):
                events.append(("proof", self.scope.slot, expected))
                if expected != trigger:
                    raise H.Unavailable("wrong fixed proof trigger")
                self.scope.live = False
                return {"trigger": trigger, "scope": self.identity, "binding": self.binding,
                        "cleanup": {"kernel_populated": 0, "subtree_kill": True}}
            def close(self):
                events.append(("cleanup", self.scope.slot))
                self.scope.live = False
        stack = ExitStack()
        stack.enter_context(patch.object(H.os, "geteuid", return_value=0))
        stack.enter_context(patch.object(H, "Guardian", Guardian))
        stack.enter_context(patch.object(H.os, "fork", side_effect=lambda: events.append("root-worker-fork") or 987))
        stack.enter_context(patch.object(H.select, "select", return_value=([123], [], [])))
        stack.enter_context(patch.object(H.os, "read", side_effect=lambda *_: events.append("ready-read") or b"1"))
        stack.enter_context(patch.object(H.os, "kill", side_effect=lambda pid, number: events.append(("signal", pid, number))))
        stack.enter_context(patch.object(H, "_wait_child", side_effect=lambda *args, **kwargs: events.append("worker-reaped") or status))
        return stack, scopes, events

    def test_two_actual_lease_closures_and_sigkill_status_precede_both_eof_proofs(self):
        with tempfile.TemporaryDirectory() as folder:
            stack, scopes, events = self.observer_fixture(folder)
            with stack:
                result = H.pair_boundary_case(scopes, [Path("/fixed-0"), Path("/fixed-1")],
                    Path(folder), {"attempt": 1}, 2001, 2001, case="controller-death", outside={})
            self.assertTrue(result["controller_sigkill_observed"])
            self.assertEqual(result["guardian_triggers"], ["controller-eof", "controller-eof"])
            self.assertTrue(result["kernel_scopes_empty"])
            self.assertLess(events.index(("guardian-ready", 1)), events.index("root-worker-fork"))
            for slot in (0, 1):
                self.assertLess(events.index(("lease-close", slot)), events.index("ready-read"))
                self.assertLess(events.index(("kernel-live", slot)), events.index(("signal", 987, H.signal.SIGKILL)))
                self.assertIn(("proof", slot, "controller-eof"), events)
                self.assertIn(("cleanup", slot), events)

    def test_either_missing_live_scope_wrong_death_or_deadline_proof_cannot_qualify(self):
        for empty_slot, status, trigger, lease_failure_slot in ((0, H.signal.SIGKILL, "controller-eof", None),
                (1, H.signal.SIGKILL, "controller-eof", None), (None, 0, "controller-eof", None),
                (None, H.signal.SIGKILL, "deadline", None), (None, H.signal.SIGKILL, "controller-eof", 0),
                (None, H.signal.SIGKILL, "controller-eof", 1)):
            with self.subTest(empty_slot=empty_slot, status=status, trigger=trigger,
                              lease_failure_slot=lease_failure_slot), tempfile.TemporaryDirectory() as folder:
                stack, scopes, events = self.observer_fixture(folder, empty_slot=empty_slot, status=status,
                    trigger=trigger, lease_failure_slot=lease_failure_slot)
                with stack, self.assertRaises(H.Unavailable):
                    H.pair_boundary_case(scopes, [Path("/fixed-0"), Path("/fixed-1")],
                        Path(folder), {"attempt": 1}, 2001, 2001, case="controller-death", outside={})
                self.assertTrue(all(("cleanup", slot) in events for slot in (0, 1)))
                self.assertFalse(any(scope.live for scope in scopes))
                if lease_failure_slot is not None:
                    self.assertIn(("signal", 987, H.signal.SIGKILL), events)
                    self.assertIn("worker-reaped", events)

    def test_second_guardian_setup_failure_still_closes_first_without_fork(self):
        with tempfile.TemporaryDirectory() as folder:
            first = SimpleNamespace(close=unittest.mock.Mock())
            scopes = [SimpleNamespace(path=Path(folder)/str(slot)) for slot in (0, 1)]
            with (patch.object(H.os, "geteuid", return_value=0),
                  patch.object(H, "Guardian", side_effect=[first, H.Unavailable("fixed setup failure")]),
                  patch.object(H.os, "fork") as fork, self.assertRaises(H.Unavailable)):
                H.pair_boundary_case(scopes, [Path("/fixed-0"), Path("/fixed-1")],
                    Path(folder), {"attempt": 1}, 2001, 2001, case="controller-death", outside={})
            first.close.assert_called_once_with()
            fork.assert_not_called()

    def test_pair_boundary_bootstrap_and_reaped_live_member_checks_are_real_supervisor_steps(self):
        # Existing fixture supplies actual gated Python processes; only host
        # credentials/cgroups are explicit offline doubles, never native proof.
        fixture = ProtectedSuitePairTests("test_two_real_gated_processes_overlap_before_either_can_complete")
        with tempfile.TemporaryDirectory() as folder:
            script, scopes, plans, events, processes, popen = fixture.pair_fixture(folder, ("normal", "normal"))
            def native_role(argv, **kwargs):
                self.assertEqual(argv[-1], "daemon")
                copied = list(argv)
                copied[-1] = "suite"  # old offline launcher's explicit assertion only
                return popen(copied, **kwargs)
            for scope in scopes:
                scope.members = lambda: {99999999}
                scope.populated = lambda: 1
            def ready():
                self.assertEqual(events, [("attach", 0), ("attach", 1)])
                self.assertTrue(all(process.returncode == 0 for process in processes))
                self.assertTrue(all(scope.kills == 0 for scope in scopes))
                events.append("both-live-before-cleanup")
            with patch.object(H, "public_bootstrap", return_value=script), patch.object(H.subprocess, "Popen", side_effect=native_role):
                results = H.supervise_pair(plans, 1234, 1234, timeout=5, cancelled=[],
                                           _boundary_case="daemon", _before_cleanup=ready)
            self.assertIn("both-live-before-cleanup", events)
            self.assertTrue(all(value["trusted_cleanup_canaries"]["initial_command_reaped"] for value in results))
            self.assertTrue(all(scope.kills >= 2 for scope in scopes))

if __name__ == "__main__":
    unittest.main()
