#!/usr/bin/env python3
"""Actual retained radial callers and CPU renderer, Qt software pixel checks."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]

class RadialGradient(unittest.TestCase):
    def test_retained_callers(self):
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Quick', 'Qt6Test'], text=True))
        with tempfile.TemporaryDirectory(prefix='cpu-radial-') as temp:
            temp = Path(temp)
            binary = temp / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC',
                str(Path(__file__).with_name('cpu-radial-gradient-test.cpp')),
                '-o', str(binary), *flags], check=True, timeout=30)
            component = (ROOT / 'interface/resources/qml/controls/CpuRadialGradient.qml').read_text()
            if os.environ.get('OVERTE_RADIAL_CIRCULAR') == '1':
                component = component.replace('ctx.scale(width, height)', 'ctx.scale(width, width)')
            (temp / 'controls').mkdir()
            (temp / 'controls/CpuRadialGradient.qml').write_text(component)
            (temp / 'controls/qmldir').write_text((ROOT / 'interface/resources/qml/controls/qmldir').read_text())
            for caller in ['windows/Frame.qml', '+android_interface/Web3DSurfaceAndroid.qml']:
                source = (ROOT / 'interface/resources/qml' / caller).read_text()
                start = source.index('    CpuControls.CpuRadialGradient {')
                end = source.index('{', start) + 1
                depth = 1
                while depth:
                    depth += (source[end] == '{') - (source[end] == '}')
                    end += 1
                item = source[start:end]
                item = item.replace('CpuControls.CpuRadialGradient {', 'CpuControls.CpuRadialGradient { objectName: "radial"', 1)
                if os.environ.get('OVERTE_RADIAL_STOP_MUTATION') == '1':
                    item = item.replace('position: 0.333', 'position: 0.05')
                qml = temp / 'caller.qml'
                qml.write_text('''import QtQuick 2.5
import "controls" as CpuControls
Item { id: window; width: 400; height: 200; focus: true
    property bool gradientsSupported: true
    property QtObject content: QtObject { property bool visible: true }
''' + item + '\n}')
                with self.subTest(caller=caller):
                    subprocess.run(['unshare', '--user', '--map-root-user', '--net',
                        str(binary), str(qml), 'frame' if 'Frame' in caller else 'web'],
                        env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software'),
                        check=True, timeout=15)

if __name__ == '__main__':
    unittest.main()
