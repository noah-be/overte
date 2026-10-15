#!/usr/bin/env python3
"""Prospective hosted boundary diagnostic, not production execution/evidence.

Local tests exercise parsers and control order only. The root-only operational
entrypoint is restricted to a reviewed manual workflow on the fork's main,
uses only fixed fixtures, and never accepts a candidate command or proof JSON.
Missing tools/kernel interfaces/isolation produce nonzero unavailable results.
"""

from __future__ import annotations

from contextlib import ExitStack
import argparse
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = "overte-ci-qualification"
WORKFLOW = "noah-l-frank/overte/.github/workflows/shared-sandbox-host-diagnostic.yml@refs/heads/main"
CASES = ("protections", "nested", "daemon", "fork-exit", "timeout")
_MAX_BYTES = 65536


class Unavailable(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Unavailable(message)


def command(argv, *, timeout=5, **kwargs):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, timeout=timeout, **kwargs)
    except (OSError, subprocess.SubprocessError) as error:
        raise Unavailable("required diagnostic host command is unavailable") from error
    require(len(result.stdout) <= _MAX_BYTES and len(result.stderr) <= _MAX_BYTES, "diagnostic host command exceeds output bound")
    return result


def host_context(environment, *, effective_uid=None):
    require((os.geteuid() if effective_uid is None else effective_uid) == 0, "diagnostic requires independently provisioned trusted host root")
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": "noah-l-frank/overte",
                "GITHUB_REPOSITORY_ID": "1319052603", "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": WORKFLOW,
                "RUNNER_ENVIRONMENT": "github-hosted", "ImageOS": "ubuntu24"}
    require(all(environment.get(name) == value for name, value in expected.items()), "diagnostic is outside its reviewed hosted manual context")
    require(re.fullmatch(r"[0-9a-f]{40}", environment.get("GITHUB_SHA", ""))
            and re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", environment.get("ImageVersion", "")), "diagnostic source or image identity is missing")
    require(re.fullmatch(r"[1-9][0-9]*", environment.get("SUDO_UID", "")), "trusted runner identity is missing")
    require(all(re.fullmatch(r"[1-9][0-9]*", environment.get(name, "")) for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")),
            "diagnostic run identity is missing")
    return int(environment["SUDO_UID"])


def verify_account(runner_uid):
    try:
        account = pwd.getpwnam(ACCOUNT)
    except KeyError as error:
        raise Unavailable("fixed diagnostic account is not provisioned") from error
    require(account.pw_uid not in {0, runner_uid} and account.pw_shell == "/usr/sbin/nologin", "diagnostic account does not have an independent restricted identity")
    groups = os.getgrouplist(ACCOUNT, account.pw_gid)
    require(not set(groups).intersection({0, runner_uid})
            and not {grp.getgrgid(group).gr_name for group in groups}.intersection({"sudo", "admin", "wheel", "docker", "lxd"}),
            "diagnostic account belongs to a privileged group")
    verdict = command(["/usr/bin/sudo", "-n", "-l", "-U", ACCOUNT])
    denied = (verdict.stdout + verdict.stderr).decode("utf-8", errors="replace")
    require(verdict.returncode == 1 and re.search(r"User " + ACCOUNT + r" is not allowed to run sudo on [^\r\n]+", denied),
            "diagnostic account has sudo authority or its policy cannot be established")
    return account.pw_uid, account.pw_gid


def cgroup_mount(source):
    """Require the actual fixed root mount, not a candidate events-file claim."""
    require(type(source) is str and len(source) <= 1_000_000, "host mount inventory is unsupported")
    matches = []
    for line in source.splitlines():
        left, separator, right = line.partition(" - ")
        fields, filesystem = left.split(), right.split()
        if separator and len(fields) >= 6 and len(filesystem) >= 3 and fields[4] == "/sys/fs/cgroup":
            matches.append((fields, filesystem))
    require(len(matches) == 1, "fixed cgroup mount is missing or ambiguous")
    fields, filesystem = matches[0]
    require(filesystem[0] == "cgroup2" and fields[3] == "/" and "rw" in fields[5].split(","),
            "writable cgroup-v2 root domain is unavailable")


def scope_events(source):
    require(type(source) is bytes and len(source) <= 4096, "kernel scope observation exceeds bound")
    try:
        lines = source.decode("ascii").splitlines()
        values = {}
        for line in lines:
            require(re.fullmatch(r"(?:populated|frozen) [01]", line), "unsupported kernel scope event")
            name, value = line.split(" ")
            require(name not in values, "duplicate kernel scope event")
            values[name] = int(value)
        require(set(values) == {"populated", "frozen"}, "incomplete kernel scope event")
        return values
    except UnicodeError as error:
        raise Unavailable("unsupported kernel scope event encoding") from error


def delegation_path(properties, membership):
    """Parse independently queried manager/kernel facts; strings are not auth."""
    require(type(properties) is str and len(properties) <= 4096 and type(membership) is str and len(membership) <= 4096,
            "delegation metadata exceeds bounds")
    fields = {}
    for line in properties.splitlines():
        name, separator, value = line.partition("=")
        require(separator and name in {"Delegate", "ControlGroup"} and name not in fields,
                "delegation metadata is unknown or ambiguous")
        fields[name] = value
    require(set(fields) == {"Delegate", "ControlGroup"} and fields["Delegate"] == "yes", "systemd has not delegated the diagnostic subtree")
    relative = fields["ControlGroup"]
    require(relative.startswith("/") and relative != "/" and str(Path(relative)) == relative
            and all(part not in {".", ".."} and re.fullmatch(r"[A-Za-z0-9_.@-]+", part) for part in relative.split("/")[1:]),
            "systemd control group path is unsupported")
    require(membership == "0::" + relative + "\n", "current process is outside the independently queried delegated unit")
    return Path("/sys/fs/cgroup") / relative.lstrip("/")


def prepare_delegation():
    unit = "overte-shared-qualification-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"] + ".service"
    queried = command(["/usr/bin/systemctl", "show", unit, "--property=ControlGroup", "--property=Delegate", "--no-pager"])
    require(queried.returncode == 0, "actual systemd delegation cannot be queried")
    root = delegation_path(queried.stdout.decode("ascii"), Path("/proc/self/cgroup").read_text(encoding="ascii"))
    cgroup_mount(Path("/proc/self/mountinfo").read_text(encoding="ascii"))
    current = Path("/sys/fs/cgroup")
    for part in root.relative_to(current).parts:
        current /= part
        info = current.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "delegated cgroup directory is not controlled by host root")
    # Obey the no-processes-in-inner-nodes rule. Write only a child we create,
    # never attributes of the systemd-owned unit or hierarchy root. systemd
    # collects this controller child after the transient service exits.
    controller = root / "diagnostic-controller"
    controller.mkdir(mode=0o700)
    descriptor = os.open(controller / "cgroup.procs", os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.write(descriptor, (str(os.getpid()) + "\n").encode("ascii"))
    finally:
        os.close(descriptor)
    expected = "0::/" + str(controller.relative_to("/sys/fs/cgroup")) + "\n"
    require(Path("/proc/self/cgroup").read_text(encoding="ascii") == expected,
            "controller did not enter its independent delegated child")
    return root


def _read(fd, limit=4096):
    os.lseek(fd, 0, os.SEEK_SET)
    data = os.read(fd, limit + 1)
    require(len(data) <= limit, "kernel control observation exceeds bound")
    return data


class OwnedScope:
    """Created and held by root on the verified kernel mount, never from JSON."""

    def __init__(self, uid, gid, delegated):
        self.uid, self.gid, self.path, self.leaf, self.fds = uid, gid, None, None, []
        cgroup_mount(Path("/proc/self/mountinfo").read_text(encoding="ascii"))
        mount = Path("/sys/fs/cgroup")
        info = mount.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "cgroup mount is not controlled by host root")
        require(isinstance(delegated, Path) and delegated.is_relative_to(mount) and delegated != mount,
                "private scopes require the independently verified delegated subtree")
        self.path = delegated / ("fixture-scope-" + uuid.uuid4().hex)
        try:
            self.path.mkdir(mode=0o700)
            self.leaf = self.path / "fixture"
            self.leaf.mkdir(mode=0o700)
            for directory in (self.path, self.leaf):
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                self.fds.append(descriptor)
                current = os.fstat(descriptor)
                require(current.st_uid == 0 and current.st_dev == info.st_dev and not current.st_mode & 0o077,
                        "kernel scope directory is not exclusively parent-owned")
            self.directory, self.leaf_directory = self.fds
            self.events = self.open("cgroup.events", os.O_RDONLY)
            self.kill_fd = self.open("cgroup.kill", os.O_WRONLY)
            self.procs = self.open("cgroup.procs", os.O_RDWR, leaf=True)
            kind = self.open("cgroup.type", os.O_RDONLY)
            require(_read(kind).strip() == b"domain" and self.populated() == 0, "fresh kernel scope is not an empty domain")
        except BaseException:
            self.close()
            raise

    def open(self, name, flags, *, leaf=False):
        descriptor = os.open(name, flags | os.O_CLOEXEC | os.O_NOFOLLOW,
                             dir_fd=self.leaf_directory if leaf else self.directory)
        self.fds.append(descriptor)
        info = os.fstat(descriptor)
        require(info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022,
                "kernel scope control file is writable outside its parent")
        return descriptor

    def populated(self):
        return scope_events(_read(self.events))["populated"]

    def members(self):
        raw = _read(self.procs)
        require(re.fullmatch(rb"(?:[1-9][0-9]*\n)*", raw), "kernel scope member inventory is unsupported")
        return {int(value) for value in raw.splitlines()}

    def attach(self, process):
        require(process.pid != os.getpid() and self.uid != 0 and self.populated() == 0, "scope attachment is not a new independent child")
        status = Path("/proc/" + str(process.pid) + "/status").read_text(encoding="ascii")
        match = re.search(r"^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)$", status, re.M)
        require(match is not None and {int(value) for value in match.groups()} == {self.uid}, "bootstrap has not dropped its real host identity")
        group = re.search(r"^Gid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)$", status, re.M)
        supplementary = re.search(r"^Groups:[ \t]*([0-9 \t]*)$", status, re.M)
        require(group is not None and {int(value) for value in group.groups()} == {self.gid}
                and supplementary is not None and not supplementary[1].strip(), "bootstrap retained an unexpected actual host group")
        os.write(self.procs, (str(process.pid) + "\n").encode("ascii"))
        require(self.members() == {process.pid} and self.populated() == 1, "bootstrap was not exclusively attached before release")

    def kill_and_wait(self, timeout=3):
        os.write(self.kill_fd, b"1\n")
        deadline = time.monotonic() + timeout
        while self.populated():
            require(time.monotonic() < deadline, "kernel scope retained live descendants after kill")
            time.sleep(0.02)
        return {"kernel_populated": 0, "subtree_kill": True}

    def close(self):
        for descriptor in reversed(self.fds):
            os.close(descriptor)
        self.fds.clear()
        if self.leaf is not None and self.leaf.exists():
            self.leaf.rmdir()
        if self.path is not None and self.path.exists():
            self.path.rmdir()


def trusted_cleanup_canaries(count):
    """Fixed trusted cgroup kill canaries, never arbitrary pre-sandbox work.

    PID namespace teardown may already kill the inner fixture's children. These
    separate low-UID controls inherit the authenticated scope after release and
    survive the initial bwrap process, without relaxing its namespace flags.
    """
    require(type(count) is int and count in {1, 3}, "unsupported fixed cleanup canary inventory")
    reader, writer = os.pipe2(os.O_CLOEXEC)
    try:
        for _ in range(count):
            if os.fork() == 0:
                try:
                    os.close(reader)
                    os.setsid()
                    for descriptor in (0, 1, 2):
                        os.close(descriptor)
                    os.write(writer, b"1")
                    os.close(writer)
                    # Longer than the eight-second case deadline. Kernel-owned
                    # cleanup must terminate us; this fixed fallback is bounded.
                    time.sleep(60)
                finally:
                    os._exit(0)
        os.close(writer)
        writer = None
        remaining = count
        while remaining:
            block = os.read(reader, remaining)
            require(block and block == b"1" * len(block), "fixed cleanup canaries did not become ready")
            remaining -= len(block)
    finally:
        os.close(reader)
        if writer is not None:
            os.close(writer)


def bootstrap(gate, plan, case="protections"):
    """Trusted unprivileged pre-exec gate: no workload runs before attachment."""
    require(os.getuid() != 0 and os.geteuid() == os.getuid(), "bootstrap must already run under the restricted actual host UID")
    with os.fdopen(gate, "rb", closefd=True) as channel:
        require(channel.read(1) == b"1", "parent did not release the attached bootstrap")
    value = json.loads(Path(plan).read_text(encoding="ascii"))
    require(type(value) is list and value and value[0] == "/usr/bin/bwrap"
            and all(type(arg) is str and "\0" not in arg for arg in value), "fixed diagnostic launch plan is unsupported")
    require(case in CASES, "unsupported fixed bootstrap case")
    if case in {"daemon", "fork-exit"}:
        trusted_cleanup_canaries(3 if case == "fork-exit" else 1)
    os.execve(value[0], value, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def supervise(scope, plan, uid, gid, *, timeout, case="protections"):
    """Contain before exec, then kill/confirm the whole kernel subtree."""
    require(case in CASES and 0 < timeout <= 8, "unsupported fixed supervisor case or deadline")
    gate_read, gate_write = os.pipe2(os.O_CLOEXEC)
    process, data, reason = None, bytearray(), None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(["/usr/bin/python3", "-I", str(Path(__file__).resolve()), "--bootstrap", str(gate_read), str(plan), case],
                                   user=uid, group=gid, extra_groups=(), pass_fds=(gate_read,), close_fds=True,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, start_new_session=True)
        os.close(gate_read)
        gate_read = None
        scope.attach(process)
        os.write(gate_write, b"1")
        os.close(gate_write)
        gate_write = None
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                reason = "timeout"
                break
            for key, _ in selector.select(0.02):
                block = os.read(key.fileobj.fileno(), min(8192, _MAX_BYTES + 1 - len(data)))
                if block:
                    data.extend(block)
                    require(len(data) <= _MAX_BYTES, "fixed fixture diagnostic output exceeded bound")
                else:
                    selector.unregister(key.fileobj)
            if process.poll() is not None:
                # Reap the initial command before observing the separate trusted
                # cleanup canaries; output EOF alone cannot prove this ordering.
                process.wait(timeout=3)
                break
        live_before_cleanup = scope.populated()
        canaries = None
        if case in {"daemon", "fork-exit"}:
            minimum = 3 if case == "fork-exit" else 1
            members = scope.members()
            require(reason is None and process.returncode is not None and process.pid not in members
                    and live_before_cleanup == 1 and len(members) >= minimum,
                    "no kernel-observed cleanup canaries survived the initial command")
            canaries = {"initial_command_reaped": True, "kernel_populated": live_before_cleanup,
                        "kernel_member_count": len(members), "minimum_canaries": minimum}
        cleanup = scope.kill_and_wait()
        process.wait(timeout=3)
        # Drain bounded fixed-fixture output ONLY after kernel scope is empty.
        remainder = process.stdout.read(_MAX_BYTES + 1 - len(data))
        data.extend(remainder)
        require(len(data) <= _MAX_BYTES, "fixed fixture diagnostic output exceeded bound")
        try:
            observation = json.loads(data)
        except (ValueError, UnicodeError):
            observation = None
        return {"exit_code": process.returncode, "reason": reason, "live_before_cleanup": live_before_cleanup,
                "cleanup": cleanup, "observation": observation, "trusted_cleanup_canaries": canaries}
    finally:
        for descriptor in (gate_read, gate_write):
            if descriptor is not None:
                os.close(descriptor)
        if process is not None:
            # This is the same authenticated root-owned scope even on errors.
            # No PGID/JSON/bwrap-exit fallback is accepted as descendant cleanup.
            scope.kill_and_wait()
            if process.poll() is None:
                process.kill()  # bootstrap may have failed before attachment
            process.wait(timeout=3)
            process.stdout.close()
        selector.close()


def validate_case(name, result, outside):
    require(name in CASES and result["cleanup"] == {"kernel_populated": 0, "subtree_kill": True}, "fixed fixture has no confirmed scope cleanup")
    observed = result["observation"]
    require(type(observed) is dict, "fixed fixture did not report its actual observation")
    if name == "timeout":
        require(result["reason"] == "timeout" and observed.get("descendants_started") == 1
                and result["live_before_cleanup"] == 1 and result["exit_code"] != 0, "timeout fixture did not retain a contained descendant")
    else:
        require(result["reason"] is None and result["exit_code"] == 0, "fixed fixture did not execute successfully")
        if name in {"daemon", "fork-exit"}:
            require(observed == {"descendants_started": 3 if name == "fork-exit" else 1}, "detached descendant fixture did not execute")
            controls = result.get("trusted_cleanup_canaries")
            minimum = 3 if name == "fork-exit" else 1
            require(result.get("live_before_cleanup") == 1 and type(controls) is dict
                    and set(controls) == {"initial_command_reaped", "kernel_populated", "kernel_member_count", "minimum_canaries"}
                    and controls["initial_command_reaped"] is True and controls["kernel_populated"] == 1
                    and type(controls["minimum_canaries"]) is int and controls["minimum_canaries"] == minimum
                    and type(controls["kernel_member_count"]) is int
                    and controls["kernel_member_count"] >= minimum,
                    "trusted cleanup canary kill coverage lacks actual surviving kernel members")
        elif name == "nested":
            require(observed == {"nested_loopback": True, "nested_network_distinct": True}, "required nested user/network namespace fixture failed")
        else:
            protected = observed.get("process", {})
            require(protected == {"NoNewPrivs": "1", **{key: "0000000000000000" for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}},
                    "actual namespace process retained privileges")
            namespaces = observed.get("namespaces", {})
            require(set(namespaces) == set(outside) and all(type(value) is int and value != outside[key] for key, value in namespaces.items()),
                    "mandatory namespaces are not independent of the host")
            flags = set(observed) - {"process", "namespaces", "uid_map"}
            expected = {"parent_proc_hidden", "protected_read_hidden", "protected_write_hidden", "command_files_hidden", "scope_hidden",
                        "source_readonly", "git_readonly", "venv_readonly", "policy_readonly", "loopback", "only_loopback_interface",
                        "no_ipv4_default_route", "credential_environment_absent", "path_socket_hidden", "abstract_socket_hidden",
                        "home_writable", "temp_writable", "build_writable", "sudo_denied", "venv_aliases", "protected_descriptors_absent", "readonly_mount_flags"}
            require(flags == expected and all(observed[key] is True for key in expected), "one or more real boundary attacks succeeded or prerequisites failed")


def _module():
    # Import only the current trusted source, never fixture/candidate modules.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    spec = importlib.util.spec_from_file_location("trusted_boundary_plan", Path(__file__).with_name("sandbox.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_host():
    runner = host_context(os.environ)
    release = Path("/etc/os-release").read_text(encoding="ascii")
    require('ID=ubuntu' in release and 'VERSION_ID="24.04"' in release, "actual host OS is outside the diagnostic contract")
    uid, gid = verify_account(runner)
    ip = next((value for value in ("/usr/bin/ip", "/usr/sbin/ip") if Path(value).is_file()), None)
    require(ip is not None, "fixed system network tool is unavailable")
    tools = {}
    for executable in ("/usr/bin/bwrap", ip, "/usr/bin/unshare", "/usr/bin/python3", "/usr/bin/sudo"):
        info = Path(executable).stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022, "required fixed host tool is unavailable or mutable")
        tools[Path(executable).name] = "sha256:" + hashlib.sha256(Path(executable).read_bytes()).hexdigest()
        if executable == "/usr/bin/bwrap":
            require(not info.st_mode & 0o6000, "privileged bubblewrap executable is outside the diagnostic profile")
    delegated = prepare_delegation()
    os.environ["HOST_DIAGNOSTIC_CANARY"] = "public-fixture-canary-not-a-secret"
    source = _module()
    result = {"schema": 1, "status": "started", "authority": "none", "production_qualified": False,
              "source": os.environ["GITHUB_SHA"], "image": {name: os.environ[name] for name in ("ImageOS", "ImageVersion")},
              "kernel": os.uname().release, "tools": tools, "account_uid": uid, "cases": {}, "runtime_compatibility": "unqualified",
              "diagnostic_sources": {name: "sha256:" + hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                     for name in ("sandbox_host.py", "sandbox_host_fixture.py", "workflows/shared-sandbox-host-diagnostic.yml")}}
    with tempfile.TemporaryDirectory(prefix="overte-boundary-diagnostic-") as temporary, ExitStack() as stack:
        base = Path(temporary)
        base.chmod(0o755)
        paths = {name: base / name for name in ("candidate", "scratch", "policy", "venv", "protected")}
        for name, path in paths.items():
            path.mkdir(mode=0o700 if name in {"scratch", "protected"} else 0o755)
        os.chown(paths["scratch"], uid, gid)
        (paths["candidate"] / ".git").mkdir()
        (paths["candidate"] / "build").mkdir()
        (paths["candidate"] / "fixture.py").write_bytes(Path(__file__).with_name("sandbox_host_fixture.py").read_bytes())
        command(["/usr/bin/python3", "-m", "venv", "--without-pip", str(paths["venv"])]).check_returncode()
        for name in ("candidate", "policy", "venv"):
            canary = paths[name] / "readonly-canary"
            canary.write_text("public-readonly-canary\n", encoding="ascii")
            canary.chmod(0o666)
        git_canary = paths["candidate"] / ".git/config"
        git_canary.write_text("public-readonly-git-canary\n", encoding="ascii")
        git_canary.chmod(0o666)
        protected = paths["protected"] / "dummy-secret"
        protected.write_text("diagnostic-canary-not-a-secret\n", encoding="ascii")
        private_descriptor = stack.enter_context(protected.open("rb"))
        os.set_inheritable(private_descriptor.fileno(), True)
        command_files = [os.environ.get(name, "") for name in ("QUALIFY_GITHUB_ENV", "QUALIFY_GITHUB_OUTPUT")]
        require(all(value and Path(value).is_absolute() and not Path(value).is_symlink() and Path(value).is_file()
                    and Path(value).stat().st_uid == runner for value in command_files), "actual runner command-file probes are unavailable")
        outside = {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("user", "mnt", "pid", "net", "ipc", "uts")}
        abstract = "overte-boundary-" + uuid.uuid4().hex
        path_socket = str(paths["protected"] / "host.socket")
        for target in (path_socket, "\0" + abstract):
            server = stack.enter_context(socket.socket(socket.AF_UNIX))
            server.bind(target)
            server.listen(1)
        context = {"parent_pid": os.getpid(), "protected_canary": str(protected), "command_files": command_files,
                   "abstract_socket": abstract, "path_socket": path_socket, "ip": ip}
        layout = source.Layout(paths["candidate"], paths["scratch"], paths["policy"], paths["venv"], paths["protected"])
        for case in CASES:
            scope = OwnedScope(uid, gid, delegated)
            try:
                (paths["candidate"] / "context.json").write_text(json.dumps({**context, "scope_directory": str(scope.path)}), encoding="ascii")
                plan = source.build_plan(layout, ["/opt/overte-ci/venv/bin/python", "-I", "/work/fixture.py", case])
                plan_path = base / "fixed-plan.json"
                plan_path.write_text(json.dumps(plan["argv"]), encoding="ascii")
                observation = supervise(scope, plan_path, uid, gid, timeout=4 if case == "timeout" else 8, case=case)
                validate_case(case, observation, outside)
                require(git_canary.read_text(encoding="ascii") == "public-readonly-git-canary\n"
                        and protected.read_text(encoding="ascii") == "diagnostic-canary-not-a-secret\n", "outside protected source or report canary was altered")
                result["cases"][case] = {"status": "passed", "kernel_scope_empty": True,
                    "live_before_cleanup": observation["live_before_cleanup"], "trusted_cleanup_canaries": observation["trusted_cleanup_canaries"]}
            finally:
                scope.kill_and_wait()
                scope.close()
        result.update(status="boundary-diagnostic-passed", contract=source.contract()["digest"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", nargs=3, metavar=("GATE_FD", "FIXED_PLAN", "FIXTURE_CASE"))
    arguments = parser.parse_args(argv)
    if arguments.bootstrap is not None:
        bootstrap(int(arguments.bootstrap[0]), arguments.bootstrap[1], arguments.bootstrap[2])
        return 1
    try:
        result = run_host()
        code = 0
    except (Unavailable, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result = {"schema": 1, "status": "unavailable", "authority": "none", "production_qualified": False,
                  "error": str(error) if isinstance(error, Unavailable) else "required host diagnostic operation failed"}
        code = 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
