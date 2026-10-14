#!/usr/bin/env python3
"""Evaluate the actual iOS platform workflow guards without dispatching jobs."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "noah-l-frank/overte"
JOBS = {
    "ios-bootstrap.yml": ("prerelease-build",),
    "ios-pre-release-check.yml": ("configuration", "inspect"),
    "ios-release-build.yml": (
        "gate-contracts", "provision-qt", "production-after-qt",
        "production-from-checkpoints",
    ),
}


def selected(expression, **context):
    """Support exactly the comparison/conjunction grammar used by these jobs."""
    results = []
    for clause in expression.split(" && "):
        match = re.fullmatch(
            r"(github\.(?:repository|event_name)|inputs\.(?:prerelease_build|qt_host_cache_key))"
            r"(?: (==|!=) '([^']*)')?", clause,
        )
        if not match:
            raise AssertionError(f"unreviewed job condition: {clause}")
        field, operator, expected = match.groups()
        value = context[field]
        results.append(bool(value) if operator is None else
                       value == expected if operator == "==" else value != expected)
    return all(results)


class RepositoryGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            name: yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
            for name in JOBS
        }

    def conditions(self):
        for workflow, jobs in JOBS.items():
            for job in jobs:
                yield workflow, job, self.workflows[workflow]["jobs"][job]["if"]

    def context(self, repository=REPOSITORY, event="workflow_dispatch", enabled=True, cache=""):
        return {"github.repository": repository, "github.event_name": event,
                "inputs.prerelease_build": enabled, "inputs.qt_host_cache_key": cache}

    def test_all_seven_guards_accept_only_current_fork(self):
        self.assertEqual(7, sum(len(jobs) for jobs in JOBS.values()))
        for workflow, job, expression in self.conditions():
            cache = "reviewed-checkpoint" if job == "production-from-checkpoints" else ""
            with self.subTest(workflow=workflow, job=job):
                self.assertTrue(selected(expression, **self.context(cache=cache)))
                for foreign in ("noah-be/overte", "overte-org/overte", "other/overte",
                                "noah-l-frank/other", "NOAH-L-FRANK/overte"):
                    self.assertFalse(selected(expression, **self.context(foreign, cache=cache)))

    def test_prerelease_still_requires_dispatch_opt_in_and_host_gate(self):
        job = self.workflows["ios-bootstrap.yml"]["jobs"]["prerelease-build"]
        self.assertEqual("host-contracts", job["needs"])
        for event in ("push", "pull_request", "workflow_call"):
            self.assertFalse(selected(job["if"], **self.context(event=event)))
        self.assertFalse(selected(job["if"], **self.context(enabled=False)))

    def test_production_checkpoint_routes_remain_exclusive_and_unsigned(self):
        jobs = self.workflows["ios-release-build.yml"]["jobs"]
        for cache in ("", "reviewed-checkpoint"):
            choices = [selected(jobs[job]["if"], **self.context(cache=cache))
                       for job in ("production-after-qt", "production-from-checkpoints")]
            self.assertEqual([not bool(cache), bool(cache)], choices)
        self.assertEqual("gate-contracts", jobs["provision-qt"]["needs"])
        self.assertEqual("provision-qt", jobs["production-after-qt"]["needs"])
        self.assertEqual("gate-contracts", jobs["production-from-checkpoints"]["needs"])
        for name in ("production-after-qt", "production-from-checkpoints"):
            self.assertIs(False, jobs[name]["with"]["e2e_test_build"])

    def test_private_inspection_remains_separate_and_read_only(self):
        workflow = self.workflows["ios-pre-release-check.yml"]
        self.assertEqual({"contents": "read"}, workflow["permissions"])
        self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
        self.assertEqual("configuration", workflow["jobs"]["inspect"]["needs"])
        self.assertEqual("self-hosted", workflow["jobs"]["inspect"]["runs-on"][0])
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                self.assertFalse(step.get("uses", "").startswith("actions/upload-artifact@"))


if __name__ == "__main__":
    unittest.main()
