# SPDX-License-Identifier: Apache-2.0
"""Regression checks for F-Droid's wrapper removal and source-bound packaging."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location('submission_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder, staging = load('build'), load('stage')


class BuildContractTests(unittest.TestCase):
    def test_provisioning_runs_from_fdroid_home_before_source_preparation(self):
        # fdroidserver.build.build_local runs sudo from the builder home, not
        # the app checkout. Exercise that directory layout without root/APT.
        template = (HERE / 'metadata/org.overte.phone.yml.in').read_text()
        command = next(line.strip()[6:] for line in template.splitlines()
                       if line.strip().startswith('sudo: '))
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            script = home / 'build/org.overte.phone' / staging.BASE / 'provision.sh'
            script.parent.mkdir(parents=True)
            script.write_text('set -eu\n[ "$1" = --fdroid-buildserver ]\nprintf ready > provisioned\n')
            subprocess.run(shlex.split(command), cwd=home, check=True)
            self.assertEqual('ready', (home / 'provisioned').read_text())

    def test_rejects_ambiguous_commit_and_invalid_versions(self):
        for commit, code, name in [('main', 1, '0.1.0'), ('a' * 40, 0, '0.1.0'),
                                    ('a' * 40, 2147483648, '0.1.0'),
                                    ('a' * 40, 1, '0.1.0; echo injected')]:
            with self.subTest(commit=commit, code=code, name=name), self.assertRaises(ValueError):
                builder.validate_coordinates(commit, code, name)
        builder.validate_coordinates('a' * 40, 1, '0.1.0')

    def test_gradle_distribution_matches_existing_lock(self):
        lock = json.loads((ROOT / 'android/phone/fdroid/manifests/toolchain-provisioning.lock.json').read_text())
        self.assertEqual(builder.GRADLE_SHA256, lock['gradle_bindings']['distribution_sha256'])
        self.assertIn('gradle-' + lock['gradle_bindings']['gradle'] + '-bin.zip', builder.GRADLE_URL)

    def test_corrupted_distribution_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / 'bad.zip').write_bytes(b'not a Gradle archive')
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                builder.extract_gradle(p / 'bad.zip', p / 'out')
            self.assertFalse((p / 'out').exists())

    def test_archive_path_traversal_rejected_even_after_hash_check(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            with zipfile.ZipFile(p / 'bad.zip', 'w') as z:
                z.writestr('gradle-8.13/../../escape', b'bad')
            with patch.object(builder, 'GRADLE_SHA256', builder.digest(p / 'bad.zip')):
                with self.assertRaisesRegex(ValueError, 'unsafe'):
                    builder.extract_gradle(p / 'bad.zip', p / 'out')
            self.assertFalse((p / 'escape').exists())

    def test_developer_environment_does_not_select_binary_dependencies(self):
        args = argparse.Namespace(work_dir=Path('/work/new'), source_store=Path('/sources'),
                                  commit='a' * 40, sdk=Path('/sdk'), java_home=Path('/jdk'))
        dirty = {'PHONE_ALLOW_LEGACY_4K_DEPS': '1', 'OVERTE_FDROID_CONAN_DIR': '/old/binaries',
                 'CONAN_HOME': '/personal', 'CMAKE_PREFIX_PATH': '/old',
                 'JAVA_TOOL_OPTIONS': '-javaagent:bad.jar', 'ORG_GRADLE_PROJECT_VERSION_CODE': '999'}
        with patch.dict(os.environ, dirty):
            env = builder.environment(args)
        for key in dirty:
            self.assertNotIn(key, env)
        self.assertEqual('/work/new/gradle-home', env['GRADLE_USER_HOME'])

    def test_release_command_survives_fdroid_wrapper_removal(self):
        args = argparse.Namespace(sdk=Path('/sdk'), version_code=1, version_name='0.1.0')
        command = [str(x) for x in builder.release_command(args, Path('/new/gradle-8.13/bin/gradle'))]
        self.assertEqual('/new/gradle-8.13/bin/gradle', command[0])
        self.assertNotIn('gradlew', ' '.join(command))
        self.assertIn('--offline', command)
        self.assertIn('--no-build-cache', command)
        self.assertIn(':phoneInterface:assembleRelease', command)
        self.assertIn('-PVERSION_CODE=1', command)
        self.assertIn('-PRELEASE_NUMBER=0.1.0', command)

    def test_existing_work_directory_rejected_without_running_build(self):
        with tempfile.TemporaryDirectory() as td:
            args = ['build.py', '--commit', 'a' * 40, '--version-code', '1', '--version-name', '0.1.0',
                    '--sdk', '/sdk', '--work-dir', td]
            with patch('sys.argv', args), patch.object(builder, 'preflight') as preflight:
                with self.assertRaisesRegex(ValueError, 'must be new'):
                    builder.main()
                preflight.assert_not_called()

    def test_store_text_stays_within_fdroid_limits(self):
        p = ROOT / staging.STORE
        self.assertLessEqual(len((p / 'title.txt').read_text().strip()), 50)
        self.assertLessEqual(len((p / 'short_description.txt').read_text().strip()), 80)
        self.assertLessEqual(len((p / 'full_description.txt').read_text().strip()), 4000)
        self.assertLessEqual(len((p / 'changelogs/1.txt').read_text().strip()), 500)


class SourceBoundStagingTests(unittest.TestCase):
    def test_staging_uses_committed_text_and_keeps_draft_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'repo'; root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            for relative, text in {
                staging.BASE + '/build.py': '# fixture entry point\n',
                staging.BASE + '/metadata/org.overte.phone.yml.in': 'commit: "@COMMIT@"\ndisable: draft\n',
                staging.STORE + '/title.txt': 'Committed title\n',
                staging.STORE + '/short_description.txt': 'Description\n',
                staging.STORE + '/full_description.txt': 'Full description\n',
            }.items():
                f = root / relative; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-qm', 'Create test fixture'], check=True)
            (root / staging.STORE / 'title.txt').write_text('Uncommitted title\n')
            output = Path(td) / 'draft'
            with patch.object(staging, 'ROOT', root):
                staging.stage(output, 'HEAD')
                with self.assertRaisesRegex(ValueError, 'new directory'):
                    staging.stage(output, 'HEAD')
            self.assertEqual('Committed title\n', (output / 'metadata/org.overte.phone/en-US/title.txt').read_text())
            text = (output / 'metadata/org.overte.phone.yml').read_text()
            self.assertNotIn('@COMMIT@', text)
            self.assertIn('disable: draft', text)


if __name__ == '__main__':
    unittest.main()
