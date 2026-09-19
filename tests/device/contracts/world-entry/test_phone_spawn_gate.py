# SPDX-License-Identifier: Apache-2.0
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class PhoneSpawnGateTests(unittest.TestCase):
    def test_release_timeout_and_destination_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = pathlib.Path(directory) / 'phone-spawn-gate'
            subprocess.run([
                'c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I', str(ROOT), str(pathlib.Path(__file__).with_name('phone-spawn-gate-test.cpp')),
                '-o', str(binary),
            ], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
