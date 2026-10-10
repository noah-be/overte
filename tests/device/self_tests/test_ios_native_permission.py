"""Keep native permission capability and Settings observations exact."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import sys
import unittest
import time
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.appium.adapter import AppiumAdapter
from adapters.ios import native_permission
from adapters.ios.adapter import IOSAdapter
from contracts import validate_operation_result


class NativePermissionTest(unittest.TestCase):
    def setUp(self):
        self.target = {"platform":"ios", "physical":True, "appId":"org.example.client",
            "testBuild":{"resultsDirectory":"owned", "fixtureOrigin":"http://fixture.invalid", "scenePath":"/scene.json"}, "probe":{"kind":"ios-documents"},
            "nativePermission":{"kind":"ios-settings-ui","permissionId":"microphone"}}
        self.receipt = {"snapshot":{"schemaVersion":1,"permissionId":"microphone","state":"granted"},
                       "processBefore":123,"processAfter":123,"stoppedByOperatingSystem":False,
                       "recoveryLaunchEpochMs":int(time.time()*1000)}

    def test_binding_is_explicit_and_microphone_only(self):
        self.assertFalse(native_permission.enabled({}))
        self.assertTrue(native_permission.enabled(self.target))
        for value in ({"kind":"simulated","permissionId":"microphone"},
                      {"kind":"ios-settings-ui","permissionId":"camera"}):
            with self.assertRaises(ValueError):native_permission.enabled({"nativePermission":value})

    def test_foreign_process_ambiguous_state_and_invalid_types_are_rejected(self):
        self.assertEqual("granted",native_permission.observation(self.receipt,"123")["state"])
        for field,value in (("processBefore",124),("processAfter",True),
                            ("stoppedByOperatingSystem",1)):
            invalid=copy.deepcopy(self.receipt);invalid[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                native_permission.observation(invalid,"123")
        for field,value in (("state","unknown"),("schemaVersion",True),("permissionId","camera")):
            invalid=copy.deepcopy(self.receipt);invalid["snapshot"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                native_permission.observation(invalid,"123")

    def adapter(self):
        adapter=IOSAdapter.__new__(IOSAdapter)
        client=Mock();client.execute.return_value=self.receipt
        adapter.target=Mock(return_value=self.target)
        adapter.ensure_session=Mock(return_value=(client,"session",{}))
        adapter.assert_ios_process_identity=Mock(return_value="123")
        adapter.native_process=Mock(return_value={"pid":124,"foreground":True,"bundleId":"org.example.client"})
        adapter.reset_launch_state=Mock()
        adapter.launch_ios_test_build=Mock()
        adapter.wait_first_ios_probe=Mock()
        adapter.save_session=Mock()
        return adapter,client

    def test_set_requires_the_independently_observed_requested_switch_state(self):
        adapter,client=self.adapter()
        self.assertEqual({"performed":True},adapter.invoke("selected","permission.set",
                         {"permissionId":"microphone","state":"granted"}))
        client.execute.assert_called_with("session","mobile: overteMicrophonePermission",
                                         {"permissionId":"microphone","state":"granted"})
        with self.assertRaises(RuntimeError):
            adapter.invoke("selected","permission.set",{"permissionId":"microphone","state":"denied"})

    def test_unattested_restart_remains_a_failure(self):
        adapter,_=self.adapter();self.receipt["processAfter"]=124
        with self.assertRaisesRegex(RuntimeError,"ASSERTION.*restarted"):
            adapter.invoke("selected","permission.set",{"permissionId":"microphone","state":"granted"})
        adapter.reset_launch_state.assert_called_once()
        adapter.wait_first_ios_probe.assert_called_once()
        adapter.launch_ios_test_build.assert_not_called()

    def test_snapshot_observes_native_audio_without_visiting_settings(self):
        adapter,client=self.adapter()
        value={"ok":True,"iosPermission":1,"iosForeground":True,
               "sampleEpochMs":int(time.time()*1000)}
        with patch.object(AppiumAdapter,"invoke",return_value=value) as exchange:
            observed=adapter.invoke("selected","permission.snapshot",{"permissionId":"microphone"})
        self.assertEqual("granted",observed["state"])
        client.execute.assert_not_called()
        self.assertEqual(("selected","voice.exchange"),exchange.call_args.args[:2])
        self.assertEqual("status",exchange.call_args.args[2]["action"])
        adapter.assert_ios_process_identity.assert_called()
        adapter.assert_ios_process_identity.side_effect=["123","124"]
        with patch.object(AppiumAdapter,"invoke",return_value=value),self.assertRaisesRegex(RuntimeError,"crossed process"):
            adapter.invoke("selected","permission.snapshot",{"permissionId":"microphone"})

    def test_native_audio_observation_rejects_unknown_stale_and_background_state(self):
        value={"ok":True,"iosPermission":1,"iosForeground":True,
               "sampleEpochMs":int(time.time()*1000)}
        self.assertEqual("denied",native_permission.audio_snapshot({**value,"iosPermission":2})["state"])
        for change in ({"iosPermission":0},{"iosPermission":3},{"iosPermission":True},
                       {"iosForeground":False},{"ok":False},{"sampleEpochMs":1},
                       {"sampleEpochMs":float("nan")},{"sampleEpochMs":True}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                native_permission.audio_snapshot({**value,**change})

    def test_only_observed_settings_termination_with_a_verified_replacement_is_allowed(self):
        adapter,_=self.adapter()
        self.receipt.update(processAfter=124,stoppedByOperatingSystem=True)
        result=adapter.invoke("selected","permission.set",{"permissionId":"microphone","state":"granted"})
        self.assertEqual({"performed":True,"recovery":{
            "kind":"ios-settings-process-restart","permissionId":"microphone",
            "processBefore":123,"processAfter":124,"stoppedByOperatingSystem":True}},result)
        adapter.wait_first_ios_probe.assert_called_once()
        adapter.launch_ios_test_build.assert_not_called()
        for actual in (None,{"pid":125,"foreground":True},{"pid":124,"foreground":False}):
            adapter.native_process.return_value=actual
            with self.subTest(actual=actual),self.assertRaises(RuntimeError):
                adapter.invoke("selected","permission.set",{"permissionId":"microphone","state":"granted"})
        self.receipt["stoppedByOperatingSystem"]=False
        adapter.native_process.return_value={"pid":124,"foreground":True}
        with self.assertRaises(RuntimeError):
            adapter.invoke("selected","permission.set",{"permissionId":"microphone","state":"granted"})

    def test_portable_permission_result_rejects_forged_or_ambiguous_recovery(self):
        recovery={"kind":"ios-settings-process-restart","permissionId":"microphone",
                  "processBefore":123,"processAfter":124,"stoppedByOperatingSystem":True}
        self.assertEqual({"performed":True},validate_operation_result("permission.set",{"performed":True}))
        for field,value in (("kind","arbitrary-restart"),("permissionId","camera"),
                            ("processAfter",123),("processAfter",True),("stoppedByOperatingSystem",False)):
            invalid={**recovery,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_operation_result("permission.set",{"performed":True,"recovery":invalid})


if __name__ == "__main__":unittest.main()
