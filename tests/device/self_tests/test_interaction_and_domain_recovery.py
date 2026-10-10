#!/usr/bin/env python3
"""Device-free proofs for world interaction and domain roundtrip scenarios."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class InteractionAndDomainRecoveryTest(unittest.TestCase):
    def run_suite(self, suite: str, environment: dict[str, str], module_ids=None):
        temporary = tempfile.TemporaryDirectory(prefix=f"overte-{suite}-")
        root = Path(temporary.name)
        output = root / "results"
        env = os.environ.copy()
        env.update({
            "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            **environment,
        })
        catalog = DEVICE_ROOT / "catalog.json"
        if module_ids is not None:
            document = json.loads(catalog.read_text())
            lookup = {m["id"]: m for m in document["modules"]}
            document["modules"] = [lookup[identifier] for identifier in module_ids]
            for module in document["modules"]:
                module["command"][0] = str(DEVICE_ROOT / module["command"][0])
            catalog = root / "regression-first-catalog.json"
            catalog.write_text(json.dumps(document))
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(catalog),
            "--suite", suite, "--allow-virtual", "--require-complete",
            "--output-dir", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=env, check=False)
        return temporary, root, output, result

    def test_crash_recovery_rebinds_a_process_local_probe_sequence(self):
        temporary, root, output, result = self.run_suite("crash-recovery-under-load", {
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
        })
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            state = json.loads((root / "state.json").read_text())
            self.assertEqual(2, state["launchCount"])
            receipt = json.loads((output / "modules/crash-recovery-under-load/crash-recovery.json").read_text())
            self.assertTrue(receipt["processChanged"])
            self.assertTrue(receipt["sceneReady"])
        finally:
            temporary.cleanup()

    def test_world_interaction_observes_one_fresh_entity_press(self):
        temporary, root, output, result = self.run_suite("interaction-smoke", {
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
        })
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["launch-smoke", "scene", "world-interaction"],
                [item["id"] for item in summary["results"]],
            )
            before = json.loads((output / "modules/world-interaction/interaction-before.json")
                                .read_text(encoding="utf-8"))
            after = json.loads((output / "modules/world-interaction/interaction-after.json")
                               .read_text(encoding="utf-8"))
            self.assertEqual(before["interaction"]["pressCount"] + 1,
                             after["interaction"]["pressCount"])
            self.assertEqual("OVERTE_E2E_INTERACTABLE",
                             after["interaction"]["lastEntityName"])
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(1, state["interactionCount"])
        finally:
            temporary.cleanup()

    def test_world_interaction_rejects_missing_and_duplicate_effects(self):
        for failure in ("primary-interaction-missing", "primary-interaction-duplicate"):
            with self.subTest(failure=failure):
                temporary, _root, output, result = self.run_suite("interaction-smoke", {
                    "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
                    "OVERTE_E2E_TIMEOUT_SECONDS": "1",
                    "OVERTE_MOCK_E2E_FAILURES": failure,
                })
                try:
                    self.assertEqual(1, result.returncode, result.stdout)
                    summary = json.loads((output / "summary.json").read_text(
                        encoding="utf-8"))
                    interaction = next(item for item in summary["results"]
                                       if item["id"] == "world-interaction")
                    self.assertEqual("failed", interaction["status"])
                finally:
                    temporary.cleanup()

    def test_domain_roundtrip_preserves_process_and_reconnects_content(self):
        manifest = json.loads(
            (DEVICE_ROOT / "fixture/domain-manifest.json").read_text(encoding="utf-8"))
        domain_id = "11111111-2222-4333-8444-555555555555"
        temporary, root, output, result = self.run_suite("domain-recovery", {
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
            "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
            "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
            "OVERTE_E2E_DOMAIN_ID": domain_id,
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(manifest["requiredMarkers"]),
            "OVERTE_MOCK_E2E_DOMAIN_ID": domain_id,
        })
        try:
            self.assertEqual(0, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["launch-smoke", "domain-enter", "domain-roundtrip"],
                [item["id"] for item in summary["results"]],
            )
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(1, state["launchCount"])
            self.assertEqual(2, state["domainEnterCount"])
            self.assertEqual(1, state["sceneLoadCount"])
            evidence = json.loads((output / "modules/domain-roundtrip/domain-roundtrip.json")
                                  .read_text(encoding="utf-8"))
            self.assertTrue(evidence["processStable"])
            self.assertTrue(evidence["serverlessObserved"])
            self.assertGreaterEqual(evidence["stableReconnectSamples"], 3)
        finally:
            temporary.cleanup()

    def test_roundtrip_can_run_before_the_previously_passed_domain_enter(self):
        manifest = json.loads((DEVICE_ROOT / "fixture/domain-manifest.json").read_text())
        domain_id = "11111111-2222-4333-8444-555555555555"
        temporary, root, output, result = self.run_suite("domain-recovery", {
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
            "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40282/0,2,4/0,0,0,1",
            "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
            "OVERTE_E2E_DOMAIN_ID": domain_id,
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(manifest["requiredMarkers"]),
            "OVERTE_MOCK_E2E_DOMAIN_ID": domain_id,
        }, ["launch-smoke", "domain-roundtrip", "domain-enter"])
        try:
            self.assertEqual(0,result.returncode,result.stdout)
            summary=json.loads((output / "summary.json").read_text())
            self.assertEqual(["launch-smoke","domain-roundtrip","domain-enter"],
                             [m["id"] for m in summary["results"]])
            proof=json.loads((output / "modules/domain-roundtrip/domain-roundtrip.json").read_text())
            self.assertTrue(proof["processStable"] and proof["serverlessObserved"])
            self.assertEqual(domain_id,proof["domainId"])
            self.assertEqual(1,json.loads((root / "state.json").read_text())["launchCount"])
        finally:
            temporary.cleanup()

    def test_domain_roundtrip_rejects_process_restart_during_reentry(self):
        manifest = json.loads(
            (DEVICE_ROOT / "fixture/domain-manifest.json").read_text(encoding="utf-8"))
        domain_id = "11111111-2222-4333-8444-555555555555"
        temporary, _root, output, result = self.run_suite("domain-recovery", {
            "OVERTE_E2E_SCENE_URL": "http://fixture.invalid/scene.json",
            "OVERTE_E2E_DOMAIN_URL": "hifi://127.0.0.1:40102/0,2,4/0,0,0,1",
            "OVERTE_E2E_DOMAIN_HOST": "127.0.0.1",
            "OVERTE_E2E_DOMAIN_ID": domain_id,
            "OVERTE_E2E_DOMAIN_MARKERS_JSON": json.dumps(manifest["requiredMarkers"]),
            "OVERTE_MOCK_E2E_DOMAIN_ID": domain_id,
            "OVERTE_MOCK_E2E_FAILURES": "domain-reentry-process-restart",
        })
        try:
            self.assertEqual(1, result.returncode, result.stdout)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            roundtrip = next(item for item in summary["results"]
                             if item["id"] == "domain-roundtrip")
            self.assertEqual("failed", roundtrip["status"])
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
