#!/usr/bin/env python3
"""Real-Git regressions for dormant trusted Browser CPU-history selection."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/repository-checks/browser_cpu.py"
SPEC = importlib.util.spec_from_file_location("browser_cpu_selection", HELPER)
BROWSER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BROWSER)
LEGACY = (ROOT / BROWSER.WORKFLOW).read_bytes()


class BrowserCpuTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Browser selection fixture")
        self.git("config", "user.email", "browser-selection@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("CMakeLists.txt", b"project(BrowserFixture)\n")
        self.write("browser-client/package.json", b'{"scripts":{"test":"node --test"}}\n')
        self.write("browser-client/package-lock.json", b'{"lockfileVersion":3}\n')
        self.write("browser-client/src/Main.ts", b"export const production = true;\n")
        self.write(BROWSER.WORKFLOW, LEGACY)
        for path in BROWSER.CPU_PATHS:
            self.write(path, b"Reviewed CPU fixture source\n")
        self.base = self.commit("Create isolated reviewed Browser readers")
        # Explicit isolated fixture review; never refresh production anchors.
        anchor = BROWSER.review_boundary(self.root, self.base)["boundary"]
        replacement = patch.object(BROWSER, "REVIEWED_BOUNDARY", anchor)
        replacement.start()
        self.addCleanup(replacement.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                              text=True, check=True, timeout=30).stdout.strip()

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message, *, stage=True):
        if stage:
            self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def classify(self, candidate, base=None):
        return BROWSER.classify(BROWSER.snapshot(self.root, base or self.base),
                                BROWSER.snapshot(self.root, candidate))

    def activate_fixture(self):
        self.write(BROWSER.WORKFLOW, BROWSER.canonical_workflow())
        self.base = self.commit("Integrate exact reviewed fixture orchestration")

    def merge(self, changes, *, base=None):
        base = base or self.base
        self.git("checkout", "-q", "--detach", base)
        for path, data in changes.items():
            self.write(path, data)
        head = self.commit("Change reviewed fixture inputs")
        self.git("checkout", "-q", "-B", "merge-fixture", base)
        self.git("merge", "-q", "--no-ff", "-m", "Merge exact browser fixture", head)
        candidate = self.git("rev-parse", "HEAD")
        event = {"repository": dict(BROWSER.REPOSITORY), "pull_request": {
            "base": {"repo": dict(BROWSER.REPOSITORY), "ref": "main", "sha": base},
            "head": {"repo": dict(BROWSER.REPOSITORY), "ref": "fix/main/cpu-fixture", "sha": head}}}
        return event, candidate

    def needs(self, outputs):
        cpu = outputs["mode"] == "cpu"
        return {"route": {"result": "success", "outputs": deepcopy(outputs)},
                "cpu": {"result": "success" if cpu else "skipped"},
                "browser": {"result": "skipped" if cpu else "success"},
                "native-journey": {"result": "skipped" if cpu else "success"}}

    def test_all_twelve_exact_cpu_inputs_and_approved_bootstrap_select_cpu(self):
        changes = {path: b"Updated exact CPU history source\n" for path in BROWSER.CPU_PATHS}
        changes[BROWSER.WORKFLOW] = BROWSER.canonical_workflow()
        event, candidate = self.merge(changes)
        selection = self.classify(candidate)
        self.assertEqual(selection["mode"], "cpu")
        self.assertEqual(selection["reason"], "approved-workflow-bootstrap-and-cpu-history")
        self.assertEqual(len(selection["changes"]), 13)
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        self.assertEqual(outputs["mode"], "cpu")
        self.assertEqual(outputs["audit"], "false")
        self.assertEqual(BROWSER.verify(event, "pull_request", self.root, candidate, self.needs(outputs)),
                         {"candidate": candidate, "plan": outputs["plan"], "verified": "true"})

    def test_only_exact_workflow_bootstrap_bytes_can_be_admitted(self):
        event, candidate = self.merge({BROWSER.WORKFLOW: BROWSER.canonical_workflow()})
        self.assertEqual(self.classify(candidate)["mode"], "full")
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate)["mode"], "full")
        for workflow in (LEGACY + b"\n# Unknown workflow\n", BROWSER.canonical_workflow() + b"\n# Candidate skip\n"):
            event, candidate = self.merge({BROWSER.WORKFLOW: workflow, next(iter(BROWSER.CPU_PATHS)): b"Updated\n"})
            self.assertEqual(self.classify(candidate)["mode"], "full")
            with self.assertRaisesRegex(ValueError, "trusted canonical"):
                BROWSER.route(event, "pull_request", self.root, candidate)

    def test_regular_cpu_only_changes_are_git_data_never_imported(self):
        self.activate_fixture()
        event, candidate = self.merge({path: b"throw new Error('candidate must never execute in router');\n"
                                       for path in BROWSER.CPU_PATHS})
        self.assertEqual(self.classify(candidate)["mode"], "cpu")
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate)["mode"], "cpu")

    def test_other_mixed_unknown_package_and_product_inputs_stay_full(self):
        self.activate_fixture()
        cpu = next(iter(BROWSER.CPU_PATHS))
        for path in ("browser-client/src/Main.ts", "browser-client/package.json", "browser-client/package-lock.json",
                     "browser-client/vite.config.mjs", "browser-client/native-input/Input.cpp",
                     "browser-client/tests/new.test.mjs", "browser-client/tests/fixtures/unknown.json",
                     "browser-client/lab/manage.py", "browser-client/tools/trusted-network/src/launcher.c",
                     "browser-client/gateway/server.mjs", "cmake/compiler.cmake", "new/unknown",
                     "tools/repository-checks/browser_cpu.py"):
            with self.subTest(path=path):
                event, candidate = self.merge({cpu: b"CPU change\n", path: b"Other or unknown input\n"})
                outputs = BROWSER.route(event, "pull_request", self.root, candidate)
                self.assertEqual(outputs["mode"], "full")
                self.assertEqual(outputs["audit"], str(path in BROWSER.PACKAGE_PATHS).lower())
                BROWSER.verify(event, "pull_request", self.root, candidate, self.needs(outputs))

    def test_missing_selected_results_skips_and_earlier_failures_cannot_green(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"CPU change\n"})
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        for name in BROWSER.JOBS:
            for status in (None, "failure", "cancelled", "timed_out", "pending", "neutral"):
                with self.subTest(job=name, status=status):
                    needs = self.needs(outputs)
                    needs[name]["result"] = status
                    with self.assertRaises(ValueError):
                        BROWSER.verify(event, "pull_request", self.root, candidate, needs)
            needs = self.needs(outputs)
            del needs[name]
            with self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)
        needs = self.needs(outputs)
        needs["cpu"]["result"] = "skipped"
        with self.assertRaises(ValueError):
            BROWSER.verify(event, "pull_request", self.root, candidate, needs)
        # Unselected heavy-job failures also remain failures; never hide them
        # behind a later CPU selection or failed-only rerun's retained result.
        for name in ("browser", "native-journey"):
            needs = self.needs(outputs)
            needs[name]["result"] = "failure"
            with self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)

    def test_full_route_requires_both_existing_heavy_jobs(self):
        self.activate_fixture()
        event, candidate = self.merge({"browser-client/src/Main.ts": b"Production change\n"})
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        for name in ("browser", "native-journey"):
            needs = self.needs(outputs)
            needs[name]["result"] = "skipped"
            with self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)

    def test_forged_plan_mode_audit_tree_and_candidate_cannot_replace_recomputation(self):
        self.activate_fixture()
        event, candidate = self.merge({"browser-client/src/Main.ts": b"Production change\n"})
        outputs = BROWSER.route(event, "pull_request", self.root, candidate)
        for field, value in (("mode", "cpu"), ("audit", "true"), ("tree", "f" * 40),
                             ("candidate", self.base), ("plan", "sha256:" + "0" * 64), ("base", "")):
            needs = self.needs(outputs)
            needs["route"]["outputs"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                BROWSER.verify(event, "pull_request", self.root, candidate, needs)

    def test_repository_merge_parent_head_and_checkout_are_independent(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"CPU change\n"})
        for side, field, value in (("repository", "full_name", "overte-org/overte"),
                                  ("repository", "id", 42), ("base", "sha", "f" * 40),
                                  ("head", "sha", self.base)):
            changed = deepcopy(event)
            target = changed["repository"] if side == "repository" else changed["pull_request"][side]
            target[field] = value
            with self.subTest(side=side, field=field), self.assertRaises(ValueError):
                BROWSER.route(changed, "pull_request", self.root, candidate)
        with self.assertRaises(ValueError):
            BROWSER.route(event, "pull_request", self.root, event["pull_request"]["head"]["sha"])
        with self.assertRaises(ValueError):
            BROWSER.route(event, "pull_request_target", self.root, candidate)

    def test_reader_then_cpu_changes_stay_full_without_automatic_anchor_refresh(self):
        self.activate_fixture()
        self.write("CMakeLists.txt", b"file(READ browser-client/tests/integration/prepare-tablet-capture-acceptance.mjs APP_INPUT)\n")
        integrated = self.commit("Integrate a new reader of a formerly independent fixture")
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"Later CPU source change\n"}, base=integrated)
        selection = self.classify(candidate, integrated)
        self.assertEqual(selection["mode"], "full")
        self.assertEqual(selection["reason"], "reader-boundary-not-reviewed")
        self.assertNotEqual(selection["base_boundary"], BROWSER.REVIEWED_BOUNDARY)
        self.assertNotEqual(selection["candidate_boundary"], BROWSER.REVIEWED_BOUNDARY)
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate)["mode"], "full")

    def test_modes_symlinks_and_gitlinks_anywhere_disable_cpu_selection(self):
        self.activate_fixture()
        path = next(iter(BROWSER.CPU_PATHS))
        self.write(path, b"CPU mode-only change\n")
        (self.root / path).chmod(0o755)
        mode = self.commit("Make a CPU input executable")
        self.assertEqual(self.classify(mode)["mode"], "full")
        self.git("checkout", "-q", "--detach", self.base)
        (self.root / "source-link").symlink_to(path)
        linked = self.commit("Add a source alias")
        anchor = BROWSER.review_boundary(self.root, linked)["boundary"]
        self.write(path, b"Changed through unchanged alias\n")
        later = self.commit("Change alias referent")
        with patch.object(BROWSER, "REVIEWED_BOUNDARY", anchor):
            self.assertEqual(self.classify(later, linked)["mode"], "full")
        self.git("checkout", "-q", "--detach", self.base)
        self.git("update-index", "--add", "--cacheinfo", "160000," + self.base + ",vendor/dependency")
        gitlink = self.commit("Add uninspected submodule", stage=False)
        self.assertEqual(self.classify(gitlink)["mode"], "full")

    def test_deletion_rename_and_new_history_path_are_not_lost(self):
        self.activate_fixture()
        paths = sorted(BROWSER.CPU_PATHS)
        (self.root / paths[0]).unlink()
        deleted = self.commit("Delete exact CPU input")
        self.assertEqual(self.classify(deleted)["mode"], "cpu")
        self.git("checkout", "-q", "--detach", self.base)
        self.git("mv", paths[0], paths[0] + ".unknown")
        renamed = self.commit("Rename CPU input into unknown path")
        selection = self.classify(renamed)
        self.assertEqual(selection["mode"], "full")
        self.assertEqual(len(selection["changes"]), 2)

    def test_worktree_index_and_replacement_refs_cannot_supply_candidate(self):
        self.activate_fixture()
        event, candidate = self.merge({next(iter(BROWSER.CPU_PATHS)): b"CPU change\n"})
        expected = BROWSER.route(event, "pull_request", self.root, candidate)
        self.write("browser-client/src/Main.ts", b"Staged local production change\n")
        self.git("add", "browser-client/src/Main.ts")
        self.write(BROWSER.WORKFLOW, b"Unstaged candidate orchestration\n")
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate), expected)
        self.git("reset", "--hard", "-q", candidate)
        self.write("browser-client/src/Main.ts", b"Replacement production bytes\n")
        replacement = self.commit("Create replacement object")
        self.git("replace", candidate, replacement)
        self.git("checkout", "-q", "--detach", candidate)
        self.assertEqual(BROWSER.route(event, "pull_request", self.root, candidate), expected)

    def test_empty_unknown_and_truncated_inventory_cannot_select_cpu(self):
        self.assertEqual(self.classify(self.base)["mode"], "full")
        for value in ("HEAD", "0" * 40, "a" * 39, None):
            with self.subTest(revision=value), self.assertRaises((ValueError, subprocess.SubprocessError)):
                BROWSER.snapshot(self.root, value)
        original = BROWSER.git
        def truncated(repository, *args):
            return b"100644 blob " + b"a" * 40 + b"\tREADME.md" if args[0] == "ls-tree" else original(repository, *args)
        with patch.object(BROWSER, "git", side_effect=truncated), self.assertRaises(ValueError):
            BROWSER.snapshot(self.root, self.base)

    def test_manual_dispatch_preserves_full_scope_and_diagnostics_are_not_required_proof(self):
        self.activate_fixture()
        event = {"repository": dict(BROWSER.REPOSITORY), "inputs": {"startup_diagnostics": "true"}}
        outputs = BROWSER.route(event, "workflow_dispatch", self.root, self.base)
        self.assertEqual(outputs["mode"], "full")
        self.assertEqual(BROWSER.verify(event, "workflow_dispatch", self.root, self.base, self.needs(outputs))["verified"],
                         "diagnostic-only")


class CanonicalTemplateTests(unittest.TestCase):
    def job(self, text, name):
        body = text.split("\n  " + name + ":\n", 1)[1]
        return re.split(r"\n  [A-Za-z][A-Za-z0-9_-]*:\n", body, maxsplit=1)[0]

    def test_existing_browser_and_native_job_scopes_are_preserved_exactly(self):
        old = LEGACY.decode()
        new = BROWSER.canonical_workflow().decode()
        for name in ("browser", "native-journey"):
            body = self.job(new, name)
            body = body.replace("    needs: route\n    if: needs.route.outputs.mode == 'full'\n", "", 1)
            body = body.replace("      - name: Audit changed browser package inputs\n        if: needs.route.outputs.audit == 'true'\n        run: npm audit --audit-level=high\n", "", 1)
            self.assertEqual(body.strip(), self.job(old, name).strip())

    def test_cpu_lane_retains_real_fixture_prerequisites_and_avoids_product_work(self):
        body = self.job(BROWSER.canonical_workflow().decode(), "cpu")
        for required in ("ffmpeg", "xvfb", "xauth", "bubblewrap", "slirp4netns", "iproute2", "gcc", "libssl-dev",
                         "apparmor-profiles", "tools/prepare-apparmor-userns.py", "prepare_signed_library.py",
                         "tools/trusted-network/workflow/build.py", "tools/trusted-network/workflow/install.py",
                         "OVERTE_GATEWAY_TRUSTED_NETWORK_SETUP=1", "run: npm test", "run: npm ci",
                         "test_runner.py", "test_chrome_scope.py"):
            self.assertIn(required, body)
        for forbidden in ("npm run build", "vite build", "playwright install", "qtbase5-dev", "build-native-input.py",
                          "manage.py prepare", "run-core-journey.sh", "pulseaudio --start"):
            self.assertNotIn(forbidden, body)

    def test_route_and_final_recompute_in_independent_trusted_jobs(self):
        text = BROWSER.canonical_workflow().decode()
        for name, command in (("route", "route"), ("verify", "verify")):
            body = self.job(text, name)
            self.assertIn("ref: ${{ github.event.repository.default_branch }}", body)
            self.assertIn("trusted/tools/repository-checks/browser_cpu.py " + command, body)
            self.assertIn('--event "$GITHUB_EVENT_PATH" --event-name "$GITHUB_EVENT_NAME"', body)
            self.assertIn("persist-credentials: false", body)
        self.assertIn("needs: [route, cpu, browser, native-journey]", text)
        self.assertIn("if: always()", self.job(text, "verify"))

    def test_workflow_generation_is_exact_and_never_activates_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "browser-client.yml"
            result = subprocess.run([sys.executable, str(HELPER), "workflow", "--output", str(output)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), BROWSER.canonical_workflow())
        self.assertEqual(BROWSER._blob(LEGACY), BROWSER.REVIEWED_WORKFLOW)


if __name__ == "__main__":
    unittest.main()
