#!/usr/bin/env python3
"""Fail-closed checks for repeated real-cell execution."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stability_campaign", ROOT / "stability_campaign.py")
CAMPAIGN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CAMPAIGN)


class StabilityCampaignTest(unittest.TestCase):
    def test_campaign_owns_retries_output_and_one_explicit_suite(self):
        accepted = CAMPAIGN.checked_pipeline_arguments([
            "--", "--platform", "linux", "--suite", "portable-smoke"])
        self.assertEqual("--platform", accepted[0])
        for arguments, message in (
            (["--suite", "a", "--suite", "b"], "exactly one"),
            (["--minimum-state", "accepted"], "exactly one"),
            (["--suite", "a", "--retry-infrastructure", "2"], "campaign owns"),
            (["--suite", "a", "--output-dir=/tmp/x"], "campaign owns"),
        ):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                    ValueError, message):
                CAMPAIGN.checked_pipeline_arguments(arguments)

    def test_outcome_counts_only_real_runner_attempts(self):
        with tempfile.TemporaryDirectory(prefix="overte-stability-contract-") as name:
            root = Path(name)
            run = root / "portable-smoke/attempt-02"
            run.mkdir(parents=True)
            for attempt in (root / "portable-smoke/attempt-01", run):
                attempt.mkdir(parents=True, exist_ok=True)
                (attempt / "run-manifest.json").write_text("{}", encoding="utf-8")
                (attempt / "summary.json").write_text("{}", encoding="utf-8")
            (root / "pipeline-summary.json").write_text(json.dumps({
                "schemaVersion": 1,
                "outcomes": [{"classification": "passed", "attempt": 2,
                              "result": "portable-smoke/attempt-02"}],
            }), encoding="utf-8")
            classification, history, attempts = CAMPAIGN.pipeline_outcome(root)
            self.assertEqual("passed", classification)
            self.assertEqual(2, attempts)
            self.assertEqual(2, len(history))


if __name__ == "__main__":
    unittest.main()
