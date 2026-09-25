"""Exercise the actual Phone focus transition with real Qt widgets."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class EditorTeardownTest(unittest.TestCase):
    def test_focus_transition_and_no_focus_stealing(self):
        source = (ROOT / 'interface/src/Application_Graphics.cpp').read_text()
        marker = 'connect(offscreenUi.data(), &OffscreenUi::focusTextChanged, _primaryWidget, [this](bool focusText) {'
        begin = source.index(marker) + len(marker)
        body = source[begin:source.index('\n    });', begin)]
        fixture = r'''
#include <QApplication>
#include <QWidget>
#include <QInputMethod>
#include <cassert>
struct Receiver {
    QWidget* _primaryWidget;
    void changed(bool focusText) {
BODY
    }
};
int main(int argc, char** argv) {
    QApplication app(argc, argv);
    QWidget window;
    QWidget viewport(&window), other(&window);
    viewport.setFocusPolicy(Qt::StrongFocus);
    other.setFocusPolicy(Qt::StrongFocus);
    window.show(); window.activateWindow(); viewport.setFocus(); app.processEvents();
    assert(viewport.hasFocus());
    Receiver receiver { &viewport };
    int transitions = 0;
    int nativeTransitions = 0;
    QObject::connect(&app, &QGuiApplication::focusObjectChanged, [&](QObject*) { ++nativeTransitions; });
    QObject::connect(&app, &QApplication::focusChanged, [&](QWidget*, QWidget*) { ++transitions; });
    receiver.changed(true);
    assert(viewport.testAttribute(Qt::WA_InputMethodEnabled));
    assert(transitions == 0);
    receiver.changed(false);
    assert(!viewport.testAttribute(Qt::WA_InputMethodEnabled));
    assert(viewport.hasFocus());
    assert(transitions >= 2);
    assert(nativeTransitions >= 2); // The platform receives the focus-object transition.
    other.setFocus(); app.processEvents();
    transitions = 0;
    receiver.changed(false);
    assert(other.hasFocus());
    assert(transitions == 0); // Never steal focus from another window/editor.
}
'''.replace('BODY', body)
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Widgets'], text=True))
        with tempfile.TemporaryDirectory(prefix='phone-editor-teardown-') as directory:
            p = Path(directory)
            (p / 'test.cpp').write_text(fixture)
            subprocess.run(['c++', '-std=c++17', '-fPIC', str(p / 'test.cpp'),
                            '-o', str(p / 'test'), *flags], check=True, timeout=30)
            subprocess.run([str(p / 'test')], check=True, timeout=10,
                           env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})


if __name__ == '__main__':
    unittest.main()
