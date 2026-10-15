#!/usr/bin/env python3
"""Dormant shared sandbox plans and supervisor controls, never reusable proof.

Stage A deliberately cannot launch a production sandbox or issue an execution
receipt. A bwrap exit is not proof that its PID namespace is empty. Host UID
provisioning, loopback initialization, kernel-owned process scopes and actual
host qualification are prerequisites, not assertions accepted from JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time

import runtime

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/shared-sandbox.json"
ACTIVATION_READY = False
REQUIREMENTS = (
    "separate-host-uid-without-sudo",
    "mandatory-user-mount-pid-ipc-uts-network-namespaces",
    "private-proc-without-host-processes",
    "no-new-privileges-and-no-capabilities",
    "readonly-source-git-policy-and-toolchains",
    "private-home-temp-and-build-output",
    "closed-inherited-descriptors-and-host-sockets",
    "loopback-only-network-with-nested-user-network-namespaces",
    "parent-owned-kernel-scope-and-confirmed-empty-descendants",
    "protected-before-after-runtime-probes-in-effective-sandbox",
    "complete-shared-host-suite-compatibility",
)
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_POLICY_FILES = (POLICY, "tools/test-evidence/sandbox.py", "tools/test-evidence/sandbox_probe.py", "tools/test-evidence/runtime.py")
_SYSTEM_DIRECTORIES = ("/usr",)
_SYSTEM_FILES = ("/etc/os-release", "/etc/ld.so.cache", "/etc/localtime", "/var/lib/dpkg/status")
_ENVIRONMENT = {
    "HOME": "/home/candidate", "TMPDIR": "/tmp", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
    "PATH": "/opt/overte-ci/venv/bin:/usr/bin:/bin", "VIRTUAL_ENV": "/opt/overte-ci/venv",
    "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
    "OVERTE_QML_TEST_RUNNER": "/usr/lib/qt6/bin/qmltestrunner",
    "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0",
}


class SandboxUnavailable(ValueError):
    """No qualified sandbox execution or reusable observation is available."""


def _require(condition, reason):
    if not condition:
        raise SandboxUnavailable(reason)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "sandbox policy contains duplicate fields")
        result[key] = value
    return result


def _directory(value):
    path = Path(value)
    _require(path.is_absolute() and path == Path(os.path.normpath(path)), "sandbox directory must be canonical")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        _require(not current.is_symlink(), "sandbox directory contains an alias")
    _require(path.is_dir() and path.resolve(strict=True) == path, "sandbox directory is unavailable")
    return path


def _source(root, relative):
    path = root / relative
    current = root
    for part in Path(relative).parts:
        current /= part
        _require(not current.is_symlink(), "sandbox policy source contains an alias")
    try:
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= 1_000_000, "sandbox policy source is unsupported")
        return path.read_bytes()
    except OSError as error:
        raise SandboxUnavailable("sandbox policy source is unavailable") from error


def load_policy(root=ROOT):
    root = _directory(root)
    try:
        policy = json.loads(_source(root, POLICY), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SandboxUnavailable("sandbox policy is invalid") from error
    expected = {"schema": 1, "profile": "ubuntu24-shared-bwrap-v1", "enabled": False,
                "qualified_hosts": [], "requirements": list(REQUIREMENTS)}
    _require(policy == expected and type(policy.get("schema")) is int and policy.get("enabled") is False,
             "sandbox policy is not the reviewed unqualified generation")
    return policy


def contract(root=ROOT):
    """Bind actual trusted bytes. This identity does not attest a running host."""
    root = _directory(root)
    policy = load_policy(root)
    sources = {name: "sha256:" + hashlib.sha256(_source(root, name)).hexdigest() for name in _POLICY_FILES}
    try:
        requirements, manifests = runtime._requirement_inventory(root)
    except runtime.RuntimeIdentityError as error:
        raise SandboxUnavailable("sandbox trusted requirement closure is unavailable") from error
    for name, expected in manifests.items():
        observed = "sha256:" + hashlib.sha256(_source(root, name)).hexdigest()
        _require(observed == expected, "sandbox trusted requirements changed during inspection")
        sources[name] = observed
    value = {"schema": 1, "profile": policy["profile"], "sources": sources,
             "requirements": policy["requirements"], "python_requirements": requirements, "qualification": "unavailable"}
    return {**value, "digest": "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()}


def _git(candidate, *arguments):
    # Do not inherit candidate/user Git configuration, helpers, replacement
    # objects, lazy fetch or pager behavior into an outside-sandbox process.
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
                   "GIT_TERMINAL_PROMPT": "0", "GIT_OBJECT_DIRECTORY": str(candidate / ".git/objects")}
    command = ["/usr/bin/git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
               "-c", "protocol.allow=never", "-c", "core.pager=cat", "-c", "maintenance.auto=false",
               "-c", "gc.auto=0", *arguments]
    try:
        # Never ask outside-sandbox Git to parse candidate .git/config at all.
        # A private bare metadata projection exposes only the checked immutable
        # object directory, with no candidate refs, includes, remotes or hooks.
        with tempfile.TemporaryDirectory(prefix="overte-protected-object-reader-") as directory:
            control = Path(directory)
            (control / "objects").mkdir()
            (control / "refs").mkdir()
            (control / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
            (control / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = true\n", encoding="ascii")
            return subprocess.run([*command[:1], "--git-dir", str(control), *command[1:]], cwd=control,
                                  env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise SandboxUnavailable("protected immutable Git read failed") from error


def pristine_git_identity(candidate, revision):
    """Read raw immutable objects, never status/diff or candidate-owned reports.

    This preliminary reader does not certify materialized worktree bytes. A
    production launcher must prepare and verify a private immutable snapshot,
    then mount its source AND Git metadata read-only for the entire execution.
    Linked/shared object stores and promisor metadata are unsupported here.
    """
    candidate = _directory(candidate)
    _require(isinstance(revision, str) and _SHA.fullmatch(revision) and set(revision) != {"0"},
             "sandbox candidate requires a full immutable revision")
    metadata = _directory(candidate / ".git")
    _directory(metadata / "objects")
    _directory(metadata / "objects/pack")
    _directory(metadata / "objects/info")
    for name in ("objects/info/alternates", "objects/info/http-alternates", "info/grafts", "shallow"):
        _require(not (metadata / name).exists() and not (metadata / name).is_symlink(),
                 "candidate Git metadata requires unsupported external or partial objects")
    _require(not any((metadata / "objects/pack").glob("*.promisor")), "candidate Git objects may require a fetch")
    # cat-file returns the actual commit body; replace refs/grafts must not
    # redefine its tree or ordered parents. No checkout filters are executed.
    size = _git(candidate, "cat-file", "-s", revision).strip()
    _require(len(size) <= 10 and re.fullmatch(rb"[0-9]+", size) and 0 < int(size) <= 1_000_000,
             "candidate commit object exceeds its bounded source metadata size")
    commit = _git(candidate, "cat-file", "commit", revision)
    _require(len(commit) == int(size), "candidate commit object changed during inspection")
    _require(hashlib.sha1(b"commit " + str(len(commit)).encode() + b"\0" + commit).hexdigest() == revision,
             "candidate commit object hash differs")
    try:
        header = commit.split(b"\n\n", 1)[0].splitlines()
        tree = header[0].removeprefix(b"tree ").decode("ascii")
        parents = [line[7:].decode("ascii") for line in header if line.startswith(b"parent ")]
        _require(header[0] == b"tree " + tree.encode("ascii") and _SHA.fullmatch(tree) and all(_SHA.fullmatch(v) for v in parents),
                 "candidate commit header is unsupported")
    except UnicodeError as error:
        raise SandboxUnavailable("candidate commit header is unsupported") from error
    return {"commit": revision, "tree": tree, "parents": parents}


@dataclass(frozen=True)
class Layout:
    candidate: Path
    scratch: Path
    policy_source: Path
    venv: Path
    protected: Path
    toolchains: tuple[Path, ...] = ()


def build_plan(layout, command, *, root=ROOT, environment=None):
    """Render fixed bwrap arguments for review, NOT a launch authorization.

    The future launcher must first establish a distinct real host UID and a
    protected kernel process scope. --uid alone only changes the namespace UID.
    Loopback initialization and complete effective-runtime capture remain
    unqualified. No arbitrary mounts, environment overrides or bwrap flags.
    """
    _require(type(layout) is Layout, "trusted sandbox layout is required")
    directories = [_directory(getattr(layout, name)) for name in ("candidate", "scratch", "policy_source", "venv", "protected")]
    _require(all(not left.is_relative_to(right) and not right.is_relative_to(left)
                 for index, left in enumerate(directories) for right in directories[index + 1:]),
             "writable, source, toolchain and protected directories must be disjoint")
    _directory(directories[0] / ".git")
    _require(not (directories[2] / ".git").exists(), "probe policy projection must not expose checkout metadata")
    _require(isinstance(command, (list, tuple)) and command and all(isinstance(v, str) and v and "\0" not in v for v in command),
             "sandbox command must be an explicit argument vector")
    # setup-node/Python/Java may be under hostedtoolcache. Mount ONLY the
    # independently identified version directory, never the whole cache.
    toolchains = []
    for value in layout.toolchains:
        path = _directory(value)
        _require(path.is_relative_to("/opt/hostedtoolcache") and len(path.parts) >= 5,
                 "sandbox toolchain is outside a versioned hosted toolcache directory")
        _require(all(not path.is_relative_to(other) and not other.is_relative_to(path) for other in directories + toolchains),
                 "sandbox toolchain overlaps another mount")
        toolchains.append(path)
    allowed = {"/opt/overte-ci/venv/bin/python", "/usr/bin/bash", "/usr/bin/node"}
    allowed.update(str(path / "bin/node") for path in toolchains)
    _require(command[0] in allowed, "sandbox entrypoint is outside the initial reviewed command inventory")
    effective = dict(_ENVIRONMENT)
    effective["PATH"] = ":".join(["/opt/overte-ci/venv/bin", *(str(path / "bin") for path in toolchains), "/usr/bin", "/bin"])
    _require(environment is None or isinstance(environment, dict), "sandbox environment is unsupported")
    for name, value in (environment or {}).items():
        if name in runtime._CHOICES:
            choices, _ = runtime._CHOICES[name]
            _require(type(value) is str and value in choices, "sandbox variant is unsupported")
            effective[name] = next(choice for choice in choices if choice == value)
        elif name in {"ImageOS", "ImageVersion", "RUNNER_ENVIRONMENT"}:
            pattern = {"ImageOS": r"ubuntu24", "ImageVersion": r"[0-9]+(?:\.[0-9]+)+", "RUNNER_ENVIRONMENT": r"github-hosted"}[name]
            _require(type(value) is str and re.fullmatch(pattern, value), "sandbox runner context is unsupported")
            effective[name] = value
        else:
            raise SandboxUnavailable("sandbox environment contains an unsupported override")
    args = ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts",
            "--new-session", "--die-with-parent", "--cap-drop", "ALL", "--clearenv"]
    for path in _SYSTEM_DIRECTORIES:
        args += ["--ro-bind", path, path]
    for target in ("bin", "sbin", "lib", "lib64"):
        args += ["--symlink", "usr/" + target, "/" + target]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home", "--dir", "/home/candidate"]
    for path in _SYSTEM_FILES:
        args += ["--ro-bind", path, path]
    for path in ("/etc/fonts", "/etc/alternatives"):
        args += ["--ro-bind", path, path]
    for path in toolchains:
        args += ["--ro-bind", str(path), str(path)]
    args += ["--ro-bind", str(directories[0]), "/work", "--bind", str(directories[1]), "/work/build",
             "--ro-bind", str(directories[2]), "/overte-policy", "--ro-bind", str(directories[3]), "/opt/overte-ci/venv"]
    for name, value in sorted(effective.items()):
        args += ["--setenv", name, value]
    args += ["--chdir", "/work", "--", *command]
    return {"schema": 1, "contract": contract(root), "launchable": False, "argv": args,
            "unresolved": list(REQUIREMENTS)}


def parse_scope_events(source):
    """Parse bounded cgroup.events bytes; parsed data is NOT scope ownership.

    A future privileged trusted launcher must open the actual parent-owned
    cgroup-v2 domain before any candidate can execute, forbid migration/write
    access, kill the scope and observe populated=0. Caller JSON, temporary
    files, process-group exit and bwrap exit cannot authorize a post-probe.
    """
    _require(type(source) is bytes and len(source) <= 4096, "kernel scope observation is unsupported")
    try:
        result = {}
        for line in source.decode("ascii").splitlines():
            _require(re.fullmatch(r"(?:populated|frozen) [01]", line), "kernel scope observation has unknown fields")
            name, value = line.split(" ")
            _require(name not in result, "kernel scope observation is ambiguous")
            result[name] = int(value)
        _require(set(result) == {"populated", "frozen"}, "kernel scope observation is incomplete")
        return result
    except UnicodeError as error:
        raise SandboxUnavailable("kernel scope observation is unsupported") from error


def capture_after_execution(*args, **kwargs):
    """No post-capture before real kernel-backed ownership/cleanup exists."""
    raise SandboxUnavailable("post-runtime capture requires a qualified parent-owned empty kernel scope")


def safe_diagnostic(data):
    """Encode arbitrary bytes as one ordinary log line, never Actions commands."""
    _require(isinstance(data, bytes) and len(data) <= 1_000_000, "diagnostic exceeds its bounded byte budget")
    # ensure_ascii escapes CR/LF, ESC and other control characters; the fixed
    # prefix prevents ::command:: and legacy command syntax at line start.
    return "candidate-output: " + json.dumps(data.decode("utf-8", errors="replace"), ensure_ascii=True)


def _diagnostic_process(command, *, timeout, limit=65536):
    """Private control-test supervisor; explicitly NOT a sandbox/evidence API.

    Process-group termination handles ordinary fixtures only. Detached sessions
    require the future kernel-owned scope, so neither exit zero nor EOF permits
    a post-runtime capture or a reusable successful execution receipt.
    """
    _require(isinstance(timeout, (int, float)) and 0 < timeout <= 30 and type(limit) is int and 0 < limit <= 1_000_000,
             "diagnostic supervisor bounds are unsupported")
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, close_fds=True, start_new_session=True)
    except OSError as error:
        raise SandboxUnavailable("diagnostic process could not start") from error
    output, reason = bytearray(), None
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while True:
            if time.monotonic() >= deadline:
                reason = "timeout"
                break
            events = selector.select(min(0.05, max(0, deadline - time.monotonic())))
            for key, _ in events:
                block = os.read(key.fileobj.fileno(), min(8192, limit + 1 - len(output)))
                if not block:
                    selector.unregister(key.fileobj)
                else:
                    output.extend(block)
                if len(output) > limit:
                    reason = "output-limit"
                    break
            if reason is not None or (process.poll() is not None and not selector.get_map()):
                break
    finally:
        # Always terminate the original group, even when its leader exited.
        # This still cannot certify that a malicious setsid child is dead.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        selector.close()
        process.stdout.close()
    return {"exit_code": process.returncode, "reason": reason, "diagnostic": safe_diagnostic(bytes(output[:limit])),
            "descendants_empty": None, "post_runtime": None, "reusable": False}


def execute(*args, **kwargs):
    """No policy flag, supplied probe JSON or caller boolean enables execution."""
    raise SandboxUnavailable("sandbox execution is unqualified: host UID, kernel scope, loopback and effective runtime require trusted host verification")
