#!/usr/bin/env python3
"""Negative routing, merge identity and aggregate-result regressions."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_checks", ROOT / "tools/repository-checks/check.py")
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)
CONFIG, BRANCHES = CHECKS.configuration()


def event(base="main", head="fix/main/example", fork=False):
    repository = {"id": CONFIG["repository_id"], "full_name": CONFIG["repository"]}
    return {"repository": repository, "pull_request": {
        "base": {"ref": base, "repo": repository, "sha": "1" * 40},
        "head": {"ref": head, "repo": {"id": 123, "full_name": "contributor/fork"} if fork else repository,
                 "sha": "2" * 40}}}


def results(mode="full", security="true"):
    return {"route": {"result": "success", "outputs": {"mode": mode, "security": security}},
            "project": {"result": "success" if mode == "full" else "skipped"},
            "documentation": {"result": "success"},
            "workflow-security": {"result": "success" if security == "true" else "skipped"}}


class RoutingTests(unittest.TestCase):
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
        self.assertIn("needs: [route, project, documentation, workflow-security]", source)
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
