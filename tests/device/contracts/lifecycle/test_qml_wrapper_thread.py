"""Real QML properties reject worker writes before the GUI queue is delivered."""
import os
from pathlib import Path
import resource
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class QmlWrapperThread(unittest.TestCase):
    def test_worker_writes_are_delivered_only_on_the_gui_thread(self):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        source = (ROOT / 'libraries/ui/src/ui/QmlWrapper.cpp').read_text()
        methods = '\n'.join(block(source, signature) for signature in (
            'void QmlWrapper::writeProperty(', 'void QmlWrapper::writeProperties('))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Qml'], text=True))
        moc = Path(subprocess.check_output(
            ['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = Path(__file__).with_name('qml-wrapper-thread-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-qml-thread-') as temporary:
            scratch = Path(temporary)
            subprocess.run([str(moc), str(driver), '-o', str(scratch / 'wrapper.moc')],
                           check=True, timeout=15)
            for original in (False, True):
                with self.subTest(original=original):
                    body = methods.replace('        return;\n', '') if original else methods
                    (scratch / 'wrapper-methods.inc').write_text(body)
                    binary = scratch / 'test'
                    subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(scratch),
                                    str(driver), '-o', str(binary), *flags], check=True, timeout=40)
                    run = subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                                         capture_output=True, text=True, timeout=8)
                    if original:
                        self.assertNotEqual(run.returncode, 0)
                    else:
                        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
