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


if __name__ == "__main__":
    unittest.main()
