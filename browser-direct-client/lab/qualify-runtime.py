#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind completed native checks, live owned processes and observed socket scope."""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from manage import REPO, ROOT, owns_process, read_state


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-log", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.test_log, args.build_log, args.junit):
        if not path.resolve().is_relative_to((REPO / "build/browser-direct").resolve()):
            parser.error("qualification inputs must belong to this worktree's direct build")
    text = args.test_log.read_text()
    totals = [{"passed": int(passed), "failed": int(failed), "skipped": int(skipped)}
              for passed, failed, skipped in re.findall(
                  r"Totals:\s+(\d+) passed, (\d+) failed, (\d+) skipped", text)]
    cases = ET.parse(args.junit).getroot().findall(".//testcase")
    expected = {"browser-direct-transport-BrowserEntityProjectionTests-test",
                "browser-direct-transport-NativeAvatarAudioWireTests-test",
                "browser-direct-transport-WebRTCTransportTests-test",
                "networking-PacketTests-test", "networking-ReceivedMessageTests-test",
                "networking-SequenceNumberStatsTests-test"}
    if len(totals) != 6 or len(cases) != 6 or {case.get("name") for case in cases} != expected or \
            any(item["failed"] or item["skipped"] for item in totals) or \
            any(case.find("failure") is not None or case.find("skipped") is not None for case in cases) or \
            "100% tests passed, 0 tests failed out of 6" not in text:
        raise RuntimeError("All six normal native test executables must pass without skips")
    pointer = json.loads((ROOT / "runtime/native-runtime.json").read_text())
    readiness = json.loads((ROOT / "runtime/assignment-readiness.json").read_text())
    if pointer["runtimeSHA256"] != readiness["runtimeSHA256"]:
        raise RuntimeError("Native snapshot and live readiness marker differ")
    state = read_state()
    for kind, ticks, pid in (("domain", "domainStartTicks", "domainPID"),
                             ("assignments", "assignmentsStartTicks", "assignmentsPID")):
        entry = state.get(kind)
        if not entry or not owns_process(entry) or entry["startTicks"] != readiness[ticks] or \
                entry["pid"] != readiness[pid] or entry["runtimeSHA256"] != readiness["runtimeSHA256"]:
            raise RuntimeError("The qualified owned native process identity changed")
    credentials = json.loads((ROOT / "runtime/admin.json").read_text())
    token = base64.b64encode(
        f"{credentials['username']}:{credentials['password']}".encode()).decode()
    connection = http.client.HTTPConnection("127.0.0.3", 46100, timeout=2)
    try:
        connection.request("GET", "/nodes.json", headers={"Authorization": f"Basic {token}"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Own authenticated native readiness read failed")
        nodes = json.loads(response.read())["nodes"]
    finally:
        connection.close()
    if isinstance(nodes, dict):
        nodes = nodes.values()
    endpoints = [{key: node[key] for key in ("type", "local", "public")}
                 for node in nodes if node["type"] in readiness["assignmentTypes"]]
    if len(endpoints) != 6 or any(node["local"]["ip"] != "127.0.0.3" for node in endpoints):
        raise RuntimeError("All six native assignment endpoints must use the isolated alias")
    sockets = []
    for line in subprocess.check_output(["ss", "-H", "-lntu"], text=True).splitlines():
        fields = line.split()
        address = fields[4]
        try:
            port = int(address.rsplit(":", 1)[1])
        except ValueError:
            continue
        if 46100 <= port <= 46229:
            sockets.append({"protocol": fields[0], "localAddress": address})
    required = {"127.0.0.3:46102", "127.0.0.3:46120",
                *(f"127.0.0.3:{port}" for port in range(46110, 46116))}
    if not required <= {item["localAddress"] for item in sockets if item["protocol"] == "udp"}:
        raise RuntimeError("Actual isolated native UDP sockets are missing")
    scene = ROOT / "scene/hub-with-atp-and-https.json"
    record = {"schema": 1, "recordedUnixTime": time.time(), "runtime": pointer,
              "readiness": readiness,
              "nativeTests": {"passed": 6, "failed": 0, "skipped": 0, "qtTotals": totals,
                              "ctestTimeoutSeconds": 45, "log": str(args.test_log),
                              "logSHA256": digest(args.test_log),
                              "buildLog": str(args.build_log), "buildLogSHA256": digest(args.build_log),
                              "junitSHA256": digest(args.junit)},
              "nativeAssignmentEndpoints": endpoints, "observedListeningSockets": sockets,
              "sceneSHA256": digest(scene), "hardwareGPUUsed": False,
              "physicalMicrophoneUsed": False}
    output = ROOT / "runtime/native-qualification.json"
    temporary = output.with_suffix(".pending")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(output)
    print(json.dumps({"runtimeSHA256": pointer["runtimeSHA256"], "nativeChecksPassed": 6,
                      "skipped": 0, "strictNativeUDPBindVerified": True,
                      "qualification": str(output)}))


if __name__ == "__main__":
    main()
