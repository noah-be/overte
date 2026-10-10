"""Exercise native UID/package permission precedence and ambiguous observations."""
import unittest
from tests.device.adapters.pico4.permission_observation import permission_snapshot


class NativePermissionObservation(unittest.TestCase):
    def observe(self, granted, appops):
        class Adb:
            def shell(self, target, *args):
                return ("android.permission.RECORD_AUDIO: granted=" + granted
                        if args[0] == "dumpsys" else appops)
        return permission_snapshot(Adb(), "synthetic-device", "org.overte.pico")["state"]

    def test_uid_denial_overrides_package_allow(self):
        self.assertEqual(self.observe("true", "Uid mode: RECORD_AUDIO: ignore\nRECORD_AUDIO: allow"), "denied")

    def test_uid_grant_cannot_replace_missing_runtime_grant(self):
        self.assertEqual(self.observe("false", "Uid mode: RECORD_AUDIO: allow"), "denied")

    def test_package_denial_applies_when_uid_is_default(self):
        self.assertEqual(self.observe("true", "Uid mode: RECORD_AUDIO: default\nRECORD_AUDIO: deny"), "denied")

    def test_default_appops_retains_native_runtime_grant(self):
        self.assertEqual(self.observe("true", "No operations."), "granted")

    def test_ambiguous_native_modes_are_rejected(self):
        with self.assertRaises(RuntimeError):
            self.observe("true", "Uid mode: RECORD_AUDIO: allow\nUid mode: RECORD_AUDIO: ignore")


if __name__ == '__main__':
    unittest.main()
