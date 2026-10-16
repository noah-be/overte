#!/usr/bin/env python3
"""Shared sandbox plans and supervisor controls, never reusable proof.

The legacy execute/capture entrypoints cannot launch a production sandbox or
issue an execution receipt. A bwrap exit is not proof that its PID namespace is
empty. Host UID provisioning, loopback initialization, kernel-owned process
scopes and actual host qualification are prerequisites, not JSON assertions.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import tempfile
import time
import zlib

import runtime

ROOT = Path(__file__).resolve().parents[2]
POLICY = ".github/shared-sandbox.json"
# Protected producer source capability only. The legacy entrypoints below stay
# unavailable even after a separately reviewed activation of this capability.
ACTIVATION_READY = True
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
    "HOME": "/home/candidate", "TMPDIR": "/tmp", "PWD": "/work", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
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
    """Read the fixed diagnostic/legacy identity, never production permission.

    enabled:false and qualified_hosts:[] deliberately remain exact. Production
    uses the protected supervisor's independent native/runtime/kernel checks;
    supplying a host assertion or enabled JSON cannot authorize that path.
    """
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


def require_protected_execution(root=ROOT):
    """Admit only a reviewed source capability; this does not prove execution."""
    _require(ACTIVATION_READY is True, "protected sandbox execution is not qualified")
    # Preserve the diagnostic contract used by the actual fixed namespace
    # plan. Its disabled JSON is an identity, not the protected permission.
    load_policy(root)


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


def _git(candidate, *arguments, input_bytes=None, limit=2_000_000, index_result=False, timeout=10, bounded=False):
    # Do not inherit candidate/user Git configuration, helpers, replacement
    # objects, lazy fetch or pager behavior into an outside-sandbox process.
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
                   "GIT_TERMINAL_PROMPT": "0", "GIT_OBJECT_DIRECTORY": str(candidate / ".git/objects")}
    command = ["/usr/bin/git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
               "-c", "protocol.allow=never", "-c", "core.pager=cat", "-c", "maintenance.auto=false",
               "-c", "gc.auto=0", *arguments]
    _require(type(limit) is int and 0 < limit <= 16_000_000, "protected Git output bound is unsupported")
    _require(type(timeout) in (int, float) and 0 < timeout <= 120 and type(bounded) is bool,
             "protected Git process bounds are unsupported")
    _require(index_result is False or (index_result is True and len(arguments) == 2
             and arguments[0] == "read-tree" and _SHA.fullmatch(arguments[1])), "private Git index request is unsupported")
    _require(input_bytes is None or (type(input_bytes) is bytes and len(input_bytes) <= 16_000_000),
             "protected Git input exceeds its source metadata bound")
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
            with tempfile.TemporaryFile() as incoming:
                if input_bytes is not None:
                    incoming.write(input_bytes)
                    incoming.seek(0)
                process = subprocess.Popen([*command[:1], "--git-dir", str(control), *command[1:]], cwd=control,
                                           env=environment, stdin=incoming, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
                output, deadline = bytearray(), time.monotonic() + timeout
                selector = selectors.DefaultSelector()
                selector.register(process.stdout, selectors.EVENT_READ)
                try:
                    if bounded:
                        _git_limits(process.pid)
                    while selector.get_map():
                        _require(time.monotonic() < deadline, "protected immutable Git read timed out")
                        for key, _ in selector.select(0.02):
                            block = os.read(key.fileobj.fileno(), min(65536, limit + 1 - len(output)))
                            if not block:
                                selector.unregister(key.fileobj)
                            output.extend(block)
                            _require(len(output) <= limit, "protected immutable Git read exceeds bound")
                    _require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0,
                             "protected immutable Git read failed")
                    if index_result:
                        index = control / "index"
                        _require(not output and index.is_file() and index.stat().st_size <= limit,
                                 "private immutable Git index is unavailable")
                        return index.read_bytes()
                    return bytes(output)
                finally:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait(timeout=3)
                    process.stdout.close()
                    selector.close()
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
    return _raw_commit_identity(candidate, revision)


def _raw_commit_identity(candidate, revision, *, deadline=None):
    # cat-file returns the actual commit body; replace refs/grafts must not
    # redefine its tree or ordered parents. No checkout filters are executed.
    def read(*arguments, **kwargs):
        if deadline is not None:
            remaining = deadline - time.monotonic()
            _require(remaining > 0, "snapshot identity deadline exceeded")
            kwargs["timeout"] = min(10, remaining)
        return _git(candidate, *arguments, **kwargs)
    size = read("cat-file", "-s", revision).strip()
    _require(len(size) <= 10 and re.fullmatch(rb"[0-9]+", size) and 0 < int(size) <= 1_000_000,
             "candidate commit object exceeds its bounded source metadata size")
    commit = read("cat-file", "commit", revision)
    _require(len(commit) == int(size), "candidate commit object changed during inspection")
    # This is Git's public object identity, not a security hash. Ask the fixed
    # protected Git binary to check it without writing any object or metadata.
    observed = read("hash-object", "-t", "commit", "--stdin", input_bytes=commit).strip()
    _require(re.fullmatch(rb"[0-9a-f]{40}", observed) and observed.decode("ascii") == revision,
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


def _snapshot_path(name):
    _require(type(name) is str and name and len(name) <= 4096 and "\\" not in name and "\0" not in name,
             "snapshot path is unsupported")
    _require(all(part not in {"", ".", "..", ".git"} for part in name.split("/"))
             and not name.startswith("/"), "snapshot path escapes its immutable source")
    return name


def _file_hash(path, *, deadline=None):
    digest = hashlib.sha256()
    with path.open("rb") as incoming:
        while block := incoming.read(65536):
            _require(deadline is None or time.monotonic() < deadline, "snapshot file digest deadline exceeded")
            digest.update(block)
    return digest.hexdigest()


def _files(root, *, streamed=False, deadline=None):
    """Complete negative inventory, including metadata; never follow aliases."""
    result, total = {}, 0
    maximum, count = (65 * 1024 * 1024, 65536) if streamed else (16_000_000, 20000)
    info = root.lstat()
    _require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o755,
             "snapshot root is not a private ordinary directory")
    for directory, children, names in os.walk(root, followlinks=False):
        for name in children + names:
            _require(deadline is None or time.monotonic() < deadline, "snapshot inventory deadline exceeded")
            path = Path(directory) / name
            info = path.lstat()
            _require(len(result) < count, "snapshot inventory exceeds bound")
            _require(not stat.S_ISLNK(info.st_mode) and info.st_uid == os.geteuid(),
                     "snapshot contains an alias or foreign-owned entry")
            if stat.S_ISDIR(info.st_mode):
                _require(stat.S_IMODE(info.st_mode) == 0o755, "snapshot directory is mutable or unsupported")
                result[path.relative_to(root).as_posix()] = {"directory": True}
                continue
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= maximum
                     and stat.S_IMODE(info.st_mode) in {0o444, 0o555}, "snapshot file is not private immutable ordinary source")
            total += info.st_size
            _require(not streamed or total <= 4 * 1024 ** 3, "snapshot filesystem byte budget exceeded")
            result[path.relative_to(root).as_posix()] = {
                "mode": stat.S_IMODE(info.st_mode), "size": info.st_size,
                "sha256": _file_hash(path, deadline=deadline)}
    return result


def _write_source(root, name, data, executable=False):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    with path.open("xb") as target:
        target.write(data)
    path.chmod(0o555 if executable else 0o444)


_STREAMED_PROFILE = "streamed-candidate-source-v1"
_STREAMED_OBJECTS = 32768
_STREAMED_BYTES = 2 * 1024 ** 3
_STREAMED_BLOB = 64 * 1024 ** 2
_STREAMED_SECONDS = 300


def _git_limits(pid):
    # Install the limits before sending any object request to the idle reader.
    # The helper is Linux-only and fails closed if prlimit is unavailable.
    resource.prlimit(pid, resource.RLIMIT_AS, (512 * 1024 ** 2,) * 2)
    resource.prlimit(pid, resource.RLIMIT_CPU, (120, 120))
    resource.prlimit(pid, resource.RLIMIT_NOFILE, (64, 64))


class _StreamedObjects:
    """One protected Git reader; bounded chunks and one fetch per object ID."""
    def __init__(self, candidate, spool, destination, deadline):
        self.spool, self.destination, self.deadline = spool, destination, deadline
        self.objects, self.buffer, self.total, self.metadata = {}, bytearray(), 0, 0
        self.body_hashes, self.stored = {}, {}
        control = spool / "control"
        control.mkdir()
        for name in ("objects", "refs"):
            (control / name).mkdir()
        (control / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
        (control / "config").write_text("[core]\nbare = true\nrepositoryformatversion = 0\n", encoding="ascii")
        command = ["/usr/bin/git", "--git-dir", str(control), "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
                   "-c", "core.fsmonitor=false", "-c", "protocol.allow=never", "-c", "maintenance.auto=false", "-c", "gc.auto=0",
                   "-c", "core.deltaBaseCacheLimit=16m", "-c", "core.packedGitLimit=128m", "-c", "core.packedGitWindowSize=16m",
                   "cat-file", "--batch"]
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
                       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
                       "GIT_TERMINAL_PROMPT": "0", "GIT_OBJECT_DIRECTORY": str(candidate / ".git/objects")}
        self.process = subprocess.Popen(command, cwd=control, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        self.selector = selectors.DefaultSelector()
        try:
            _git_limits(self.process.pid)
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.wait(timeout=3)
        self.process.stdin.close()
        self.process.stdout.close()
        self.selector.close()

    def fill(self):
        remaining = self.deadline - time.monotonic()
        _require(remaining > 0, "streamed snapshot deadline exceeded")
        if self.selector.select(min(0.05, remaining)):
            block = os.read(self.process.stdout.fileno(), 65536)
            _require(block, "protected streamed Git reader ended early")
            self.buffer.extend(block)

    def take(self, size):
        while len(self.buffer) < size:
            self.fill()
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def read(self, oid, kind):
        if oid in self.objects:
            _require(self.objects[oid][0] == kind, "streamed snapshot object type differs")
            return self.objects[oid][1:]
        _require(type(oid) is str and _SHA.fullmatch(oid) and len(self.objects) < _STREAMED_OBJECTS,
                 "streamed snapshot object inventory exceeds bound")
        _require(os.write(self.process.stdin.fileno(), (oid + "\n").encode("ascii")) == 41, "Git object request failed")
        while b"\n" not in self.buffer:
            _require(len(self.buffer) <= 160, "Git object response header exceeds bound")
            self.fill()
        length = self.buffer.index(b"\n")
        _require(length <= 160, "Git object response header exceeds bound")
        fields = self.take(length + 1).strip().split(b" ")
        _require(len(fields) == 3 and fields[:2] == [oid.encode("ascii"), kind.encode("ascii")]
                 and re.fullmatch(rb"[0-9]{1,10}", fields[2]), "Git object response has wrong identity or type")
        size = int(fields[2])
        maximum = _STREAMED_BLOB if kind == "blob" else 4 * 1024 ** 2 if kind == "tree" else 1_000_000
        self.total += size
        if kind != "blob":
            self.metadata += size
        _require(size <= maximum and self.total <= _STREAMED_BYTES and self.metadata <= 32 * 1024 ** 2,
                 "streamed snapshot object byte budget exceeded")
        raw = self.spool / (kind + "-" + oid)
        target = self.destination / ".git/objects" / oid[:2] / oid[2:]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        compressor = zlib.compressobj(1)
        body_hash, stored_hash, stored_size = hashlib.sha256(), hashlib.sha256(), 0
        with raw.open("xb") as output, target.open("xb") as packed:
            def store(block):
                nonlocal stored_size
                _require(packed.write(block) == len(block), "private object write was incomplete")
                stored_hash.update(block)
                stored_size += len(block)
            store(compressor.compress(kind.encode("ascii") + b" " + str(size).encode("ascii") + b"\0"))
            remaining = size
            while remaining:
                block = self.take(min(65536, remaining))
                _require(output.write(block) == len(block), "private source spool write was incomplete")
                body_hash.update(block)
                store(compressor.compress(block))
                remaining -= len(block)
            store(compressor.flush())
        target.chmod(0o444)
        _require(self.take(1) == b"\n", "Git object response has invalid framing")
        self.objects[oid] = (kind, raw, size)
        self.body_hashes[oid] = body_hash.hexdigest()
        self.stored[target.relative_to(self.destination).as_posix()] = {
            "mode": 0o444, "size": stored_size, "sha256": stored_hash.hexdigest()}
        return raw, size

    def verify(self):
        # Three bounded Git invocations hash private ordinary spool files. No
        # checkout/filter executes, and no blob is loaded into Python memory.
        # Git also validates .gitmodules referenced by a tree. Resolve those
        # objects from the complete private stream, never reopen source packs
        # whose mmap window may exceed this verifier's address-space bound.
        for kind in ("commit", "tree", "blob"):
            items = [(oid, path) for oid, (actual, path, _size) in self.objects.items() if actual == kind]
            if not items:
                continue
            paths = "".join(str(path) + "\n" for _oid, path in items).encode("ascii")
            remaining = self.deadline - time.monotonic()
            _require(remaining > 0, "streamed snapshot verification deadline exceeded")
            observed = _git(self.destination, "hash-object", "-t", kind, "--no-filters", "--stdin-paths", input_bytes=paths,
                            limit=len(items) * 41, timeout=min(120, remaining), bounded=True)
            _require(observed.splitlines() == [oid.encode("ascii") for oid, _path in items], "streamed object hash differs")


def materialize_candidate_snapshot(candidate, revision, destination, *, context_revisions=()):
    """Prepare source only; this does not authorize execution or evidence.

    Only explicitly named commits and their complete trees enter the private
    object store. Raw ordered parents remain truthful; every included commit
    with an omitted parent is marked as a shallow boundary. Never traverse or
    silently fabricate unavailable history. The legacy diagnostic is unchanged.
    """
    candidate, destination = _directory(candidate), _directory(destination)
    _require(not any(destination.iterdir()) and not destination.is_relative_to(candidate)
             and not candidate.is_relative_to(destination), "snapshot destination must be private, empty and disjoint")
    _require(type(context_revisions) is tuple and len(context_revisions) <= 7,
             "streamed Git context requires at most eight explicit commits")
    revisions = (revision, *context_revisions)
    _require(all(type(oid) is str and _SHA.fullmatch(oid) and set(oid) != {"0"} for oid in revisions)
             and len(set(revisions)) == len(revisions), "streamed Git context contains invalid or duplicate revisions")
    metadata = _directory(candidate / ".git")
    for name in ("objects", "objects/pack", "objects/info"):
        _directory(metadata / name)
    for name in ("objects/info/alternates", "objects/info/http-alternates", "info/grafts"):
        _require(not (metadata / name).exists() and not (metadata / name).is_symlink(), "external Git objects are unsupported")
    _require(not any((metadata / "objects/pack").glob("*.promisor")), "lazy Git objects are unsupported")
    if (metadata / "shallow").exists() or (metadata / "shallow").is_symlink():
        raw = _source(metadata, "shallow")
        _require(raw and all(re.fullmatch(rb"[0-9a-f]{40}", row) for row in raw.splitlines()), "source shallow metadata is unsupported")
    deadline = time.monotonic() + _STREAMED_SECONDS
    commits, trees, source_files, expanded, materialized = {}, {}, {}, 0, 0
    with tempfile.TemporaryDirectory(prefix="overte-streamed-objects-", dir="/tmp") as directory:
        reader = _StreamedObjects(candidate, Path(directory), destination, deadline)
        try:
            def tree(oid, prefix="", write=False):
                nonlocal expanded, materialized
                _require(prefix.count("/") < 128, "streamed snapshot nesting exceeds bound")
                if oid not in trees:
                    path, _size = reader.read(oid, "tree")
                    data, entries, names, position = path.read_bytes(), [], set(), 0
                    while position < len(data):
                        end = data.find(b"\0", position)
                        _require(end >= position and end + 21 <= len(data), "streamed tree entry is incomplete")
                        header = data[position:end]
                        mode, separator, raw_name = header.partition(b" ")
                        try:
                            name = raw_name.decode("utf-8")
                        except UnicodeError as error:
                            raise SandboxUnavailable("streamed tree path is unsupported") from error
                        _require(separator and name not in names and "/" not in name, "streamed tree entry is ambiguous")
                        names.add(name)
                        _snapshot_path(name)
                        _require(mode in {b"40000", b"100644", b"100755"}, "streamed tree contains symlink, gitlink or unsupported mode")
                        entries.append((mode, name, data[end + 1:end + 21].hex()))
                        position = end + 21
                    trees[oid] = entries
                for mode, name, child in trees[oid]:
                    expanded += 1
                    _require(expanded <= 65536, "streamed tree expansion exceeds bound")
                    relative = _snapshot_path(prefix + name)
                    if mode == b"40000":
                        if write:
                            (destination / relative).mkdir(mode=0o755)
                            source_files[relative] = {"directory": True}
                        tree(child, relative + "/", write)
                    else:
                        raw, size = reader.read(child, "blob")
                        if write:
                            materialized += size
                            _require(materialized <= 1024 ** 3, "materialized source exceeds byte budget")
                            with raw.open("rb") as incoming, (destination / relative).open("xb") as output:
                                while block := incoming.read(65536):
                                    _require(time.monotonic() < deadline, "source materialization deadline exceeded")
                                    output.write(block)
                            (destination / relative).chmod(0o555 if mode == b"100755" else 0o444)
                            source_files[relative] = {"mode": 0o555 if mode == b"100755" else 0o444,
                                                      "size": size, "sha256": reader.body_hashes[child]}
            for oid in revisions:
                path, _size = reader.read(oid, "commit")
                header = path.read_bytes().split(b"\n\n", 1)[0].splitlines()
                _require(header and re.fullmatch(rb"tree [0-9a-f]{40}", header[0]), "streamed commit tree is unsupported")
                parents = []
                for row in header[1:]:
                    if row.startswith(b"parent "):
                        _require(re.fullmatch(rb"parent [0-9a-f]{40}", row), "streamed commit parent is unsupported")
                        parents.append(row[7:].decode("ascii"))
                commits[oid] = {"commit": oid, "tree": header[0][5:].decode("ascii"), "parents": parents}
                tree(commits[oid]["tree"], write=oid == revision)
            reader.verify()
            objects = len(reader.objects)
            stored = dict(reader.stored)
        finally:
            reader.close()
    _require(not (destination / "build").exists(), "private build mount would hide tracked source inputs")
    (destination / "build").mkdir(mode=0o755)
    source_files["build"] = {"directory": True}
    expected_files = dict(source_files)
    expected_files.update(stored)
    for path in stored:
        expected_files[str(Path(path).parent)] = {"directory": True}
    expected_files[".git"] = {"directory": True}
    expected_files[".git/objects"] = {"directory": True}
    for name in (".git/objects/pack", ".git/objects/info", ".git/refs"):
        (destination / name).mkdir(parents=True, exist_ok=True, mode=0o755)
        expected_files[name] = {"directory": True}
    def metadata_file(name, body):
        _write_source(destination, name, body)
        expected_files[name] = {"mode": 0o444, "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    shallow = sorted(oid for oid, item in commits.items() if set(item["parents"]) - commits.keys())
    metadata_file(".git/HEAD", (revision + "\n").encode("ascii"))
    metadata_file(".git/config", b"[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = true\n")
    if shallow:
        metadata_file(".git/shallow", ("\n".join(shallow) + "\n").encode("ascii"))
    remaining = deadline - time.monotonic()
    _require(remaining > 0, "streamed snapshot index deadline exceeded")
    metadata_file(".git/index", _git(destination, "read-tree", revision, index_result=True,
                  limit=8_000_000, timeout=min(120, remaining), bounded=True))
    _require(_files(destination, streamed=True, deadline=deadline) == expected_files,
             "materialized source or private Git bytes differ from the verified object stream")
    value = {"profile": _STREAMED_PROFILE, "identity": commits[revision], "objects": objects,
             "git_context": {"commits": commits, "shallow": shallow},
             "files": expected_files}
    value["digest"] = "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()
    return value


def materialize_snapshot(candidate, revision, destination):
    """Copy verified raw Git objects, never checkout hooks/config/filters.

    This bounded diagnostic implementation supports complete ordinary Git
    histories only (4096 objects/64 MB). Unsupported real candidates fail;
    no shallow/alternate/promisor, symlink or gitlink fallback is available.
    The returned inventory is retained by the protected parent, never loaded
    from a candidate report. Read-only mounts enforce it during execution.
    """
    candidate, destination = _directory(candidate), _directory(destination)
    _require(not any(destination.iterdir()) and not destination.is_relative_to(candidate)
             and not candidate.is_relative_to(destination), "snapshot destination must be private, empty and disjoint")
    identity = pristine_git_identity(candidate, revision)
    objects, total, entries = {}, 0, 0

    def read(oid, kind):
        nonlocal total
        if oid in objects:
            _require(objects[oid][0] == kind, "snapshot object type is ambiguous")
            return objects[oid][1]
        _require(_SHA.fullmatch(oid) and len(objects) < 4096, "snapshot object inventory is unsupported")
        size = _git(candidate, "cat-file", "-s", oid).strip()
        _require(re.fullmatch(rb"[0-9]{1,8}", size) and int(size) <= 16_000_000, "snapshot object exceeds bound")
        total += int(size)
        _require(total <= 64_000_000, "snapshot reachable objects exceed bound")
        data = _git(candidate, "cat-file", kind, oid, limit=max(1, int(size)))
        _require(len(data) == int(size), "snapshot object changed during inspection")
        observed = _git(candidate, "hash-object", "-t", kind, "--stdin", input_bytes=data).strip()
        _require(observed == oid.encode("ascii"), "snapshot object identity differs")
        objects[oid] = (kind, data)
        return data

    def tree(oid, prefix="", materialize=False):
        nonlocal entries
        _require(prefix.count("/") < 128, "snapshot tree nesting exceeds bound")
        data = read(oid, "tree")
        seen = set()
        while data:
            entries += 1
            _require(entries <= 20000, "snapshot tree inventory exceeds bound")
            header, separator, rest = data.partition(b"\0")
            _require(separator and len(rest) >= 20, "snapshot tree entry is incomplete")
            mode, separator, raw_name = header.partition(b" ")
            try:
                name = raw_name.decode("utf-8")
            except UnicodeError as error:
                raise SandboxUnavailable("snapshot tree name is unsupported") from error
            _require(separator and name not in seen and "/" not in name, "snapshot tree entry is ambiguous")
            seen.add(name)
            relative = _snapshot_path(prefix + name)
            child, data = rest[:20].hex(), rest[20:]
            if mode == b"40000":
                if materialize:
                    (destination / relative).mkdir(mode=0o755)
                tree(child, relative + "/", materialize)
            else:
                _require(mode in {b"100644", b"100755"}, "snapshot contains a symlink, gitlink or unsupported mode")
                body = read(child, "blob")
                if materialize:
                    _write_source(destination, relative, body, mode == b"100755")

    pending, commits = [revision], set()
    while pending:
        oid = pending.pop()
        if oid in commits:
            continue
        commits.add(oid)
        header = read(oid, "commit").split(b"\n\n", 1)[0].splitlines()
        _require(header and re.fullmatch(rb"tree [0-9a-f]{40}", header[0]), "snapshot commit is unsupported")
        tree(header[0][5:].decode("ascii"))
        for line in header[1:]:
            if line.startswith(b"parent "):
                _require(re.fullmatch(rb"parent [0-9a-f]{40}", line), "snapshot parent is unsupported")
                pending.append(line[7:].decode("ascii"))
    tree(identity["tree"], materialize=True)
    _require(not (destination / "build").exists(), "private build mount would hide tracked source inputs")
    (destination / "build").mkdir(mode=0o755)
    for name in (".git/objects/pack", ".git/objects/info", ".git/refs"):
        (destination / name).mkdir(parents=True, exist_ok=True, mode=0o755)
    _write_source(destination, ".git/HEAD", (revision + "\n").encode("ascii"))
    _write_source(destination, ".git/config", b"[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = true\n")
    for oid, (kind, body) in objects.items():
        raw = kind.encode("ascii") + b" " + str(len(body)).encode("ascii") + b"\0" + body
        _write_source(destination, ".git/objects/" + oid[:2] + "/" + oid[2:], zlib.compress(raw))
    # Build an actual pristine index in the protected temporary control repo,
    # without checking out, parsing candidate configuration or running filters.
    # Ordinary Git commands in the eventual read-only sandbox then see the
    # truthful detached source rather than an absent-index deletion illusion.
    index = _git(destination, "read-tree", revision, index_result=True)
    _write_source(destination, ".git/index", index)
    inventory = _files(destination)
    value = {"identity": identity, "files": inventory, "objects": len(objects)}
    value["digest"] = "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()
    verify_snapshot(destination, value)
    return value


def verify_snapshot(destination, expected):
    """Only the protected parent's retained inventory is a valid comparator."""
    destination = _directory(destination)
    if "profile" in expected:
        deadline = time.monotonic() + _STREAMED_SECONDS
        _require(expected["profile"] == _STREAMED_PROFILE, "unknown snapshot profile")
        unsigned = {name: value for name, value in expected.items() if name != "digest"}
        _require(expected.get("digest") == "sha256:" + hashlib.sha256(_canonical(unsigned)).hexdigest(),
                 "streamed snapshot context digest differs")
        _require(_files(destination, streamed=True, deadline=deadline) == expected["files"],
                 "immutable snapshot or its negative inventory changed")
        context = expected["git_context"]
        _require(type(context) is dict and set(context) == {"commits", "shallow"} and type(context["commits"]) is dict
                 and 0 < len(context["commits"]) <= 8 and expected["identity"] == context["commits"].get(expected["identity"]["commit"]),
                 "streamed snapshot Git context is incomplete")
        commits = context["commits"]
        for oid, identity in commits.items():
            _require(type(oid) is str and _SHA.fullmatch(oid) and _raw_commit_identity(destination, oid, deadline=deadline) == identity,
                     "streamed snapshot commit or ordered parents changed")
        shallow = sorted(oid for oid, identity in commits.items() if set(identity["parents"]) - commits.keys())
        _require(context["shallow"] == shallow, "streamed snapshot has an untruthful history boundary")
        path = destination / ".git/shallow"
        _require(path.read_bytes() == ("\n".join(shallow) + "\n").encode("ascii") if shallow else not path.exists(),
                 "streamed snapshot shallow metadata changed")
        return
    _require(_files(destination) == expected["files"], "immutable snapshot or its negative inventory changed")
    _require(pristine_git_identity(destination, expected["identity"]["commit"]) == expected["identity"],
             "private pristine Git identity changed")


PROJECTION_FILES = ("tools/test-evidence/sandbox_probe.py", "tools/test-evidence/runtime.py", "readonly-canary")
_PROJECTION_INVENTORY = {*PROJECTION_FILES, "tools", "tools/test-evidence"}


def project_policy(snapshot, destination, expected, *, root=ROOT):
    """Project only exact trusted source bytes, never candidate policy code."""
    verify_snapshot(snapshot, expected)
    destination = _directory(destination)
    _require(not any(destination.iterdir()), "policy projection must start empty")
    for name in PROJECTION_FILES:
        data = (snapshot / "policy" / name).read_bytes()
        trusted = b"public-readonly-canary\n" if name == "readonly-canary" else _source(_directory(root), name)
        _require(data == trusted, "candidate cannot supply the protected policy implementation")
        _write_source(destination, name, data)
    inventory = _files(destination)
    _require(set(inventory) == _PROJECTION_INVENTORY, "policy projection has unknown inputs")
    return inventory


def verify_projection(destination, expected):
    _require(_files(_directory(destination)) == expected
             and set(expected) in (_PROJECTION_INVENTORY, _PROJECTION_INVENTORY | {"context.json"}),
             "source-only policy projection changed")


def bind_projection(destination, expected, context):
    """Add only parent-created diagnostic context before any workload starts."""
    verify_projection(destination, expected)
    _require(set(expected) == _PROJECTION_INVENTORY, "diagnostic context is already sealed")
    _write_source(destination, "context.json", _canonical(context))
    return _files(destination)


@dataclass(frozen=True)
class Layout:
    candidate: Path
    scratch: Path
    policy_source: Path
    venv: Path
    protected: Path
    toolchains: tuple[Path, ...] = ()


def build_plan(layout, command, *, root=ROOT, environment=None, runtime_profile='ubuntu24-host-qt5-qt6-v1'):
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
    _require(runtime_profile in {'ubuntu24-host-qt5-qt6-v1','ubuntu24-ci37-v1'}, 'unknown sandbox runtime profile')
    if runtime_profile == 'ubuntu24-ci37-v1':
        for name in ('QT_QPA_PLATFORM','QT_QUICK_BACKEND','OVERTE_QML_TEST_RUNNER'):
            effective.pop(name)
    effective["PATH"] = ":".join(["/opt/overte-ci/venv/bin", *(str(path / "bin") for path in toolchains), "/usr/bin", "/bin"])
    _require(environment is None or isinstance(environment, dict), "sandbox environment is unsupported")
    for name, value in (environment or {}).items():
        if name in runtime._CHOICES and runtime_profile == 'ubuntu24-host-qt5-qt6-v1':
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
