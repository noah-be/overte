"""Entire actual render transaction method, original Shared state, real host Qt."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class SceneGeneration(unittest.TestCase):
    def test_original_queued_caller(self):
        include_root = pathlib.Path(os.environ.get('OVERTE_SCENE_BASELINE_ROOT', ROOT))
        source = (include_root / 'libraries/entities-renderer/src/RenderableEntityItem.cpp').read_text()
        start = source.index('void EntityRenderer::updateInScene(')
        end = source.index('\nvoid EntityRenderer::fade(', start)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-scene-generation-') as temporary:
            directory = pathlib.Path(temporary)
            (directory / 'scene-method.inc').write_text(source[start:end])
            for ios in (0, 1):
                with self.subTest(ios=ios):
                    binary = directory / ('scene-' + str(ios))
                    subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(include_root), '-I', str(directory),
                                    '-DTEST_BASELINE=' + str(int('OVERTE_SCENE_BASELINE_ROOT' in os.environ)),
                                    '-DTEST_IOS=' + str(ios), str(pathlib.Path(__file__).with_name('ios-scene-generation-test.cpp')),
                                    '-o', str(binary), *flags], check=True, timeout=30)
                    subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
