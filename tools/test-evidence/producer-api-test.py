#!/usr/bin/env python3
"""Adversarial fake-API tests; no live requests, builds, installs or dispatch."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import producer_api as A
import producer as P


SPEC = importlib.util.spec_from_file_location("protocol_api_fixtures", Path(__file__).with_name("producer-test.py"))
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
NOW = FIXTURES.NOW


class FakeApi:
    def __init__(self, case):
        self.case = case
        self.calls = []
        self.mutate = lambda endpoint, value: value

    def json(self, endpoint):
        self.calls.append(endpoint)
        case, binding = self.case, self.case.binding
        require = lambda condition: self._unexpected(endpoint) if not condition else None
        require(endpoint == A.PREFIX or endpoint.startswith(A.PREFIX + "/"))
        path = endpoint[len(A.PREFIX):].lstrip("/").split("?", 1)[0]
        query = parse_qs(urlsplit(endpoint).query)
        if not path:
            result = {"id": 1319052603, "full_name": A.REPOSITORY, "default_branch": "main"}
        elif path == "pulls/17":
            result = {"number": 17, "state": "open", "merge_commit_sha": binding["merge_sha"],
                      **{side: {"repo": {"id": 1319052603, "full_name": A.REPOSITORY},
                                "ref": binding[side + "_ref"], "sha": binding[side + "_sha"]} for side in ("base", "head")}}
        elif path.startswith("git/ref/"):
            ref = path[len("git/ref/"):]
            identities = {"heads/main": binding["base_sha"], "heads/" + binding["head_ref"]: binding["head_sha"],
                          "pull/17/merge": binding["merge_sha"]}
            require(ref in identities)
            result = {"ref": "refs/" + ref, "object": {"type": "commit", "sha": identities[ref]}}
        elif path == "git/commits/" + binding["merge_sha"]:
            result = {"sha": binding["merge_sha"], "tree": {"sha": binding["merge_tree"]},
                      "parents": [{"sha": sha} for sha in binding["merge_parents"]]}
        elif path.startswith("git/trees/"):
            identity = path.rsplit("/", 1)[1]
            if identity == binding["merge_tree"]:
                entries = [{"path": ".github", "mode": "040000", "type": "tree", "sha": "1" * 40}]
            elif identity == "1" * 40:
                entries = [{"path": "workflows", "mode": "040000", "type": "tree", "sha": "2" * 40}]
            else:
                require(identity == "2" * 40)
                entries = [{"path": name.rsplit("/", 1)[1], **entry} for name, entry in case.generation.items()]
            result = {"sha": identity, "truncated": False, "tree": entries}
        elif path == "actions/workflows/99/runs":
            require(query.get("head_sha") == [binding["head_sha"]] and "status" not in query and "created" not in query)
            result = self.page(list(case.runs.values()), "workflow_runs", query)
        elif path.startswith("actions/runs/"):
            parts = path.split("/")
            run_id = int(parts[2]); require(run_id in case.runs)
            if len(parts) == 3 or len(parts) == 5 and parts[3] == "attempts":
                result = deepcopy(case.runs[run_id])
                if len(parts) == 5:
                    require(int(parts[4]) == result["run_attempt"])
            elif parts[-1] == "jobs":
                result = self.page(case.jobs[run_id], "jobs", query)
            elif parts[-1] == "artifacts":
                result = self.page(case.artifacts[run_id], "artifacts", query)
            else:
                self._unexpected(endpoint)
        elif path.startswith("check-suites/"):
            run = next(value for value in case.runs.values() if value["check_suite_id"] == int(path.rsplit("/", 1)[1]))
            result = {"id": run["check_suite_id"], "head_sha": binding["head_sha"],
                      "repository": {"id": 1319052603, "full_name": A.REPOSITORY}, "app": {"id": 15368}}
        elif path.startswith("check-runs/"):
            identity = int(path.rsplit("/", 1)[1]); job = next(job for jobs in case.jobs.values() for job in jobs if job["id"] == identity)
            result = {"id": identity, "head_sha": job["head_sha"], "app": {"id": 15368},
                      "check_suite": {"id": case.runs[job["run_id"]]["check_suite_id"]}}
        elif path.startswith("actions/artifacts/"):
            identity = int(path.rsplit("/", 1)[1])
            result = next(item for items in case.artifacts.values() for item in items if item["id"] == identity)
        else:
            self._unexpected(endpoint)
        return self.mutate(endpoint, deepcopy(result))

    def page(self, items, field, query):
        page = int(query["page"][0]); return {"total_count": len(items), field: items[(page - 1) * 100:page * 100]}

    def bytes(self, endpoint):
        self.calls.append(endpoint)
        return self.case.archives[int(endpoint.split("/")[-2])]

    def _unexpected(self, endpoint):
        raise AssertionError("unexpected fake GET endpoint")


class AdapterTests(unittest.TestCase):
    def setUp(self):
        example = FIXTURES.ProducerProtocolTests()
        example.setUp()
        self.binding, self.plan, self.context = example.binding, example.plan, example.context
        self.pp = replace(example.policy, workflow_path=".github/workflows/project-tests.yml", events=("pull_request",),
                          workflow_ref="refs/pull/17/merge")
        self.generation = {path: {"mode": "100644", "type": "blob", "sha": str(index + 4) * 40}
                           for index, path in enumerate(sorted(A.WORKFLOWS))}
        self.generation[self.pp.workflow_path]["sha"] = self.pp.workflow_blob
        self.policy = A.AdapterPolicy(self.pp, 99, ".github/workflows/repository-checks.yml", {"reviewed": self.generation},
                                      "project / Publish producer descriptor", {"shared-host": "project / Shared tests"})
        self.runs, self.jobs, self.artifacts, self.archives = {}, {}, {}, {}
        self.aggregate = deepcopy(example.aggregate)
        self.add_run(replace(example.run, workflow_path=self.pp.workflow_path, workflow_commit=self.binding["merge_sha"],
                             workflow_ref=self.pp.workflow_ref, event="pull_request"))
        self.api = FakeApi(self)
        self.adapter = A.Adapter(self.api)

    def add_run(self, run, *, descriptor=True):
        self.runs[run.run_id] = {
            "id": run.run_id, "workflow_id": 99, "check_suite_id": run.run_id + 1000,
            "path": self.policy.caller_path, "event": "pull_request", "head_sha": self.binding["head_sha"],
            "head_branch": self.binding["head_ref"], "repository": {"id": 1319052603, "full_name": A.REPOSITORY},
            "head_repository": {"id": 1319052603, "full_name": A.REPOSITORY}, "pull_requests": [{"number": 17}],
            "referenced_workflows": [{"path": A.REPOSITORY + "/" + self.pp.workflow_path + "@" + self.binding["merge_sha"],
                                      "sha": self.binding["merge_sha"], "ref": self.pp.workflow_ref}],
            "run_attempt": run.attempt, "run_started_at": run.attempt_started_at,
            "status": run.status, "conclusion": run.conclusion, "updated_at": "2026-10-15T10:04:30Z"}
        self.jobs[run.run_id] = [{"id": job.job_id, "run_id": run.run_id, "run_attempt": job.attempt,
                                "head_sha": self.binding["head_sha"], "name": name, "status": job.status,
                                "conclusion": job.conclusion, "started_at": job.started_at, "completed_at": job.completed_at,
                                "check_run_url": f"https://api.github.com/{A.PREFIX}/check-runs/{job.job_id}"}
                               for name, job in [(self.policy.publisher_job, run.publisher),
                                                 *[(self.policy.owner_jobs[name], job) for name, job in run.owners.items()]] if job is not None]
        self.artifacts[run.run_id] = []
        if descriptor:
            value = P.descriptor(self.binding, self.plan, self.pp, run)
            self.artifact(run, "descriptor", value)
            aggregate = deepcopy(self.aggregate)
            aggregate["descriptor_digest"] = value["descriptor_digest"]
            self.artifact(run, "aggregate", FIXTURES.signed(aggregate, "aggregate_digest"))

    def artifact(self, run, kind, value):
        raw = P.artifact_bytes(value, kind)
        identity = run.run_id * 10 + (1 if kind == "descriptor" else 2)
        item = {"id": identity, "name": f"ci-{kind}-{run.run_id}-{run.attempt}", "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "size_in_bytes": len(raw), "expired": False, "created_at": run.publisher.completed_at if kind == "descriptor" else "2026-10-15T10:04:30Z",
                "expires_at": "2026-10-17T10:00:00Z", "workflow_run": {"id": run.run_id, "repository_id": 1319052603,
                "head_repository_id": 1319052603, "head_sha": self.binding["head_sha"]}}
        self.artifacts[run.run_id].append(item); self.archives[identity] = raw

    def capture(self):
        return self.adapter.capture(17, self.plan, self.policy, now=NOW)

    def verify(self):
        return self.adapter.verify(17, self.plan, self.policy, {"shared-host": self.context}, clock=lambda: NOW)

    def authority(self):
        snapshot = self.capture()
        return P.select_authority(snapshot.observations, snapshot.binding, self.plan, self.pp,
                                  inventory_complete=snapshot.inventory_complete, now=NOW)

    def test_complete_api_chain_and_inner_receipt_preserve_original_expiry(self):
        with patch.object(P.execution, "execute", side_effect=AssertionError("read-only verifier")):
            result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["expires_at"], self.aggregate["expires_at"])
        self.assertEqual(result["source_chain"]["producer_commit"], self.binding["merge_sha"])
        self.assertNotEqual(result["source_chain"]["producer_commit"], self.binding["head_sha"])
        self.assertTrue(all(path.startswith(A.PREFIX) for path in self.api.calls))

    def test_run_head_is_never_used_as_original_merge_or_owner_source(self):
        def changed(endpoint, value):
            if "/attempts/" in endpoint and "referenced_workflows" in value:
                value["referenced_workflows"][0]["sha"] = self.binding["head_sha"]
            return value
        self.api.mutate = changed
        self.assertEqual(self.authority()["state"], "unresolved")
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_artifact_claims_cannot_supply_missing_api_chain_or_check_app(self):
        cases = (lambda value: value.update(referenced_workflows=[]),
                 lambda value: value["repository"].update(id=42),
                 lambda value: value["pull_requests"][0].update(number=18))
        for change in cases:
            with self.subTest(change=change):
                def mutate(endpoint, value):
                    if "/attempts/" in endpoint and "referenced_workflows" in value: change(value)
                    return value
                self.api.mutate = mutate
                self.assertEqual(self.authority()["state"], "unresolved")
        self.api.mutate = lambda endpoint, value: ({**value, "app": {"id": 42}} if "/check-runs/" in endpoint else value)
        self.assertEqual(self.authority()["state"], "unresolved")

    def test_foreign_remote_duplicate_and_nonlocal_references_fail_closed(self):
        for mode in ("foreign", "duplicate", "nonlocal", "stale"):
            def mutate(endpoint, value):
                if "/attempts/" in endpoint and "referenced_workflows" in value:
                    item = value["referenced_workflows"][0]
                    if mode == "foreign": item["path"] = item["path"].replace(A.REPOSITORY, "overte-org/overte")
                    elif mode == "duplicate": value["referenced_workflows"].append(deepcopy(item))
                    elif mode == "nonlocal": item["ref"] = "refs/heads/main"
                    else: item["sha"] = "f" * 40
                return value
            self.api.mutate = mutate
            with self.subTest(mode=mode): self.assertEqual(self.authority()["state"], "unresolved")

    def test_original_caller_or_mixed_workflow_generation_cannot_be_borrowed(self):
        for field, value in (("sha", "f" * 40), ("mode", "100755"), ("type", "commit")):
            def mutate(endpoint, result):
                if endpoint.endswith("git/trees/" + "2" * 40):
                    next(entry for entry in result["tree"] if entry["path"] == "repository-checks.yml")[field] = value
                return result
            self.api.mutate = mutate
            with self.subTest(field=field): self.assertEqual(self.authority()["state"], "unresolved")

    def test_latest_queued_unclassified_failed_or_tied_run_never_uses_old_green(self):
        original = self.capture().observations[0].run
        for status, conclusion, descriptor in (("queued", None, False), ("completed", "failure", True)):
            later = replace(original, run_id=101, status=status, conclusion=conclusion,
                            attempt_started_at="2026-10-15T10:01:00Z", publisher=None, owners={})
            # Failure with descriptor needs an actual independently bound publisher.
            if descriptor:
                later = replace(later, publisher=replace(original.publisher, job_id=111,
                                started_at="2026-10-15T10:01:00Z", completed_at="2026-10-15T10:01:30Z"))
            self.add_run(later, descriptor=descriptor)
            with self.subTest(status=status):
                self.assertIn(self.authority()["state"], {"unresolved", "failed"})
                with self.assertRaises(P.ProtocolError): self.verify()
            del self.runs[101]; del self.jobs[101]; del self.artifacts[101]
        tied = replace(original, run_id=102, publisher=replace(original.publisher, job_id=112),
                       owners={name: replace(job, job_id=122) for name, job in original.owners.items()})
        self.add_run(tied)
        self.assertEqual(self.authority()["state"], "unresolved")

    def test_latest_attempt_is_read_and_mixed_rerun_jobs_never_reuse_attempt_one(self):
        run = self.capture().observations[0].run
        current = replace(run, attempt=2, latest_attempt=2,
                          publisher=replace(run.publisher, attempt=2),
                          owners={name: replace(job, attempt=2) for name, job in run.owners.items()})
        self.add_run(current)
        snapshot = self.capture()
        self.assertTrue(snapshot.inventory_complete)
        self.assertEqual(snapshot.observations[0].run.attempt, 2)
        self.assertTrue(any("/attempts/2/jobs?" in path for path in self.api.calls))
        self.jobs[100][-1]["run_attempt"] = 1
        self.assertEqual(self.authority()["state"], "unresolved")

    def test_reused_artifact_name_foreign_owner_digest_size_and_expiry_fail(self):
        original = deepcopy(self.artifacts[100])
        for change in (lambda rows: rows.append({**rows[0], "id": 999}),
                       lambda rows: rows[0].update(digest="unavailable"),
                       lambda rows: rows[0].update(size_in_bytes=P._MAX_ARCHIVE + 1),
                       lambda rows: rows[0].update(expired=True),
                       lambda rows: rows[0]["workflow_run"].update(id=999),
                       lambda rows: rows[0]["workflow_run"].update(head_sha="f" * 40)):
            self.artifacts[100] = deepcopy(original); change(self.artifacts[100])
            with self.subTest(change=change): self.assertEqual(self.authority()["state"], "unresolved")
        self.artifacts[100] = original
        self.archives[1001] = b"Tampered compressed archive"
        self.assertEqual(self.authority()["state"], "unresolved")

    def test_missing_aggregate_fails(self):
        self.artifacts[100] = self.artifacts[100][:1]
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_actual_runtime_mismatch_fails(self):
        self.context = replace(self.context, environment={"different": "actual runtime"})
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_missing_failed_skipped_or_pending_selected_owner_never_verifies(self):
        original = deepcopy(self.jobs[100])
        for status, conclusion in (("completed", "failure"), ("completed", "skipped"), ("queued", None)):
            self.jobs[100] = deepcopy(original)
            self.jobs[100][-1].update(status=status, conclusion=conclusion)
            with self.subTest(status=status, conclusion=conclusion), self.assertRaises(P.ProtocolError):
                self.verify()
        self.jobs[100] = original[:1]
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_forged_artifact_detail_and_deleted_or_replaced_archive_fail(self):
        for field, replacement in (("digest", "sha256:" + "f" * 64), ("expired", True), ("id", 999)):
            def mutate(endpoint, value):
                if endpoint.endswith("actions/artifacts/1001"):
                    value[field] = replacement
                return value
            self.api.mutate = mutate
            with self.subTest(field=field): self.assertFalse(self.capture().inventory_complete)
        self.api.mutate = lambda endpoint, value: value
        self.archives[1002] = self.archives[1001]
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_initial_final_current_refs_and_new_authority_are_rechecked(self):
        count = 0
        def mutate(endpoint, value):
            nonlocal count
            if endpoint.endswith("pulls/17"):
                count += 1
                if count >= 4: value["head"]["sha"] = "f" * 40
            return value
        self.api.mutate = mutate
        with self.assertRaises(P.ProtocolError): self.verify()
        self.setUp()
        count = 0
        def new_attempt(endpoint, value):
            nonlocal count
            if "/runs?head_sha=" in endpoint:
                count += 1
                if count >= 2: value["workflow_runs"][0]["run_attempt"] = 2
            return value
        self.api.mutate = new_attempt
        self.assertFalse(self.capture().inventory_complete)
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_final_aggregate_inventory_cannot_delete_replace_or_duplicate_downloaded_proof(self):
        for mode in ("deleted", "replaced", "duplicated"):
            count = 0
            def mutate(endpoint, value):
                nonlocal count
                if "/actions/runs/100/artifacts?" in endpoint:
                    count += 1
                    if count == 2:
                        if mode == "deleted": value["artifacts"] = value["artifacts"][:1]
                        elif mode == "replaced": value["artifacts"][-1]["id"] = 999
                        else: value["artifacts"].append({**value["artifacts"][-1], "id": 999})
                        value["total_count"] = len(value["artifacts"])
                return value
            self.api.mutate = mutate
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.verify()

    def test_complete_pagination_and_search_cap_missing_pages_or_duplicate_ids(self):
        values = [{"id": number} for number in range(1, 102)]
        calls = []
        def pages(endpoint):
            calls.append(endpoint); page = int(parse_qs(urlsplit(endpoint).query)["page"][0])
            return {"total_count": 101, "workflow_runs": values[(page - 1) * 100:page * 100]}
        with patch.object(self.api, "json", side_effect=pages):
            self.assertEqual(len(self.adapter._pages("actions/workflows/99/runs", "workflow_runs", search=True)), 101)
        self.assertEqual(len(calls), 2)
        for value in ({"total_count": 1000, "workflow_runs": []}, {"total_count": 2, "workflow_runs": [{"id": 1}]},
                      {"total_count": 2, "workflow_runs": [{"id": 1}, {"id": 1}]}):
            with patch.object(self.api, "json", return_value=value), self.assertRaises(P.ProtocolError):
                self.adapter._pages("actions/workflows/99/runs", "workflow_runs", search=True)
        values = [{"id": number} for number in range(1, 1001)]
        def maximum(endpoint):
            page = int(parse_qs(urlsplit(endpoint).query)["page"][0])
            return {"total_count": 1000, "jobs": values[(page - 1) * 100:page * 100]}
        with patch.object(self.api, "json", side_effect=maximum):
            self.assertEqual(len(self.adapter._pages("actions/runs/100/jobs", "jobs")), 1000)
        counts = iter((101, 102))
        def changing(endpoint):
            return {"total_count": next(counts), "workflow_runs": values[:100]}
        with patch.object(self.api, "json", side_effect=changing), self.assertRaises(P.ProtocolError):
            self.adapter._pages("actions/workflows/99/runs", "workflow_runs", search=True)


class ManualFakeApi(FakeApi):
    """Synthetic reviewed controller tree only; no real workflow is admitted."""
    def json(self, endpoint):
        path = endpoint[len(A.PREFIX):].lstrip("/").split("?", 1)[0]
        case = self.case
        if path == "git/commits/" + case.source.controller_commit:
            result = {"sha": case.source.controller_commit, "tree": {"sha": case.source.controller_tree},
                      "parents": [{"sha": "8" * 40}]}
        elif path.startswith("git/trees/") and path.rsplit("/", 1)[1] in case.controller_trees:
            identity = path.rsplit("/", 1)[1]
            result = {"sha": identity, "truncated": False, "tree": case.controller_trees[identity]}
        elif path == "actions/workflows/99/runs":
            query = parse_qs(urlsplit(endpoint).query)
            self.case.assertEqual(query.get("head_sha"), [case.source.controller_commit])
            self.case.assertEqual(query.get("event"), ["workflow_dispatch"])
            self.case.assertEqual(query.get("branch"), ["main"])
            self.case.assertNotIn("status", query)
            self.case.assertNotIn("created", query)
            result = self.page(list(case.runs.values()), "workflow_runs", query)
        elif path.startswith("actions/jobs/"):
            identity = int(path.rsplit("/", 1)[1])
            result = next(job for jobs in case.jobs.values() for job in jobs if job["id"] == identity)
        elif path.startswith("check-suites/"):
            identity = int(path.rsplit("/", 1)[1])
            result = {"id": identity, "head_sha": case.source.controller_commit,
                      "repository": {"id": 1319052603, "full_name": A.REPOSITORY}, "app": {"id": 15368}}
        else:
            return super().json(endpoint)
        self.calls.append(endpoint)
        return self.mutate(endpoint, deepcopy(result))


class ManualAdapterTests(unittest.TestCase):
    add_run = AdapterTests.add_run
    capture = AdapterTests.capture
    verify = AdapterTests.verify
    authority = AdapterTests.authority
    artifact = AdapterTests.artifact

    def setUp(self):
        AdapterTests.setUp(self)
        example = FIXTURES.ProducerProtocolTests()
        example.setUp()
        sources = {
            ".github/workflows/producer.yml": {"mode": "100644", "type": "blob", "sha": example.policy.workflow_blob},
            "tools/test-evidence/fake-manual-controller.py": {"mode": "100644", "type": "blob", "sha": "6" * 40},
            "tools/test-evidence/producer.py": {"mode": "100644", "type": "blob", "sha": "7" * 40},
        }
        self.source = A.ManualSource(True, self.binding["base_sha"], "9" * 40,
                                     "tools/test-evidence/fake-manual-controller.py", sources)
        self.pp = replace(example.policy, controller_digest=A.manual_identity(self.source))
        self.policy = A.AdapterPolicy(self.pp, 99, self.pp.workflow_path, {},
                                      "Publish descriptor", {"shared-host": "Protected shared owner"},
                                      "manual-main-v1", self.source)
        self.runs, self.jobs, self.artifacts, self.archives = {}, {}, {}, {}
        self.run = replace(example.run, workflow_commit=self.source.controller_commit)
        self.add_manual_run(self.run)
        # Build a small immutable tree with the complete synthetic executable map.
        directories = {"": self.source.controller_tree}
        self.controller_trees = {self.source.controller_tree: []}
        for path, entry in sources.items():
            parts = path.split("/")
            for index, part in enumerate(parts):
                parent = "/".join(parts[:index])
                entries = self.controller_trees[directories[parent]]
                if index == len(parts) - 1:
                    entries.append({"path": part, **entry})
                else:
                    directory = "/".join(parts[:index + 1])
                    if directory not in directories:
                        identity = hashlib.sha1(directory.encode()).hexdigest()
                        directories[directory] = identity
                        self.controller_trees[identity] = []
                        entries.append({"path": part, "mode": "040000", "type": "tree", "sha": identity})
        self.api = ManualFakeApi(self)
        self.adapter = A.Adapter(self.api)

    def add_manual_run(self, run, *, descriptor=True):
        AdapterTests.add_run(self, run, descriptor=descriptor)
        self.runs[run.run_id].update(event="workflow_dispatch", head_sha=self.source.controller_commit,
                                     head_branch="main", pull_requests=[], referenced_workflows=[])
        for job in self.jobs[run.run_id]:
            job["head_sha"] = self.source.controller_commit
        for artifact in self.artifacts[run.run_id]:
            artifact["workflow_run"]["head_sha"] = self.source.controller_commit

    def test_manual_candidate_proof_is_distinct_from_authenticated_main_source(self):
        with patch.object(P.execution, "execute", side_effect=AssertionError("no candidate execution")):
            snapshot = self.capture()
            with self.assertRaisesRegex(P.ProtocolError, "protected post-kill receipt verification is not implemented"):
                self.verify()
        self.assertTrue(snapshot.inventory_complete)
        chain = snapshot.source_chains[100]
        self.assertEqual(chain["source_kind"], "manual-main-v1")
        self.assertEqual(chain["producer_commit"], self.source.controller_commit)
        self.assertNotEqual(chain["producer_commit"], self.binding["merge_sha"])
        self.assertEqual(chain["original_attempt"], 1)
        self.assertEqual(chain["owner_job_ids"], {"shared-host": 120})
        self.assertEqual(self.authority()["state"], "proof-required", "source admission is never a passed reusable result")
        self.assertIn(A.PREFIX + "/actions/jobs/120", self.api.calls)

    def test_manual_support_is_default_off_and_json_cannot_supply_policy(self):
        for manual in (A.ManualSource(), replace(self.source, enabled=False),
                       replace(self.source, enabled="true"), self.source.__dict__, None):
            self.api.calls.clear()
            with self.subTest(manual=manual), self.assertRaises(P.ProtocolError):
                self.adapter.capture(17, self.plan, replace(self.policy, manual=manual), now=NOW)
            self.assertEqual(self.api.calls, [])
        self.assertEqual(A.AdapterPolicy(self.pp, 99, self.pp.workflow_path, {}, "publisher", {}).source_kind,
                         "reusable-pr")
        with self.assertRaises(P.ProtocolError):
            self.adapter.capture(17, self.plan, self.policy.__dict__, now=NOW)
        for changes in ({"source_kind": "unreviewed"}, {"source_kind": "reusable-pr"},
                        {"generations": {"mixed": self.generation}}):
            with self.subTest(changes=changes), self.assertRaises(P.ProtocolError):
                self.adapter.capture(17, self.plan, replace(self.policy, **changes), now=NOW)

    def test_manual_run_cannot_change_main_repo_event_source_or_use_reusable_callee(self):
        cases = ({"event": "pull_request"}, {"head_branch": "other"}, {"head_sha": self.binding["merge_sha"]},
                 {"path": ".github/workflows/other.yml"}, {"workflow_id": 98},
                 {"repository": {"id": 42, "full_name": A.REPOSITORY}},
                 {"head_repository": {"id": 1319052603, "full_name": "overte-org/overte"}},
                 {"pull_requests": [{"number": 17}]}, {"referenced_workflows": [{"sha": self.binding["merge_sha"]}]})
        for change in cases:
            with self.subTest(change=change):
                original = deepcopy(self.runs[100])
                self.runs[100].update(change)
                self.assertFalse(self.capture().inventory_complete)
                with self.assertRaises(P.ProtocolError): self.verify()
                self.runs[100] = original

    def test_complete_controller_tree_sources_modes_and_digest_must_match_review(self):
        source = self.source
        for change in ({"controller_tree": "8" * 40}, {"controller_commit": "7" * 40},
                       {"controller_path": "tools/untrusted.py"},
                       {"sources": {self.pp.workflow_path: source.sources[self.pp.workflow_path]}}):
            with self.subTest(change=change):
                modified = replace(source, **change)
                policy = replace(self.policy, manual=modified,
                                 producer=replace(self.pp, controller_digest=A.manual_identity(modified)))
                with self.assertRaises(P.ProtocolError):
                    self.adapter.verify(17, self.plan, policy, {"shared-host": self.context}, clock=lambda: NOW)
        for mutation in ("blob", "mode", "truncated", "duplicate"):
            def mutate(endpoint, value):
                if "/git/trees/" in endpoint:
                    if mutation == "truncated": value["truncated"] = True
                    for entry in value["tree"][:]:
                        if entry.get("path") == "fake-manual-controller.py":
                            if mutation == "blob": entry["sha"] = "0" * 40
                            elif mutation == "mode": entry["mode"] = "120000"
                            elif mutation == "duplicate": value["tree"].append(deepcopy(entry))
                return value
            self.api.mutate = mutate
            with self.subTest(mutation=mutation):
                self.assertEqual(self.authority()["state"], "unresolved")
        self.api.mutate = lambda endpoint, value: value
        with self.assertRaises(P.ProtocolError):
            self.adapter.capture(17, self.plan, replace(self.policy, producer=replace(self.pp, controller_digest="sha256:" + "0" * 64)), now=NOW)

    def test_original_attempt_is_never_inferred_from_rerun_snapshot_or_old_timestamps(self):
        self.add_manual_run(replace(self.run, run_id=101, attempt=2, latest_attempt=2), descriptor=False)
        self.runs[101]["run_started_at"] = self.runs[100]["run_started_at"]
        for job in self.jobs[101]:
            job["run_attempt"] = 2  # A later snapshot can retain original success times.
        snapshot = self.capture()
        self.assertIn("manual-original-attempt-unavailable", snapshot.unavailable)
        self.assertFalse(snapshot.inventory_complete)
        with self.assertRaises(P.ProtocolError): self.verify()
        self.assertFalse(any("/attempts/2/jobs" in call for call in self.api.calls))

    def test_job_specific_identity_check_app_and_first_attempt_inventory_are_required(self):
        for field, value in (("id", 999), ("run_id", 999), ("head_sha", self.binding["merge_sha"]),
                             ("run_attempt", 2), ("run_attempt", True), ("name", "other")):
            def mutate(endpoint, document):
                if endpoint.endswith("/actions/jobs/120"): document[field] = value
                return document
            self.api.mutate = mutate
            with self.subTest(field=field, value=value):
                self.assertEqual(self.authority()["state"], "unresolved")
        self.api.mutate = lambda endpoint, value: ({**value, "app": {"id": 42}}
                                                   if "/check-runs/" in endpoint else value)
        self.assertEqual(self.authority()["state"], "unresolved")
        self.api.mutate = lambda endpoint, value: value
        for job in self.jobs[100]: job.pop("run_attempt")
        self.assertTrue(self.capture().inventory_complete,
                        "first-ever attempt can authenticate job IDs without snapshot attempt fields")
        with self.assertRaisesRegex(P.ProtocolError, "protected post-kill receipt verification is not implemented"):
            self.verify()

    def test_artifact_json_cannot_replace_actual_candidate_context_or_original_run(self):
        with self.assertRaises(P.ProtocolError):
            self.adapter.verify(17, self.plan, self.policy, {}, clock=lambda: NOW)
        for context in (replace(self.context, candidate_commit=self.source.controller_commit),
                        replace(self.context, candidate_tree="8" * 40)):
            with self.assertRaises(P.ProtocolError):
                self.adapter.verify(17, self.plan, self.policy, {"shared-host": context}, clock=lambda: NOW)
        self.artifacts[100][1]["workflow_run"]["head_sha"] = self.binding["head_sha"]
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_current_base_advance_or_old_base_receipt_cannot_relabel_candidate(self):
        aggregate = deepcopy(self.aggregate)
        receipt = aggregate["results"]["shared-host"]["receipt"]
        receipt.update(candidate_commit="8" * 40, candidate_tree="7" * 40)
        aggregate["results"]["shared-host"]["receipt"] = FIXTURES.signed(receipt, "receipt_digest")
        descriptor = P.descriptor(self.binding, self.plan, self.pp, self.run)
        aggregate["descriptor_digest"] = descriptor["descriptor_digest"]
        self.artifacts[100].pop()
        self.artifact(self.run, "aggregate", FIXTURES.signed(aggregate, "aggregate_digest"))
        self.artifacts[100][-1]["workflow_run"]["head_sha"] = self.source.controller_commit
        with self.assertRaisesRegex(P.ProtocolError, "shared source|complete original proof"):
            self.verify()
        self.binding["base_sha"] = "8" * 40
        self.binding["merge_sha"] = "7" * 40
        self.binding["merge_tree"] = "6" * 40
        self.binding["merge_parents"][0] = self.binding["base_sha"]
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_newer_pending_missing_or_failed_manual_run_never_falls_back_to_old_green(self):
        for status, conclusion in (("queued", None), ("in_progress", None), ("completed", "failure")):
            self.add_manual_run(replace(self.run, run_id=101, status=status, conclusion=conclusion,
                                        attempt_started_at="2026-10-15T10:04:00Z", owners={},
                                        publisher=replace(self.run.publisher, job_id=210,
                                                          started_at="2026-10-15T10:04:00Z",
                                                          completed_at="2026-10-15T10:04:10Z")),
                                descriptor=status != "queued")
            with self.subTest(status=status), self.assertRaises(P.ProtocolError): self.verify()
            self.assertNotEqual(self.authority()["state"], "proof-required")

    def test_final_bookend_reauthenticates_original_job_ids(self):
        original = self.api.bytes
        def replace_owner(endpoint):
            raw = original(endpoint)
            if endpoint.endswith("/1002/zip"):
                self.jobs[100][1].update(id=121, check_run_url=f"https://api.github.com/{A.PREFIX}/check-runs/121")
            return raw
        with patch.object(self.api, "bytes", side_effect=replace_owner), self.assertRaisesRegex(
                P.ProtocolError, "manual original source/job provenance changed"):
            self.verify()


class ReadOnlyBoundaryTests(unittest.TestCase):
    def test_only_fixed_fork_gets_are_issued_and_error_details_stay_private(self):
        real = subprocess.Popen
        commands = []
        def child(command, **kwargs):
            commands.append(command)
            return real([sys.executable, "-c", "import os;os.write(2,b'private-token signed-url');raise SystemExit(1)"], **kwargs)
        with patch.object(A.shutil, "which", return_value="/usr/bin/gh"), patch.object(A.subprocess, "Popen", side_effect=child):
            with self.assertRaises(A.ApiError) as result: A.GitHubReadOnly().json(A.PREFIX + "/actions/runs/1")
        self.assertNotIn("private-token", str(result.exception)); self.assertNotIn("signed-url", str(result.exception))
        self.assertIn("GET", commands[0]); self.assertIn("github.com", commands[0]); self.assertNotIn("POST", commands[0])
        for endpoint in ("https://signed.example/private", "repos/overte-org/overte/actions/runs", A.PREFIX + "/../other", A.PREFIX + "/x\nsecret"):
            with patch.object(A.subprocess, "Popen") as process, self.assertRaises(A.ApiError):
                A.GitHubReadOnly().json(endpoint)
            process.assert_not_called()

    def test_raw_output_and_json_are_bounded_and_candidate_shadowed_gh_is_rejected(self):
        real = subprocess.Popen
        with patch.object(A.shutil, "which", return_value="/usr/bin/gh"), patch.object(
                A.subprocess, "Popen", side_effect=lambda command, **kwargs: real(
                    [sys.executable, "-c", "import os;os.write(1,b'x'*1000)"], **kwargs)), self.assertRaises(A.ApiError):
            A.GitHubReadOnly()._request(A.PREFIX + "/actions/runs/1", 16)
        with patch.object(A.shutil, "which", return_value="/candidate/gh"), self.assertRaises(A.ApiError):
            A.GitHubReadOnly().json(A.PREFIX + "/actions/runs/1")
        with patch.object(A.GitHubReadOnly, "_request", return_value=b'{"duplicate":1,"duplicate":2}'), self.assertRaises(A.ApiError):
            A.GitHubReadOnly().json(A.PREFIX + "/actions/runs/1")
        with patch.object(A.GitHubReadOnly, "_request", return_value=b'{"invalid":NaN}'), self.assertRaises(A.ApiError):
            A.GitHubReadOnly().json(A.PREFIX + "/actions/runs/1")

    def test_deadline_kills_the_read_only_child_and_closes_its_pipes(self):
        real, children = subprocess.Popen, []
        def child(command, **kwargs):
            process = real([sys.executable, "-c", "import time;time.sleep(5)"], **kwargs)
            children.append(process)
            return process
        with patch.object(A.shutil, "which", return_value="/usr/bin/gh"), patch.object(
                A.subprocess, "Popen", side_effect=child), patch.object(A.time, "monotonic", side_effect=(0, 46)), self.assertRaises(A.ApiError):
            A.GitHubReadOnly().json(A.PREFIX + "/actions/runs/1")
        self.assertIsNotNone(children[0].returncode)
        self.assertTrue(children[0].stdout.closed and children[0].stderr.closed)


if __name__ == "__main__":
    unittest.main()
