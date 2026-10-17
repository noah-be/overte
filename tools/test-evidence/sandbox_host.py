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
import errno
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import select
import selectors
import signal
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
_BOOTSTRAP_CASES = (*CASES, "probe", "suite", "shared-probe")
_MAX_BYTES = 65536
_BOOTSTRAP_DIRECTORY = None


class Unavailable(ValueError):
    pass


_PUBLIC_FAILURE_SOURCES = (
    'sandbox_host.py', 'sandbox_shared.py', 'sandbox.py', 'sandbox_probe.py',
    'runtime.py', 'runtime_ci.py', 'execution.py', 'inputs.py', 'ci_profile.py',
    'producer_workflow.py', 'producer_api.py', 'producer.py',
)
_PUBLIC_FAILURE_STAGES = {
    'host_context': 'native-context', 'verify_account': 'account-permissions',
    'command': 'fixed-host-command', 'prepare_delegation': 'kernel-delegation',
    'verify_source': 'trusted-source', 'verify_qualification_source': 'trusted-source',
    'prepared_tools': 'prepared-tool-selection', 'prepared_identity': 'prepared-input-identity',
    'materialize_source': 'candidate-materialization', 'materialize_candidate_snapshot': 'candidate-materialization',
    'project_policy': 'policy-projection', 'check_batch': 'shared-batch',
    'run_suites': 'selected-suites', 'probe': 'protected-runtime-probe',
    'capture_host_environment': 'actual-full-runtime', 'capture_ci_environment': 'actual-ci37-runtime',
    '_git': 'immutable-git-read', '_file_hash': 'readonly-file-hash',
    'kill_and_wait': 'kernel-kill-and-empty', 'empty': 'kernel-empty-check',
    'populated': 'kernel-empty-check', 'close': 'scope-or-guardian-cleanup',
    'finish': 'guardian-cleanup-proof', 'launch': 'contained-command',
    'supervise': 'contained-process', '_write_receipt': 'diagnostic-report-write',
    'run_host': 'profile-control', 'main': 'profile-entry',
    '_shared_controller_module': 'trusted-module-identity',
    'protected_admission': 'protected-source-admission',
    'prepare': 'protected-owner-selection', 'current_run': 'native-current-role',
    '_descriptor': 'native-descriptor-read', '_request': 'github-get-boundary',
    'shared_execution': 'protected-shared-execution', 'protected_receipt': 'protected-receipt',
}
_PUBLIC_EXCEPTION_KINDS = (
    (Unavailable, 'Unavailable'), (FileNotFoundError, 'FileNotFoundError'),
    (PermissionError, 'PermissionError'), (NotADirectoryError, 'NotADirectoryError'),
    (IsADirectoryError, 'IsADirectoryError'), (TimeoutError, 'TimeoutError'),
    (OSError, 'OSError'), (subprocess.TimeoutExpired, 'TimeoutExpired'),
    (subprocess.CalledProcessError, 'CalledProcessError'), (subprocess.SubprocessError, 'SubprocessError'),
    (KeyError, 'KeyError'), (UnicodeError, 'UnicodeError'), (ValueError, 'ValueError'),
)
_PUBLIC_FAILURE_INPUTS = (
    (r'/opt/overte-ci/venv(?:/|$)', 'prepared-venv'),
    (r'/opt/hostedtoolcache/Python/3\.12\.[0-9]+/x64(?:/|$)', 'prepared-python'),
    (r'/opt/hostedtoolcache/node/22\.[0-9]+\.[0-9]+/x64(?:/|$)', 'prepared-node'),
    (r'/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/17\.[0-9.-]+/x64(?:/|$)', 'prepared-java-cache'),
    (r'/usr/lib/jvm(?:/|$)', 'system-jvm'),
    (r'/sys/fs/cgroup(?:/|$)', 'kernel-cgroup'),
)


def failure_summary(error):
    """Public types/callsites only; never exception text, paths, args or output.

    Inspect at most four private cause/context links. This retains the original
    operation if a finally/temporary cleanup raises a second error, without
    altering cleanup, exception propagation or the unavailable verdict.
    """
    sources = {str(ROOT / 'tools/test-evidence' / name): 'tools/test-evidence/' + name
               for name in _PUBLIC_FAILURE_SOURCES}
    chain, seen = [], set()
    while isinstance(error, BaseException) and id(error) not in seen and len(chain) < 4:
        seen.add(id(error))
        kind = next((name for cls, name in _PUBLIC_EXCEPTION_KINDS if isinstance(error, cls)), 'OtherException')
        number = error.errno if isinstance(error, OSError) else None
        number = number if type(number) is int and 0 < number <= 4095 else None
        item = {'exception_class': kind, 'errno': number, 'errno_name': errno.errorcode.get(number),
                'stage': 'unclassified-host-operation'}
        # Emit only a fixed public root label, never the actual filename or
        # relative leaf. Unknown/private paths supply no hint at all.
        filename = error.filename if isinstance(error, OSError) else None
        if type(filename) is str and len(filename) <= 2048:
            for pattern, label in _PUBLIC_FAILURE_INPUTS:
                if re.match(pattern, filename):
                    item['input_root'] = label
                    break
        trace = error.__traceback__
        frames, callers = 0, []
        while trace is not None and frames < 64:
            code = trace.tb_frame.f_code
            if (code.co_filename in sources and code.co_name not in {'require', '_require'}
                    and type(trace.tb_lineno) is int and 0 < trace.tb_lineno <= 1_000_000):
                callers.append({'source': sources[code.co_filename], 'line': trace.tb_lineno,
                                'stage': _PUBLIC_FAILURE_STAGES.get(code.co_name, 'trusted-controller-operation')})
                callers = callers[-4:]
            trace = trace.tb_next
            frames += 1
        if callers:
            item.update(callers[-1], callers=callers[:-1])
        chain.append(item)
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return {'chain': chain, 'chain_truncated': isinstance(error, BaseException) and id(error) not in seen}


def _shared_controller_module():
    # The workflow executes this file as __main__, while sandbox_shared imports
    # sandbox_host. Preserve one reviewed controller/global state and one
    # Unavailable class. Never replace an already loaded foreign module.
    current = sys.modules.get(__name__)
    require(isinstance(current, type(sys)) and vars(current) is globals(),
            'diagnostic controller module identity is unavailable')
    existing = sys.modules.get('sandbox_host')
    require(existing is None or existing is current, 'diagnostic controller module identity is ambiguous')
    sys.modules['sandbox_host'] = current


def require(condition, message):
    if not condition:
        raise Unavailable(message)


def command(argv, *, timeout=5, **kwargs):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                                     "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                                     "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1"}, timeout=timeout, **kwargs)
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
            and environment.get("GITHUB_WORKFLOW_SHA") == environment.get("GITHUB_SHA")
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
    # sudo1.9.15p5 display_privs returns success even when its command count
    # is zero; the frontend maps that successful listing to exit0. Accept only
    # its complete single denial line, with no diagnostics or extra policy.
    denial = rb"User " + ACCOUNT.encode("ascii") + rb" is not allowed to run sudo on [A-Za-z0-9_.-]{1,255}\.\n"
    if verdict.returncode not in {0, 1} or verdict.stderr or not re.fullmatch(denial, verdict.stdout):
        # Do not dump hostnames, sudoers entries or arbitrary command listings.
        # Unknown output remains denial of qualification; these public-only
        # facts distinguish an unexpected exit/wording from an actual grant.
        summary = {"exit_code": verdict.returncode,
                   "stdout_bytes": len(verdict.stdout), "stderr_bytes": len(verdict.stderr),
                   "stdout_sha256": hashlib.sha256(verdict.stdout).hexdigest(),
                   "stderr_sha256": hashlib.sha256(verdict.stderr).hexdigest(),
                   "denial_marker": "is not allowed to run sudo" in denied,
                   "grant_marker": "may run the following commands" in denied,
                   "policy_error_marker": any(value in denied.lower() for value in (
                       "policy plugin", "authentication failure", "a password is required", "parse error"))}
        raise Unavailable("diagnostic sudo policy is unestablished: " + json.dumps(summary, sort_keys=True))
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
    require(case in _BOOTSTRAP_CASES, "unsupported fixed bootstrap case")
    if case in {"daemon", "fork-exit"}:
        trusted_cleanup_canaries(3 if case == "fork-exit" else 1)
    os.execve(value[0], value, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def public_bootstrap():
    """Copy this verified controller once outside the private runner checkout.

    Python opens its script after Popen drops the actual host UID. The copy is
    public source, never a report or credential, and imports only the stdlib on
    the fixed --bootstrap path. The original protected controller keeps ROOT.
    """
    global _BOOTSTRAP_DIRECTORY
    require(os.geteuid() == 0, "bootstrap provisioning requires actual trusted root")
    for path, modes in ((Path("/"), {0o555, 0o755}), (Path("/tmp"), {0o1777})):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) in modes,
                "public bootstrap ancestor is not the fixed root-owned directory")
    descriptor = os.open(Path(__file__).resolve(), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as original:
        info = os.fstat(original.fileno())
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 1_000_000,
                "verified bootstrap source is not a bounded ordinary file")
        body = original.read(1_000_001)
    require(len(body) == info.st_size, "verified bootstrap source changed while reading")
    if _BOOTSTRAP_DIRECTORY is None:
        temporary = tempfile.TemporaryDirectory(prefix="overte-sandbox-bootstrap-", dir="/tmp")
        try:
            base = Path(temporary.name)
            base.chmod(0o755)
            target = base / "sandbox_host.py"
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            with os.fdopen(descriptor, "wb") as copied:
                copied.write(body)
                copied.flush()
                os.fsync(copied.fileno())
                os.fchmod(copied.fileno(), 0o444)
            _BOOTSTRAP_DIRECTORY = temporary
        except BaseException:
            temporary.cleanup()
            raise
    base = Path(_BOOTSTRAP_DIRECTORY.name)
    info = base.lstat()
    require(base.parent == Path("/tmp") and base.resolve(strict=True) == base
            and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o755,
            "public bootstrap storage is not a fixed root-owned directory")
    target = base / "sandbox_host.py"
    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as copied:
        info = os.fstat(copied.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o444
                and info.st_nlink == 1 and info.st_size == len(body), "public bootstrap copy has unsafe metadata")
        require(copied.read(len(body) + 1) == body, "public bootstrap copy differs from the verified controller")
    return target


def supervise(scope, plan, uid, gid, *, timeout, case="protections", _before_cleanup=None, cancelled=None):
    """Contain before exec, then kill/confirm the whole kernel subtree."""
    maximum = 900 if case == "suite" else 120 if case == "shared-probe" else 8
    limit = 2_000_000 if case == "shared-probe" else 1_000_000 if case == "suite" else _MAX_BYTES
    require(case in _BOOTSTRAP_CASES and 0 < timeout <= maximum, "unsupported fixed supervisor case or deadline")
    launcher = public_bootstrap()
    gate_read, gate_write = os.pipe2(os.O_CLOEXEC)
    process, data, reason = None, bytearray(), None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(["/usr/bin/python3", "-I", str(launcher), "--bootstrap", str(gate_read), str(plan), case],
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
            if cancelled:
                reason = "cancelled"
                break
            if time.monotonic() >= deadline:
                reason = "timeout"
                break
            for key, _ in selector.select(0.02):
                block = os.read(key.fileobj.fileno(), min(8192, limit + 1 - len(data)))
                if block:
                    data.extend(block)
                    require(len(data) <= limit, "fixed fixture diagnostic output exceeded bound")
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
        if _before_cleanup is not None:
            # Only the fixed controller-death diagnostic uses this private
            # trusted callback, after actual initial-command reap/live proof.
            require(case == "daemon" and canaries is not None, "controller-death fixture has no live cleanup canary")
            _before_cleanup()
        cleanup = scope.kill_and_wait()
        process.wait(timeout=3)
        # Drain bounded fixed-fixture output ONLY after kernel scope is empty.
        remainder = process.stdout.read(limit + 1 - len(data))
        data.extend(remainder)
        require(len(data) <= limit, "fixed fixture diagnostic output exceeded bound")
        observation = None
        if case != "suite":
            try:
                observation = json.loads(data)
            except (ValueError, UnicodeError):
                pass
        return {"exit_code": process.returncode, "reason": reason, "live_before_cleanup": live_before_cleanup,
                "cleanup": cleanup, "observation": observation, "trusted_cleanup_canaries": canaries,
                **({"diagnostic": bytes(data)} if case in {"suite", "shared-probe", "probe"} else {})}
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


def supervise_pair(scopes_and_plans, uid, gid, *, timeout, cancelled=None,
                   _boundary_case=None, _before_cleanup=None):
    """One root thread owns two separately contained suite processes."""
    require(type(scopes_and_plans) in (tuple, list) and len(scopes_and_plans) == 2
            and scopes_and_plans[0][0] is not scopes_and_plans[1][0]
            and scopes_and_plans[0][0].path != scopes_and_plans[1][0].path
            and type(timeout) is int and 0 < timeout <= 900,
            "parallel suite supervision requires two distinct bounded kernel scopes")
    require(_boundary_case in (None, "daemon")
            and (_before_cleanup is None or _boundary_case == "daemon"),
            "unsupported fixed pair boundary control")
    launcher = public_bootstrap()
    selector = selectors.DefaultSelector()
    entries = []
    limit = 1_000_000

    def finish(entry):
        process, scope = entry["process"], entry["scope"]
        cleanup = scope.kill_and_wait()
        process.wait(timeout=3)
        if entry["registered"]:
            selector.unregister(process.stdout)
            entry["registered"] = False
        entry["data"].extend(process.stdout.read(limit + 1 - len(entry["data"])))
        require(len(entry["data"]) <= limit, "fixed fixture diagnostic output exceeded bound")
        entry["result"] = {"exit_code": process.returncode, "reason": entry["reason"],
            "cleanup": cleanup, "diagnostic": bytes(entry["data"]),
            "duration": time.monotonic() - entry["started"]}
        if _boundary_case is not None:
            entry["result"]["trusted_cleanup_canaries"] = entry["canaries"]

    try:
        for scope, plan in scopes_and_plans:
            entry = {"scope": scope, "process": None, "gate_read": None, "gate_write": None,
                     "data": bytearray(), "reason": None, "result": None, "registered": False}
            entries.append(entry)
            if cancelled:
                entry["result"] = {"exit_code": 128 + cancelled[0], "reason": "cancelled",
                    "cleanup": scope.kill_and_wait(), "diagnostic": b"", "duration": 0.0}
                continue
            entry["gate_read"], entry["gate_write"] = os.pipe2(os.O_CLOEXEC)
            entry["process"] = subprocess.Popen(
                ["/usr/bin/python3", "-I", str(launcher), "--bootstrap",
                 str(entry["gate_read"]), str(plan), _boundary_case or "suite"],
                user=uid, group=gid, extra_groups=(), pass_fds=(entry["gate_read"],),
                close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                start_new_session=True)
            entry["started"] = time.monotonic()
            os.close(entry["gate_read"]); entry["gate_read"] = None
            scope.attach(entry["process"])
            os.write(entry["gate_write"], b"1")
            os.close(entry["gate_write"]); entry["gate_write"] = None
            selector.register(entry["process"].stdout, selectors.EVENT_READ, entry)
            entry["registered"] = True
        if _boundary_case is not None:
            # Only the fixed manual boundary supplies this control. Require
            # actual detached kernel members after BOTH initial commands exit.
            for entry in entries:
                process, scope = entry["process"], entry["scope"]
                process.wait(timeout=3)
                members = scope.members()
                require(process.returncode == 0 and process.pid not in members
                        and scope.populated() == 1 and len(members) >= 1,
                        "pair boundary lacks actual surviving detached canaries")
                entry["canaries"] = {"initial_command_reaped": True,
                    "kernel_populated": 1, "kernel_member_count": len(members), "minimum_canaries": 1}
            if _before_cleanup is not None:
                _before_cleanup()
        while any(entry["result"] is None for entry in entries):
            for key, _ in selector.select(0.02):
                entry = key.data
                block = os.read(key.fileobj.fileno(), min(8192, limit + 1 - len(entry["data"])))
                if block:
                    entry["data"].extend(block)
                    require(len(entry["data"]) <= limit, "fixed fixture diagnostic output exceeded bound")
                else:
                    selector.unregister(key.fileobj)
                    entry["registered"] = False
            for entry in entries:
                if entry["result"] is not None:
                    continue
                process = entry["process"]
                if cancelled:
                    entry["reason"] = "cancelled"
                elif time.monotonic() - entry["started"] >= timeout:
                    entry["reason"] = "timeout"
                elif process.poll() is None:
                    continue
                finish(entry)
        return [entry["result"] for entry in entries]
    finally:
        # Both independent parent-owned cgroups are closed even if the second
        # attachment, either output read, or either command fails unexpectedly.
        def stop(process):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
        # ExitStack attempts every cleanup even if one actual cgroup operation
        # fails. Such a failure still propagates and cannot become success.
        with ExitStack() as cleanup:
            cleanup.callback(selector.close)
            for entry in entries:
                process = entry["process"]
                if process is not None:
                    cleanup.callback(process.stdout.close)
                    cleanup.callback(stop, process)
                cleanup.callback(entry["scope"].kill_and_wait)
                for name in ("gate_read", "gate_write"):
                    if entry[name] is not None:
                        cleanup.callback(os.close, entry[name])


def _wait_child(pid, timeout=5):
    deadline = time.monotonic() + timeout
    while True:
        observed, status = os.waitpid(pid, os.WNOHANG)
        if observed == pid:
            return status
        require(time.monotonic() < deadline, "trusted cleanup process did not finish")
        time.sleep(0.02)


def _guardian_loop(scope, channel, proof, binding, *, lifetime=30):
    """Independent root owner of already opened kernel controls.

    The workload never inherits the release pipe or protected result FD.
    Controller death closes the sole writer; EOF triggers the same actual
    subtree kill/empty check as normal release. No candidate JSON is read.
    """
    ready = select.select([channel], [], [], lifetime)[0]
    payload = os.read(channel, 5) if ready else None
    trigger = "controller-eof" if payload == b"" else "released" if payload == b"done" else "deadline"
    cleanup = scope.kill_and_wait()
    info = os.fstat(scope.directory)
    value = {"trigger": trigger, "cleanup": cleanup, "scope": [info.st_dev, info.st_ino], "binding": binding}
    os.write(proof, (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))


class Guardian:
    """Root-owned sibling, provisioned and ready before any low-UID launch."""
    def __init__(self, scope, protected, binding, *, lifetime=30):
        require(type(lifetime) is int and 1 <= lifetime <= 930, "cleanup guardian deadline is unsupported")
        require(os.geteuid() == 0, "cleanup guardian requires actual trusted root")
        info = protected.lstat()
        require(protected.is_absolute() and protected.resolve(strict=True) == protected
                and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                "guardian report directory is not private trusted storage")
        self.scope, self.binding = scope, binding
        info = os.fstat(scope.directory)
        self.identity = [info.st_dev, info.st_ino]
        self.path = protected / ("guardian-" + uuid.uuid4().hex + ".json")
        proof = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        reader, self.writer = os.pipe2(os.O_CLOEXEC)
        ready_read, ready_write = os.pipe2(os.O_CLOEXEC)
        try:
            self.pid = os.fork()
        except OSError:
            for descriptor in (proof, reader, self.writer, ready_read, ready_write):
                os.close(descriptor)
            self.writer = None
            self.pid = None
            scope.kill_and_wait()
            raise Unavailable("root cleanup guardian could not start") from None
        if self.pid == 0:
            code = 1
            try:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                keep = {reader, proof, ready_write, scope.kill_fd, scope.events, scope.directory}
                for entry in Path("/proc/self/fd").iterdir():
                    descriptor = int(entry.name)
                    if descriptor not in keep:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
                os.write(ready_write, b"1")
                os.close(ready_write)
                _guardian_loop(scope, reader, proof, binding, lifetime=lifetime)
                code = 0
            except (Unavailable, OSError, ValueError):
                pass
            finally:
                os._exit(code)
        os.close(reader)
        os.close(proof)
        os.close(ready_write)
        try:
            require(select.select([ready_read], [], [], 3)[0] and os.read(ready_read, 1) == b"1",
                    "root cleanup guardian did not become ready")
        except BaseException:
            self.close()
            raise
        finally:
            os.close(ready_read)

    def relinquish_writer(self):
        """Death fixture: only its root worker keeps the pipe writer alive."""
        if self.writer is not None:
            os.close(self.writer)
            self.writer = None

    def finish(self, expected="released"):
        if self.writer is not None:
            try:
                os.write(self.writer, b"done")
            finally:
                self.relinquish_writer()
        status = _wait_child(self.pid)
        self.pid = None
        require(status == 0, "root cleanup guardian failed")
        info = self.path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1 and info.st_size <= _MAX_BYTES, "cleanup result lost its protected origin")
        value = json.loads(self.path.read_bytes())
        require(value == {"trigger": expected, "cleanup": {"kernel_populated": 0, "subtree_kill": True},
                          "scope": self.identity, "binding": self.binding}
                and self.scope.populated() == 0, "guardian has no independently confirmed empty bound scope")
        return value

    def close(self):
        # Failure never becomes qualification. Still perform independent cleanup
        # and reap the guardian before removing any private scope directory.
        self.relinquish_writer()
        if self.pid is not None:
            try:
                _wait_child(self.pid)
            except Unavailable:
                os.kill(self.pid, signal.SIGKILL)
                _wait_child(self.pid)
            self.pid = None
        self.scope.kill_and_wait()


def controller_death(scope, guardian, plan, uid, gid):
    """SIGKILL an actual root worker after reap + kernel-live canary proof."""
    reader, writer = os.pipe2(os.O_CLOEXEC)
    worker = os.fork()
    if worker == 0:
        try:
            os.close(reader)
            def ready_then_wait():
                os.write(writer, b"1")
                # The outer trusted observer must kill this controller. A
                # timeout cannot qualify a simulated death or an empty scope.
                time.sleep(30)
                raise Unavailable("controller death was not exercised")
            supervise(scope, plan, uid, gid, timeout=8, case="daemon", _before_cleanup=ready_then_wait)
        finally:
            os._exit(1)
    os.close(writer)
    guardian.relinquish_writer()
    reaped = False
    try:
        require(select.select([reader], [], [], 12)[0] and os.read(reader, 1) == b"1"
                and scope.populated() == 1 and len(scope.members()) >= 1,
                "controller-death fixture has no actual surviving kernel-owned canary")
        os.kill(worker, signal.SIGKILL)
        status = _wait_child(worker)
        reaped = True
        require(os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL,
                "fixed controller did not actually die by SIGKILL")
        proof = guardian.finish("controller-eof")
        return {"controller_sigkill_observed": True, "live_before_cleanup": 1,
                "kernel_scope_empty": True, "guardian_trigger": proof["trigger"]}
    finally:
        os.close(reader)
        if not reaped:
            try:
                os.kill(worker, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _wait_child(worker)
        guardian.close()


def pair_boundary_case(scopes, plans, protected, binding, uid, gid, *, case, outside):
    """Fixed manual-only pair controls; never candidate commands or reusable E."""
    require(os.geteuid() == 0 and case in {"protections", "cancel", "controller-death"}
            and len(scopes) == len(plans) == 2 and scopes[0] is not scopes[1]
            and scopes[0].path != scopes[1].path, "unsupported fixed pair boundary case")
    worker, reaped = None, False
    with ExitStack() as cleanup:
        guardians = []
        for scope in scopes:
            guardian = Guardian(scope, protected, binding, lifetime=20)
            guardians.append(guardian)
            cleanup.callback(guardian.close)
        reader, writer = os.pipe2(os.O_CLOEXEC)
        cleanup.callback(os.close, reader)
        def close_writer():
            nonlocal writer
            if writer is not None:
                os.close(writer)
                writer = None
        cleanup.callback(close_writer)
        result_path = protected / ("pair-worker-" + uuid.uuid4().hex + ".json")
        descriptor = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        cleanup.callback(os.close, descriptor)
        worker = os.fork()
        if worker == 0:
            code = 1
            try:
                os.close(reader)
                cancelled = []
                signal.signal(signal.SIGTERM, lambda number, _frame: cancelled.append(number))
                def ready_then_wait():
                    os.write(writer, b"1")
                    deadline = time.monotonic() + 5
                    while not cancelled:
                        require(time.monotonic() < deadline, "pair observer did not exercise its fixed signal")
                        time.sleep(0.02)
                options = {} if case == "protections" else {
                    "_boundary_case": "daemon", "_before_cleanup": ready_then_wait}
                observed = supervise_pair(list(zip(scopes, plans)), uid, gid, timeout=8,
                                          cancelled=cancelled, **options)
                # Only this root worker holds the lease writers after fork.
                # Workloads receive only their own attach gate, closed at exec.
                for guardian in guardians:
                    os.write(guardian.writer, b"done")
                    guardian.relinquish_writer()
                serial = [{**value, "diagnostic": value["diagnostic"].decode("ascii")} for value in observed]
                os.write(descriptor, json.dumps(serial, sort_keys=True).encode("ascii"))
                code = 0
            except BaseException:
                pass  # nonzero + lease EOF fail closed; no fabricated observation
            finally:
                os._exit(code)
        try:
            close_writer()
            # No observer or sibling guardian may retain either supervisor lease.
            # Otherwise actual controller death could not produce BOTH EOF proofs.
            for guardian in guardians:
                guardian.relinquish_writer()
            if case != "protections":
                require(select.select([reader], [], [], 10)[0] and os.read(reader, 1) == b"1"
                        and all(scope.populated() == 1 and len(scope.members()) >= 1 for scope in scopes),
                        "pair boundary has no two actual live detached kernel scopes")
                os.kill(worker, signal.SIGKILL if case == "controller-death" else signal.SIGTERM)
            status = _wait_child(worker, timeout=12)
            reaped = True
            if case == "controller-death":
                require(os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL,
                        "pair supervisor did not actually die by SIGKILL")
            else:
                require(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
                        "fixed pair boundary supervisor failed")
                info = result_path.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                        and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= _MAX_BYTES,
                        "pair boundary result lost its protected origin")
                observed = json.loads(result_path.read_bytes())
                require(type(observed) is list and len(observed) == 2
                        and all(value["cleanup"] == {"kernel_populated": 0, "subtree_kill": True}
                                for value in observed), "pair boundary cleanup is incomplete")
                if case == "cancel":
                    require(all(value["reason"] == "cancelled"
                                and value["trusted_cleanup_canaries"]["initial_command_reaped"] is True
                                and value["trusted_cleanup_canaries"]["kernel_populated"] == 1
                                and value["trusted_cleanup_canaries"]["kernel_member_count"] >= 1
                                for value in observed), "pair cancellation did not exercise both live scopes")
                else:
                    observations = []
                    for value in observed:
                        measured = json.loads(value["diagnostic"])
                        validate_case("protections", {**value, "observation": measured["protections"]}, outside)
                        descriptors = measured["descriptors"]
                        require(type(descriptors) is dict and set(descriptors) == {"0", "1", "2"}
                                and descriptors["0"] == "/dev/null"
                                and re.fullmatch(r"pipe:\[[0-9]+\]", descriptors["1"])
                                and descriptors["2"] == descriptors["1"],
                                "pair workload inherited a private control descriptor")
                        observations.append(measured["protections"]["namespaces"])
                    require(all(observations[0][name] != observations[1][name] for name in outside),
                            "pair workloads shared a mandatory private namespace")
            expected = "controller-eof" if case == "controller-death" else "released"
            proofs = [guardian.finish(expected) for guardian in guardians]
            require(proofs[0]["scope"] != proofs[1]["scope"]
                    and all(proof["binding"] == binding and scope.populated() == 0
                            for proof, scope in zip(proofs, scopes)), "pair guardian scope binding is incomplete")
            return {"status": "passed", "scope_count": 2, "kernel_scopes_empty": True,
                    "distinct_scope_identities": [proof["scope"] for proof in proofs],
                    "guardian_triggers": [proof["trigger"] for proof in proofs],
                    "controller_sigkill_observed": case == "controller-death",
                    "detached_members_observed": case != "protections",
                    "private_descriptors_checked": case == "protections"}
        finally:
            if worker is not None and not reaped:
                try:
                    os.kill(worker, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _wait_child(worker)


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
                        "home_writable", "temp_writable", "build_writable", "sudo_denied", "venv_aliases", "protected_descriptors_absent", "readonly_mount_flags", "git_pristine"}
            # Report only fixed reviewed names, never unexpected keys or values.
            diagnostics = {"failed": sorted(key for key in expected & flags if observed[key] is not True),
                           "missing": sorted(expected - flags), "extra": bool(flags - expected)}
            require(flags == expected and all(observed[key] is True for key in expected),
                    "one or more real boundary attacks succeeded or prerequisites failed: "
                    + json.dumps(diagnostics, sort_keys=True))


def _module():
    # Import only the current trusted source, never fixture/candidate modules.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    spec = importlib.util.spec_from_file_location("trusted_boundary_plan", Path(__file__).with_name("sandbox.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def diagnostic_snapshot(source, original, destination, policy):
    """Fixed real-Git fixture only; no application or arbitrary PR is run."""
    original.mkdir(mode=0o755)
    bodies = {"fixture.py": Path(__file__).with_name("sandbox_host_fixture.py").read_bytes(),
              "readonly-canary": b"public-readonly-canary\n"}
    for name in ("sandbox_probe.py", "runtime.py"):
        bodies["policy/tools/test-evidence/" + name] = Path(__file__).with_name(name).read_bytes()
    bodies["policy/readonly-canary"] = b"public-readonly-canary\n"
    for name, body in bodies.items():
        path = original / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        path.write_bytes(body)
    git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
           "-c", "commit.gpgsign=false", "-c", "user.name=Boundary diagnostic", "-c", "user.email=fixture@example.invalid"]
    for args in (("init", "-q", "--initial-branch=main"), ("add", "--all"), ("commit", "-qm", "Record fixed boundary fixture")):
        command([*git, *args], cwd=original).check_returncode()
    revision = command([*git, "rev-parse", "HEAD"], cwd=original).stdout.strip().decode("ascii")
    snapshot = source.materialize_snapshot(original, revision, destination)
    projection = source.project_policy(destination, policy, snapshot)
    return snapshot, projection


def verify_qualification_source(source, revision, *, root=ROOT):
    """Match actual loaded finite controls to the immutable manual source.

    A shallow trusted checkout is sufficient: no history traversal, candidate
    configuration, filters, hooks, refs or downloaded objects are consulted.
    """
    names = {*source.contract(root)["sources"], "tools/test-evidence/sandbox_host.py",
             "tools/test-evidence/sandbox_host_fixture.py", "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml",
             ".github/workflows/shared-sandbox-host-diagnostic.yml"}
    require(re.fullmatch(r"[0-9a-f]{40}", revision), "qualification source is not immutable")
    raw = source._git(root, "ls-tree", "-rz", "--full-tree", revision, "--", *sorted(names))
    seen = set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, separator, relative = entry.partition(b"\t")
        fields = metadata.split(b" ")
        require(separator and len(fields) == 3 and fields[:2] == [b"100644", b"blob"],
                "qualification source entry is missing, nonregular or executable")
        name = relative.decode("utf-8")
        require(name in names and name not in seen and re.fullmatch(rb"[0-9a-f]{40}", fields[2]),
                "qualification source inventory is ambiguous")
        seen.add(name)
        body = source._git(root, "cat-file", "blob", fields[2].decode("ascii"), limit=1_000_000)
        observed = source._git(root, "hash-object", "-t", "blob", "--stdin", input_bytes=body).strip()
        require(observed == fields[2] and body == source._source(root, name),
                "loaded qualification controls differ from the immutable manual source")
    require(seen == names, "immutable qualification controls are incomplete")


def validate_runtime(result, binding, environment, uid, gid):
    def fields(checks, message, details=None):
        failed = [name for name, valid in checks.items() if not valid]
        if failed:
            raise Unavailable(message + ": " + json.dumps({"failed": failed, **(details or {})},
                                                        sort_keys=True, ensure_ascii=True))

    def names(keys):
        # Report bounded public variable names, never unexpected values. Odd
        # or oversized keys receive only a digest; JSON escapes all controls.
        return [key if type(key) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key)
                else "sha256:" + hashlib.sha256(str(key).encode()).hexdigest()
                for key in sorted(keys, key=str)[:16]]

    if not (result["exit_code"] == 0 and result["reason"] is None
            and result["cleanup"] == {"kernel_populated": 0, "subtree_kill": True}):
        detail = {"exit_code": result["exit_code"], "reason": result["reason"], "cleanup": result["cleanup"],
                  "protected_probe_tail": _module().safe_diagnostic(result.get("diagnostic", b"")[-8192:])}
        raise Unavailable("protected runtime probe did not finish in an empty owned scope: "
                          + json.dumps(detail, sort_keys=True, ensure_ascii=True))
    observed = result["observation"]
    ordinary = type(observed) is dict
    fields({"observation": ordinary, "schema": ordinary and observed.get("schema") == 1,
            "authority": ordinary and observed.get("authority") == "none",
            "measurement": ordinary and observed.get("measurement") == "protected-boundary-profile",
            "reusable": ordinary and observed.get("reusable") is False,
            "runtime_compatibility": ordinary and observed.get("runtime_compatibility") == "unqualified"},
           "unqualified runtime observation is missing")
    identity, process = observed.get("identity"), observed.get("process")
    ordinary = type(identity) is dict
    actual_binding = identity.get("binding") if ordinary else None
    actual_environment = identity.get("environment") if ordinary else None
    files = identity.get("files") if ordinary else None
    differences = {}
    if type(actual_environment) is dict:
        expected, actual = set(environment), set(actual_environment)
        differences = {"missing": names(expected - actual), "extra": names(actual - expected),
                       "different": names(key for key in expected & actual if environment[key] != actual_environment[key]),
                       "expected_count": len(expected), "actual_count": len(actual)}
    fields({"identity": ordinary, "binding": actual_binding == binding,
            "environment": actual_environment == environment,
            "prefix": ordinary and identity.get("prefix") == "/opt/overte-ci/venv",
            "files": type(files) is dict, "file_count": type(files) is dict and len(files) >= 8,
            "file_digests": type(files) is dict and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
                                                       for value in files.values())},
           "runtime probe is not bound to the actual source, run, snapshot, projection and profile",
           {"environment_keys": differences, "file_count": len(files) if type(files) is dict else None,
            "binding_fields": [key for key in binding if type(actual_binding) is not dict
                               or actual_binding.get(key) != binding[key]]})
    fields({"process": type(process) is dict,
            "status": type(process) is dict and type(process.get("status")) is dict},
           "runtime process protection observation is missing")
    status = process["status"]
    fields({"NoNewPrivs": status.get("NoNewPrivs") == "1", "Uid": status.get("Uid", "").split() == [str(uid)] * 4,
            "Gid": status.get("Gid", "").split() == [str(gid)] * 4,
            **{key: status.get(key) == "0000000000000000" for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}},
           "protected runtime probe retained host privileges")
    return "sha256:" + hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def protected_launch(source, layout, snapshot, projection, scope, binding, plan_path, arguments, uid, gid, *, case, timeout=8):
    """Root-only diagnostic control flow, never a production launch API."""
    require(os.geteuid() == 0, "protected diagnostic launch requires actual root")
    source.verify_snapshot(layout.candidate, snapshot)
    source.verify_projection(layout.policy_source, projection)
    plan = source.build_plan(layout, arguments)
    plan_path.write_text(json.dumps(plan["argv"]), encoding="ascii")
    guardian = Guardian(scope, layout.protected, binding)
    try:
        observation = supervise(scope, plan_path, uid, gid, timeout=timeout, case=case)
        guardian.finish()
        source.verify_snapshot(layout.candidate, snapshot)
        source.verify_projection(layout.policy_source, projection)
        return observation
    finally:
        guardian.close()


def runtime_probe(scopes, launch, binding, environment, uid, gid):
    # No source/caller "empty" boolean can enter this path. These are the
    # actual already authenticated, held kernel scope descriptors.
    require(all(scope.populated() == 0 for scope in scopes.values()),
            "protected probe attempted before all owned scopes were empty")
    arguments = ["/opt/overte-ci/venv/bin/python", "-I", "/overte-policy/tools/test-evidence/sandbox_probe.py", "--boundary-diagnostic"]
    return validate_runtime(launch(arguments), binding, environment, uid, gid)


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
    verify_qualification_source(source, os.environ["GITHUB_SHA"])
    result = {"schema": 1, "status": "started", "authority": "none", "production_qualified": False,
              "source": os.environ["GITHUB_SHA"], "image": {name: os.environ[name] for name in ("ImageOS", "ImageVersion")},
              "kernel": os.uname().release, "tools": tools, "account_uid": uid, "cases": {}, "runtime_compatibility": "unqualified",
              "diagnostic_sources": {name: "sha256:" + hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                     for name in ("tools/test-evidence/sandbox_host.py", "tools/test-evidence/sandbox_host_fixture.py",
                                                  "tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml")}}
    with tempfile.TemporaryDirectory(prefix="overte-boundary-diagnostic-") as temporary, ExitStack() as stack:
        base = Path(temporary)
        base.chmod(0o755)
        paths = {name: base / name for name in ("candidate", "scratch", "policy", "venv", "protected")}
        for name, path in paths.items():
            path.mkdir(mode=0o700 if name in {"scratch", "protected"} else 0o755)
        os.chown(paths["scratch"], uid, gid)
        snapshot, projection = diagnostic_snapshot(source, base / "original", paths["candidate"], paths["policy"])
        command(["/usr/bin/python3", "-m", "venv", "--without-pip", str(paths["venv"])]).check_returncode()
        (paths["venv"] / "readonly-canary").write_text("public-readonly-canary\n", encoding="ascii")
        (paths["venv"] / "readonly-canary").chmod(0o666)
        git_canary = paths["candidate"] / ".git/config"
        expected_config = git_canary.read_bytes()
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
        # Allocate every immutable scope identity before sealing context. No
        # candidate/source/projection byte is rewritten between before/after.
        scopes = {}
        for case in (*CASES, "before", "after", "controller-death",
                     *("pair-" + case + "-" + str(slot) for case in ("protections", "cancel", "controller-death") for slot in (0, 1))):
            scope = scopes[case] = OwnedScope(uid, gid, delegated)
            stack.callback(scope.close)
            stack.callback(scope.kill_and_wait)
        binding = {"source": os.environ["GITHUB_SHA"], "run_id": int(os.environ["GITHUB_RUN_ID"]),
                   "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]), "snapshot": snapshot["digest"],
                   "projection": "sha256:" + hashlib.sha256(source._canonical(projection)).hexdigest()}
        projection = source.bind_projection(paths["policy"], projection, {"binding": binding,
            "fixture": {**context, "scope_directory": str(scopes["protections"].path)}})
        result["snapshot"] = {**snapshot["identity"], "digest": snapshot["digest"], "objects": snapshot["objects"]}
        result["binding"] = binding

        def launch(case, arguments, timeout=8):
            return protected_launch(source, layout, snapshot, projection, scopes[case], binding, base / "fixed-plan.json",
                                    arguments, uid, gid, timeout=timeout,
                                    case="probe" if case in {"before", "after"} else case)

        before = runtime_probe(scopes, lambda args: launch("before", args), binding, source._ENVIRONMENT, uid, gid)
        for case in CASES:
            observation = launch(case, ["/opt/overte-ci/venv/bin/python", "-I", "/work/fixture.py", case],
                                 timeout=4 if case == "timeout" else 8)
            validate_case(case, observation, outside)
            require(git_canary.read_bytes() == expected_config
                    and protected.read_text(encoding="ascii") == "diagnostic-canary-not-a-secret\n",
                    "outside protected source or report canary was altered")
            result["cases"][case] = {"status": "passed", "kernel_scope_empty": True,
                "live_before_cleanup": observation["live_before_cleanup"], "trusted_cleanup_canaries": observation["trusted_cleanup_canaries"]}
        source.verify_snapshot(paths["candidate"], snapshot)
        source.verify_projection(paths["policy"], projection)
        death_plan = source.build_plan(layout, ["/opt/overte-ci/venv/bin/python", "-I", "/work/fixture.py", "daemon"])
        death_path = base / "fixed-plan.json"
        death_path.write_text(json.dumps(death_plan["argv"]), encoding="ascii")
        scope = scopes["controller-death"]
        guardian = Guardian(scope, paths["protected"], binding)
        try:
            result["cases"]["controller-death"] = controller_death(scope, guardian, death_path, uid, gid)
        finally:
            guardian.close()
        for pair_case in ("protections", "cancel", "controller-death"):
            pair_scopes, pair_plans = [], []
            for slot in (0, 1):
                name = "pair-" + pair_case + "-" + str(slot)
                scratch = base / (name + "-scratch")
                scratch.mkdir(mode=0o700)
                os.chown(scratch, uid, gid)
                pair_layout = source.Layout(paths["candidate"], scratch, paths["policy"], paths["venv"], paths["protected"])
                arguments = ["/opt/overte-ci/venv/bin/python", "-I", "/work/fixture.py",
                             "pair-protections" if pair_case == "protections" else "daemon"]
                plan = base / (name + "-plan.json")
                plan.write_text(json.dumps(source.build_plan(pair_layout, arguments)["argv"]), encoding="ascii")
                pair_scopes.append(scopes[name])
                pair_plans.append(plan)
            source.verify_snapshot(paths["candidate"], snapshot)
            source.verify_projection(paths["policy"], projection)
            result["cases"]["pair-" + pair_case] = pair_boundary_case(
                pair_scopes, pair_plans, paths["protected"], binding, uid, gid, case=pair_case, outside=outside)
            require(git_canary.read_bytes() == expected_config
                    and protected.read_text(encoding="ascii") == "diagnostic-canary-not-a-secret\n",
                    "pair boundary changed an outside protected canary")
        # Every prior workload and canary is confirmed gone BEFORE starting a
        # separate fixed protected post-probe under the same effective profile.
        after = runtime_probe(scopes, lambda args: launch("after", args), binding, source._ENVIRONMENT, uid, gid)
        require(before == after, "protected runtime profile changed between before and post-kill observations")
        result["runtime_boundary"] = {"before": before, "after": after, "matching": True,
                                      "scope": "diagnostic-profile-only", "reusable": False}
        result.update(status="boundary-diagnostic-passed", contract=source.contract()["digest"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", nargs=3, metavar=("GATE_FD", "FIXED_PLAN", "FIXTURE_CASE"))
    parser.add_argument("--profile", choices=("boundary", "shared-host", "ci37"), default="boundary")
    arguments = parser.parse_args(argv)
    if arguments.bootstrap is not None:
        bootstrap(int(arguments.bootstrap[0]), arguments.bootstrap[1], arguments.bootstrap[2])
        return 1
    try:
        if arguments.profile in {"shared-host", "ci37"}:
            _shared_controller_module()
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import sandbox_shared
            result = sandbox_shared.run_host_ci37() if arguments.profile == "ci37" else sandbox_shared.run_host()
        else:
            result = run_host()
        code = 0
    except (Unavailable, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result = {"schema": 1, "status": "unavailable", "authority": "none", "production_qualified": False,
                  "error": str(error) if isinstance(error, Unavailable) else "required host diagnostic operation failed",
                  "failure": failure_summary(error)}
        code = 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
