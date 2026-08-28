#!/usr/bin/env python3
"""Contract and device-free scenario tests for vertical locomotion."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from contracts import (load_capability_registry, validate_operation_arguments,
                       validate_performed_result, validate_probe_snapshot)


def snapshot(**avatar_overrides: object) -> dict:
    avatar = {
        "position": {"x": 0.0, "y": 1.0, "z": 4.0},
        "inAir": False,
        "flying": False,
        "flyingEnabled": True,
    }
    avatar.update(avatar_overrides)
    return {
        "schemaVersion": 1,
        "sampleEpochMs": 1,
        "build": {"platform": "Mock", "version": "1", "date": "1970-01-01"},
        "application": {"running": True},
        "scene": {"ready": True, "entityCount": 4},
        "avatar": avatar,
        "view": {"orientation": {"x": 0.0, "y": 0.0, "z": 0.0}},
        "tablet": {"open": False},
    }


def tracking_mock_manifest(root: Path) -> tuple[Path, Path]:
    """Wrap the mock adapter to attest the app identity seen by each module."""
    evidence = root / "process-evidence.jsonl"
    adapter = root / "tracking-adapter.py"
    delegate = DEVICE_ROOT / "adapters/mock/adapter.py"
    adapter.write_text(
        f'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys

delegate = {str(delegate)!r}
result = subprocess.run(
    [sys.executable, delegate, *sys.argv[1:]], text=True,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
if result.returncode == 0 and sys.argv[1] == "invoke":
    operation = sys.argv[sys.argv.index("--operation") + 1]
    artifact = os.environ.get("OVERTE_DEVICE_ARTIFACT_DIR")
    if operation == "probe.snapshot" and artifact:
        target = sys.argv[sys.argv.index("--target") + 1]
        process = subprocess.run([
            sys.executable, delegate, "invoke", "--target", target,
            "--operation", "app.process", "--arguments", "{{}}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if process.returncode != 0:
            print(process.stderr, end="", file=sys.stderr)
            raise SystemExit(process.returncode)
        with Path(os.environ["OVERTE_MOCK_PROCESS_EVIDENCE"]).open(
                "a", encoding="utf-8") as stream:
            stream.write(json.dumps({{
                "module": Path(artifact).name,
                "identity": json.loads(process.stdout)["identity"],
            }}) + "\\n")
print(result.stdout, end="")
print(result.stderr, end="", file=sys.stderr)
raise SystemExit(result.returncode)
''',
        encoding="utf-8",
    )
    adapter.chmod(0o700)
    manifest = root / "tracking-adapter.json"
    manifest.write_text(json.dumps({
        "schemaVersion": 1,
        "id": "tracking-mock",
        "command": [adapter.name],
    }), encoding="utf-8")
    return manifest, evidence


class VerticalLocomotionTest(unittest.TestCase):
    def test_vertical_suite_catalog_selection_is_exact_and_ordered(self):
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--suite", "vertical-locomotion", "--list",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(
            ["launch-smoke", "jump", "fly"],
            [line.split(":", 1)[0] for line in result.stdout.splitlines()],
        )

    def test_capabilities_are_registered(self):
        registry = load_capability_registry()
        self.assertEqual("input.jump", registry["input.jump"]["operation"])
        self.assertEqual("input.fly", registry["input.fly"]["operation"])

    def test_operation_argument_and_result_contracts(self):
        self.assertEqual({}, validate_operation_arguments("input.jump", {}))
        self.assertEqual(
            {"durationSeconds": 2.0},
            validate_operation_arguments("input.fly", {"durationSeconds": 2.0}),
        )
        self.assertEqual(
            {"performed": True},
            validate_performed_result("input.jump", {"performed": True}),
        )
        for operation, arguments in (
                ("input.jump", {"button": "A"}),
                ("input.fly", {}),
                ("input.fly", {"durationSeconds": 0}),
                ("input.fly", {"durationSeconds": 11}),
                ("input.fly", {"durationSeconds": True})):
            with self.subTest(operation=operation, arguments=arguments):
                with self.assertRaises(ValueError):
                    validate_operation_arguments(operation, arguments)
        with self.assertRaises(ValueError):
            validate_performed_result("input.fly", {"performed": False})

    def test_pico_fly_gesture_is_self_contained_and_covers_delayed_probe(self):
        source = (DEVICE_ROOT / "overte_session.py").read_text(encoding="utf-8")
        self.assertIn("if self.pico_openxr:", source)
        self.assertNotIn('operation("input.jump", takeoff)', source)
        self.assertIn("duration_seconds = 6.0", source)

    def test_probe_requires_vertical_state_and_rejects_inconsistent_avatar(self):
        self.assertEqual(snapshot(), validate_probe_snapshot(snapshot()))
        for invalid in (
                snapshot(inAir=None),
                snapshot(flying=None),
                snapshot(flyingEnabled=None),
                snapshot(inAir=False, flying=True)):
            with self.subTest(avatar=invalid["avatar"]):
                with self.assertRaises(ValueError):
                    validate_probe_snapshot(invalid)

    def test_complete_vertical_suite_reuses_one_app_session_and_cleans_up(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-vertical-") as temporary:
            root = Path(temporary)
            output = root / "results"
            manifest, process_evidence = tracking_mock_manifest(root)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_MOCK_PROCESS_EVIDENCE": str(process_evidence),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
            })
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(manifest),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "vertical-locomotion", "--allow-virtual", "--require-complete",
                "--output-dir", str(output),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", summary["status"])
            self.assertEqual(
                ["launch-smoke", "jump", "fly"],
                [item["id"] for item in summary["results"]],
            )
            self.assertTrue(all(item["status"] == "passed"
                                for item in summary["results"]))
            launch_metrics = json.loads(
                (output / "modules/launch-smoke/metrics.json").read_text(encoding="utf-8"))
            self.assertEqual("mock-e2e-process", launch_metrics["processIdentity"])
            identities_by_module: dict[str, set[str]] = {}
            for line in process_evidence.read_text(encoding="utf-8").splitlines():
                observed = json.loads(line)
                identities_by_module.setdefault(observed["module"], set()).add(
                    observed["identity"])
            self.assertEqual(
                {launch_metrics["processIdentity"]}, identities_by_module["jump"])
            self.assertEqual(
                {launch_metrics["processIdentity"]}, identities_by_module["fly"])
            jump_airborne = json.loads(
                (output / "modules/jump/jump-airborne.json").read_text(encoding="utf-8"))
            jump_landed = json.loads(
                (output / "modules/jump/jump-landed.json").read_text(encoding="utf-8"))
            fly_active = json.loads(
                (output / "modules/fly/fly-active.json").read_text(encoding="utf-8"))
            self.assertTrue(jump_airborne["avatar"]["inAir"])
            self.assertFalse(jump_airborne["avatar"]["flying"])
            self.assertFalse(jump_landed["avatar"]["inAir"])
            self.assertTrue(fly_active["avatar"]["inAir"])
            self.assertTrue(fly_active["avatar"]["flying"])
            self.assertTrue(jump_airborne["application"]["running"])
            self.assertTrue(fly_active["application"]["running"])

            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(1, state["sceneLoadCount"])
            self.assertFalse(state["running"])
            self.assertFalse(state["foreground"])

            junit = ET.parse(output / "junit.xml").getroot()
            self.assertEqual("3", junit.attrib["tests"])
            self.assertEqual("0", junit.attrib["failures"])
            self.assertEqual("0", junit.attrib["errors"])
            private_selector = b"mock-e2e-target"
            self.assertNotIn(private_selector, result.stdout.encode("utf-8"))
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(private_selector, artifact.read_bytes(), str(artifact))

    def test_adapter_without_vertical_capabilities_skips_or_fails_complete(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-no-vertical-") as temporary:
            root = Path(temporary)
            adapter = root / "adapter.py"
            adapter.write_text(
                "#!/usr/bin/env python3\n"
                "import json,sys\n"
                "if sys.argv[1] == 'discover':\n"
                " print(json.dumps([{'selector':'mock','displayName':'Mock','platform':'mock','physical':False,'capabilities':['probe.snapshot','scene.load']}]))\n"
                "elif sys.argv[1] == 'describe': print('{}')\n"
                "else: print(json.dumps({'cleaned': True}))\n",
                encoding="utf-8")
            adapter.chmod(0o700)
            manifest = root / "adapter.json"
            manifest.write_text(json.dumps({
                "schemaVersion": 1, "id": "no-vertical", "command": ["adapter.py"]}),
                encoding="utf-8")
            base = [
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(manifest), "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "vertical-locomotion", "--allow-virtual",
            ]
            skipped = subprocess.run(
                [*base, "--output-dir", str(root / "skip")], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            complete = subprocess.run(
                [*base, "--require-complete", "--output-dir", str(root / "complete")],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, skipped.returncode, skipped.stdout)
            skipped_results = json.loads(
                (root / "skip/summary.json").read_text(encoding="utf-8"))["results"]
            self.assertEqual(
                ["launch-smoke", "jump", "fly"],
                [item["id"] for item in skipped_results],
            )
            self.assertEqual(["skipped"] * 3,
                             [item["status"] for item in skipped_results])
            self.assertEqual(1, complete.returncode, complete.stdout)
            complete_results = json.loads(
                (root / "complete/summary.json").read_text(encoding="utf-8"))["results"]
            self.assertEqual(
                ["launch-smoke", "jump", "fly"],
                [item["id"] for item in complete_results],
            )
            self.assertEqual(["error"] * 3,
                             [item["status"] for item in complete_results])

    def test_jump_and_fly_reject_missing_height_gain(self):
        with tempfile.TemporaryDirectory(prefix="overte-e2e-bad-vertical-") as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment.update({
                "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
                "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
                "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                "OVERTE_E2E_POLL_SECONDS": "0.05",
                "OVERTE_E2E_TIMEOUT_SECONDS": "1",
                "OVERTE_MOCK_E2E_BAD_JUMP": "1",
                "OVERTE_MOCK_E2E_BAD_FLY": "1",
            })
            result = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "run.py"),
                "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
                "--catalog", str(DEVICE_ROOT / "catalog.json"),
                "--suite", "vertical-locomotion", "--allow-virtual", "--require-complete",
                "--output-dir", str(root / "results"),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               env=environment, check=False)
            self.assertEqual(1, result.returncode, result.stdout)
            summary = json.loads(
                (root / "results/summary.json").read_text(encoding="utf-8"))
            self.assertEqual(["passed", "failed", "failed"],
                             [item["status"] for item in summary["results"]])


if __name__ == "__main__":
    unittest.main()
