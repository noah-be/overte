"""Reject false physical acceptance receipts and execute the read-only observer."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ios.acceptance_evidence import EvidenceError, landscape_geometry, local_resume, observation, stability


class EvidenceTests(unittest.TestCase):
    def rows(self):
        return [{"elapsedSeconds": index * 15, "processId": 42, "foreground": True,
                 "thermalState": 0, "physicalFootprintBytes": 1700 * 1024 * 1024,
                 "sampleSequence": index * 15 + 1, "renderFrameCount": index * 450 + 1}
                for index in range(121)]

    def test_accepts_one_complete_process_and_rejects_missing_coverage(self):
        self.assertTrue(stability(self.rows())["passed"])
        for rows in (self.rows()[1:], self.rows()[:-1], self.rows()[:30] + self.rows()[34:]):
            with self.assertRaises(EvidenceError):
                stability(rows)
        with self.assertRaises(EvidenceError):
            stability(self.rows(), minimum_seconds=1799)

    def test_rejects_restart_critical_thermal_missing_memory_and_frozen_render(self):
        for key, value in (("processId", 43), ("thermalState", 3), ("physicalFootprintBytes", None),
                           ("renderFrameCount", 1), ("sampleSequence", 1), ("foreground", False),
                           ("thermalState", True), ("elapsedSeconds", float("nan"))):
            rows = self.rows()
            rows[90][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                stability(rows)

    def test_rejects_sustained_memory_growth(self):
        rows = self.rows()
        for row in rows:
            if row["elapsedSeconds"] >= 1500:
                row["physicalFootprintBytes"] += 256 * 1024 * 1024
        with self.assertRaises(EvidenceError):
            stability(rows)

    def test_requires_real_native_landscape_safe_area_and_keyboard_metrics(self):
        doc = {"nativeUi": {"valid": True, "surfaceWidth": 1366, "surfaceHeight": 1024,
                            "safeInsetLeft": 0, "safeInsetTop": 20, "safeInsetRight": 0,
                            "safeInsetBottom": 0, "imeInsetBottom": 400, "density": 2,
                            "fontScale": 1, "keyboardVisible": True},
               "window": {"width": 1366, "height": 1004}}
        self.assertTrue(landscape_geometry(doc, keyboard=True)["passed"])
        # A floating keyboard is visible without a full-width bottom inset.
        doc["nativeUi"]["imeInsetBottom"] = 0
        self.assertTrue(landscape_geometry(doc, keyboard=True)["passed"])
        for key, value in (("valid", False), ("surfaceWidth", 700), ("safeInsetTop", 1100),
                           ("imeInsetBottom", None), ("keyboardVisible", False), ("density", 0)):
            changed = copy.deepcopy(doc)
            changed["nativeUi"][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                landscape_geometry(changed, keyboard=True)
        doc["window"] = {"width": 700, "height": 1004}
        with self.assertRaises(EvidenceError):
            landscape_geometry(doc)

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute the actual observer")
    def test_actual_observer_is_read_only_and_binds_native_render_and_run(self):
        script = ROOT / "ios/acceptance_observation.js"
        harness = r'''
const fs = require("fs"), vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const state = { saved: {}, stats: { frameDrawcallCount: 12, frameTriangleCount: 100,
    newStats: { connect(callback) { state.render = callback; }, disconnect(callback) {
        if (callback !== state.render) throw Error("wrong renderer cleanup"); state.disconnected = true;
    } } } };
const native = { ok: true, physicalDevice: true, iosForeground: true, prepared: false,
    measurementMode: false, sourceEnabled: false, sourceClockActive: false, iosInterrupted: false,
    nativeMuted: true, iosPermission: 1, iosOutcome: 3, audioLifecycleRunning: true, audioPaused: false,
    iosCaptureAllowed: false, inputPresent: false, inputState: -1, inputError: -1 };
const context = { OVERTE_ACCEPTANCE_RUN: { id: "output-" + "f".repeat(32) },
    Render: { getConfig(name) { if (name !== "Stats") throw Error("wrong stats"); return state.stats; } },
    Test: { acousticTest(command) {
        if (command.action !== "status") throw Error("observer changed audio"); return native;
    }, saveObject(value, name) { state.saved[name] = value; } },
    About: { buildVersion: "fixture" }, Entities: { findEntities() { return ["b", "a"]; },
        getEntityProperties(id) { return { name: id === "a" ? "OVERTE_E2E_DOMAIN_FLOOR" : "unrelated" }; } },
    MyAvatar: { position: { x: 0, y: 2, z: 0 }, feetPosition: { x: 0, y: 1, z: 0 } },
    Quat: { safeEulerAngles() { return { x: 0, y: 0, z: 0 }; } }, Camera: { orientation: {} },
    Window: { innerWidth: 1366, innerHeight: 1024, hasFocus() { return true; } },
    location: { protocol: "file", isConnected: true },
    Tablet: { touchUiRuntimeMetrics: { valid: true, surfaceWidth: 1366, surfaceHeight: 1024 },
        getTablet() { return { tabletShown: false }; } }, HMD: { showTablet: false },
    Script: { setInterval(callback) { state.tick = callback; return 1; }, clearInterval(value) {
        if (value !== 1) throw Error("wrong timer cleanup"); state.cleared = true;
    }, scriptEnding: { connect(callback) { state.ending = callback; } },
    setTimeout(callback, delay) { if (delay !== 4200000) throw Error("unbounded observer"); }, stop() {} } };
vm.runInNewContext(code, context); state.render(); state.tick();
const observed = state.saved["acceptance-observation.json"];
const heartbeat = state.saved["output-foreground.json"];
state.ending();
native.prepared = true; state.tick();
if (!state.saved["acceptance-observation.json"].error || !state.cleared || !state.disconnected) {
    throw Error("observer did not reject instrumentation or release handlers");
}
process.stdout.write(JSON.stringify({ observed, heartbeat }));
'''
        completed = subprocess.run(["node", "-e", harness, str(script)],
                                   capture_output=True, text=True, check=True, timeout=10)
        result = json.loads(completed.stdout)
        doc = result["observed"]
        # The native object was subsequently mutated in the Node fixture.
        doc["nativeAudio"]["prepared"] = False
        self.assertTrue(result["heartbeat"]["iosForeground"])
        valid = observation(doc, "output-" + "f" * 32, "fixture", doc["sampleEpochMs"])
        self.assertEqual(valid["scene"]["entityIds"], ["a", "b"])
        self.assertEqual(valid["scene"]["domainMarkers"], ["OVERTE_E2E_DOMAIN_FLOOR"])
        self.assertTrue(valid["nativeUi"]["valid"])
        for key, value in (("runId", "old"), ("buildVersion", "other"), ("sampleEpochMs", 1)):
            changed = copy.deepcopy(doc)
            changed[key] = value
            with self.assertRaises(EvidenceError):
                observation(changed, doc["runId"], "fixture", doc["sampleEpochMs"])
        resumed = copy.deepcopy(doc)
        resumed["sampleSequence"] += 1
        resumed["render"]["frameCount"] += 1
        self.assertTrue(local_resume(doc, resumed)["passed"])
        broken_audio = copy.deepcopy(resumed)
        broken_audio["nativeAudio"]["audioPaused"] = True
        with self.assertRaises(EvidenceError):
            local_resume(doc, broken_audio)
        resumed["scene"]["entityIds"] = ["replacement-a", "replacement-b"]
        with self.assertRaises(EvidenceError):
            local_resume(doc, resumed)


if __name__ == "__main__":
    unittest.main()
