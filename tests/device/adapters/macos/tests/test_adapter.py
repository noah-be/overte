#!/usr/bin/env python3
"""Hardware-free contracts for the macOS desktop adapter."""

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
from unittest.mock import MagicMock, patch


DEVICE_ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = DEVICE_ROOT / "adapters/macos/adapter.py"
MANIFEST = DEVICE_ROOT / "adapters/macos/adapter.json"
VERIFIER = DEVICE_ROOT / "verify_adapter.py"
SPEC = importlib.util.spec_from_file_location("macos_adapter", ADAPTER_PATH)
MACOS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MACOS)


class MacOSAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="macos-adapter-test-")
        self.root = Path(self.temporary.name)
        self.jar = self.root / "oculix.jar"
        self.jar.write_bytes(b"pinned mock OculiX")
        self.executable = self.root / "Overte"
        self.executable.write_bytes(b"mock Interface")
        self.probe = self.root / "probe.json"
        self.probe.write_text("{}", encoding="utf-8")
        self.target = {
            "selector": "macos-lab",
            "displayName": "macOS Lab",
            "platform": "macos",
            "physical": False,
            "enabled": True,
            "executable": str(self.executable),
            "arguments": [],
            "workingDirectory": str(self.root),
            "windowTitle": "Overte",
            "oculixJar": str(self.jar),
            "oculixSha256": hashlib.sha256(self.jar.read_bytes()).hexdigest(),
            "javaExecutable": sys.executable,
            "javaArguments": [],
            "environment": {"OVERTE_MACOS_TEST": "1"},
            "probe": {"kind": "injected-test-script"},
            "clientControl": {"kind": "probe-command-file"},
        }
        self.config = self.root / "targets.json"
        self.write_config()
        self.environment = {
            **os.environ,
            "OVERTE_MACOS_TARGETS": str(self.config),
            "OVERTE_DEVICE_STATE_ROOT": str(self.root / "state"),
            "OVERTE_DEVICE_ARTIFACT_DIR": str(self.root / "artifacts"),
        }
        (self.root / "artifacts").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_config(self) -> None:
        self.config.write_text(
            json.dumps({"schemaVersion": 1, "targets": [self.target]}),
            encoding="utf-8",
        )

    def adapter(self) -> object:
        with patch.dict(os.environ, self.environment, clear=True):
            return MACOS.MacOSAdapter()

    @staticmethod
    def running_state() -> dict:
        return {"pid": 4242, "processToken": "token", "identity": "4242:token"}

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

    def test_configuration_is_macos_only_and_requires_pinned_oculix(self) -> None:
        self.target["platform"] = "not-macos"
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "non-macOS"):
            MACOS.MacOSAdapter()
        self.target["platform"] = "macos"
        self.target["oculixSha256"] = "0" * 63
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), self.assertRaisesRegex(
                RuntimeError, "64 hexadecimal"):
            MACOS.MacOSAdapter()

    def test_physical_target_rejects_a_non_macos_host(self) -> None:
        self.target["physical"] = True
        self.write_config()
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
                MACOS.sys, "platform", "not-darwin"), self.assertRaisesRegex(
                    RuntimeError, "require a macOS host"):
            MACOS.MacOSAdapter().discover()

    def test_capabilities_and_description_are_target_specific(self) -> None:
        adapter = self.adapter()
        discovered = adapter.discover()
        self.assertEqual("macos", discovered[0]["platform"])
        self.assertEqual("macos-desktop", adapter.describe("macos-lab")["adapter"])
        self.assertTrue({"navigation.enter-domain", "asset.load", "sound.play"}.issubset(
            discovered[0]["capabilities"]
        ))

    def test_oculix_is_hash_pinned_pid_scoped_and_environment_bounded(self) -> None:
        adapter = self.adapter()
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(MACOS.subprocess, "run", return_value=completed) as run:
            adapter.oculix(self.target, "focus", {"processId": 4242})
        arguments = run.call_args.args[0]
        self.assertEqual(str(Path(sys.executable).resolve()), arguments[0])
        self.assertIn(str(self.jar), arguments)
        self.assertIn(str(DEVICE_ROOT / "adapters/macos/overte.sikuli"), arguments)
        payload = json.loads(arguments[-1])
        self.assertEqual(4242, payload["processId"])
        self.assertEqual("Overte", payload["windowTitle"])
        self.assertNotIn("HIFI_ALLOW_MULTIPLE_INSTANCES", run.call_args.kwargs["env"])

    def test_process_token_ignores_scheduler_state_and_rejects_zombies(self) -> None:
        responses = [
            subprocess.CompletedProcess([], 0, "R Tue Aug 25 10:00:00 2026\n", ""),
            subprocess.CompletedProcess([], 0, "S Tue Aug 25 10:00:00 2026\n", ""),
            subprocess.CompletedProcess([], 0, "Z Tue Aug 25 10:00:00 2026\n", ""),
            subprocess.CompletedProcess([], 0, "S Tue Aug 25 10:00:01 2026\n", ""),
        ]
        with patch.object(MACOS.subprocess, "run", side_effect=responses):
            first = MACOS.MacOSAdapter.process_token(42)
            second = MACOS.MacOSAdapter.process_token(42)
            zombie = MACOS.MacOSAdapter.process_token(42)
            reused = MACOS.MacOSAdapter.process_token(42)
        self.assertEqual(first, second)
        self.assertIsNone(zombie)
        self.assertNotEqual(first, reused)

    def test_control_commands_reuse_the_authoritative_process(self) -> None:
        adapter = self.adapter()
        adapter.prepare_injected_probe("macos-lab")
        state = self.running_state()
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                MACOS.subprocess, "Popen") as spawn:
            result = adapter.invoke("macos-lab", "navigation.enter-domain", {
                "url": "hifi://127.0.0.1:40102/",
            })
        self.assertEqual({"requested": True}, result)
        spawn.assert_not_called()
        command = json.loads(adapter.client_command_path("macos-lab").read_text())
        self.assertEqual("navigate", command["action"])
        self.assertEqual("hifi://127.0.0.1:40102/", command["url"])

    def test_sound_requires_exact_fixture_acknowledgement(self) -> None:
        adapter = self.adapter()
        adapter.prepare_injected_probe("macos-lab")
        state = self.running_state()
        values = {
            "schemaVersion": 1,
            "commandId": "sound-macos",
            "url": "http://127.0.0.1:41000/audio/tone.wav",
            "commandUrl": "http://127.0.0.1:41000/sound-command.json",
        }
        accepted = {
            "schemaVersion": 1,
            "commandId": "sound-macos",
            "action": "play",
            "soundUrl": values["url"],
        }
        response = MagicMock(status=200)
        response.read.return_value = json.dumps(accepted).encode("utf-8")
        response.__enter__.return_value = response
        with patch.object(adapter, "read_state", return_value=state), patch.object(
                adapter, "state_alive", return_value=True), patch.object(
                MACOS, "urlopen", return_value=response):
            result = adapter.invoke("macos-lab", "sound.play", values)
        self.assertEqual({"requested": True, "commandId": "sound-macos"}, result)
        command = json.loads(adapter.client_command_path("macos-lab").read_text())
        self.assertEqual("sound-channel", command["action"])

    def test_driver_resolves_only_the_launched_process_window(self) -> None:
        source = (DEVICE_ROOT / "adapters/macos/overte.sikuli/overte.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("candidate.getPID() == expected_pid", source)
        self.assertIn("application.getPID() != expected_pid", source)
        self.assertIn("captured = window.getScreen().capture(window)", source)
        self.assertIn("finally:\n        mouseUp(Button.RIGHT)", source)
        self.assertIn("finally:\n        keyUp(key)", source)


if __name__ == "__main__":
    unittest.main()
