#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Synthetic native observations through the actual public qualification CLI.

The process-ownership check uses an owned local child. No native client, domain,
HTTPS fixture, motion operation or historical laboratory evidence is used.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "browser-direct-client/lab"))


def module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


qualifier = module("native_visitor_qualification_contract", "browser-direct-client/lab/qualify-native-visitor.py")
runner = module("native_visitor_qualification_runner", "browser-direct-client/e2e/run.py")


class NativeVisitorQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name in ("runtime", "logs", "source"):
            (self.root / name).mkdir()
        self.script = self.root / "source/native-visitor.js"
        self.script.write_text("// Controlled observer source; no native execution.\n")
        self.script_sha = hashlib.sha256(self.script.read_bytes()).hexdigest()
        self.process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"],
                                        start_new_session=True, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
        self.identity = runner.process_identity(self.process.pid)
        self.assertIsNotNone(self.identity)
        self.native = {"parent": self.identity, "children": [], "release": "2026.04.1",
                       "observerScriptSHA256": self.script_sha}
        self.runtime_sha = "a" * 64
        services = {kind: {**self.identity, "runtimeSHA256": self.runtime_sha}
                    for kind in ("domain", "assignments")}
        marker = {"runtimeSHA256": self.runtime_sha}
        for kind in services:
            marker[kind + "PID"] = self.identity["pid"]
            marker[kind + "StartTicks"] = self.identity["startTicks"]
        self.write("runtime/native-runtime.json", {"runtimeSHA256": self.runtime_sha})
        self.write("runtime/assignment-readiness.json", marker)
        self.session = "{11111111-2222-4333-8444-555555555555}"
        self.center = {"x": 155.084, "y": -98.5, "z": -397.328}
        self.observed = {"connected": True, "domain": "127.0.0.3", "session": self.session,
                         "position": dict(self.center), "sequence": 1,
                         "observedAtUnixTime": time.time(), "nativeMotionControlVersion": 2,
                         "nativeMotionTest": None,
                         "skeletonModelURL": "https://127.0.0.1:46119/default-avatar/defaultAvatar_full.fst",
                         "avatarJointCount": 69, "avatarGraphics": {"meshCount": 2},
                         "entitiesNearSpawn": 53, "loadedATPModels": 34,
                         "httpsBridge": {"loaded": True, "graphics": {"meshCount": 1}}}
        files = [{"path": path, "sourceSHA256": hashlib.sha256(path.encode()).hexdigest()}
                 for path in ("defaultAvatar_full.fst", "mannequin/mannequin.fbx")]
        self.write("runtime/native-avatar-provenance.json", {
            "skeletonModelURL": self.observed["skeletonModelURL"], "files": files})
        self.write("runtime/fixture-tls-qualification.json", {"syntheticFixture": True})
        self.requests = [{"unixTime": time.time(), "clientClass": "Qt",
                          "relativePath": "default-avatar/" + row["path"],
                          "servedSHA256": row["sourceSHA256"]} for row in files]
        self.write_requests()
        self.types = ["asset-server", "audio-mixer", "avatar-mixer", "entity-script-server",
                      "entity-server", "messages-mixer"]
        self.write_activations(self.types)
        self.patches = [patch.object(qualifier, "ROOT", self.root),
                        patch.object(qualifier, "SOURCE", self.root / "source"),
                        patch.object(qualifier, "read_state", lambda: copy.deepcopy(services)),
                        patch.object(qualifier.visitor, "read_state", lambda: copy.deepcopy(self.native)),
                        patch.object(qualifier.visitor, "evidence", lambda: copy.deepcopy(self.observed))]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=3)
        self.temporary.cleanup()

    def write(self, relative, value):
        (self.root / relative).write_text(json.dumps(value) + "\n")

    def write_requests(self):
        (self.root / "runtime/https-fixture-requests.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.requests))

    def write_activations(self, types):
        (self.root / "logs/assignments.log").write_text("".join(
            f'[{kind}] Activating symmetric socket "127.0.0.1":46116 {self.session}\n'
            for kind in types))

    def execute(self, operation):
        with patch.object(sys, "argv", ["qualify-native-visitor.py", operation]), \
                contextlib.redirect_stdout(io.StringIO()):
            qualifier.main()

    def capture_and_place(self):
        self.execute("capture-ordinary")
        ordinary = copy.deepcopy(self.observed)
        self.observed.update(position={**self.center, "z": self.center["z"] - 3}, sequence=2,
                             observedAtUnixTime=time.time(),
                             nativeTestSetup={"offset": {"x": 0, "y": 0, "z": -3},
                                              "normalDomainSpawnObserved": ordinary})

    def assert_not_qualified(self):
        with self.assertRaises((RuntimeError, KeyError)):
            self.execute("qualify")
        self.assertFalse((self.root / "runtime/native-visitor-qualification.json").exists())

    def test_documented_sequence_writes_binding_accepted_by_real_browser_guard(self):
        self.capture_and_place()
        self.execute("qualify")
        path = self.root / "runtime/native-visitor-qualification.json"
        record = json.loads(path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(record["nativeMotionControlVersion"], 2)
        self.assertEqual(record["observerScriptSHA256"], self.script_sha)
        self.assertIs(record["nativeMotionTrialUnused"], True)
        self.assertTrue(record["worldLoadingQualified"])
        self.assertTrue(record["modelGraphicsAndNativeQtHTTPSQualified"])
        self.assertEqual(runner.qualify_native_browser("direct", self.native, record, self.script_sha), self.session)

    def test_changed_source_or_missing_started_digest_cannot_qualify(self):
        self.capture_and_place()
        self.script.write_text("// Changed after the owned process started.\n")
        self.assert_not_qualified()
        self.script.write_text("// Controlled observer source; no native execution.\n")
        self.native.pop("observerScriptSHA256")
        self.assert_not_qualified()

    def test_version_and_fresh_sample_bounds_fail_closed(self):
        self.capture_and_place()
        valid = copy.deepcopy(self.observed)
        for changes in ({"nativeMotionControlVersion": 1}, {"nativeMotionControlVersion": 2.0},
                        {"observedAtUnixTime": time.time() - 6.1},
                        {"observedAtUnixTime": time.time() + 10},
                        {"observedAtUnixTime": float("nan")}, {"sequence": True},
                        {"sequence": 2 ** 53}):
            with self.subTest(fields=list(changes)):
                self.observed = {**valid, **changes}
                self.assert_not_qualified()

    def test_consumed_or_failed_host_trial_cannot_be_sealed_as_unused(self):
        self.capture_and_place()
        self.observed["nativeMotionTest"] = {"phase": "restored"}
        self.assert_not_qualified()
        self.observed["nativeMotionTest"] = None
        self.write("runtime/native-motion.json", {"session": self.session, "operationFailed": True})
        self.assert_not_qualified()
        self.write("runtime/native-motion.json", {"session": "previous-test-session"})
        self.execute("qualify")

    def test_stopped_or_replaced_owned_process_cannot_qualify(self):
        self.capture_and_place()
        saved = self.native["parent"]
        self.native["parent"] = {**saved, "startTicks": str(int(saved["startTicks"]) + 1)}
        self.assert_not_qualified()
        self.native["parent"] = saved
        self.process.terminate()
        self.process.wait(timeout=3)
        self.assert_not_qualified()

    def test_existing_world_spawn_and_placement_guards_remain_required(self):
        self.capture_and_place()
        valid = copy.deepcopy(self.observed)
        for changes in ({"entitiesNearSpawn": 0}, {"loadedATPModels": 0},
                        {"avatarJointCount": 68}, {"avatarGraphics": {"meshCount": 1}},
                        {"httpsBridge": {"loaded": False, "graphics": {"meshCount": 1}}},
                        {"nativeTestSetup": {"offset": {"x": 1, "y": 0, "z": -3},
                                             "normalDomainSpawnObserved": {"session": self.session}}}):
            with self.subTest(fields=list(changes)):
                self.observed = {**valid, **changes}
                self.assert_not_qualified()

    def test_same_launch_qt_hashes_and_all_six_activations_remain_required(self):
        self.capture_and_place()
        self.requests[0]["servedSHA256"] = "0" * 64
        self.write_requests()
        self.assert_not_qualified()
        self.requests[0]["servedSHA256"] = hashlib.sha256(b"defaultAvatar_full.fst").hexdigest()
        self.requests[0]["clientClass"] = "Chrome"
        self.write_requests()
        self.assert_not_qualified()
        self.requests[0]["clientClass"] = "Qt"
        self.write_requests()
        self.write_activations(self.types[:-1])
        self.assert_not_qualified()


if __name__ == "__main__":
    unittest.main()
