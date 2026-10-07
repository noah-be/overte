#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record read-only native cleanup evidence after an owned browser run ends."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import time

from manage import REPO, ROOT, SOURCE, owns_process, read_state

spec = importlib.util.spec_from_file_location("owned_asset_stats", SOURCE / "asset-stats.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-result", type=Path, required=True)
    parser.add_argument("--statistics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.probe_result.resolve().is_relative_to((REPO / "build/browser-direct").resolve()) or \
            not args.statistics.resolve().is_relative_to(ROOT.resolve()) or \
            not args.output.resolve().is_relative_to(ROOT.resolve()) or args.output.exists():
        parser.error("Use owned direct-build evidence and a new owned lab output file")
    if json.loads((ROOT / "runtime/browser-tests.json").read_text()) != {}:
        raise RuntimeError("The browser owner must finish and clean its registered test processes first")
    probe = json.loads(args.probe_result.read_text())
    ended = probe.get("endedUTC", probe.get("finished"))
    if not isinstance(ended, str):
        raise RuntimeError("The browser result must record its actual end time")
    ended_time = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    trace = json.loads(args.statistics.read_text())
    marker = json.loads((ROOT / "runtime/assignment-readiness.json").read_text())
    state = read_state()
    if marker["runtimeSHA256"] != trace["runtimeSHA256"]:
        raise RuntimeError("The sampled native runtime has changed")
    for kind, prefix in (("domain", "domain"), ("assignments", "assignments")):
        entry = state.get(kind)
        if not entry or not owns_process(entry) or entry["pid"] != marker[prefix + "PID"] or \
                entry["startTicks"] != marker[prefix + "StartTicks"] or \
                entry["runtimeSHA256"] != marker["runtimeSHA256"]:
            raise RuntimeError("Current owned services differ from the qualified runtime")
    credentials = json.loads((ROOT / "runtime/admin.json").read_text())
    token = base64.b64encode(
        f"{credentials['username']}:{credentials['password']}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    connection = http.client.HTTPConnection("127.0.0.3", 46100, timeout=2)
    try:
        connection.request("GET", "/nodes.json", headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Own authenticated native node read failed")
        nodes = json.loads(response.read())["nodes"]
    finally:
        connection.close()
    if isinstance(nodes, dict):
        nodes = nodes.values()
    agents = [node for node in nodes if node["type"] == "agent"]
    native = json.loads((ROOT / "runtime/native-visitor-qualification.json").read_text())
    session = native["explicitNativePlacementObservation"]["session"].strip("{}")
    native_present = any(node["uuid"].strip("{}") == session for node in agents)
    other_count = sum(node["uuid"].strip("{}") != session for node in agents)
    sample = stats.sample(headers)
    failed, after = 0, 0
    for name in ("domain", "assignments"):
        for line in (ROOT / "logs" / (name + ".log")).read_text(errors="replace").splitlines():
            lower = line.lower()
            if "webrtc" not in lower or not any(text in lower for text in
                                                ("failed writing", "failed write", "failed to write", "write failed")):
                continue
            failed += 1
            timestamp = re.match(r"\[(\d{2}/\d{2}) (\d{2}:\d{2}:\d{2})\]", line)
            if timestamp:
                event = datetime.strptime(f"{ended_time.year}/{timestamp[1]} {timestamp[2]}",
                                          "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if event > ended_time:
                    after += 1
    record = {"runtimeSHA256": marker["runtimeSHA256"], "probeResults": str(args.probe_result),
              "probeResultSHA256": hashlib.sha256(args.probe_result.read_bytes()).hexdigest(),
              "probeEndUTC": ended, "recordedUnixTime": time.time(), "nativeAgentPresent": native_present,
              "admittedAgentCount": len(agents), "otherAdmittedAgentCount": other_count,
              "assetServerPeerCountAfterLeave": len(sample["peers"]),
              "webRTCFailedWriteLogRecordsSinceRuntimeStart": failed,
              "webRTCFailedWriteLogRecordsAfterProbeEnd": after,
              "statisticsTrace": str(args.statistics), "statisticSamples": len(trace["samples"]),
              "readOnlyNativeServices": True, "rawIDsAndCredentialsExported": False,
              "nativeCleanupQualified": native_present and other_count == 0 and len(sample["peers"]) == 2 and after == 0,
              "note": "Cleanup evidence does not establish model/skybox/avatar/audio acceptance."}
    temporary = args.output.with_suffix(".pending")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(args.output)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
