#!/usr/bin/env python3
"""Complete production inverse conversion; actual Qt registry and host V8."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest
from v8_abort_fixture import write_abort_fixture
ROOT = pathlib.Path(__file__).resolve().parents[4]

class InverseConversion(unittest.TestCase):
    def test_production_inverse_conversion(self):
        prefix = pathlib.Path(os.environ['V8_TEST_ROOT']).resolve(strict=True)
        path = 'libraries/script-engine/src/v8/ScriptEngineV8_cast.cpp'
        baseline = os.environ.get('OVERTE_INVERSE_BASELINE')
        source = (subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT, text=True)
                  if baseline else (ROOT / path).read_text())
        method = 'V8ScriptValue ScriptEngineV8::castVariantToValue(' + source.split(
            'V8ScriptValue ScriptEngineV8::castVariantToValue(', 1)[1].split('\n}', 1)[0] + '\n}\n'
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='sh005-inverse-') as directory:
            directory = pathlib.Path(directory)
            (directory / 'inverse.inc').write_text(method)
            write_abort_fixture(ROOT, directory)
            library = prefix / 'usr/lib64'
            binary = directory / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(directory),
                '-isystem', str(prefix / 'usr/include/node'),
                str(pathlib.Path(__file__).with_name('v8-inverse-conversion-test.cpp')),
                '-L', str(library), '-Wl,-rpath,' + str(library), '-lnode', '-o', str(binary), *flags],
                check=True, timeout=40)
            for mode in ('ordinary', 'custom', 'prototype', 'stopped-custom', 'stopped-prototype', 'reentrant-stop'):
                with self.subTest(mode=mode):
                    result = subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary), mode],
                        text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
if __name__ == '__main__':
    unittest.main()
