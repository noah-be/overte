#!/usr/bin/env python3
"""Fixed hostile diagnostic fixtures; never arbitrary PR/test execution.

Only the reviewed host diagnostic copies these exact bytes into a read-only
source mount. Results are observations for that diagnostic, not test receipts.
No credentials, arbitrary environment or file contents are printed.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def inaccessible(path, write=False):
    try:
        descriptor = os.open(path, (os.O_WRONLY if write else os.O_RDONLY) | os.O_CLOEXEC)
    except OSError:
        return True
    os.close(descriptor)
    return False


def readonly(path):
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CLOEXEC)
    except OSError as error:
        if error.errno not in {errno.EROFS, errno.EACCES}:
            return False
        # A protected canary can fail DAC before the read-only mount check.
        # Require the kernel's read-only flag at this exact path as well.
        try:
            return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
        except OSError:
            return False
    os.close(descriptor)
    return False


def loopback():
    with socket.socket() as server, socket.socket() as client:
        server.settimeout(1)
        client.settimeout(1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        client.connect(server.getsockname())
        peer, _ = server.accept()
        with peer:
            peer.settimeout(1)
            client.sendall(b"private-loopback")
            return peer.recv(32) == b"private-loopback"


def protections(context):
    values = {}
    for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
        name, _, value = line.partition(":")
        if name in {"NoNewPrivs", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"}:
            values[name] = value.strip()
    # The immutable root-owned snapshot is deliberately owned by another host
    # UID. Admit only its fixed in-sandbox path for this diagnostic command;
    # never disable ownership protection globally or mutate the pristine index.
    git = subprocess.run(["/usr/bin/git", "-c", "safe.directory=/work", "-c", "core.fsmonitor=false",
                          "-c", "core.hooksPath=/dev/null", "--no-optional-locks", "status", "--porcelain", "--untracked-files=all"],
                         cwd="/work", stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
    result = {
        "git_pristine": git.returncode == 0 and git.stdout == b"",
        "process": values,
        "namespaces": {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("user", "mnt", "pid", "net", "ipc", "uts")},
        "uid_map": Path("/proc/self/uid_map").read_text(encoding="ascii"),
        "parent_proc_hidden": inaccessible("/proc/" + str(context["parent_pid"]) + "/environ"),
        "protected_read_hidden": inaccessible(context["protected_canary"]),
        "protected_write_hidden": inaccessible(context["protected_canary"], True),
        "command_files_hidden": all(inaccessible(path) and inaccessible(path, True) for path in context["command_files"]),
        "scope_hidden": inaccessible(context["scope_directory"] + "/cgroup.procs", True),
        "source_readonly": readonly("/work/readonly-canary"),
        "git_readonly": readonly("/work/.git/config"),
        "venv_readonly": readonly("/opt/overte-ci/venv/readonly-canary"),
        "policy_readonly": readonly("/overte-policy/readonly-canary"),
        "loopback": loopback(),
        "only_loopback_interface": {name for _, name in socket.if_nameindex()} == {"lo"},
        "no_ipv4_default_route": not any(line.split()[1] == "00000000" for line in Path("/proc/net/route").read_text().splitlines()[1:]),
        "credential_environment_absent": not any(name in os.environ for name in (
            "GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN", "GITHUB_ENV", "GITHUB_OUTPUT", "HOST_DIAGNOSTIC_CANARY")),
    }
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text(encoding="ascii").splitlines():
        fields = line.partition(" - ")[0].split()
        if len(fields) >= 6:
            mounts[fields[4]] = fields[5].split(",")
    result["readonly_mount_flags"] = all("ro" in mounts.get(path, []) for path in (
        "/usr", "/work", "/overte-policy", "/opt/overte-ci/venv")) and "rw" in mounts.get("/work/build", [])
    forbidden = {context["protected_canary"], *context["command_files"]}
    descriptors = []
    for entry in Path("/proc/self/fd").iterdir():
        try:
            descriptors.append(os.readlink(entry))
        except FileNotFoundError:
            pass
    result["protected_descriptors_absent"] = not forbidden.intersection(descriptors)
    # Opening the outside socket pathname must fail; connecting to a host
    # abstract socket must also fail because the network namespace is private.
    for name, target in (("path_socket_hidden", context["path_socket"]), ("abstract_socket_hidden", "\0" + context["abstract_socket"])):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(0.2)
            try:
                client.connect(target)
                result[name] = False
            except OSError:
                result[name] = True
    for name, path in (("home_writable", "/home/candidate/fixture"), ("temp_writable", "/tmp/fixture"), ("build_writable", "/work/build/fixture")):
        Path(path).write_text("private-output\n", encoding="ascii")
        result[name] = Path(path).read_text(encoding="ascii") == "private-output\n"
    # no_new_privs must also deny an actual attempt to invoke installed sudo.
    command = subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/true"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    result["sudo_denied"] = command.returncode != 0
    result["venv_aliases"] = all(subprocess.check_output([alias, "-I", "-c", "import sys;print(sys.prefix)"], timeout=2).strip()
                                 == b"/opt/overte-ci/venv" for alias in ("python", "python3"))
    return result


def main():
    mode = sys.argv[1]
    context = json.loads(Path("/overte-policy/context.json").read_text(encoding="ascii"))["fixture"]
    if mode == "pair-protections":
        measured = protections(context)
        descriptors = {}
        for entry in Path("/proc/self/fd").iterdir():
            try:
                descriptors[entry.name] = os.readlink(entry)
            except FileNotFoundError:
                pass
        print(json.dumps({"protections": measured, "descriptors": descriptors}, sort_keys=True), flush=True)
        return 0
    if mode == "protections":
        print(json.dumps(protections(context), sort_keys=True), flush=True)
        return 0
    if mode == "nested":
        before = os.stat("/proc/self/ns/net").st_ino
        command = ["/usr/bin/unshare", "--user", "--map-root-user", "--net",
                   "/opt/overte-ci/venv/bin/python", "-I", "/work/fixture.py", "nested-inner"]
        nested = json.loads(subprocess.check_output(command, timeout=5))
        print(json.dumps({"nested_loopback": nested["loopback"], "nested_network_distinct": nested["net"] != before}), flush=True)
        return 0
    if mode == "nested-inner":
        if context["ip"] not in {"/usr/bin/ip", "/usr/sbin/ip"}:
            raise ValueError("fixed system network tool is unsupported")
        subprocess.run([context["ip"], "link", "set", "lo", "up"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        print(json.dumps({"loopback": loopback(), "net": os.stat("/proc/self/ns/net").st_ino}), flush=True)
        return 0
    if mode in {"daemon", "fork-exit", "timeout"}:
        count = 3 if mode == "fork-exit" else 1
        ready_read, ready_write = os.pipe()
        for _ in range(count):
            if os.fork() == 0:
                os.close(ready_read)
                os.setsid()
                os.write(ready_write, b"1")
                os.close(ready_write)
                # Close all diagnostics, so stdout EOF cannot prove cleanup.
                for descriptor in (0, 1, 2):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                time.sleep(20)
                os._exit(0)
        os.close(ready_write)
        remaining = count
        while remaining:
            block = os.read(ready_read, remaining)
            if not block:
                raise RuntimeError("bounded child fixture did not become ready")
            remaining -= len(block)
        os.close(ready_read)
        print(json.dumps({"descendants_started": count}), flush=True)
        if mode == "timeout":
            time.sleep(20)
        return 0
    raise ValueError("unsupported fixed diagnostic fixture")


if __name__ == "__main__":
    raise SystemExit(main())
