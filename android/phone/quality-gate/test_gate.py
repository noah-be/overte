# SPDX-License-Identifier: Apache-2.0
"""Offline contract tests. No scanners, builds, network or devices are invoked."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
from core import Gate
from evidence import regular_file, write_receipt, validate_receipt, FIXED_FILES, MODULE
from runtime_checks import archive_members
from source_checks import materialize, secrets, dependencies, licenses


class GateContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        for args in [('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        (self.root / 'input.txt').write_text('ordinary public source\n')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Fixture'], cwd=self.root, check=True)
        self.out = self.base / 'out'
        self.out.mkdir()
        policy = json.loads(Path(__file__).with_name('policy.json').read_text())
        policy['source_files'] = ['input.txt']
        self.g = Gate(self.root, self.out, {}, policy)
        materialize(self.g)

    def test_missing_tool_blocks(self):
        self.g.run('missing', [str(self.base / 'absent')])
        self.assertEqual(self.g.findings[-1]['rule'], 'tool-missing')

    def test_timeout_blocks(self):
        self.g.run('timeout', [sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.05)
        self.assertEqual(self.g.findings[-1]['rule'], 'tool-timeout')

    def test_nonzero_blocks(self):
        self.g.run('nonzero', [sys.executable, '-c', 'raise SystemExit(7)'])
        self.assertEqual(self.g.findings[-1]['rule'], 'command-failed')

    def test_partial_is_never_release_pass(self):
        self.g.completed = ['secrets']
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.g.report(['secrets']), 1)
        report = json.loads((self.out / 'report.json').read_text())
        self.assertEqual(report['categories']['secrets'], 'PASS')
        self.assertTrue(report['result'].endswith('FAIL'))

    def test_source_mutation_rejected(self):
        (self.root / 'input.txt').write_text('changed')
        with self.assertRaises(ValueError):
            self.g.assert_source_unchanged()

    def test_scanner_failure_with_empty_report_rejected(self):
        def fake_run(label, argv, **kwargs):
            Path(argv[argv.index('--report-path') + 1]).write_text('[]')
            return 1, self.out / 'unused'
        with patch.object(self.g, 'tool', return_value=True), patch.object(self.g, 'run', side_effect=fake_run):
            with self.assertRaises(ValueError):
                secrets(self.g)

    def test_missing_scanner_report_blocks(self):
        with patch.object(self.g, 'tool', return_value=True), patch.object(self.g, 'run', return_value=(0, self.out / 'unused')):
            secrets(self.g)
        self.assertEqual(len([r for r in self.g.findings if r['rule']=='gitleaks-report']), 2)

    def test_exception_is_hash_bound_and_not_for_artifacts(self):
        self.g.exceptions = [dict(rule='fixture', path='input.txt', sha256=self.g.source_hashes['input.txt'],
                                 reason='Synthetic fixture', owner='Test', expires='2099-01-01')]
        self.g.finding('fixture', 'FAIL', 'input.txt', 'fixture', 'review')
        self.assertEqual(self.g.findings[-1]['status'], 'WARNING')
        self.g.category = 'artifact'
        self.g.finding('fixture', 'FAIL', 'input.txt', 'fixture', 'review')
        self.assertEqual(self.g.findings[-1]['status'], 'FAIL')
        self.g.category = 'secrets'
        self.g.exceptions[0]['expires'] = '2000-01-01'
        self.g.finding('fixture', 'FAIL', 'input.txt', 'fixture', 'review')
        self.assertEqual(self.g.findings[-1]['status'], 'FAIL')

    def test_unreviewed_manual_evidence_blocks(self):
        self.g.review('licenses')
        self.assertEqual(len(self.g.findings), 3)
        self.assertTrue(all(r['status']=='FAIL' for r in self.g.findings))

    def test_evidence_escape_and_symlink_rejected(self):
        (self.out / 'link').symlink_to(self.root / 'input.txt')
        for name in ('../repo/input.txt', 'link', '/etc/passwd'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                regular_file(self.out, name)

    def test_unsafe_and_oversize_archives_rejected(self):
        for name, size in [('../escape', 1), ('/absolute', 1), ('safe', 3)]:
            self.g.policy['max_archive_member_bytes'] = 2
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr(name, b'x' * size)
            stream.seek(0)
            with zipfile.ZipFile(stream) as z, self.assertRaises(ValueError):
                archive_members(self.g, z)

    def test_timestamp_is_not_a_dynamic_dependency(self):
        self.g.files = ['recipe.lock.json']
        (self.out / 'source-scope/recipe.lock.json').write_text(
            '{"measured_at": "2026-09-05T11:09:58+02:00"}')
        with patch.object(self.g, 'review'):
            dependencies(self.g)
        self.assertFalse(any(r['rule']=='dynamic-dependency' for r in self.g.findings))

    def test_real_dynamic_dependencies_still_block(self):
        self.g.files = ['build.gradle']
        (self.out / 'source-scope/build.gradle').write_text(
            "implementation 'org.example:library:1.+'\nimplementation 'org.example:other:2-SNAPSHOT'")
        with patch.object(self.g, 'review'):
            dependencies(self.g)
        self.assertEqual(len([r for r in self.g.findings if r['rule']=='dynamic-dependency']), 2)

    def test_receipt_rejects_changed_build_evidence(self):
        self.g.attempt = self.out / 'attempt'
        self.g.attempt.mkdir()
        extra = [MODULE + 'build/outputs/bundle/release/app.aab',
                 MODULE + 'build/outputs/logs/manifest-merger-release-report.txt',
                 MODULE + '.cxx/Release/fixture/arm64-v8a/compile_commands.json']
        for rel in [*FIXED_FILES.values(), *extra]:
            path = self.g.attempt / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        self.g.artifact = self.g.attempt / FIXED_FILES['apk']
        self.g.config.update(builder_image='sha256:' + '1'*64, version_code=2, version_name='test')
        write_receipt(self.g)
        self.assertEqual(validate_receipt(self.g), self.g.artifact)
        (self.g.attempt / FIXED_FILES['gradle']).write_text('changed dependency evidence')
        with self.assertRaises(ValueError):
            validate_receipt(self.g)

    def test_scanner_resource_limit_rejects_invalid_values(self):
        for value in (0, 9, True, '2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Gate(self.root, self.out, {'scancode_processes': value}, self.g.policy)

    def test_failed_license_scan_keeps_file_diagnostics(self):
        def fake_run(label, argv, **kwargs):
            report = Path(argv[argv.index('--json-pp') + 1])
            report.write_text(json.dumps({'files': [{'path': 'source-scope/input.txt',
                'type': 'file', 'scan_errors': ['synthetic per-file failure'],
                'detected_license_expression_spdx': None}]}))
            return 1, self.out / 'unused'
        with patch.object(self.g, 'tool', return_value=True), patch.object(self.g, 'run', side_effect=fake_run), patch.object(self.g, 'review'):
            licenses(self.g)
        errors = [r for r in self.g.findings if r['rule']=='license-scan-error']
        self.assertEqual([r['path'] for r in errors], ['input.txt'])
        self.assertEqual(errors[0]['status'], 'FAIL')

    def test_vcs_license_metadata_is_scanned_explicitly(self):
        self.g.source_hashes['.gitignore'] = 'fixture-hash'
        (self.out / 'source-scope/.gitignore').write_text('build/\n')
        calls = []
        def fake_run(label, argv, **kwargs):
            calls.append(label)
            path = 'source-scope/input.txt' if label=='scancode' else '.gitignore'
            Path(argv[argv.index('--json-pp') + 1]).write_text(json.dumps({'files': [
                {'path': path, 'type': 'file', 'scan_errors': [],
                 'detected_license_expression_spdx': 'Apache-2.0'}]}))
            return 0, self.out / 'unused'
        with patch.object(self.g, 'tool', return_value=True), patch.object(self.g, 'run', side_effect=fake_run), patch.object(self.g, 'review'):
            licenses(self.g)
        self.assertIn('scancode-vcs-0', calls)
        self.assertFalse(any(r['rule']=='license-scan-coverage' for r in self.g.findings))

    def test_nested_failure_keeps_correct_category(self):
        self.g.category = 'build'
        with self.g.category_scope('static'):
            raise ValueError('synthetic error')
        self.assertEqual(self.g.category, 'build')
        self.assertEqual(self.g.findings[-1]['category'], 'static')


if __name__ == '__main__':
    unittest.main()
