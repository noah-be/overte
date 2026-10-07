#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Actual owned-process/file relay checks; no browser/native domain/GPU involved."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from native_host_actions import NativeHostActions, identity_label
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab"))
from manage import owns_process, process_identity


class HostActionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="own-host-relay-")
        self.directory = Path(self.temporary.name)
        self.native = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
        self.identity = process_identity(self.native.pid)
        self.visitor = {"release": "2026.04.1", "parent": self.identity}
        self.observation = {"connected": True, "session": "unit-native-session", "sequence": 10,
                            "nativeMotionTest": None, "nativeMotionControlVersion":2}
        self.launched = []
        self.processes = {}
        self.delay = 0
        def observe():
            return {**self.observation, "observedAtUnixTime": time.time()}
        def launch(name, operation, output):
            self.launched.append(operation)
            result = {"operation": operation.removeprefix("motion-"), "session": "unit-native-session", "browserMoved": False}
            code = "import time;time.sleep(" + str(self.delay) + ");print(" + repr(json.dumps(result)) + ")"
            with output.open("w") as destination:
                process = subprocess.Popen([sys.executable, "-c", code], stdout=destination, start_new_session=True)
            self.processes[name] = process
            return process
        def cancel(name):
            process = self.processes[name]
            process.terminate()
        self.control = NativeHostActions(self.directory / "relay", self.identity, "unit-native-session",
            lambda: self.visitor, observe, owns_process, launch, cancel, maximum_job_seconds=0.3)

    def tearDown(self):
        self.control.close()
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)
        if self.native.poll() is None:
            self.native.terminate()
        self.native.wait(timeout=3)
        self.temporary.cleanup()

    def request(self, **changes):
        request_id = str(uuid.uuid4())
        value = {"requestId": request_id, "operation": "motion-move", "nativeSession": "unit-native-session",
            "processIdentity": identity_label(self.identity), "issuedUnixTime": time.time(), "runNonce": self.control.run_nonce}
        value.update(changes)
        path = self.control.requests / (request_id + ".json")
        self.control.write(path, value)
        return request_id, path

    def result(self, request_id):
        deadline = time.monotonic() + 2
        path = self.control.results / (request_id + ".json")
        while not path.exists() and time.monotonic() < deadline:
            self.control.tick()
            time.sleep(0.01)
        return json.loads(path.read_text())

    def test_real_host_identity_and_nonce_bind_proof_and_once_only_fixed_operation(self):
        self.control.proof(True)
        proof = json.loads((self.control.directory / "host-proof.json").read_text())
        self.assertTrue(proof["live"])
        self.assertEqual(proof["processIdentity"], identity_label(self.identity))
        self.assertEqual(proof["runNonce"], self.control.run_nonce)
        request_id, _ = self.request()
        response = self.result(request_id)
        self.assertTrue(response["ok"])
        self.assertEqual(response["runNonce"], self.control.run_nonce)
        self.control.tick()
        self.assertEqual(self.launched, ["motion-move"])
        second, _ = self.request()
        self.assertFalse(self.result(second)["ok"])
        restore, _ = self.request(operation="motion-restore")
        self.assertTrue(self.result(restore)["ok"])
        self.assertEqual(self.launched, ["motion-move", "motion-restore"])

    def test_changed_live_host_start_tick_prevents_action(self):
        self.visitor = {"release": "2026.04.1", "parent": {**self.identity, "startTicks": "wrong"}}
        request_id, _ = self.request()
        self.assertFalse(self.result(request_id)["ok"])
        self.control.proof(True)
        self.assertFalse(json.loads((self.control.directory / "host-proof.json").read_text())["live"])
        self.assertEqual(self.launched, [])

    def test_stale_motion_observer_version_prevents_action_and_live_proof(self):
        self.observation["nativeMotionControlVersion"] = 1
        request_id, _ = self.request()
        self.assertFalse(self.result(request_id)["ok"])
        self.control.proof(True)
        self.assertFalse(json.loads((self.control.directory / "host-proof.json").read_text())["live"])
        self.assertEqual(self.launched, [])

    def test_old_run_nonce_and_expired_request_cannot_replay(self):
        for changes in ({"runNonce": str(uuid.uuid4())}, {"issuedUnixTime": time.time() - 10},
                        {"nativeSession": "other-session"}, {"operation": "start"}):
            request_id, _ = self.request(**changes)
            self.assertFalse(self.result(request_id)["ok"])
        self.assertEqual(self.launched, [])

    def test_fifo_and_symlink_cannot_block_host_watchdog_or_launch_actions(self):
        for kind in ("fifo", "symlink"):
            request_id = str(uuid.uuid4())
            path = self.control.requests / (request_id + ".json")
            if kind == "fifo":
                os.mkfifo(path, 0o600)
            else:
                path.symlink_to(self.directory / "never-created")
            started = time.monotonic()
            self.control.accept(path)
            self.assertLess(time.monotonic() - started, 0.1)
            self.assertFalse(json.loads((self.control.results / (request_id + ".json")).read_text())["ok"])
        self.assertEqual(self.launched, [])

    def test_stalled_owned_helper_has_finite_credit_and_is_terminated(self):
        self.delay = 20
        request_id, _ = self.request()
        response = self.result(request_id)
        self.assertFalse(response["ok"])
        self.assertIn("timed out", response["error"])
        self.assertTrue(all(process.poll() is not None for process in self.processes.values()))
        self.assertEqual(self.control.jobs, {})

    def test_driver_exit_restores_only_current_owned_moved_setup(self):
        self.control.move_started = True
        self.observation["nativeMotionTest"] = {"phase": "moved"}
        self.control.close()
        self.assertEqual(self.launched, ["motion-restore"])
        self.assertTrue((self.control.directory / "cleanup-restore.json").is_file())
        proof = json.loads((self.control.directory / "host-proof.json").read_text())
        self.assertFalse(proof["live"])
        self.assertTrue(proof["closed"])
        # Tear-down close is idempotent after the fixed compensation.
        self.observation["nativeMotionTest"] = {"phase": "restored"}


if __name__ == "__main__":
    unittest.main()
