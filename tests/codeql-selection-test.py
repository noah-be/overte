#!/usr/bin/env python3
"""Offline language-selection regressions, with disposable Git inventories."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


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
    def pinned_trees(self):
        before = reviewed_tree()
        before['.github/workflows/codeql.yml']['sha'] = CODEQL._PINNED_RESULTS_WORKFLOW
        before.update({path: entry() for path in CODEQL._PYTHON_POLICY_JSONS | CODEQL._INERT_CI_JSONS})
        return before, deepcopy(before)

    def test_only_four_existing_ci_metadata_leaves_need_no_language_in_the_pinned_generation(self):
        self.assertEqual(CODEQL._INERT_CI_JSONS, {
            '.github/branch-cleanup.json', '.github/issue-policy.json',
            '.github/repository-health.json', '.github/dependency-releases.json'})
        for path in CODEQL._INERT_CI_JSONS:
            for event in ('pull_request', 'push'):
                before, after = self.pinned_trees()
                after[path] = entry('b')
                with self.subTest(path=path, event=event):
                    plan = CODEQL.select_languages(before, after, event=event)
                    self.assertEqual(plan['languages'], [])
                    self.assertFalse(plan['full_scan'])
                    self.assertEqual(plan['reasons'], [{'code': 'reviewed-pinned-ci-metadata', 'path': path}])
                    self.assertEqual([change['path'] for change in plan['changes']], [path])

    def test_ci_metadata_mixed_changes_retain_every_existing_language_owner(self):
        for changed, expected in (
                ({'tools/helper.py'}, ['python']),
                ({'browser-client/main.ts'}, ['javascript-typescript']),
                ({'tools/helper.py', 'browser-client/main.ts'}, list(CODEQL.LANGUAGES)),
                ({'.github/android-orchestration.json'}, ['python']),
                ({'.github/test-suites.json'}, ['python']),
                ({'.github/workflows/branch-cleanup.yml'}, ['javascript-typescript']),
                ({'tools/repository-checks/workflows/producers/parent-qualification.yml'}, ['javascript-typescript']),
                ({'browser-client/package-lock.json'}, ['javascript-typescript']),
                ({'script-archive/marketplace/S3Server/package-lock.json'}, ['javascript-typescript']),
                ({'.github/unknown-metadata.json'}, ['javascript-typescript']),
                ({'tools/repository-checks/codeql.py'}, list(CODEQL.LANGUAGES)),
                ({'tools/repository-checks/check.py'}, list(CODEQL.LANGUAGES)),
                ({'bin/unknown-input'}, list(CODEQL.LANGUAGES)),
                ({'custom/qlpack.yml'}, list(CODEQL.LANGUAGES))):
            before, after = self.pinned_trees()
            for path in CODEQL._INERT_CI_JSONS | changed: after[path] = entry('b')
            with self.subTest(changed=changed):
                self.assertEqual(CODEQL.select_languages(before, after)['languages'], expected)

    def test_ci_metadata_cannot_omit_added_deleted_renamed_or_nonordinary_paths(self):
        for path in CODEQL._INERT_CI_JSONS:
            for mutation in ('addition', 'removal', 'renamed', 'before-executable', 'after-executable', 'symlink', 'gitlink'):
                before, after = self.pinned_trees()
                after[path] = entry('b')
                if mutation == 'addition': del before[path]
                elif mutation == 'removal': del after[path]
                elif mutation == 'renamed': after[path + '.other.json'] = after.pop(path)
                elif mutation == 'before-executable': before[path] = entry(mode='100755')
                else:
                    after[path] = entry('b', {'after-executable': '100755', 'symlink': '120000', 'gitlink': '160000'}[mutation])
                expected = list(CODEQL.LANGUAGES) if mutation in ('symlink', 'gitlink') else ['javascript-typescript']
                with self.subTest(path=path, mutation=mutation):
                    self.assertEqual(CODEQL.select_languages(before, after)['languages'], expected)

    def test_ci_metadata_requires_both_pinned_workflows_and_cannot_hide_pack_or_alias_inputs(self):
        for previous in (CODEQL._REVIEWED_CONTROLS['.github/workflows/codeql.yml'], CODEQL._SELECTIVE_WORKFLOW,
                         CODEQL._RESULTS_WORKFLOW, CODEQL._RETARGET_RESULTS_WORKFLOW):
            before, after = self.pinned_trees()
            for path in CODEQL._INERT_CI_JSONS: after[path] = entry('b')
            before['.github/workflows/codeql.yml']['sha'] = previous
            after['.github/workflows/codeql.yml']['sha'] = previous
            self.assertEqual(CODEQL.select_languages(before, after)['languages'], ['javascript-typescript'])
            after['.github/workflows/codeql.yml']['sha'] = CODEQL._PINNED_RESULTS_WORKFLOW
            self.assertTrue(CODEQL.select_languages(before, after)['full_scan'])
        for path in CODEQL._REVIEWED_CONTROLS:
            for side in ('before', 'after'):
                before, after = self.pinned_trees()
                after['.github/branch-cleanup.json'] = entry('b')
                (before if side == 'before' else after)[path] = entry('c')
                with self.subTest(path=path, side=side):
                    self.assertEqual(CODEQL.select_languages(before, after)['reasons'][0]['code'],
                                     'unreviewed-analysis-configuration')
        for unknown in ('.github/qlpack.yml', 'qlpack.yml', 'unchanged-alias.js', 'unchanged-submodule'):
            before, after = self.pinned_trees()
            mode = '120000' if unknown.endswith('.js') else '160000' if unknown == 'unchanged-submodule' else '100644'
            before[unknown] = after[unknown] = entry(mode=mode)
            after['.github/branch-cleanup.json'] = entry('b')
            with self.subTest(unknown=unknown):
                self.assertTrue(CODEQL.select_languages(before, after)['full_scan'])

    def test_ci_metadata_keeps_schedule_unknown_events_and_inventory_failures_conservative(self):
        before, after = self.pinned_trees()
        after['.github/branch-cleanup.json'] = entry('b')
        for event in ('schedule', 'workflow_dispatch', 'pull_request_target', 'unknown'):
            with self.subTest(event=event):
                self.assertTrue(CODEQL.select_languages(before, after, event=event)['full_scan'])
        for left, right in ((None, after), (before, None), ({}, after)):
            self.assertTrue(CODEQL.select_languages(left, right)['full_scan'])

    def test_only_existing_ordinary_policy_jsons_use_python_in_the_exact_pinned_generation(self):
        for path in CODEQL._PYTHON_POLICY_JSONS:
            for event in ('pull_request', 'push'):
                before, after = self.pinned_trees()
                after[path] = entry('b')
                with self.subTest(path=path, event=event):
                    self.assertEqual(CODEQL.select_languages(before, after, event=event)['languages'], ['python'])
                after['tools/check.py'] = entry('b')
                self.assertEqual(CODEQL.select_languages(before, after)['languages'], ['python'])

    def test_pinned_policy_exception_retains_javascript_and_unknown_input_owners(self):
        for path in ('client/main.ts', 'data.json', 'package.json', 'package-lock.json', 'yarn.lock',
                     '.github/workflows/branch-cleanup.yml', 'other.yaml', '.github/test-suites-extra.json',
                     'tools/new-unknown-input', 'tools/repository-checks/check.py', 'custom/qlpack.yml'):
            before, after = self.pinned_trees()
            after['.github/test-suites.json'] = entry('b')
            after[path] = entry('b')
            with self.subTest(path=path):
                self.assertEqual(CODEQL.select_languages(before, after)['languages'], list(CODEQL.LANGUAGES))

    def test_policy_json_add_remove_and_modes_cannot_inherit_the_exception(self):
        for path in CODEQL._PYTHON_POLICY_JSONS:
            for mutation in ('addition', 'removal', 'executable', 'symlink', 'gitlink'):
                before, after = self.pinned_trees()
                if mutation == 'addition':
                    del before[path]
                elif mutation == 'removal':
                    del after[path]
                else:
                    after[path] = entry('b', {'executable': '100755', 'symlink': '120000', 'gitlink': '160000'}[mutation])
                expected = ['javascript-typescript'] if mutation in ('addition', 'removal', 'executable') else list(CODEQL.LANGUAGES)
                with self.subTest(path=path, mutation=mutation):
                    self.assertEqual(CODEQL.select_languages(before, after)['languages'], expected)

    def test_pinned_policy_requires_both_exact_workflows_and_unchanged_configuration(self):
        for workflow in (CODEQL._REVIEWED_CONTROLS['.github/workflows/codeql.yml'], CODEQL._SELECTIVE_WORKFLOW,
                         CODEQL._RESULTS_WORKFLOW, CODEQL._RETARGET_RESULTS_WORKFLOW):
            before, after = self.pinned_trees()
            before['.github/workflows/codeql.yml']['sha'] = workflow
            after['.github/workflows/codeql.yml']['sha'] = workflow
            after['.github/test-suites.json'] = entry('b')
            self.assertEqual(CODEQL.select_languages(before, after)['languages'], ['javascript-typescript'])
            after['.github/workflows/codeql.yml']['sha'] = CODEQL._PINNED_RESULTS_WORKFLOW
            self.assertTrue(CODEQL.select_languages(before, after)['full_scan'])
        for path in CODEQL._REVIEWED_CONTROLS:
            for side in ('base', 'candidate'):
                before, after = self.pinned_trees()
                after['.github/test-suites.json'] = entry('b')
                (before if side == 'base' else after)[path] = entry('b')
                self.assertEqual(CODEQL.select_languages(before, after)['reasons'][0]['code'],
                                 'unreviewed-analysis-configuration')

    def test_result_generations_advance_without_allowing_deployed_rollbacks(self):
        generations = CODEQL.result_workflow_blobs()
        self.assertEqual(len(generations), 3)
        for old_index, old in enumerate(generations):
            for new_index, new in enumerate(generations):
                before, after = self.pinned_trees()
                before['.github/workflows/codeql.yml']['sha'] = old
                after['.github/workflows/codeql.yml']['sha'] = new
                rollback = CODEQL.result_workflow_rollback(before['.github/workflows/codeql.yml'], after['.github/workflows/codeql.yml'])
                with self.subTest(old=old, new=new):
                    self.assertEqual(rollback, new_index < old_index)

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
        for path in (".github/workflows/codeql.yml",
                     ".github/codeql/model.py", "custom/queries/check.ql", "custom/queries/lib.qll", "queries/security.qls",
                     "custom/qlpack.yml", "packs/codeql-pack.lock.yml", "custom/codeql-config.yml",
                     "custom/codeql-python/model.py", "custom/qlpacks/model.yaml", "AGENTS.md", ".gitignore",
                     ".gitattributes", ".gitmodules", ".codeqlignore", ".tool-versions",
                     "tools/repository-checks/codeql.py", "tools/test-evidence/inputs.py"):
            with self.subTest(path=path):
                self.assertTrue(self.change(path, replacement=entry("b"))["full_scan"])

    def test_verifier_and_regression_python_changes_do_not_change_javascript_extraction(self):
        for path in ('tools/repository-checks/codeql_results.py', 'tests/codeql-selection-test.py'):
            with self.subTest(path=path):
                self.assertEqual(self.change(path, replacement=entry('b'))['languages'], ['python'])

    def test_unrelated_workflow_data_and_local_actions_keep_their_own_language(self):
        self.assertEqual(self.change('.github/workflows/new.yml', replacement=entry('b'))['languages'],
                         ['javascript-typescript'])
        self.assertEqual(self.change('.github/actions/scan/index.py', replacement=entry('b'))['languages'],
                         ['python'])

    def test_reviewed_selective_workflow_supports_pure_language_changes(self):
        for digest in (CODEQL._REVIEWED_CONTROLS['.github/workflows/codeql.yml'], CODEQL._SELECTIVE_WORKFLOW):
            before = reviewed_tree()
            before['.github/workflows/codeql.yml']['sha'] = digest
            after = deepcopy(before)
            after['tools/check.py'] = entry('b')
            self.assertEqual(CODEQL.select_languages(before, after)['languages'], ['python'])
        before = reviewed_tree()
        after = deepcopy(before)
        after['.github/workflows/codeql.yml']['sha'] = CODEQL._SELECTIVE_WORKFLOW
        self.assertTrue(CODEQL.select_languages(before, after)['full_scan'])

    def test_saved_workflow_digest_matches_the_actual_reviewed_activation(self):
        actual = subprocess.check_output(['git', 'hash-object', '.github/workflows/codeql.yml'],
                                         cwd=ROOT, text=True).strip()
        self.assertIn(actual, {CODEQL._SELECTIVE_WORKFLOW, *CODEQL.result_workflow_blobs()})
        canonical = ROOT / "tools/repository-checks/workflows/codeql-results.yml"
        expected = subprocess.check_output(["git", "hash-object", str(canonical)], cwd=ROOT, text=True).strip()
        self.assertEqual(expected, CODEQL._RESULTS_WORKFLOW)
        successor = ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml'
        self.assertEqual(subprocess.check_output(['git', 'hash-object', str(successor)], cwd=ROOT, text=True).strip(),
                         CODEQL._RETARGET_RESULTS_WORKFLOW)
        pinned = successor.with_name('codeql-pinned.yml')
        self.assertEqual(subprocess.check_output(['git', 'hash-object', str(pinned)], cwd=ROOT, text=True).strip(),
                         CODEQL._PINNED_RESULTS_WORKFLOW)
        # Changing the tool pin or its required version check cannot keep admission.
        for source in (pinned.read_bytes().replace(b'v2.27.2/', b'v2.27.3/'),
                       pinned.read_bytes().replace(b'= 2.27.2', b'= 2.27.3')):
            modified = subprocess.check_output(['git', 'hash-object', '--stdin'], input=source, cwd=ROOT).decode().strip()
            before, after = self.pinned_trees()
            before['.github/workflows/codeql.yml']['sha'] = modified
            after['.github/test-suites.json'] = entry('b')
            self.assertEqual(CODEQL.select_languages(before, after)['reasons'][0]['code'], 'unreviewed-analysis-configuration')

    def test_retarget_generation_is_exact_and_classification_control_is_shared(self):
        before = reviewed_tree()
        before['.github/workflows/codeql.yml']['sha'] = CODEQL._RETARGET_RESULTS_WORKFLOW
        for path, expected in (('app/main.py', ['python']), ('app/main.ts', ['javascript-typescript']),
                               ('tools/repository-checks/check.py', list(CODEQL.LANGUAGES))):
            after = deepcopy(before); after[path] = entry('b')
            self.assertEqual(CODEQL.select_languages(before, after)['languages'], expected)
        after = deepcopy(before)
        after['.github/workflows/codeql.yml']['sha'] = CODEQL._RESULTS_WORKFLOW
        selected = CODEQL.select_languages(before, after)
        self.assertTrue(selected['full_scan'])
        self.assertEqual(selected['reasons'][0]['code'], 'analysis-workflow-rollback')
        self.assertTrue(CODEQL.result_workflow_rollback(before['.github/workflows/codeql.yml'],
                                                       after['.github/workflows/codeql.yml']))

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
        # Historical transitions start at the exact predecessor even after the
        # checkout activates its successor; do not inherit ROOT's active version.
        self.write(".github/workflows/codeql.yml",
                   (ROOT / "tools/repository-checks/workflows/codeql-results.yml").read_text())
        self.write("tools/check.py", "raise RuntimeError('candidate source must never be imported')\n")
        self.write("tools/test-evidence/inputs.py", "raise RuntimeError('candidate inventory must never be imported')\n")
        self.write("browser/main.ts", "export const value = 1;\n")
        self.base = self.commit()
        self.assertEqual(self.git("rev-parse", self.base + ":.github/workflows/codeql.yml"),
                         CODEQL._RESULTS_WORKFLOW)

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

    def test_retarget_reselects_from_new_base_and_actual_merge_without_importing_sources(self):
        self.write('.github/workflows/codeql.yml',
                   (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml').read_text())
        base = self.commit()
        for changes, expected in (({'app.py': 'raise RuntimeError("never import")\n'}, ['python']),
                                  ({'app.ts': 'export const value=2;\n'}, ['javascript-typescript']),
                                  ({'app.py': '# changed\n', 'app.ts': '// changed\n'}, list(CODEQL.LANGUAGES)),
                                  ({'unknown.input': 'unknown\n'}, list(CODEQL.LANGUAGES))):
            self.git('checkout', '-q', '--detach', base)
            for path, source in changes.items(): self.write(path, source)
            head = self.commit()
            merge = self.git('commit-tree', self.git('rev-parse', head + '^{tree}'),
                             '-p', base, '-p', head, '-m', 'Retarget exact merge fixture')
            with self.subTest(changes=changes):
                plan = CODEQL.select_repository(self.root, base, merge, event='pull_request')
                self.assertEqual(plan['languages'], expected)
                self.assertEqual(plan['commits'], {'base': base, 'candidate': merge})


RESULT_SPEC = importlib.util.spec_from_file_location("trusted_codeql_results", ROOT / "tools/repository-checks/codeql_results.py")
RESULTS = importlib.util.module_from_spec(RESULT_SPEC)
assert RESULT_SPEC.loader
RESULT_SPEC.loader.exec_module(RESULTS)


class FakeCodeScanningApi:
    """Authenticated server response fixture; never executes gh or a candidate."""
    def __init__(self, owner):
        self.owner, self.calls = owner, []
        self.error = None
        self.change = None

    def json(self, endpoint):
        from urllib.parse import parse_qs, urlsplit
        self.calls.append(endpoint)
        if self.error:
            raise self.error
        if self.change:
            self.change(endpoint)
        assert endpoint == RESULTS.PREFIX or endpoint.startswith(RESULTS.PREFIX + '/')
        parsed = urlsplit(endpoint[len(RESULTS.PREFIX):])
        path, query, o = parsed.path.lstrip('/'), parse_qs(parsed.query), self.owner
        objects = {'': o.repo, 'actions/workflows/codeql.yml': o.workflow,
                   'actions/runs/12': o.run, 'actions/runs/12/attempts/1': o.run,
                   'pulls/42': o.pr, 'commits/refs/pull/42/merge': o.merge}
        if path in objects:
            if path == 'commits/refs/pull/42/merge':
                assert query == {'per_page': ['1'], 'page': ['1']}
            return deepcopy(objects[path])
        if path.startswith('git/ref/'):
            ref = path[len('git/ref/'):]
            return {'ref': 'refs/' + ref, 'object': {'type': 'commit', 'sha': o.refs[ref]}}
        if path == 'actions/runs/12/attempts/1/jobs':
            items = o.jobs
            count = len(items) if o.job_total is None else o.job_total
            field = 'jobs'
        elif path == 'code-scanning/analyses':
            assert query['ref'] == [o.env['GITHUB_REF']] and query['tool_name'] == ['CodeQL']
            items, field = o.analyses, None
        elif path.startswith('code-scanning/analyses/'):
            return deepcopy(next(x for x in o.analyses if x['id'] == int(path.rsplit('/', 1)[1])))
        elif path == 'code-scanning/alerts':
            assert query['state'] == ['open'] and query['ref'] == [o.env['GITHUB_REF']]
            items, field = o.alerts, None
        elif path.startswith('code-scanning/alerts/') and path.endswith('/instances'):
            assert query['ref'] == [o.env['GITHUB_REF']]
            items, field = o.instances[int(path.split('/')[2])], None
        else:
            raise AssertionError('Unexpected fixed API endpoint: ' + path)
        page = int(query['page'][0])
        assert query['per_page'] == ['100']
        rows = deepcopy(items[(page - 1) * 100:page * 100])
        return {'total_count': count, field: rows} if field else rows


class SelectedResultTests(unittest.TestCase):
    git = ImmutableRepositoryTests.git
    write = ImmutableRepositoryTests.write
    commit = ImmutableRepositoryTests.commit

    def setUp(self):
        ImmutableRepositoryTests.setUp(self)
        self.write('tools/check.py', '# immutable changed Python source\n')
        self.head = self.commit()
        tree = self.git('rev-parse', 'HEAD^{tree}')
        self.candidate = self.git('commit-tree', tree, '-p', self.base, '-p', self.head, '-m', 'Exact merge fixture')
        self.git('checkout', '-q', '--detach', self.candidate)
        self.repo = {'id': RESULTS.REPOSITORY_ID, 'full_name': RESULTS.REPOSITORY, 'default_branch': 'main'}
        side = lambda ref, revision: {'ref': ref, 'sha': revision, 'repo': deepcopy(self.repo)}
        self.pr = {'number': 42, 'state': 'open', 'base': side('main', self.base),
                   'head': side('fix/main/example', self.head), 'merge_commit_sha': self.candidate}
        self.event = {'repository': deepcopy(self.repo), 'number': 42, 'pull_request': deepcopy(self.pr)}
        self.env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': RESULTS.REPOSITORY,
                    'GITHUB_REPOSITORY_ID': str(RESULTS.REPOSITORY_ID), 'GITHUB_EVENT_NAME': 'pull_request',
                    'GITHUB_SHA': self.candidate, 'GITHUB_RUN_ID': '12', 'GITHUB_RUN_ATTEMPT': '1',
                    'GITHUB_REF': 'refs/pull/42/merge', 'GITHUB_HEAD_REF': 'fix/main/example',
                    'GITHUB_BASE_REF': 'main', 'CODEQL_EXPECTED_LANGUAGES': '["python"]',
                    'GITHUB_WORKFLOW_SHA': self.candidate,
                    'GITHUB_WORKFLOW_REF': RESULTS.REPOSITORY + '/' + RESULTS.WORKFLOW + '@refs/pull/42/merge'}
        self.refs = {'heads/main': self.base, 'heads/fix/main/example': self.head, 'pull/42/merge': self.candidate}
        self.merge = {'sha': self.candidate, 'parents': [{'sha': self.base}, {'sha': self.head}]}
        self.workflow = {'id': 7, 'path': RESULTS.WORKFLOW, 'state': 'active'}
        self.run = {'id': 12, 'run_attempt': 1, 'workflow_id': 7, 'path': RESULTS.WORKFLOW,
                    'repository': deepcopy(self.repo), 'head_repository': deepcopy(self.repo),
                    'head_sha': self.head, 'head_branch': 'fix/main/example', 'event': 'pull_request',
                    'status': 'in_progress', 'conclusion': None, 'run_started_at': '2026-10-15T21:00:00Z'}
        self.jobs = [{'id': 81, 'name': 'CodeQL (python)', 'run_id': 12, 'run_attempt': 1,
                      'head_sha': self.head, 'status': 'completed', 'conclusion': 'success',
                      'started_at': '2026-10-15T21:00:01Z', 'completed_at': '2026-10-15T21:00:21Z',
                      'steps': [{'name': 'Analyze', 'status': 'completed', 'conclusion': 'success',
                                 'started_at': '2026-10-15T21:00:10Z', 'completed_at': '2026-10-15T21:00:20Z'}]}]
        self.jobs.append(dict(self.jobs[0], id=80, name='Select affected CodeQL languages', steps=[],
                              started_at='2026-10-15T21:00:00Z', completed_at='2026-10-15T21:00:01Z'))
        self.job_total = None
        self.analyses = [{'id': 91, 'ref': self.env['GITHUB_REF'], 'commit_sha': self.candidate,
                          'analysis_key': RESULTS.ANALYSIS_KEY, 'environment': '{"language":"python"}',
                          'category': '/language:python', 'error': '', 'rules_count': 43, 'results_count': 1,
                          'created_at': '2026-10-15T21:00:15Z', 'tool': {'name': 'CodeQL', 'version': '2.27.2'}}]
        self.alerts, self.instances = [], {}
        self.api = FakeCodeScanningApi(self)

    def verify(self, **options):
        return RESULTS.Verifier(self.root, self.event, self.env, api=self.api, **options).verify(processing_seconds=0)

    def pinned_policy_candidate(self, changed_path='.github/test-suites.json', extra_sources=None):
        """Real immutable two-parent candidate; only fake authenticated API I/O."""
        self.write(RESULTS.WORKFLOW,
                   (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql-pinned.yml').read_text())
        for path in CODEQL._PYTHON_POLICY_JSONS | CODEQL._INERT_CI_JSONS: self.write(path, '{"fixture":1}\n')
        self.base = self.commit()
        self.write(changed_path, '{"fixture":2}\n')
        for path, source in (extra_sources or {}).items(): self.write(path, source)
        self.head = self.commit()
        self.candidate = self.git('commit-tree', self.git('rev-parse', self.head + '^{tree}'),
                                  '-p', self.base, '-p', self.head, '-m', 'Pinned policy merge fixture')
        self.git('checkout', '-q', '--detach', self.candidate)
        self.pr['base']['sha'], self.pr['head']['sha'] = self.base, self.head
        self.pr['merge_commit_sha'] = self.candidate
        self.event['pull_request'] = deepcopy(self.pr)
        self.env.update(GITHUB_SHA=self.candidate, GITHUB_WORKFLOW_SHA=self.candidate)
        self.refs = {'heads/main': self.base, 'heads/fix/main/example': self.head, 'pull/42/merge': self.candidate}
        self.merge = {'sha': self.candidate, 'parents': [{'sha': self.base}, {'sha': self.head}]}
        self.run['head_sha'] = self.head
        for job in self.jobs: job['head_sha'] = self.head
        self.jobs[0]['steps'].insert(0, {'name': 'Require reviewed CodeQL extractor version',
            'status': 'completed', 'conclusion': 'success',
            'started_at': '2026-10-15T21:00:02Z', 'completed_at': '2026-10-15T21:00:03Z'})
        self.analyses[0]['commit_sha'] = self.candidate

    def test_pinned_ci_metadata_uses_real_git_and_still_requires_current_successful_selector(self):
        self.pinned_policy_candidate('.github/branch-cleanup.json')
        self.env['CODEQL_EXPECTED_LANGUAGES'] = '[]'
        selector = deepcopy(self.jobs[-1])
        self.jobs, self.analyses = [selector], []
        self.write('browser/main.ts', '// dirty worktree never changes immutable selection\n')
        self.assertEqual(self.verify()['languages'], [])
        self.assertFalse(any('/code-scanning/' in call for call in self.api.calls))
        for mutation in ('missing', 'failure', 'skipped', 'stale-head', 'wrong-attempt', 'duplicate'):
            self.jobs = [deepcopy(selector)]
            if mutation == 'missing': self.jobs.clear()
            elif mutation == 'failure': self.jobs[0]['conclusion'] = 'failure'
            elif mutation == 'skipped': self.jobs[0]['conclusion'] = 'skipped'
            elif mutation == 'stale-head': self.jobs[0]['head_sha'] = self.base
            elif mutation == 'wrong-attempt': self.jobs[0]['run_attempt'] = 2
            else: self.jobs.append(deepcopy(selector))
            with self.subTest(mutation=mutation), self.assertRaises(RESULTS.ResultError): self.verify()

    def test_ci_metadata_cannot_hide_changed_python_or_an_open_current_python_finding(self):
        self.pinned_policy_candidate('.github/issue-policy.json', {'tools/check.py': '# changed Python\n'})
        self.env['CODEQL_EXPECTED_LANGUAGES'] = '[]'
        with self.assertRaisesRegex(RESULTS.ResultError, 'independent immutable selection'): self.verify()
        self.env['CODEQL_EXPECTED_LANGUAGES'] = '["python"]'
        self.assertEqual(self.verify()['languages'], ['python'])
        self.alerts = [{'number': 9, 'state': 'open', 'tool': {'name': 'CodeQL'}}]
        self.instances = {9: [{'ref': self.env['GITHUB_REF'], 'commit_sha': self.candidate,
            'category': '/language:python', 'state': 'open', 'analysis_key': RESULTS.ANALYSIS_KEY}]}
        with self.assertRaisesRegex(RESULTS.ResultError, 'open CodeQL finding'): self.verify()

    def test_pinned_policy_json_uses_python_results_bound_to_actual_candidate_and_extractor(self):
        old_candidate = self.candidate
        self.pinned_policy_candidate()
        # Worktree content and supplied languages cannot replace Git object selection.
        self.write('browser/main.ts', '// dirty JavaScript is outside the candidate\n')
        self.assertEqual(self.verify()['languages'], ['python'])
        self.env['CODEQL_EXPECTED_LANGUAGES'] = '[]'
        with self.assertRaisesRegex(RESULTS.ResultError, 'independent immutable selection'): self.verify()
        self.env['CODEQL_EXPECTED_LANGUAGES'] = '["python"]'
        self.analyses[0]['commit_sha'] = old_candidate
        with self.assertRaises(RESULTS.ResultError): self.verify()
        self.analyses[0]['commit_sha'] = self.candidate
        for version in ('2.27.1', '2.27.3', None):
            self.analyses[0]['tool']['version'] = version
            with self.subTest(version=version), self.assertRaisesRegex(RESULTS.ResultError, 'reviewed extractor version'):
                self.verify()

    def test_pinned_result_requires_the_successful_version_step_before_analysis(self):
        self.pinned_policy_candidate()
        original = deepcopy(self.jobs[0]['steps'])
        mutations = [original[1:], original + [original[0]]]
        for key, value in (('conclusion', 'failure'), ('status', 'in_progress'),
                           ('started_at', '2026-10-15T21:00:12Z'),
                           ('completed_at', '2026-10-15T21:00:11Z')):
            changed = deepcopy(original); changed[0][key] = value; mutations.append(changed)
        for steps in mutations:
            self.jobs[0]['steps'] = steps
            with self.subTest(steps=steps), self.assertRaises(RESULTS.ResultError): self.verify()
        self.jobs[0]['steps'] = original
        self.assertEqual(self.verify()['languages'], ['python'])

    def test_pinned_policy_json_keeps_current_python_findings_required(self):
        self.pinned_policy_candidate()
        self.alerts = [{'number': 9, 'state': 'open', 'tool': {'name': 'CodeQL'}}]
        self.instances = {9: [{'ref': self.env['GITHUB_REF'], 'commit_sha': self.candidate,
            'category': '/language:python', 'state': 'open', 'analysis_key': RESULTS.ANALYSIS_KEY}]}
        with self.assertRaisesRegex(RESULTS.ResultError, 'open CodeQL finding'): self.verify()

    def test_pinned_result_verifier_independently_rejects_every_older_result_workflow(self):
        self.pinned_policy_candidate()
        for template in ('codeql-results.yml', 'metadata-edits/codeql.yml'):
            self.git('checkout', '-q', '--detach', self.base)
            self.write(RESULTS.WORKFLOW, (ROOT / 'tools/repository-checks/workflows' / template).read_text())
            head = self.commit()
            candidate = self.git('commit-tree', self.git('rev-parse', head + '^{tree}'),
                                 '-p', self.base, '-p', head, '-m', 'Reject pinned rollback fixture')
            self.git('checkout', '-q', '--detach', candidate)
            self.event['pull_request']['base']['sha'] = self.base
            self.event['pull_request']['head']['sha'] = head
            env = dict(self.env, GITHUB_SHA=candidate, GITHUB_WORKFLOW_SHA=candidate,
                       CODEQL_EXPECTED_LANGUAGES='["javascript-typescript","python"]')
            with self.subTest(template=template), self.assertRaisesRegex(RESULTS.ResultError, 'cannot be reverted'):
                RESULTS.Verifier(self.root, self.event, env, api=self.api).plan()

    def test_real_immutable_selection_success_accepts_nonzero_dismissed_result_count(self):
        result = self.verify()
        self.assertEqual(result['languages'], ['python'])
        self.assertEqual(result['analyses'], [{'id': 91, 'category': '/language:python', 'rules_count': 43, 'job_id': 81}])
        self.assertEqual(result['open_selected_findings'], 0)
        self.assertEqual(self.api.calls.count(RESULTS.PREFIX + '/pulls/42'), 2)
        self.assertNotIn('results_count', json.dumps(result))
        self.assertNotIn('location', json.dumps(result))

    def test_server_workflow_identity_and_fresh_api_replace_unreliable_event_merge_field(self):
        for event_merge in (None, self.base):
            self.event['pull_request']['merge_commit_sha'] = event_merge
            self.assertEqual(self.verify()['languages'], ['python'])
        self.assertFalse(any('/git/ref/pull/' in call for call in self.api.calls))
        for key, value in [('GITHUB_WORKFLOW_SHA', self.base),
                           ('GITHUB_WORKFLOW_REF', RESULTS.REPOSITORY + '/' + RESULTS.WORKFLOW + '@refs/heads/main')]:
            old = self.env[key]
            self.env[key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(RESULTS.ResultError, 'executed workflow source'):
                    self.verify()
            self.env[key] = old

    def test_latest_api_without_merge_sha_requires_the_current_ref_and_ordered_parents(self):
        del self.pr['merge_commit_sha']
        self.assertEqual(self.verify()['languages'], ['python'])
        self.assertEqual(self.api.calls.count(RESULTS.PREFIX + '/commits/refs/pull/42/merge?per_page=1&page=1'), 2)
        self.merge['sha'] = self.base
        with self.assertRaisesRegex(RESULTS.ResultError, 'ordered merge parents'):
            self.verify()
        self.merge['sha'] = self.candidate
        self.merge['parents'] = [{'sha': self.head}, {'sha': self.base}]
        with self.assertRaisesRegex(RESULTS.ResultError, 'ordered merge parents'):
            self.verify()

    def test_live_merge_ref_advancement_is_rejected_at_the_final_bookend(self):
        del self.pr['merge_commit_sha']
        seen = [0]
        def advance(endpoint):
            if endpoint.endswith('/commits/refs/pull/42/merge?per_page=1&page=1'):
                seen[0] += 1
                if seen[0] == 2:
                    self.merge['sha'] = self.base
        self.api.change = advance
        with self.assertRaisesRegex(RESULTS.ResultError, 'ordered merge parents'):
            self.verify()
        self.assertEqual(seen[0], 2)

    def test_original_child_workflow_is_base_only_and_unknown_workflows_still_reject(self):
        workflow = RESULTS.WORKFLOW
        original = 'name: Original child workflow fixture\non: push\njobs: {}\n'
        self.git('checkout', '-q', '--detach', self.base)
        self.write(workflow, original)
        base = self.commit()
        original_blob = self.git('rev-parse', base + ':' + workflow)
        self.write(workflow, (ROOT / workflow).read_text())
        head = self.commit()

        def select_at_merge(head):
            candidate = self.git('commit-tree', self.git('rev-parse', head + '^{tree}'),
                                 '-p', base, '-p', head, '-m', 'Child workflow transition fixture')
            self.git('checkout', '-q', '--detach', candidate)
            self.pr['base']['sha'], self.pr['head']['sha'] = base, head
            self.event['pull_request'] = deepcopy(self.pr)
            env = dict(self.env, GITHUB_SHA=candidate, GITHUB_WORKFLOW_SHA=candidate,
                       CODEQL_EXPECTED_LANGUAGES='["javascript-typescript","python"]')
            return RESULTS.Verifier(self.root, self.event, env, api=self.api).plan()

        # A synthetic approved baseline avoids relying on historical objects in
        # hosted shallow checkouts; the real six base blobs are checked offline.
        with patch.dict(RESULTS.codeql._REVIEWED_CONTROLS, {workflow: original_blob}):
            self.assertEqual(select_at_merge(head), ['javascript-typescript', 'python'])
        with self.assertRaisesRegex(RESULTS.ResultError, 'not approved'):
            select_at_merge(head)
        self.write(workflow, original)
        legacy_head = self.commit()
        with patch.dict(RESULTS.codeql._REVIEWED_CONTROLS, {workflow: original_blob}):
            with self.assertRaisesRegex(RESULTS.ResultError, 'not approved'):
                select_at_merge(legacy_head)

    def test_candidate_json_cannot_choose_languages_or_import_policy(self):
        self.event['languages'] = []
        self.env['CODEQL_EXPECTED_LANGUAGES'] = '[]'
        with self.assertRaisesRegex(RESULTS.ResultError, 'independent immutable selection'):
            self.verify()

    def test_selected_result_plan_rejects_deployed_successor_rollback_independently(self):
        workflow = RESULTS.WORKFLOW
        self.write(workflow, (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml').read_text())
        base = self.commit()
        self.write(workflow, (ROOT / 'tools/repository-checks/workflows/codeql-results.yml').read_text())
        head = self.commit()
        candidate = self.git('commit-tree', self.git('rev-parse', head + '^{tree}'),
                             '-p', base, '-p', head, '-m', 'Forbidden rollback fixture')
        self.git('checkout', '-q', '--detach', candidate)
        self.event['pull_request']['base']['sha'] = base
        self.event['pull_request']['head']['sha'] = head
        env = dict(self.env, GITHUB_SHA=candidate, GITHUB_WORKFLOW_SHA=candidate,
                   CODEQL_EXPECTED_LANGUAGES='["javascript-typescript","python"]')
        with self.assertRaisesRegex(RESULTS.ResultError, 'cannot be reverted'):
            RESULTS.Verifier(self.root, self.event, env, api=self.api).plan()

    def test_successor_retarget_verifies_current_candidate_results_and_rejects_old_sarif(self):
        old_candidate = self.candidate
        self.write(RESULTS.WORKFLOW, (ROOT / 'tools/repository-checks/workflows/metadata-edits/codeql.yml').read_text())
        self.base = self.commit()
        self.write('tools/check.py', '# changed Python after retarget baseline\n')
        self.head = self.commit()
        self.candidate = self.git('commit-tree', self.git('rev-parse', self.head + '^{tree}'),
                                  '-p', self.base, '-p', self.head, '-m', 'Current retarget merge fixture')
        self.git('checkout', '-q', '--detach', self.candidate)
        self.pr['base'].update(ref='apple-main', sha=self.base)
        self.pr['head']['sha'] = self.head
        self.pr['merge_commit_sha'] = self.candidate
        self.event.update(action='edited', changes={'base': {'ref': {'from': 'main'},
                                                            'sha': {'from': '1' * 40}}},
                          pull_request=deepcopy(self.pr))
        self.env.update(GITHUB_SHA=self.candidate, GITHUB_WORKFLOW_SHA=self.candidate, GITHUB_BASE_REF='apple-main')
        self.refs = {'heads/apple-main': self.base, 'heads/fix/main/example': self.head,
                     'pull/42/merge': self.candidate}
        self.merge = {'sha': self.candidate, 'parents': [{'sha': self.base}, {'sha': self.head}]}
        self.run['head_sha'] = self.head
        for job in self.jobs: job['head_sha'] = self.head
        self.analyses[0]['commit_sha'] = self.candidate
        self.assertEqual(self.verify()['languages'], ['python'])
        self.analyses[0]['commit_sha'] = old_candidate
        with self.assertRaises(RESULTS.ResultError): self.verify()

    def test_unknown_duplicate_languages_and_foreign_actions_repository_reject(self):
        for key, value in [('CODEQL_EXPECTED_LANGUAGES', '["python","python"]'),
                           ('CODEQL_EXPECTED_LANGUAGES', '["ruby"]'),
                           ('GITHUB_REPOSITORY', 'overte-org/overte'), ('GITHUB_RUN_ATTEMPT', '2')]:
            with self.subTest(key=key, value=value):
                env = dict(self.env, **{key: value})
                with self.assertRaises(RESULTS.ResultError):
                    RESULTS.Verifier(self.root, self.event, env, api=self.api).verify(processing_seconds=0)

    def test_foreign_api_repository_and_workflow_identity_reject(self):
        for target, key, value in [(self.run['repository'], 'full_name', 'overte-org/overte'),
                                   (self.run['head_repository'], 'id', 1),
                                   (self.run, 'workflow_id', 8), (self.run, 'path', '.github/workflows/fake.yml'),
                                   (self.run, 'head_sha', self.base), (self.run, 'run_attempt', 2)]:
            old = target[key]
            with self.subTest(key=key):
                target[key] = value
                with self.assertRaises(RESULTS.ResultError): self.verify()
                target[key] = old

    def test_failed_skipped_missing_duplicate_and_carried_old_jobs_reject(self):
        original = deepcopy(self.jobs)
        mutations = [[], original * 2]
        for key, value in [('conclusion', 'failure'), ('conclusion', 'skipped'), ('status', 'in_progress'),
                           ('run_attempt', 2), ('conclusion', 'cancelled'), ('head_sha', self.base), ('started_at', '2026-10-14T21:00:01Z')]:
            row = deepcopy(original[0]); row[key] = value
            mutations.append([row])
        for jobs in mutations:
            with self.subTest(jobs=jobs):
                self.jobs = jobs
                with self.assertRaises(RESULTS.ResultError): self.verify()
        self.jobs = original
        self.jobs[0]['steps'][0]['conclusion'] = 'skipped'
        with self.assertRaises(RESULTS.ResultError): self.verify()

    def test_stale_or_missing_analysis_wrong_category_environment_errors_and_zero_rules_reject(self):
        original = deepcopy(self.analyses[0])
        changes = [('commit_sha', self.base), ('category', '/language:javascript-typescript'),
                   ('environment', '{"language":"python","other":true}'), ('analysis_key', 'other:analyze'),
                   ('error', 'extractor failed'), ('rules_count', 0), ('rules_count', True),
                   ('created_at', '2026-10-15T20:59:00Z'), ('ref', 'refs/heads/main'),
                   ('tool', {'name': 'different'})]
        for key, value in changes:
            with self.subTest(key=key):
                self.analyses = [dict(original, **{key: value})]
                with self.assertRaises(RESULTS.ResultError): self.verify()
        self.analyses = []
        with self.assertRaises(RESULTS.ResultError): self.verify()
        self.analyses = [original, dict(original, id=92)]
        with self.assertRaisesRegex(RESULTS.ResultError, 'ambiguous'): self.verify()

    def test_any_open_selected_finding_blocks_without_severity_threshold(self):
        self.alerts = [{'number': 9, 'state': 'open', 'tool': {'name': 'CodeQL'}}]
        self.instances = {9: [{'ref': self.env['GITHUB_REF'], 'commit_sha': self.candidate,
                               'category': '/language:python', 'state': 'open', 'analysis_key': RESULTS.ANALYSIS_KEY}]}
        with self.assertRaisesRegex(RESULTS.ResultError, 'open CodeQL finding'): self.verify()
        self.instances[9][0]['commit_sha'] = self.base
        with self.assertRaisesRegex(RESULTS.ResultError, 'stale'): self.verify()
        self.instances[9][0]['state'] = 'fixed'
        self.assertEqual(self.verify()['open_selected_findings'], 0)
        self.instances[9][0]['state'] = 'dismissed'
        self.assertEqual(self.verify()['open_selected_findings'], 0)
        self.instances[9][0]['state'] = 'open'
        self.instances[9][0]['category'] = '/language:javascript-typescript'
        self.assertEqual(self.verify()['open_selected_findings'], 0)

    def test_changed_pr_branch_refs_merge_and_ordered_parents_reject(self):
        for target, key, value in [(self.pr['base'], 'sha', self.head), (self.pr['head'], 'ref', 'foreign'),
                                   (self.pr, 'merge_commit_sha', self.head), (self.refs, 'heads/main', self.head),
                                   (self.refs, 'heads/fix/main/example', self.base),
                                   (self.merge, 'parents', [{'sha': self.head}, {'sha': self.base}])]:
            old = deepcopy(target[key]); target[key] = value
            with self.subTest(key=key):
                with self.assertRaises(RESULTS.ResultError): self.verify()
            target[key] = old

    def test_fresh_bookends_reject_pr_advancement_future_attempt_and_analysis_replacement(self):
        for mutation in ('pr', 'attempt', 'analysis'):
            seen = [0]
            def change(endpoint):
                trigger = '/pulls/42' if mutation == 'pr' else '/actions/runs/12' if mutation == 'attempt' else '/code-scanning/analyses/91'
                if endpoint.endswith(trigger):
                    seen[0] += 1
                    if mutation == 'pr' and seen[0] == 2: self.pr['head']['sha'] = self.base
                    if mutation == 'attempt' and seen[0] == 2: self.run['run_attempt'] = 2
                    if mutation == 'analysis': self.analyses[0]['rules_count'] += 1
            self.api.change = change
            with self.subTest(mutation=mutation):
                with self.assertRaises(RESULTS.ResultError): self.verify()
            self.pr['head']['sha'] = self.head; self.run['run_attempt'] = 1; self.analyses[0]['rules_count'] = 43

    def test_all_pages_are_read_for_analyses_alerts_instances_and_jobs(self):
        self.jobs = [dict(self.jobs[0], id=1000 + i, name='unrelated') for i in range(100)] + self.jobs
        self.analyses = [dict(self.analyses[0], id=2000 + i, commit_sha=self.base) for i in range(100)] + self.analyses
        self.alerts = [{'number': i, 'state': 'open', 'tool': {'name': 'CodeQL'}} for i in range(1, 102)]
        self.instances = {i: [{'ref': self.env['GITHUB_REF'], 'commit_sha': self.candidate,
                              'category': '/language:javascript-typescript', 'state': 'open'}] for i in range(1, 102)}
        self.instances[101] = [dict(self.instances[101][0], ordinal=i) for i in range(100)] + [
            {'ref': self.env['GITHUB_REF'], 'commit_sha': self.candidate, 'category': '/language:python', 'state': 'open'}]
        with self.assertRaisesRegex(RESULTS.ResultError, 'open CodeQL finding'): self.verify()
        for endpoint in ('/jobs?', '/analyses?', '/alerts?', '/101/instances?'):
            self.assertTrue(any(endpoint in call and 'page=2' in call for call in self.api.calls), endpoint)

    def test_truncated_counted_inventory_and_api_errors_never_become_success_or_poll(self):
        self.job_total = len(self.jobs) + 1
        with self.assertRaisesRegex(RESULTS.ResultError, 'truncated'): self.verify()
        self.job_total = None
        self.api.error = RuntimeError('fake HTTP 403')
        with self.assertRaises(RuntimeError): self.verify()

    def test_repeated_and_excessive_array_pagination_reject_incomplete_inventory(self):
        record = deepcopy(self.analyses[0])
        self.analyses = [dict(record, id=1000 + index, commit_sha=self.base) for index in range(1000)]
        with self.assertRaisesRegex(RESULTS.ResultError, 'bounded pagination'): self.verify()
        self.analyses = [record, deepcopy(record)]
        with self.assertRaisesRegex(RESULTS.ResultError, 'repeated API'): self.verify()

    def test_only_missing_sarif_processing_can_poll_then_current_results_must_arrive(self):
        clock = [0]
        saved = deepcopy(self.analyses)
        self.analyses = []
        def sleep(seconds):
            clock[0] += seconds
            self.analyses = deepcopy(saved)
        result = RESULTS.Verifier(self.root, self.event, self.env, api=self.api,
                                  clock=lambda: clock[0], sleep=sleep).verify(processing_seconds=5)
        self.assertEqual(clock[0], 5)
        self.assertEqual(result['languages'], ['python'])

    def test_empty_languages_still_require_current_selector_success_but_no_analysis_or_alert_api(self):
        self.git('checkout', '-q', '--detach', self.base)
        self.write('docs/design.md', 'Changed Markdown only\n')
        self.head = self.commit()
        self.candidate = self.git('commit-tree', self.git('rev-parse', 'HEAD^{tree}'),
                                  '-p', self.base, '-p', self.head, '-m', 'Documentation merge')
        self.git('checkout', '-q', '--detach', self.candidate)
        self.env.update(CODEQL_EXPECTED_LANGUAGES='[]', GITHUB_SHA=self.candidate, GITHUB_WORKFLOW_SHA=self.candidate)
        self.pr['head']['sha'] = self.head
        self.pr['merge_commit_sha'] = self.candidate
        self.event['pull_request'] = deepcopy(self.pr)
        self.refs.update({'heads/fix/main/example': self.head, 'pull/42/merge': self.candidate})
        self.merge = {'sha': self.candidate, 'parents': [{'sha': self.base}, {'sha': self.head}]}
        self.run['head_sha'] = self.head
        self.jobs = [dict(self.jobs[-1], head_sha=self.head)]
        self.analyses = []
        self.assertEqual(self.verify()['analyses'], [])
        self.assertFalse(any('/code-scanning/' in call for call in self.api.calls))
        self.jobs[0]['conclusion'] = 'failure'
        with self.assertRaises(RESULTS.ResultError): self.verify()

    def test_seven_permanent_pr_targets_are_bound_and_arbitrary_target_is_rejected(self):
        for target in sorted(RESULTS.TARGETS):
            self.env['GITHUB_BASE_REF'] = target
            self.event['pull_request']['base']['ref'] = target
            self.pr['base']['ref'] = target
            self.refs['heads/' + target] = self.base
            with self.subTest(target=target):
                self.assertEqual(self.verify()['languages'], ['python'])
        self.env['GITHUB_BASE_REF'] = 'unreviewed-target'
        self.event['pull_request']['base']['ref'] = 'unreviewed-target'
        with self.assertRaisesRegex(RESULTS.ResultError, 'permanent target'):
            self.verify()

    def test_all_seven_push_targets_require_their_actual_branch_source(self):
        self.env.update(GITHUB_EVENT_NAME='push', GITHUB_REF_TYPE='branch')
        self.run.update(event='push', head_sha=self.candidate)
        for job in self.jobs: job['head_sha'] = self.candidate
        for target in sorted(RESULTS.TARGETS):
            ref = 'refs/heads/' + target
            self.env['GITHUB_REF'] = ref
            self.env['GITHUB_WORKFLOW_REF'] = RESULTS.REPOSITORY + '/' + RESULTS.WORKFLOW + '@' + ref
            self.event = {'repository': deepcopy(self.repo), 'before': self.base, 'after': self.candidate,
                          'deleted': False, 'ref': ref}
            self.refs['heads/' + target] = self.candidate
            self.run['head_branch'] = target
            self.analyses[0]['ref'] = ref
            with self.subTest(target=target):
                self.assertEqual(self.verify()['languages'], ['python'])

    def test_cli_uses_only_server_event_and_withholds_untrusted_error_details(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        import os
        import sys
        from unittest.mock import patch
        event_file = self.root / 'server-event.json'
        event_file.write_text(json.dumps(self.event))
        env = {**self.env, 'GITHUB_EVENT_PATH': str(event_file)}
        output, errors = io.StringIO(), io.StringIO()
        arguments = ['codeql_results.py', '--root', str(self.root), '--event-file', str(event_file)]
        with patch.dict(os.environ, env), patch.object(sys, 'argv', arguments), \
                patch.object(RESULTS, 'default_api', return_value=self.api), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(RESULTS.main(), 0)
        self.assertEqual(json.loads(output.getvalue())['languages'], ['python'])
        self.assertEqual(errors.getvalue(), '')
        self.api.error = RuntimeError('fake private API response must not appear')
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env), patch.object(sys, 'argv', arguments), \
                patch.object(RESULTS, 'default_api', return_value=self.api), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(RESULTS.main(), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('fake private', errors.getvalue())

    def test_push_and_schedule_bind_exact_branch_run_source_and_selection(self):
        for event_name in ('push', 'schedule'):
            with self.subTest(event=event_name):
                self.env.update(GITHUB_EVENT_NAME=event_name, GITHUB_REF='refs/heads/main', GITHUB_REF_TYPE='branch',
                                GITHUB_WORKFLOW_REF=RESULTS.REPOSITORY + '/' + RESULTS.WORKFLOW + '@refs/heads/main')
                self.event = {'repository': deepcopy(self.repo), 'before': self.base, 'after': self.candidate,
                              'deleted': False, 'ref': 'refs/heads/main'}
                self.refs['heads/main'] = self.candidate
                self.run.update(event=event_name, head_sha=self.candidate, head_branch='main')
                for job in self.jobs: job['head_sha'] = self.candidate
                self.analyses[0].update(ref='refs/heads/main')
                if event_name == 'schedule':
                    self.env['CODEQL_EXPECTED_LANGUAGES'] = json.dumps(list(CODEQL.LANGUAGES))
                    js = dict(self.jobs[0], id=82, name='CodeQL (javascript-typescript)')
                    self.jobs.append(js)
                    self.analyses.append(dict(self.analyses[0], id=92, category='/language:javascript-typescript',
                                              environment='{"language":"javascript-typescript"}'))
                self.assertEqual(self.verify()['languages'], json.loads(self.env['CODEQL_EXPECTED_LANGUAGES']))
                self.refs['heads/main'] = self.base
                with self.assertRaisesRegex(RESULTS.ResultError, 'advanced'): self.verify()



if __name__ == "__main__":
    unittest.main()
