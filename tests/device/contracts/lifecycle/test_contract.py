# SPDX-License-Identifier: Apache-2.0
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]

class LifecycleTests(unittest.TestCase):
    def test_compiled_state_event_order_and_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = pathlib.Path(temporary) / 'lifecycle'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                            '-I', str(ROOT), str(pathlib.Path(__file__).with_name('test_lifecycle.cpp')),
                            '-o', str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_qt_lifecycle_caller_is_bound(self):
        source = (ROOT / 'interface/src/Application_Events.cpp').read_text()
        body = source.split('void Application::activeChanged(Qt::ApplicationState state) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('applicationGate().visible(state == Qt::ApplicationActive)', body)
        definition = (ROOT / 'interface/src/Application.cpp').read_text()
        self.assertIn('Gate& overte::lifecycle::applicationGate()', definition)

if __name__ == '__main__':
    unittest.main()
