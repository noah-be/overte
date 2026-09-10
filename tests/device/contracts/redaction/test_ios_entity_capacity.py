"""All actual Shared observation recorders, bounded storage, real Qt containers."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class EntityCapacity(unittest.TestCase):
    def test_complete_production_header_and_every_insertion_path(self):
        baseline = os.environ.get('OVERTE_ENTITY_CAPACITY_BASELINE')
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-entity-capacity-') as temporary:
            scratch = Path(temporary)
            include = ROOT
            if baseline:
                include = scratch
                relative = 'libraries/shared/src/shared/IOSRuntimeLogging.h'
                target = scratch / relative
                target.parent.mkdir(parents=True)
                target.write_bytes(subprocess.check_output(['git', '-C', str(ROOT),
                                   'show', baseline + ':' + relative]))
                (scratch / 'security').symlink_to(ROOT / 'security', target_is_directory=True)
            for name in ('ios-entity-correlation-test.cpp', 'ios-entity-capacity-test.cpp'):
                with self.subTest(fixture=name):
                    binary = scratch / name.removesuffix('.cpp')
                    subprocess.run(['c++', '-std=c++17', '-fPIC', '-DOVERTE_IOS=1',
                                    '-DTEST_BASELINE=' + str(int(bool(baseline))), '-I', str(include),
                                    str(Path(__file__).with_name(name)),
                                    '-o', str(binary), *flags], check=True, timeout=30)
                    subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                                   check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
