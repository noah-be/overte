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
import re
import copy

sys.dont_write_bytecode = True
from core import Gate, digest
from evidence import regular_file, write_receipt, validate_receipt, FIXED_FILES, MODULE
from runtime_checks import archive_members, analyze_telemetry, e2e, inspect_payload
from source_checks import materialize, secrets, dependencies, licenses, hygiene, android_resource, android_manifest, fdroid
from test_store import verify_inventory, write_inventory, stage_runtimes, store_paths, RUNTIMES
from history_review import load_reviews, reviewed_exception


class GateContracts(unittest.TestCase):
    def history_fixture(self):
        row = dict(Commit=self.g.commit, File='input.txt', RuleID='fixture', StartLine=1, EndLine=1)
        entry = dict(commit=self.g.commit, path='input.txt', rule='gitleaks-fixture',
                     blob_sha256=digest(self.root / 'input.txt'), locations=[[1, 1]],
                     owner='Fixture review', reason='Synthetic ordinary source', expires='2099-01-01')
        self.g.history_exceptions = [entry]
        return row, entry

    def test_history_exception_requires_every_identity_field_and_current_review(self):
        row, entry = self.history_fixture()
        self.assertEqual(reviewed_exception(self.g, row, 'input.txt'), entry)
        for key, value in [('Commit', 'b' * 40), ('RuleID', 'other'), ('StartLine', 2), ('EndLine', 2), ('StartLine', True)]:
            with self.subTest(field=key):
                self.assertIsNone(reviewed_exception(self.g, dict(row, **{key: value}), 'input.txt'))
        self.assertIsNone(reviewed_exception(self.g, row, 'other.txt'))
        for key, value in [('blob_sha256', 'f' * 64), ('expires', '2000-01-01')]:
            self.g.history_exceptions = [dict(entry, **{key: value})]
            self.assertIsNone(reviewed_exception(self.g, row, 'input.txt'))

    def test_history_exception_does_not_waive_source_scan(self):
        row, entry = self.history_fixture()
        def fake_run(label, argv, **kwargs):
            Path(argv[argv.index('--report-path') + 1]).write_text(json.dumps([row]))
            return 1, self.out / 'unused'
        with patch.object(self.g, 'tool', return_value=True), patch.object(self.g, 'run', side_effect=fake_run):
            secrets(self.g)
        findings = [r for r in self.g.findings if r['rule']=='gitleaks-fixture']
        self.assertEqual([r['status'] for r in findings], ['FAIL', 'WARNING'])
        self.assertIsNone(findings[0]['exception'])
        self.assertEqual(findings[1]['exception'], entry)

    def test_history_review_schema_rejects_broad_and_duplicate_exceptions(self):
        _, entry = self.history_fixture()
        path = self.out / 'reviews.json'
        for key, value in [('commit', '*'), ('path', '../escape'), ('locations', []),
                           ('locations', [[True, 1]]), ('locations', [[2, 1]]), ('owner', '')]:
            path.write_text(json.dumps(dict(schema=1, entries=[dict(entry, **{key: value})])))
            with self.subTest(field=key), self.assertRaises(ValueError):
                load_reviews(path)
        path.write_text(json.dumps(dict(schema=1, entries=[entry, copy.deepcopy(entry)])))
        with self.assertRaises(ValueError):
            load_reviews(path)

    def test_unavailable_historical_object_cannot_be_waived(self):
        row, entry = self.history_fixture()
        row['Commit'] = entry['commit'] = 'f' * 40
        self.assertIsNone(reviewed_exception(self.g, row, 'input.txt'))

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

    def test_reviewed_exceptions_require_unchanged_repository_files(self):
        root = Path(__file__).resolve().parents[3]
        for entry in self.g.exceptions:
            with self.subTest(path=entry['path'], rule=entry['rule']):
                self.assertEqual(digest(root / entry['path']), entry['sha256'],
                                 'Changed exception input requires renewed review, not automatic rebinding')

    def test_source_exception_cannot_waive_history_or_changed_input(self):
        self.g.exceptions = [dict(rule='fixture', path='input.txt', sha256=self.g.source_hashes['input.txt'],
                                 reason='Reviewed fixture', owner='Test', expires='2099-01-01')]
        self.g.finding('fixture', 'FAIL', 'input.txt', 'candidate', 'review', history_commit='a' * 40)
        self.assertEqual(self.g.findings[-1]['status'], 'FAIL')
        self.assertIsNone(self.g.findings[-1]['file_sha256'])
        self.assertEqual(self.g.findings[-1]['history_commit'], 'a' * 40)
        self.g.source_hashes['input.txt'] = 'b' * 64
        self.g.finding('fixture', 'FAIL', 'input.txt', 'candidate', 'review')
        self.assertEqual(self.g.findings[-1]['status'], 'FAIL')

    def test_history_scanner_retains_commit_and_rejects_missing_identity(self):
        commit = 'a' * 40
        def fake_run(label, argv, **kwargs):
            rows = [] if label.endswith('-dir') else [dict(File='input.txt', RuleID='fixture', StartLine=3, Commit=commit)]
            Path(argv[argv.index('--report-path') + 1]).write_text(json.dumps(rows))
            return int(bool(rows)), self.out / 'unused'
        with patch.object(self.g, 'tool', return_value=True), patch.object(self.g, 'run', side_effect=fake_run):
            secrets(self.g)
            self.assertEqual(self.g.findings[-1]['history_commit'], commit)
            self.assertIsNone(self.g.findings[-1]['file_sha256'])
            commit = None
            with self.assertRaisesRegex(ValueError, 'commit identity'):
                secrets(self.g)

    def test_evidence_escape_and_symlink_rejected(self):
        (self.out / 'link').symlink_to(self.root / 'input.txt')
        for name in ('../repo/input.txt', 'link', '/etc/passwd'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                regular_file(self.out, name)

    def test_phone_ignore_rules_cover_outputs_without_hiding_source(self):
        root = Path(__file__).resolve().parents[3]
        (self.root / '.gitignore').write_bytes((root / '.gitignore').read_bytes())
        phone = self.root / 'android/phone'
        phone.mkdir(parents=True)
        (phone / '.gitignore').write_bytes((root / 'android/phone/.gitignore').read_bytes())
        hygiene(self.g)
        self.assertFalse(any(r['rule'].startswith('ignore-') for r in self.g.findings))
        # A later negation must be detected, even though '*.log' is still present.
        with (phone / '.gitignore').open('a') as stream:
            stream.write('!diagnostic.log\n')
        hygiene(self.g)
        self.assertTrue(any(r['path']=='android/phone/diagnostic.log' for r in self.g.findings))
        for name in ('android/phone/quality-gate/test_gate.py', 'android/phone/config.example.json',
                     'android/vr/pico/diagnostic.log', 'ios/diagnostic.log'):
            self.assertEqual(subprocess.run(['git', 'check-ignore', '--no-index', name],
                             cwd=self.root, capture_output=True).returncode, 1, name)

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

    def test_license_inventory_includes_texture_font_and_avatar_formats(self):
        names = ['sky.ktx', 'texture.dds', 'animation.gif', 'font.woff',
                 'font.woff2', 'font.eot', 'avatar.fst', 'sound.raw', 'logo.svg',
                 'FiraSans.license']
        self.g.files = names
        for name in names:
            (self.root / name).write_text('fixture resource')
            (self.out / 'source-scope' / name).write_text('fixture resource')
        with patch.object(self.g, 'tool', return_value=False), patch.object(self.g, 'review'):
            licenses(self.g)
        rows = json.loads((self.out / 'license-inventory.json').read_text())
        self.assertEqual({r['path'] for r in rows}, set(names))
        self.assertTrue(all(r['license']=='REQUIRES_RECONCILIATION' for r in rows if r['kind']=='media'))
        branding = json.loads((self.out / 'branding.json').read_text())
        self.assertIn('logo.svg', [r['path'] for r in branding])

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

    def test_android_resource_policies_use_xml_semantics(self):
        android_resource(self.g, """<network-security-config>
            <base-config cleartextTrafficPermitted = 'tr&#117;e'>
              <trust-anchors><certificates src = 'user'/></trust-anchors>
            </base-config></network-security-config>""", 'network.xml')
        self.assertEqual({r['rule'] for r in self.g.findings}, {'cleartext-config', 'user-certificate-trust'})
        self.g.findings.clear()
        for attribute in ('', "path=''", "path='.'", "path='/'"):
            android_resource(self.g, f'<paths><external-path name="shared" {attribute}/></paths>', 'paths.xml')
        self.assertEqual(len(self.g.findings), 4)
        self.g.findings.clear()
        android_resource(self.g, """<paths><!-- <root-path path='/'/> -->
            <files-path name='exports' path='exports/'/></paths>""", 'paths.xml')
        self.assertFalse(self.g.findings)

    def test_release_manifest_rejects_dangerous_mutations(self):
        root = Path(__file__).resolve().parents[3]
        source = (root / 'android/phone/apps/phoneInterface/src/main/AndroidManifest.xml').read_text()
        android_manifest(self.g, source, 'manifest.xml', final=True)
        self.assertFalse(any(r['status']=='FAIL' for r in self.g.findings))
        for before, after, rule in [
            ('android:allowBackup="false"', 'android:allowBackup="true"', 'manifest-allowBackup'),
            ('android:hasCode="true"', 'android:debuggable="true"', 'manifest-debuggable'),
            ('android:exported="false"', 'android:exported="true"', 'exported-component'),
            ('android.permission.VIBRATE', 'android.permission.READ_CONTACTS', 'permission-unreviewed')]:
            self.g.findings.clear()
            android_manifest(self.g, source.replace(before, after), 'manifest.xml', final=True)
            self.assertTrue(any(r['rule']==rule and r['status']=='FAIL' for r in self.g.findings), rule)

    def test_soak_requires_continuous_valid_measurements(self):
        module = self.out / 'modules/idle-soak'
        module.mkdir(parents=True)
        valid = [dict(elapsedSeconds=t, memoryPssKb=100000, memoryRssKb=120000,
                      batteryLevel=80, batteryTemperatureDeciC=300, thermalStatus=0)
                 for t in range(0, 7200, 30)]
        def check(samples):
            (module / 'telemetry.jsonl').write_text('\n'.join(json.dumps(s) for s in samples))
            (module / 'metrics.json').write_text(json.dumps(dict(durationSeconds=7200, samples=len(samples))))
            return analyze_telemetry(self.g, self.out)
        self.assertEqual(check(valid), 7200)
        for samples in ([valid[0], valid[120], valid[-1]], valid[3:], valid[:-3],
                        [valid[0], *valid], [dict(valid[0], elapsedSeconds=-1), *valid[1:]]):
            with self.subTest(case='coverage'):
                self.assertEqual(check(samples), 0)
        for field, value in [('memoryPssKb', None), ('memoryRssKb', -1),
                             ('batteryLevel', True), ('batteryTemperatureDeciC', float('nan')),
                             ('thermalStatus', 6)]:
            with self.subTest(field=field):
                self.assertEqual(check([dict(valid[0], **{field: value}), *valid[1:]]), 0)

    def test_device_groups_never_run_without_explicit_authorization(self):
        for group in ('functional', 'robustness', 'long'):
            with self.subTest(group=group), patch.object(self.g, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'explicitly enabled'):
                    e2e(self.g, group)
                run.assert_not_called()

    def test_apk_and_aab_apply_the_same_payload_checks(self):
        self.g.category = 'artifact'
        dest = self.out / 'payload'
        dest.mkdir()
        name = 'debug/fixture.log'
        (dest / 'debug').mkdir()
        (dest / name).write_bytes(b'com/google/android/gms')
        expected = {'unexpected-payload', 'packaged-sdk'}
        for prefix in ('', 'AAB/'):
            self.g.findings.clear()
            inspect_payload(self.g, dest, [dict(path=name, size=22)], prefix)
            self.assertEqual({r['rule'] for r in self.g.findings}, expected)
            self.assertTrue(all(r['status']=='FAIL' and r['path']==prefix + name for r in self.g.findings))

    def test_gradle_store_rejects_unlisted_changed_and_missing_inputs(self):
        directory = self.out / 'caches/modules-2/files-2.1/fixture'
        directory.mkdir(parents=True)
        artifact = directory / 'fixture.jar'
        artifact.write_bytes(b'original')
        write_inventory(self.out)
        verify_inventory(self.out)
        artifact.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'missing, changed'):
            verify_inventory(self.out)
        artifact.write_bytes(b'original')
        (directory / 'undeclared.jar').write_bytes(b'added')
        with self.assertRaisesRegex(ValueError, 'outside the inventory'):
            verify_inventory(self.out)
        (directory / 'undeclared.jar').unlink()
        artifact.unlink()
        with self.assertRaises(ValueError):
            verify_inventory(self.out)

    def test_acquisition_cannot_overwrite_or_recursively_copy_its_base(self):
        for output in (self.out, self.out / 'nested', self.root / 'cache', Path('relative')):
            with self.subTest(output=output), self.assertRaises(ValueError):
                store_paths(self.out, output, self.root)
        alias = self.base / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            store_paths(self.out, alias / 'cache', self.root)
        self.assertEqual(store_paths(self.out, self.base / 'new-store', self.root),
                         (self.out, self.base / 'new-store'))

    def test_robolectric_requires_both_pinned_offline_sdks(self):
        destination = self.out / 'runtimes'
        for index, version in enumerate(RUNTIMES):
            with self.assertRaises(ValueError):
                stage_runtimes(self.out, destination)
            p = self.out / 'caches/modules-2/files-2.1/org.robolectric/android-all-instrumented' / version / 'fixture'
            p.mkdir(parents=True)
            (p / f'android-all-instrumented-{version}.jar').write_bytes(b'fixture')
        stage_runtimes(self.out, destination)
        self.assertEqual(len(list(destination.iterdir())), 2)

    def test_acquisition_roots_track_phone_unit_test_dependencies(self):
        root = Path(__file__).resolve().parents[3]
        phone = (root / 'android/phone/apps/phoneInterface/build.gradle').read_text()
        acquisition = Path(__file__).with_name('gradle-tests').joinpath('build.gradle').read_text()
        self.assertEqual(set(re.findall(r"testImplementation '([^']+)'", phone)),
                         set(re.findall(r"gateUnitTests '([^']+)'", acquisition)))

    def test_wrapper_drift_blocks_without_claiming_fdroid_approval(self):
        rel = 'android/common/gradle/wrapper/gradle-wrapper.jar'
        wrapper = self.root / rel
        wrapper.parent.mkdir(parents=True)
        wrapper.write_bytes(b'PK\x03\x04fixture')
        lock = self.root / 'android/phone/fdroid/manifests/toolchain-provisioning.lock.json'
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps(dict(gradle_bindings={rel: digest(wrapper)})))
        self.g.files = [rel]
        with patch.object(self.g, 'review'):
            fdroid(self.g)
            self.assertFalse(any(r['rule']=='wrapper-integrity' for r in self.g.findings))
            self.assertTrue(any(r['rule']=='binary-origin' for r in self.g.findings))
            wrapper.write_bytes(b'changed')
            fdroid(self.g)
            self.assertTrue(any(r['rule']=='wrapper-integrity' and r['status']=='FAIL' for r in self.g.findings))


if __name__ == '__main__':
    unittest.main()
