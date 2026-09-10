# SPDX-License-Identifier: Apache-2.0
"""Execute production account binding across terminal events and manager replacement."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

class AccountLoginBindingTest(unittest.TestCase):
    def test_terminal_events_and_stale_manager(self):
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        moc = Path(subprocess.check_output(
            ['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        source = Path(__file__).with_name('account-login-binding-test.cpp')
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            subprocess.run([str(moc), str(source), '-o', str(directory / 'account-login-binding.moc')],
                           check=True, timeout=15)
            binary = directory / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(directory),
                            str(source), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)

if __name__ == '__main__':
    unittest.main()
