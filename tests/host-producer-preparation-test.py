#!/usr/bin/env python3
"""Offline compatibility and trust-boundary tests for staged host receipts."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("host_receipt_package_policy", ROOT / "tools/repository-checks/package_checks.py")
PACKAGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGES)


def blob(data):
    return {"mode": "100644", "type": "blob",
            "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


class TemporaryGit:
    def temporary(self):
        directory = tempfile.TemporaryDirectory(prefix="overte-host-receipt-")
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def git(self, root, *args):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                                       cwd=root, text=True, stderr=subprocess.PIPE).strip()

    def initialize(self, root):
        self.git(root, "init", "-q", "--initial-branch=main")
        self.git(root, "config", "user.name", "Host receipt fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "config", "maintenance.auto", "false")
        self.git(root, "config", "gc.auto", "0")
        self.git(root, "config", "core.fileMode", "true")

    def write(self, root, relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


class WorkflowGenerationTests(TemporaryGit, unittest.TestCase):
    def setUp(self):
        self.generations = PACKAGES.workflow_generations()
        paths = list((ROOT / "tools/repository-checks/workflows").rglob("*.yml"))
        self.contents = {blob(path.read_bytes())["sha"]: path.read_bytes() for path in paths}
        # Immutable historical fixtures must survive later template edits and
        # remain available in shallow source snapshots without Git history.
        for oid in ('93f35c99ec6580b8796420997b1dcc586b7bfd95',
                    '861db7b76a11b9b8772e91cb24ec7cb9d918e339',
                    '6684e18785719813c51f9e3f5481a82ca40f0baf',
                    '84d98cac819755f98eecffba847e0bbcf667a6ca',
                    'c1d3d14a9098de214b6544dca8dcba0072090c6b',
                    'c01ff8a69f1ccbc60196da17e782c9a09defe4e5',
                    '1f8a7c3b4fe400a7c62ec2682de3f77d08dfd70d',
                    'b9022d17b985f93838b92cb42c7e2d873e7cb11f'):
            self.assertIn(oid, self.contents)
            self.assertEqual(blob(self.contents[oid])['sha'], oid)

    def materialize(self, generation):
        root = self.temporary()
        for path, entry in generation["workflows"].items():
            self.write(root, path, self.contents[entry["sha"]])
        return root

    def test_old_and_receipt_generations_each_accept_only_a_complete_tuple(self):
        self.assertTrue({"packages-v1", "packages-v1-direct", "shared-receipt-v1", "shared-receipt-v1-direct"}
                        .issubset({generation["name"] for generation in self.generations}))
        for generation in self.generations:
            with self.subTest(generation=generation["name"]):
                self.assertEqual(PACKAGES.validate_wiring(self.materialize(generation)), generation["name"])
                # Independently enumerated API entries include their own path.
                tree = {path: {"path": path, **entry} for path, entry in generation["workflows"].items()}
                self.assertEqual(PACKAGES.validate_tree_wiring(tree), generation["name"])

    def test_missing_unknown_nonregular_or_modified_workflow_cannot_pass(self):
        original = self.generations[0]["workflows"]
        for path in PACKAGES.WORKFLOW_PATHS:
            for mutation in (None, {"sha": "a" * 40}, {"mode": "100755"}, {"mode": "120000"},
                             {"type": "commit", "mode": "160000"}, {"sha": 1}):
                tree = deepcopy(original)
                if mutation is None:
                    del tree[path]
                else:
                    tree[path].update(mutation)
                with self.subTest(path=path, mutation=mutation), self.assertRaises(ValueError):
                    PACKAGES.validate_tree_wiring(tree)
        for change in ("missing", "modified", "executable", "symlink", "oversized"):
            root = self.materialize(self.generations[0])
            path = root / PACKAGES.WORKFLOW_PATHS[0]
            if change == "missing": path.unlink()
            elif change == "modified": path.write_bytes(path.read_bytes() + b"\n# unapproved\n")
            elif change == "executable": path.chmod(0o755)
            elif change == "symlink": path.unlink(); path.symlink_to(ROOT / PACKAGES.PRODUCER_TEMPLATE)
            else: path.write_bytes(b"x" * 1_000_001)
            with self.subTest(change=change), self.assertRaises(ValueError):
                PACKAGES.validate_wiring(root)

    def test_individually_known_workflows_cannot_be_mixed_between_generations(self):
        policy = self.temporary()
        first = deepcopy(self.generations[0])
        second = deepcopy(first)
        first["name"], second["name"] = "first", "second"
        for path in PACKAGES.WORKFLOW_PATHS[:2]:
            second["workflows"][path]["sha"] = "a" * 40
        manifest = {"schema": 1, "repository": {"full_name": PACKAGES.REPOSITORY, "id": PACKAGES.REPOSITORY_ID},
                    "generations": [first, second]}
        self.write(policy, PACKAGES.GENERATION_MANIFEST, json.dumps(manifest).encode())
        mixed = deepcopy(first["workflows"])
        mixed[PACKAGES.WORKFLOW_PATHS[0]] = second["workflows"][PACKAGES.WORKFLOW_PATHS[0]]
        with patch.object(PACKAGES, "ROOT", policy):
            self.assertEqual(PACKAGES.validate_tree_wiring(first["workflows"]), "first")
            self.assertEqual(PACKAGES.validate_tree_wiring(second["workflows"]), "second")
            with self.assertRaises(ValueError): PACKAGES.validate_tree_wiring(mixed)

    def test_protected_producer_requires_the_complete_new_pair_and_all_five_siblings(self):
        previous = next(g for g in self.generations if g['name'] == 'android-owned-npm5-sync-ci-v1')
        prospective = next(g for g in self.generations if g['name'] == 'protected-shared-producer-v1')
        self.assertEqual(set(prospective['workflows']), set(PACKAGES.CONSUMER_WORKFLOW_PATHS))
        self.assertEqual(len(self.generations), 21)
        for path in prospective['workflows']:
            if path not in {'.github/workflows/repository-checks.yml', '.github/workflows/project-tests.yml'}:
                self.assertEqual(prospective['workflows'][path], previous['workflows'][path])
        for path in ('.github/workflows/repository-checks.yml', '.github/workflows/project-tests.yml'):
            mixed = deepcopy(prospective['workflows'])
            mixed[path] = deepcopy(previous['workflows'][path])
            with self.subTest(mixed=path), self.assertRaises(ValueError):
                PACKAGES.validate_tree_wiring(mixed)
        for path in prospective['workflows']:
            for mutation in (None, {'mode': '100755'}, {'mode': '120000'}, {'type': 'commit', 'mode': '160000'}, {'sha': 'a' * 40}):
                mixed = deepcopy(prospective['workflows'])
                if mutation is None: del mixed[path]
                else: mixed[path].update(mutation)
                with self.subTest(path=path, mutation=mutation), self.assertRaises(ValueError):
                    PACKAGES.validate_tree_wiring(mixed)

    def test_candidate_generation_manifest_never_authorizes_its_own_workflows(self):
        root = self.materialize(self.generations[0])
        path = PACKAGES.WORKFLOW_PATHS[0]
        self.write(root, path, b"candidate-controlled owner\n")
        forged = deepcopy(self.generations[0])
        forged["workflows"][path] = blob((root / path).read_bytes())
        self.write(root, PACKAGES.GENERATION_MANIFEST, json.dumps({"schema": 1,
            "repository": {"full_name": PACKAGES.REPOSITORY, "id": PACKAGES.REPOSITORY_ID},
            "generations": [forged]}).encode())
        with self.assertRaises(ValueError): PACKAGES.validate_wiring(root)

    def test_metadata_generation_requires_the_complete_six_ordinary_immutable_entries(self):
        for name in ('protected-producer-metadata-ci-v1', 'protected-producer-seven-target-ci-v1'):
            generation = next(row for row in self.generations if row['name'] == name)
            original = generation['workflows']
            self.assertEqual(set(original), set(PACKAGES.METADATA_WORKFLOW_PATHS))
            self.assertEqual(PACKAGES.validate_tree_wiring(original), name)
            for path in original:
                known_other = next(value for row in self.generations for value in row['workflows'].values()
                                   if value != original[path])
                for change in ('missing', 'neighbor', 'mixed-known', 'executable', 'symlink', 'gitlink', 'unknown'):
                    tree = deepcopy(original)
                    if change == 'missing': del tree[path]
                    elif change == 'neighbor': tree[path + '.neighbor.yml'] = tree.pop(path)
                    elif change == 'mixed-known': tree[path] = deepcopy(known_other)
                    elif change == 'executable': tree[path]['mode'] = '100755'
                    elif change == 'symlink': tree[path]['mode'] = '120000'
                    elif change == 'gitlink': tree[path].update(mode='160000', type='commit')
                    else: tree[path]['sha'] = 'a' * 40
                    with self.subTest(generation=name, path=path, change=change), self.assertRaises(ValueError):
                        PACKAGES.validate_tree_wiring(tree)

    def test_seven_target_generation_binds_all_canonical_sources_and_retains_metadata_baseline(self):
        generation = next(row for row in self.generations if row['name'] == 'protected-producer-seven-target-ci-v1')
        canonical = {
            '.github/workflows/project-tests.yml': 'producers/protected-project-tests.yml',
            '.github/workflows/parent-qualification.yml': 'producers/parent-qualification.yml',
            '.github/workflows/repository-checks.yml': 'producers/repository-checks.yml',
            '.github/workflows/sync-validation.yml': 'sync-ci-selection.yml',
            '.github/workflows/browser-client.yml': 'npm-consumers/browser-client.yml',
            '.github/workflows/pr-metadata-context.yml': 'metadata-edits/pr-metadata-context.yml',
        }
        expected = {}
        for target, relative in canonical.items():
            path = ROOT / 'tools/repository-checks/workflows' / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            expected[target] = blob(path.read_bytes())
        self.assertEqual(generation['workflows'], expected)
        self.assertEqual(PACKAGES.validate_tree_wiring(expected), generation['name'])
        previous = next(row for row in self.generations if row['name'] == 'protected-producer-metadata-ci-v1')
        for target, filename, oid in (
                ('.github/workflows/project-tests.yml', 'protected-project-tests', 'c01ff8a69f1ccbc60196da17e782c9a09defe4e5'),
                ('.github/workflows/parent-qualification.yml', 'parent-qualification', '1f8a7c3b4fe400a7c62ec2682de3f77d08dfd70d'),
                ('.github/workflows/repository-checks.yml', 'repository-checks', 'b9022d17b985f93838b92cb42c7e2d873e7cb11f')):
            frozen = ROOT / ('tools/repository-checks/workflows/producers/legacy/' + filename + '-metadata-v1.yml')
            self.assertEqual(blob(frozen.read_bytes())['sha'], oid)
            self.assertEqual(previous['workflows'][target], blob(frozen.read_bytes()))
            self.assertNotEqual(expected[target], previous['workflows'][target])
        for target in set(expected) - {'.github/workflows/project-tests.yml', '.github/workflows/parent-qualification.yml',
                                       '.github/workflows/repository-checks.yml'}:
            self.assertEqual(expected[target], previous['workflows'][target])

    def test_metadata_candidate_and_immutable_base_cannot_omit_or_alias_the_sixth_workflow(self):
        generation = next(row for row in self.generations if row['name'] == 'protected-producer-metadata-ci-v1')
        helper = '.github/workflows/pr-metadata-context.yml'
        for change in ('valid', 'missing', 'mixed-known', 'executable', 'symlink'):
            root = self.materialize(generation)
            path = root / helper
            if change == 'missing': path.unlink()
            elif change == 'mixed-known': path.write_bytes(self.contents[self.generations[0]['workflows'][PACKAGES.WORKFLOW_PATHS[0]]['sha']])
            elif change == 'executable': path.chmod(0o755)
            elif change == 'symlink': path.unlink(); path.symlink_to(ROOT / PACKAGES.PRODUCER_TEMPLATE)
            with self.subTest(change=change):
                if change == 'valid':
                    self.assertEqual(PACKAGES.validate_wiring(root), generation['name'])
                    self.assertTrue(PACKAGES.consumer_generation(root))
                else:
                    with self.assertRaises(ValueError): PACKAGES.validate_wiring(root)
                    with self.assertRaises(ValueError): PACKAGES.consumer_generation(root)
        root = self.materialize(generation)
        self.initialize(root)
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'Complete six-workflow immutable fixture')
        self.assertTrue(PACKAGES.consumer_base(root, self.git(root, 'rev-parse', 'HEAD')))
        self.git(root, 'rm', helper)
        self.git(root, 'commit', '-qm', 'Missing sixth workflow immutable negative')
        self.assertFalse(PACKAGES.consumer_base(root, self.git(root, 'rev-parse', 'HEAD')))

    def test_unrelated_source_and_sparse_candidate_do_not_change_generation_identity(self):
        root = self.materialize(self.generations[2])
        self.write(root, "unrelated/source.py", b"raise RuntimeError('must never execute')\n")
        self.initialize(root)
        self.git(root, "add", "."); self.git(root, "commit", "-qm", "Approved sparse candidate fixture")
        sparse = self.temporary() / "candidate"
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(root), str(sparse)], check=True, capture_output=True)
        self.git(sparse, "sparse-checkout", "set", ".github")
        self.git(sparse, "checkout", "-q", "HEAD")
        self.assertFalse((sparse / "unrelated/source.py").exists())
        self.assertEqual(PACKAGES.validate_wiring(sparse), self.generations[2]["name"])


class TrustedGenerationPolicyTests(TemporaryGit, unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / PACKAGES.GENERATION_MANIFEST).read_text())

    def policy(self, document):
        root = self.temporary()
        self.write(root, PACKAGES.GENERATION_MANIFEST, document if isinstance(document, bytes) else json.dumps(document).encode())
        return root

    def test_unknown_foreign_duplicate_partial_and_corrupt_policy_fails_closed(self):
        cases = [b"not-json", b"x" * 64_001, {}, {**self.document, "schema": True},
                 {**self.document, "schema": 2}, {**self.document, "extra": True},
                 {**self.document, "repository": {"full_name": "overte-org/overte", "id": 1}},
                 {**self.document, "generations": []}]
        for change in ("name", "tuple", "path", "mode", "zero", "fields"):
            value = deepcopy(self.document)
            generation = value["generations"][0]
            if change == "name": value["generations"][1]["name"] = generation["name"]
            elif change == "tuple": value["generations"][1]["workflows"] = deepcopy(generation["workflows"])
            elif change == "path": generation["workflows"].pop(PACKAGES.WORKFLOW_PATHS[0])
            elif change == "mode": generation["workflows"][PACKAGES.WORKFLOW_PATHS[0]]["mode"] = "100755"
            elif change == "zero": generation["workflows"][PACKAGES.WORKFLOW_PATHS[0]]["sha"] = "0" * 40
            else: generation["extra"] = True
            cases.append(value)
        cases.append(json.dumps(self.document).replace('"schema": 1', '"schema": 1, "schema": 1').encode())
        for value in cases:
            root = self.policy(value)
            with self.subTest(value=str(value)[:80]), patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError):
                PACKAGES.workflow_generations()
        for change in ("missing", "symlink", "directory"):
            root = self.policy(self.document)
            path = root / PACKAGES.GENERATION_MANIFEST
            path.unlink()
            if change == "symlink": path.symlink_to(ROOT / PACKAGES.GENERATION_MANIFEST)
            elif change == "directory": path.mkdir()
            with self.subTest(change=change), patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError):
                PACKAGES.workflow_generations()

    def trusted_fixture(self):
        identities = PACKAGES._policy_inputs()
        root = self.temporary()
        for relative in identities:
            self.write(root, relative, (ROOT / relative).read_bytes())
        self.initialize(root)
        self.git(root, "add", "."); self.git(root, "commit", "-qm", "Trusted policy input fixture")
        return root, identities

    def test_complete_trusted_helpers_and_transitive_requirements_are_bound(self):
        root, baseline = self.trusted_fixture()
        required = {PACKAGES.GENERATION_MANIFEST, PACKAGES.PRODUCER_TEMPLATE, ".github/test-suites.json",
                    "tools/test-evidence/run.py", "tests/run-project-tests.py", "tests/platform-profile.json",
                    "tools/sync-test-reuse/qualification.py", "tests/requirements-host.txt",
                    "tests/requirements-repository.txt", "tools/sbom/requirements-validation.txt"}
        self.assertLessEqual(required, set(baseline))
        for relative in required:
            path = root / relative
            previous = path.read_bytes()
            # Preserve valid JSON/pins while changing exact trusted bytes.
            path.write_bytes(previous + b"\n")
            with patch.object(PACKAGES, "ROOT", root):
                self.assertNotEqual(baseline, PACKAGES._policy_inputs(), relative)
            path.write_bytes(previous)

    def test_old_trusted_sparse_layout_has_exactly_the_same_complete_policy_hash(self):
        root, baseline = self.trusted_fixture()
        sparse = self.temporary() / "trusted"
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(root), str(sparse)], check=True, capture_output=True)
        # The existing outer caller intentionally remains byte-identical.
        self.git(sparse, "sparse-checkout", "set", ".github", "tools/repository-checks", "tools/test-evidence",
                 "tools/native-tests", "tools/ios-build-qualification")
        self.git(sparse, "checkout", "-q", "HEAD")
        self.assertFalse((sparse / "tests/requirements-host.txt").exists())
        self.assertFalse((sparse / "tools/sbom/requirements-validation.txt").exists())
        with patch.object(PACKAGES, "ROOT", sparse):
            self.assertEqual(PACKAGES._policy_inputs(), baseline)
        # Ordinary deletion must not be mistaken for an omitted sparse input.
        (root / "tests/requirements-host.txt").unlink()
        with patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError): PACKAGES._policy_inputs()

    def test_unknown_requirement_graph_fails_closed(self):
        for source in (b"-r ../../outside.txt\n", b"-r absent.txt\n", b"requests>=1\n",
                       b"Thing==1\nthing==2\n", b"x" * 100_001):
            root = self.temporary()
            self.write(root, "tests/requirements-host.txt", source)
            with self.subTest(source=source[:40]), patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError):
                PACKAGES._requirement_paths()

    def test_recursive_requirement_additions_and_changes_are_in_the_policy_identity(self):
        root, baseline = self.trusted_fixture()
        host = root / "tests/requirements-host.txt"
        host.write_bytes(host.read_bytes() + b"\n-r ../extra/validation-pins.txt\n")
        path = self.write(root, "extra/validation-pins.txt", b"FixtureDependency==1\n")
        with patch.object(PACKAGES, "ROOT", root):
            added = PACKAGES._policy_inputs()
            self.assertIn("extra/validation-pins.txt", added)
            self.assertNotEqual(added, baseline)
            path.write_bytes(b"FixtureDependency==2\n")
            self.assertNotEqual(added, PACKAGES._policy_inputs())

    def test_symlink_gitlink_and_oversized_trusted_sparse_blobs_cannot_be_hashed(self):
        for change in ("symlink", "gitlink", "oversized"):
            root, _ = self.trusted_fixture()
            relative = "tests/requirements-host.txt"
            path = root / relative
            if change == "symlink":
                path.unlink(); path.symlink_to("requirements-repository.txt")
                self.git(root, "add", relative)
            elif change == "gitlink":
                revision = self.git(root, "rev-parse", "HEAD")
                self.git(root, "rm", "-q", relative)
                self.git(root, "update-index", "--add", "--cacheinfo", "160000," + revision + "," + relative)
            else:
                path.write_bytes(b"x" * 100_001)
                self.git(root, "add", relative)
            self.git(root, "commit", "-qm", "Unproven trusted sparse requirement fixture")
            sparse = self.temporary() / "trusted"
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(root), str(sparse)],
                           check=True, capture_output=True)
            self.git(sparse, "sparse-checkout", "set", ".github", "tools/repository-checks", "tools/test-evidence")
            self.git(sparse, "checkout", "-q", "HEAD")
            self.assertFalse((sparse / relative).exists())
            with self.subTest(change=change), patch.object(PACKAGES, "ROOT", sparse), self.assertRaises(ValueError):
                PACKAGES._policy_inputs()


class ProtectedProducerPermissionTests(unittest.TestCase):
    def test_caller_grants_exact_read_ceiling_only_to_native_owner_roles(self):
        old = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/android-owned/repository-checks.yml').read_text())
        source = (ROOT / 'tools/repository-checks/workflows/producers/repository-checks.yml').read_text()
        prospective = yaml.safe_load(source)
        permissions = {'contents': 'read', 'actions': 'read', 'pull-requests': 'read', 'checks': 'read'}
        expected = deepcopy(old)
        expected['jobs']['project']['permissions'] = permissions
        expected['jobs']['metadata-source'] = {
            'name': 'Authenticate PR text edit',
            'if': "github.event_name == 'pull_request' && github.base_ref == 'main' && github.event.action == 'edited' && !github.event.changes.base && (github.event.changes.title || github.event.changes.body)",
            'uses': './.github/workflows/pr-metadata-context.yml',
        }
        route = expected['jobs']['route']
        route['needs'] = 'metadata-source'
        route['if'] = "always() && (needs.metadata-source.result == 'success' || needs.metadata-source.result == 'skipped')"
        route['permissions'] = {'contents': 'read', 'actions': 'read', 'pull-requests': 'read'}
        event = next(step for step in route['steps'] if step.get('id') == 'event')
        event['env'] = {'GH_TOKEN': '${{ github.token }}',
                        'NATIVE_METADATA_INTENT': '${{ needs.metadata-source.outputs.metadata_intent }}'}
        docs = expected['jobs']['documentation']
        docs['needs'] = ['route', 'project']
        docs['if'] = "always() && needs.route.result == 'success' && (needs.project.result == 'success' || needs.project.result == 'skipped') && needs.route.outputs.metadata_only != 'true' && needs.project.outputs.documentation_verified != 'true'"
        expected['jobs']['workflow-security']['with'] = {'defer_workflow_contracts': True}
        expected['jobs']['workflow-contracts'] = {
            'needs': ['route', 'project'],
            'if': "always() && needs.route.result == 'success' && (needs.project.result == 'success' || needs.project.result == 'skipped') && needs.route.outputs.metadata_only != 'true' && needs.route.outputs.security == 'true' && needs.project.outputs.workflow_contracts_verified != 'true'",
            'runs-on': 'ubuntu-24.04', 'timeout-minutes': 5,
            'steps': [{'name': 'Check out the exact candidate without credentials',
                'uses': 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
                'with': {'ref': '${{ github.sha }}', 'fetch-depth': 2, 'persist-credentials': False}},
                {'name': 'Verify remaining workflow contracts',
                 'run': 'PYTHONDONTWRITEBYTECODE=1 python3 tests/workflow-contract-test.py'}]}
        outer = expected['jobs']['repository-checks']
        outer['permissions'] = permissions
        outer['needs'].insert(outer['needs'].index('native'), 'workflow-contracts')
        candidate = next(step['with'] for step in outer['steps'] if step.get('with', {}).get('path') == 'candidate')
        candidate.update({'sparse-checkout-cone-mode': False,
                          'sparse-checkout': '.github\ntests/platform-profile.json\n'})
        verify = outer['steps'][-1]
        verify['env']['GH_TOKEN'] = '${{ github.token }}'
        verify['run'] = verify['run'].replace(' verify --needs-json', ' verify --event "$GITHUB_EVENT_PATH" --needs-json')
        self.assertEqual(prospective, expected)
        self.assertEqual(prospective['permissions'], {'contents': 'read'})
        self.assertEqual(prospective['jobs']['project']['uses'], './.github/workflows/project-tests.yml')
        self.assertNotIn('secrets', prospective['jobs']['project'])
        callee = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests.yml').read_text())
        self.assertEqual(callee['permissions'], {'contents': 'read'})
        for name, job in callee['jobs'].items():
            actual = job.get('permissions', callee['permissions'])
            self.assertTrue(all(value == 'read' and permissions.get(key) == 'read' for key, value in actual.items()), name)
            self.assertEqual(actual, permissions if name in {'route', 'project-tests', 'producer-publication'} else {'contents': 'read'}, name)

    def test_callee_retains_permissions_readers_and_exact_historical_baseline(self):
        source = (ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests.yml').read_bytes()
        self.assertEqual(source.count(b'      checks: read\n'), 3)
        self.assertEqual(source.count(b'          tools/branch-policy/check.py\n'), 6)
        self.assertEqual(source.count(b'        sparse-checkout-cone-mode: false\n'), 6)
        historical = (ROOT / 'tools/repository-checks/workflows/producers/legacy/protected-project-tests-postmerge-v1.yml').read_bytes()
        self.assertEqual(blob(historical)['sha'], '861db7b76a11b9b8772e91cb24ec7cb9d918e339')
        previous = historical.replace(b'          tools/branch-policy/check.py\n', b'').replace(
            b'        sparse-checkout-cone-mode: false\n', b'').replace(b'      checks: read\n', b'').replace(
            b'# Prospective protected producer; dormant wiring approved, production guards false.',
            b'# Prospective protected producer; production guards false and no active generation approval.')
        actual = subprocess.check_output(['/usr/bin/git', 'hash-object', '--stdin'], input=previous).decode().strip()
        self.assertEqual(actual, 'cad732c967d4d18b5a341c578b90789a271c02e9')


class ReceiptWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.old = yaml.safe_load((PACKAGES.TEMPLATES / "project-tests.yml").read_text())
        self.new = yaml.safe_load((ROOT / PACKAGES.PRODUCER_TEMPLATE).read_text())

    def test_only_full_host_execution_changes_and_other_owner_jobs_remain_identical(self):
        for key in self.old:
            if key != "jobs": self.assertEqual(self.old[key], self.new[key], key)
        self.assertEqual(set(self.old["jobs"]), set(self.new["jobs"]))
        for name in self.old["jobs"]:
            if name != "project-tests": self.assertEqual(self.old["jobs"][name], self.new["jobs"][name], name)
        previous, current = self.old["jobs"]["project-tests"], self.new["jobs"]["project-tests"]
        for key in previous:
            if key != "steps": self.assertEqual(previous[key], current[key], key)
        before = {step["name"]: step for step in previous["steps"]}
        after = {step["name"]: step for step in current["steps"]}
        for name in ("Set up Python", "Set up Node.js", "Set up Java", "Verify runner prerequisites",
                     "Install QML and portable C++ contract prerequisites"):
            self.assertEqual(before[name], after[name], name)

    def test_exact_candidate_trusted_requirements_controller_and_external_receipt_paths(self):
        steps = self.new["jobs"]["project-tests"]["steps"]
        trusted, candidate = steps[:2]
        self.assertEqual(trusted["with"]["ref"], "${{ github.event.repository.default_branch }}")
        self.assertEqual(trusted["with"]["path"], "trusted")
        self.assertFalse(trusted["with"]["sparse-checkout-cone-mode"])
        self.assertEqual(candidate["with"]["ref"], "${{ github.sha }}")
        self.assertEqual(candidate["with"]["path"], "candidate")
        self.assertEqual(candidate["with"]["fetch-depth"], 2)
        self.assertTrue(all(not step["with"]["persist-credentials"] for step in steps
                            if step.get("uses", "").startswith("actions/checkout@")))
        prepare = next(step for step in steps if step["name"] == "Prepare isolated host evidence validators")
        self.assertIn('-r trusted/tests/requirements-host.txt', prepare["run"])
        self.assertIn('python3 -m venv "$RUNNER_TEMP/overte-shared-host-env"', prepare["run"])
        self.assertIn('unshare --user --map-root-user --net true', prepare["run"])
        execute = next(step for step in steps if step["name"].startswith("Execute the complete trusted"))
        for expected in ('trusted/tools/test-evidence/run.py', '--candidate candidate --include-platform',
                         '--timeout 240 --host-timeout 900', '--junit "$RUNNER_TEMP/', '--receipt "$RUNNER_TEMP/'):
            self.assertIn(expected, execute["run"])
        self.assertNotIn('--suite', execute["run"])
        self.assertNotIn('candidate/tests/run-project-tests.py', execute["run"])
        self.assertEqual(execute["env"], {"GH_TOKEN": "", "GITHUB_TOKEN": ""})
        receipt = next(step for step in steps if step["name"] == "Preserve actual execution receipt for diagnosis")
        self.assertEqual(receipt["if"], "always()")
        self.assertEqual(receipt["with"]["path"], "${{ runner.temp }}/overte-shared-host-results/execution.json")
        self.assertIn('${{ github.run_id }}-attempt-${{ github.run_attempt }}', receipt["with"]["name"])
        self.assertNotIn('continue-on-error', execute)
        self.assertNotIn('descriptor', json.dumps(self.new))

    def test_sparse_controller_contains_actual_runtime_and_recursive_requirement_inputs(self):
        runtime = PACKAGES.load("host_receipt_runtime_contract", "tools/test-evidence/runtime.py")
        _, manifests = runtime._requirement_inventory(ROOT)
        patterns = self.new["jobs"]["project-tests"]["steps"][0]["with"]["sparse-checkout"].splitlines()
        required = {*runtime._TRUSTED_EXECUTION_FILES, *manifests, ".github/test-suites.json", "tests/platform-profile.json"}
        for path in required:
            self.assertTrue(any(path == pattern or path.startswith(pattern + "/") for pattern in patterns), path)


if __name__ == "__main__":
    unittest.main()
