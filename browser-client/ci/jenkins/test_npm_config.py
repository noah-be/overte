# SPDX-License-Identifier: Apache-2.0
"""Real npm configuration-loader regression; no install, network, or services."""
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ci_run', Path(__file__).with_name('run.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class NpmConfig(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime = Path(self.temporary.name)
        self.runtime.chmod(0o700)

    def npm(self, environment, name='userconfig'):
        npm = shutil.which('npm')
        self.assertIsNotNone(npm, 'Actual npm config-loader is required for this regression')
        return subprocess.run([npm, 'config', 'get', name], cwd=self.runtime,
                              env={**r.safe_environment(), **environment},
                              capture_output=True, text=True, timeout=15)

    def test_old_single_file_negative_control_fails_actual_npm_loader(self):
        file = self.runtime/'old-empty-npmrc'
        file.write_text('')
        result = self.npm({'NPM_CONFIG_USERCONFIG':str(file), 'NPM_CONFIG_GLOBALCONFIG':str(file)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('double-loading config', result.stderr)

    def test_two_distinct_private_files_load_actual_npm_with_same_gate_environment(self):
        prepared = r.empty_npm_environment(self.runtime, create=True)
        gate = r.empty_npm_environment(self.runtime)
        self.assertEqual(prepared, gate)
        self.assertNotEqual(os.stat(prepared['NPM_CONFIG_USERCONFIG']).st_ino,
                            os.stat(prepared['NPM_CONFIG_GLOBALCONFIG']).st_ino)
        for key, name in (('NPM_CONFIG_USERCONFIG','userconfig'),('NPM_CONFIG_GLOBALCONFIG','globalconfig')):
            file = Path(prepared[key])
            self.assertEqual(file.parent, self.runtime)
            self.assertEqual(file.read_bytes(), b'')
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            result = self.npm(gate, name)
            self.assertEqual(result.returncode, 0, 'Actual npm must resolve both distinct scopes')
            self.assertEqual(result.stdout.strip(), str(file))

    def test_creation_is_idempotent_and_clears_only_own_config(self):
        environment = r.empty_npm_environment(self.runtime, create=True)
        path = Path(environment['NPM_CONFIG_USERCONFIG'])
        before = path.stat().st_ino
        path.write_text('registry=https://authored.invalid\n')
        with self.assertRaisesRegex(RuntimeError, 'not-empty-private'):
            r.empty_npm_environment(self.runtime)
        self.assertEqual(r.empty_npm_environment(self.runtime, create=True), environment)
        self.assertEqual(path.stat().st_ino, before)
        self.assertEqual(path.read_bytes(), b'')

    def test_symlink_cannot_read_or_truncate_unrelated_config(self):
        outside = self.runtime/'unrelated'
        outside.write_text('unchanged-authored-config')
        (self.runtime/'empty-user-npmrc').symlink_to(outside)
        with self.assertRaises(OSError):
            r.empty_npm_environment(self.runtime, create=True)
        self.assertEqual(outside.read_text(), 'unchanged-authored-config')

    def test_hardlink_alias_cannot_modify_other_file(self):
        outside = self.runtime/'unrelated'
        outside.write_text('unchanged-authored-config')
        os.link(outside, self.runtime/'empty-user-npmrc')
        with self.assertRaisesRegex(RuntimeError, 'owned-private-regular'):
            r.empty_npm_environment(self.runtime, create=True)
        self.assertEqual(outside.read_text(), 'unchanged-authored-config')

    def test_actual_fifo_is_refused_without_waiting_for_a_writer(self):
        environment = r.empty_npm_environment(self.runtime, create=True)
        path = Path(environment['NPM_CONFIG_USERCONFIG'])
        path.unlink()
        os.mkfifo(path, 0o600)
        script = """
import importlib.util, pathlib, sys
spec=importlib.util.spec_from_file_location('actual_run',sys.argv[1])
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
try:r.empty_npm_environment(pathlib.Path(sys.argv[2]))
except RuntimeError as error:
 assert str(error)=='CI-npm-config-is-not-owned-private-regular-file'
 print('refused',flush=True)
else:raise AssertionError('FIFO admitted')
"""
        result = subprocess.run([sys.executable, '-c', script, str(Path(r.__file__)), str(self.runtime)],
                                capture_output=True, text=True, timeout=3, env=r.safe_environment())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'refused')

    def test_old_blocking_open_negative_control_cannot_reach_fifo_fstat(self):
        environment = r.empty_npm_environment(self.runtime, create=True)
        path = Path(environment['NPM_CONFIG_USERCONFIG'])
        path.unlink()
        os.mkfifo(path, 0o600)
        script = """
import importlib.util, pathlib, sys
spec=importlib.util.spec_from_file_location('actual_run',sys.argv[1])
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
original=r.os.open
r.os.open=lambda path,flags,*args,**kwargs: original(path, flags & ~r.os.O_NONBLOCK,*args,**kwargs)
print('ready',flush=True)
r.empty_npm_environment(pathlib.Path(sys.argv[2]))
"""
        process = subprocess.Popen([sys.executable, '-c', script, str(Path(r.__file__)), str(self.runtime)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=r.safe_environment())
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            with self.assertRaises(subprocess.TimeoutExpired):
                process.wait(timeout=.15)
        finally:
            process.kill()
            process.communicate(timeout=3)
        self.assertNotEqual(process.returncode, 0)

    def test_changed_mode_and_missing_config_fail_before_gate_commands(self):
        environment = r.empty_npm_environment(self.runtime, create=True)
        file = Path(environment['NPM_CONFIG_GLOBALCONFIG'])
        file.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'not-empty-private'):
            r.empty_npm_environment(self.runtime)
        file.unlink()
        with self.assertRaises(OSError):
            r.empty_npm_environment(self.runtime)


if __name__ == '__main__':
    unittest.main()
