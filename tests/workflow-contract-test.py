#!/usr/bin/env python3
"""Security and reproducibility contracts for shared repository workflows."""

import fnmatch
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock


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


def has_automatic_app_trigger(source):
    return re.search(r"(?m)^  (?:push|pull_request):", source) is not None


def workflow_data(source):
    import yaml
    try:
        return yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise ValueError('invalid workflow YAML') from error


def workflow_events(source):
    data = workflow_data(source)
    return data.get('on', data.get(True))


def push_filters(source):
    """Check the semantic push filters independently of YAML presentation."""
    events = workflow_events(source)
    result = events.get('push') if isinstance(events, dict) else None
    if not isinstance(result, dict) or set(result) != {'branches', 'paths-ignore'}:
        raise ValueError('expected explicit branches and paths-ignore filters')
    for values in result.values():
        if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./*-]+', value)
                for value in values):
            raise ValueError('unsupported push filter patterns')
    if result['paths-ignore'] != ['**/*.md']:
        raise ValueError('routing matrix supports only the existing Markdown exclusion')
    return result


def selects_host_push(source, branch, changed_paths):
    filters = push_filters(source)
    if not any(fnmatch.fnmatchcase(branch, item) for item in filters["branches"]):
        return False
    # GitHub's **/ also matches the repository root, unlike fnmatch's **/.
    return any(not path.endswith(".md") for path in changed_paths)


def artifact_retention_limit(workflow_name, artifact_lines):
    # The existing iOS source checkpoint is a verified reusable build input.
    # Diagnostic artifacts and every other workflow retain the ordinary limit.
    checkpoint_paths = {
        "build-ios/qt-source-checkpoint/checkpoint.tar.gz",
        "build-ios/qt-source-checkpoint/manifest.json",
    }
    source_checkpoint = (workflow_name == "ios-qt-source.yml" and
                         checkpoint_paths <= {line.strip() for line in artifact_lines})
    return 90 if source_checkpoint else 30


class LightweightWorkflowContracts(unittest.TestCase):
    def test_documentation_changes_use_lightweight_checks(self):
        documentation = DOCUMENTATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('workflow_call:', documentation)
        self.assertIn('--all', documentation)
        self.assertIn("tests/check-documentation.py", documentation)
        self.assertIn("timeout-minutes: 5", documentation)
        self.assertIn("persist-credentials: false", documentation)

    def test_markdown_pushes_skip_expensive_shared_checks(self):
        for path in (WORKFLOW, PARENT_QUALIFICATION_WORKFLOW, CODEQL_WORKFLOW):
            source = path.read_text(encoding="utf-8")
            self.assertEqual(workflow_events(source)['push']['paths-ignore'], ['**/*.md'])
        source = CODEQL_WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(workflow_events(source)['pull_request']['paths-ignore'], ['**/*.md'])

    def test_app_test_workflows_exclude_markdown(self):
        aggregate = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text(encoding="utf-8")
        self.assertIn("if: needs.route.outputs.mode == 'full'", aggregate)
        self.assertIn("uses: ./.github/workflows/project-tests.yml", aggregate)
        for workflow in (IOS_WORKFLOW, MACOS_WORKFLOW):
            if workflow.exists():
                source = workflow.read_text(encoding="utf-8")
                if has_automatic_app_trigger(source):
                    self.assertRegex(source, r"[\"']!\*\*/\*\.md[\"']", workflow.name)

    def test_manual_app_workflows_do_not_need_nonexistent_pr_filters(self):
        self.assertFalse(has_automatic_app_trigger("on:\n  workflow_dispatch:\n"))
        self.assertTrue(has_automatic_app_trigger("on:\n  pull_request:\n"))
        self.assertTrue(has_automatic_app_trigger("on:\n  push:\n"))

    def test_manual_sandbox_diagnostic_has_no_pr_or_reusable_evidence_authority(self):
        name = "shared-sandbox-host-diagnostic.yml"
        source = (WORKFLOW_DIRECTORY / name).read_text(encoding="utf-8")
        self.assertEqual(source, (ROOT / "tools/test-evidence/workflows" / name).read_text(encoding="utf-8"))
        self.assertEqual(workflow_events(source), {"workflow_dispatch": None})
        data = workflow_data(source)
        self.assertEqual(data["permissions"], {"contents": "read"})
        self.assertEqual(data["concurrency"], {"group": "shared-sandbox-host-diagnostic", "cancel-in-progress": False})
        self.assertEqual(set(data["jobs"]), {"boundary-diagnostic"})
        job = data["jobs"]["boundary-diagnostic"]
        self.assertEqual(set(job), {"runs-on", "timeout-minutes", "steps"})
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertEqual(job["timeout-minutes"], 5)
        steps = job["steps"]
        self.assertEqual(set(steps[0]), {"name", "run"})
        guard = steps[0]["run"]
        for assertion in (
                'test "$GITHUB_REPOSITORY" = noah-l-frank/overte',
                'test "$GITHUB_REPOSITORY_ID" = 1319052603',
                'test "$GITHUB_EVENT_NAME" = workflow_dispatch',
                'test "$GITHUB_REF" = refs/heads/main',
                'test "$GITHUB_WORKFLOW_REF" = \'noah-l-frank/overte/.github/workflows/' + name + '@refs/heads/main\''):
            self.assertIn(assertion, guard)
        self.assertIn("set -euo pipefail", guard)
        checkout = steps[1]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["repository"], "noah-l-frank/overte")
        self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")
        self.assertIs(checkout["with"]["persist-credentials"], False)
        provision = steps[2]
        self.assertEqual(provision["id"], "account")
        self.assertIn('test "$RUNNER_ENVIRONMENT" = github-hosted', provision["run"])
        self.assertIn('test "$ImageOS" = ubuntu24', provision["run"])
        self.assertIn("if getent passwd overte-ci-qualification", provision["run"])
        self.assertIn("useradd --system --no-create-home --shell /usr/sbin/nologin overte-ci-qualification", provision["run"])
        measure = steps[3]["run"]
        self.assertIn("--wait --pipe --collect --quiet --service-type=exec", measure)
        self.assertIn("--expand-environment=no --property=Delegate=yes", measure)
        self.assertIn('/usr/bin/env -i', measure)
        self.assertIn('/usr/bin/python3 -I "$GITHUB_WORKSPACE/tools/test-evidence/sandbox_host.py"', measure)
        self.assertNotIn("GITHUB_TOKEN", measure)
        self.assertEqual(steps[4]["if"], "always() && steps.account.outputs.created == 'true'")
        self.assertEqual(steps[4]["run"], "sudo -n /usr/sbin/userdel overte-ci-qualification")
        artifact = steps[5]
        self.assertEqual(artifact["if"], "always()")
        self.assertTrue(artifact["uses"].startswith("actions/upload-artifact@"))
        self.assertEqual(artifact["with"]["path"], "${{ runner.temp }}/shared-sandbox-diagnostic/result.json")
        self.assertEqual(artifact["with"]["retention-days"], 7)
        self.assertEqual(len(steps), 6)
        self.assertNotIn("continue-on-error", source)
        for caller in ("repository-checks.yml", "project-tests.yml", "parent-qualification.yml", "sync-validation.yml"):
            self.assertNotIn(name, (WORKFLOW_DIRECTORY / caller).read_text(encoding="utf-8"))

    def test_canonical_runner_inventory_covers_descendants_and_is_governed(self):
        config = (ROOT / ".github/actionlint.yaml").read_text()
        labels = set(re.findall(r"(?m)^    - (overte-[a-z0-9-]+)$", config))
        self.assertEqual(labels, {
            "overte-android-build", "overte-android-phone-build",
            "overte-android-phone-emulator", "overte-android-phone-release",
            "overte-android-release", "overte-pico4-device", "overte-ios-ipad",
        })
        workflow = (WORKFLOW_DIRECTORY / "workflow-security.yml").read_text()
        self.assertIn("actionlint -config-file .github/actionlint.yaml -no-color", workflow)
        self.assertNotIn("ACTIONLINT_SELF_HOSTED_LABELS", workflow)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1 python3 tests/workflow-contract-test.py", workflow)
        policy = (ROOT / "tools/branch-policy/check.py").read_text().split("PRIVILEGED_PATHS = (", 1)[1].split(")", 1)[0]
        self.assertIn('".github/actionlint.yaml"', policy)
        reuse = json.loads((ROOT / ".github/sync-test-reuse.json").read_text())
        self.assertIn(".github/actionlint.yaml", reuse["qualified_inputs"])
        self.assertIn(".github/actionlint.yaml", reuse["required_qualified_inputs"])


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
                self.assertLessEqual(retentions[0], artifact_retention_limit(workflow.name, block), workflow.name)
                self.assertGreaterEqual(retentions[0], 1, workflow.name)
        self.assertGreater(upload_count, 0)

    def test_source_checkpoint_retention_exception_cannot_cover_other_artifacts(self):
        checkpoint = ["build-ios/qt-source-checkpoint/checkpoint.tar.gz",
                      "build-ios/qt-source-checkpoint/manifest.json"]
        self.assertEqual(artifact_retention_limit("ios-qt-source.yml", checkpoint), 90)
        self.assertEqual(artifact_retention_limit("other.yml", checkpoint), 30)
        self.assertEqual(artifact_retention_limit("ios-qt-source.yml", checkpoint[:1]), 30)
        self.assertEqual(artifact_retention_limit("ios-qt-source.yml", ["build-ios/log.txt"]), 30)

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
        self.assertIn('--gate-run-id "$GITHUB_RUN_ID"', source)
        self.assertIn('--gate-run-attempt "$GITHUB_RUN_ATTEMPT"', source)
        self.assertIn("steps.inspect.outputs.mode != 'ordinary'", source)
        self.assertNotIn("github.event.pull_request.head.sha }}\n          path:", source)
        self.assertNotIn("${{ secrets.", source)

    def test_candidate_execution_is_isolated_read_only(self):
        import yaml
        source = SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8")
        workflow = yaml.safe_load(source)
        self.assertEqual(workflow['permissions'], {'actions': 'read', 'contents': 'read', 'pull-requests': 'read'})
        self.assertNotRegex(source, r"(?m)^\s+[a-z-]+: write$")
        self.assertNotIn("secrets.", source)
        steps = workflow['jobs']['validate']['steps']
        checkouts = [step['with'] for step in steps if step.get('uses', '').startswith('actions/checkout@')]
        self.assertEqual([(step['path'], step['ref'], step['persist-credentials']) for step in checkouts],
                         [('trusted', 'main', False), ('candidate', '${{ inputs.expected_merge_sha }}', False)])
        self.assertIn("inputs.mode == 'fallback'", source)
        self.assertIn('GH_TOKEN: ""', source)
        self.assertIn('GITHUB_TOKEN: ""', source)
        self.assertNotIn('candidate/tests/run-project-tests.py', source)
        self.assertNotIn('python tests/run-project-tests.py', source)
        for step in steps:
            if 'trusted/tools/test-evidence/validate-sync.py' in step.get('run', ''):
                self.assertNotEqual(step.get('working-directory'), 'candidate')
                self.assertIn('--candidate candidate', step['run'])
                for field in ('base-sha', 'head-sha', 'merge-sha'):
                    self.assertIn('--' + field, step['run'])
                self.assertIn('--receipt build/test-results/sync-validation.json', step['run'])

    def test_sync_reuse_has_no_readiness_rerun_or_postvalidation_cancellation(self):
        import yaml
        source = SYNC_REUSE_WORKFLOW.read_text(encoding="utf-8")
        workflow = yaml.safe_load(source)
        triggers = workflow.get('on', workflow.get(True))
        self.assertEqual(triggers['pull_request_target']['types'], ['opened', 'reopened', 'synchronize', 'edited'])
        self.assertNotIn('cancel-redundant', source)
        self.assertNotIn('--window', source)
        self.assertEqual(source.count('gate.py dispatch-and-wait'), 1)
        self.assertTrue(workflow['concurrency']['cancel-in-progress'])

    def test_qualification_is_exact_push_only_and_bounded(self):
        source = PARENT_QUALIFICATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("push:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("workflow_dispatch:", source)
        self.assertEqual(workflow_events(source)['push']['branches'], ['main', 'android-main', 'android-vr', 'apple-main'])
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("retention-days: 4", source)

    def test_reused_shared_qualification_still_runs_product_suites(self):
        import yaml
        source = SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8")
        steps = yaml.safe_load(source)['jobs']['validate']['steps']
        product = next(step for step in steps if 'build/host-tests-env/bin/python trusted/tools/test-evidence/validate-sync.py'
                       in step.get('run', ''))
        self.assertEqual(product['if'], "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')")
        self.assertIn('--mode "$MODE" --profile "$PROFILE"', product['run'])
        self.assertEqual(product['env']['MODE'], '${{ inputs.mode }}')
        # The trusted consumer, rather than a mutable candidate runner, owns
        # execution of all declared product suites on reuse and fallback alike.
        consumer = ast.parse((ROOT / 'tools/test-evidence/validate-sync.py').read_text())
        executions = [node for node in ast.walk(consumer) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                      and (node.func.value.id, node.func.attr) == ('execution', 'execute')]
        self.assertEqual(len(executions), 1)
        self.assertTrue(next(item.value for item in executions[0].keywords if item.arg == 'include_platform').value)

    def test_project_workflow_is_reusable_with_single_caller_routing(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", source)
        self.assertNotIn("run_full", source)
        self.assertIn("needs: route", source)
        self.assertIn('--event "$GITHUB_EVENT_PATH"', source)
        self.assertNotIn("pull_request:", source)
        aggregate = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text()
        self.assertIn("if: needs.route.outputs.mode == 'full'", aggregate)
        pull_request = aggregate.split("  pull_request:", 1)[1].split("  workflow_dispatch:", 1)[0]
        self.assertNotIn("paths", pull_request)
        self.assertIn("edited", pull_request)


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
            if name == "Apple target branch topology":
                expected_checks.append(
                    {"context": "ios-device-build", "integration_id": 15368}
                )
            if name == "Permanent branch governance":
                expected_checks.insert(0, {"context": "dependency-release-policy", "integration_id": 15368})
                expected_checks.append(
                    {"context": "sync-test-reuse", "integration_id": 15368}
                )
                expected_checks.append(
                    {"context": "repository-checks", "integration_id": 15368}
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
        self.assertEqual(settings["repository"], "noah-l-frank/overte")
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
    def test_tool_dependency_lane_is_bounded_and_selected_by_the_trusted_router(self):
        jobs = workflow_data(WORKFLOW.read_text())['jobs']
        self.assertEqual(jobs['project-tests']['if'], "needs.route.outputs.package_host_mode == 'full'")
        light = jobs['tool-dependencies']
        self.assertEqual(light['if'], "needs.route.outputs.package_host_mode == 'tool-dependencies'")
        runs = '\n'.join(step.get('run', '') for step in light['steps'])
        self.assertIn('trusted/tools/repository-checks/package_checks.py run', runs)
        self.assertIn('--lane tool-dependencies', runs)
        self.assertNotIn('apt-get', runs)
        self.assertNotIn('tests/run-project-tests.py', runs)
        for step in light['steps']:
            if step.get('uses', '').startswith('actions/checkout@'):
                self.assertIs(step['with']['persist-credentials'], False)
        self.assertEqual(light['steps'][0]['with']['path'], 'trusted')
        self.assertEqual(light['steps'][0]['with']['ref'], '${{ github.event.repository.default_branch }}')
        controller = (ROOT / 'tools/repository-checks/package_checks.py').read_text()
        self.assertIn('with controller.candidate_process_environment():', controller)
        final = jobs['project-results']
        self.assertEqual(final['if'], 'always()')
        self.assertEqual(set(final['needs']), {'route', 'project-tests', 'tool-dependencies', 'package-checks'})
        caller = workflow_data((WORKFLOW_DIRECTORY / 'repository-checks.yml').read_text())['jobs']['project']
        self.assertIn("needs.route.outputs.mode == 'tool-dependencies'", caller['if'])
        self.assertIn("needs.route.outputs.package_set != '[]'", caller['if'])
        self.assertEqual(caller['with']['dependency_projects'], '${{ needs.route.outputs.tool_projects }}')
        self.assertEqual(caller['with']['expected_package_plan'], '${{ needs.route.outputs.package_plan }}')

    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_untrusted_pull_requests_have_read_only_permissions(self):
        self.assertIn("workflow_call:", self.source)
        caller = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text()
        self.assertIn("pull_request:", caller)
        self.assertNotIn("pull_request_target:", caller)
        self.assertNotRegex(caller, r"(?m)^\s+[a-z-]+: write$")
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
        self.assertIn("--profile host --timeout 240 --host-timeout 900", self.source)
        self.assertIn("device-e2e-control-plane.xml", self.source)


class HostWorkflowRoutingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = {
            "shared": WORKFLOW.read_text(encoding="utf-8"),
            "parent": PARENT_QUALIFICATION_WORKFLOW.read_text(encoding="utf-8"),
        }
        cls.branches = json.loads((ROOT / ".github/branch-policy.json").read_text())["branches"]

    def selected(self, branch, changed_paths):
        return [name for name, source in self.workflows.items()
                if selects_host_push(source, branch, changed_paths)]

    def test_every_permanent_branch_push_runs_exactly_one_complete_host_lane(self):
        for branch, settings in self.branches.items():
            with self.subTest(branch=branch):
                expected = "parent" if settings["children"] else "shared"
                self.assertEqual(self.selected(branch, ["interface/src/Application.cpp"]), [expected])

    def test_development_push_coverage_and_manual_reusable_entrypoints_remain(self):
        for branch in ("ci/main/workflow-change", "test/main/test-change", "ci/example", "test/example"):
            with self.subTest(branch=branch):
                self.assertEqual(self.selected(branch, ["tests/new-test.py"]), ["shared"])
        for branch in ("feature/main/example", "ci", "testing/example"):
            self.assertEqual(self.selected(branch, ["tests/new-test.py"]), [])
        for event in ("workflow_call", "workflow_dispatch"):
            self.assertIn(event, workflow_events(self.workflows['shared']))
            self.assertNotIn(event, workflow_events(self.workflows['parent']))
        aggregate = (WORKFLOW_DIRECTORY / "repository-checks.yml").read_text()
        self.assertIn("pull_request:", aggregate)
        self.assertIn("if: needs.route.outputs.mode == 'full'", aggregate)
        self.assertIn("uses: ./.github/workflows/project-tests.yml", aggregate)

    def test_only_markdown_changes_skip_push_lanes(self):
        for branch in (*self.branches, "ci/main/example", "test/main/example"):
            with self.subTest(branch=branch):
                self.assertEqual(self.selected(branch, ["README.md", "docs/guide.md"]), [])
                self.assertEqual(len(self.selected(branch, ["README.md", "tests/new-test.py"])), 1)
                self.assertEqual(len(self.selected(branch, ["unknown.extension"])), 1)

    def test_routing_parser_rejects_unsupported_or_incomplete_configuration(self):
        valid = 'on:\n  push:\n    branches: [main]\n    paths-ignore:\n      - "**/*.md"\n'
        self.assertTrue(selects_host_push(valid, "main", ["tests/test.py"]))
        variants = (
            valid.replace("branches: [main]", "branches-ignore: [main]"),
            valid.replace("branches: [main]", "branches: []"),
            valid.replace("branches: [main]", "branches: [main, '!apple-main']"),
            valid.replace('"**/*.md"', '"**/*.py"'),
            valid.replace("    branches: [main]\n", ""),
            valid.replace("  push:\n", "  push: {}\n"),
            valid + "    tags: [v*]\n",
        )
        for source in variants:
            with self.subTest(source=source), self.assertRaises(ValueError):
                push_filters(source)

    def test_parent_and_shared_keep_matching_tools_and_complete_host_coverage(self):
        for name, source in self.workflows.items():
            with self.subTest(workflow=name):
                workflow = workflow_data(source)
                steps = [step for job in workflow['jobs'].values() for step in job.get('steps', [])]
                for action, key, version in (('setup-python', 'python-version', '3.12'),
                                             ('setup-node', 'node-version', '22'),
                                             ('setup-java', 'java-version', '17')):
                    matching = [step['with'] for step in steps if step.get('uses', '').startswith('actions/' + action + '@')]
                    self.assertTrue(any(item.get(key) == version for item in matching), action)
                    if action == 'setup-java': self.assertTrue(all(item['distribution'] == 'temurin' for item in matching))
                runs = '\n'.join(step.get('run', '') for step in steps)
                for fragment in ("command -v cmake", "command -v ctest",
                                 "qml-module-qttest", "qtdeclarative5-dev-tools",
                                 "qt6-base-dev qt6-base-dev-tools",
                                 "unshare --user --map-root-user --net true"):
                    self.assertIn(fragment, runs)
                if name == "parent":
                    self.assertIn("-r trusted/tests/requirements-host.txt", runs)
                    self.assertIn("build/host-tests-env/bin/python trusted/tools/test-evidence/run.py", runs)
                    self.assertIn("--candidate candidate --include-platform --timeout 240 --host-timeout 900", runs)
                    self.assertNotIn("python tests/run-project-tests.py", source)
                    self.assertNotIn("candidate/tests/run-project-tests.py", source)
                else:
                    self.assertIn("-r tests/requirements-host.txt", runs)
                    self.assertEqual(runs.count("tests/run-project-tests.py"), 1)
                    self.assertIn("build/host-tests-env/bin/python tests/run-project-tests.py", runs)
                    self.assertIn("--profile host --timeout 240 --host-timeout 900", runs)
                self.assertNotIn("tests/device/run_control_plane_tests.py", source)
                self.assertNotIn("--shared-only", source)
                self.assertNotIn("--platform-only", source)
                self.assertNotIn("continue-on-error:", source)

    def test_host_namespace_setup_is_ephemeral_and_preserves_isolation(self):
        import yaml
        workflows = [(name, source, "Prepare isolated host evidence validators")
                     for name, source in self.workflows.items()]
        workflows.append(("sync-fallback", SYNC_VALIDATION_WORKFLOW.read_text(encoding="utf-8"),
                          "Prepare isolated shared and product Python validators"))
        for name, source, step in workflows:
            with self.subTest(workflow=name):
                self.assertIn("runs-on: ubuntu-24.04", source)
                setup_steps = [item for job in yaml.safe_load(source)['jobs'].values()
                               for item in job.get('steps', []) if item.get('name') == step]
                self.assertEqual(len(setup_steps), 1)
                setup = setup_steps[0]['run']
                guard = 'test "$RUNNER_ENVIRONMENT" = github-hosted'
                setting = "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0"
                probe = "unshare --user --map-root-user --net true"
                self.assertLess(setup.index(guard), setup.index(setting))
                self.assertLess(setup.index(setting), setup.index(probe))
                self.assertLess(setup.index(probe), setup.index("python3 -m venv"))
                self.assertNotIn("||", setup)
                self.assertNotIn("/etc/sysctl", setup)
                self.assertNotIn("sudo unshare", source)
                self.assertNotIn("sudo python", source)
                self.assertNotIn("continue-on-error:", source)

    def test_sync_platform_and_fallback_install_host_packages_before_execution(self):
        import yaml
        workflow = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())
        steps = workflow['jobs']['validate']['steps']
        installs = [(index, step) for index, step in enumerate(steps)
                    if 'apt-get' in step.get('run', '') and 'install' in step['run']]
        self.assertEqual(len(installs), 1, 'Both paths must share one prerequisite installation')
        index, install = installs[0]
        self.assertEqual(install['if'], "inputs.mode == 'fallback' || (inputs.profile != 'documentation' && inputs.profile != 'tool-dependencies')")
        for package in ('qt6-base-dev', 'qt6-base-dev-tools', 'pkg-config',
                        'qml-module-qttest', 'qtdeclarative5-dev-tools'):
            self.assertIn(package, install['run'].split())
        executions = [i for i, step in enumerate(steps)
                      if 'build/host-tests-env/bin/python trusted/tools/test-evidence/validate-sync.py'
                      in step.get('run', '')]
        self.assertEqual(len(executions), 1, 'Reuse and fallback share one trusted execution controller')
        self.assertLess(index, executions[0])
        self.assertEqual(install['if'], steps[executions[0]]['if'])

    def test_reused_product_suites_share_the_prepared_python_interpreter(self):
        import yaml
        steps = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        name = 'Prepare isolated shared and product Python validators'
        index = next(i for i, step in enumerate(steps) if step.get('name') == name)
        prepare = steps[index]
        product = next(step for step in steps if 'build/host-tests-env/bin/python trusted/tools/test-evidence/validate-sync.py'
                       in step.get('run', ''))
        self.assertEqual(prepare['if'], product['if'])
        self.assertIsNone(prepare.get('working-directory'))
        self.assertIsNone(product.get('working-directory'))
        self.assertLess(index, steps.index(product))
        interpreter = 'build/host-tests-env/bin/python'
        self.assertIn('python3 -m venv build/host-tests-env', prepare['run'])
        self.assertIn(interpreter + ' -m pip install --disable-pip-version-check '
                      '-r trusted/tests/requirements-host.txt', prepare['run'])
        self.assertEqual(product['run'].split()[0], interpreter)
        self.assertIn('trusted/tools/test-evidence/validate-sync.py', product['run'])
        self.assertIn('--candidate candidate', product['run'])
        self.assertEqual(prepare['env'], {'GH_TOKEN': '', 'GITHUB_TOKEN': ''})
        # The controller uses this read-only token for API evidence; its scoped
        # candidate environment removes it before executing any candidate input.
        self.assertEqual(product['env']['GH_TOKEN'], '${{ github.token }}')
        self.assertNotIn('continue-on-error', prepare)
        self.assertNotIn('continue-on-error', product)

    def test_complete_fallback_isolates_disposable_git_background_writers(self):
        import yaml
        steps = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        fallback = next(step for step in steps if 'build/host-tests-env/bin/python trusted/tools/test-evidence/validate-sync.py'
                        in step.get('run', ''))
        self.assertIn("inputs.mode == 'fallback'", fallback['if'])
        self.assertNotEqual(fallback.get('working-directory'), 'candidate')
        self.assertNotIn('git config --global', fallback['run'])
        self.assertNotIn('continue-on-error', fallback)
        # Background-writer policy now belongs to the shared trusted controller,
        # applying equally to qualification, reuse, and fallback subprocesses.
        directory = ROOT / 'tools/test-evidence'
        spec = importlib.util.spec_from_file_location('workflow_contract_execution', directory / 'execution.py')
        execution = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, 'path', [str(directory), *sys.path]), mock.patch.dict(sys.modules):
            spec.loader.exec_module(execution)
            hostile = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'maintenance.auto',
                       'GIT_CONFIG_VALUE_0': 'true', 'GIT_CONFIG_KEY_9': 'gc.auto', 'GIT_CONFIG_VALUE_9': '1',
                       'GH_TOKEN': 'fixture-private', 'GITHUB_TOKEN': 'fixture-private',
                       'GITHUB_ENV': '/fixture/private-command-file', 'GITHUB_OUTPUT': '/fixture/private-command-file'}
            with mock.patch.dict(os.environ, hostile):
                before = dict(os.environ)
                with execution.candidate_process_environment():
                    self.assertEqual(os.environ['GIT_CONFIG_COUNT'], '2')
                    self.assertNotIn('GIT_CONFIG_KEY_9', os.environ)
                    for variable in ('GH_TOKEN', 'GITHUB_TOKEN', 'GITHUB_ENV', 'GITHUB_OUTPUT'):
                        self.assertNotIn(variable, os.environ)
                    for key, expected in (('maintenance.auto', 'false'), ('gc.auto', '0')):
                        observed = subprocess.check_output(['git', 'config', '--get', key], text=True).strip()
                        self.assertEqual(observed, expected)
                self.assertEqual(dict(os.environ), before, 'Trusted API/runtime operations retain their original environment')

    def test_parent_evidence_stays_bound_to_the_successful_exact_push(self):
        source = self.workflows["parent"]
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn("PARENT_COMMIT: ${{ github.sha }}", source)
        self.assertIn("RUN_ATTEMPT: ${{ github.run_attempt }}", source)
        self.assertIn("RUN_ID: ${{ github.run_id }}", source)

        self.assertIn("cancel-in-progress: false", source)
        self.assertLess(source.index("trusted/tools/test-evidence/run.py"), source.index("qualification.py"))
        self.assertIn('trusted/tools/sync-test-reuse/qualification.py', source)
        self.assertIn('--execution-receipt build/parent-qualification/execution.json', source)
        self.assertIn('--receipt build/parent-qualification/execution.json', source)
        self.assertIn('--candidate candidate', source)
        steps = workflow_data(source)['jobs']['qualify-parent']['steps']
        create = next(step for step in steps if step['name'] == 'Create content-addressed qualification evidence')
        upload = next(step for step in steps if step['name'] == 'Upload immutable qualification evidence')
        for step in (create, upload):
            self.assertEqual(step['if'], "steps.route.outputs.package_host_mode == 'full'")
        self.assertIn('Check only affected tool dependencies and behavior', source)
        self.assertNotIn('continue-on-error:', source)
        self.assertEqual(upload['with']['name'], 'parent-qualification-${{ github.sha }}')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')

    def test_parent_trusted_checkout_contains_transitive_host_requirements(self):
        import yaml
        workflow = yaml.safe_load(PARENT_QUALIFICATION_WORKFLOW.read_text())
        checkout = next(step['with'] for step in workflow['jobs']['qualify-parent']['steps']
                        if step.get('with', {}).get('path') == 'trusted')
        # File paths require non-cone mode. Every recursively included pip file
        # must exist in this checkout before installation/runtime fingerprinting.
        self.assertIs(checkout['sparse-checkout-cone-mode'], False)
        included = checkout['sparse-checkout'].split()
        pending = [ROOT / 'tests/requirements-host.txt']
        seen = set()
        while pending:
            path = pending.pop().resolve()
            if path in seen:
                continue
            seen.add(path)
            relative = path.relative_to(ROOT).as_posix()
            self.assertTrue(any(relative == entry or relative.startswith(entry.rstrip('/') + '/')
                                for entry in included), relative + ' is missing from trusted checkout')
            for line in path.read_text().splitlines():
                if line.strip().startswith('-r '):
                    pending.append(path.parent / line.strip()[3:].strip())

    def test_bounded_tool_sync_skips_product_and_host_prerequisites(self):
        import yaml
        steps = yaml.safe_load(SYNC_VALIDATION_WORKFLOW.read_text())['jobs']['validate']['steps']
        tools = next(step for step in steps if step['name'] == 'Verify bounded synchronization without product setup')
        self.assertEqual(tools['if'], "inputs.mode == 'reuse' && (inputs.profile == 'documentation' || inputs.profile == 'tool-dependencies')")
        self.assertEqual(tools['run'].split()[0], 'python3')
        self.assertIn('trusted/tools/test-evidence/validate-sync.py', tools['run'])
        self.assertIn('--mode reuse --profile "$PROFILE"', tools['run'])
        self.assertNotIn('apt-get', tools['run'])
        self.assertNotIn('host-tests-env', tools['run'])
        product = next(step for step in steps if 'build/host-tests-env/bin/python trusted/tools/test-evidence/validate-sync.py'
                       in step.get('run', ''))
        self.assertIn("inputs.profile != 'tool-dependencies'", product['if'])
        for step in steps:
            if 'apt-get' in step.get('run', '') or step.get('name') in {
                    'Set up candidate Java', 'Prepare isolated shared and product Python validators'}:
                self.assertEqual(step['if'], product['if'])






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
