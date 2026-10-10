"""Exercise the real probe classifier against delayed native motion samples."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


PROBE = Path(__file__).resolve().parents[1] / "probe/overte_e2e_probe.js"
sys.path.insert(0, str(PROBE.parents[1]))
from adapters.android.adapter import AndroidAdapter, ANDROID_CONTROL_CONTRACT


class NativeMotionProcessBindingTest(unittest.TestCase):
    def test_legacy_and_exact_running_process_marker_are_supported(self):
        self.assertTrue(AndroidAdapter.control_marker_matches(ANDROID_CONTROL_CONTRACT, "123:456"))
        self.assertTrue(AndroidAdapter.control_marker_matches(
            {**ANDROID_CONTROL_CONTRACT, "processId": 123}, "123:456"))

    def test_foreign_process_extra_fields_and_wrong_types_are_rejected(self):
        for marker in ({**ANDROID_CONTROL_CONTRACT, "processId": 124},
                       {**ANDROID_CONTROL_CONTRACT, "processId": "123"},
                       {**ANDROID_CONTROL_CONTRACT, "processId": True},
                       {**ANDROID_CONTROL_CONTRACT, "processId": 123, "unexpected": 1},
                       {**ANDROID_CONTROL_CONTRACT, "processId": 123, "probe": "foreign.js"}):
            self.assertFalse(AndroidAdapter.control_marker_matches(marker, "123:456"))


@unittest.skipUnless(shutil.which("node"), "Node is required for probe execution")
class NativeMotionHistoryTest(unittest.TestCase):
    def test_missing_native_source_preserves_direct_avatar_observation(self):
        source = PROBE.read_text()
        functions = source[source.index("    function observeVerticalMotion("):
                           source.index("    function sample(")]
        update = source[source.index("    function updateProbe("):
                        source.index("    Script.update.connect(updateProbe)")]
        program = """
var androidControlProcessId = 123, nativeMotionAvailable = false;
var nativeMotionLastSequence = 0, nativeMotionUpdatedEpochMs = 0;
var nativeMotionLastRequestEpochMs = 0, nativeMotionUrl = 'missing.json';
var verticalObservationPrevious = null, verticalJumpActive = false;
var sceneReady = true, flightNormalizationAllowed = false, flightNormalizationActive = false;
var verticalEvents = {jumpCount:0,jumpCompletedCount:0,flightCount:0,
 lastJumpStartY:null,lastJumpPeakY:null,lastJumpLandingY:null};
var current = {y:1,air:false};
var MyAvatar = {get position(){return {y:current.y}},
 isInAir:function(){return current.air},isFlying:function(){return false}};
var Script = {require:function(){throw new Error('missing native source')}};
Script.require.cache = {};
Script.require.resolve = function(){throw new Error('missing module')};
Date.now = function(){return 10000};
var lastSampleEpochMs = 10000, sampleIntervalMs = 250;
""" + functions + update + """
updateProbe(); current={y:1.4,air:true}; updateProbe();
current={y:1,air:false}; updateProbe();
console.log(JSON.stringify({events:verticalEvents,native:nativeMotionAvailable}));
"""
        result = subprocess.run(["node", "-e", program], check=True,
                                capture_output=True, text=True)
        value = json.loads(result.stdout)
        self.assertFalse(value["native"])
        self.assertEqual(1, value["events"]["jumpCompletedCount"])
        self.assertAlmostEqual(1.4, value["events"]["lastJumpPeakY"])

    def run_history(self, history, poll=False):
        source = PROBE.read_text()
        functions = source[source.index("    function observeVerticalMotion("):
                           source.index("    function sample(")]
        program = """
var androidControlProcessId = 123, nativeMotionLastSequence = 0;
var nativeMotionUpdatedEpochMs = 0, verticalObservationPrevious = null;
var nativeMotionAvailable = false;
var nativeMotionLastRequestEpochMs = 0, nativeMotionUrl = 'native-motion.json';
var sceneReady = true, flightNormalizationAllowed = false;
var flightNormalizationActive = false, verticalJumpActive = false;
var verticalEvents = {jumpCount:0,jumpCompletedCount:0,flightCount:0,
 lastJumpStartY:null,lastJumpPeakY:null,lastJumpLandingY:null,
 lastFlightStartY:null,lastFlightPeakY:null};
""" + functions + "\nvar history = " + json.dumps(history) + ";\n"
        if poll:
            program += """
var Script = {require:function(id){Script.require.cache[id]=history;return history}};
Script.require.cache = {unrelated: {keep:true}};
Script.require.resolve = function(id){return id};
Date.now = function(){return 10000};
pollNativeMotion(10000); pollNativeMotion(10500);
verticalEvents.cachedModules = Object.keys(Script.require.cache);
"""
        else:
            program += "consumeNativeMotion(history,10000);consumeNativeMotion(history,10000);\n"
        program += """
verticalEvents.nativeMotionAvailable = nativeMotionAvailable;
console.log(JSON.stringify(verticalEvents));
"""
        result = subprocess.run(["node", "-e", program], check=True,
                                capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_one_use_native_modules_are_released_without_clearing_other_modules(self):
        result = self.run_history(self.history(), poll=True)
        self.assertEqual(["unrelated"], result["cachedModules"])
        self.assertEqual(1, result["jumpCount"])
        self.assertEqual(1, result["jumpCompletedCount"])

    def history(self, *, flying=False, landed=True):
        values = [(1.0, False, False), (1.4, True, flying)]
        if landed:
            values.append((1.0, False, False))
        return {"schemaVersion": 1, "processId": 123,
                "source": "native-avatar-motion", "updatedEpochMs": 9900,
                "samples": [{"sampleSequence": i + 1, "sampleEpochMs": 9500 + i * 100,
                             "avatarMotion": {"position": {"y": y},
                                              "inAir": air, "flying": flight}}
                            for i, (y, air, flight) in enumerate(values)]}

    def test_short_jump_survives_delayed_read_without_duplicate_events(self):
        result = self.run_history(self.history())
        self.assertEqual(1, result["jumpCount"])
        self.assertEqual(1, result["jumpCompletedCount"])
        self.assertAlmostEqual(0.4, result["lastJumpPeakY"] - result["lastJumpStartY"])
        self.assertEqual(1.0, result["lastJumpLandingY"])
        self.assertTrue(result["nativeMotionAvailable"])

    def test_stale_or_other_process_history_cannot_supply_a_jump(self):
        for key, value in (("processId", 124), ("updatedEpochMs", 4000),
                           ("updatedEpochMs", 12000), ("source", "injected-command")):
            with self.subTest(key=key, value=value):
                history = self.history()
                history[key] = value
                result = self.run_history(history)
                self.assertEqual(0, result["jumpCount"])
                self.assertFalse(result["nativeMotionAvailable"])

    def test_flight_is_not_jump_and_missing_landing_is_not_completed(self):
        flight = self.run_history(self.history(flying=True))
        self.assertEqual(0, flight["jumpCount"])
        self.assertEqual(1, flight["flightCount"])
        self.assertEqual(0, self.run_history(self.history(landed=False))["jumpCompletedCount"])

    def test_malformed_motion_cannot_supply_a_jump(self):
        history = self.history()
        history["samples"][1]["avatarMotion"]["inAir"] = "true"
        self.assertEqual(0, self.run_history(history)["jumpCount"])


if __name__ == "__main__":
    unittest.main()
