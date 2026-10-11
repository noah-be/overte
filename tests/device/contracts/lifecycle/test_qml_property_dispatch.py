"""Real QML URL/int storage, queued writes, ordered reads and target teardown."""
import resource
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class QmlPropertyDispatch(unittest.TestCase):
    def test_actual_gate_and_original_direct_write_negative(self):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        production = ROOT / 'libraries/script-engine/src/v8/QmlPropertyThreadGate.h'
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Qml'], text=True))
        driver = Path(__file__).with_name('qml-property-dispatch-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-qml-property-') as temporary:
            scratch = Path(temporary)
            for original in (False, True):
                with self.subTest(original=original):
                    source = production.read_text()
                    if original:
                        marker = 'inline void writeQmlProperty('
                        source = source[:source.index(marker)] + '''
inline void writeQmlProperty(QObject* object, const QMetaProperty& property, const QVariant& value) {
    property.write(object, value);
}
}
#endif
'''
                    (scratch / production.name).write_text(source)
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
