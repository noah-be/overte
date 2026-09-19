"""Run production map-retirement and destruction callback with real host Qt.

V8 value management is outside this focused test; the native script-engine
regression also covers full engine destruction with script-owned QObjects.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class WrapperTeardown(unittest.TestCase):
    def test_owned_object_reentrant_destruction(self):
        relative = 'libraries/script-engine/src/v8/ScriptEngineV8.cpp'
        baseline = os.environ.get('OVERTE_WRAPPER_TEARDOWN_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative], text=True)
                  if baseline else (ROOT / relative).read_text())
        start = source.index('    _customPrototypes.clear();', source.index('ScriptEngineV8::~ScriptEngineV8()'))
        start += len('    _customPrototypes.clear();')
        finish = source.index('    // Events need to be processed one more time', start)
        retirement = source[start:finish]
        proxy = (ROOT / 'libraries/script-engine/src/v8/ScriptObjectV8Proxy.cpp').read_text()
        start = proxy.index('        object->connect(object, &QObject::destroyed, engine,')
        finish = proxy.index('\n        });', start) + len('\n        });')
        connection = proxy[start:finish]
        driver = r'''
#include <QCoreApplication>
#include <QMap>
#include <QMutex>
#include <QPointer>
#include <QSharedPointer>
#include <QObject>
#include <cstdio>
struct Signal { void disconnectAllScriptSignalProxies() {} };
struct ScriptObjectV8Proxy {
    QObject* object;
    QList<Signal*> _signalInstances;
    ~ScriptObjectV8Proxy() { delete object; }
};
struct ScriptEngineV8 : QObject {
    using ObjectWrapperMap = QMap<QObject*, QWeakPointer<ScriptObjectV8Proxy>>;
    QMutex _qobjectWrapperMapProtect;
    ObjectWrapperMap _qobjectWrapperMap;
    QMap<QObject*, QSharedPointer<ScriptObjectV8Proxy>> _qobjectWrapperMapV8;
    void retire() {
RETIREMENT
    }
};
int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    ScriptEngineV8 owner;
    auto* engine = &owner;
    int deleted = 0;
    for (int cycle = 0; cycle < 5; ++cycle) {
        for (int i = 0; i < 5; ++i) {
            auto* object = new QObject;
            auto proxy = QSharedPointer<ScriptObjectV8Proxy>::create();
            proxy->object = object;
            engine->_qobjectWrapperMap.insert(object, proxy);
            engine->_qobjectWrapperMapV8.insert(object, proxy);
            QObject::connect(object, &QObject::destroyed, &application, [&] { ++deleted; });
            QPointer<ScriptEngineV8> enginePtr = engine;
CONNECTION
        }
        // Normal external deletion must remove the corresponding map entries.
        auto* external = new QObject;
        auto proxy = QSharedPointer<ScriptObjectV8Proxy>::create();
        proxy->object = nullptr;
        auto* object = external;
        engine->_qobjectWrapperMap.insert(object, proxy);
        engine->_qobjectWrapperMapV8.insert(object, proxy);
        QPointer<ScriptEngineV8> enginePtr = engine;
CONNECTION
        delete external;
        if (engine->_qobjectWrapperMap.contains(object) || engine->_qobjectWrapperMapV8.contains(object)) return 2;
        engine->retire();
        if (!engine->_qobjectWrapperMap.empty() || !engine->_qobjectWrapperMapV8.empty()) return 3;
        if (deleted != (cycle + 1) * 5) return 4;
    }
    std::puts("25 owned objects retired; external deletion and repeated cleanup passed");
}
'''.replace('RETIREMENT', retirement).replace('CONNECTION', connection)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-wrapper-teardown-') as temporary:
            scratch = Path(temporary)
            source_path = scratch / 'test.cpp'
            source_path.write_text(driver)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', str(source_path), '-o', str(binary), *flags],
                           check=True, timeout=40)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('25 owned objects retired', run.stdout)


if __name__ == '__main__':
    unittest.main()
