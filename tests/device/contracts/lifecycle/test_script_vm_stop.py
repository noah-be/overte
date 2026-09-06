#!/usr/bin/env python3
"""Real V8 execution and original stop/abort bodies; native callbacks are a seam."""
import os
import resource
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class ScriptVMStop(unittest.TestCase):
    def test_stop_interrupts_vm_before_queued_manager_delivery(self):
        prefix = Path(os.environ['V8_TEST_ROOT']).resolve(strict=True)
        manager = (ROOT / 'libraries/script-engine/src/ScriptManager.cpp').read_text()
        engine = (ROOT / 'libraries/script-engine/src/v8/ScriptEngineV8.cpp').read_text()
        stop = 'void ScriptManager::stop(' + manager.split('void ScriptManager::stop(', 1)[1].split('\n}', 1)[0] + '\n}\n'
        abort = 'void ScriptEngineV8::abortEvaluation(' + engine.split('void ScriptEngineV8::abortEvaluation(', 1)[1].split('\n}', 1)[0] + '\n}\n'
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-vm-stop-') as temporary:
            scratch = Path(temporary)
            (scratch / 'methods.inc').write_text(abort + stop)
            binary = scratch / 'test'
            library = prefix / 'usr/lib64'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(ROOT),
                '-I', str(scratch), '-isystem', str(prefix / 'usr/include/node'),
                str(Path(__file__).with_name('script-vm-stop-test.cpp')), '-L', str(library),
                '-Wl,-rpath,' + str(library), '-lnode', '-o', str(binary), *flags],
                check=True, timeout=40)
            for mode in ('normal', 'stop', 'duplicate'):
                with self.subTest(mode=mode):
                    result = subprocess.run(['unshare', '--user', '--map-root-user', '--net',
                        str(binary), mode], text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
