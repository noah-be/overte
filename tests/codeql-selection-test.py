#!/usr/bin/env python3
"""Offline language-selection regressions, with disposable Git inventories."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("trusted_codeql_selection", ROOT / "tools/repository-checks/codeql.py")
CODEQL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(CODEQL)


def entry(sha="a", mode="100644"):
    return {"mode": mode, "type": "commit" if mode == "160000" else "blob", "sha": sha * 40}


def reviewed_tree():
    return {path: {"mode": "100644", "type": "blob", "sha": sha}
            for path, sha in CODEQL._REVIEWED_CONTROLS.items()} | {
                "tools/check.py": entry(), "browser/src/main.ts": entry(), "docs/design.md": entry(),
            }


class LanguageSelectionTests(unittest.TestCase):
    def change(self, path, *, original=None, replacement=None, event="pull_request"):
        before = reviewed_tree()
        if original is not None:
            before[path] = original
        after = deepcopy(before)
        if replacement is None:
            after.pop(path, None)
        else:
            after[path] = replacement
        return CODEQL.select_languages(before, after, event=event)

    def test_pure_python_and_python_dependencies_do_not_select_javascript(self):
        for path in ("tools/check.py", "helper.pyw", "typing.pyi", "protocol.thrift", "requirements.txt",
                     "tests/requirements-host.txt", "constraints-ci.in", "docs/pyproject.toml", "setup.cfg"):
            with self.subTest(path=path):
                plan = self.change(path, replacement=entry("b"))
                self.assertEqual(plan["languages"], ["python"])
                self.assertFalse(plan["full_scan"])

    def test_requirement_names_keep_unknown_inputs_conservative_without_backtracking(self):
        for name in ('requirements.txt', 'constraints.in', 'requirements-dev.txt',
                     'constraints_ci.in', 'requirements.a-b.c.txt',
                     'constraints-' + '-' * 200 + '.txt'):
            with self.subTest(name=name):
                self.assertEqual(self.change(name, replacement=entry('b'))['languages'], ['python'])
        for name in ('requirementsX.txt', 'constraints-.in', 'requirements..txt',
                     'constraints--..txt', 'requirements.a..b.txt',
                     'constraints-' + '-' * 200 + '..txt'):
            with self.subTest(name=name):
                self.assertEqual(self.change(name, replacement=entry('b'))['languages'], list(CODEQL.LANGUAGES))

    def test_python_lock_and_yaml_manifests_are_also_javascript_data_inputs(self):
        for path in ("Pipfile.lock", "poetry.lock", "uv.lock", "environment.yml", "environment.yaml", "conda-lock.yml"):
            with self.subTest(path=path):
                self.assertEqual(self.change(path, replacement=entry("b"))["languages"], list(CODEQL.LANGUAGES))

    def test_javascript_closure_includes_templates_data_config_and_uncommon_source_extensions(self):
        for path in ("client/main.js", "client/view.jsx", "main.cjs", "main.mjs", "main.es6", "main.xsjslib",
                     "types/main.ts", "types/view.tsx", "types/main.mts", "types/main.cts", "web/index.HTML",
                     "web/view.vue", "web/view.html.erb", "web/view.njk", "web/view.hbs", "web/view.ejs",
                     "client/package.json", "client/package-lock.json", "client/tsconfig.json", "yarn.lock",
                     "api/model.raml", "client/data.yaml", "client/data.yml", "client/.babelrc", "client/.xsaccess"):
            with self.subTest(path=path):
                self.assertEqual(self.change(path, replacement=entry("b"))["languages"], ["javascript-typescript"])

    def test_markdown_and_identical_inputs_require_no_language_job(self):
        self.assertEqual(self.change("docs/design.md", replacement=entry("b"))["languages"], [])
        tree = reviewed_tree()
        self.assertEqual(CODEQL.select_languages(tree, deepcopy(tree))["languages"], [])

    def test_python_mixed_with_markdown_remains_python_only(self):
        before = reviewed_tree()
        after = deepcopy(before)
        after["tools/check.py"] = entry("b")
        after["docs/design.md"] = entry("b")
        self.assertEqual(CODEQL.select_languages(before, after)["languages"], ["python"])

    def test_rename_keeps_old_and_new_paths_and_both_language_closures(self):
        before = reviewed_tree()
        after = deepcopy(before)
        after["browser/renamed.js"] = after.pop("tools/check.py")
        plan = CODEQL.select_languages(before, after)
        self.assertEqual(plan["languages"], list(CODEQL.LANGUAGES))
        by_path = {item["path"]: item for item in plan["changes"]}
        self.assertIsNone(by_path["tools/check.py"]["after"])
        self.assertIsNone(by_path["browser/renamed.js"]["before"])

    def test_python_delete_and_executable_mode_only_change_select_python(self):
        self.assertEqual(self.change("tools/check.py", original=entry())["languages"], ["python"])
        plan = self.change("tools/check.py", original=entry(), replacement=entry(mode="100755"))
        self.assertEqual(plan["languages"], ["python"])
        self.assertEqual(plan["changes"][0]["before"]["sha"], plan["changes"][0]["after"]["sha"])
        self.assertNotEqual(plan["changes"][0]["before"]["mode"], plan["changes"][0]["after"]["mode"])

    def test_every_shared_analysis_control_and_query_pack_keeps_both_languages(self):
        for path in (".github/workflows/codeql.yml", ".github/workflows/new.yml", ".github/actions/scan/index.py",
                     ".github/codeql/model.py", "custom/queries/check.ql", "custom/queries/lib.qll", "queries/security.qls",
                     "custom/qlpack.yml", "packs/codeql-pack.lock.yml", "custom/codeql-config.yml",
                     "custom/codeql-python/model.py", "custom/qlpacks/model.yaml", "AGENTS.md", ".gitignore",
                     ".gitattributes", ".gitmodules", ".codeqlignore", ".tool-versions",
                     "tools/repository-checks/codeql.py", "tools/test-evidence/inputs.py", "tests/codeql-selection-test.py"):
            with self.subTest(path=path):
                self.assertTrue(self.change(path, replacement=entry("b"))["full_scan"])

    def test_both_sides_must_match_reviewed_actual_workflow_and_configuration(self):
        for path in CODEQL._REVIEWED_CONTROLS:
            before = reviewed_tree()
            after = deepcopy(before)
            after["tools/check.py"] = entry("b")
            for action in ("changed-both", "missing-base", "missing-candidate", "executable-control"):
                left, right = deepcopy(before), deepcopy(after)
                if action == "changed-both":
                    left[path] = right[path] = entry("c")
                elif action == "missing-base":
                    del left[path]
                elif action == "missing-candidate":
                    del right[path]
                else:
                    left[path]["mode"] = right[path]["mode"] = "100755"
                with self.subTest(path=path, action=action):
                    self.assertEqual(CODEQL.select_languages(left, right)["reasons"][0]["code"],
                                     "unreviewed-analysis-configuration")

    def test_querypack_helpers_and_models_keep_the_complete_pack_directory_global(self):
        for manifest in ("custom/security/qlpack.yml", "qlpack.yml"):
            for changed in ("custom/security/helpers/generate.py", "custom/security/models/library.yaml"):
                before = reviewed_tree() | {manifest: entry(), changed: entry()}
                after = deepcopy(before)
                after[changed] = entry("b")
                with self.subTest(manifest=manifest, changed=changed):
                    plan = CODEQL.select_languages(before, after)
                    self.assertTrue(plan["full_scan"])
                    self.assertEqual(plan["reasons"][0]["code"], "shared-analysis-control")

    def test_ignored_javascript_remains_conservative_for_import_and_type_dependencies(self):
        path = "interface/resources/qml/controls/CpuShadowPixels.js"
        self.assertEqual(self.change(path, replacement=entry("b"))["languages"], ["javascript-typescript"])

    def test_unknown_inputs_and_extensionless_shebangs_never_disappear(self):
        for path in ("bin/script", "web/new.extractor-input", "interface/model.qml", "CMakeLists.txt"):
            with self.subTest(path=path):
                plan = self.change(path, replacement=entry("b"))
                self.assertTrue(plan["full_scan"])
                self.assertEqual(plan["reasons"][0]["code"], "unknown-analysis-input")

    def test_unchanged_aliases_and_gitlinks_still_require_full_scan(self):
        for mode in ("120000", "160000"):
            before = reviewed_tree() | {"browser/alias.js": entry(mode=mode)}
            after = deepcopy(before)
            after["tools/check.py"] = entry("b")
            plan = CODEQL.select_languages(before, after)
            self.assertTrue(plan["full_scan"])
            self.assertEqual(plan["reasons"][0]["code"], "unresolved-source-alias-or-submodule")

    def test_schedules_and_unsupported_events_always_scan_both_languages(self):
        self.assertEqual(CODEQL.select_languages(None, None, event="schedule")["languages"], list(CODEQL.LANGUAGES))
        for event in ("workflow_dispatch", "pull_request_target", "unrecognized"):
            with self.subTest(event=event):
                self.assertTrue(self.change("tools/check.py", replacement=entry("b"), event=event)["full_scan"])

    def test_missing_or_malformed_inventory_fails_closed(self):
        for tree in (None, [], ["tools/check.py"], {"tools/check.py": {"sha": "a" * 40}},
                     {"../other.py": entry()}, {"tools/check.py": entry(mode="100664")}):
            for left, right in ((tree, reviewed_tree()), (reviewed_tree(), tree)):
                with self.subTest(tree=tree):
                    plan = CODEQL.select_languages(left, right)
                    self.assertTrue(plan["full_scan"])
                    self.assertEqual(plan["reasons"][0]["code"], "unavailable-complete-inventory")


class ImmutableRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-codeql-selection-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "CodeQL selection fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        for relative in CODEQL._REVIEWED_CONTROLS:
            self.write(relative, (ROOT / relative).read_text())
        self.write("tools/check.py", "raise RuntimeError('candidate source must never be imported')\n")
        self.write("tools/test-evidence/inputs.py", "raise RuntimeError('candidate inventory must never be imported')\n")
        self.write("browser/main.ts", "export const value = 1;\n")
        self.base = self.commit()

    def git(self, *arguments):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *arguments],
                                       cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def write(self, relative, source):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Immutable CodeQL selection fixture")
        return self.git("rev-parse", "HEAD")

    def test_complete_git_inventory_ignores_dirty_candidate_and_never_imports_candidate_code(self):
        self.write("tools/check.py", "raise RuntimeError('changed candidate must never be imported')\n")
        candidate = self.commit()
        self.write("browser/main.ts", "uncommitted worktree file is not the candidate object\n")
        plan = CODEQL.select_repository(self.root, self.base, candidate)
        self.assertEqual(plan["languages"], ["python"])
        self.assertEqual(plan["commits"], {"base": self.base, "candidate": candidate})
        self.assertEqual([change["path"] for change in plan["changes"]], ["tools/check.py"])
        self.assertEqual(plan, json.loads(json.dumps(plan)))

    def test_real_git_rename_delete_and_mode_changes_are_retained(self):
        original = self.git("rev-parse", "HEAD:tools/check.py")
        self.git("mv", "tools/check.py", "tools/renamed.py")
        (self.root / "tools/renamed.py").chmod(0o755)
        (self.root / "browser/main.ts").unlink()
        candidate = self.commit()
        plan = CODEQL.select_repository(self.root, self.base, candidate)
        self.assertTrue(plan["full_scan"])
        by_path = {change["path"]: change for change in plan["changes"]}
        self.assertIsNone(by_path["tools/check.py"]["after"])
        self.assertIsNone(by_path["browser/main.ts"]["after"])
        self.assertEqual(by_path["tools/renamed.py"]["after"], {"mode": "100755", "type": "blob", "sha": original})

    def test_unavailable_history_or_nonimmutable_reference_never_yields_partial_selection(self):
        for sha in ("HEAD", "a" * 40, "0" * 40, ""):
            with self.subTest(sha=sha):
                self.assertTrue(CODEQL.select_repository(self.root, sha, self.base)["full_scan"])
                self.assertTrue(CODEQL.select_repository(self.root, self.base, sha)["full_scan"])
        self.assertTrue(CODEQL.select_repository("/missing-repository", "", "", event="schedule")["full_scan"])


if __name__ == "__main__":
    unittest.main()
