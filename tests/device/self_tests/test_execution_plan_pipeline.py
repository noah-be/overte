#!/usr/bin/env python3
"""Fail-closed proofs for planning, owned fixtures, signals and evidence integrity."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE_ROOT))

from acceptance_policy import load_policy
from execution_plan import compile_plan, load_profiles, select_suites
from pipeline import start_fixture, stop_process


class ExecutionPlanPipelineTest(unittest.TestCase):
    def environment(self, root: Path, settle: str = "0") -> dict[str, str]:
        environment = os.environ.copy()
        for name in list(environment):
            if name.startswith("OVERTE_E2E_SCENE_") or name.startswith("OVERTE_E2E_DOMAIN_"):
                environment.pop(name)
        environment.update({
            "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": settle,
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_TIMEOUT_SECONDS": "2",
        })
        return environment

    def pipeline_command(self, output: Path, suite: str = "e2e-core",
                         manifest: Path | None = None, profiles: Path | None = None) -> list[str]:
        return [
            sys.executable, str(DEVICE_ROOT / "pipeline.py"),
            "--adapter-manifest", str(manifest or DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--policy", str(DEVICE_ROOT / "acceptance-policy.json"),
            "--profiles", str(profiles or DEVICE_ROOT / "execution-profiles.json"),
            "--platform", "mock", "--suite", suite, "--allow-virtual",
            "--output-dir", str(output),
        ]

    def test_profiles_cover_catalog_and_plan_merges_fixture_requirements(self):
        catalog = DEVICE_ROOT / "catalog.json"
        profiles = load_profiles(DEVICE_ROOT / "execution-profiles.json", catalog)
        policy = load_policy(DEVICE_ROOT / "acceptance-policy.json", catalog)
        plan = compile_plan(
            policy, catalog, profiles, "mock",
            ["smoke", "e2e-core", "domain-smoke"], set(), False, set(), "auto",
            {"assignment-client", "domain-server"})
        self.assertTrue(plan["ready"])
        self.assertEqual("domain", plan["fixture"])
        self.assertEqual(["smoke", "e2e-core", "domain-smoke"],
                         [item["suite"] for item in plan["suites"]])
        capabilities = plan["suites"][1]["capabilities"]
        self.assertEqual(capabilities, sorted(set(capabilities)))

    def test_upgrade_plan_rejects_missing_versions_and_artifacts(self):
        catalog = DEVICE_ROOT / "catalog.json"
        plan = compile_plan(
            load_policy(DEVICE_ROOT / "acceptance-policy.json", catalog), catalog,
            load_profiles(DEVICE_ROOT / "execution-profiles.json", catalog),
            "mock", ["update-upgrade"], set(), False, set(), "none")
        self.assertFalse(plan["ready"])
        self.assertEqual([
            "OVERTE_E2E_UPGRADE_FROM_VERSION", "OVERTE_E2E_UPGRADE_TO_VERSION",
            "artifact:candidate", "artifact:source",
        ], plan["missingInputs"])

    def test_policy_lifecycle_can_select_required_suites(self):
        catalog = DEVICE_ROOT / "catalog.json"
        profiles = load_profiles(DEVICE_ROOT / "execution-profiles.json", catalog)
        policy = load_policy(DEVICE_ROOT / "acceptance-policy.json", catalog)
        policy["platforms"]["mock"]["suites"]["smoke"] = {
            "state": "required", "evidence": ["self-test-1", "self-test-2", "self-test-3"]}
        self.assertEqual(["smoke"], select_suites(
            policy, profiles, "mock", None, "required"))
        with self.assertRaisesRegex(ValueError, "no suites"):
            select_suites(load_policy(
                DEVICE_ROOT / "acceptance-policy.json", catalog),
                profiles, "mock", None, "required")

    def test_required_promotion_needs_three_registered_successful_runs(self):
        catalog = DEVICE_ROOT / "catalog.json"
        with tempfile.TemporaryDirectory(prefix="overte-promotion-policy-") as temporary:
            root = Path(temporary)
            policy = json.loads(
                (DEVICE_ROOT / "acceptance-policy.json").read_text(encoding="utf-8"))
            policy["platforms"]["linux"]["suites"]["domain-smoke"]["state"] = "required"
            policy_path = root / "acceptance-policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            (root / "acceptance-evidence.json").write_text(
                (DEVICE_ROOT / "acceptance-evidence.json").read_text(encoding="utf-8"),
                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "needs 3 successful real runs"):
                load_policy(policy_path, catalog)

    def test_invalid_recipe_fails_before_adapter_discovery(self):
        with tempfile.TemporaryDirectory(prefix="overte-plan-preflight-") as temporary:
            root = Path(temporary)
            marker = root / "adapter-contacted"
            adapter = root / "adapter.py"
            adapter.write_text(
                "#!/usr/bin/env python3\nfrom pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('contacted')\n",
                encoding="utf-8")
            adapter.chmod(0o700)
            manifest = root / "adapter.json"
            manifest.write_text(json.dumps({
                "schemaVersion": 1, "id": "preflight", "command": ["adapter.py"]}),
                encoding="utf-8")
            profile = json.loads(
                (DEVICE_ROOT / "execution-profiles.json").read_text(encoding="utf-8"))
            profile["suites"].pop("smoke")
            invalid = root / "profiles.json"
            invalid.write_text(json.dumps(profile, sort_keys=True), encoding="utf-8")
            result = subprocess.run(
                self.pipeline_command(root / "output", "smoke", manifest, invalid),
                env=self.environment(root), text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertFalse(marker.exists())
            self.assertFalse((root / "output").exists())

    def test_owned_scene_fixture_is_stopped_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="overte-owned-fixture-") as temporary:
            root = Path(temporary)
            output = root / "output"
            result = subprocess.run(
                self.pipeline_command(output), env=self.environment(root), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            plan = json.loads((output / "execution-plan.json").read_text(encoding="utf-8"))
            self.assertEqual("scene", plan["fixture"])
            self.assertNotIn("127.0.0.1", json.dumps(plan))
            events = [json.loads(line) for line in
                      (output / "pipeline-timeline.jsonl").read_text().splitlines()]
            fixture_states = [item["status"] for item in events
                              if item["phase"] == "fixtures"]
            self.assertEqual(["starting", "ready", "stopping"], fixture_states)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertFalse(state["running"])
            parsed = urlsplit(state["sceneUrl"])
            with self.assertRaises((OSError, URLError)):
                urlopen(f"{parsed.scheme}://{parsed.netloc}/healthz", timeout=0.5)

            run = output / "e2e-core/attempt-01"
            summary = run / "summary.json"
            summary.write_text(summary.read_text(encoding="utf-8") + " ", encoding="utf-8")
            matrix = subprocess.run([
                sys.executable, str(DEVICE_ROOT / "evaluate_matrix.py"),
                "--result", str(run), "--require", "mock:e2e-core",
                "--allow-virtual-platform", "mock", "--output-dir", str(root / "matrix"),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(2, matrix.returncode)
            self.assertIn("integrity", matrix.stdout)

    def test_early_runner_failure_is_retried_as_infrastructure(self):
        with tempfile.TemporaryDirectory(prefix="overte-early-runner-") as temporary:
            root = Path(temporary)
            manifest = root / "bad-adapter.json"
            manifest.write_text('{"schemaVersion":99}\n', encoding="utf-8")
            output = root / "output"
            result = subprocess.run(
                self.pipeline_command(output, "smoke", manifest)
                + ["--retry-infrastructure", "2"],
                env=self.environment(root), text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            self.assertEqual(2, result.returncode, result.stdout)
            for attempt in range(1, 4):
                self.assertTrue((output / f"smoke/attempt-{attempt:02d}/pipeline-driver.json")
                                .is_file())

    def test_domain_fixture_preflight_failure_is_reported_without_device_access(self):
        with tempfile.TemporaryDirectory(prefix="overte-domain-preflight-") as temporary:
            root = Path(temporary)
            output = root / "output"
            result = subprocess.run(
                self.pipeline_command(output, "domain-smoke"),
                env=self.environment(root), text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertFalse((root / "state.json").exists())
            self.assertFalse(output.exists())
            self.assertIn("executable:assignment-client", result.stdout)

    def test_signal_stops_runner_application_and_owned_fixture(self):
        with tempfile.TemporaryDirectory(prefix="overte-signal-cleanup-") as temporary:
            root = Path(temporary)
            output = root / "output"
            process = subprocess.Popen(
                self.pipeline_command(output), env=self.environment(root), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            state_path = root / "state.json"
            scene_url = ""
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and process.poll() is None:
                if state_path.is_file():
                    try:
                        scene_url = json.loads(
                            state_path.read_text(encoding="utf-8")).get("sceneUrl", "")
                    except json.JSONDecodeError:
                        pass
                if scene_url:
                    break
                time.sleep(0.05)
            self.assertTrue(scene_url, "pipeline did not reach the controlled scene")
            os.kill(process.pid, signal.SIGTERM)
            stdout, _ = process.communicate(timeout=30)
            self.assertEqual(2, process.returncode, stdout)
            summary = json.loads(
                (output / "pipeline-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("infrastructure-error",
                             summary["outcomes"][-1]["classification"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertFalse(state["running"])
            events = [json.loads(line) for line in
                      (output / "pipeline-timeline.jsonl").read_text().splitlines()]
            self.assertEqual("interrupted", events[-1]["status"])
            parsed = urlsplit(scene_url)
            with self.assertRaises((OSError, URLError)):
                urlopen(f"{parsed.scheme}://{parsed.netloc}/healthz", timeout=0.5)

    @unittest.skipUnless(Path("/proc/self/task").is_dir(), "requires Linux process children")
    def test_fixture_child_abort_is_detected_and_server_is_closed(self):
        with tempfile.TemporaryDirectory(prefix="overte-fixture-abort-") as temporary:
            root = Path(temporary)
            args = SimpleNamespace(
                fixture_bind="127.0.0.1", fixture_port=0, public_host=None,
                domain_server=None, assignment_client=None,
                domain_port=40102, domain_http_port=40100)
            process, environment = start_fixture(args, "scene", root)
            parsed = urlsplit(environment["OVERTE_E2E_SCENE_URL"])
            health = f"{parsed.scheme}://{parsed.netloc}/healthz"
            self.assertEqual(200, urlopen(health, timeout=1).status)
            children = Path(
                f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()
            self.assertEqual(1, len(children))
            os.kill(int(children[0]), signal.SIGTERM)
            process.wait(timeout=10)
            self.assertNotEqual(0, process.returncode)
            stop_process(process)
            stop_process(process)
            with self.assertRaises((OSError, URLError)):
                urlopen(health, timeout=0.5)


if __name__ == "__main__":
    unittest.main()
