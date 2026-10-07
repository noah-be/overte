#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record bounded own AssetServer connection metrics without changing services."""
from __future__ import annotations

import argparse
import base64
import http.client
import json
from pathlib import Path
import time

from manage import ROOT, owns_process, read_state


def sample(headers: dict[str, str]) -> dict:
    def read(path: str) -> dict:
        connection = http.client.HTTPConnection("127.0.0.3", 46100, timeout=2)
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError("Own AssetServer stats endpoint did not return HTTP 200")
            return json.loads(response.read())
        finally:
            connection.close()

    nodes = read("/nodes.json")["nodes"]
    if isinstance(nodes, dict):
        nodes = nodes.values()
    assets = [node for node in nodes if node["type"] == "asset-server"]
    if len(assets) != 1:
        raise RuntimeError("Own domain must have exactly one admitted AssetServer")
    asset_uuid = assets[0]["uuid"]
    stats = read(f"/nodes/{asset_uuid}.json")
    peers = {}
    for peer_uuid, value in stats.items():
        if not isinstance(value, dict) or "Connection Stats" not in value:
            continue
        peers[peer_uuid] = {
            section: {key: metric for key, metric in value.get(section, {}).items()
                      if isinstance(metric, (int, float)) and not isinstance(metric, bool)}
            for section in ("Connection Stats", "Upstream Stats", "Downstream Stats")
        }
    return {"unixTime": time.time(), "assetServerUUID": asset_uuid, "peers": peers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=45)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.duration <= 180 or not 0.2 <= args.interval <= 10:
        parser.error("duration must be at most 180 seconds; interval must be 0.2–10 seconds")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT.resolve()) or output.exists():
        parser.error("output must be a new file under this worktree's owned lab state")
    readiness = json.loads((ROOT / "runtime/assignment-readiness.json").read_text())
    credentials = json.loads((ROOT / "runtime/admin.json").read_text())
    token = base64.b64encode(
        f"{credentials['username']}:{credentials['password']}".encode()).decode()
    result = {"schema": 1, "runtimeSHA256": readiness["runtimeSHA256"],
              "domainStartTicks": readiness["domainStartTicks"],
              "assignmentsStartTicks": readiness["assignmentsStartTicks"],
              "readOnlyNativeServices": True, "samples": []}
    deadline = time.monotonic() + args.duration
    try:
        while True:
            state = read_state()
            for kind, field, pid_field in (("domain", "domainStartTicks", "domainPID"),
                                           ("assignments", "assignmentsStartTicks", "assignmentsPID")):
                entry = state.get(kind)
                if not entry or not owns_process(entry) or entry["startTicks"] != readiness[field] or \
                        entry["pid"] != readiness[pid_field] or \
                        entry["runtimeSHA256"] != readiness["runtimeSHA256"]:
                    raise RuntimeError("Own native runtime changed during connection-stat sampling")
            result["samples"].append(sample({"Authorization": f"Basic {token}"}))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(args.interval, remaining))
    finally:
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = output.with_suffix(output.suffix + ".pending")
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(output)
    print(json.dumps({"samples": len(result["samples"]),
                      "peerCounts": [len(item["peers"]) for item in result["samples"]],
                      "output": str(output)}))


if __name__ == "__main__":
    main()
