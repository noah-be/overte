#!/usr/bin/env python3
"""Offline adversarial tests for the dormant authenticated producer protocol."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import zipfile

import producer as P


NOW = datetime(2026, 10, 15, 10, 5, tzinfo=timezone.utc)


def signed(value, field):
    result = deepcopy(value)
    result.pop(field, None)
    result[field] = P.digest(result)
    return result


class ProducerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.binding = {
            "repository": "noah-l-frank/overte", "repository_id": 1319052603, "pull_request": 17,
            "head_repository_id": 1319052603, "base_ref": "main", "base_sha": "a" * 40,
            "head_ref": "fix/main/example", "head_sha": "b" * 40, "merge_sha": "c" * 40,
            "merge_tree": "d" * 40, "merge_parents": ["a" * 40, "b" * 40],
        }
        self.plan = {"owners": {"shared-host": {"kind": "shared", "suites": ["first", "second"],
                                               "include_platform": False, "platform": {}}}}
        self.policy = P.Policy("noah-l-frank/overte", 1319052603, 15368, ".github/workflows/producer.yml",
                               "e" * 40, "refs/heads/main", ("workflow_dispatch",), "sha256:" + "a" * 64,
                               "sha256:" + "b" * 64, 3600)
        publisher = P.AuthenticatedJob(110, 1, "completed", "success", "2026-10-15T10:00:00Z", "2026-10-15T10:01:00Z")
        owner = P.AuthenticatedJob(120, 1, "completed", "success", "2026-10-15T10:02:00Z", "2026-10-15T10:03:00Z")
        self.run = P.AuthenticatedRun("noah-l-frank/overte", 1319052603, 15368, 100, 1, 1,
                                     "2026-10-15T09:59:00Z", ".github/workflows/producer.yml", "e" * 40,
                                     "f" * 40, "refs/heads/main", "workflow_dispatch", "completed", "success",
                                     publisher, {"shared-host": owner})
        self.registry = {"schema": 1, "control_inputs": ["tools/controller.py"], "suites": {name: {
            "command": ["python", f"tests/{name}.py"], "layer": "quick", "scope": "content", "environment": "host-qt5-qt6",
            "closure": {"kind": "patterns", "inputs": [f"tests/{name}.py"], "required": [f"tests/{name}.py"]},
        } for name in ("first", "second")}}
        self.tree = {path: {"mode": "100644", "type": "blob", "sha": "5" * 40}
                     for path in ("tools/controller.py", "tests/first.py", "tests/second.py")}
        self.environment = {"profile": "independently-captured-offline-fixture", "compiler": "fixture-1"}
        self.context = P.SharedContext(self.registry, self.tree, self.environment, self.binding["merge_sha"], self.binding["merge_tree"])
        self.receipt = {
            "schema": 1, "producer": P.execution.PRODUCER, "candidate_commit": self.binding["merge_sha"],
            "candidate_tree": self.binding["merge_tree"], "environment": self.environment, "reusable": True,
            "requested_suites": ["first", "second"], "include_platform": False,
            "results": {name: {"status": "passed", "fingerprint": P.inputs.suite_fingerprint(
                self.registry, name, self.tree, self.environment)} for name in ("first", "second")},
            "platform_results": {}, "conclusion": "success", "started_at": "2026-10-15T10:02:10Z",
            "completed_at": "2026-10-15T10:02:50Z",
        }
        self.receipt = signed(self.receipt, "receipt_digest")
        final = P.AuthenticatedJob(130, 1, "completed", "success", "2026-10-15T10:03:30Z", "2026-10-15T10:04:45Z")
        self.run = replace(self.run, final_publisher=P.AuthenticatedPublication(
            final, hashlib.sha256(P.canonical(self.receipt)).hexdigest()))
        self.descriptor = P.descriptor(self.binding, self.plan, self.policy, self.run)
        self.aggregate = signed({
            "schema": 1, "producer": "overte-producer-aggregate-v1", "descriptor_digest": self.descriptor["descriptor_digest"],
            "results": {"shared-host": {"status": "passed", "job_id": 120, "attempt": 1, "receipt": self.receipt}},
            "qualified_at": "2026-10-15T10:04:00Z", "expires_at": "2026-10-15T11:04:00Z",
        }, "aggregate_digest")

    def artifact(self, value, kind, run=None):
        run = run or self.run
        raw = P.artifact_bytes(value, kind)
        descriptor_created = (datetime.fromisoformat(run.publisher.started_at.replace("Z", "+00:00"))
                              + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
        facts = P.AuthenticatedArtifact(300 if kind == "descriptor" else 301, 1319052603, run.run_id,
                                        f"ci-{kind}-{run.run_id}-{run.attempt}",
                                        "sha256:" + hashlib.sha256(raw).hexdigest(), False,
                                        descriptor_created if kind == "descriptor" else "2026-10-15T10:04:30Z",
                                        "2026-10-17T10:00:00Z", True, 1)
        return raw, facts

    def observation(self, run=None, descriptor=None):
        run = run or self.run
        value = descriptor if descriptor is not None else P.descriptor(self.binding, self.plan, self.policy, run)
        raw, facts = self.artifact(value, "descriptor", run)
        return P.Observation(run, raw, facts)

    def select(self, observations=None, **kwargs):
        return P.select_authority(observations if observations is not None else [self.observation()],
                                  self.binding, self.plan, self.policy, inventory_complete=kwargs.get("complete", True), now=NOW)

    def verify(self, value=None, *, observations=None, final=None, final_binding=None, contexts=None, now=NOW, facts=None):
        observations = observations if observations is not None else [self.observation()]
        raw, original_facts = self.artifact(self.aggregate if value is None else value, "aggregate")
        return P.verify_aggregate(raw, facts or original_facts, self.binding, self.plan, self.policy, observations,
                                  inventory_complete=True, final_binding=final_binding or self.binding,
                                  final_observations=observations if final is None else final, final_inventory_complete=True,
                                  contexts=contexts if contexts is not None else {"shared-host": self.context}, now=now)

    def later(self, *, run_id=101, attempt=1, status="in_progress", conclusion=None):
        return replace(self.run, run_id=run_id, attempt=attempt, latest_attempt=attempt,
                       attempt_started_at="2026-10-15T10:04:00Z", status=status, conclusion=conclusion,
                       publisher=replace(self.run.publisher, job_id=run_id + 10, attempt=attempt,
                                         started_at="2026-10-15T10:04:00Z", completed_at="2026-10-15T10:04:40Z"),
                       owners={}, final_publisher=None)

    def test_valid_complete_proof_preserves_original_expiry_and_runs_no_candidate_commands(self):
        with patch.object(P.execution, "execute", side_effect=AssertionError("proof validation must not execute candidate")), \
                patch.object(P.execution, "capture_execution_environment", side_effect=AssertionError("no implicit host setup")):
            result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["expires_at"], self.aggregate["expires_at"])
        self.assertEqual(result["qualified_at"], self.aggregate["qualified_at"])
        self.assertEqual(result["final_publisher_job_id"], 130)
        self.assertEqual(result["receipt_sha256"], hashlib.sha256(P.execution.canonical_json(self.receipt)).hexdigest())
        self.assertEqual(self.select()["state"], "proof-required", "run success alone is not a verified result")

    def test_workflow_source_commit_remains_distinct_from_tested_merge_candidate(self):
        self.assertNotEqual(self.descriptor["source"]["workflow_commit"], self.binding["merge_sha"])
        self.assertTrue(self.verify()["verified"])
        wrong = deepcopy(self.descriptor)
        wrong["source"]["workflow_commit"] = self.binding["merge_sha"]
        self.assertEqual(self.select([self.observation(descriptor=signed(wrong, "descriptor_digest"))])["state"], "unresolved")

    def test_all_binding_fields_and_exact_live_parents_are_bound(self):
        for key, replacement in (("base_ref", "android-main"), ("head_ref", "other"), ("base_sha", "6" * 40),
                                 ("head_sha", "7" * 40), ("merge_sha", "8" * 40), ("merge_tree", "9" * 40),
                                 ("head_repository_id", 123), ("pull_request", 18)):
            changed = deepcopy(self.binding)
            changed[key] = replacement
            if key in ("base_sha", "head_sha"):
                changed["merge_parents"] = [changed["base_sha"], changed["head_sha"]]
            with self.subTest(key=key), self.assertRaises(P.ProtocolError):
                self.verify(final_binding=changed)
        invalid = deepcopy(self.binding)
        invalid["merge_parents"].reverse()
        with self.assertRaises(P.ProtocolError):
            P.validate_binding(invalid)

    def test_missing_partial_unclassified_and_tied_inventory_cannot_choose_old_green(self):
        self.assertEqual(self.select([])["state"], "absent")
        self.assertEqual(self.select(complete=False)["state"], "unresolved")
        newest = self.later(status="queued")
        missing = P.Observation(newest, None, None)
        self.assertEqual(self.select([self.observation(), missing])["state"], "unresolved")
        tie = replace(self.run, run_id=102)
        self.assertEqual(self.select([self.observation(), self.observation(tie)])["state"], "unresolved")
        self.assertEqual(self.select([self.observation(), self.observation()])["state"], "unresolved")

    def test_newest_pending_failure_cancelled_and_incomplete_attempt_block_old_success(self):
        for status, conclusion, expected in (("in_progress", None, "pending"), ("queued", None, "pending"),
                                             ("completed", "failure", "failed"), ("completed", "cancelled", "failed"),
                                             ("completed", "timed_out", "failed"), ("completed", "neutral", "failed")):
            run = self.later(status=status, conclusion=conclusion)
            observations = [self.observation(), self.observation(run)]
            with self.subTest(status=status, conclusion=conclusion):
                self.assertEqual(self.select(observations)["state"], expected)
                with self.assertRaises(P.ProtocolError):
                    self.verify(observations=observations)

    def test_full_attempt_history_selects_actual_latest_and_missing_latest_is_unresolved(self):
        old = replace(self.run, latest_attempt=2)
        current = self.later(run_id=self.run.run_id, attempt=2, status="completed", conclusion="success")
        observations = [replace(self.observation(), run=old), self.observation(current)]
        self.assertEqual({key: self.select(observations)[key] for key in ("state", "run_id", "attempt")},
                         {"state": "proof-required", "run_id": 100, "attempt": 2})
        self.assertEqual(self.select(observations[:1])["state"], "unresolved")
        self.assertEqual(self.select([self.observation(), self.observation(current)])["state"], "unresolved")

    def test_later_rerun_of_older_run_is_authoritative_over_a_newer_run_number(self):
        earlier_new_run = replace(self.later(run_id=200, status="completed", conclusion="success"),
                                  attempt_started_at="2026-10-15T10:03:00Z")
        retest = self.later(run_id=100, attempt=2, status="completed", conclusion="failure")
        decision = self.select([self.observation(earlier_new_run), self.observation(retest)])
        self.assertEqual({key: decision[key] for key in ("state", "run_id", "attempt")},
                         {"state": "failed", "run_id": 100, "attempt": 2})

    def test_mixed_owner_job_attempt_and_missing_attempt_start_are_unresolved(self):
        mixed = replace(self.run, owners={"shared-host": replace(self.run.owners["shared-host"], attempt=2)})
        unknown = replace(self.run, attempt_started_at=None)
        for run in (mixed, unknown):
            with self.subTest(run=run):
                observation = replace(self.observation(), run=run)
                self.assertEqual(self.select([observation])["state"], "unresolved")

    def test_json_claims_cannot_authenticate_wrong_repository_app_workflow_or_attempt(self):
        for field, value in (("repository", "overte-org/overte"), ("repository_id", 1), ("actions_app_id", 1),
                             ("workflow_path", ".github/workflows/other.yml"), ("workflow_blob", "1" * 40),
                             ("workflow_ref", "refs/heads/other"), ("event", "pull_request"), ("latest_attempt", 2)):
            with self.subTest(field=field):
                actual = replace(self.run, **{field: value})
                self.assertEqual(self.select([replace(self.observation(), run=actual)])["state"], "unresolved")
        self.assertEqual(self.select([replace(self.observation(), run=deepcopy(self.descriptor["source"]))])["state"], "unresolved")

    def test_policy_plan_and_runtime_contract_changes_require_new_proof(self):
        for change in (replace(self.policy, controller_digest="sha256:" + "c" * 64),
                       replace(self.policy, runtime_contract="sha256:" + "d" * 64)):
            self.assertEqual(P.select_authority([self.observation()], self.binding, self.plan, change,
                                               inventory_complete=True, now=NOW)["state"], "unresolved")
        changed = deepcopy(self.plan)
        changed["owners"]["shared-host"]["suites"].pop()
        self.assertEqual(P.select_authority([self.observation()], self.binding, changed, self.policy,
                                           inventory_complete=True, now=NOW)["state"], "unresolved")

    def test_artifact_api_ownership_name_digest_lifetime_and_facts_type_are_mandatory(self):
        raw, facts = self.artifact(self.descriptor, "descriptor")
        for field, value in (("repository_id", 1), ("run_id", 99), ("name", "ci-descriptor-100-2"),
                             ("archive_digest", "sha256:" + "0" * 64), ("expired", True),
                             ("inventory_complete", False), ("matching_artifacts", 2),
                             ("expires_at", "2026-10-15T10:05:00Z"), ("created_at", "2026-10-16T10:00:00Z")):
            with self.subTest(field=field), self.assertRaises(P.ProtocolError):
                P.read_artifact(raw, "descriptor", replace(facts, **{field: value}), self.run, now=NOW)
        with self.assertRaises(P.ProtocolError):
            P.read_artifact(raw, "descriptor", facts.__dict__, self.run, now=NOW)

    def test_duplicate_extra_symlink_compressed_oversize_and_noncanonical_members_rejected(self):
        sources = []
        for mode in ("extra", "symlink", "noncanonical", "oversize", "duplicate-json", "duplicate-member"):
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
                member = zipfile.ZipInfo("descriptor.json")
                if mode == "symlink":
                    member.external_attr = 0o120777 << 16
                content = P.canonical(self.descriptor)
                if mode == "noncanonical":
                    content = json.dumps(self.descriptor, indent=2).encode()
                elif mode == "oversize":
                    content = b" " * (P._MAX_JSON + 1)
                elif mode == "duplicate-json":
                    content = b'{"schema":1,"schema":1}\n'
                archive.writestr(member, content)
                if mode == "extra":
                    archive.writestr("../other.json", b"{}")
                if mode == "duplicate-member":
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        archive.writestr("descriptor.json", content)
            sources.append((mode, out.getvalue()))
        _, facts = self.artifact(self.descriptor, "descriptor")
        for mode, raw in sources:
            with self.subTest(mode=mode), self.assertRaises(P.ProtocolError):
                P.read_artifact(raw, "descriptor", replace(facts, archive_digest="sha256:" + hashlib.sha256(raw).hexdigest()), self.run, now=NOW)

    def test_self_consistent_json_alone_is_never_an_authenticated_aggregate(self):
        raw, facts = self.artifact(self.aggregate, "aggregate")
        altered = deepcopy(self.aggregate)
        altered["expires_at"] = "2026-10-16T10:00:00Z"
        forged = P.artifact_bytes(signed(altered, "aggregate_digest"), "aggregate")
        with self.assertRaises(P.ProtocolError):
            P.verify_aggregate(forged, facts, self.binding, self.plan, self.policy, [self.observation()], inventory_complete=True,
                               final_binding=self.binding, final_observations=[self.observation()], final_inventory_complete=True,
                               contexts={"shared-host": self.context}, now=NOW)
        self.assertNotEqual(raw, forged)

    def test_missing_failed_skipped_unknown_and_wrong_job_selected_results_fail_even_if_run_is_green(self):
        changes = [lambda value: value["results"].clear(),
                   lambda value: value["results"].update(unrelated=deepcopy(value["results"]["shared-host"])),
                   lambda value: value["results"]["shared-host"].update(status="skipped"),
                   lambda value: value["results"]["shared-host"].update(status="failed"),
                   lambda value: value["results"]["shared-host"].update(job_id=999),
                   lambda value: value["results"]["shared-host"].update(attempt=2)]
        for change in changes:
            altered = deepcopy(self.aggregate)
            change(altered)
            with self.subTest(change=change), self.assertRaises(P.ProtocolError):
                self.verify(signed(altered, "aggregate_digest"))
        failed = replace(self.run, owners={"shared-host": replace(self.run.owners["shared-host"], conclusion="failure")})
        with self.assertRaises(P.ProtocolError):
            self.verify(observations=[self.observation(failed)])

    def test_missing_forged_failing_nonreusable_or_wrong_candidate_inner_receipts_fail(self):
        changes = [lambda value: value["results"].pop("second"),
                   lambda value: value["results"]["first"].update(fingerprint="sha256:" + "0" * 64),
                   lambda value: value.update(conclusion="failure"),
                   lambda value: value.update(reusable=False, environment=None),
                   lambda value: value.update(candidate_commit="6" * 40),
                   lambda value: value.update(candidate_tree="7" * 40),
                   lambda value: value.update(started_at="2026-10-15T09:00:00Z")]
        for change in changes:
            value = deepcopy(self.aggregate)
            change(value["results"]["shared-host"]["receipt"])
            value["results"]["shared-host"]["receipt"] = signed(value["results"]["shared-host"]["receipt"], "receipt_digest")
            with self.subTest(change=change), self.assertRaises(P.ProtocolError):
                self.verify(signed(value, "aggregate_digest"))

    def test_actual_source_definition_and_environment_context_are_independently_bound(self):
        tree = deepcopy(self.tree)
        tree["tests/first.py"]["sha"] = "6" * 40
        registry = deepcopy(self.registry)
        registry["suites"]["first"]["command"].append("--changed")
        for context in (replace(self.context, tree=tree), replace(self.context, registry=registry),
                        replace(self.context, environment={"profile": "different-actual-runtime"}),
                        replace(self.context, candidate_commit="6" * 40), replace(self.context, candidate_tree="7" * 40)):
            with self.subTest(context=context), self.assertRaises(P.ProtocolError):
                self.verify(contexts={"shared-host": context})

    def test_platform_assertions_cannot_be_omitted_from_otherwise_valid_shared_execution(self):
        self.plan["owners"]["shared-host"].update(include_platform=True, platform={"product": ["python", "tests/product.py"]})
        self.descriptor = P.descriptor(self.binding, self.plan, self.policy, self.run)
        self.aggregate["descriptor_digest"] = self.descriptor["descriptor_digest"]
        self.aggregate = signed(self.aggregate, "aggregate_digest")
        with self.assertRaises(P.ProtocolError):
            self.verify()
        receipt = self.aggregate["results"]["shared-host"]["receipt"]
        receipt.update(include_platform=True, platform_results={"product": {"status": "passed", "command": ["python", "tests/product.py"]}})
        self.aggregate["results"]["shared-host"]["receipt"] = signed(receipt, "receipt_digest")
        self.run = replace(self.run, final_publisher=replace(self.run.final_publisher, receipt_sha256=hashlib.sha256(
            P.canonical(self.aggregate["results"]["shared-host"]["receipt"])).hexdigest()))
        self.assertTrue(self.verify(signed(self.aggregate, "aggregate_digest"))["verified"])

    def test_early_descriptor_has_no_final_publication_dependency_but_aggregate_does(self):
        early = replace(self.run, final_publisher=None)
        self.assertEqual(P.descriptor(self.binding, self.plan, self.policy, early), self.descriptor)
        self.assertEqual(self.select([self.observation(early)])["state"], "proof-required")
        with self.assertRaisesRegex(P.ProtocolError, "final publisher is missing"):
            self.verify(observations=[self.observation(early)])

    def test_final_publication_fact_is_not_a_mapping_or_multiple_commitments(self):
        fact = self.run.final_publisher
        for value in (fact.__dict__, [fact], (fact,), {"shared-host": fact}, {"first": fact, "second": fact}):
            with self.subTest(value=value), self.assertRaises(P.ProtocolError):
                self.verify(observations=[self.observation(replace(self.run, final_publisher=value))])

    def test_final_publication_requires_exact_whole_receipt_hash_not_its_self_digest(self):
        for digest in ("", "a" * 63, "A" * 64, "sha256:" + "a" * 64,
                       self.receipt["receipt_digest"].removeprefix("sha256:"), "0" * 64):
            with self.subTest(digest=digest), self.assertRaises(P.ProtocolError):
                actual = replace(self.run, final_publisher=replace(self.run.final_publisher, receipt_sha256=digest))
                self.verify(observations=[self.observation(actual)])

    def test_sibling_candidate_can_resign_a_valid_receipt_but_cannot_change_protected_commitment(self):
        altered = deepcopy(self.aggregate)
        receipt = altered["results"]["shared-host"]["receipt"]
        receipt["started_at"] = "2026-10-15T10:02:11Z"
        altered["results"]["shared-host"]["receipt"] = signed(receipt, "receipt_digest")
        P.execution.validate_receipt(altered["results"]["shared-host"]["receipt"], self.registry, self.tree)
        with self.assertRaisesRegex(P.ProtocolError, "authenticated final publisher commitment"):
            self.verify(signed(altered, "aggregate_digest"))
        self.assertTrue(self.verify()["verified"])

    def test_final_publication_requires_a_distinct_successful_complete_current_attempt_job(self):
        final = self.run.final_publisher
        jobs = [replace(final.job, job_id=self.run.publisher.job_id),
                replace(final.job, job_id=self.run.owners["shared-host"].job_id),
                replace(final.job, attempt=2), replace(final.job, conclusion="failure"),
                replace(final.job, conclusion="skipped"), replace(final.job, status="in_progress", conclusion=None),
                replace(final.job, started_at=None, completed_at=None), replace(final.job, completed_at=None),
                None]
        for job in jobs:
            with self.subTest(job=job), self.assertRaises(P.ProtocolError):
                actual = replace(self.run, final_publisher=replace(final, job=job))
                self.verify(observations=[self.observation(actual)])

    def test_final_publisher_starts_after_owner_and_covers_qualification_and_artifact_creation(self):
        final = self.run.final_publisher
        for job in (replace(final.job, started_at="2026-10-15T10:02:59Z"),
                    replace(final.job, started_at="2026-10-15T10:04:10Z"),
                    replace(final.job, completed_at="2026-10-15T10:04:20Z")):
            with self.subTest(job=job), self.assertRaises(P.ProtocolError):
                actual = replace(self.run, final_publisher=replace(final, job=job))
                self.verify(observations=[self.observation(actual)])
        _, facts = self.artifact(self.aggregate, "aggregate")
        with self.assertRaisesRegex(P.ProtocolError, "actual time window"):
            self.verify(facts=replace(facts, created_at="2026-10-15T10:04:46Z"))

    def test_final_publisher_id_hash_and_timing_are_stable_across_both_api_bookends(self):
        final = self.run.final_publisher
        for changed in (None, replace(final, receipt_sha256="0" * 64),
                        replace(final, job=replace(final.job, job_id=131)),
                        replace(final, job=replace(final.job, completed_at="2026-10-15T10:04:46Z"))):
            with self.subTest(changed=changed), self.assertRaisesRegex(P.ProtocolError, "final publisher is missing or changed"):
                self.verify(final=[self.observation(replace(self.run, final_publisher=changed))])

    def test_final_publication_rejects_multiple_selected_shared_owners(self):
        self.plan["owners"]["second-host"] = deepcopy(self.plan["owners"]["shared-host"])
        self.run = replace(self.run, owners={**self.run.owners, "second-host": replace(self.run.owners["shared-host"], job_id=121)})
        self.descriptor = P.descriptor(self.binding, self.plan, self.policy, self.run)
        value = deepcopy(self.aggregate)
        value["descriptor_digest"] = self.descriptor["descriptor_digest"]
        value["results"]["second-host"] = {**deepcopy(value["results"]["shared-host"]), "job_id": 121}
        with self.assertRaisesRegex(P.ProtocolError, "exactly one shared execution owner"):
            self.verify(signed(value, "aggregate_digest"), contexts={"shared-host": self.context, "second-host": self.context})

    def test_final_publication_cannot_turn_a_successful_rerun_into_original_execution(self):
        final = self.run.final_publisher
        self.run = replace(self.run, attempt=2, latest_attempt=2,
                           publisher=replace(self.run.publisher, attempt=2),
                           owners={name: replace(job, attempt=2) for name, job in self.run.owners.items()},
                           final_publisher=replace(final, job=replace(final.job, attempt=2)))
        self.descriptor = P.descriptor(self.binding, self.plan, self.policy, self.run)
        value = deepcopy(self.aggregate)
        value["descriptor_digest"] = self.descriptor["descriptor_digest"]
        value["results"]["shared-host"]["attempt"] = 2
        self.assertEqual(self.select()["state"], "proof-required")
        with self.assertRaisesRegex(P.ProtocolError, "original first execution attempt"):
            self.verify(signed(value, "aggregate_digest"))

    def test_unimplemented_owner_kinds_and_relay_fields_remain_explicitly_no_reuse(self):
        self.plan["owners"]["shared-host"]["kind"] = "native"
        self.descriptor = P.descriptor(self.binding, self.plan, self.policy, self.run)
        self.aggregate["descriptor_digest"] = self.descriptor["descriptor_digest"]
        with self.assertRaises(P.ProtocolError):
            self.verify(signed(self.aggregate, "aggregate_digest"))
        value = deepcopy(self.aggregate)
        value["original_producer"] = {"run_id": 99, "expires_at": self.aggregate["expires_at"]}
        with self.assertRaises(P.ProtocolError):
            self.verify(signed(value, "aggregate_digest"))

    def test_expiry_future_qualification_and_artifact_shorter_retention_cannot_renew_proof(self):
        for qualified, expires in (("2026-10-15T10:06:00Z", "2026-10-15T11:06:00Z"),
                                   ("2026-10-15T10:04:00Z", "2026-10-15T10:05:00Z"),
                                   ("2026-10-15T10:04:00Z", "2026-10-16T10:04:00Z")):
            value = deepcopy(self.aggregate)
            value.update(qualified_at=qualified, expires_at=expires)
            with self.subTest(qualified=qualified, expires=expires), self.assertRaises(P.ProtocolError):
                self.verify(signed(value, "aggregate_digest"))
        _, facts = self.artifact(self.aggregate, "aggregate")
        with self.assertRaises(P.ProtocolError):
            self.verify(facts=replace(facts, expires_at="2026-10-15T10:30:00Z"))

    def test_new_attempt_or_unavailable_inventory_at_final_recheck_cannot_pass(self):
        with self.assertRaises(P.ProtocolError):
            self.verify(final=[self.observation(), self.observation(self.later())])
        with self.assertRaises(P.ProtocolError):
            self.verify(final=[])

    def test_descriptor_must_precede_candidate_work_and_owner_completion_must_precede_qualification(self):
        for owner in (replace(self.run.owners["shared-host"], started_at="2026-10-15T10:00:10Z"),
                      replace(self.run.owners["shared-host"], completed_at="2026-10-15T10:04:10Z")):
            with self.subTest(owner=owner), self.assertRaises(P.ProtocolError):
                self.verify(observations=[self.observation(replace(self.run, owners={"shared-host": owner}))])

    def test_runtime_capture_adapter_uses_existing_controller_and_never_invents_unknown(self):
        with patch.object(P.execution, "checkout_identity", return_value=(self.binding["merge_sha"], self.binding["merge_tree"])), \
                patch.object(P.inputs, "full_tree", return_value=self.tree):
            with patch.object(P.execution, "capture_execution_environment", return_value=self.environment) as capture:
                context = P.capture_shared_context(self.registry, "/immutable-source", self.binding["merge_sha"])
                self.assertEqual(context.environment, self.environment)
                self.assertEqual(context.candidate_tree, self.binding["merge_tree"])
                capture.assert_called_once_with()
            with patch.object(P.execution, "capture_execution_environment", side_effect=P.execution.runtime.RuntimeIdentityError("unsupported")), \
                    self.assertRaises(P.execution.runtime.RuntimeIdentityError):
                P.capture_shared_context(self.registry, "/immutable-source", self.binding["merge_sha"])
            with self.assertRaises(P.ProtocolError):
                P.capture_shared_context(self.registry, "/immutable-source", "6" * 40)

    def test_canonical_schema_rejects_unknown_fields_boolean_version_and_oversize_values(self):
        for value in (dict(self.descriptor, extra=True), dict(self.descriptor, schema=True)):
            with self.assertRaises(P.ProtocolError):
                P.validate_descriptor(value, self.binding, self.plan, self.policy, self.run)
        with self.assertRaises(P.ProtocolError):
            P.canonical({"oversize": "x" * P._MAX_JSON})


class MaterializedGitContextTests(unittest.TestCase):
    def fixture(self):
        case = ProducerProtocolTests()
        case.setUp()
        case.policy = replace(case.policy, required_execution_schema=3)
        binding = case.binding
        context = {"profile": "streamed-candidate-source-v1", "commits": {
            binding["merge_sha"]: {"commit": binding["merge_sha"], "tree": binding["merge_tree"], "parents": binding["merge_parents"]},
            binding["base_sha"]: {"commit": binding["base_sha"], "tree": "1" * 40, "parents": ["6" * 40]},
            binding["head_sha"]: {"commit": binding["head_sha"], "tree": "2" * 40, "parents": [binding["base_sha"]]},
        }, "shallow": [binding["base_sha"]]}
        case.receipt.update(schema=3, git_context=deepcopy(context))
        case.receipt = signed(case.receipt, "receipt_digest")
        case.context = replace(case.context, git_context=context)
        case.run = replace(case.run, final_publisher=replace(case.run.final_publisher,
            receipt_sha256=hashlib.sha256(P.canonical(case.receipt)).hexdigest()))
        case.descriptor = P.descriptor(case.binding, case.plan, case.policy, case.run)
        case.aggregate["descriptor_digest"] = case.descriptor["descriptor_digest"]
        case.aggregate["results"]["shared-host"]["receipt"] = case.receipt
        case.aggregate = signed(case.aggregate, "aggregate_digest")
        return case

    def test_schema_three_binds_original_git_shape_without_changing_content_fingerprints(self):
        case = self.fixture()
        self.assertTrue(case.verify()["verified"])
        old = ProducerProtocolTests(); old.setUp()
        self.assertEqual(case.receipt["results"], old.receipt["results"])
        self.assertTrue(old.verify()["verified"], "legacy schema1 remains supported by its original policy")

    def test_new_policy_rejects_legacy_receipts_and_missing_independent_context(self):
        case = self.fixture()
        for context in (None, {**case.context.git_context, "shallow": []}):
            with self.subTest(context=context), self.assertRaises(P.ProtocolError):
                case.verify(contexts={"shared-host": replace(case.context, git_context=context)})
        legacy = ProducerProtocolTests(); legacy.setUp()
        legacy.policy = replace(legacy.policy, required_execution_schema=3)
        legacy.aggregate["descriptor_digest"] = P.descriptor(legacy.binding, legacy.plan, legacy.policy, legacy.run)["descriptor_digest"]
        with self.assertRaises(P.ProtocolError):legacy.verify(signed(legacy.aggregate, "aggregate_digest"))

    def test_context_tampering_is_rejected_even_with_recomputed_public_digests(self):
        for mutation in ('parents', 'extra', 'missing', 'shallow', 'tree', 'mode', 'profile'):
            case = self.fixture()
            context = case.receipt['git_context']
            if mutation == 'parents':context['commits'][case.binding['merge_sha']]['parents'].reverse()
            elif mutation == 'extra':context['commits']['7'*40]={'commit':'7'*40,'tree':'8'*40,'parents':[]}
            elif mutation == 'missing':del context['commits'][case.binding['head_sha']]
            elif mutation == 'shallow':context['shallow']=[]
            elif mutation == 'tree':context['commits'][case.binding['merge_sha']]['tree']='8'*40
            elif mutation == 'mode':context['commits'][case.binding['base_sha']]['parents']=['invalid']
            else:context['profile']='full-history-assumed'
            case.receipt = signed(case.receipt, 'receipt_digest')
            case.aggregate['results']['shared-host']['receipt']=case.receipt
            case.run = replace(case.run, final_publisher=replace(case.run.final_publisher,
                receipt_sha256=hashlib.sha256(P.canonical(case.receipt)).hexdigest()))
            with self.subTest(mutation=mutation), self.assertRaises(P.ProtocolError):
                case.verify(signed(case.aggregate, 'aggregate_digest'))


if __name__ == "__main__":
    unittest.main()
