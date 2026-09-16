#!/usr/bin/env python3
"""Security and reproducibility contracts for shared repository workflows."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/project-tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/pico4-build.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/pico4-release-candidate.yml"
RELEASE_BUNDLE_WORKFLOW = ROOT / ".github/workflows/release-bundle-attest-draft.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/pico4-device-acceptance.yml"
ANDROID_TESTS_WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
DOCUMENTATION_WORKFLOW = ROOT / ".github/workflows/documentation-checks.yml"
BRANCH_POLICY_WORKFLOW = ROOT / ".github/workflows/branch-policy.yml"
BRANCH_SYNC_WORKFLOW = ROOT / ".github/workflows/branch-sync.yml"
PARENT_QUALIFICATION_WORKFLOW = ROOT / ".github/workflows/parent-qualification.yml"
SYNC_REUSE_WORKFLOW = ROOT / ".github/workflows/sync-test-reuse.yml"
SYNC_VALIDATION_WORKFLOW = ROOT / ".github/workflows/sync-validation.yml"
WORKFLOW_DIRECTORY = ROOT / ".github/workflows"
CODEQL_WORKFLOW = ROOT / ".github/workflows/codeql.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-bootstrap.yml"
MACOS_WORKFLOW = ROOT / ".github/workflows/macos-bootstrap.yml"
RULESETS = ROOT / ".github/rulesets"
RULESET_FILES = {
    "Android target branch topology": "android-target-branches.json",
    "Apple target branch topology": "apple-target-branches.json",
    "Immutable Android, canonical, and archive tags": "android-release-tags.json",
    "Immutable Pico 4 release and dependency tags": "pico4-release-tags.json",
    "Permanent branch governance": "permanent-branches.json",
}
ACTION_USE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class LightweightWorkflowContracts(unittest.TestCase):
    def test_documentation_changes_use_lightweight_checks(self):
        documentation = DOCUMENTATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"**/*.md"', documentation)
        self.assertIn("tests/check-documentation.py", documentation)
        self.assertIn("timeout-minutes: 5", documentation)
        self.assertIn("persist-credentials: false", documentation)

    def test_markdown_pushes_skip_expensive_shared_checks(self):
        for path in (WORKFLOW, PARENT_QUALIFICATION_WORKFLOW, CODEQL_WORKFLOW):
            source = path.read_text(encoding="utf-8")
            push = source.split("  push:\n", 1)[1]
            push = re.split(r"(?m)^  [a-z_]+:", push, maxsplit=1)[0]
            self.assertIn('    paths-ignore:\n      - "**/*.md"', push)
        source = CODEQL_WORKFLOW.read_text(encoding="utf-8")
        pull_request = source.split("  pull_request:\n", 1)[1].split("  schedule:", 1)[0]
        self.assertIn('    paths-ignore:\n      - "**/*.md"', pull_request)

    def test_triggered_app_test_workflows_exclude_markdown(self):
        for workflow in (
            WORKFLOW,
            IOS_WORKFLOW,
            MACOS_WORKFLOW,
        ):
            if not workflow.exists():
                continue
            source = workflow.read_text(encoding="utf-8")
            if not re.search(r"(?m)^  (?:push|pull_request):", source):
                continue
            self.assertRegex(source, r'''["']!\*\*/\*\.md["']''', workflow.name)


class WorkflowStorageContracts(unittest.TestCase):
    def test_artifact_uploads_have_explicit_bounded_retention(self):
        upload_count = 0
        for workflow in sorted(WORKFLOW_DIRECTORY.glob("*.yml")):
            lines = workflow.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if not re.match(r"^\s*uses:\s*actions/upload-artifact@", line):
                    continue
                upload_count += 1
                uses_indent = len(line) - len(line.lstrip())
                block = []
                for candidate in lines[index + 1 :]:
                    if candidate.strip():
                        indent = len(candidate) - len(candidate.lstrip())
                        if indent < uses_indent:
                            break
                    block.append(candidate)
                retentions = [
                    int(match.group(1))
                    for candidate in block
                    if (match := re.match(r"^\s*retention-days:\s*(\d+)\s*$", candidate))
                ]
                self.assertEqual(
                    len(retentions),
                    1,
                    f"{workflow.name}: each artifact upload needs one retention-days value",
                )
                # This digest-verified source bundle is a reusable build input,
                # not a diagnostic report. Keep the exception scoped to its
                # exact workflow and artifact contents.
                checkpoint_paths = {
                    "build-ios/qt-source-checkpoint/checkpoint.tar.gz",
                    "build-ios/qt-source-checkpoint/manifest.json",
                }
                source_checkpoint = (workflow.name == "ios-qt-source.yml" and
                                     checkpoint_paths <= {line.strip() for line in block})
                self.assertLessEqual(retentions[0], 90 if source_checkpoint else 30, workflow.name)
                self.assertGreaterEqual(retentions[0], 1, workflow.name)
        self.assertGreater(upload_count, 0)

    def test_native_sccache_github_backend_stays_disabled(self):
        sources = "\n".join(
            workflow.read_text(encoding="utf-8")
            for workflow in sorted(WORKFLOW_DIRECTORY.glob("*.yml"))
        )
        self.assertNotIn("SCCACHE_GHA_ENABLED", sources)


class CodeQLWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CODEQL_WORKFLOW.read_text(encoding="utf-8")

    def test_pilot_is_github_hosted_and_bounded(self):
        self.assertIn("runs-on: ubuntu-24.04", self.source)
        self.assertNotIn("self-hosted", self.source)
        self.assertIn("timeout-minutes: 30", self.source)
        self.assertIn("language: [javascript-typescript, python]", self.source)
        self.assertIn("build-mode: none", self.source)

    def test_permissions_are_least_privilege(self):
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        analyze = self.source.split("  analyze:", 1)[1]
        self.assertRegex(
            analyze,
            r"(?m)^    permissions:\n      contents: read\n      security-events: write$",
        )
        self.assertNotRegex(self.source, r"(?m)^\s+(actions|attestations|id-token|packages): write$")

    def test_actions_are_fresh_full_sha_pins(self):
        actions = ACTION_USE.findall(self.source)
        self.assertEqual(len(actions), 3)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        codeql = [action for action in actions if action.startswith("github/codeql-action/")]
        self.assertEqual(
            codeql,
            [
                "github/codeql-action/init@cdf488f595d80d6e07e03d4674febd5ab45fa938",
                "github/codeql-action/analyze@cdf488f595d80d6e07e03d4674febd5ab45fa938",
            ],
        )

    def test_checkout_is_credential_free_and_default_setup_is_not_mixed_in(self):
        self.assertIn("persist-credentials: false", self.source)
        self.assertNotIn("autobuild", self.source)


class BranchGovernanceWorkflowContracts(unittest.TestCase):
    def test_policy_is_a_native_read_only_pull_request_check(self):
        source = BRANCH_POLICY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", source)
        self.assertNotIn("pull_request_target:", source)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", source)
        self.assertIn("persist-credentials: false", source)
        self.assertRegex(
            source,
            r"(?m)^permissions:\n  contents: read\n  pull-requests: read$",
        )
        self.assertIn("name: branch-policy", source)
        self.assertIn("github.event.pull_request.head.sha", source)
        self.assertIn("github.event.pull_request.head.repo.id", source)
        self.assertIn("github.event.pull_request.base.repo.id", source)
        self.assertIn("github.event.pull_request.user.login", source)
        self.assertIn("github.event.pull_request.user.type", source)
        self.assertIn("github.event.repository.id", source)
        self.assertNotIn("check-runs", source)
        self.assertNotRegex(source, r"(?m)^\s*(checks|pull-requests|contents): write$")

    def test_policy_never_executes_pull_request_policy_or_workflow_changes(self):
        source = BRANCH_POLICY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Check out trusted policy", source)
        self.assertIn("github.event.repository.default_branch", source)
        checkout = source.split("with:", 1)[1].split("- name: Validate", 1)[0]
        self.assertNotIn("github.event.pull_request.head.sha", checkout)
        self.assertIn("pulls/$PULL_REQUEST/files", source)
        self.assertIn("gh api --paginate", source)
        self.assertIn("--jq '.[].filename'", source)
        self.assertNotIn("--paginate --slurp", source)
        self.assertIn("--changed-files-stdin", source)

    def test_governance_actions_are_pinned(self):
        for workflow in (BRANCH_POLICY_WORKFLOW, BRANCH_SYNC_WORKFLOW):
            actions = ACTION_USE.findall(workflow.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(actions), 1)
            self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])

    def test_sync_is_read_only_drift_detection(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("tools/branch-policy/drift.py", source)
        self.assertIn("--expected-parent-sha \"$PUSH_SHA\"", source)
        self.assertIn('--expected-parent-sha "$PUSH_SHA" --observe-push', source)
        strict_tail = source.split('          else\n', 1)[1]
        self.assertNotIn('--observe-push', strict_tail)
        self.assertIn("github.event.repository.default_branch", source)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", source)
        self.assertNotIn("actions/create-github-app-token@", source)
        self.assertNotIn("BRANCH_SYNC_APP", source)
        self.assertNotIn("${{ secrets.", source)
        self.assertNotIn("gh pr", source)
        self.assertNotIn("--auto", source)
        self.assertNotIn("check-runs", source)
        self.assertIn("group: branch-synchronization-${{ github.ref_name }}", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertNotIn("Skipping $parent -> $child", source)
        self.assertNotIn("continue", source)

    def test_multiple_prs_cannot_be_selected_or_merged(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in ("gh pr list", "gh pr create", "gh pr merge", "pulls?", ".[0]"):
            self.assertNotIn(forbidden, source)

    def test_wrong_app_or_author_cannot_authorize_sync(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in ("create-github-app-token", "client-id", "private-key", "author", "login"):
            self.assertNotIn(forbidden, source)


    def test_retired_desktop_branches_have_no_workflow_routes(self):
        for path in WORKFLOW_DIRECTORY.glob("*.yml"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertNotIn("linux-main", source)
                self.assertNotIn("windows-main", source)
        policy = json.loads((ROOT / ".github/branch-policy.json").read_text())
        self.assertEqual(policy["branches"]["main"]["children"], ["android-main", "apple-main"])
        for platform in ("linux", "windows"):
            self.assertTrue((ROOT / "tests/device/adapters/desktop_oculix" / f"{platform}.json").is_file())

    def test_sync_reuse_gate_is_trusted_terminal_and_fail_closed(self):
        source = SYNC_REUSE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", source)
        self.assertNotIn("paths:", source)
        self.assertIn("timeout-minutes: 35", source)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("dispatch-and-wait", source)
        self.assertIn("steps.inspect.outputs.mode != 'ordinary'", source)
        self.assertNotIn("github.event.pull_request.head.sha }}\n          path:", source)
        self.assertNotIn("${{ secrets.", source)

    def test_candidate_execution_is_isolated_read_only(self):
        source = SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^permissions:\n  contents: read\n  pull-requests: read$")
        self.assertNotIn("actions: write", source)
        self.assertNotIn("secrets.", source)
        self.assertIn("ref: main", source)
        self.assertIn("path: trusted", source)
        self.assertIn("ref: ${{ inputs.expected_merge_sha }}", source)
        self.assertIn("path: candidate", source)
        self.assertIn("inputs.mode == 'fallback'", source)
        self.assertIn('GH_TOKEN: ""', source)
        self.assertIn('GITHUB_TOKEN: ""', source)

    def test_qualification_is_exact_push_only_and_bounded(self):
        source = PARENT_QUALIFICATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("push:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("workflow_dispatch:", source)
        self.assertIn("branches: [main, android-main, android-vr, apple-main]", source)
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("retention-days: 4", source)

    def test_reused_shared_qualification_still_runs_product_suites(self):
        source = SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("inputs.mode == 'reuse' && inputs.profile != 'documentation'", source)
        self.assertIn("tests/run-project-tests.py --platform-only --timeout 240", source)
        self.assertIn("working-directory: candidate", source)

    def test_common_suites_delegate_only_governed_same_repository_sync_shapes(self):
        for path in (
            ROOT / ".github/workflows/project-tests.yml",
        ):
            source = path.read_text(encoding="utf-8")
            self.assertIn("SAME_REPOSITORY", source)
            self.assertIn("run_full=true", source)
            self.assertIn("needs.route.outputs.run_full == 'true'", source)
            pull_request = source.split("  pull_request:", 1)[1].split("  push:", 1)[0]
            self.assertNotIn("paths-ignore:", pull_request)





class RulesetManifestContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = {
            name: json.loads((RULESETS / filename).read_text(encoding="utf-8"))
            for name, filename in RULESET_FILES.items()
        }

    @staticmethod
    def rule(manifest, rule_type):
        return next(rule for rule in manifest["rules"] if rule["type"] == rule_type)

    def test_all_five_persistent_rulesets_are_complete_and_versioned(self):
        versioned = []
        for path in RULESETS.glob("*.json"):
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if "target" in candidate:
                versioned.append(path.name)

        self.assertEqual(sorted(versioned), sorted(RULESET_FILES.values()))
        self.assertEqual(set(self.manifests), set(RULESET_FILES))
        for name, manifest in self.manifests.items():
            self.assertEqual(manifest["name"], name)
            self.assertIn(manifest["target"], ("branch", "tag"))
            self.assertEqual(manifest["enforcement"], "active")
            self.assertEqual(manifest["bypass_actors"], [])
            self.assertEqual(manifest["conditions"]["ref_name"]["exclude"], [])
            self.assertTrue(manifest["conditions"]["ref_name"]["include"])
            self.assertTrue(manifest["rules"])

    def test_required_checks_are_strict_and_bound_to_github_actions(self):
        expected = {
            "Android target branch topology": "Enforce Android parent sync path",
            "Apple target branch topology": "Enforce apple-main sync path",
            "Permanent branch governance": "branch-policy",
        }
        for name, context in expected.items():
            parameters = self.rule(
                self.manifests[name], "required_status_checks"
            )["parameters"]
            self.assertTrue(parameters["strict_required_status_checks_policy"])
            self.assertFalse(parameters["do_not_enforce_on_create"])
            expected_checks = [{"context": context, "integration_id": 15368}]
            if name == "Permanent branch governance":
                expected_checks.insert(0, {"context": "dependency-release-policy", "integration_id": 15368})
                expected_checks.append(
                    {"context": "sync-test-reuse", "integration_id": 15368}
                )
            self.assertEqual(parameters["required_status_checks"], expected_checks)


    def test_solo_profile_is_active_without_locking_out_the_maintainer(self):
        solo = json.loads(
            (RULESETS / "review-profiles/solo-maintainer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(solo["required_approving_review_count"], 0)
        self.assertFalse(solo["require_last_push_approval"])
        self.assertEqual(solo["allowed_merge_methods"], ["merge"])
        for name in (
            "Android target branch topology",
            "Apple target branch topology",
            "Permanent branch governance",
        ):
            self.assertEqual(
                self.rule(self.manifests[name], "pull_request")["parameters"], solo
            )

    def test_independent_reviewer_profile_is_ready_but_not_active(self):
        independent = json.loads(
            (RULESETS / "review-profiles/independent-reviewer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(independent["required_approving_review_count"], 1)
        self.assertTrue(independent["dismiss_stale_reviews_on_push"])
        self.assertTrue(independent["require_last_push_approval"])
        self.assertTrue(independent["required_review_thread_resolution"])
        for manifest in self.manifests.values():
            for rule in manifest["rules"]:
                if rule["type"] == "pull_request":
                    self.assertNotEqual(rule["parameters"], independent)

    def test_governed_refs_retain_deletion_and_non_fast_forward_protection(self):
        for name in (
            "Android target branch topology",
            "Apple target branch topology",
            "Immutable Android, canonical, and archive tags",
            "Immutable Pico 4 release and dependency tags",
            "Permanent branch governance",
        ):
            rule_types = {rule["type"] for rule in self.manifests[name]["rules"]}
            self.assertIn("deletion", rule_types)
            self.assertIn("non_fast_forward", rule_types)

    def test_used_release_dependency_and_archive_tag_namespaces_are_protected(self):
        protected = set()
        for name, manifest in self.manifests.items():
            if manifest["target"] == "tag":
                protected.update(manifest["conditions"]["ref_name"]["include"])
        self.assertEqual(
            protected,
            {
                "refs/tags/[0-9]*",
                "refs/tags/v[0-9]*",
                "refs/tags/android-phone-v*",
                "refs/tags/android-phone-16k-deps-v*",
                "refs/tags/archive/**",
                "refs/tags/pico4-v*-rc.*",
                "refs/tags/pico4-preview-*",
                "refs/tags/pico4-deps-v*",
            },
        )

    def test_signed_commits_are_not_required(self):
        for manifest in self.manifests.values():
            self.assertNotIn(
                "required_signatures", {rule["type"] for rule in manifest["rules"]}
            )

    def test_repository_merge_settings_match_transition_policy(self):
        settings = json.loads(
            (RULESETS / "repository-merge-settings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(settings["repository"], "noah-be/overte")
        self.assertEqual(
            settings["settings"],
            {
                "allow_auto_merge": False,
                "allow_merge_commit": True,
                "allow_rebase_merge": False,
                "allow_squash_merge": False,
                "allow_update_branch": False,
                "delete_branch_on_merge": False,
            },
        )


class ArchivedRefRetirementContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = RULESETS / "retirements/archived-branches.json"
        cls.plan = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_temporary_ruleset_is_retired_without_bypass(self):
        retirement = self.plan["ruleset_retirement"]
        self.assertEqual(retirement["name"], "Archived branches")
        self.assertEqual(retirement["operation"], "delete_ruleset_by_freshly_resolved_id")
        self.assertEqual(retirement["expected_current"]["bypass_actors"], [])
        self.assertIn("never use a bypass", retirement["sequence"])
        self.assertFalse((RULESETS / "archived-branches.json").exists())

    def test_all_exact_archive_refs_are_unique_and_batched_4_4_4_1(self):
        refs = self.plan["archive_refs"]
        self.assertEqual(len(refs), 13)
        self.assertEqual(
            [item["disposition"] for item in refs].count("verify_existing"), 2
        )
        self.assertEqual(
            [item["disposition"] for item in refs].count("create_annotated"), 11
        )
        sources = [item["source"] for item in refs]
        tags = [item["tag"] for item in refs]
        self.assertEqual(len(sources), len(set(sources)))
        self.assertEqual(len(tags), len(set(tags)))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", item["tip"]) for item in refs))
        self.assertTrue(all(tag.startswith("refs/tags/archive/") for tag in tags))
        batches = self.plan["deletion_batches"]
        self.assertEqual([len(batch) for batch in batches], [4, 4, 4, 1])
        self.assertEqual([source for batch in batches for source in batch], sources)

class ProjectWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_untrusted_pull_requests_have_read_only_permissions(self):
        self.assertIn("pull_request:", self.source)
        self.assertNotIn("pull_request_target:", self.source)
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        self.assertNotRegex(self.source, r"(?m)^\s*(id-token|packages|actions): write$")

    def test_every_action_is_pinned_to_a_full_commit(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 5)
        self.assertEqual(
            [action for action in actions if not FULL_SHA_ACTION.fullmatch(action)],
            [],
            "pin every action to an immutable 40-character commit SHA",
        )

    def test_checkout_does_not_persist_credentials(self):
        self.assertIn("persist-credentials: false", self.source)

    def test_duplicate_runs_are_cancelled_and_jobs_are_bounded(self):
        self.assertIn("cancel-in-progress: true", self.source)
        timeout = re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)\s*$", self.source)
        self.assertIsNotNone(timeout)
        self.assertLessEqual(int(timeout.group(1)), 30)

    def test_reports_have_short_explicit_retention(self):
        retention = re.search(r"(?m)^\s+retention-days:\s*(\d+)\s*$", self.source)
        self.assertIsNotNone(retention)
        self.assertLessEqual(int(retention.group(1)), 7)
        self.assertNotIn("*.apk", self.source.lower())

    def test_ci_uses_the_repository_entry_point(self):
        self.assertIn("tests/run-project-tests.py", self.source)
        self.assertIn("--junit build/test-results/project-tests.xml", self.source)

    def test_ci_runs_complete_device_control_plane_with_qml(self):
        self.assertIn("qml-module-qttest", self.source)
        self.assertIn("qtdeclarative5-dev-tools", self.source)
        self.assertIn("tests/device/run_control_plane_tests.py", self.source)
        self.assertIn("--profile full --require-qml", self.source)
        self.assertIn("device-e2e-control-plane.xml", self.source)






class SharedReleaseBundleWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RELEASE_BUNDLE_WORKFLOW.read_text(encoding="utf-8")

    def test_reusable_gate_has_no_untrusted_or_manual_entrypoint(self):
        self.assertRegex(self.source, r"(?m)^  workflow_call:$")
        self.assertNotRegex(
            self.source,
            r"(?m)^  (pull_request|pull_request_target|push|workflow_dispatch):$",
        )
        self.assertIn("validate-release-bundle.py", self.source)
        self.assertIn('git rev-list -n 1 "refs/tags/$RELEASE_TAG"', self.source)
        self.assertEqual(self.source.count('[[ "$GITHUB_REF_TYPE" == tag ]]'), 2)
        self.assertEqual(
            self.source.count('[[ "$GITHUB_REF" == "refs/tags/$RELEASE_TAG" ]]'), 2
        )

    def test_release_products_tags_and_publish_environments_are_closed_sets(self):
        for value in (
                "android-phone-release-candidate", "pico4-release-candidate",
                "^android-phone-v[0-9]+\\.[0-9]+\\.[0-9]+-alpha\\.[0-9]+$",
                "^pico4-v[0-9]+\\.[0-9]+\\.[0-9]+-rc\\.[0-9]+$"):
            self.assertIn(value, self.source)
        self.assertEqual(self.source.count("Unsupported release product"), 2)
        publish = self.source.split("  draft-publish:", 1)[1]
        self.assertLess(
            publish.index("Reject non-tag or unprotected release invocation"),
            publish.index("actions/checkout@"),
        )

    def test_build_and_sbom_attestations_are_isolated_and_pinned(self):
        attest = self.source.split("  attest:", 1)[1].split("  draft-publish:", 1)[0]
        self.assertRegex(
            attest,
            r"(?m)^    permissions:\n      contents: read\n      id-token: write\n      attestations: write$",
        )
        self.assertEqual(attest.count(
            "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"), 2)
        self.assertIn("subject-path:", attest)
        self.assertIn("sbom-path:", attest)
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 6)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])

    def test_draft_job_has_only_contents_write_and_environment_approval(self):
        publish = self.source.split("  draft-publish:", 1)[1]
        self.assertIn("environment: ${{ inputs.publish_environment }}", publish)
        self.assertRegex(publish, r"(?m)^    permissions:\n      contents: write$")
        self.assertNotIn("id-token: write", publish)
        self.assertNotIn("attestations: write", publish)
        self.assertIn("gh release create", publish)
        self.assertIn("--draft --verify-tag", publish)
        self.assertNotIn("gh release edit", publish)
        self.assertNotIn("gh release upload", publish)




if __name__ == "__main__":
    unittest.main(verbosity=2)
