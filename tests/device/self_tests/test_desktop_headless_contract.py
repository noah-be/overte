#!/usr/bin/env python3
"""Device-free input and scene contracts for isolated Linux desktop tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "adapters/desktop_oculix/adapter.py"
SPEC = importlib.util.spec_from_file_location("headless_contract_adapter", ADAPTER_PATH)
ADAPTER_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ADAPTER_MODULE)


FAKE_EXECUTABLE = "#!" + sys.executable + "\nimport time\ntime.sleep(0.01)\n"
FAKE_XDOTOOL = r'''#!PYTHON
import json, os, pathlib, sys
record = {
    "arguments": sys.argv[1:],
    "environment": {name: os.environ.get(name) for name in (
        "DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET",
        "DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_ADDRESS",
        "DBUS_STARTER_BUS_TYPE", "AT_SPI_BUS_ADDRESS", "XDG_SESSION_TYPE",
        "GDK_BACKEND", "SDL_VIDEODRIVER", "QT_QPA_PLATFORM",
        "GTK_USE_PORTAL", "QT_NO_XDG_DESKTOP_PORTAL")},
}
with pathlib.Path(os.environ["HEADLESS_XDOTOOL_LOG"]).open("a", encoding="utf-8") as out:
    out.write(json.dumps(record) + "\n")
arguments = sys.argv[1:]
if arguments and arguments[0] == "search":
    print("1001\n1002")
elif arguments and arguments[0] == "getwindowgeometry":
    window = arguments[-1]
    if window == "1001":
        print("WINDOW=1001\nX=0\nY=0\nWIDTH=640\nHEIGHT=480\nSCREEN=0")
    else:
        print("WINDOW=1002\nX=0\nY=0\nWIDTH=1280\nHEIGHT=720\nSCREEN=0")
'''.replace("PYTHON", sys.executable)


class HeadlessDesktopContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="headless-contract-")
        self.root = Path(self.temporary.name)
        self.executable = self.root / "interface"
        self.xdotool = self.root / "xdotool"
        self.screenshot = self.root / "screenshot"
        self.executable.write_text(FAKE_EXECUTABLE, encoding="utf-8")
        self.xdotool.write_text(FAKE_XDOTOOL, encoding="utf-8")
        self.screenshot.write_text(FAKE_EXECUTABLE, encoding="utf-8")
        for executable in (self.executable, self.xdotool, self.screenshot):
            executable.chmod(0o700)
        self.log = self.root / "xdotool.jsonl"
        self.probe = self.root / "probe.json"
        target = {
            "selector": "headless", "platform": "linux", "physical": False,
            "enabled": True, "executable": str(self.executable),
            "arguments": [], "windowTitle": "Overte", "environment": {
                "QT_QPA_PLATFORM": "xcb",
            },
            "isolatedX11": True, "xwayland": False, "inputDriver": "xdotool",
            "xdotoolExecutable": str(self.xdotool),
            "xdotoolSha256": self._sha(self.xdotool),
            "screenshotExecutable": str(self.screenshot),
            "screenshotSha256": self._sha(self.screenshot),
            "screenshotArguments": [],
            "gpuHeadlessRuntime": {
                "virtualMonitor": "1280x720",
                "allowedVendorPatterns": ["Test Vendor"],
                "allowedRendererPatterns": ["Test Renderer"],
                **{
                    field + "Executable": str(self.executable)
                    for field in ("dbusRunSession", "dbusDaemon", "mutter", "python",
                                  "xwayland", "glxinfo", "xrandr")
                },
                **{
                    field + "Sha256": self._sha(self.executable)
                    for field in ("dbusRunSession", "dbusDaemon", "mutter", "python",
                                  "xwayland", "glxinfo", "xrandr")
                },
            },
            "tabletClosePoint": {"xFraction": 0.1, "yFraction": 0.1},
            "probe": {"kind": "host-file", "path": str(self.probe)},
        }
        self.config = self.root / "targets.json"
        self.config.write_text(json.dumps({"schemaVersion": 1, "targets": [target]}),
                               encoding="utf-8")
        with patch.dict(os.environ, {
            "OVERTE_DESKTOP_TARGETS": str(self.config),
            "OVERTE_DEVICE_STATE_ROOT": str(self.root / "state"),
        }, clear=True):
            self.adapter = ADAPTER_MODULE.DesktopAdapter("linux")
        self.target = self.adapter.target("headless")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def safe_environment(self) -> dict[str, str]:
        hostile = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HEADLESS_XDOTOOL_LOG": str(self.log),
            "WAYLAND_DISPLAY": "wayland-0", "WAYLAND_SOCKET": "wayland-0",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "DBUS_STARTER_ADDRESS": "unix:path=/run/user/1000/starter-bus",
            "DBUS_STARTER_BUS_TYPE": "session",
            "AT_SPI_BUS_ADDRESS": "unix:path=/run/user/1000/at-spi/bus",
            "XDG_SESSION_TYPE": "wayland", "GTK_USE_PORTAL": "1",
            "QT_NO_XDG_DESKTOP_PORTAL": "0",
        }
        environment = ADAPTER_MODULE.GpuHeadlessLifecycle._base_environment(hostile)
        environment.update({
            "DISPLAY": ":7777", "XAUTHORITY": str(self.root / "Xauthority"),
            "XDG_RUNTIME_DIR": str(self.root / "runtime"),
            "XDG_SESSION_TYPE": "x11", "GDK_BACKEND": "x11",
            "SDL_VIDEODRIVER": "x11", "QT_QPA_PLATFORM": "xcb",
        })
        return environment

    def calls(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text(
            encoding="utf-8").splitlines()]

    def test_scene_is_bound_to_initial_process_and_never_relaunches(self) -> None:
        state = {
            "pid": 4242, "identity": "4242:token", "processToken": "token",
            "initialSceneUrl": "http://fixture/scene.json",
        }
        with patch.object(self.adapter, "read_state", return_value=state), patch.object(
                self.adapter, "state_alive", return_value=True), patch.object(
                self.adapter, "visual_action") as visual:
            result = self.adapter.invoke(
                "headless", "scene.load", {"url": "http://fixture/scene.json"})
            self.assertEqual({"requested": True, "lifecycle": "initial-process"}, result)
            visual.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "initial-process|live relaunch"):
                self.adapter.invoke(
                    "headless", "scene.load", {"url": "http://other/scene.json"})

    def test_failed_interface_spawn_cleans_the_private_lifecycle(self) -> None:
        with patch.object(self.adapter, "gpu_headless_lifecycle") as factory, patch.object(
                ADAPTER_MODULE.subprocess, "Popen", side_effect=OSError("spawn failed")):
            lifecycle = factory.return_value
            lifecycle.ensure_started.return_value = self.safe_environment()
            with self.assertRaisesRegex(OSError, "spawn failed"):
                self.adapter.launch("headless", self.target)
        lifecycle.cleanup.assert_called_once_with()

    def test_look_move_and_tab_toggle_use_only_private_xdotool(self) -> None:
        environment = self.safe_environment()
        with patch.object(self.adapter, "runtime_environment",
                          return_value=environment), patch.object(
                              ADAPTER_MODULE.time, "sleep", return_value=None) as sleep:
            self.adapter.linux_visual_action(
                self.target, "look", {"processId": 4242,
                                      "horizontal": 0.25, "vertical": 0.1})
            self.adapter.linux_visual_action(
                self.target, "move", {"processId": 4242,
                                      "direction": "forward", "durationSeconds": 0.1})
            self.adapter.linux_visual_action(
                self.target, "tablet-open", {"processId": 4242})
            self.adapter.linux_visual_action(
                self.target, "tablet-close", {"processId": 4242})

        self.assertEqual(4, sleep.call_args_list.count(call(0.35)))

        calls = self.calls()
        arguments = [item["arguments"] for item in calls]
        self.assertEqual(4, arguments.count(
            ["search", "--onlyvisible", "--pid", "4242"]))
        self.assertEqual(4, arguments.count(
            ["windowactivate", "--sync", "1002"]))
        self.assertFalse(any(argument and argument[0] == "windowfocus"
                             for argument in arguments),
                         "raw XSetInputFocus must not bypass WM activation")
        self.assertIn(["mousedown", "3"], arguments)
        self.assertIn(["mouseup", "3"], arguments)
        self.assertEqual(1, arguments.count(
            ["keydown", "w", "sleep", "0.1", "keyup", "w"]))
        self.assertEqual(2, arguments.count(
            ["keydown", "Tab", "sleep", "0.05", "keyup", "Tab"]))
        for argument in arguments:
            if argument and argument[0] in {"keydown", "keyup", "key"}:
                self.assertNotIn(
                    "--window", argument,
                    "focused headless keyboard input must use global XTEST events")
        keyboard_calls = [argument for argument in arguments
                          if argument and argument[0] == "keydown"]
        self.assertEqual(3, len(keyboard_calls),
                         "each key hold must use exactly one xdotool process")
        flattened = " ".join(" ".join(argument) for argument in arguments)
        self.assertNotIn("ctrl", flattened.lower())
        self.assertNotIn("click", flattened.lower())
        self.assertNotIn("1001", " ".join(
            " ".join(argument) for argument in arguments
            if argument and argument[0] == "windowactivate"))

        for item in calls:
            child = item["environment"]
            for forbidden in (
                    "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DBUS_SESSION_BUS_ADDRESS",
                    "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE",
                    "AT_SPI_BUS_ADDRESS"):
                self.assertIsNone(child[forbidden])
            self.assertEqual(":7777", child["DISPLAY"])
            self.assertEqual(str(self.root / "Xauthority"), child["XAUTHORITY"])
            self.assertEqual("x11", child["XDG_SESSION_TYPE"])
            self.assertEqual("x11", child["GDK_BACKEND"])
            self.assertEqual("x11", child["SDL_VIDEODRIVER"])
            self.assertEqual("xcb", child["QT_QPA_PLATFORM"])
            self.assertEqual("0", child["GTK_USE_PORTAL"])
            self.assertEqual("1", child["QT_NO_XDG_DESKTOP_PORTAL"])

    def test_move_hold_is_one_bounded_process_after_exact_pid_activation(self) -> None:
        environment = self.safe_environment()
        with patch.object(self.adapter, "runtime_environment",
                          return_value=environment), patch.object(
                              ADAPTER_MODULE.time, "sleep", return_value=None):
            self.adapter.linux_visual_action(
                self.target, "move", {"processId": 4242,
                                      "direction": "forward",
                                      "durationSeconds": 2.0})

        arguments = [item["arguments"] for item in self.calls()]
        self.assertEqual(1, arguments.count(
            ["search", "--onlyvisible", "--pid", "4242"]))
        self.assertEqual(1, arguments.count(
            ["windowactivate", "--sync", "1002"]))
        self.assertEqual(1, arguments.count(
            ["keydown", "w", "sleep", "2", "keyup", "w"]))
        self.assertEqual(1, len([
            argument for argument in arguments
            if argument and argument[0] == "keydown"
        ]), "the entire hold must use one xdotool process")
        self.assertFalse(any("--window" in argument for argument in arguments
                             if argument and argument[0] in {"keydown", "keyup", "key"}))
        self.assertFalse(any("1001" in argument for argument in arguments
                             if argument and argument[0] == "windowactivate"))

    def test_tablet_operation_contract_uses_tab_actions_and_probe_state(self) -> None:
        state = {"pid": 4242, "identity": "4242:token", "processToken": "token"}
        closed = {"tablet": {"open": False}}
        opened = {"tablet": {"open": True}}
        with patch.object(self.adapter, "read_state", return_value=state), patch.object(
                self.adapter, "state_alive", return_value=True), patch.object(
                self.adapter, "visual_action") as visual, patch.object(
                ADAPTER_MODULE, "read_fresh_json", side_effect=[closed, opened]):
            result = self.adapter.invoke("headless", "tablet.open", {})
        self.assertEqual({"performed": True, "changed": True}, result)
        visual.assert_called_once_with(
            self.target, "tablet-open", {
                "processId": 4242, "normalizeKeyUp": False})

        with patch.object(self.adapter, "read_state", return_value=state), patch.object(
                self.adapter, "state_alive", return_value=True), patch.object(
                self.adapter, "visual_action") as visual, patch.object(
                ADAPTER_MODULE, "read_fresh_json", side_effect=[opened, closed]), patch.object(
                ADAPTER_MODULE.time, "sleep", return_value=None):
            result = self.adapter.invoke("headless", "tablet.close", {})
        self.assertEqual({"performed": True, "changed": True}, result)
        visual.assert_called_once_with(
            self.target, "tablet-close", {
                "processId": 4242, "normalizeKeyUp": False})

    def test_tablet_retry_is_probe_gated_bounded_and_normalizes_release(self) -> None:
        state = {"pid": 4242, "identity": "4242:token", "processToken": "token"}
        opened = {"tablet": {"open": True}}
        closed = {"tablet": {"open": False}}
        # Initial state, ten unchanged polls after the first pulse, then the
        # first poll after the retry observes the requested transition.
        observations = [opened] + [opened] * 10 + [closed]
        with patch.object(self.adapter, "read_state", return_value=state), patch.object(
                self.adapter, "state_alive", return_value=True), patch.object(
                self.adapter, "visual_action") as visual, patch.object(
                ADAPTER_MODULE, "read_fresh_json", side_effect=observations), patch.object(
                ADAPTER_MODULE.time, "sleep", return_value=None):
            result = self.adapter.invoke("headless", "tablet.close", {})
        self.assertEqual({"performed": True, "changed": True}, result)
        self.assertEqual([
            call(self.target, "tablet-close", {
                "processId": 4242, "normalizeKeyUp": False}),
            call(self.target, "tablet-close", {
                "processId": 4242, "normalizeKeyUp": True}),
        ], visual.call_args_list)


if __name__ == "__main__":
    unittest.main()
