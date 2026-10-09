"""Keep native permission capability and Settings observations exact."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_permission
from adapters.ios.adapter import IOSAdapter


class NativePermissionTest(unittest.TestCase):
    def setUp(self):
        self.target = {"platform":"ios", "physical":True, "appId":"org.example.client",
            "testBuild":{"resultsDirectory":"owned"}, "probe":{"kind":"ios-documents"},
            "nativePermission":{"kind":"ios-settings-ui","permissionId":"microphone"}}
        self.receipt = {"snapshot":{"schemaVersion":1,"permissionId":"microphone","state":"granted"},
                       "processBefore":123,"processAfter":123,"stoppedByOperatingSystem":False}

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
        return adapter,client

    def test_set_requires_the_independently_observed_requested_switch_state(self):
        adapter,client=self.adapter()
        self.assertEqual({"performed":True},adapter.invoke("selected","permission.set",
                         {"permissionId":"microphone","state":"granted"}))
        client.execute.assert_called_with("session","mobile: overteMicrophonePermission",
                                         {"permissionId":"microphone","state":"granted"})
        with self.assertRaises(RuntimeError):
            adapter.invoke("selected","permission.set",{"permissionId":"microphone","state":"denied"})

    def test_process_restart_remains_a_failure_until_physical_recovery_is_qualified(self):
        adapter,_=self.adapter();self.receipt["processAfter"]=124
        with self.assertRaisesRegex(RuntimeError,"ASSERTION.*restarted"):
            adapter.invoke("selected","permission.snapshot",{"permissionId":"microphone"})
        adapter.reset_launch_state.assert_called_once()
        adapter.launch_ios_test_build.assert_called_once()


if __name__ == "__main__":unittest.main()
