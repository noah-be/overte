"""Native observation contracts reject missing frames and ambiguous OS evidence."""
from io import BytesIO
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.shared_appium.android_observation import (classify_frame,
    permission_snapshot, presented_frames)

class FakeAdb:
    def __init__(self, runtime="true", mode="foreground", frames="123 456 789"):
        self.runtime, self.mode, self.frames = runtime, mode, frames
        self.calls = []
    def shell(self, device, *args):
        self.calls.append(args)
        if args[:2] == ("dumpsys", "package"):
            return "android.permission.RECORD_AUDIO: granted=" + self.runtime
        if args[:3] == ("cmd", "appops", "get"):
            return "RECORD_AUDIO: " + self.mode
        return "RequestedLayerState{abc SurfaceView[owned.package/Activity](BLAST)#4 parentId=3}"
    def execute(self, args, *, target):
        self.calls.append(tuple(args))
        return "16666667\n" + self.frames + "\n"

class AndroidObservationTest(unittest.TestCase):
    def test_os_appops_denial_overrides_runtime_grant(self):
        self.assertEqual("denied", permission_snapshot(FakeAdb(mode="ignore"), "mock", "owned.package")["state"])
        self.assertEqual("denied", permission_snapshot(FakeAdb(runtime="false"), "mock", "owned.package")["state"])
        self.assertEqual("granted", permission_snapshot(FakeAdb(), "mock", "owned.package")["state"])
    def test_ambiguous_permission_fails_closed(self):
        with self.assertRaises(RuntimeError):
            permission_snapshot(FakeAdb(runtime="unknown"), "mock", "owned.package")
    def test_uid_and_package_modes_follow_os_precedence(self):
        for uid, package, expected in (("foreground", "allow", "granted"),
                                       ("ignore", "allow", "denied"),
                                       ("default", "ignore", "denied")):
            class ModesAdb(FakeAdb):
                def shell(self, device, *args):
                    if args[:3] == ("cmd", "appops", "get"):
                        return f"Uid mode: RECORD_AUDIO: {uid}\nRECORD_AUDIO: {package}; time=+1s"
                    return super().shell(device, *args)
            with self.subTest(uid=uid, package=package):
                self.assertEqual(expected, permission_snapshot(ModesAdb(), "mock", "owned.package")["state"])
    def test_surface_name_is_one_remote_argument(self):
        adb = FakeAdb()
        self.assertEqual(456, presented_frames(adb, "mock", "owned.package"))
        import shlex
        self.assertEqual(["dumpsys", "SurfaceFlinger", "--latency",
                         "abc SurfaceView[owned.package/Activity](BLAST)#4"], shlex.split(adb.calls[-1][1]))
    def test_absent_or_pending_presentation_cannot_pass(self):
        for row in ("0 0 0", "123 9223372036854775807 789", "unavailable"):
            with self.assertRaises(RuntimeError):
                presented_frames(FakeAdb(frames=row), "mock", "owned.package")
    def test_black_interior_cannot_be_hidden_by_system_bars(self):
        from PIL import Image, ImageDraw
        picture = Image.new("RGB", (320, 160), "black")
        ImageDraw.Draw(picture).rectangle((0, 0, 319, 15), fill="white")
        buffer = BytesIO(); picture.save(buffer, format="PNG")
        self.assertTrue(classify_frame(buffer.getvalue()))
        picture.paste("grey", (64, 32, 256, 128))
        buffer = BytesIO(); picture.save(buffer, format="PNG")
        self.assertFalse(classify_frame(buffer.getvalue()))

if __name__ == "__main__": unittest.main()
