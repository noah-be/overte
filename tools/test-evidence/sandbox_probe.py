#!/usr/bin/env python3
"""Observe this actual process; local output is diagnostic, not authentication.

The future qualified launcher must invoke these trusted bytes in its enforced
sandbox using a protected output channel, before candidate work and only after
kernel-confirmed descendant cleanup. Calling this script on a host does not
make that host a sandbox. Never accept a candidate-created copy of this JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import runtime


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


if __name__ == "__main__":
    print(json.dumps(measure_local_process(), sort_keys=True, separators=(",", ":"), allow_nan=False))
