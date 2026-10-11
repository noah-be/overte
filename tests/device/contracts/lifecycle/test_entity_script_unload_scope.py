"""Execute all production unload entry points after the outer VM scope ends.

Real Qt dispatch and containers; the value-copy seam enforces the documented
ScriptEngine scope requirement. This is not a native V8 or device test.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

class EntityUnloadScope(unittest.TestCase):
    def test_production_unload_entry_points(self):
        relative = 'libraries/script-engine/src/ScriptManager.cpp'
        baseline = os.environ.get('OVERTE_UNLOAD_SCOPE_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative], text=True)
                  if baseline else (ROOT / relative).read_text())
        methods = '\n'.join(block(source, signature) for signature in (
            'void ScriptManager::unloadEntityScript(',
            'void ScriptManager::unloadAllEntityScriptsForEntity(',
            'void ScriptManager::unloadAllEntityScripts('))
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-entity-unload-') as directory:
            scratch = Path(directory)
            (scratch / 'unload.inc').write_text(methods)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(scratch),
                str(Path(__file__).with_name('entity-script-unload-scope-test.cpp')),
                '-o', str(binary), *flags], check=True, timeout=40)
            for entry in ('single', 'entity', 'all'):
                for delivery in ('direct', 'queued', 'nested'):
                    with self.subTest(entry=entry, delivery=delivery):
                        result = subprocess.run([str(binary), entry, delivery], capture_output=True, text=True, timeout=5)
                        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__':
    unittest.main()
