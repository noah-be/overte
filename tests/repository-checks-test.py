#!/usr/bin/env python3
"""Negative routing, merge identity and aggregate-result regressions."""

from copy import deepcopy
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_checks", ROOT / "tools/repository-checks/check.py")
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)
CONFIG, BRANCHES = CHECKS.configuration()
TOOL_SPEC = importlib.util.spec_from_file_location(
    "tool_dependencies_test", ROOT / "tools/repository-checks/tool_dependencies.py")
TOOLS = importlib.util.module_from_spec(TOOL_SPEC)
TOOL_SPEC.loader.exec_module(TOOLS)


def event(base="main", head="fix/main/example", fork=False):
    repository = {"id": CONFIG["repository_id"], "full_name": CONFIG["repository"]}
    return {"repository": repository, "pull_request": {
        "base": {"ref": base, "repo": repository, "sha": "1" * 40},
        "head": {"ref": head, "repo": {"id": 123, "full_name": "contributor/fork"} if fork else repository,
                 "sha": "2" * 40}}}


def results(mode="full", security="true"):
    return {"route": {"result": "success", "outputs": {"mode": mode, "security": security, "native": "full"}},
            "project": {"result": "success" if mode in {"full", "tool-dependencies"} else "skipped"},
            "documentation": {"result": "success"},
            "native": {"result": "success"},
            "workflow-security": {"result": "success" if security == "true" else "skipped"}}


class RoutingTests(unittest.TestCase):
    def test_current_account_name_keeps_exact_repository_and_base_identity(self):
        self.assertEqual(CONFIG['repository'], 'noah-l-frank/overte')
        self.assertEqual(CONFIG['repository_id'], 1319052603)
        self.assertEqual(CHECKS.plan(event(), ['a.cpp'], CONFIG, BRANCHES)['mode'], 'full')
        for side in ('repository', 'base'):
            for change in ({'full_name': 'noah-be/overte'}, {'id': 42},
                           {'full_name': 'overte-org/overte'}):
                candidate = deepcopy(event())
                identity = (candidate['repository'] if side == 'repository'
                            else candidate['pull_request']['base']['repo'])
                identity.update(change)
                with self.subTest(side=side, change=change), self.assertRaises(ValueError):
                    CHECKS.plan(candidate, ['a.cpp'], CONFIG, BRANCHES)
        # A stale head name cannot claim same-repository sync delegation, even
        # with the real numeric repository ID.
        candidate = deepcopy(event('android-main', 'main'))
        candidate['pull_request']['head']['repo'] = {
            'full_name': 'noah-be/overte', 'id': 1319052603}
        self.assertEqual(CHECKS.plan(candidate, ['a.cpp'], CONFIG, BRANCHES)['mode'], 'full')

    def test_rename_does_not_bootstrap_the_old_default_branch_router(self):
        legacy = {**CONFIG, 'repository': 'noah-be/overte'}
        with self.assertRaisesRegex(ValueError, 'repository identity mismatch'):
            CHECKS.plan(event(), ['.github/repository-checks.json'], legacy, BRANCHES)
        manual = {'repository': deepcopy(event()['repository'])}
        with self.assertRaisesRegex(ValueError, 'repository mismatch'):
            CHECKS.native_required(legacy, manual)
        self.assertTrue(CHECKS.native_required(CONFIG, manual))
        manual['repository']['full_name'] = 'noah-be/overte'
        with self.assertRaisesRegex(ValueError, 'repository mismatch'):
            CHECKS.native_required(CONFIG, manual)

    def test_tool_manifests_select_only_the_affected_projects(self):
        for project in TOOLS.PROJECTS:
            for filename in ("package.json", "package-lock.json"):
                route = CHECKS.plan(event(), [f"{project}/{filename}", "docs/change.md"], CONFIG, BRANCHES)
                self.assertEqual(route, {"mode": "tool-dependencies", "security": "false",
                                         "tool_projects": project})
        route = CHECKS.plan(event(), sorted(TOOLS.MANIFESTS), CONFIG, BRANCHES)
        self.assertEqual(route["tool_projects"], "server-console,tools/jsdoc")

    def test_tool_route_does_not_cover_source_build_unknown_or_nonregular_changes(self):
        manifests = ["tools/jsdoc/package-lock.json"]
        for path in ("interface/src/Application.cpp", "tools/jsdoc/CMakeLists.txt",
                     "tools/jsdoc/plugins/hifi.js", "tools/jsdoc/unknown.json", "server-console/src/main.js",
                     "tools/repository-checks/tool_dependencies.py", ".github/workflows/project-tests.yml",
                     "browser-client/package-lock.json", "docs/image.png"):
            self.assertEqual(CHECKS.plan(event(), manifests + [path], CONFIG, BRANCHES)["mode"], "full")
        self.assertEqual(CHECKS.plan(event(), manifests, CONFIG, BRANCHES,
                                     documentation_safe=False)["mode"], "full")
        route = CHECKS.plan(event("android-main", "main"), manifests, CONFIG, BRANCHES)
        self.assertEqual(route["mode"], "delegated-sync")
        self.assertNotIn("tool_projects", route)

    def test_previously_uncovered_and_unknown_paths_run_project_checks(self):
        for path in ("CMakeLists.txt", "cmake/compiler.cmake", "assignment-client/src/Agent.cpp",
                     "domain-server/src/DomainServer.cpp", "ice-server/src/main.cpp",
                     "plugins/example.cpp", "tools/new-tool.py", "new-area/future.unknown",
                     "android/reintroduced.cpp"):
            with self.subTest(path=path):
                self.assertEqual(CHECKS.plan(event(), [path], CONFIG, BRANCHES)["mode"], "full")

    def test_only_markdown_can_take_documentation_route(self):
        self.assertEqual(CHECKS.plan(event(), ["README.md", "docs/a.md"], CONFIG, BRANCHES),
                         {"mode": "documentation", "security": "false"})
        for paths in ([], ["docs/a.md", "docs/image.png"], ["README.md", "tools/check.py"]):
            self.assertEqual(CHECKS.plan(event(), paths, CONFIG, BRANCHES)["mode"], "full")
        self.assertEqual(CHECKS.plan(event(), ["README.md"], CONFIG, BRANCHES,
                                     documentation_safe=False)["mode"], "full")

    def test_governance_and_security_changes_require_security_checks(self):
        for path in (".github/workflows/new.yml", ".github/repository-checks.json",
                     ".github/rulesets/README.md", "tools/repository-checks/check.py",
                     "tools/workflow-security/check-action-pins.py"):
            self.assertEqual(CHECKS.plan(event(), [path], CONFIG, BRANCHES)["security"], "true")

    def test_only_same_repository_direct_edges_or_scoped_reconciliations_delegate(self):
        for target, value in BRANCHES.items():
            if not value["parent"]:
                continue
            for head in (value["parent"], f"reconcile/{value['scope']}/reviewed-merge"):
                self.assertEqual(CHECKS.plan(event(target, head), ["a.cpp"], CONFIG, BRANCHES)["mode"],
                                 "delegated-sync")
                self.assertEqual(CHECKS.plan(event(target, head, fork=True), ["a.cpp"], CONFIG, BRANCHES)["mode"],
                                 "full")
        for base, head in (("main", "android-main"), ("android-phone", "main"),
                           ("android-phone", "apple-main"), ("android-phone", "sync/android-phone/x"),
                           ("android-phone", "reconcile/android/x")):
            self.assertEqual(CHECKS.plan(event(base, head), ["a.cpp"], CONFIG, BRANCHES)["mode"], "full")

    def test_foreign_base_and_invalid_paths_fail(self):
        wrong = deepcopy(event())
        wrong["repository"]["full_name"] = "overte-org/overte"
        with self.assertRaises(ValueError):
            CHECKS.plan(wrong, ["a.cpp"], CONFIG, BRANCHES)
        for path in ("../escape.md", "/absolute.md", "bad\x00name", ""):
            with self.assertRaises(ValueError):
                CHECKS.plan(event(), [path], CONFIG, BRANCHES)


class AggregateTests(unittest.TestCase):
    def test_tool_checks_cannot_be_skipped_or_hide_a_failure(self):
        for conclusion in ("skipped", "cancelled", "failure", "neutral", "pending"):
            candidate = results("tool-dependencies", "false")
            candidate["project"]["result"] = conclusion
            with self.assertRaises(ValueError):
                CHECKS.verify(candidate)

    def test_valid_full_documentation_and_delegated_modes(self):
        for mode in CHECKS.MODES:
            for security in ("true", "false"):
                self.assertEqual(CHECKS.verify(results(mode, security))["status"], "PASS")
        self.assertEqual(CHECKS.verify(results("delegated-sync"))["delegated_requirement"], "sync-test-reuse")

    def test_failure_cancellation_missing_and_required_skips_fail(self):
        for job in results():
            for result in ("failure", "cancelled", "skipped", "neutral", "pending", None):
                with self.subTest(job=job, result=result):
                    candidate = results()
                    candidate[job]["result"] = result
                    with self.assertRaises(ValueError):
                        CHECKS.verify(candidate)
            candidate = results()
            del candidate[job]
            with self.assertRaises(ValueError):
                CHECKS.verify(candidate)

    def test_invalid_route_and_unexpected_executions_do_not_hide_failures(self):
        for outputs in ({}, {"mode": "ordinary", "security": "false"},
                        {"mode": "full", "security": "maybe"}):
            candidate = results()
            candidate["route"]["outputs"] = outputs
            with self.assertRaises(ValueError):
                CHECKS.verify(candidate)
        candidate = results("documentation", "false")
        candidate["project"]["result"] = "failure"
        with self.assertRaises(ValueError):
            CHECKS.verify(candidate)

    def test_scoped_native_activation_uses_the_trusted_base_not_head(self):
        config = {**CONFIG, "native_required": False, "native_required_branches": ["main"]}
        legacy = results()
        del legacy["native"]
        del legacy["route"]["outputs"]["native"]
        for head in ("fix/main/example", "apple-ios", "main"):
            self.assertTrue(CHECKS.native_required(config, event("main", head)))
            with self.assertRaises(ValueError):
                CHECKS.verify(legacy, CHECKS.native_required(config, event("main", head)))
        for target in ("apple-main", "apple-ios", "android-main", "android-phone"):
            self.assertFalse(CHECKS.native_required(config, event(target, "main")))
            self.assertEqual(CHECKS.verify(legacy, CHECKS.native_required(config, event(target)))["status"], "PASS")
        manual = {"repository": event()["repository"], "ref": "refs/heads/main"}
        self.assertTrue(CHECKS.native_required(config, manual))
        self.assertTrue(CHECKS.native_required({**config, "native_required": True}, event("apple-ios")))
        self.assertFalse(CHECKS.native_required({**config, "native_required_branches": []}, None))
        for invalid in (None, {}, {"repository": {"full_name": "overte-org/overte", "id": 1}}):
            with self.assertRaises(ValueError):
                CHECKS.native_required(config, invalid)
        wrong = deepcopy(event())
        wrong["pull_request"]["base"]["repo"] = {"full_name": "contributor/fork", "id": 123}
        with self.assertRaises(ValueError):
            CHECKS.native_required(config, wrong)

    def test_legacy_cli_inherits_the_runner_event_for_scoped_activation(self):
        legacy = results()
        del legacy["native"]
        del legacy["route"]["outputs"]["native"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'event.json'
            for target in ('main', 'apple-ios'):
                payload = event(target)
                path.write_text(json.dumps(payload))
                result = subprocess.run([sys.executable, str(ROOT / 'tools/repository-checks/check.py'),
                                         'verify', '--needs-json', json.dumps(legacy)],
                                        env={**os.environ, 'GITHUB_EVENT_PATH': str(path)}, capture_output=True)
                self.assertEqual(result.returncode == 0, not CHECKS.native_required(CONFIG, payload),
                                 result.stderr.decode())

    def test_cli_returns_nonzero_for_failed_aggregate(self):
        candidate = results()
        candidate["documentation"]["result"] = "failure"
        result = subprocess.run([sys.executable, str(ROOT / "tools/repository-checks/check.py"),
                                 "verify", "--needs-json", json.dumps(candidate)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_manifest_keeps_both_aggregate_and_independent_sync_gate_required(self):
        manifest = json.loads((ROOT / ".github/rulesets/permanent-branches.json").read_text())
        required = next(rule for rule in manifest["rules"] if rule["type"] == "required_status_checks")
        entries = required["parameters"]["required_status_checks"]
        self.assertEqual({item["context"] for item in entries}, set(CONFIG["required_contexts"]))
        self.assertTrue(all(item["integration_id"] == 15368 for item in entries))
        source = (ROOT / ".github/workflows/repository-checks.yml").read_text()
        self.assertIn("if: always()", source)
        dependencies = "route, project, documentation, workflow-security"
        if CONFIG.get("native_required", False) or "main" in CONFIG.get("native_required_branches", []):
            dependencies += ", native"
        else:
            dependencies += "(?:, native)?"
        dependencies += (", direct-browser" if "main" in CONFIG.get("direct_browser_required_branches", [])
                         else "(?:, direct-browser)?")
        self.assertRegex(source, r"needs: \[" + dependencies + r"\]")
        self.assertNotIn("paths:", source)
        self.assertNotIn("secrets:", source)
        self.assertNotIn("secrets.", source)
        self.assertNotIn(": write", source)

    def test_reusable_concurrency_groups_do_not_cancel_the_caller(self):
        workflows = ROOT / ".github/workflows"
        groups = []
        for name in ("repository-checks.yml", "project-tests.yml", "documentation-checks.yml", "workflow-security.yml"):
            text = (workflows / name).read_text()
            groups.append(text.split("  group: ", 1)[1].splitlines()[0])
        self.assertEqual(len(groups), len(set(groups)))
        self.assertTrue(all("github.workflow" not in group for group in groups))

    def test_new_governance_inputs_are_bound_to_parent_qualification(self):
        import fnmatch
        reuse = json.loads((ROOT / ".github/sync-test-reuse.json").read_text())
        for path in (".github/repository-checks.json", ".github/repository-health.json",
                     "tools/repository-checks/check.py", "tools/repository-maintenance/check.py",
                     "tools/repository-policy/check.py", "tools/repository-health/check.py",
                     "tests/requirements-repository.txt"):
            self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in reuse["qualified_inputs"]), path)


class DirectBrowserTests(unittest.TestCase):
    def test_prospective_transport_wiring_requires_selected_jobs_and_shared_fixtures(self):
        import ast
        import yaml
        templates = ROOT / 'tools/repository-checks/workflows'
        workflow = yaml.safe_load((templates / 'browser-direct-client.yml').read_text())
        caller = yaml.safe_load((templates / 'repository-checks.yml').read_text())
        triggers = workflow.get('on', workflow.get(True))
        self.assertIn('workflow_call', triggers)
        self.assertNotIn('pull_request', triggers, 'The aggregate replaces the standalone PR consumer')
        jobs = workflow['jobs']
        self.assertEqual(set(jobs['verify']['needs']), {'route', 'browser', 'native'})
        self.assertEqual(jobs['verify']['if'], 'always()')
        for lane, output in (('browser', 'direct_browser'), ('native', 'direct_native')):
            self.assertEqual(jobs[lane]['needs'], 'route')
            self.assertEqual(jobs[lane]['if'], f"needs.route.outputs.{output} == 'true'")
        verifier = next(step for step in jobs['verify']['steps'] if step.get('id') == 'verify')
        self.assertIn('trusted/tools/repository-checks/check.py direct-verify', verifier['run'])
        self.assertIn('--needs-json "$DIRECT_RESULTS"', verifier['run'])
        self.assertIn('--sha "$GITHUB_SHA"', verifier['run'])
        self.assertIn('direct-browser', caller['jobs']['repository-checks']['needs'])
        consumer = caller['jobs']['direct-browser']
        self.assertEqual(consumer['uses'], './.github/workflows/browser-direct-client.yml')
        self.assertEqual(consumer['permissions'], {'contents': 'read', 'packages': 'read'})
        self.assertEqual(set(consumer['with']), {'expected_candidate', 'expected_plan',
                                                'browser_required', 'native_required'})
        aggregate = caller['jobs']['repository-checks']['steps'][-1]
        self.assertIn('--candidate candidate --sha "$GITHUB_SHA"', aggregate['run'])
        # These browser JSON files are read by actual C++ tests, so an extension-
        # only frontend exemption would silently miss a required native consumer.
        fixtures = set()
        for source in (ROOT / 'tests/browser-direct-transport/src').glob('*.cpp'):
            fixtures.update(re.findall(r'QFINDTESTDATA\("\.\./\.\./\.\./(browser-direct-client/[^\"]+)"\)',
                                       source.read_text()))
        self.assertTrue(fixtures)
        for fixture in fixtures:
            selected = CHECKS.direct_browser_plan([fixture])
            self.assertTrue(selected['browser'] and selected['native'], fixture)
        driver = ast.parse((ROOT / 'browser-direct-client/tools/ci-native.py').read_text())
        for node in ast.walk(driver):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith(('tools/native-tests/', 'tools/conan-profiles/'))):
                self.assertTrue(CHECKS.direct_browser_plan([node.value])['native'], node.value)

    def test_push_routing_cannot_omit_transitive_dependencies(self):
        import yaml
        workflow = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/browser-direct-client.yml').read_text())
        events = workflow.get('on', workflow.get(True))
        push = events['push']
        self.assertEqual(set(push), {'branches'})
        self.assertEqual(set(push['branches']), set(BRANCHES))
        for path in ('LICENSE', 'interface/resources/meshes/mannequin/mannequin.fbx',
                     'libraries/shared/src/Constants.h', 'libraries/avatars/src/AvatarData.cpp',
                     'libraries/audio/src/AudioConstants.h', 'tools/native-tests/packages.py',
                     'CMakeLists.txt', 'conanfile.py'):
            selected = CHECKS.direct_browser_plan([path])
            self.assertTrue(selected['browser'] or selected['native'], path)

    def candidate_plan(self, browser=True, native=False):
        return {"browser": browser, "native": native, "candidate": "a" * 40, "plan": "b" * 64}

    def inner_results(self, selected):
        return {"route": {"result": "success", "outputs": CHECKS.direct_outputs(selected)},
                **{lane: {"result": "success" if selected[lane] else "skipped"}
                   for lane in ("browser", "native")}}

    def outer_results(self, selected):
        candidate = results()
        candidate["route"]["outputs"].update(CHECKS.direct_outputs(selected))
        candidate["direct-browser"] = {"result": "success", "outputs": {
            "verified": "true", "candidate": selected["candidate"], "plan": selected["plan"]}}
        if not selected["browser"] and not selected["native"]:
            candidate["direct-browser"] = {"result": "skipped", "outputs": {}}
        return candidate

    def test_frontend_docs_and_lab_tools_do_not_build_native_products(self):
        for path in ("browser-direct-client/src/world.ts", "browser-direct-client/src/style.css",
                     "browser-direct-client/package-lock.json", "browser-direct-client/lab/build-native.py",
                     "browser-direct-client/e2e/native-build-evidence.test.py", "browser-direct-client/README.md"):
            with self.subTest(path=path):
                self.assertFalse(CHECKS.direct_browser_plan([path])["native"])
        self.assertTrue(CHECKS.direct_browser_plan(["browser-direct-client/src/world.ts"])["browser"])
        self.assertFalse(CHECKS.direct_browser_plan(["browser-direct-client/README.md"])["browser"])
        for path in ("tools/repository-checks/check.py", "tests/repository-checks-test.py", "docs/ci.md",
                     "tools/test-evidence/execution.py", "tools/test-evidence/fixture.json"):
            self.assertEqual(CHECKS.direct_browser_plan([path]),
                             {"browser": False, "native": False, "reasons": {"browser": [], "native": []}})
        for path in CHECKS.DIRECT_UNRELATED_NATIVE_TOOLS:
            selected = CHECKS.direct_browser_plan([path])
            self.assertFalse(selected["browser"] or selected["native"], path)

    def test_s3_npm_manifests_do_not_select_optional_browser_or_native_products(self):
        manifests = ["script-archive/marketplace/S3Server/package.json",
                     "script-archive/marketplace/S3Server/package-lock.json"]
        empty = {"browser": False, "native": False,
                 "reasons": {"browser": [], "native": []}}
        self.assertEqual(CHECKS.direct_browser_plan(manifests), empty)
        for path in manifests:
            self.assertEqual(CHECKS.direct_browser_plan([path]), empty)
            self.assertTrue(CHECKS.direct_browser_plan([path], False)["native"])
            self.assertTrue(CHECKS.direct_browser_plan([path, "libraries/shared/src/AABox.cpp"])["native"])
        for name in ("CMakeLists.txt", "input.cmake", "resources.qrc", "unknown.json", "new.cpp"):
            self.assertTrue(CHECKS.direct_browser_plan(
                [*manifests, f"script-archive/marketplace/S3Server/{name}"])["native"])
        browser = CHECKS.direct_browser_plan(
            [*manifests, "browser-direct-client/package-lock.json"])
        self.assertTrue(browser["browser"])
        self.assertFalse(browser["native"])

    def test_native_fixtures_libraries_and_complete_build_context_require_transport(self):
        paths = sorted(CHECKS.DIRECT_NATIVE_FIXTURES) + [
            "libraries/avatars/src/AvatarData.cpp", "libraries/audio/src/AudioConstants.h",
            "libraries/shared/src/GLMHelpers.h", "libraries/script-engine/src/ScriptEngine.cpp",
            "libraries/model-networking/src/ModelCache.cpp", "libraries/new-component/src/input.h",
            "domain-server/src/LocalUserPolicy.h", "assignment-client/src/entities/BrowserEntityProjection.h",
            "tests/browser-direct-transport/src/WebRTCTransportTests.cpp", "tests/networking/src/PacketTests.cpp",
            "cmake/macros/TargetDataChannel.cmake", "CMakeLists.txt", "conanfile.py", "conan.lock",
            ".github/native-tests.json", "tools/native-tests/conan-linux.lock", "tools/conan-profiles/linux",
            "browser-direct-client/tools/ci-native.py", "browser-direct-client/lab/new.cpp",
            "browser-direct-client/lab/CMakeLists.txt", "browser-direct-client/new.unknown",
            "tools/test-evidence/new.cpp", "tools/test-evidence/new.unknown"]
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(CHECKS.direct_browser_plan([path])["native"])
        for path in CHECKS.DIRECT_NATIVE_FIXTURES:
            self.assertTrue(CHECKS.direct_browser_plan([path])["browser"])
        mixed = CHECKS.direct_browser_plan(["browser-direct-client/src/world.ts", paths[0]])
        self.assertTrue(mixed["browser"] and mixed["native"])

    def test_browser_generation_assets_and_nonregular_unknown_inputs_are_not_omitted(self):
        for path in CHECKS.DIRECT_BROWSER_ASSETS | {"libraries/networking/src/udt/PacketHeaders.cpp"}:
            self.assertTrue(CHECKS.direct_browser_plan([path])["browser"], path)
        for paths, regular in (([], True), (["browser-direct-client/README.md"], False),
                               (["unowned/new-input"], True)):
            selected = CHECKS.direct_browser_plan(paths, regular)
            self.assertTrue(selected["browser"] and selected["native"])
        self.assertFalse(CHECKS.direct_browser_plan([], verified_empty=True)["native"])
        with self.assertRaises(ValueError):
            CHECKS.direct_browser_plan(["a"], verified_empty=True)
        for path in ("../outside", "/absolute", "", "bad\x00path", "bad\\path", 123):
            with self.subTest(path=path), self.assertRaises(ValueError):
                CHECKS.direct_browser_plan([path])

    def test_inner_selected_failure_skip_missing_and_misbound_route_fail(self):
        selected = self.candidate_plan(True, True)
        good = self.inner_results(selected)
        self.assertEqual(CHECKS.verify_direct(good, selected)["verified"], "true")
        for lane in ("route", "browser", "native"):
            for conclusion in ("failure", "skipped", "cancelled", None):
                bad = deepcopy(good)
                bad[lane]["result"] = conclusion
                with self.subTest(lane=lane, conclusion=conclusion), self.assertRaises(ValueError):
                    CHECKS.verify_direct(bad, selected)
            bad = deepcopy(good)
            del bad[lane]
            with self.assertRaises(ValueError):
                CHECKS.verify_direct(bad, selected)
        for field in CHECKS.direct_outputs(selected):
            bad = deepcopy(good)
            bad["route"]["outputs"][field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                CHECKS.verify_direct(bad, selected)
        unselected = self.candidate_plan(True, False)
        good = self.inner_results(unselected)
        self.assertEqual(CHECKS.verify_direct(good, unselected)["verified"], "true")
        good["native"]["result"] = "success"
        with self.assertRaises(ValueError):
            CHECKS.verify_direct(good, unselected)

    def test_outer_receipt_is_required_even_before_branch_activation(self):
        selected = self.candidate_plan()
        good = self.outer_results(selected)
        self.assertEqual(CHECKS.verify(good, direct_plan=selected)["status"], "PASS")
        with self.assertRaises(ValueError):
            CHECKS.verify(good)
        for field in ("candidate", "plan", "verified"):
            bad = deepcopy(good)
            bad["direct-browser"]["outputs"][field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                CHECKS.verify(bad, direct_plan=selected)
        for conclusion in ("failure", "skipped", "cancelled", None):
            bad = deepcopy(good)
            bad["direct-browser"]["result"] = conclusion
            with self.assertRaises(ValueError):
                CHECKS.verify(bad, direct_plan=selected)
        good["route"]["outputs"]["direct_native"] = "true"
        with self.assertRaises(ValueError):
            CHECKS.verify(good, direct_plan=selected)
        empty = self.candidate_plan(False, False)
        self.assertEqual(CHECKS.verify(self.outer_results(empty), direct_plan=empty)["status"], "PASS")

    def test_only_trusted_base_activation_permits_legacy_omission(self):
        config = {**CONFIG, "direct_browser_required_branches": ["main"]}
        self.assertFalse(CHECKS.direct_browser_required({**config, "direct_browser_required_branches": []}, None))
        for head in ("fix/main/example", "apple-ios", "main"):
            self.assertTrue(CHECKS.direct_browser_required(config, event("main", head)))
        for base in ("apple-ios", "android-main", "android-vr-pico"):
            self.assertFalse(CHECKS.direct_browser_required(config, event(base, "main")))
        self.assertEqual(CHECKS.verify(results(), require_direct=False)["status"], "PASS")
        with self.assertRaisesRegex(ValueError, "aggregate missing"):
            CHECKS.verify(results(), require_direct=True)
        for payload in (None, {}, {"repository": {"full_name": "overte-org/overte", "id": 1}}):
            with self.assertRaises(ValueError):
                CHECKS.direct_browser_required(config, payload)
        bad = event()
        bad["pull_request"]["base"]["repo"] = {"full_name": "contributor/fork", "id": 12}
        with self.assertRaises(ValueError):
            CHECKS.direct_browser_required(config, bad)

    def test_candidate_plan_cli_rechecks_exact_merge_tree_and_trusted_templates(self):
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            def git(*args):
                return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null",
                                                "-c", "commit.gpgsign=false", *args],
                                               cwd=candidate, text=True, stderr=subprocess.PIPE).strip()
            git("init", "-q", "--initial-branch=main")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            workflows = candidate / ".github/workflows"
            workflows.mkdir(parents=True)
            for name in CHECKS.DIRECT_WORKFLOWS:
                (workflows / name).write_bytes((ROOT / "tools/repository-checks/workflows" / name).read_bytes())
            source = candidate / "browser-direct-client/lab/manage.py"
            source.parent.mkdir(parents=True)
            source.write_text("# before\n")
            git("add", ".")
            git("commit", "-qm", "Base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "fix/main/example")
            source.write_text("# after\n")
            git("add", ".")
            git("commit", "-qm", "Head")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "-qm", "Candidate", "fix/main/example")
            sha = git("rev-parse", "HEAD")
            payload = event()
            payload["pull_request"]["base"]["sha"] = base
            payload["pull_request"]["head"]["sha"] = head
            selected = CHECKS.direct_candidate_plan(candidate, payload, sha)
            self.assertTrue(selected["browser"])
            self.assertFalse(selected["native"])
            push = {"repository": payload["repository"], "before": base, "after": sha}
            pushed = CHECKS.direct_candidate_plan(candidate, push, sha)
            self.assertTrue(pushed["browser"])
            self.assertFalse(pushed["native"])
            empty = CHECKS.direct_candidate_plan(candidate, {**push, "before": sha}, sha)
            self.assertFalse(empty["browser"] or empty["native"])
            with self.assertRaises(ValueError):
                CHECKS.direct_candidate_plan(candidate, {**push, "after": head}, sha)
            CHECKS.validate_direct_wiring(candidate)
            event_file, output = candidate / "event.json", candidate / "outputs"
            event_file.write_text(json.dumps(payload))
            common = ["--event", str(event_file), "--candidate", str(candidate), "--sha", sha]
            command = [sys.executable, str(ROOT / "tools/repository-checks/check.py")]
            run = subprocess.run(command + ["direct-plan", *common, "--output", str(output),
                                           "--expected-candidate", sha, "--expected-plan", selected["plan"],
                                           "--expected-browser", "true", "--expected-native", "false"], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            run = subprocess.run(command + ["direct-plan", *common, "--output", str(output),
                                           "--expected-candidate", sha, "--expected-plan", selected["plan"],
                                           "--expected-browser", "true", "--expected-native", "true"], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            run = subprocess.run(command + ["direct-verify", *common, "--output", str(output),
                                           "--needs-json", json.dumps(self.inner_results(selected))], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            outer = self.outer_results(selected)
            run = subprocess.run(command + ["verify", *common, "--needs-json", json.dumps(outer)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            outer["direct-browser"]["outputs"]["plan"] = "0" * 64
            run = subprocess.run(command + ["verify", *common, "--needs-json", json.dumps(outer)], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            with self.assertRaises(ValueError):
                CHECKS.direct_candidate_plan(candidate, payload, head)
            changed = workflows / "browser-direct-client.yml"
            changed.write_text(changed.read_text().replace("    if: always()", "    if: false"))
            with self.assertRaises(ValueError):
                CHECKS.validate_direct_wiring(candidate)
            changed.unlink()
            changed.symlink_to(ROOT / "tools/repository-checks/workflows/browser-direct-client.yml")
            with self.assertRaises(ValueError):
                CHECKS.validate_direct_wiring(candidate)


class ToolDependencyTests(unittest.TestCase):
    def test_push_inventory_uses_both_sides_and_exact_commit_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null',
                                                '-c', 'commit.gpgsign=false', *args], cwd=root, text=True).strip()
            git('init', '-q', '--initial-branch=main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / 'tools/jsdoc').mkdir(parents=True)
            manifest = root / 'tools/jsdoc/package-lock.json'
            manifest.write_text('{}')
            (root / 'native.cpp').write_text('initial source')
            git('add', '.')
            git('commit', '-qm', 'Base')
            base = git('rev-parse', 'HEAD')
            manifest.write_text('{"updated":true}')
            git('commit', '-qam', 'Tool update')
            updated = git('rev-parse', 'HEAD')
            payload = {'repository': event()['repository'], 'before': base, 'after': updated}
            self.assertEqual(TOOLS.push_projects(root, payload), ('tools/jsdoc',))
            for repository in ({'full_name': 'noah-be/overte', 'id': 1319052603},
                               {'full_name': 'noah-l-frank/overte', 'id': 42}):
                with self.subTest(repository=repository), self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    TOOLS.push_projects(root, {**payload, 'repository': repository})
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'before': '9' * 40}), ())
            with self.assertRaises(ValueError):
                TOOLS.push_projects(root, {**payload, 'after': base})
            with self.assertRaises(ValueError):
                TOOLS.push_projects(root, {**payload, 'repository': {'full_name': 'overte-org/overte', 'id': 1}})
            manifest.chmod(0o755)
            git('commit', '-qam', 'Executable manifest')
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'after': git('rev-parse', 'HEAD')}), ())
            manifest.chmod(0o644)
            (root / 'native.cpp').write_text('source')
            git('add', '.')
            git('commit', '-qm', 'Mixed source update')
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'after': git('rev-parse', 'HEAD')}), ())
            git('mv', 'native.cpp', 'server-console-package-lock.md')
            git('commit', '-qm', 'Rename source to Markdown')
            self.assertEqual(TOOLS.push_projects(root, {**payload, 'after': git('rev-parse', 'HEAD')}), ())
            self.assertEqual(TOOLS.push_projects(root, {}), ())

    def test_unknown_duplicate_and_empty_projects_are_rejected_before_execution(self):
        with patch.object(TOOLS.subprocess, "run") as run:
            for projects in ([], ["browser-client"], ["tools/jsdoc", "tools/jsdoc"], ["../tools/jsdoc"]):
                with self.assertRaises(ValueError):
                    TOOLS.run(ROOT, projects)
            run.assert_not_called()

    def test_install_or_audit_failure_stops_before_behavior_checks(self):
        for fail_at in (0, 1):
            failure = subprocess.CalledProcessError(1, "npm")
            with patch.object(TOOLS.subprocess, "run", side_effect=[None] * fail_at + [failure]) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    TOOLS.run(ROOT, ["server-console"])
                self.assertEqual(run.call_count, fail_at + 1)

    def test_dependency_install_disables_scripts_and_the_audit_includes_all_severities(self):
        with patch.object(TOOLS.subprocess, "run") as run:
            TOOLS.run(ROOT, ["server-console"])
            calls = [call.args[0] for call in run.call_args_list]
            self.assertIn("--ignore-scripts", calls[0])
            self.assertEqual(calls[1], ("npm", "audit", "--audit-level=low"))
            self.assertEqual(calls[2], ("npm", "test"))
            self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))


class CandidateTests(unittest.TestCase):
    def test_exact_merge_paths_and_stale_candidate_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c",
                                                 "core.hooksPath=/dev/null", *args], cwd=root,
                                                text=True, stderr=subprocess.PIPE).strip()
            git("init", "-q", "--initial-branch=main")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (root / "README.md").write_text("# Initial\n")
            git("add", ".")
            git("commit", "-qm", "Base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "fix/main/example")
            (root / "README.md").write_text("# Changed\n")
            git("commit", "-qam", "Documentation")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "--no-edit", "fix/main/example")
            merge = git("rev-parse", "HEAD")
            value = event()
            value["pull_request"]["base"]["sha"] = base
            value["pull_request"]["head"]["sha"] = head
            self.assertEqual(CHECKS.changed_paths(root, value, merge), (["README.md"], True))
            with self.assertRaises(ValueError):
                CHECKS.changed_paths(root, value, head)
            value["pull_request"]["base"]["sha"] = head
            with self.assertRaises(ValueError):
                CHECKS.changed_paths(root, value, merge)
            git("checkout", "-q", "fix/main/example")
            (root / "README.md").chmod(0o755)
            git("commit", "-qam", "Executable Markdown is not documentation only")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            base = git("rev-parse", "HEAD")
            git("merge", "--no-ff", "--no-edit", "fix/main/example")
            merge = git("rev-parse", "HEAD")
            value["pull_request"]["base"]["sha"] = base
            value["pull_request"]["head"]["sha"] = head
            self.assertEqual(CHECKS.changed_paths(root, value, merge), (["README.md"], False))


if __name__ == "__main__":
    unittest.main()
