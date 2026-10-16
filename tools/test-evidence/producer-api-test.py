#!/usr/bin/env python3
"""Adversarial fake-API tests; no live requests, builds, installs or dispatch."""

from copy import deepcopy
from dataclasses import replace
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

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
        elif path == "commits/refs/pull/17/merge":
            result = {"sha": binding["merge_sha"], "commit": {"tree": {"sha": binding["merge_tree"]}},
                      "parents": [{"sha": sha} for sha in binding["merge_parents"]]}
        elif path.startswith("git/ref/"):
            ref = unquote(path[len("git/ref/"):])
            identities = {"heads/main": binding["base_sha"], "heads/" + binding["head_ref"]: binding["head_sha"]}
            require(ref in identities)
            result = {"ref": "refs/" + ref, "object": {"type": "commit", "sha": identities[ref]}}
        elif path.startswith("git/commits/"):
            revision = path.rsplit("/",1)[1]
            if revision == binding["merge_sha"]:
                tree,parents=binding["merge_tree"],binding["merge_parents"]
            elif revision == binding["head_sha"]:
                tree,parents="8"*40,["7"*40]
            else:
                require(revision in case.originals)
                tree,parents=case.originals[revision]
            result = {"sha": revision, "tree": {"sha": tree}, "parents": [{"sha": sha} for sha in parents]}
        elif path.startswith("git/trees/"):
            identity = path.rsplit("/", 1)[1]
            if identity == binding["merge_tree"] or identity in {tree for tree,_ in case.originals.values()}:
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
                      "check_suite": {"id": case.runs[job["run_id"]]["check_suite_id"]},
                      **{key: job[key] for key in ("name", "status", "conclusion", "started_at", "completed_at")}}
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
                                      "project / Publish producer descriptor", {"shared-host": "project / Shared tests"},
                                      "project / Publish final producer ")
        self.runs, self.jobs, self.artifacts, self.archives, self.originals = {}, {}, {}, {}, {}
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
        if run.final_publisher is not None:
            publication = run.final_publisher
            job = publication.job
            self.jobs[run.run_id].append({"id": job.job_id, "run_id": run.run_id, "run_attempt": job.attempt,
                "head_sha": self.binding["head_sha"], "name": self.policy.final_publisher_prefix + publication.receipt_sha256,
                "status": job.status, "conclusion": job.conclusion, "started_at": job.started_at,
                "completed_at": job.completed_at,
                "check_run_url": f"https://api.github.com/{A.PREFIX}/check-runs/{job.job_id}"})
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
                            attempt_started_at="2026-10-15T10:01:00Z", publisher=None, owners={}, final_publisher=None)
            # Failure with descriptor needs an actual independently bound publisher.
            if descriptor:
                later = replace(later, publisher=replace(original.publisher, job_id=111,
                                started_at="2026-10-15T10:01:00Z", completed_at="2026-10-15T10:01:30Z"))
            self.add_run(later, descriptor=descriptor)
            with self.subTest(status=status):
                self.assertEqual(self.authority()["state"], "failed" if descriptor else "unresolved")
                with self.assertRaises(P.ProtocolError): self.verify()
            del self.runs[101]; del self.jobs[101]; del self.artifacts[101]
        tied = replace(original, run_id=102, publisher=replace(original.publisher, job_id=112),
                       owners={name: replace(job, job_id=122) for name, job in original.owners.items()},
                       final_publisher=replace(original.final_publisher,
                                               job=replace(original.final_publisher.job, job_id=132)))
        self.add_run(tied)
        self.assertEqual(self.authority()["state"], "unresolved")

    def test_latest_attempt_is_read_and_mixed_rerun_jobs_never_reuse_attempt_one(self):
        run = self.capture().observations[0].run
        current = replace(run, attempt=2, latest_attempt=2,
                          publisher=replace(run.publisher, attempt=2,job_id=210),
                          owners={name: replace(job, attempt=2,job_id=220) for name, job in run.owners.items()},
                          final_publisher=replace(run.final_publisher,
                                                  job=replace(run.final_publisher.job, attempt=2, job_id=230)))
        self.add_run(current)
        snapshot = self.capture()
        self.assertFalse(snapshot.inventory_complete)
        self.assertIn('original-attempt-unavailable',snapshot.unavailable)
        self.assertEqual(snapshot.observations,[])
        self.assertFalse(any("/attempts/2" in path for path in self.api.calls))
        with self.assertRaises(P.ProtocolError): self.verify()
        next(job for job in self.jobs[100] if job["name"] == self.policy.owner_jobs["shared-host"])["run_attempt"] = 1
        self.assertEqual(self.authority()["state"], "unresolved")

    def test_current_merge_uses_supported_commit_ref_without_legacy_payload_field(self):
        for legacy in ('missing',None,'e'*40):
            def mutate(endpoint,value):
                if endpoint.endswith('pulls/17'):
                    if legacy=='missing':value.pop('merge_commit_sha')
                    else:value['merge_commit_sha']=legacy
                return value
            self.api.mutate=mutate
            with self.subTest(legacy=legacy):
                binding,refs=self.adapter.current(17)
                self.assertEqual(binding,self.binding)
                self.assertEqual(refs['merge'],self.binding['merge_sha'])
        self.assertTrue(any(path.endswith('/commits/refs/pull/17/merge') for path in self.api.calls))
        self.assertFalse(any('/git/ref/pull/' in path for path in self.api.calls))

    def test_valid_branch_uri_characters_are_escaped_inside_fixed_fork_endpoints(self):
        self.binding['head_ref']='fix/main/hash#percent%20'
        binding,_=self.adapter.current(17)
        self.assertEqual(binding['head_ref'],self.binding['head_ref'])
        self.assertTrue(any(path.endswith('/git/ref/heads/fix/main/hash%23percent%2520') for path in self.api.calls))
        self.assertTrue(all('#' not in path and path.startswith(A.PREFIX) for path in self.api.calls))

    def test_current_ref_must_match_immutable_tree_ordered_parents_and_fresh_branches(self):
        for mode in ('tree','parents','head-as-merge','base-ref','head-ref'):
            def mutate(endpoint,value):
                if endpoint.endswith('/commits/refs/pull/17/merge'):
                    if mode=='tree':value['commit']['tree']['sha']='f'*40
                    elif mode=='parents':value['parents'].reverse()
                    elif mode=='head-as-merge':value['sha']=self.binding['head_sha']
                elif mode=='base-ref' and endpoint.endswith('/git/ref/heads/main'):value['object']['sha']='f'*40
                elif mode=='head-ref' and '/git/ref/heads/fix/' in endpoint:value['object']['sha']='f'*40
                return value
            self.api.mutate=mutate
            with self.subTest(mode=mode),self.assertRaises(P.ProtocolError):self.adapter.current(17)

    def add_other_candidate(self,status='completed',conclusion='failure'):
        run=self.capture().observations[0].run
        other=replace(run,run_id=101,status=status,conclusion=conclusion,
                      attempt_started_at='2026-10-15T10:01:00Z',publisher=None,owners={})
        self.add_run(other,descriptor=False)
        self.originals['f'*40]=('9'*40,['8'*40,self.binding['head_sha']])
        source=self.runs[101]['referenced_workflows'][0]
        source.update(sha='f'*40,path=A.REPOSITORY+'/'+self.pp.workflow_path+'@'+'f'*40)

    def test_authenticated_different_original_candidate_is_reported_without_reusing_it(self):
        self.add_other_candidate()
        snapshot=self.capture()
        self.assertTrue(snapshot.inventory_complete)
        self.assertEqual([item.run.run_id for item in snapshot.observations],[100])
        other=snapshot.other_candidates[101]
        self.assertEqual(other['candidate'],{'merge_sha':'f'*40,'merge_tree':'9'*40,
                                           'merge_parents':['8'*40,self.binding['head_sha']]})
        self.assertEqual(self.verify()['run_id'],100)
        self.assertFalse(any('/runs/101/artifacts' in path for path in self.api.calls))

    def test_other_candidate_cannot_hide_unknown_chain_parents_app_or_attempt(self):
        self.add_other_candidate()
        for mode in ('parent','workflow','app','attempt','missing-source'):
            def mutate(endpoint,value):
                if mode=='parent' and endpoint.endswith('/git/commits/'+'f'*40):value['parents'][1]['sha']='7'*40
                elif mode=='workflow' and endpoint.endswith('/git/trees/'+'2'*40):
                    value['tree'][0]['mode']='100755'
                elif mode=='app' and endpoint.endswith('/check-suites/1101'):value['app']['id']=42
                elif mode=='attempt' and endpoint.endswith('/actions/runs/101'):value['run_attempt']=2
                elif mode=='missing-source' and '/actions/runs/101' in endpoint and 'referenced_workflows' in value:
                    value['referenced_workflows']=[]
                return value
            self.api.mutate=mutate
            with self.subTest(mode=mode):
                snapshot=self.capture()
                self.assertFalse(snapshot.inventory_complete)
                with self.assertRaises(P.ProtocolError):self.verify()

    def test_new_current_candidate_failure_still_blocks_even_with_known_other_context(self):
        self.add_other_candidate()
        current=self.capture().observations[0].run
        failed=replace(current,run_id=102,conclusion='failure',attempt_started_at='2026-10-15T10:01:00Z',
                       publisher=replace(current.publisher,job_id=112,started_at='2026-10-15T10:01:00Z',
                                         completed_at='2026-10-15T10:01:30Z'),owners={},final_publisher=None)
        self.add_run(failed)
        with self.assertRaises(P.ProtocolError):self.verify()

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
            owner = next(job for job in self.jobs[100] if job["name"] == self.policy.owner_jobs["shared-host"])
            owner.update(status=status, conclusion=conclusion)
            with self.subTest(status=status, conclusion=conclusion), self.assertRaises(P.ProtocolError):
                self.verify()
        self.jobs[100] = [job for job in original if job["name"] != self.policy.owner_jobs["shared-host"]]
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

    def test_final_publisher_native_commitment_is_required_and_returned(self):
        result = self.verify()
        receipt = self.aggregate["results"]["shared-host"]["receipt"]
        self.assertEqual(result["final_publisher_job_id"], 130)
        self.assertEqual(result["receipt_sha256"], hashlib.sha256(P.canonical(receipt)).hexdigest())
        self.jobs[100] = [job for job in self.jobs[100]
                          if not job["name"].startswith(self.policy.final_publisher_prefix)]
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_reserved_final_publisher_malformed_duplicate_or_conflicting_jobs_deny(self):
        original = deepcopy(self.jobs[100])
        for mode in ("uppercase", "short", "suffix", "duplicate", "conflicting", "reused-owner"):
            self.jobs[100] = deepcopy(original)
            final = self.jobs[100][-1]
            if mode == "uppercase": final["name"] = self.policy.final_publisher_prefix + "A" * 64
            elif mode == "short": final["name"] = self.policy.final_publisher_prefix + "a" * 63
            elif mode == "suffix": final["name"] += " other"
            elif mode in {"duplicate", "conflicting"}:
                duplicate = {**final, "id": 131,
                             "check_run_url": f"https://api.github.com/{A.PREFIX}/check-runs/131"}
                if mode == "conflicting": duplicate["name"] = self.policy.final_publisher_prefix + "f" * 64
                self.jobs[100].append(duplicate)
            else: final["id"] = 120
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.verify()

    def test_final_publisher_native_check_name_status_timing_app_and_attempt_are_bound(self):
        for key, value in (("name", self.policy.final_publisher_prefix + "f" * 64),
                           ("status", "queued"), ("conclusion", "failure"),
                           ("started_at", "2026-10-15T10:03:31Z"),
                           ("completed_at", "2026-10-15T10:04:44Z"), ("app", {"id": 42})):
            def changed(endpoint, result):
                if endpoint.endswith("/check-runs/130"): result[key] = value
                return result
            self.api.mutate = changed
            with self.subTest(key=key):
                self.assertFalse(self.capture().inventory_complete)
                with self.assertRaises(P.ProtocolError): self.verify()
        self.api.mutate = lambda endpoint, value: value
        self.jobs[100][-1]["run_attempt"] = 2
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_changed_final_native_commitment_between_authority_snapshots_denies(self):
        count = 0
        def changed(endpoint, result):
            nonlocal count
            if "/actions/runs/100/attempts/1/jobs?" in endpoint:
                count += 1
                if count >= 2:
                    self.jobs[100][-1]["name"] = self.policy.final_publisher_prefix + "f" * 64
                    result["jobs"][-1] = deepcopy(self.jobs[100][-1])
            return result
        self.api.mutate = changed
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_resigned_whole_receipt_cannot_replace_native_committed_bytes(self):
        aggregate = deepcopy(self.aggregate)
        receipt = aggregate["results"]["shared-host"]["receipt"]
        receipt["completed_at"] = "2026-10-15T10:02:49Z"
        aggregate["results"]["shared-host"]["receipt"] = FIXTURES.signed(receipt, "receipt_digest")
        run = self.capture().observations[0].run
        descriptor_digest = P.descriptor(self.binding, self.plan, self.pp, run)["descriptor_digest"]
        aggregate["descriptor_digest"] = descriptor_digest
        self.artifacts[100] = self.artifacts[100][:1]
        self.artifact(run, "aggregate", FIXTURES.signed(aggregate, "aggregate_digest"))
        with self.assertRaisesRegex(P.ProtocolError, "commitment"): self.verify()


class MetadataFakeApi(FakeApi):
    def json(self, endpoint):
        path = endpoint[len(A.PREFIX):].lstrip("/").split("?", 1)[0]
        trees = {
            "3" * 40: [{"path": "tools", "mode": "040000", "type": "tree", "sha": "4" * 40}],
            "4" * 40: [{"path": "repository-checks", "mode": "040000", "type": "tree", "sha": "5" * 40}],
            "5" * 40: [{"path": "metadata_context.py", "mode": "100644", "type": "blob", "sha": "6" * 40}],
        }
        if path.startswith("git/trees/") and path.rsplit("/", 1)[1] in trees:
            identity = path.rsplit("/", 1)[1]
            self.calls.append(endpoint)
            return self.mutate(endpoint, {"sha": identity, "truncated": False, "tree": deepcopy(trees[identity])})
        return super().json(endpoint)


class MetadataNonproducerTests(unittest.TestCase):
    """Finite native classification fixtures are not hosted qualification proof."""
    def setUp(self):
        self.case = AdapterTests()
        self.case.setUp()
        c = self.case
        c.generation = {**deepcopy(c.generation),
            ".github/workflows/browser-client.yml": {"mode": "100644", "type": "blob", "sha": "1" * 40},
            A.METADATA_WORKFLOW: {"mode": "100644", "type": "blob", "sha": "2" * 40}}
        self.sources = {A.METADATA_SOURCE: {"mode": "100644", "type": "blob", "sha": "6" * 40}}
        c.policy = replace(c.policy, metadata_generations={"metadata-v1": deepcopy(c.generation)},
                           metadata_sources={"metadata-v1": self.sources})
        c.originals[c.binding["base_sha"]] = ("3" * 40, ["7" * 40])
        c.runs[101] = {**deepcopy(c.runs[100]), "id": 101, "check_suite_id": 1101,
            "status": "in_progress", "conclusion": None, "run_started_at": "2026-10-15T10:04:00Z",
            "referenced_workflows": [{"path": A.REPOSITORY + "/" + A.METADATA_WORKFLOW + "@" + c.binding["merge_sha"],
                                      "sha": c.binding["merge_sha"], "ref": c.pp.workflow_ref}]}
        c.jobs[101] = [{"id": 140, "run_id": 101, "run_attempt": 1, "head_sha": c.binding["head_sha"],
            "name": A.METADATA_JOB, "status": "completed", "conclusion": "success",
            "started_at": "2026-10-15T10:04:01Z", "completed_at": "2026-10-15T10:04:20Z",
            "check_run_url": f"https://api.github.com/{A.PREFIX}/check-runs/140",
            "steps": [{"number": 1, "name": A.METADATA_STEP, "status": "completed", "conclusion": "success",
                       "started_at": "2026-10-15T10:04:02Z", "completed_at": "2026-10-15T10:04:19Z"}]}]
        c.artifacts[101] = []
        c.api = MetadataFakeApi(c)
        c.adapter = A.Adapter(c.api)

    def test_completed_native_marker_excludes_active_metadata_run_without_granting_a_result(self):
        c = self.case
        value = c.capture()
        self.assertTrue(value.inventory_complete)
        self.assertEqual([row.run.run_id for row in value.observations], [100])
        self.assertEqual(set(value.metadata_nonproducers), {101})
        marker = value.metadata_nonproducers[101]
        self.assertEqual(marker["candidate"]["merge_sha"], c.binding["merge_sha"])
        self.assertNotIn("verified", marker)
        self.assertNotIn("environment", marker)
        self.assertEqual(c.verify()["run_id"], 100)

    def test_optional_policy_is_off_by_default_and_cannot_be_partial_or_arbitrary(self):
        c = self.case
        c.policy = replace(c.policy, metadata_generations=None, metadata_sources=None)
        self.assertFalse(c.capture().inventory_complete)
        self.setUp(); c = self.case
        for shape in ("missing-sources", "missing-workflow", "extra-source", "alias", "duplicate-pair"):
            policy = deepcopy(c.policy)
            if shape == "missing-sources": policy = replace(policy, metadata_sources=None)
            elif shape == "missing-workflow": policy.metadata_generations["metadata-v1"].pop(A.METADATA_WORKFLOW)
            elif shape == "extra-source": policy.metadata_sources["metadata-v1"]["arbitrary.py"] = self.sources[A.METADATA_SOURCE]
            elif shape == "alias": policy.metadata_sources["metadata-v1"][A.METADATA_SOURCE]["mode"] = "120000"
            else:
                policy.metadata_generations["duplicate"] = deepcopy(policy.metadata_generations["metadata-v1"])
                policy.metadata_sources["duplicate"] = deepcopy(policy.metadata_sources["metadata-v1"])
            with self.subTest(shape=shape), self.assertRaises(P.ProtocolError):
                c.adapter.capture(17, c.plan, policy, now=NOW)

    def test_missing_or_forged_source_marker_cannot_hide_an_unknown_run(self):
        for shape in ("missing-edge", "wrong-edge", "duplicate-edge", "mixed-edge", "wrong-helper", "alias-parent",
                      "wrong-caller", "foreign-head", "wrong-parents", "unknown-generation", "child-target"):
            self.setUp(); c = self.case
            if shape == "missing-edge": c.runs[101]["referenced_workflows"] = []
            elif shape == "wrong-edge": c.runs[101]["referenced_workflows"][0]["sha"] = "8" * 40
            elif shape == "duplicate-edge": c.runs[101]["referenced_workflows"] *= 2
            elif shape == "mixed-edge": c.runs[101]["referenced_workflows"].append({"path": "other/repo/.github/workflows/x.yml@" + c.binding["merge_sha"], "sha": c.binding["merge_sha"], "ref": c.pp.workflow_ref})
            elif shape == "wrong-helper":
                c.api.mutate = lambda e,v: ({**v, "tree": [{**v["tree"][0], "sha": "9" * 40}]} if e.endswith("/git/trees/" + "5" * 40) else v)
            elif shape == "alias-parent":
                c.api.mutate = lambda e,v: ({**v, "tree": [{**v["tree"][0], "mode": "120000", "type": "blob"}]} if e.endswith("/git/trees/" + "4" * 40) else v)
            elif shape == "wrong-caller": c.runs[101]["workflow_id"] = 98
            elif shape == "foreign-head": c.runs[101]["head_repository"]["id"] = 123
            elif shape == "wrong-parents":
                c.api.mutate = lambda e,v: ({**v, "parents": list(reversed(v["parents"]))} if e.endswith("/git/commits/" + c.binding["merge_sha"]) else v)
            elif shape == "unknown-generation": c.generation[A.METADATA_WORKFLOW]["sha"] = "9" * 40
            else: c.binding["base_ref"] = "apple-ios"
            with self.subTest(shape=shape):
                # Direct classification avoids current() rejecting an intentionally
                # malformed live fixture before the source-classification boundary.
                try: marker = c.adapter._metadata_observation(c.runs[101], c.policy, c.binding, NOW)
                except P.ProtocolError: marker = None
                self.assertIsNone(marker)

    def test_native_job_check_step_status_time_and_attempt_must_all_match(self):
        for shape in ("pending-marker", "failed-step", "missing-step", "duplicate-step", "future-time",
                      "wrong-app", "wrong-suite", "check-name", "check-status", "mixed-job", "rerun"):
            self.setUp(); c = self.case
            job = c.jobs[101][0]
            if shape == "pending-marker": job.update(status="in_progress", conclusion=None, completed_at=None)
            elif shape == "failed-step": job["steps"][0]["conclusion"] = "failure"
            elif shape == "missing-step": job["steps"] = []
            elif shape == "duplicate-step": job["steps"] *= 2
            elif shape == "future-time": job["completed_at"] = "2026-10-15T12:00:00Z"
            elif shape == "wrong-app": c.api.mutate = lambda e,v: ({**v, "app": {"id": 42}} if e.endswith("/check-runs/140") else v)
            elif shape == "wrong-suite": c.api.mutate = lambda e,v: ({**v, "check_suite": {"id": 1111}} if e.endswith("/check-runs/140") else v)
            elif shape == "check-name": c.api.mutate = lambda e,v: ({**v, "name": "forged"} if e.endswith("/check-runs/140") else v)
            elif shape == "check-status": c.api.mutate = lambda e,v: ({**v, "conclusion": "failure"} if e.endswith("/check-runs/140") else v)
            elif shape == "mixed-job": job["run_attempt"] = 2
            else: c.runs[101]["run_attempt"] = 2
            with self.subTest(shape=shape): self.assertFalse(c.capture().inventory_complete)

    def test_any_producer_job_or_artifact_including_unrelated_or_duplicate_denies_exclusion(self):
        for shape in ("descriptor", "shared", "publisher", "artifact", "unrelated", "duplicate"):
            self.setUp(); c = self.case
            if shape in {"descriptor", "shared", "publisher"}:
                name = {"descriptor": c.policy.publisher_job, "shared": c.policy.owner_jobs["shared-host"],
                        "publisher": c.policy.final_publisher_prefix + "a" * 64}[shape]
                c.jobs[101].append({**deepcopy(c.jobs[101][0]), "id": 141, "name": name,
                                   "status": "queued", "conclusion": None, "started_at": None, "completed_at": None})
            else:
                c.artifacts[101] = [{"id": 1011, "name": "unrelated" if shape == "unrelated" else "ci-descriptor-101-1"}]
                if shape == "duplicate": c.artifacts[101].append({"id": 1012, "name": "ci-descriptor-101-1"})
            with self.subTest(shape=shape):
                value = c.capture()
                self.assertFalse(value.inventory_complete)
                self.assertNotIn(101, value.metadata_nonproducers)

    def test_metadata_marker_does_not_replace_pending_or_failed_real_producer(self):
        for status, conclusion, expected in (("in_progress", None, "pending"), ("completed", "failure", "failed")):
            self.setUp(); c = self.case
            c.runs[100].update(status=status, conclusion=conclusion)
            self.assertEqual(c.authority()["state"], expected)
            with self.assertRaises(P.ProtocolError): c.verify()

    def test_skipped_metadata_edge_preserves_ordinary_proof_and_failure_before_shared_work(self):
        c = self.case
        c.runs[100]["referenced_workflows"].extend(deepcopy(c.runs[101]["referenced_workflows"]))
        skipped = {**deepcopy(c.jobs[101][0]), "id": 142, "run_id": 100,
                   "status": "completed", "conclusion": "skipped", "started_at": None,
                   "completed_at": None, "steps": [],
                   "check_run_url": f"https://api.github.com/{A.PREFIX}/check-runs/142"}
        c.jobs[100].append(skipped)
        self.assertEqual(c.verify()["run_id"], 100)
        # An ordinary failure after its descriptor but before shared execution
        # still classifies through the producer path, never as a metadata run.
        c.runs[100].update(status="completed", conclusion="failure")
        c.jobs[100] = [job for job in c.jobs[100] if job["name"] in {c.policy.publisher_job, A.METADATA_JOB}]
        self.assertEqual(c.authority()["state"], "failed")
        with self.assertRaises(P.ProtocolError): c.verify()

    def test_metadata_jobs_and_artifacts_are_rechecked_inside_each_capture(self):
        for shape in ("producer-job", "artifact"):
            self.setUp(); c = self.case
            reads = 0
            def mutate(endpoint, value):
                nonlocal reads
                suffix = "/actions/runs/101/attempts/1/jobs?" if shape == "producer-job" else "/actions/runs/101/artifacts?"
                if suffix in endpoint:
                    reads += 1
                    if reads == 2:
                        field = "jobs" if shape == "producer-job" else "artifacts"
                        item = {**deepcopy(c.jobs[101][0]), "id": 141, "name": c.policy.owner_jobs["shared-host"]} if field == "jobs" else {"id": 1011, "name": "ci-aggregate-101-1"}
                        value[field].append(item); value["total_count"] += 1
                return value
            c.api.mutate = mutate
            with self.subTest(shape=shape): self.assertFalse(c.capture().inventory_complete)

    def test_metadata_snapshot_must_also_match_across_aggregate_verification(self):
        c = self.case
        reads = 0
        def mutate(endpoint, value):
            nonlocal reads
            if "/actions/runs/101/attempts/1/jobs?" in endpoint:
                reads += 1
                if reads >= 3: value["jobs"][0]["steps"][0]["number"] = 2
            return value
        c.api.mutate = mutate
        with self.assertRaisesRegex(P.ProtocolError, "metadata non-producer inventory changed"):
            c.verify()

    def test_separate_codeql_caller_uses_typed_two_workflow_policy_without_producer_facts(self):
        c = self.case
        path = ".github/workflows/codeql.yml"
        c.generation[path] = {"mode": "100644", "type": "blob", "sha": "9" * 40}
        policy = A.MetadataPolicy(77, path, {"metadata-v1": {p: c.generation[p] for p in (path, A.METADATA_WORKFLOW)}},
                                  {"metadata-v1": self.sources})
        c.runs[101].update(path=path, workflow_id=77)
        marker = c.adapter.metadata_observation(c.runs[101], c.binding, policy, now=NOW)
        self.assertEqual(marker["generation"], "metadata-v1")
        c.jobs[101].append({**deepcopy(c.jobs[101][0]), "id": 141, "name": "CodeQL (python)", "status": "queued", "conclusion": None})
        self.assertIsNone(c.adapter.metadata_observation(c.runs[101], c.binding, policy, now=NOW))


class IntegratedFakeApi(FakeApi):
    """Closed PR metadata survives deletion; no live topic/PR merge ref exists."""
    def detail(self, number):
        case, binding = self.case, self.case.binding
        if number != 17:
            if number not in case.associated_details:
                raise A.ApiError("full associated PR is unavailable")
            return deepcopy(case.associated_details[number])
        return {"id": 1700, "number": 17, "state": "closed", "merged": True,
                "merge_commit_sha": case.integrated, "merged_at": case.merged_at, "closed_at": case.merged_at,
                **{side: {"repo": {"id": 1319052603, "full_name": A.REPOSITORY},
                          "ref": binding[side + "_ref"], "sha": binding[side + "_sha"]}
                   for side in ("base", "head")}}

    def integrated_pr(self, number):
        endpoint = A.PREFIX + f"/pulls/{number}"
        self.calls.append(endpoint)
        self.case.legacy_pr_calls.append(number)
        return self.mutate(endpoint, self.detail(number))

    def json(self, endpoint):
        case, binding = self.case, self.case.binding
        path = endpoint[len(A.PREFIX):].lstrip("/").split("?", 1)[0]
        query = parse_qs(urlsplit(endpoint).query)
        if path == "pulls/17":
            result = self.detail(17)
            del result["merge_commit_sha"]
        elif path == "commits/" + case.integrated + "/pulls":
            page = int(query["page"][0])
            result = deepcopy(case.associated[(page - 1) * 100:page * 100])
            for row in result:
                detail = self.detail(row["number"]) if row["number"] in case.associated_details else self.detail(17)
                for side in ("base", "head"):
                    row.setdefault(side, deepcopy(detail[side]))
        elif path.startswith("branches/"):
            self._require(unquote(path[len("branches/"):]) == binding["base_ref"], endpoint)
            result = {"name": binding["base_ref"], "protected": True, "commit": {"sha": case.integrated}}
        elif path.startswith("git/ref/"):
            ref = unquote(path[len("git/ref/"):])
            self._require(ref in {"heads/main", "heads/" + binding["base_ref"]}, endpoint)
            revision = case.integrated if ref == "heads/" + binding["base_ref"] else "6" * 40
            result = {"ref": "refs/" + ref, "object": {"type": "commit", "sha": revision}}
        elif path == "git/commits/" + case.integrated:
            result = {"sha": case.integrated, "tree": {"sha": binding["merge_tree"]},
                      "parents": [{"sha": revision} for revision in binding["merge_parents"]]}
        elif path == "actions/workflows/" + str(case.push["workflow_id"]):
            result = {"id": case.push["workflow_id"], "path": case.push["path"]}
        elif path in {"actions/runs/500", "actions/runs/500/attempts/1"}:
            result = deepcopy(case.push)
        elif path == "check-suites/1500":
            result = {"id": 1500, "head_sha": case.integrated,
                      "repository": {"id": 1319052603, "full_name": A.REPOSITORY}, "app": {"id": 15368}}
        else:
            return super().json(endpoint)
        self.calls.append(endpoint)
        return self.mutate(endpoint, deepcopy(result))

    def _require(self, condition, endpoint):
        if not condition: self._unexpected(endpoint)


class IntegratedSourceTests(unittest.TestCase):
    def setUp(self):
        self.case = AdapterTests(methodName="runTest")
        self.case.setUp()
        self.case.integrated, self.case.merged_at = "9" * 40, "2026-10-15T10:04:50Z"
        self.case.associated = [{"id": 1700, "number": 17, "state": "closed"}]
        self.case.associated_details, self.case.legacy_pr_calls = {}, []
        self.case.push = {"id": 500, "workflow_id": 350930890, "check_suite_id": 1500,
                          "path": ".github/workflows/parent-qualification.yml", "event": "push",
                          "head_sha": self.case.integrated, "head_branch": "main", "run_attempt": 1,
                          "run_started_at": "2026-10-15T10:04:51Z", "status": "in_progress", "conclusion": None,
                          **{key: {"id": 1319052603, "full_name": A.REPOSITORY}
                             for key in ("repository", "head_repository")}}
        self.case.runs[100]["pull_requests"] = []
        self.api = IntegratedFakeApi(self.case)
        self.adapter = A.Adapter(self.api)

    def capture(self):
        return self.adapter.capture_integrated(500, self.case.plan, self.case.policy, now=NOW)

    def verify(self, *, context=None, clock=lambda: NOW):
        return self.adapter.verify_integrated(500, self.case.plan, self.case.policy,
                                              {"shared-host": context or self.case.context}, clock=clock)

    def add_association(self, *, number=18, state="open", merged=False, merge="6" * 40):
        detail = self.api.detail(17)
        detail.update(id=number * 100, number=number, state=state, merged=merged, merge_commit_sha=merge,
                      merged_at=self.case.merged_at if merged else None,
                      closed_at=self.case.merged_at if state == "closed" else None)
        detail["base"].update(ref="android-phone", sha=self.case.integrated)
        detail["head"].update(ref="sync/android-phone/example", sha="7" * 40)
        self.case.associated_details[number] = detail
        self.case.associated.append({key: deepcopy(detail[key]) for key in ("id", "number", "state", "base", "head")})

    def test_deleted_topic_lookup_preserves_original_candidate_receipt_and_expiry(self):
        with patch.object(P.execution, "execute", side_effect=AssertionError("no candidate execution")):
            snapshot, result = self.capture(), self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(snapshot.binding, self.case.binding)
        self.assertEqual(result["source_chain"]["producer_commit"], self.case.binding["merge_sha"])
        self.assertEqual(result["integration"]["commit"], self.case.integrated)
        self.assertNotEqual(result["integration"]["commit"], snapshot.binding["merge_sha"])
        self.assertEqual(result["expires_at"], self.case.aggregate["expires_at"])
        self.assertEqual(result["qualified_at"], self.case.aggregate["qualified_at"])
        self.assertFalse(any("commits/refs/pull/" in endpoint or
                             "/git/ref/heads/" + self.case.binding["head_ref"] in endpoint
                             for endpoint in self.api.calls))
        self.assertTrue(all(endpoint.startswith(A.PREFIX) for endpoint in self.api.calls))
        self.assertTrue(self.case.legacy_pr_calls, "actual merged SHA requires the explicitly versioned full PR endpoint")

    def test_original_source_context_is_never_aliased_to_integrated_commit(self):
        with self.assertRaises(P.ProtocolError):
            self.verify(context=replace(self.case.context, candidate_commit=self.case.integrated))

    def test_current_pending_consumer_is_provenance_not_required_completed_test_proof(self):
        for status, conclusion in (("queued", None), ("in_progress", None), ("completed", "success")):
            self.case.push.update(status=status, conclusion=conclusion)
            with self.subTest(status=status):
                result = self.verify()
                self.assertTrue(result["verified"])
                self.assertEqual(result["integration"]["push_status"], status)
                self.assertEqual(result["run_id"], 100, "proof belongs to original producer, not consumer500")
        for conclusion in ("failure", "cancelled", "timed_out", "skipped"):
            self.case.push.update(status="completed", conclusion=conclusion)
            with self.subTest(conclusion=conclusion), self.assertRaises(P.ProtocolError): self.capture()

    def test_open_contract_still_rejects_missing_run_pr_association(self):
        self.assertFalse(self.case.capture().inventory_complete)
        with self.assertRaises(P.ProtocolError): self.case.verify()

    def test_all_seven_exact_registered_protected_push_profiles_capture(self):
        for workflow_id, (path, branches) in A.PROTECTED_PUSH_WORKFLOWS.items():
            for target in sorted(branches):
                self.case.binding["base_ref"] = target
                self.case.push.update(workflow_id=workflow_id, path=path, head_branch=target)
                with self.subTest(target=target):
                    # This is source capture only: changed target descriptors
                    # deliberately cannot become reusable proof by mutation.
                    binding, refs = self.adapter._integrated_current(500, 15368, NOW)
                    self.assertEqual(binding["base_ref"], target)
                    self.assertEqual(refs["target"], self.case.integrated)

    def test_push_event_current_protection_source_app_and_first_attempt_are_required(self):
        cases = (("event", "pull_request"), ("event", "workflow_dispatch"), ("run_attempt", 2),
                 ("workflow_id", 42), ("path", ".github/workflows/other.yml"),
                 ("head_branch", "topic"), ("head_sha", "f" * 40),
                 ("status", "queued-without-contract"), ("conclusion", "failure"))
        original = deepcopy(self.case.push)
        for key, value in cases:
            self.case.push = {**deepcopy(original), key: value}
            with self.subTest(key=key, value=value), self.assertRaises(P.ProtocolError): self.capture()
        self.case.push = original
        for mode in ("fork", "head-fork", "app", "suite", "unprotected", "branch-tip", "independent-ref", "workflow"):
            def changed(endpoint, result):
                if "/actions/runs/500" in endpoint and mode in {"fork", "head-fork"}:
                    result["repository" if mode == "fork" else "head_repository"]["id"] = 42
                elif endpoint.endswith("/check-suites/1500"):
                    if mode == "app": result["app"]["id"] = 42
                    elif mode == "suite": result["head_sha"] = "f" * 40
                elif endpoint.endswith("/branches/main"):
                    if mode == "unprotected": result["protected"] = False
                    elif mode == "branch-tip": result["commit"]["sha"] = "f" * 40
                elif mode == "independent-ref" and endpoint.endswith("/git/ref/heads/main"):
                    result["object"]["sha"] = "f" * 40
                elif mode == "workflow" and endpoint.endswith("/actions/workflows/350930890"):
                    result["path"] = ".github/workflows/other.yml"
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.capture()

    def test_unique_actual_merged_same_fork_pr_and_exact_ordered_parents_are_required(self):
        for mode in ("unmerged", "open", "foreign-head", "foreign-base", "wrong-pr", "wrong-merge",
                     "wrong-base", "wrong-head", "target", "parents", "squash", "rebase", "different-tree"):
            def changed(endpoint, result):
                if endpoint.endswith("/pulls/17"):
                    if mode == "unmerged": result["merged"] = False
                    elif mode == "open": result["state"] = "open"
                    elif mode in {"foreign-head", "foreign-base"}: result[mode.split("-")[1]]["repo"]["id"] = 42
                    elif mode == "wrong-pr": result["id"] = 1701
                    elif mode == "wrong-merge": result["merge_commit_sha"] = "f" * 40
                    elif mode in {"wrong-base", "wrong-head"}: result[mode.split("-")[1]]["sha"] = "f" * 40
                    elif mode == "target": result["base"]["ref"] = "android-main"
                elif endpoint.endswith("/git/commits/" + self.case.integrated):
                    if mode == "parents": result["parents"].reverse()
                    elif mode == "squash": result["parents"] = result["parents"][:1]
                    elif mode == "rebase": result["parents"].append({"sha": "f" * 40})
                    elif mode == "different-tree": result["tree"]["sha"] = "f" * 40
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.capture()

    def test_association_inventory_missing_multiple_duplicate_or_unbounded_deny(self):
        original = deepcopy(self.case.associated)
        for items in ([], original + [{**original[0], "id": 1701, "number": 18}], original + original,
                      [{**original[0], "id": index + 1, "number": index + 1} for index in range(1000)]):
            self.case.associated = items
            with self.subTest(count=len(items)), self.assertRaises(P.ProtocolError): self.capture()
        self.case.associated = original
        self.api.mutate = lambda endpoint, value: ({"items": value} if "/pulls?" in endpoint else value)
        with self.assertRaises(P.ProtocolError): self.capture()

    def test_known_open_and_merged_downstream_associations_do_not_supply_or_obstruct_introducer(self):
        self.add_association()
        self.add_association(number=19, state="closed", merged=True, merge="8" * 40)
        snapshot = self.capture()
        self.assertEqual([item["classification"] for item in snapshot.references["associated_prs"]],
                         ["introducer", "known-nonintroducer", "known-nonintroducer"])
        self.assertEqual(self.verify()["run_id"], 100)
        self.assertEqual(set(self.case.legacy_pr_calls), {17, 18, 19})
        self.assertFalse(any("refs/pull/18" in endpoint or "refs/pull/19" in endpoint for endpoint in self.api.calls))
        self.case.associated = self.case.associated[1:]
        with self.assertRaisesRegex(P.ProtocolError, "introducer PR is missing"): self.capture()

    def test_multiple_or_contradictory_introducers_and_unknown_associations_deny(self):
        for mode in ("second-introducer", "open-claims-integration", "unknown-detail", "foreign", "conflicting-summary"):
            self.case.associated = [{"id": 1700, "number": 17, "state": "closed"}]
            self.case.associated_details = {}
            self.add_association(state="closed" if mode == "second-introducer" else "open",
                                 merged=mode == "second-introducer",
                                 merge=self.case.integrated if mode in {"second-introducer", "open-claims-integration"}
                                 else "6" * 40)
            if mode == "unknown-detail": del self.case.associated_details[18]
            elif mode == "foreign": self.case.associated_details[18]["head"]["repo"]["id"] = 42
            elif mode == "conflicting-summary": self.case.associated[1]["head"]["sha"] = "f" * 40
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.capture()

    def test_missing_legacy_merge_field_and_mismatched_full_summary_identity_deny(self):
        for mode in ("missing-merge", "missing-merged", "state", "base", "head", "summary-merge"):
            def changed(endpoint, result):
                if endpoint.endswith("/pulls/17"):
                    if mode == "missing-merge": del result["merge_commit_sha"]
                    elif mode == "missing-merged": del result["merged"]
                    elif mode == "state": result["state"] = "open"
                    elif mode in {"base", "head"}: result[mode]["sha"] = "f" * 40
                elif mode == "summary-merge" and "/pulls?" in endpoint:
                    result[0]["merge_commit_sha"] = "f" * 40
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.capture()

    def test_recorded_seven_real_api_shapes_authenticate_current_introducers(self):
        # Actual minimal field observations, 2026-10-16. Summaries and 2026
        # full PRs omit merge_commit_sha; only explicit 2022 full PRs supply it.
        # These fake API source snapshots are not hosted qualification receipts.
        records = (
            ("main", 1321, 4883606325, "727c6e2b9ec33dbd343740f5daaaa92196e53120",
             "ad636dc97fe7e213c7ff626dd5b5cf7873a7d4c2", "25ec68fbfa00768828f82ee78a56a8fdeea295fc",
             "fix/main/ci-sandbox-host-snapshot-qualification-20261016", "2026-10-16T05:16:32Z"),
            ("apple-main", 1261, 4869813471, "f7f6c47aff64213deb46c2d0b834b6df2cc93b06",
             "20f9c44665bc08e9e924d2da1d0c3429d8ab0c23", "a9b600cabc5a3d85e1b107e1734545847c53cb5e",
             "reconcile/apple/ios-kit-fetch-fixture-policy-20261015", "2026-10-15T07:47:02Z"),
            ("apple-ios", 1300, 4878868180, "2fc894a0605103843b36653f250f854714a963ee",
             "3941e0861eb7995b9cfa6e4116e9f70bc25d9837", "5ea4f920e01be7c48650affcda75b6ec5e0d0efa",
             "fix/ios/host-only-qualification-20261015", "2026-10-15T20:05:31Z"),
            ("android-main", 1272, 4871975509, "664fb0e83dd80f1557571471d2a8c48a86d1b2ee",
             "17e3e529c4a82fef8057558206cb9d4ceed680bd", "d753ff8ef163207c7466660d4872b0a71c20bb93",
             "fix/android/common-qml-reporter-fixture-isolation-20261015", "2026-10-15T10:58:30Z"),
            ("android-phone", 1286, 4874106309, "a89d21db26a30aa1cc6627f40708c4b2801fc480",
             "277bad9119c9ee16f4bbb3038cedeb6625741d34", "2338d3547fec0a2e3a337bc51775658cb17019fd",
             "fix/android-phone/adopted-history-pr-1198-319a59f04eae", "2026-10-15T13:46:39Z"),
            ("android-vr", 1270, 4871580861, "2199dc03b796b14d69973b50cb538e3779866306",
             "d2f09ed8872f48dd81d157ed3881db74ae9795d2", "4895b4a4d10b9a023ff921ed6b4134e85369370a",
             "reconcile/android-vr/shared-reporting-current-parent-20261015", "2026-10-15T10:26:26Z"),
            ("android-vr-pico", 1276, 4872457039, "410847ff312553de81f9f8ff7e32029b22495603",
             "5505cf999978c07a4d42de825362270f9282d097", "abb558cde0fd9b40370f643cc61a57a8372246b7",
             "fix/android-pico/activity-focus-current-parent-20261015", "2026-10-15T11:44:51Z"),
        )
        for target, number, identity, revision, base, head, head_ref, merged in records:
            self.case.integrated, self.case.merged_at = revision, merged
            self.case.binding.update(base_ref=target, base_sha=base, head_sha=head, head_ref=head_ref,
                                     merge_parents=[base, head])
            detail = {"id": identity, "number": number, "state": "closed", "merged": True,
                      "merge_commit_sha": revision, "merged_at": merged, "closed_at": merged,
                      **{side: {"ref": ref, "sha": sha, "repo": {"id": 1319052603, "full_name": A.REPOSITORY}}
                         for side, ref, sha in (("base", target, base), ("head", head_ref, head))}}
            self.case.associated_details = {number: detail}
            self.case.associated = [{key: deepcopy(detail[key]) for key in
                                     ("id", "number", "state", "base", "head", "merged_at", "closed_at")}]
            workflow_id = next(identity for identity, (_, targets) in A.PROTECTED_PUSH_WORKFLOWS.items()
                               if target in targets)
            self.case.push.update(workflow_id=workflow_id, path=A.PROTECTED_PUSH_WORKFLOWS[workflow_id][0],
                                  head_branch=target, head_sha=revision, run_started_at="2026-10-16T05:32:01Z")
            with self.subTest(target=target):
                binding, refs = self.adapter._integrated_current(500, 15368, NOW.replace(day=17))
                self.assertEqual(binding["pull_request"], number)
                self.assertEqual(refs["integration"]["commit"], revision)
                self.assertEqual(refs["associated_prs"][0]["classification"], "introducer")
                self.assertNotIn("merge_commit_sha", self.case.associated[0])

    def test_known_nonintroducer_inventory_is_also_bookended(self):
        self.add_association()
        count = 0
        def changed(endpoint, result):
            nonlocal count
            if "/commits/" in endpoint and "/pulls?" in endpoint:
                count += 1
                if count >= 2:
                    self.case.associated_details[18]["head"]["sha"] = "f" * 40
                    result[1]["head"]["sha"] = "f" * 40
            return result
        self.api.mutate = changed
        with self.assertRaisesRegex(P.ProtocolError, "current refs changed"): self.capture()

    def test_missing_original_ref_unknown_chain_or_conflicting_run_association_deny(self):
        for mode in ("missing", "ref", "sha", "foreign", "wrong-pr", "multiple-pr"):
            def changed(endpoint, result):
                if "/actions/runs/100" in endpoint and "referenced_workflows" in result:
                    if mode == "missing": result["referenced_workflows"] = []
                    elif mode == "ref": result["referenced_workflows"][0]["ref"] = "refs/heads/main"
                    elif mode == "sha": result["referenced_workflows"][0]["sha"] = self.case.integrated
                    elif mode == "foreign": result["repository"]["id"] = 42
                    elif mode == "wrong-pr": result["pull_requests"] = [{"number": 18}]
                    else: result["pull_requests"] = [{"number": 17}, {"number": 18}]
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.verify()

    def test_partial_capped_or_changed_original_run_inventory_cannot_choose_old_green(self):
        for mode in ("partial", "capped", "changed"):
            count = 0
            def changed(endpoint, result):
                nonlocal count
                if "/actions/workflows/99/runs?" in endpoint:
                    count += 1
                    if mode == "partial": result["total_count"] = 2
                    elif mode == "capped": result["total_count"] = 1000
                    elif count >= 2:
                        result["workflow_runs"] = []
                        result["total_count"] = 0
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.verify()

    def test_two_distinct_original_candidates_with_same_tree_and_parents_are_ambiguous(self):
        original = self.capture().observations[0].run
        self.case.add_run(replace(original, run_id=101,
                                 publisher=replace(original.publisher, job_id=111),
                                 owners={name: replace(job, job_id=121) for name, job in original.owners.items()},
                                 final_publisher=replace(original.final_publisher,
                                                         job=replace(original.final_publisher.job, job_id=131))),
                          descriptor=False)
        alternate = "f" * 40
        self.case.originals[alternate] = (self.case.binding["merge_tree"], self.case.binding["merge_parents"][:])
        self.case.runs[101]["referenced_workflows"][0].update(
            sha=alternate, path=A.REPOSITORY + "/" + self.case.pp.workflow_path + "@" + alternate)
        with self.assertRaisesRegex(P.ProtocolError, "ambiguous"): self.capture()

    def test_known_other_original_is_classified_without_its_artifacts_but_unknown_is_not(self):
        original = self.capture().observations[0].run
        self.case.add_run(replace(original, run_id=101, conclusion="failure"), descriptor=False)
        self.case.originals["f" * 40] = ("8" * 40, ["7" * 40, self.case.binding["head_sha"]])
        self.case.runs[101]["referenced_workflows"][0].update(
            sha="f" * 40, path=A.REPOSITORY + "/" + self.case.pp.workflow_path + "@" + "f" * 40)
        snapshot = self.capture()
        self.assertTrue(snapshot.inventory_complete)
        self.assertEqual(set(snapshot.other_candidates), {101})
        self.assertTrue(self.verify()["verified"])
        self.assertFalse(any("/runs/101/artifacts" in endpoint for endpoint in self.api.calls))
        self.case.runs[101]["referenced_workflows"] = []
        self.assertFalse(self.capture().inventory_complete)
        with self.assertRaises(P.ProtocolError): self.verify()

    def test_newer_pending_failed_cancelled_or_rerun_source_never_uses_older_green(self):
        original = self.capture().observations[0].run
        for status, conclusion, attempt in (("queued", None, 1), ("completed", "failure", 1),
                                             ("completed", "cancelled", 1), ("completed", "success", 2)):
            later = replace(original, run_id=101, attempt=attempt, latest_attempt=attempt,
                            status=status, conclusion=conclusion, attempt_started_at="2026-10-15T10:01:00Z",
                            publisher=None, owners={}, final_publisher=None)
            if attempt == 1:
                later = replace(later, publisher=replace(original.publisher, job_id=111,
                                started_at="2026-10-15T10:01:00Z", completed_at="2026-10-15T10:01:30Z"))
            self.case.add_run(later, descriptor=attempt == 1)
            with self.subTest(status=status, attempt=attempt):
                snapshot = self.capture()
                authority = P.select_authority(snapshot.observations, snapshot.binding, self.case.plan, self.case.pp,
                                               inventory_complete=snapshot.inventory_complete, now=NOW)
                self.assertEqual(authority["state"], "unresolved" if attempt == 2 else
                                 "pending" if status == "queued" else "failed")
                with self.assertRaises(P.ProtocolError): self.verify()
            del self.case.runs[101]; del self.case.jobs[101]; del self.case.artifacts[101]

    def test_current_push_pr_association_protection_and_default_are_bookended(self):
        for mode in ("pr", "association", "protection", "target", "attempt", "run-status"):
            counts = {}
            def changed(endpoint, result):
                counts[endpoint] = counts.get(endpoint, 0) + 1
                if counts[endpoint] >= 2:
                    if mode == "pr" and endpoint.endswith("/pulls/17"): result["head"]["sha"] = "f" * 40
                    elif mode == "association" and "/commits/" in endpoint and "/pulls?" in endpoint:
                        result.append({**result[0], "id": 1701, "number": 18})
                    elif mode == "protection" and endpoint.endswith("/branches/main"): result["protected"] = False
                    elif mode == "target" and endpoint.endswith("/git/ref/heads/main"):
                        result["object"]["sha"] = "f" * 40
                    elif mode == "attempt" and endpoint.endswith("/actions/runs/500"): result["run_attempt"] = 2
                    elif mode == "run-status" and "/actions/runs/500" in endpoint:
                        result.update(status="completed", conclusion="success")
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.verify()

    def test_default_ref_is_bookended_independently_of_child_target(self):
        self.case.binding["base_ref"] = "android-main"
        self.case.push["head_branch"] = "android-main"
        count = 0
        def changed(endpoint, result):
            nonlocal count
            if endpoint.endswith("/git/ref/heads/main"):
                count += 1
                if count >= 2: result["object"]["sha"] = "f" * 40
            return result
        self.api.mutate = changed
        with self.assertRaisesRegex(P.ProtocolError, "current refs changed"): self.capture()

    def test_original_evidence_must_finish_before_merge_and_keep_original_expiry(self):
        for merged in ("2026-10-15T10:03:00Z", "2026-10-15T10:04:10Z", "2026-10-15T10:04:40Z"):
            self.case.merged_at = merged
            with self.subTest(merged=merged), self.assertRaisesRegex(P.ProtocolError, "before integration"):
                self.verify()
        self.case.merged_at = "2026-10-15T10:04:50Z"
        later = NOW.replace(hour=12)
        with self.assertRaises(P.ProtocolError): self.verify(clock=lambda: later)

    def test_merge_and_push_chronology_and_latest_attempt_bookends_are_required(self):
        for mode in ("future-merge", "early-close", "early-push", "latest-attempt", "attempt-head"):
            def changed(endpoint, result):
                if endpoint.endswith("/pulls/17"):
                    if mode == "future-merge": result["merged_at"] = "2026-10-15T10:06:00Z"
                    elif mode == "early-close": result["closed_at"] = "2026-10-15T10:04:40Z"
                elif "/actions/runs/500" in endpoint:
                    if mode == "early-push": result["run_started_at"] = "2026-10-15T10:04:40Z"
                    elif mode == "latest-attempt" and endpoint.endswith("/actions/runs/500"):
                        result["run_attempt"] = 2
                    elif mode == "attempt-head" and endpoint.endswith("/attempts/1"):
                        result["head_sha"] = "f" * 40
                return result
            self.api.mutate = changed
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError): self.capture()


class ReadOnlyBoundaryTests(unittest.TestCase):
    def blob(self, content=b'{"holds":{}}\n'):
        identity=hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
        value={'sha':identity,'size':len(content),'encoding':'base64',
            'content':base64.b64encode(content).decode()+'\n',
            'url':'https://api.github.com/'+A.PREFIX+'/git/blobs/'+identity,'node_id':'fixture-node'}
        return identity,value

    def read_blob(self, identity, value, **options):
        raw=value if isinstance(value,bytes) else json.dumps(value).encode()
        with patch.object(A.GitHubReadOnly,'_request',return_value=raw) as request:
            result=A.GitHubReadOnly().immutable_blob(identity,**options)
        request.assert_called_once_with(A.PREFIX+'/git/blobs/'+identity,100_000)
        return result

    def test_immutable_blob_authenticates_exact_bytes_and_fixed_cli_endpoint(self):
        content=b'{"holds":{}}\n'
        identity,value=self.blob(content)
        self.assertEqual(self.read_blob(identity,value,maximum=len(content)),content)
        real,commands=subprocess.Popen,[]
        raw=json.dumps(value).encode()
        def child(command,**kwargs):
            commands.append(command)
            return real([sys.executable,'-c','import sys;sys.stdout.buffer.write('+repr(raw)+')'],**kwargs)
        with patch.object(A.shutil,'which',return_value='/usr/bin/gh'), \
             patch.object(A.subprocess,'Popen',side_effect=child):
            self.assertEqual(A.GitHubReadOnly().immutable_blob(identity),content)
        self.assertEqual(len(commands),1)
        self.assertEqual(commands[0][-1],A.PREFIX+'/git/blobs/'+identity)
        self.assertIn('GET',commands[0]);self.assertIn('github.com',commands[0])
        self.assertIn('X-GitHub-Api-Version: 2026-03-10',commands[0])

    def test_immutable_blob_has_no_path_ref_version_or_larger_limit_override(self):
        identity,_=self.blob()
        for invalid in (None,'0'*40,'A'*40,'a'*39,'a'*40+'?ref=main','../other',
                A.PREFIX+'/git/blobs/'+'a'*40,'refs/heads/main'):
            with self.subTest(identity=invalid),patch.object(A.GitHubReadOnly,'_request') as request, \
                 self.assertRaises(A.ApiError):A.GitHubReadOnly().immutable_blob(invalid)
            request.assert_not_called()
        for maximum in (True,False,None,'64000',0,-1,64_001,20_000_000,1.0):
            with self.subTest(maximum=maximum),patch.object(A.GitHubReadOnly,'_request') as request, \
                 self.assertRaises(A.ApiError):A.GitHubReadOnly().immutable_blob(identity,maximum)
            request.assert_not_called()
        for options in ({'path':'policy.json'},{'ref':'main'},{'endpoint':'other'},{'api_version':'2022-11-28'}):
            with self.subTest(options=options),patch.object(A.GitHubReadOnly,'_request') as request, \
                 self.assertRaises(TypeError):A.GitHubReadOnly().immutable_blob(identity,**options)
            request.assert_not_called()

    def test_immutable_blob_rejects_rebound_content_identity_metadata_or_size(self):
        identity,original=self.blob()
        variants=[{'sha':'a'*40},{'url':'https://api.github.com/repos/overte-org/overte/git/blobs/'+identity},
            {'url':'https://api.github.com/'+A.PREFIX+'/git/blobs/'+'a'*40},
            {'encoding':'utf-8'},{'size':True},{'size':-1},{'size':original['size']-1},
            {'size':64_001},{'content':[]},{'node_id':{}},{'unexpected':'field'},
            {'content':base64.b64encode(b'altered').decode(),'size':len(b'altered')}]
        for change in variants:
            with self.subTest(change=next(iter(change))),self.assertRaises(A.ApiError):
                self.read_blob(identity,{**original,**change})
        for value in (None,[],{},'unknown'):
            with self.subTest(shape=value),self.assertRaises(A.ApiError):self.read_blob(identity,value)

    def test_immutable_blob_accepts_only_strict_canonical_base64_with_api_lf_wrapping(self):
        identity,original=self.blob(b'a')
        self.assertEqual(self.read_blob(identity,{**original,'content':'YQ==\n'}),b'a')
        for content in ('YR==','YQ=','YQ===','YQ==!','YQ== ','YQ==\r\n','\u20ac', 'YQ==YQ=='):
            with self.subTest(content=content),self.assertRaises(A.ApiError):
                self.read_blob(identity,{**original,'content':content})

    def test_immutable_blob_bounds_raw_json_and_decoded_bytes_and_rejects_duplicate_fields(self):
        identity,value=self.blob()
        for raw in (b' '*100_001,b'{"size":1,'+json.dumps(value).encode()[1:],
                b'{"content":"YQ==",'+json.dumps(value).encode()[1:],b'{"size":NaN}'):
            with self.subTest(length=len(raw)),self.assertRaises(A.ApiError):self.read_blob(identity,raw)
        for size in (64_000,64_001):
            content=b'a'*64_001
            with self.subTest(size=size),self.assertRaises(A.ApiError):
                self.read_blob(identity,{**value,'size':size,'content':base64.b64encode(content).decode()})
        with self.assertRaises(A.ApiError):self.read_blob(identity,value,maximum=value['size']-1)

    def test_legacy_pr_version_is_explicit_and_unavailable_for_other_endpoints(self):
        real, commands = subprocess.Popen, []
        def child(command, **kwargs):
            commands.append(command)
            return real([sys.executable, "-c", "print('{}')"], **kwargs)
        with patch.object(A.shutil, "which", return_value="/usr/bin/gh"), patch.object(
                A.subprocess, "Popen", side_effect=child):
            api = A.GitHubReadOnly()
            self.assertEqual(api.integrated_pr(17), {})
            self.assertEqual(api.json(A.PREFIX + "/pulls/17"), {})
        self.assertIn("X-GitHub-Api-Version: 2022-11-28", commands[0])
        self.assertIn("X-GitHub-Api-Version: 2026-03-10", commands[1])
        self.assertTrue(all(command[-1] == A.PREFIX + "/pulls/17" and "GET" in command for command in commands))
        for endpoint, version in ((A.PREFIX + "/actions/runs/100", "2022-11-28"),
                                  (A.PREFIX + "/pulls/17?other=1", "2022-11-28"),
                                  (A.PREFIX + "/pulls/17", "unknown")):
            with patch.object(A.subprocess, "Popen") as process, self.assertRaises(A.ApiError):
                api._request(endpoint, 1000, api_version=version)
            process.assert_not_called()
        with patch.object(A.GitHubReadOnly, "_request", return_value=b'{"duplicate":1,"duplicate":2}'), \
                self.assertRaises(A.ApiError):
            A.GitHubReadOnly().integrated_pr(17)

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


class MainConsumerTests(unittest.TestCase):
    """Native push + actual protocol/API validator; no workload/E probes."""
    def setUp(self):
        import postmerge
        from types import SimpleNamespace
        self.module = postmerge
        self.real_host_policy = postmerge.producer._host_policy
        self.real_package = self.real_host_policy().package_policy()
        self.real_full_tree = postmerge.inputs.full_tree
        self.real_selection_profile = getattr(postmerge.producer, 'selection_profile', None)
        fixture = IntegratedSourceTests(); fixture.setUp()
        self.case, self.api, self.adapter = fixture.case, fixture.api, fixture.adapter
        self.case.originals[self.case.binding['base_sha']] = ('6'*40, ['7'*40])
        old = FIXTURES.ProducerProtocolTests(); old.setUp()
        self.registry = old.registry
        self.tree = deepcopy(old.tree)
        generations = json.loads((postmerge.ROOT / '.github/package-workflow-generations.json').read_text())['generations']
        self.generation_name = getattr(self,'generation_name','protected-producer-metadata-ci-v1')
        generation = next(item for item in generations if item['name'] == self.generation_name)
        self.generations = {item['name']:deepcopy(item['workflows']) for item in generations}
        if self.generation_name == 'protected-producer-metadata-ci-v1':
            # Derive the actual prospective native tuple from its reviewed
            # sources. A stale hard-coded historical tuple must not hide a
            # missing admission of the installed producer generation.
            sources={'.github/workflows/project-tests.yml':postmerge.producer.TEMPLATE,
                '.github/workflows/repository-checks.yml':'tools/repository-checks/workflows/producers/repository-checks.yml',
                '.github/workflows/parent-qualification.yml':postmerge.TEMPLATE,
                '.github/workflows/sync-validation.yml':'.github/workflows/sync-validation.yml',
                '.github/workflows/browser-client.yml':'.github/workflows/browser-client.yml',
                A.METADATA_WORKFLOW:'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml'}
            workflows={}
            for target,relative in sources.items():
                path=postmerge.ROOT/relative
                self.assertTrue(path.is_file() and not path.is_symlink())
                self.assertEqual(path.stat().st_mode & 0o777,0o644)
                raw=path.read_bytes()
                workflows[target]={'mode':'100644','type':'blob',
                    'sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
            self.assertEqual(workflows,generation['workflows'])
        else:
            workflows=deepcopy(generation['workflows'])
        self.tree.update(workflows)
        self.tree[postmerge.TEMPLATE] = deepcopy(self.tree['.github/workflows/parent-qualification.yml'])
        self.tree['.github/test-suites.json'] = {'mode':'100644','type':'blob','sha':'1'*40}
        self.tree['tests/platform-profile.json'] = {'mode':'100644','type':'blob','sha':'2'*40}
        self.previous = deepcopy(self.tree)
        self.case.generation = {path:self.tree[path] for path in A.WORKFLOWS}
        self.case.pp = replace(self.case.pp, workflow_blob=self.tree['.github/workflows/project-tests.yml']['sha'], required_execution_schema=3)
        self.case.policy = replace(self.case.policy, producer=self.case.pp, generations={'reviewed':self.case.generation})
        self.case.plan['owners']['shared-host']['include_platform'] = True
        self.git = postmerge.producer.expected_git_context(self.adapter, self.case.binding)
        receipt = deepcopy(self.case.aggregate['results']['shared-host']['receipt'])
        receipt.update(schema=3, git_context=self.git, include_platform=True,
                       environment=FIXTURES.isolated_codec_environment())
        receipt['results'] = {name:{'status':'passed','fingerprint':P.inputs.suite_fingerprint(
            self.registry,name,self.tree,receipt['environment'])} for name in self.registry['suites']}
        self.receipt = FIXTURES.signed(receipt,'receipt_digest')
        self.case.aggregate['results']['shared-host']['receipt'] = self.receipt
        run = replace(old.run, workflow_path=self.case.pp.workflow_path, workflow_commit=self.case.binding['merge_sha'],
            workflow_ref=self.case.pp.workflow_ref, event='pull_request', workflow_blob=self.case.pp.workflow_blob,
            final_publisher=replace(old.run.final_publisher, receipt_sha256=hashlib.sha256(P.canonical(self.receipt)).hexdigest()))
        self.case.add_run(run); self.case.runs[100]['pull_requests'] = []
        # The real adapter still reads source trees/workflows/job/check/artifact facts.
        self.api.immutable_tree = lambda oid: self.api.mutate(A.PREFIX+'/git/trees/'+oid+'?recursive=1', {
            'sha':oid,'truncated':False,'tree':[{'path':path,**entry} for path,entry in
                (self.previous if oid=='6'*40 else self.tree).items()]})
        package = SimpleNamespace(validate_tree_wiring=self.real_package.validate_tree_wiring,
            _trusted_bytes=lambda name,**_:b'{"schema":1,"platform":"shared","suites":[]}',
            tools=lambda:SimpleNamespace(PROJECTS=('server-console','tools/jsdoc')),
            S3='script-archive/marketplace/S3Server', BROWSER='browser-client')
        self.patches = [patch.object(postmerge,'SOURCE_READY',True),
            patch.object(postmerge.producer,'PRODUCTION_READY',True),
            patch.object(postmerge.sandbox,'ACTIVATION_READY',True),
            patch.object(postmerge.attested,'ISOLATED_ADMISSION_READY',True),
            patch.object(postmerge.execution,'checkout_identity',return_value=(self.case.integrated,self.case.binding['merge_tree'])),
            patch.object(postmerge.inputs,'full_tree',return_value=self.tree),
            patch.object(postmerge.inputs,'load_registry',return_value=self.registry),
            patch.object(postmerge.producer,'_host_policy',return_value=SimpleNamespace(package_policy=lambda:package)),
            patch.object(postmerge.producer,'selection_profile',create=True,return_value={
                'profile':'ubuntu24-host-qt5-qt6-v1','suites':list(self.registry['suites']),
                'selection':{'suites':list(self.registry['suites']),'full_host':True,
                    'include_platform':True,'reason':'fixture-full-owner'}}),
            patch.object(postmerge,'original_controller',return_value=self.case.pp.controller_digest),
            patch.object(postmerge,'_policy',return_value=(self.case.plan,self.case.policy)),
            patch.object(postmerge.attested,'validate_environment',return_value={'environment_digest':'sha256:'+'1'*64,'policy':{'epoch':'fixture'}}),
            patch.object(postmerge.execution,'capture_execution_environment',side_effect=AssertionError('unused consumer E')),
            patch.object(postmerge.execution,'execute',side_effect=AssertionError('no consumer workload'))]
        for item in self.patches:item.start();self.addCleanup(item.stop)
        self.event={'ref':'refs/heads/main','before':self.case.binding['base_sha'],'after':self.case.integrated,
            'deleted':False,'forced':False,'repository':{'full_name':A.REPOSITORY,'id':1319052603}}
        self.environment={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':A.REPOSITORY,'GITHUB_REPOSITORY_ID':'1319052603',
            'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/main','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'qualify-parent',
            'RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24','GITHUB_SHA':self.case.integrated,
            'GITHUB_WORKFLOW_SHA':self.case.integrated,'GITHUB_RUN_ID':'500',
            'GITHUB_WORKFLOW_REF':A.REPOSITORY+'/.github/workflows/parent-qualification.yml@refs/heads/main'}

    def lookup(self):
        return self.module.lookup(self.event,self.environment,self.adapter,clock=lambda:NOW)

    def test_original_full_e_is_authenticated_without_rebinding_or_unused_consumer_setup(self):
        value=self.lookup()
        self.assertTrue(value['reused'],value)
        proof=value['proof']
        self.assertEqual(proof['current_commit'],self.case.integrated)
        self.assertEqual(proof['original_commit'],self.case.binding['merge_sha'])
        self.assertNotEqual(proof['current_commit'],proof['original_commit'])
        self.assertEqual(proof['original_proof']['expires_at'],self.case.aggregate['expires_at'])
        self.assertEqual(proof['original_proof']['receipt_sha256'],hashlib.sha256(P.canonical(self.receipt)).hexdigest())
        self.assertEqual(proof['reused_suites'],list(self.registry['suites']))
        self.assertEqual(proof['executed_suites'],[])
        self.assertFalse(proof['reusable'])
        self.assertFalse(proof['package_work'])
        self.assertEqual(self.receipt['candidate_commit'],self.case.binding['merge_sha'])
        self.assertEqual(self.receipt['environment']['profile'],self.module.inputs.ISOLATED_FULL_PROFILE)
        self.assertIn(self.module.inputs.ISOLATED_CACERTS,self.receipt['environment']['prepared']['roots'])
        self.assertEqual(self.module.attested.validate_environment.call_args.args[0],self.receipt['environment'])

    def test_changed_prepared_identity_cannot_keep_original_fingerprints_or_native_receipt_hash(self):
        run = self.adapter.capture_integrated(500,self.case.plan,self.case.policy,now=NOW).observations[0].run
        for path in (self.module.inputs.ISOLATED_VENV,self.module.inputs.ISOLATED_CACERTS):
            original = deepcopy((self.case.aggregate,self.case.artifacts,self.case.archives))
            changed = deepcopy(self.receipt)
            changed['environment']['prepared']['roots'][path] = 'sha256:' + 'b'*64
            for renew_fingerprints in (False,True):
                if renew_fingerprints:
                    changed['results'] = {name:{'status':'passed','fingerprint':P.inputs.suite_fingerprint(
                        self.registry,name,self.tree,changed['environment'])} for name in self.registry['suites']}
                self.case.aggregate['results']['shared-host']['receipt'] = FIXTURES.signed(changed,'receipt_digest')
                self.case.aggregate = FIXTURES.signed(self.case.aggregate,'aggregate_digest')
                self.case.artifacts[100] = self.case.artifacts[100][:1]
                self.case.artifact(run,'aggregate',self.case.aggregate)
                with self.subTest(path=path,renew_fingerprints=renew_fingerprints):
                    self.assertFalse(self.lookup()['reused'])
            self.case.aggregate,self.case.artifacts,self.case.archives = original

    def test_current_canonical_producer_generation_reaches_original_native_commitment(self):
        self.assertEqual(self.real_package.validate_tree_wiring(self.tree),'protected-producer-metadata-ci-v1')
        self.assertEqual(self.tree['.github/workflows/project-tests.yml']['sha'],
                         self.generations['protected-producer-metadata-ci-v1']['.github/workflows/project-tests.yml']['sha'])
        value=self.lookup()
        self.assertTrue(value['reused'],value)
        proof=value['proof']
        self.assertEqual(proof['original_proof']['source_chain']['producer_blob'],
                         self.tree['.github/workflows/project-tests.yml']['sha'])
        self.assertEqual(proof['original_proof']['receipt_sha256'],hashlib.sha256(P.canonical(self.receipt)).hexdigest())
        self.assertNotEqual(proof['current_commit'],proof['original_commit'])
        self.assertEqual(proof['executed_suites'],[])

    def test_unknown_and_mixed_complete_workflow_tuples_decline_before_original_proof(self):
        path='.github/workflows/parent-qualification.yml'
        original=deepcopy(self.tree[path])
        for kind in ('unknown','mixed'):
            self.tree[path]={'mode':'100644','type':'blob','sha':'f'*40} if kind=='unknown' else deepcopy(
                self.generations['protected-shared-producer-v1'][path])
            # Even known individual blobs cannot form an unreviewed tuple.
            with self.subTest(kind=kind),patch.object(self.adapter,'capture_integrated',
                    side_effect=AssertionError('unapproved tuple reached original proof')):
                with self.assertRaises(ValueError):self.real_package.validate_tree_wiring(self.tree)
                self.assertEqual(self.lookup(),{'reused':False,'reason':'original-proof-unavailable'})
        self.tree[path]=original

    def test_missing_failed_newer_pending_or_rerun_original_selects_one_actual_fallback(self):
        for kind in ('missing','failed','pending','newer','attempt','publisher','artifact','foreign'):
            with self.subTest(kind=kind):
                before=deepcopy((self.case.runs,self.case.jobs,self.case.artifacts))
                if kind=='missing':self.case.runs.clear()
                elif kind=='failed':self.case.runs[100].update(status='completed',conclusion='failure')
                elif kind=='pending':self.case.runs[100].update(status='in_progress',conclusion=None)
                elif kind=='attempt':self.case.runs[100]['run_attempt']=2
                elif kind=='publisher':self.case.jobs[100][-1]['name']=self.case.policy.final_publisher_prefix+'0'*64
                elif kind=='artifact':self.case.artifacts[100].pop()
                elif kind=='foreign':self.case.runs[100]['head_repository']['id']=1
                else:
                    self.case.runs[101]={**deepcopy(self.case.runs[100]),'id':101,'status':'queued','conclusion':None}
                self.assertEqual(self.lookup(),{'reused':False,'reason':'original-proof-unavailable'})
                self.case.runs,self.case.jobs,self.case.artifacts=before

    def test_stale_main_api_changed_context_and_wrong_native_invocations_never_waive(self):
        for key,value in (('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/apple-main'),
                ('GITHUB_JOB','fake-pass'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_SHA','1'*40),
                ('GITHUB_WORKFLOW_SHA','1'*40),('GITHUB_REPOSITORY','overte-org/overte')):
            original=self.environment[key];self.environment[key]=value
            with self.subTest(key=key):self.assertFalse(self.lookup()['reused'])
            self.environment[key]=original
        self.api.mutate=lambda endpoint,value:{**value,'protected':False} if '/branches/' in endpoint else value
        self.assertFalse(self.lookup()['reused'])

    def test_full_source_truncation_aliases_new_inputs_or_changed_declarations_deny(self):
        original=deepcopy(self.tree)
        for mutation in ('truncated','missing','mode','new-import','registry','candidate-scope','runtime'):
            with self.subTest(mutation=mutation):
                self.api.mutate=lambda endpoint,value:value
                if mutation=='truncated':
                    self.api.mutate=lambda endpoint,value:{**value,'truncated':True} if '?recursive=1' in endpoint else value
                elif mutation=='missing':del self.tree['tests/first.py']
                elif mutation=='mode':self.tree['tests/first.py']['mode']='120000'
                elif mutation=='new-import':self.tree['tools/controller.py']['sha']='9'*40
                elif mutation=='registry':self.previous['.github/test-suites.json']['sha']='9'*40
                elif mutation=='candidate-scope':self.registry['suites']['first']['scope']='candidate'
                else:
                    with patch.object(self.module.attested,'validate_environment',side_effect=self.module.attested.AttestedReuseUnavailable('old epoch')):
                        self.assertFalse(self.lookup()['reused'])
                    continue
                self.assertFalse(self.lookup()['reused'])
                self.tree.clear();self.tree.update(deepcopy(original));self.previous=deepcopy(original)
                self.registry['suites']['first']['scope']='content'

    def test_each_source_guard_off_has_zero_api_and_no_policy_json_enable(self):
        for module,name in ((self.module,'SOURCE_READY'),(self.module.producer,'PRODUCTION_READY'),
                (self.module.sandbox,'ACTIVATION_READY'),
                (self.module.attested,'ISOLATED_ADMISSION_READY')):
            self.api.calls.clear()
            with patch.object(module,name,False):self.assertFalse(self.lookup()['reused'])
            self.assertEqual(self.api.calls,[])

    def test_shared_proof_retains_independent_package_work_and_fresh_ref_bookends(self):
        # A shared receipt supplies no package proof. Its original M and S maps
        # still match, while the protected base has the old package manifest.
        path='script-archive/marketplace/S3Server/package-lock.json'
        self.previous[path]={'mode':'100644','type':'blob','sha':'5'*40}
        self.tree[path]={'mode':'100644','type':'blob','sha':'6'*40}
        value=self.lookup()
        self.assertTrue(value['reused'],value)
        self.assertTrue(value['proof']['package_work'])
        count=0
        def changed(endpoint,value):
            nonlocal count
            if '/branches/main' in endpoint:
                count+=1
                if count>2:value['commit']['sha']='7'*40
            return value
        self.api.mutate=changed
        self.assertFalse(self.lookup()['reused'])

    def test_immutable_tree_extended_bound_is_fixed_to_a_validated_tree_endpoint(self):
        with patch.object(A.GitHubReadOnly,'_request',return_value=b'{"truncated":false}') as read:
            self.assertEqual(A.GitHubReadOnly().immutable_tree('a'*40),{'truncated':False})
        read.assert_called_once_with(A.PREFIX+'/git/trees/'+'a'*40+'?recursive=1',20_000_000)
        with self.assertRaises(A.ApiError):A.GitHubReadOnly().immutable_tree('../other')


class MainCI37ConsumerTests(unittest.TestCase):
    """Fake native API chain and actual source/E validators; no hosted proof."""
    def setUp(self):
        fixture = MainConsumerTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.module = fixture, fixture.module
        self.case, self.api = fixture.case, fixture.api
        C, R = self.module, self.module.runtime_ci
        self.registry, self.tree = fixture.registry, fixture.tree
        actual_registry = json.loads((C.ROOT / '.github/test-suites.json').read_bytes(),
                                     object_pairs_hook=C.inputs._unique_object)
        self.registry.clear(); self.registry.update(actual_registry)
        workflow_entries = {path:deepcopy(self.tree[path]) for path in (*A.WORKFLOWS,
            '.github/workflows/browser-client.yml', A.METADATA_WORKFLOW, C.TEMPLATE)}
        # This is the complete inventory of a small fake repository, carrying
        # every real definition's required leaf. No sparse inventory is admitted
        # as a production tree and no real checkout is executed by these tests.
        actual_tree=fixture.real_full_tree(C.ROOT, 'HEAD')
        required={C.ci_profile.POLICY,'.github/test-suites.json','README.md',
                  *self.registry['control_inputs']}
        for suite in self.registry['suites'].values():required.update(suite['closure']['required'])
        self.tree.clear(); self.tree.update({path:entry for path,entry in actual_tree.items() if path in required})
        # New required fake-test leaves may precede this source packet's first
        # commit. They are data in this complete synthetic API tree; repository
        # registry tests separately require the real files to exist.
        for path in required:
            if '*' not in path:
                self.tree.setdefault(path,{'mode':'100644','type':'blob','sha':'a'*40})
        self.tree.update(workflow_entries)
        # A genuine non-documentation CI data delta, independently admitted by
        # the strict immutable-blob guard, supplies the original quick owner.
        original_data=(C.ROOT/C.ci_profile.DATA_PATH).read_bytes()
        current_data=json.loads(original_data)
        current_data['holds']={'fix/main/retain-ci-fixture':'Keep the integration fixture branch'}
        current_data=json.dumps(current_data,sort_keys=True).encode()
        self.data_blobs={hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest():raw
                         for raw in (original_data,current_data)}
        old_data,new_data=self.data_blobs
        self.tree[C.ci_profile.DATA_PATH]={'mode':'100644','type':'blob','sha':new_data}
        fixture.previous = deepcopy(self.tree)
        fixture.previous[C.ci_profile.DATA_PATH]['sha']=old_data
        def blob_request(endpoint,maximum,**options):
            self.api.calls.append(endpoint)
            oid=endpoint.removeprefix(A.PREFIX+'/git/blobs/')
            raw=self.data_blobs[oid]
            return json.dumps({'sha':oid,'size':len(raw),'encoding':'base64',
                'content':A.base64.b64encode(raw).decode()}).encode()
        client=A.GitHubReadOnly();client._request=blob_request
        self.api.immutable_blob=client.immutable_blob
        self.policy = fixture.real_host_policy()
        self.ci_policy = {'schema':1, 'enabled':True, 'profile':C.ci_profile.PROFILE,
            'epoch':'ci37-main-consumer-fake-v1', 'suites':list(C.ci_profile.SUITES),
            'not_before':'2026-10-15T00:00:00Z', 'max_age_seconds':259200,
            'definition_digest':C.ci_profile.definition_digest(self.registry),
            'generation_digest':C.ci_profile.generation(self.tree, self.registry)}
        for owner,name,value in ((C.producer,'_host_policy',self.policy),
                (C.ci_profile,'load_policy',self.ci_policy)):
            item=patch.object(owner,name,return_value=value); item.start(); self.addCleanup(item.stop)
        for owner,name,value in ((self.policy,'REVIEWED_PROGRAMS',self.policy.program_digest(self.tree,C.ROOT)),
                (C.ci_profile,'SOURCE_READY',True)):
            item=patch.object(owner,name,value); item.start(); self.addCleanup(item.stop)
        item=patch.object(C.producer,'selection_profile',side_effect=fixture.real_selection_profile)
        self.selection = item.start(); self.addCleanup(item.stop)
        # Reuse the complete fake E shape, then restore its focused-test mocks:
        # this consumer test exercises the actual strict admission and planner.
        spec=importlib.util.spec_from_file_location('ci37_consumer_environment_fixture',
            Path(__file__).with_name('runtime-ci-test.py'))
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        environment_case=module.OriginalCIEnvironmentTests(); environment_case.setUp()
        self.original_environment=deepcopy(environment_case.environment)
        environment_case.doCleanups()
        selected=C.producer.selection_profile(self.policy,self.registry,self.tree,
            fixture.previous,fixture.previous,root=C.ROOT,read_blob=self.api.immutable_blob)
        self.original_environment['selection']=C.ci_profile.validate_selection(selected['selection'],
            self.tree,fixture.previous,self.registry,policy=self.ci_policy,root=C.ROOT,read_blob=self.api.immutable_blob)
        _, manifests=R.runtime._requirement_inventory(C.ROOT)
        self.original_environment['trusted_execution']={**R.runtime._controller_file_hashes(manifests,C.ROOT),
            **{path:R.runtime._file_digest(C.ROOT/path) for path in R._FILES}}
        self.case.plan['owners']['shared-host'].update(suites=list(C.ci_profile.SUITES),include_platform=False)
        self.publish()
        for owner,name in ((C.attested,'validate_environment'), (R,'capture_ci_environment'), (R,'_query')):
            item=patch.object(owner,name,side_effect=AssertionError('no full profile or consumer runtime query'))
            item.start(); self.addCleanup(item.stop)
        self.selection.reset_mock()

    def publish(self, *, requested=None, environment=None, include_platform=False, mutate=None):
        """Replace fake original artifact and its matching native commitment."""
        fixture, C=self.fixture,self.module
        receipt=deepcopy(fixture.receipt)
        receipt.update(environment=deepcopy(self.original_environment if environment is None else environment),
            requested_suites=list(C.ci_profile.SUITES) if requested is None else requested,
            include_platform=include_platform)
        receipt['results']={name:{'status':'passed','fingerprint':C.inputs.suite_fingerprint(
            self.registry,name,self.tree,receipt['environment'])} for name in receipt['requested_suites']}
        if mutate is not None: mutate(receipt)
        self.receipt=FIXTURES.signed(receipt,'receipt_digest')
        self.case.aggregate['results']['shared-host']['receipt']=self.receipt
        old=FIXTURES.ProducerProtocolTests(); old.setUp()
        run=replace(old.run,workflow_path=self.case.pp.workflow_path,workflow_commit=self.case.binding['merge_sha'],
            workflow_ref=self.case.pp.workflow_ref,event='pull_request',workflow_blob=self.case.pp.workflow_blob,
            final_publisher=replace(old.run.final_publisher,receipt_sha256=hashlib.sha256(P.canonical(self.receipt)).hexdigest()))
        self.case.add_run(run); self.case.runs[100]['pull_requests']=[]

    def lookup(self):
        return self.fixture.lookup()

    def test_original_exact37_environment_and_native_commitment_reuse_without_consumer_capture(self):
        before=deepcopy(self.original_environment)
        with patch.object(self.module,'full_tree',wraps=self.module.full_tree) as source:
            value=self.lookup()
        self.assertTrue(value['reused'],value)
        self.assertEqual([call.args[1] for call in source.call_args_list],
            [self.case.integrated,self.case.binding['base_sha'],self.case.binding['merge_sha']])
        proof=value['proof']
        self.assertEqual(proof['reused_suites'],list(self.module.ci_profile.SUITES))
        self.assertEqual(proof['executed_suites'],[])
        self.assertEqual(proof['original_environment_digest'],self.module.runtime_ci.digest(before))
        self.assertEqual(proof['runtime_admission']['profile'],self.module.ci_profile.PROFILE)
        self.assertEqual(proof['original_proof']['expires_at'],self.case.aggregate['expires_at'])
        self.assertEqual(proof['original_proof']['receipt_sha256'],hashlib.sha256(P.canonical(self.receipt)).hexdigest())
        self.assertEqual(self.receipt['environment'],before)
        self.assertEqual(self.selection.call_count,2)
        for call in self.selection.call_args_list:
            self.assertEqual(call.args[3:5],(self.fixture.previous,self.fixture.previous))
        self.assertFalse(proof['reusable']); self.assertFalse(proof['package_work'])
        for oid in self.data_blobs:
            self.assertIn(A.PREFIX+'/git/blobs/'+oid,self.api.calls)

    def test_cleanup_api_bytes_are_authenticated_on_both_sides_before_original_proof_reuse(self):
        original=self.api.immutable_blob
        for identity in self.data_blobs:
            with self.subTest(side=identity),patch.object(self.api,'immutable_blob',
                    side_effect=lambda oid:b'{"rebound":true}' if oid==identity else original(oid)):
                self.assertEqual(self.lookup(),{'reused':False,'reason':'original-proof-unavailable'})
        with patch.object(self.api,'immutable_blob',side_effect=A.ApiError('bounded immutable read unavailable')):
            self.assertEqual(self.lookup(),{'reused':False,'reason':'original-proof-unavailable'})

    def test_original_receipt_cannot_choose_extra_missing_reordered_or_full_owners(self):
        suites=list(self.module.ci_profile.SUITES)
        for requested,platform in ((suites[:-1],False),(list(reversed(suites)),False),
                ([*suites,'codeql-remediation'],False),(list(self.registry['suites']),True),(suites,True)):
            with self.subTest(count=len(requested),platform=platform):
                self.publish(requested=requested,include_platform=platform)
                self.assertFalse(self.lookup()['reused'])

    def test_original_environment_cannot_relabel_full_profile_or_omit_native_identity(self):
        for change in ({'schema':1},{'profile':'ubuntu24-host-qt5-qt6-v1'}, {'qt':{}}, {'native':{}},
                {'selection':{'suites':list(self.registry['suites'])}}):
            environment={**self.original_environment,**change}
            with self.subTest(change=next(iter(change))):
                self.publish(environment=environment)
                self.assertFalse(self.lookup()['reused'])

    def test_changed_original_reader_import_lookup_or_independent_selection_never_projects_quick(self):
        original=deepcopy(self.fixture.previous)
        for path in ('tools/test-evidence/runtime.py','tests/json.py','libraries/new/CMakeLists.txt',
                'browser-client/package-lock.json','.github/workflows/project-tests.yml'):
            self.fixture.previous.clear(); self.fixture.previous.update(deepcopy(original))
            self.fixture.previous[path]={'mode':'100644','type':'blob','sha':'8'*40}
            with self.subTest(path=path):self.assertFalse(self.lookup()['reused'])
        self.fixture.previous.clear(); self.fixture.previous.update(original)
        actual=self.fixture.real_selection_profile
        def changed(*args,**kwargs):
            value=actual(*args,**kwargs)
            if self.selection.call_count == 2:
                value=deepcopy(value); value['selection']['include_platform']=True
            return value
        self.selection.reset_mock(); self.selection.side_effect=changed
        self.assertFalse(self.lookup()['reused'])

    def test_ci37_guard_disabled_or_unknown_complete_generation_selects_actual_fallback(self):
        for disabled in ('source','policy','generation','definitions'):
            with self.subTest(disabled=disabled):
                policy=deepcopy(self.ci_policy)
                if disabled=='policy':policy['enabled']=False
                elif disabled=='generation':policy['generation_digest']='sha256:'+'0'*64
                elif disabled=='definitions':policy['definition_digest']='sha256:'+'0'*64
                with patch.object(self.module.ci_profile,'SOURCE_READY',disabled!='source'), \
                     patch.object(self.module.ci_profile,'load_policy',return_value=policy):
                    self.assertFalse(self.lookup()['reused'])

    def test_native_receipt_publisher_and_fresh_api_bookends_still_bind_quick_owner(self):
        self.case.jobs[100][-1]['name']=self.case.policy.final_publisher_prefix+'0'*64
        self.assertFalse(self.lookup()['reused'])
        self.publish()
        count=0
        def changed(endpoint,value):
            nonlocal count
            if '/branches/main' in endpoint:
                count+=1
                if count>2:value['commit']['sha']='7'*40
            return value
        self.api.mutate=changed
        self.assertFalse(self.lookup()['reused'])


class MainConsumerSourceTests(unittest.TestCase):
    def test_previous_complete_consumer_generations_remain_reusable(self):
        for generation in ('postmerge-original-e-v1','protected-producer-postmerge-original-e-v1','protected-producer-ci37-v1'):
            fixture=MainConsumerTests();fixture.generation_name=generation
            try:
                fixture.setUp()
                with self.subTest(generation=generation):
                    self.assertEqual(fixture.real_package.validate_tree_wiring(fixture.tree),generation)
                    self.assertTrue(fixture.lookup()['reused'])
            finally:
                fixture.doCleanups()

    def test_original_controller_is_reconstructed_from_immutable_base_without_historical_execution(self):
        import postmerge as C
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null',*args],cwd=root,stderr=subprocess.PIPE).decode().strip()
            git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            files={'tools/controller.py':b'raise RuntimeError("must never execute historic code")\n',
                   'tests/run-project-tests.py':b'print("fixture source only")\n'}
            for relative,raw in files.items():
                p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            (root/'tests/run-project-tests.py').chmod(0o755)
            git('add','.');git('commit','-qm','Create immutable controller fixture')
            tree=C.inputs.full_tree(root,'HEAD')
            package=SimpleNamespace(_trusted_bytes=lambda name,**_:(root/name).read_bytes())
            policy=SimpleNamespace(package_policy=lambda:package)
            with patch.object(C.producer,'controller_sources',return_value=sorted(files)):
                original=C.original_controller(policy,tree,tree,root)
                with patch.object(C.producer,'ROOT',root):
                    self.assertEqual(C.producer._controller_identity(policy),original)
                    injected=SimpleNamespace(__file__=str(root/'tools/injected.py'))
                    with patch.dict(sys.modules,{'unreviewed_repo_module':injected}),self.assertRaises(C.producer.host.Unavailable):
                        C.producer._controller_identity(policy)
                for mutation in ('missing','changed','mode','alias'):
                    previous=deepcopy(tree)
                    if mutation=='missing':previous.pop('tools/controller.py')
                    elif mutation=='changed':previous['tools/controller.py']['sha']='f'*40
                    else:previous['tools/controller.py']['mode']='100755' if mutation=='mode' else '120000'
                    with self.subTest(mutation=mutation),self.assertRaises(A.ApiError):
                        C.original_controller(policy,previous,tree,root)
                (root/'tools/controller.py').write_bytes(b'altered dirty source')
                with self.assertRaises(A.ApiError):C.original_controller(policy,tree,tree,root)

    def test_native_tree_rejects_duplicate_path_truncation_mode_and_wrong_tree_identity(self):
        import postmerge as C
        from types import SimpleNamespace
        row={'path':'source.py','mode':'100644','type':'blob','sha':'a'*40}
        good={'sha':'b'*40,'truncated':False,'tree':[row]}
        for mutation in ('duplicate','truncated','mode','tree','path'):
            value=deepcopy(good)
            if mutation=='duplicate':value['tree'].append(deepcopy(row))
            elif mutation=='truncated':value['truncated']=True
            elif mutation=='mode':value['tree'][0]['mode']='040000'
            elif mutation=='tree':value['sha']='c'*40
            else:value['tree'][0]['path']='../outside'
            adapter=SimpleNamespace(_commit=lambda _:('b'*40,[]),api=SimpleNamespace(immutable_tree=lambda _:value))
            with self.subTest(mutation=mutation),self.assertRaises((A.ApiError,C.inputs.InputError)):
                C.full_tree(adapter,'d'*40)

    def test_prospective_parent_keeps_existing_job_and_has_no_false_qualification_on_reuse(self):
        import postmerge as C
        import yaml
        # The baseline is an immutable reviewed legacy recipe. Reading the
        # active successor here would prepend its reuse condition twice after
        # the exact workflow installation.
        baseline=C.ROOT/'tools/repository-checks/workflows/host/parent-qualification.yml'
        legacy=next(row for row in C.producer._host_policy().package_policy().workflow_generations()
                    if row['name']=='android-owned-npm5-sync-ci-v1')
        raw=baseline.read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),
                         legacy['workflows']['.github/workflows/parent-qualification.yml']['sha'])
        old=yaml.safe_load(raw)
        new=yaml.safe_load((C.ROOT/C.TEMPLATE).read_text())
        self.assertEqual(set(new['jobs']),{'qualify-parent'})
        job=new['jobs']['qualify-parent'];self.assertEqual(job['name'],old['jobs']['qualify-parent']['name'])
        self.assertEqual(job['permissions'],{'contents':'read','actions':'read','pull-requests':'read','checks':'read'})
        # Admission reads these immutable files directly, without sparse Git
        # fallback. Every protected role must materialize the complete closure.
        _, manifests=C.attested.runtime._requirement_inventory(C.ROOT)
        required={*C.attested.runtime._TRUSTED_EXECUTION_FILES,*C.attested._CONSUMER_FILES,*manifests,
                  *C.producer.controller_sources(C.producer._host_policy())}
        templates=(new,yaml.safe_load((C.ROOT/C.producer.TEMPLATE).read_text()))
        for template in templates:
            for owner in template['jobs'].values():
                for step in owner.get('steps',[]):
                    if step.get('with',{}).get('path')!='trusted':continue
                    self.assertIs(step['with'].get('sparse-checkout-cone-mode'),False)
                    patterns=step['with']['sparse-checkout'].splitlines()
                    for relative in required:
                        self.assertTrue(any(relative==p or relative.startswith(p+'/') for p in patterns),
                                        (step['name'],relative))
        names=[row['name'] for row in job['steps']]
        lookup=names.index('Look up original protected PR proof before candidate setup')
        self.assertLess(lookup,names.index('Check out the exact parent commit'))
        for row in job['steps']:
            if row['name'] in {'Set up Python','Set up Java','Install QML and portable C++ contract prerequisites',
                'Prepare isolated host evidence validators','Run complete host qualification',
                'Run independently selected parent host contracts','Create content-addressed qualification evidence',
                'Upload immutable qualification evidence'}:
                self.assertIn("steps.reuse.outputs.shared_reused != 'true'",row['if'])
        steps={row['name']:row for row in job['steps']}
        for name in ('Check only affected tool dependencies and behavior','Check independently selected S3 package dependencies and behavior'):
            expected=deepcopy(next(row for row in old['jobs']['qualify-parent']['steps'] if row['name']==name))
            if 'S3 package' in name:
                expected['if']="(steps.reuse.outputs.shared_reused != 'true' || steps.reuse.outputs.package_work == 'true') && " + expected['if']
            self.assertEqual(steps[name],expected)
        validator=steps['Require an explicit reuse or actual-execution route']['run']
        for reused in ('true','false','','unknown'):
            for packages in ('true','false','','unknown'):
                result=subprocess.run(['bash','-c',validator],env={'SHARED_REUSED':reused,'PACKAGE_WORK':packages},capture_output=True)
                self.assertEqual(result.returncode==0,(reused,packages) in {('true','true'),('true','false'),('false','true')})
        manifest=json.loads((C.ROOT/'.github/package-workflow-generations.json').read_text())['generations']
        current={g['name']:g['workflows'] for g in manifest}
        blob=subprocess.check_output(['git','hash-object','--stdin'],input=(C.ROOT/C.TEMPLATE).read_bytes()).decode().strip()
        for before,after in (('android-owned-npm5-sync-ci-v1','postmerge-original-e-v1'),
                              ('protected-shared-producer-v1','protected-producer-postmerge-original-e-v1'),
                              ('protected-shared-producer-v1','protected-producer-ci37-v1')):
            self.assertEqual(set(current[after]),set(current[before]))
            changed=['.github/workflows/parent-qualification.yml']
            if after in {'protected-producer-postmerge-original-e-v1','protected-producer-ci37-v1'}:
                changed.insert(0,'.github/workflows/project-tests.yml')
                if after=='protected-producer-postmerge-original-e-v1':
                    source=C.ROOT/'tools/repository-checks/workflows/producers/legacy/protected-project-tests-postmerge-v1.yml'
                    project_blob=subprocess.check_output(['git','hash-object','--stdin'],input=source.read_bytes()).decode().strip()
                    self.assertEqual(project_blob,'861db7b76a11b9b8772e91cb24ec7cb9d918e339')
                else:
                    # Historical generations keep their reviewed bytes when the
                    # current dormant template gains a new execution reader.
                    project_blob='c1d3d14a9098de214b6544dca8dcba0072090c6b'
                self.assertEqual(current[after]['.github/workflows/project-tests.yml']['sha'],project_blob)
            self.assertEqual([p for p in current[after] if current[after][p]!=current[before][p]],changed)
            self.assertEqual(current[after]['.github/workflows/parent-qualification.yml']['sha'],
                             '84d98cac819755f98eecffba847e0bbcf667a6ca')
        latest=current['protected-producer-metadata-ci-v1']
        self.assertEqual(latest['.github/workflows/parent-qualification.yml']['sha'],blob)
        for active,template in (
                ('.github/workflows/project-tests.yml',C.producer.TEMPLATE),
                ('.github/workflows/pr-metadata-context.yml',
                 'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml')):
            actual=subprocess.check_output(['git','hash-object','--stdin'],input=(C.ROOT/template).read_bytes()).decode().strip()
            self.assertEqual(latest[active]['sha'],actual)

    def test_disabled_cli_has_zero_api_and_writes_no_shared_pass_or_legacy_receipt(self):
        import postmerge as C
        import tempfile,os
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output';output.touch()
            report=Path(folder)/'report.json'
            with patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}),patch.object(C,'SOURCE_READY',False), \
                    patch.object(C.A,'Adapter',side_effect=AssertionError('zero API')):
                self.assertEqual(C.main(['--report',str(report)]),0)
            self.assertEqual(output.read_text(),'shared_reused=false\npackage_work=true\n')
            self.assertEqual(json.loads(report.read_text()),{'reused':False,'reason':'protected-consumer-not-qualified'})


class MetadataRetentionConsumerTests(unittest.TestCase):
    """Actual retention/API/receipt validators over a small fake-native source.

    The two-suite registry and local controller/runtime admission are fixtures,
    not a complete shipping inventory or hosted qualification. Routing, tuple
    admission, metadata classification, native checker facts and whole-receipt
    verification remain real. No consumer environment or workload is created.
    """
    class SourceApi(FakeApi):
        def source_tree(self, identity):
            case = self.case
            nodes = {}
            for root, source in (("6" * 40, case.previous), (case.binding["merge_tree"], case.tree)):
                directories = {"": root}
                for path in source:
                    pieces = path.split("/")
                    for size in range(1, len(pieces)):
                        prefix = "/".join(pieces[:size])
                        directories[prefix] = hashlib.sha1((root + ":" + prefix).encode()).hexdigest()
                for prefix, oid in directories.items():
                    entries = []
                    for child, child_oid in directories.items():
                        if child and child.rpartition("/")[0] == prefix:
                            entries.append({"path": child.rsplit("/", 1)[-1], "mode": "040000",
                                            "type": "tree", "sha": child_oid})
                    entries.extend({"path": path.rsplit("/", 1)[-1], **entry}
                                   for path, entry in source.items() if path.rpartition("/")[0] == prefix)
                    nodes[oid] = {"sha": oid, "truncated": False, "tree": entries}
            return nodes.get(identity)

        def json(self, endpoint):
            path = endpoint[len(A.PREFIX):].lstrip("/").split("?", 1)[0]
            if path == "actions/workflows/repository-checks.yml":
                self.calls.append(endpoint)
                return self.mutate(endpoint, {"id": 99, "path": ".github/workflows/repository-checks.yml"})
            if path.startswith("git/trees/"):
                value = self.source_tree(path.rsplit("/", 1)[-1])
                if value is not None:
                    self.calls.append(endpoint)
                    return self.mutate(endpoint, deepcopy(value))
            return super().json(endpoint)

        def immutable_tree(self, identity):
            self.case.assertion(identity in {"6" * 40, self.case.binding["merge_tree"]})
            source = self.case.previous if identity == "6" * 40 else self.case.tree
            endpoint = A.PREFIX + "/git/trees/" + identity + "?recursive=1"
            self.calls.append(endpoint)
            return self.mutate(endpoint, {"sha": identity, "truncated": False,
                "tree": [{"path": path, **entry} for path, entry in source.items()]})

        def immutable_blob(self, identity):
            raise AssertionError("the full-profile fixture does not read data-admission blobs")

    def setUp(self):
        import postmerge as C
        from types import SimpleNamespace
        self.module = C
        self.case = AdapterTests(); self.case.setUp()
        c = self.case
        self.registry = deepcopy(c.context.registry)
        c.assertion = self.assertTrue
        c.originals[c.binding["base_sha"]] = ("6" * 40, ["7" * 40])
        real_host = C.producer._host_policy()
        real_package = real_host.package_policy()
        generations = real_package.workflow_generations()
        self.assertEqual(len(generations), 20)
        generation = next(row for row in generations if row["name"] == "protected-producer-metadata-ci-v1")
        sources = {".github/workflows/project-tests.yml": C.producer.TEMPLATE,
            ".github/workflows/repository-checks.yml": "tools/repository-checks/workflows/producers/repository-checks.yml",
            ".github/workflows/parent-qualification.yml": C.TEMPLATE,
            ".github/workflows/sync-validation.yml": ".github/workflows/sync-validation.yml",
            ".github/workflows/browser-client.yml": ".github/workflows/browser-client.yml",
            A.METADATA_WORKFLOW: "tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml"}
        def blob(relative):
            path = C.ROOT / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            raw = path.read_bytes()
            return {"mode": "100644", "type": "blob",
                    "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
        workflows = {path: blob(relative) for path, relative in sources.items()}
        self.assertEqual(workflows, generation["workflows"])
        c.tree = {**deepcopy(c.context.tree), **workflows,
            C.producer.TEMPLATE: workflows[".github/workflows/project-tests.yml"],
            sources[A.METADATA_WORKFLOW]: workflows[A.METADATA_WORKFLOW],
            A.METADATA_SOURCE: blob(A.METADATA_SOURCE),
            ".github/test-suites.json": {"mode": "100644", "type": "blob", "sha": "1" * 40},
            "tests/platform-profile.json": {"mode": "100644", "type": "blob", "sha": "2" * 40},
            ".github/branch-cleanup.json": {"mode": "100644", "type": "blob", "sha": "3" * 40}}
        for path in C._METADATA_OUTER_RECIPES:
            c.tree[path] = blob(path)
        c.previous = deepcopy(c.tree)
        c.tree[".github/branch-cleanup.json"]["sha"] = "4" * 40
        repository = {"full_name": A.REPOSITORY, "id": 1319052603}
        self.event = {"action": "edited", "number": 17, "repository": repository,
            "changes": {"title": {"from": "Previous title"}},
            "pull_request": {"number": 17, "state": "open", "title": "Current title",
                **{side: {"repo": deepcopy(repository), "ref": c.binding[side + "_ref"],
                           "sha": c.binding[side + "_sha"]} for side in ("base", "head")}}}
        self.environment = {"GITHUB_JOB": "route"}
        native = {"number": 17, "run_id": 101, "merge": c.binding["merge_sha"], "base": c.binding["base_sha"]}
        helper = SimpleNamespace(SOURCE_READY=True, native=lambda *args, **kwargs: deepcopy(native))
        package = SimpleNamespace(validate_tree_wiring=real_package.validate_tree_wiring,
            workflow_generations=real_package.workflow_generations, load=real_package.load,
            select=real_package.select, tools=real_package.tools, S3=real_package.S3, BROWSER=real_package.BROWSER,
            _trusted_bytes=lambda name, **kwargs: b'{"schema":1,"platform":"shared","suites":[]}'
                if name == "tests/platform-profile.json" else real_package._trusted_bytes(name, **kwargs))
        policy = SimpleNamespace(package_policy=lambda: package, ci_owned=real_host.ci_owned)
        self.selected = {"profile": C.producer.FULL_PROFILE, "suites": list(self.registry["suites"]),
            "selection": {"suites": list(self.registry["suites"]), "full_host": True,
                "include_platform": False, "reason": "fixture-complete-full-owner"}}
        self.api = self.SourceApi(c); self.adapter = A.Adapter(self.api)
        self.controller = c.pp.controller_digest
        self.patches = [patch.object(C, "_source_qualified", return_value=True),
            patch.object(C, "_metadata_module", return_value=helper),
            patch.object(C.execution, "checkout_identity", return_value=(c.binding["base_sha"], "6" * 40)),
            patch.object(C.inputs, "full_tree", side_effect=lambda *args: deepcopy(c.previous)),
            patch.object(C.inputs, "load_registry", return_value=self.registry),
            patch.object(C.producer, "_host_policy", return_value=policy),
            patch.object(C.producer, "selection_profile", return_value=self.selected),
            patch.object(C, "original_controller", return_value=self.controller),
            patch.object(C.sandbox, "contract", return_value={"digest": c.pp.runtime_contract}),
            patch.object(C.attested, "validate_environment", return_value={"environment_digest": "sha256:" + "1" * 64}),
            patch.object(C.execution, "capture_execution_environment", side_effect=AssertionError("unused consumer E")),
            patch.object(C.execution, "execute", side_effect=AssertionError("no metadata workload"))]
        for item in self.patches:
            item.start(); self.addCleanup(item.stop)
        c.plan, c.policy = C._policy(policy, self.registry, c.binding, self.controller, self.adapter, C.ROOT,
                                    self.selected["selection"])
        c.pp = c.policy.producer
        c.generation = {path: c.tree[path] for path in A.WORKFLOWS}
        self.git = C.producer.expected_git_context(self.adapter, c.binding)
        self.receipt = deepcopy(c.aggregate["results"]["shared-host"]["receipt"])
        self.receipt.update(schema=3, git_context=self.git, environment=FIXTURES.isolated_codec_environment())
        self.receipt["results"] = {name: {"status": "passed", "fingerprint": P.inputs.suite_fingerprint(
            self.registry, name, c.tree, self.receipt["environment"])} for name in self.registry["suites"]}
        self.receipt = FIXTURES.signed(self.receipt, "receipt_digest")
        c.aggregate["results"]["shared-host"]["receipt"] = self.receipt
        old = FIXTURES.ProducerProtocolTests(); old.setUp()
        self.run = replace(old.run, workflow_path=c.pp.workflow_path, workflow_blob=c.pp.workflow_blob,
            workflow_commit=c.binding["merge_sha"], workflow_ref=c.pp.workflow_ref, event="pull_request",
            final_publisher=replace(old.run.final_publisher,
                receipt_sha256=hashlib.sha256(P.canonical(self.receipt)).hexdigest()))
        c.aggregate["descriptor_digest"] = P.descriptor(c.binding, c.plan, c.pp, self.run)["descriptor_digest"]
        c.aggregate = FIXTURES.signed(c.aggregate, "aggregate_digest")
        c.add_run(self.run)
        for index, name in enumerate(("native", "android", "project / tool-dependencies", "project / package-checks"), 150):
            c.jobs[100].append(self.job(index, 100, name, skipped=True))
        for index, (path, (name, steps)) in enumerate(C._METADATA_OUTER_RECIPES.items(), 160):
            c.jobs[100].append(self.job(index, 100, name, steps=steps))
            c.runs[100]["referenced_workflows"].append(self.reference(path))
        c.runs[101] = {**deepcopy(c.runs[100]), "id": 101, "check_suite_id": 1101,
            "status": "in_progress", "conclusion": None, "run_started_at": "2026-10-15T10:04:00Z",
            "referenced_workflows": [self.reference(A.METADATA_WORKFLOW)]}
        c.jobs[101] = [self.job(140, 101, A.METADATA_JOB, steps=(A.METADATA_STEP,), late=True)]
        c.artifacts[101] = []

    def reference(self, path):
        return {"path": A.REPOSITORY + "/" + path + "@" + self.case.binding["merge_sha"],
                "sha": self.case.binding["merge_sha"], "ref": self.case.pp.workflow_ref}

    def job(self, identity, run, name, *, skipped=False, steps=(), late=False):
        start, end = ("2026-10-15T10:04:01Z", "2026-10-15T10:04:20Z") if late else (
            "2026-10-15T10:02:00Z", "2026-10-15T10:03:00Z")
        return {"id": identity, "run_id": run, "run_attempt": 1, "head_sha": self.case.binding["head_sha"],
            "name": name, "status": "completed", "conclusion": "skipped" if skipped else "success",
            "started_at": None if skipped else start, "completed_at": None if skipped else end,
            "check_run_url": f"https://api.github.com/{A.PREFIX}/check-runs/{identity}",
            "steps": [{"number": number, "name": label, "status": "completed", "conclusion": "success",
                       "started_at": start, "completed_at": end} for number, label in enumerate(steps, 1)]}

    def verify(self, *, clock=lambda: NOW):
        return self.module.verify_metadata(self.event, self.environment, self.adapter, clock=clock)

    def test_same_m_retains_original_e_native_receipt_and_actual_checker_jobs_without_execution(self):
        C = self.module
        with patch.object(C, "metadata_selection", wraps=C.metadata_selection) as selection, \
                patch.object(C, "metadata_outer_jobs", wraps=C.metadata_outer_jobs) as outer, \
                patch.object(self.adapter, "verify", wraps=self.adapter.verify) as original:
            value = self.verify()
        self.assertEqual(selection.call_count, 1)
        self.assertEqual(outer.call_count, 2)
        self.assertEqual(original.call_count, 1)
        self.assertEqual(outer.call_args.args[5], "true")
        self.assertEqual(value["metadata_only"], "true")
        self.assertIs(value["qualification"], False)
        self.assertEqual(value["executed_suites"], [])
        self.assertEqual(value["retained_suites"], list(self.registry["suites"]))
        self.assertEqual(set(value["retained_checker_jobs"]), set(C._METADATA_OUTER_RECIPES))
        proof = value["original_proof"]
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["run_id"], 100)
        self.assertEqual(proof["receipt_sha256"], hashlib.sha256(P.canonical(self.receipt)).hexdigest())
        self.assertEqual(proof["expires_at"], self.case.aggregate["expires_at"])
        self.assertEqual(proof["source_chain"]["producer_commit"], self.case.binding["merge_sha"])
        self.assertEqual(C.attested.validate_environment.call_args.args[0], self.receipt["environment"])
        C.execution.capture_execution_environment.assert_not_called()
        C.execution.execute.assert_not_called()

    def test_failed_docs_or_security_command_cannot_be_retained(self):
        for path, (name, _) in self.module._METADATA_OUTER_RECIPES.items():
            job = next(row for row in self.case.jobs[100] if row["name"] == name)
            job["steps"][0]["conclusion"] = "failure"
            with self.subTest(path=path), self.assertRaisesRegex(P.ProtocolError, "checker command"):
                self.verify()
            job["steps"][0]["conclusion"] = "success"

    def test_executed_external_owner_or_package_delta_is_not_metadata_retention(self):
        c = self.case
        for name in ("native", "android", "project / tool-dependencies", "project / package-checks"):
            job = next(row for row in c.jobs[100] if row["name"] == name)
            before = deepcopy(job)
            job.update(conclusion="success", started_at="2026-10-15T10:02:00Z", completed_at="2026-10-15T10:03:00Z")
            with self.subTest(owner=name), self.assertRaisesRegex(P.ProtocolError, "executed external owner"):
                self.verify()
            job.clear(); job.update(before)
        path = "script-archive/marketplace/S3Server/package-lock.json"
        c.previous[path] = {"mode": "100644", "type": "blob", "sha": "5" * 40}
        c.tree[path] = {"mode": "100644", "type": "blob", "sha": "6" * 40}
        with self.assertRaisesRegex(P.ProtocolError, "CI-owned|package/tool"):
            self.verify()

    def test_missing_metadata_marker_and_pending_real_producer_never_retain_success(self):
        references = self.case.runs[101]["referenced_workflows"]
        self.case.runs[101]["referenced_workflows"] = []
        with self.assertRaisesRegex(P.ProtocolError, "authenticated one-way"):
            self.verify()
        self.case.runs[101]["referenced_workflows"] = references
        marker = self.case.jobs[101][0]
        marker["steps"][0]["conclusion"] = "failure"
        with self.assertRaisesRegex(P.ProtocolError, "authenticated one-way"):
            self.verify()
        marker["steps"][0]["conclusion"] = "success"
        self.case.runs[100].update(status="in_progress", conclusion=None)
        with self.assertRaisesRegex(P.ProtocolError, "newest original producer"):
            self.verify()

    def test_resigned_original_e_cannot_change_native_whole_receipt_commitment(self):
        changed = deepcopy(self.receipt)
        changed["environment"]["prepared"]["roots"][self.module.inputs.ISOLATED_CACERTS] = "sha256:" + "b" * 64
        changed["results"] = {name: {"status": "passed", "fingerprint": P.inputs.suite_fingerprint(
            self.registry, name, self.case.tree, changed["environment"])} for name in self.registry["suites"]}
        self.case.aggregate["results"]["shared-host"]["receipt"] = FIXTURES.signed(changed, "receipt_digest")
        self.case.aggregate = FIXTURES.signed(self.case.aggregate, "aggregate_digest")
        self.case.artifacts[100] = self.case.artifacts[100][:1]
        self.case.artifact(self.run, "aggregate", self.case.aggregate)
        with self.assertRaisesRegex(P.ProtocolError, "native|receipt"):
            self.verify()

    def test_final_trusted_source_and_expiry_are_bookended_after_original_verification(self):
        C, c = self.module, self.case
        with patch.object(C.execution, "checkout_identity", side_effect=(
                (c.binding["base_sha"], "6" * 40), ("9" * 40, "6" * 40))), \
                patch.object(self.adapter, "verify", wraps=self.adapter.verify) as original:
            with self.assertRaisesRegex(P.ProtocolError, "actual trusted controller"):
                self.verify()
            self.assertEqual(original.call_count, 1)
        expired = False
        reads = 0
        def controller(*args, **kwargs):
            nonlocal expired, reads
            reads += 1
            if reads == 2:
                expired = True
            return self.controller
        with patch.object(C, "original_controller", side_effect=controller), \
                patch.object(self.adapter, "verify", wraps=self.adapter.verify) as original:
            with self.assertRaisesRegex(P.ProtocolError, "actual trusted controller"):
                self.verify(clock=lambda: P._time(c.aggregate["expires_at"]) if expired else NOW)
            self.assertEqual(original.call_count, 1)
            self.assertEqual(reads, 2)


class DocumentationPushOwnerTests(unittest.TestCase):
    """Real original schema3/native aggregate; local source primitives are fixtures.

    The separate source guard tests authenticate the real finite controller and
    lookup graph. These fake API facts cannot qualify a production runtime.
    """
    def setUp(self):
        self.fixture=MainConsumerTests('runTest')
        self.fixture.generation_name='protected-producer-postmerge-original-e-v1'
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.module=f.module;self.case=f.case;self.api=f.api;self.adapter=f.adapter
        self.original_run=self.adapter.capture_integrated(500,self.case.plan,self.case.policy,now=NOW).observations[0].run
        C=self.module
        f.tree['tests/platform-profile.json']=C.source_admission.ordinary(C.source_admission.SHARED_PROFILE)
        raw=(C.ROOT/A.DOCUMENTATION_PUSH_WORKFLOW).read_bytes()
        f.tree[A.DOCUMENTATION_PUSH_WORKFLOW]=C.source_admission.ordinary(C.source_admission.blob_id(raw))
        shipping=json.loads((C.ROOT/'.github/test-suites.json').read_bytes())
        for name in C.DOCUMENTATION_SUITES:
            f.registry['suites'][name]=deepcopy(shipping['suites'][name])
            for path in f.registry['suites'][name]['closure']['required']:
                body=(C.ROOT/path).read_bytes()
                f.tree[path]=C.source_admission.ordinary(C.source_admission.blob_id(body))
        f.previous.clear();f.previous.update(deepcopy(f.tree))
        self.case.plan['owners']['shared-host']['suites']=list(f.registry['suites'])
        C.producer.selection_profile.return_value={
            'profile':C.producer.FULL_PROFILE,'suites':list(f.registry['suites']),
            'selection':{'suites':list(f.registry['suites']),'full_host':True,'include_platform':True,'reason':'fixture-full-owner'}}
        f.receipt.update(requested_suites=list(f.registry['suites']))
        self.refresh_receipt()
        self.case.push.update(workflow_id=7654321,path=A.DOCUMENTATION_PUSH_WORKFLOW)
        base_json=self.api.json
        def json_api(endpoint):
            if endpoint==A.PREFIX+'/actions/workflows/documentation-push-owner.yml':
                self.api.calls.append(endpoint)
                return self.api.mutate(endpoint,{'id':7654321,'path':A.DOCUMENTATION_PUSH_WORKFLOW,'state':'active'})
            return base_json(endpoint)
        self.api.json=json_api
        f.environment.update(GITHUB_JOB='documentation-source',GITHUB_WORKFLOW_REF=
            A.REPOSITORY+'/'+A.DOCUMENTATION_PUSH_WORKFLOW+'@refs/heads/main')
        item=patch.object(C,'integrated_controller',return_value=self.case.pp.controller_digest)
        item.start();self.addCleanup(item.stop)

    def refresh_receipt(self):
        f=self.fixture
        f.receipt['results']={name:{'status':'passed','fingerprint':P.inputs.suite_fingerprint(
            f.registry,name,f.tree,f.receipt['environment'])} for name in f.receipt['requested_suites']}
        f.receipt=FIXTURES.signed(f.receipt,'receipt_digest')
        self.case.aggregate['results']['shared-host']['receipt']=f.receipt
        run=replace(self.original_run,final_publisher=replace(self.original_run.final_publisher,
            receipt_sha256=hashlib.sha256(P.canonical(f.receipt)).hexdigest()))
        self.case.add_run(run);self.case.runs[100]['pull_requests']=[]

    def lookup(self,clock=lambda:NOW):
        return self.module.lookup(self.fixture.event,self.fixture.environment,self.adapter,clock=clock)

    def test_actual_original_schema3_and_every_documentation_suite_are_verified_without_consumer_E(self):
        value=self.lookup();self.assertTrue(value['reused'],value)
        proof=value['proof'];self.assertEqual(proof['original_commit'],self.case.binding['merge_sha'])
        self.assertNotEqual(proof['original_commit'],proof['current_commit'])
        self.assertEqual(proof['original_proof']['receipt_sha256'],hashlib.sha256(P.canonical(self.fixture.receipt)).hexdigest())
        self.assertLessEqual(self.module.DOCUMENTATION_SUITES,set(proof['reused_suites']))
        self.assertEqual(proof['executed_suites'],[])
        self.assertTrue(any(endpoint.endswith('/actions/workflows/documentation-push-owner.yml') for endpoint in self.api.calls))
        self.assertEqual(self.case.pp.actions_app_id,15368)

    def test_each_missing_selected_documentation_suite_declines_before_original_proof(self):
        C=self.module;selected=C.producer.selection_profile.return_value['selection']
        complete=list(selected['suites'])
        for name in C.DOCUMENTATION_SUITES:
            selected['suites']=[item for item in complete if item!=name]
            with self.subTest(name=name),patch.object(self.adapter,'capture_integrated',side_effect=AssertionError('missing owner reached proof')):
                self.assertFalse(self.lookup()['reused'])
        selected['suites']=complete

    def test_fixed_filename_registration_unknown_id_path_state_and_bookend_drift_decline(self):
        for kind in ('id','path','state','late-id'):
            reads=0
            def mutate(endpoint,value):
                nonlocal reads
                if endpoint.endswith('/actions/workflows/documentation-push-owner.yml'):
                    reads+=1
                    if kind=='id' or kind=='late-id' and reads>1:value['id']=7654322
                    elif kind=='path':value['path']='.github/workflows/other.yml'
                    elif kind=='state':value['state']='disabled_manually'
                return value
            self.api.mutate=mutate
            with self.subTest(kind=kind):self.assertFalse(self.lookup()['reused'])
        self.api.mutate=lambda endpoint,value:value
        self.case.push['workflow_id']=350930890
        self.assertFalse(self.lookup()['reused'])

    def test_missing_pending_failed_foreign_and_wrong_native_whole_hash_use_actual_fallback(self):
        runs,jobs,artifacts=deepcopy((self.case.runs,self.case.jobs,self.case.artifacts))
        for kind in ('missing','pending','failed','foreign','wholehash'):
            self.case.runs,self.case.jobs,self.case.artifacts=deepcopy((runs,jobs,artifacts))
            if kind=='missing':self.case.runs.clear()
            elif kind=='pending':self.case.runs[100].update(status='in_progress',conclusion=None)
            elif kind=='failed':self.case.runs[100].update(status='completed',conclusion='failure')
            elif kind=='foreign':self.case.runs[100]['repository']['id']=42
            else:self.case.jobs[100][-1]['name']=self.case.policy.final_publisher_prefix+'f'*64
            with self.subTest(kind=kind):self.assertFalse(self.lookup()['reused'])

    def test_changed_wrapper_or_environment_and_final_expiry_cannot_retain_original_proof(self):
        f=self.fixture;before=deepcopy(f.tree[A.DOCUMENTATION_PUSH_WORKFLOW])
        # Independently read current S differs from actual trusted D.
        raw_tree=self.api.immutable_tree
        def changed(oid):
            value=raw_tree(oid)
            if oid==self.case.binding['merge_tree']:
                next(row for row in value['tree'] if row['path']==A.DOCUMENTATION_PUSH_WORKFLOW)['sha']='f'*40
            return value
        self.api.immutable_tree=changed
        self.assertFalse(self.lookup()['reused']);self.api.immutable_tree=raw_tree
        self.assertEqual(f.tree[A.DOCUMENTATION_PUSH_WORKFLOW],before)
        f.receipt['environment']['prepared']['roots'][self.module.inputs.ISOLATED_VENV]='sha256:'+'b'*64
        self.case.aggregate['results']['shared-host']['receipt']=FIXTURES.signed(f.receipt,'receipt_digest')
        self.case.aggregate=FIXTURES.signed(self.case.aggregate,'aggregate_digest')
        self.case.artifacts[100]=self.case.artifacts[100][:1]
        self.case.artifact(self.original_run,'aggregate',self.case.aggregate)
        self.assertFalse(self.lookup()['reused'])
        self.assertFalse(self.lookup(clock=lambda:P._time(self.case.aggregate['expires_at']))['reused'])


if __name__ == "__main__":
    unittest.main()
