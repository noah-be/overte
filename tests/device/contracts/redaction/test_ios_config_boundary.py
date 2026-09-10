"""Actual complete Shared diagnostic-config loader and cache, real host Qt."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class IOSConfigBoundary(unittest.TestCase):
    def test_bounded_real_hot_reload(self):
        # Read-only baseline override supports a genuine before/after test.
        include_root = pathlib.Path(os.environ.get('OVERTE_CONFIG_BASELINE_ROOT', ROOT))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-config-boundary-') as temporary:
            binary = pathlib.Path(temporary) / 'config-test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(include_root),
                            str(pathlib.Path(__file__).with_name('ios-config-boundary-test.cpp')),
                            '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                           check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
