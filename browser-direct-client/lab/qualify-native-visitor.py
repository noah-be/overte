#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record current native world/model evidence separately from explicit test placement."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import time

from manage import ROOT, SOURCE, owns_process, read_state

spec = importlib.util.spec_from_file_location("owned_native_visitor", SOURCE / "native-visitor.py")
visitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visitor)


def save(name: str, value: dict) -> None:
    output = ROOT / "runtime" / name
    temporary = output.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(output)


def observer_binding(native: dict, observed: dict) -> dict:
    """Bind the started observer, its current sample and an unused motion trial."""
    script_sha256 = hashlib.sha256((SOURCE / "native-visitor.js").read_bytes()).hexdigest()
    if native.get("observerScriptSHA256") != script_sha256:
        raise RuntimeError("The started native observer must match its exact current source")
    when, sequence = observed.get("observedAtUnixTime"), observed.get("sequence")
    if type(observed.get("nativeMotionControlVersion")) is not int or \
            observed["nativeMotionControlVersion"] != 2 or \
            type(when) not in (int, float) or not math.isfinite(when) or \
            not 0 <= time.time() - when <= 6 or \
            type(sequence) is not int or not 0 <= sequence < 2 ** 53:
        raise RuntimeError("Require a fresh actual version-2 native observer sample")
    previous_path = ROOT / "runtime/native-motion.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    if not isinstance(previous, dict) or "nativeMotionTest" not in observed or \
            observed["nativeMotionTest"] is not None or previous.get("session") == observed.get("session"):
        raise RuntimeError("Native qualification requires an unused motion trial for this process/session")
    return {"nativeMotionControlVersion": observed["nativeMotionControlVersion"],
            "observerScriptSHA256": native["observerScriptSHA256"],
            "nativeMotionTrialUnused": True}


def current() -> tuple[dict, dict, dict]:
    pointer = json.loads((ROOT / "runtime/native-runtime.json").read_text())
    marker = json.loads((ROOT / "runtime/assignment-readiness.json").read_text())
    state = read_state()
    if pointer["runtimeSHA256"] != marker["runtimeSHA256"]:
        raise RuntimeError("Current snapshot and readiness marker differ")
    for kind, prefix in (("domain", "domain"), ("assignments", "assignments")):
        entry = state.get(kind)
        if not entry or not owns_process(entry) or entry["pid"] != marker[prefix + "PID"] or \
                entry["startTicks"] != marker[prefix + "StartTicks"] or \
                entry["runtimeSHA256"] != pointer["runtimeSHA256"]:
            raise RuntimeError("Current owned native services are not qualified")
    native = visitor.read_state()
    if not native or not owns_process(native["parent"]):
        raise RuntimeError("The current owned native visitor must be alive")
    observed = visitor.evidence()
    source = json.loads((ROOT / "runtime/native-avatar-provenance.json").read_text())
    if not observed or not observed["connected"] or observed["domain"] != "127.0.0.3" or \
            observed["skeletonModelURL"] != source["skeletonModelURL"] or \
            observed["avatarJointCount"] != 69 or observed["avatarGraphics"]["meshCount"] != 2 or \
            observed["entitiesNearSpawn"] <= 0 or observed["loadedATPModels"] <= 0 or \
            not observed["httpsBridge"]["loaded"] or observed["httpsBridge"]["graphics"]["meshCount"] <= 0:
        raise RuntimeError("Actual native join, world, mannequin and historical bridge must be loaded")
    observer_binding(native, observed)
    return pointer, native, observed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture-ordinary", "qualify"))
    args = parser.parse_args()
    pointer, native, observed = current()
    if args.operation == "capture-ordinary":
        center = {"x": 155.084, "y": -98.5, "z": -397.328}
        if observed.get("nativeTestSetup") or \
                sum((observed["position"][axis] - center[axis]) ** 2 for axis in center) > 4:
            raise RuntimeError("Capture the actual ordinary Hub pose before explicit native placement")
        save("native-ordinary-world-observation.json", observed)
        save("native-ordinary-world-capture.json", {
            "recordedUnixTime": time.time(), "runtimeSHA256": pointer["runtimeSHA256"],
            "nativeProcessIdentity": native["parent"], "observation": observed})
        print(json.dumps({"ordinaryNativePoseRecorded": observed["position"],
                          "entitiesReceived": observed["entitiesNearSpawn"],
                          "loadedATPModels": observed["loadedATPModels"],
                          "ordinaryPathRetryUsed": bool(observed.get("nativeNavigationRetry"))}))
        return
    capture = json.loads((ROOT / "runtime/native-ordinary-world-capture.json").read_text())
    ordinary = capture["observation"]
    setup = observed.get("nativeTestSetup")
    if capture["runtimeSHA256"] != pointer["runtimeSHA256"] or \
            capture["nativeProcessIdentity"] != native["parent"] or \
            ordinary["session"] != observed["session"] or not setup or \
            setup["offset"] != {"x": 0, "y": 0, "z": -3} or \
            setup["normalDomainSpawnObserved"]["session"] != ordinary["session"]:
        raise RuntimeError("Current placement must follow the independently captured native ordinary spawn")
    if sum((observed["position"][axis] - ordinary["position"][axis] - setup["offset"][axis]) ** 2
           for axis in setup["offset"]) > 4:
        raise RuntimeError("Actual native pose does not confirm the explicit three-metre placement")
    launched = time.time() - time.clock_gettime(time.CLOCK_BOOTTIME) + \
        int(native["parent"]["startTicks"]) / os.sysconf("SC_CLK_TCK")
    requests = [json.loads(line) for line in (ROOT / "runtime/https-fixture-requests.jsonl").read_text().splitlines()]
    requests = [row for row in requests if row["unixTime"] >= launched and row["clientClass"] == "Qt" and
                row["relativePath"].startswith("default-avatar/")]
    source = json.loads((ROOT / "runtime/native-avatar-provenance.json").read_text())
    for expected in ("defaultAvatar_full.fst", "mannequin/mannequin.fbx"):
        digest = next(row["sourceSHA256"] for row in source["files"] if row["path"] == expected)
        if not any(row["relativePath"] == "default-avatar/" + expected and row["servedSHA256"] == digest
                   for row in requests):
            raise RuntimeError("Current-launch native Qt HTTPS FST/FBX hashes are required")
    lines = (ROOT / "logs/assignments.log").read_text(errors="replace").splitlines()
    session = observed["session"].strip("{}")
    activation = [line for line in lines if "Activating symmetric socket" in line and
                  '"127.0.0.1":46116' in line and session in line]
    types = sorted({re.search(r"\[([a-z-]+)\] Activating symmetric socket", line).group(1)
                    for line in activation})
    expected_types = {"asset-server", "audio-mixer", "avatar-mixer", "entity-script-server",
                      "entity-server", "messages-mixer"}
    if set(types) != expected_types:
        raise RuntimeError("All six assignments must activate the actual native UDP endpoint")
    sanitized = [re.sub(r'\{?[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}?',
                        "owned-native-peer", line) for line in activation]
    save("native-loopback-endpoint-proof.json", {
        "runtimeSHA256": pointer["runtimeSHA256"], "nativeUDPPort": 46116,
        "entityServerActiveNativeEndpoint": "127.0.0.1:46116",
        "assignmentTypesObserved": types, "sanitizedActivationLogLines": sanitized})
    record = {"schema": 1, "recordedUnixTime": time.time(), "runtimeSHA256": pointer["runtimeSHA256"],
              "nativeProcessIdentity": native["parent"], "nativeRelease": native["release"],
              "fixtureTLS": json.loads((ROOT / "runtime/fixture-tls-qualification.json").read_text()),
              "ordinarySpawnObservation": ordinary, "explicitNativePlacementObservation": observed,
              "ordinaryNativePathRetryUsed": bool(ordinary.get("nativeNavigationRetry")),
              "initialAutomaticSpawnQualified": not bool(ordinary.get("nativeNavigationRetry")),
              "nativeWorldEntitiesReceived": observed["entitiesNearSpawn"], "worldLoadingQualified": True,
              "modelGraphicsAndNativeQtHTTPSQualified": True, "nativeHTTPSAssetRequests": requests,
              "nativeModelProvenanceSHA256": hashlib.sha256(
                  (ROOT / "runtime/native-avatar-provenance.json").read_bytes()).hexdigest(),
              "hardwareGPUUsed": False, "physicalMicrophoneUsed": False,
              "browserMovedForThisQualification": False}
    if visitor.read_state() != native or not owns_process(native["parent"]):
        raise RuntimeError("The registered native visitor changed before qualification was written")
    record.update(observer_binding(native, observed))
    save("native-visitor-qualification.json", record)
    print(json.dumps({"runtimeSHA256": pointer["runtimeSHA256"], "nativeWorldQualified": True,
                      "entitiesReceived": observed["entitiesNearSpawn"],
                      "loadedATPModels": observed["loadedATPModels"], "nativeQtModelHashesQualified": True,
                      "ordinaryPathRetryUsed": record["ordinaryNativePathRetryUsed"]}))


if __name__ == "__main__":
    main()
