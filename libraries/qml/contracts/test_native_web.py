# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]

class NativeWebTests(unittest.TestCase):
    def test_actual_qt_policy_and_original_qml_with_native_boundary_only_substituted(self):
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs',
            'Qt6Core','Qt6Gui','Qt6Qml','Qt6Quick'],text=True))
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary)/'native-web'
            subprocess.run(['c++','-std=c++17','-fPIC','-Wall','-Wextra','-Werror','-pthread',
                '-I',str(ROOT),str(ROOT/'interface/src/NativeWebPolicy.cpp'),
                str(Path(__file__).with_name('test_native_web.cpp')),'-o',str(binary),*flags],
                check=True,timeout=60)
            subprocess.run([str(binary),str(ROOT/'interface/resources/qml/controls/+ios/FlickableWebViewCore.qml')],
                check=True,timeout=20,env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'})

    def test_application_binding_and_no_automatic_web_or_fake_success(self):
        source = (ROOT/'interface/src/Application.cpp').read_text()
        self.assertIn('return overte::web::openNativeWeb(url);',source)
        self.assertIn('overte::web::closeNativeWeb(ticket);',source)
        qml = (ROOT/'interface/resources/qml/controls/+ios/FlickableWebViewCore.qml').read_text()
        self.assertNotIn('import QtWebView',qml)
        self.assertNotIn('WebView {',qml)
        self.assertNotIn('loadingChangedCallback(',qml.split('signal loadingChangedCallback(var loadRequest)',1)[1])

if __name__ == '__main__': unittest.main()
