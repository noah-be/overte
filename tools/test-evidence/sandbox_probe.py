#!/usr/bin/env python3
"""Observe this actual process; local output is diagnostic, not authentication.

The future qualified launcher must invoke these trusted bytes in its enforced
sandbox using a protected output channel, before candidate work and only after
kernel-confirmed descendant cleanup. Calling this script on a host does not
make that host a sandbox. Never accept a candidate-created copy of this JSON.
"""

from __future__ import annotations

import json
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import sys

# -I deliberately removes the script directory from import lookup. Load only
# the protected sibling projected by the supervisor, never a candidate module.
_spec = importlib.util.spec_from_file_location("protected_probe_runtime", Path(__file__).with_name("runtime.py"))
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


def process_observation(proc=Path("/proc")):
    # proc is injectable only for offline parser fixtures, never proof input.
    status = (proc / "self/status").read_text(encoding="ascii")
    if len(status) > 100_000:
        raise ValueError("process status exceeds the diagnostic bound")
    fields = {}
    for line in status.splitlines():
        name, separator, value = line.partition(":")
        if separator and name in {"Uid", "Gid", "NoNewPrivs", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"}:
            if name in fields:
                raise ValueError("process protection metadata is ambiguous")
            fields[name] = value.strip()
    if set(fields) != {"Uid", "Gid", "NoNewPrivs", "CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"}:
        raise ValueError("process protection metadata is incomplete")
    if any(not re.fullmatch(r"[0-9]+(?:\s+[0-9]+){3}", fields[name]) for name in ("Uid", "Gid")) \
            or fields["NoNewPrivs"] not in {"0", "1"} \
            or any(not re.fullmatch(r"[0-9a-f]{16}", fields[name]) for name in fields if name.startswith("Cap")):
        raise ValueError("process protection metadata is unsupported")
    maps = {}
    for name in ("uid_map", "gid_map"):
        value = (proc / "self" / name).read_text(encoding="ascii")
        if len(value) > 4096 or not value.strip() or any(not re.fullmatch(r"\s*[0-9]+\s+[0-9]+\s+[0-9]+\s*", line)
                                                       for line in value.splitlines()):
            raise ValueError("process identity mapping is unsupported")
        maps[name] = [[int(part) for part in line.split()] for line in value.splitlines()]
    return {"status": fields, "identity_maps": maps}


def measure_local_process():
    """Measure the actual interpreter/tools; no assumed outside-host identity."""
    observation = process_observation()
    try:
        environment = runtime.capture_host_environment()
        unavailable = None
    except runtime.RuntimeIdentityError:
        environment, unavailable = None, "runtime-identity-unavailable"
    return {"schema": 1, "authority": "none", "measurement": "local-process", "process": observation,
            "environment": environment, "unavailable": unavailable, "reusable": False}


def measure_boundary():
    """Fixed tiny diagnostic profile; never the complete host E identity."""
    control = json.loads(Path("/overte-policy/context.json").read_bytes())
    if set(control) != {"binding", "fixture"}:
        raise ValueError("protected diagnostic binding is incomplete")
    binding = control["binding"]
    expected = {"source", "run_id", "run_attempt", "snapshot", "projection"}
    if type(binding) is not dict or set(binding) != expected:
        raise ValueError("protected diagnostic binding is unsupported")
    files = {}
    for path in (Path(sys.executable).resolve(), Path("/usr/bin/python3").resolve(), Path("/usr/bin/bwrap"),
                 Path("/usr/bin/git"), Path("/usr/bin/unshare"), Path("/etc/os-release"), Path("/var/lib/dpkg/status"),
                 Path(__file__), Path(__file__).with_name("runtime.py")):
        if not path.is_file() or path.stat().st_size > 32_000_000:
            raise ValueError("diagnostic runtime input is unavailable")
        files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    mount_flags = {}
    for line in Path("/proc/self/mountinfo").read_text(encoding="ascii").splitlines():
        fields = line.partition(" - ")[0].split()
        if len(fields) >= 6 and fields[4] in {"/usr", "/work", "/overte-policy", "/opt/overte-ci/venv", "/work/build"}:
            mount_flags[fields[4]] = fields[5].split(",")
    if not all("ro" in mount_flags.get(path, ()) for path in ("/usr", "/work", "/overte-policy", "/opt/overte-ci/venv")) \
            or "rw" not in mount_flags.get("/work/build", ()):
        raise ValueError("diagnostic runtime mounts are unsupported")
    observation = {"binding": binding, "files": files, "python": list(sys.version_info[:3]),
                   "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                   "kernel": os.uname().release, "environment": dict(os.environ), "mounts": mount_flags}
    return {"schema": 1, "authority": "none", "measurement": "protected-boundary-profile",
            "process": process_observation(), "identity": observation, "reusable": False,
            "runtime_compatibility": "unqualified"}


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--boundary-diagnostic"]):
        raise SystemExit("unsupported protected probe mode")
    result = measure_boundary() if sys.argv[1:] else measure_local_process()
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
