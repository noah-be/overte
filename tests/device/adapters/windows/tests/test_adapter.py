#!/usr/bin/env python3
"""Hardware-free contracts for the Windows desktop adapter."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch


DEVICE_ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = DEVICE_ROOT / "adapters/windows/adapter.py"
MANIFEST = DEVICE_ROOT / "adapters/windows/adapter.json"
VERIFIER = DEVICE_ROOT / "verify_adapter.py"
SPEC = importlib.util.spec_from_file_location("windows_adapter", ADAPTER_PATH)
WINDOWS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(WINDOWS)


class WindowsAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="windows-adapter-test-")
        self.root = Path(self.temporary.name)
        self.jar = self.root / "oculix.jar"
        self.jar.write_bytes(b"pinned mock OculiX")
        self.executable = self.root / "Interface.exe"
        self.executable.write_bytes(b"mock Interface")
        self.executable.chmod(0o700)
        self.java = Path(sys.executable).resolve()
        self.probe = self.root / "probe.json"
        self.probe.write_text("{}", encoding="utf-8")
        self.target = {
            "selector": "windows-lab",
            "displayName": "Windows Lab",
            "platform": "windows",
            "physical": False,
            "enabled": True,
            "executable": str(self.executable),
            "executableSha256": self.digest(self.executable),
            "arguments": [],
            "workingDirectory": str(self.root),
            "windowTitle": "Overte",
            "oculixJar": str(self.jar),
            "oculixSha256": self.digest(self.jar),
            "javaExecutable": str(self.java),
            "javaSha256": self.digest(self.java),
            "javaArguments": [],
            "environment": {"OVERTE_WINDOWS_TEST": "1"},
            "probe": {"kind": "injected-test-script"},
            "clientControl": {"kind": "fixture-command-http"},
        }
        self.config = self.root / "targets.json"
        self.write_config()
        self.environment = {
            **os.environ,
            "OVERTE_WINDOWS_TARGETS": str(self.config),
            "OVERTE_DEVICE_STATE_ROOT": str(self.root / "state"),
            "OVERTE_DEVICE_ARTIFACT_DIR": str(self.root / "artifacts"),
            "OVERTE_E2E_SCENE_URL": "http://127.0.0.1:41000/scene.json",
        }
        (self.root / "artifacts").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_config(self) -> None:
        self.config.write_text(
            json.dumps({"schemaVersion": 1, "targets": [self.target]}),
            encoding="utf-8",
        )

    def adapter(self) -> object:
        with patch.dict(os.environ, self.environment, clear=True):
            return WINDOWS.WindowsAdapter()

    def running_state(self) -> dict:
        return {
            "schemaVersion": 2,
            "pid": 4242,
            "processToken": "token",
            "identity": "4242:token",
            "executablePath": str(self.executable.resolve()),
            "initialSceneUrl": self.environment["OVERTE_E2E_SCENE_URL"],
        }

    @staticmethod
    def response(payload: dict, *, status: int = 200) -> MagicMock:
        response = MagicMock(status=status)
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        return response

    def test_manifest_satisfies_adapter_protocol(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERIFIER), "--adapter-manifest", str(MANIFEST),
             "--check-cleanup"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self.environment,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("for 1 target(s)", result.stdout)

    def test_configuration_is_windows_only_and_pins_all_runtime_files(self) -> None:
        self.target["platform"] = "not-windows"
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "non-Windows"):
            WINDOWS.WindowsAdapter()

        self.target["platform"] = "windows"
        self.target["javaSha256"] = "0" * 63
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "javaSha256"):
            WINDOWS.WindowsAdapter()

        self.target["javaSha256"] = self.digest(self.java)
        self.target["selector"] = "unsafe/selector"
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "bounded identifiers"):
            WINDOWS.WindowsAdapter()

    def test_control_channel_requires_the_injected_probe_and_http_fixture(self) -> None:
        self.target["clientControl"] = {"kind": "probe-command-file"}
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "fixture-command-http"):
            WINDOWS.WindowsAdapter()

        self.target["clientControl"] = {"kind": "fixture-command-http"}
        self.target["probe"] = {"kind": "host-file", "path": str(self.probe)}
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "injected in-client probe"):
            WINDOWS.WindowsAdapter()

    def test_physical_target_rejects_a_non_windows_host(self) -> None:
        self.target["physical"] = True
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
                WINDOWS.os, "name", "posix"), self.assertRaisesRegex(
                    RuntimeError, "require a Windows host"):
            WINDOWS.WindowsAdapter().discover()

    def test_capabilities_cover_the_current_desktop_contract(self) -> None:
        adapter = self.adapter()
        discovered = adapter.discover()[0]
        self.assertEqual("windows", discovered["platform"])
        expected = {
            "app.stop", "artifact.screenshot", "asset.load", "input.fly",
            "input.jump", "input.look", "input.move", "navigation.enter-domain",
            "probe.snapshot", "scene.load", "sound.play", "tablet.close",
            "tablet.open",
        }
        self.assertTrue(expected.issubset(discovered["capabilities"]))
        self.assertEqual(
            "windows-desktop", adapter.describe("windows-lab")["adapter"])

        uncontrolled = dict(self.target)
        uncontrolled.pop("clientControl")
        controlled_only = {
            "asset.load", "navigation.enter-domain", "scene.load", "sound.play"
        }
        self.assertTrue(controlled_only.isdisjoint(adapter.capabilities(uncontrolled)))

    def test_runtime_hash_mismatch_fails_before_discovery(self) -> None:
        adapter = self.adapter()
        self.jar.write_bytes(b"changed after configuration")
        with self.assertRaisesRegex(RuntimeError, "OculiX runtime JAR failed"):
            adapter.discover()

    def test_target_environment_cannot_reenable_multiple_instances(self) -> None:
        self.target["environment"]["HIFI_ALLOW_MULTIPLE_INSTANCES"] = "1"
        self.write_config()
        inherited = dict(self.environment)
        inherited["GH_TOKEN"] = "must-not-reach-interface"
        inherited["JENKINS_PRIVATE_VALUE"] = "must-not-reach-interface"
        with patch.dict(os.environ, inherited, clear=True):
            environment = WINDOWS.WindowsAdapter().target_environment(self.target)
        self.assertNotIn("HIFI_ALLOW_MULTIPLE_INSTANCES", environment)
        self.assertNotIn("OVERTE_WINDOWS_TARGETS", environment)
        self.assertNotIn("OVERTE_DEVICE_TARGET_SELECTOR", environment)
        self.assertNotIn("GH_TOKEN", environment)
        self.assertNotIn("JENKINS_PRIVATE_VALUE", environment)
        self.assertEqual("1", environment["OVERTE_WINDOWS_TEST"])

    def test_oculix_is_hash_pinned_pid_scoped_and_environment_bounded(self) -> None:
        adapter = self.adapter()
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(WINDOWS.subprocess, "run", return_value=completed) as run:
            adapter.oculix(self.target, "focus", {"processId": 4242})
        arguments = run.call_args.args[0]
        self.assertEqual(str(self.java), arguments[0])
        self.assertIn(str(self.jar), arguments)
        self.assertIn(str(DEVICE_ROOT / "adapters/windows/overte.sikuli"), arguments)
        payload = json.loads(arguments[-1])
        self.assertEqual(4242, payload["processId"])
        self.assertEqual("Overte", payload["windowTitle"])
        self.assertNotIn("HIFI_ALLOW_MULTIPLE_INSTANCES", run.call_args.kwargs["env"])

    def test_oculix_failure_normalizes_input_and_redacts_private_paths(self) -> None:
        adapter = self.adapter()
        failed = subprocess.CompletedProcess([], 9, "", f"failed at {self.jar}")
        recovered = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(
                WINDOWS.subprocess, "run", side_effect=[failed, recovered]) as run, \
                self.assertRaisesRegex(RuntimeError, "<private-path>"):
            adapter.oculix(self.target, "move", {"processId": 4242})
        self.assertIn("release-input", run.call_args_list[1].args[0])

    def test_cleanup_uses_normal_then_forced_windows_process_tree_kill(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(WINDOWS.subprocess, "run", return_value=completed) as run:
            WINDOWS.WindowsAdapter.terminate_process_tree(42, force=False)
            WINDOWS.WindowsAdapter.terminate_process_tree(42, force=True)
        self.assertEqual([
            call(["taskkill", "/PID", "42", "/T"], stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, timeout=15, check=False),
            call(["taskkill", "/PID", "42", "/T", "/F"],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 timeout=15, check=False),
        ], run.call_args_list)

    def test_process_tree_capture_tracks_exact_recursive_child_identities(self) -> None:
        state = self.running_state()
        identities = {
            4242: ("token", str(self.executable.resolve())),
            4300: ("child-a", str(self.root / "QtWebEngineProcess.exe")),
            4400: ("child-b", str(self.root / "crash-handler.exe")),
        }
        with patch.object(WINDOWS.WindowsAdapter, "process_snapshot", return_value={
                4242: 100, 4300: 4242, 4400: 4300, 9999: 100,
        }), patch.object(
                WINDOWS.WindowsAdapter, "process_identity",
                side_effect=lambda pid: identities.get(pid)):
            owned = WINDOWS.WindowsAdapter.owned_processes(state)
        self.assertEqual([4242, 4300, 4400], [item["pid"] for item in owned])
        self.assertEqual("child-b", owned[-1]["processToken"])

    def test_cleanup_escalates_after_a_timed_out_normal_tree_kill(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        owned = [{
            "pid": 4242, "processToken": "token",
            "executablePath": str(self.executable.resolve()),
        }]
        timeout = subprocess.TimeoutExpired(["taskkill"], 15)
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
                adapter, "read_state", return_value=state), patch.object(
                    adapter, "state_alive", side_effect=[True, False]), patch.object(
                        adapter, "owned_processes", return_value=owned), patch.object(
                            adapter, "visual_action"), patch.object(
                                adapter, "owned_process_alive",
                                side_effect=[True, True, True, False, False]), patch.object(
                                    adapter, "terminate_process_tree",
                                    side_effect=[timeout, None]) as terminate, patch.object(
                                        WINDOWS.time, "monotonic",
                                        side_effect=[0.0, 0.0, 6.0]):
            self.assertEqual({"cleaned": True}, adapter.cleanup("windows-lab"))
        self.assertEqual([
            call(4242, force=False), call(4242, force=True),
        ], terminate.call_args_list)

    def test_client_commands_use_scene_origin_and_exact_acknowledgement(self) -> None:
        adapter = self.adapter()
        command = {
            "schemaVersion": 1, "commandId": "scene-exact",
            "action": "scene-load", "url": self.environment["OVERTE_E2E_SCENE_URL"],
        }
        response = self.response(command)
        with patch.object(WINDOWS, "urlopen", return_value=response) as opened:
            adapter.post_client_command(
                self.environment["OVERTE_E2E_SCENE_URL"] + "?location=%2F0%2C2%2C4",
                command)
        request = opened.call_args.args[0]
        self.assertEqual(
            "http://127.0.0.1:41000/e2e-client-command.json", request.full_url)
        self.assertEqual(command, json.loads(request.data))

        response.read.return_value = b'{"schemaVersion":1}'
        with patch.object(WINDOWS, "urlopen", return_value=response), \
                self.assertRaisesRegex(RuntimeError, "exact Windows client command"):
            adapter.post_client_command(
                self.environment["OVERTE_E2E_SCENE_URL"], command)

    def test_navigation_and_asset_reuse_the_authoritative_process(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "post_client_command") as post, patch.object(
                        WINDOWS.subprocess, "Popen") as spawn:
            navigation = adapter.invoke("windows-lab", "navigation.enter-domain", {
                "url": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
            })
            asset = adapter.invoke("windows-lab", "asset.load", {
                "assetId": "texture-rgb-3x1-v1",
                "url": "http://127.0.0.1:41000/assets/texture.png",
                "entityName": "OVERTE_E2E_ASSET_LOAD",
            })
        self.assertEqual({"requested": True}, navigation)
        self.assertEqual({"requested": True}, asset)
        spawn.assert_not_called()
        self.assertEqual("navigate", post.call_args_list[0].args[1]["action"])
        self.assertEqual("asset-load", post.call_args_list[1].args[1]["action"])

    def test_sound_requires_exact_fixture_acknowledgement(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        values = {
            "schemaVersion": 1,
            "commandId": "sound-windows",
            "url": "http://127.0.0.1:41000/audio/tone.wav",
            "commandUrl": "http://127.0.0.1:41000/sound-command.json",
        }
        accepted = {
            "schemaVersion": 1,
            "commandId": "sound-windows",
            "action": "play",
            "soundUrl": values["url"],
        }
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "post_client_command") as post, patch.object(
                        WINDOWS, "urlopen", return_value=self.response(accepted)):
            result = adapter.invoke("windows-lab", "sound.play", values)
        self.assertEqual({"requested": True, "commandId": "sound-windows"}, result)
        self.assertEqual("sound-channel", post.call_args.args[1]["action"])
        self.assertEqual(values["commandUrl"], post.call_args.args[1]["url"])

    def test_scene_reload_uses_http_control_without_relaunching(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "post_client_command") as post, patch.object(
                        adapter, "settle_controlled_scene") as settle, patch.object(
                            WINDOWS.subprocess, "Popen") as spawn:
            result = adapter.invoke("windows-lab", "scene.load", {
                "url": self.environment["OVERTE_E2E_SCENE_URL"],
            })
        self.assertEqual({"requested": True, "lifecycle": "same-process"}, result)
        self.assertEqual("scene-load", post.call_args.args[1]["action"])
        settle.assert_called_once()
        spawn.assert_not_called()

        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), self.assertRaisesRegex(
                    RuntimeError, "must match app.launch"):
            adapter.invoke("windows-lab", "scene.load", {
                "url": "http://127.0.0.1:41000/other-scene.json",
            })

    def test_probe_snapshot_waits_for_a_new_sample_sequence(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        old = {"sampleSequence": 41}
        fresh = {"sampleSequence": 42}
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    WINDOWS, "read_fresh_json", side_effect=[old, fresh]), patch.object(
                        WINDOWS.time, "sleep", return_value=None):
            self.assertIs(fresh, adapter.invoke(
                "windows-lab", "probe.snapshot", {"afterSampleSequence": 41}))

    def test_look_retries_until_probe_observes_the_requested_sign(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        before = {
            "sampleSequence": 10,
            "view": {"orientation": {"x": 0.0, "y": 0.0, "z": 0.0}},
        }
        unchanged = [
            {"sampleSequence": 11 + index,
             "view": {"orientation": {"x": 0.0, "y": 0.0, "z": 0.0}}}
            for index in range(10)
        ]
        changed = {
            "sampleSequence": 21,
            "view": {"orientation": {"x": 0.0, "y": -6.0, "z": 0.0}},
        }
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "visual_action") as visual, patch.object(
                        WINDOWS, "read_fresh_json",
                        side_effect=[before, *unchanged, changed]), patch.object(
                            WINDOWS.time, "sleep", return_value=None):
            self.assertEqual({"performed": True}, adapter.invoke(
                "windows-lab", "input.look", {
                    "horizontal": -0.25, "vertical": 0.0,
                }))
        self.assertEqual(2, visual.call_count)

    def test_vertical_input_and_stop_use_the_owned_process(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "visual_action") as visual:
            self.assertEqual({"performed": True}, adapter.invoke(
                "windows-lab", "input.jump", {}))
            self.assertEqual({"performed": True}, adapter.invoke(
                "windows-lab", "input.fly", {"durationSeconds": 2.0}))
        self.assertEqual("jump", visual.call_args_list[0].args[1])
        self.assertEqual("fly", visual.call_args_list[1].args[1])
        self.assertEqual(2.0, visual.call_args_list[1].args[2]["durationSeconds"])

        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "cleanup", return_value={"cleaned": True}) as cleanup:
            self.assertEqual({"stopped": True}, adapter.invoke(
                "windows-lab", "app.stop", {}))
        cleanup.assert_called_once_with("windows-lab")

    def test_tablet_operations_use_the_distinct_bounded_driver_actions(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                    adapter, "visual_action") as visual, patch.object(
                        WINDOWS, "read_fresh_json",
                        side_effect=[{"tablet": {"open": False}},
                                     {"tablet": {"open": True}}]):
            result = adapter.invoke("windows-lab", "tablet.open", {})
        self.assertEqual({"performed": True, "changed": True}, result)
        self.assertEqual("tablet-open", visual.call_args.args[1])

    def test_screenshot_requires_a_nonempty_window_scoped_artifact(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        screenshot = self.root / "artifacts" / "screenshot.png"

        def capture(_target: dict, action: str, _values: dict) -> None:
            self.assertEqual("screenshot", action)
            screenshot.write_bytes(b"mock-png")

        with patch.dict(os.environ, self.environment, clear=True), patch.object(
                adapter, "read_state", return_value=state), patch.object(
                    adapter, "state_alive", return_value=True), patch.object(
                        adapter, "visual_action", side_effect=capture):
            result = adapter.invoke("windows-lab", "artifact.screenshot", {})
        self.assertEqual({"artifact": "screenshot.png"}, result)
        self.assertEqual(0o600, screenshot.stat().st_mode & 0o777)

    def test_launch_uses_one_pinned_process_and_private_probe_copy(self) -> None:
        adapter = self.adapter()
        process = MagicMock(pid=4242)
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
                WINDOWS.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(WINDOWS.WindowsAdapter, "process_identity", return_value=(
                    "token", str(self.executable.resolve()))), patch.object(
                        adapter, "visual_action") as visual:
            self.assertEqual({"launched": True}, adapter.launch(
                "windows-lab", adapter.target("windows-lab")))
        command = spawn.call_args.args[0]
        self.assertEqual(str(self.executable.resolve()), command[0])
        self.assertEqual(1, command.count("--testScript"))
        self.assertEqual(1, command.count("--testResultsLocation"))
        self.assertEqual(1, command.count("--url"))
        script = Path(command[command.index("--testScript") + 1])
        self.assertNotEqual(DEVICE_ROOT / "probe/overte_e2e_probe.js", script)
        self.assertEqual(0o600, script.stat().st_mode & 0o777)
        with patch.dict(os.environ, self.environment, clear=True):
            state = json.loads(
                adapter.state_path("windows-lab").read_text(encoding="utf-8"))
        self.assertEqual(2, state["schemaVersion"])
        self.assertEqual(str(self.executable.resolve()), state["executablePath"])
        visual.assert_called_once_with(self.target, "focus", {"processId": 4242})

    def test_controlled_launch_requires_a_fixture_scene_origin(self) -> None:
        environment = dict(self.environment)
        environment.pop("OVERTE_E2E_SCENE_URL")
        with patch.dict(os.environ, environment, clear=True):
            adapter = WINDOWS.WindowsAdapter()
            with patch.object(WINDOWS.subprocess, "Popen") as spawn, \
                    self.assertRaisesRegex(RuntimeError, "require OVERTE_E2E_SCENE_URL"):
                adapter.launch("windows-lab", adapter.target("windows-lab"))
        spawn.assert_not_called()

    def test_harness_controlled_launch_arguments_are_rejected(self) -> None:
        self.target["arguments"] = ["--url=http://untrusted.invalid/"]
        self.write_config()
        adapter = self.adapter()
        with patch.object(WINDOWS.subprocess, "Popen") as spawn, self.assertRaisesRegex(
                RuntimeError, "harness-controlled"):
            adapter.launch("windows-lab", adapter.target("windows-lab"))
        spawn.assert_not_called()

    def test_cleanup_removes_the_private_probe_script(self) -> None:
        adapter = self.adapter()
        script = adapter.prepare_injected_probe("windows-lab")
        self.assertTrue(script.is_file())
        with patch.object(adapter, "read_state", return_value=None):
            self.assertEqual({"cleaned": True}, adapter.cleanup("windows-lab"))
        self.assertFalse(script.exists())

    def test_state_identity_includes_the_exact_executable(self) -> None:
        adapter = self.adapter()
        state = self.running_state()
        with patch.object(WINDOWS.WindowsAdapter, "process_identity", return_value=(
                "token", str(self.executable.resolve()))):
            self.assertTrue(adapter.state_alive(state))
        with patch.object(WINDOWS.WindowsAdapter, "process_identity", return_value=(
                "token", str(self.root / "other.exe"))):
            self.assertFalse(adapter.state_alive(state))

    def test_malformed_persisted_state_fails_closed(self) -> None:
        adapter = self.adapter()
        with patch.dict(os.environ, self.environment, clear=True):
            path = adapter.state_path("windows-lab")
            path.write_text(json.dumps({
                "schemaVersion": 2, "pid": 4242, "processToken": "token",
                "identity": "wrong", "executablePath": str(self.executable),
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "process state is invalid"):
                adapter.read_state("windows-lab")

    def test_driver_is_pid_scoped_bounded_and_recovers_held_input(self) -> None:
        source = (DEVICE_ROOT / "adapters/windows/overte.sikuli/overte.py").read_text(
            encoding="utf-8"
        )
        for expression in (
                "candidate.getPID() == expected_pid",
                "application.getPID() != expected_pid",
                'action in ("move", "jump", "fly", "settle")',
                'action in ("tablet-open", "tablet-close")',
                'if action == "release-input"',
                "captured = window.getScreen().capture(window)",
                "finally:\n        mouseUp(Button.RIGHT)",
                "finally:\n        keyUp(key)"):
            self.assertIn(expression, source)


if __name__ == "__main__":
    unittest.main()
