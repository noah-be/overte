"""Execute the actual destructor with Qt logging and explicit resource seams."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class ScriptDestructorDiagnostics(unittest.TestCase):
    def test_private_filename_and_cleanup_order(self):
        source = (ROOT / 'libraries/script-engine/src/ScriptManager.cpp').read_text()
        start = source.index('ScriptManager::~ScriptManager() {')
        method = source[start:source.index('\n}', start) + 2]
        driver = r'''
#include <QtCore/QCoreApplication>
#include <QtCore/QDebug>
#include <QtCore/QLoggingCategory>
#include <QtCore/QStringList>
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>
#include <cstdio>
QStringList output;
int sequence = 0;
bool guarded = false;
struct Guard {
    Guard() { assert(!guarded); guarded = true; }
    ~Guard() { assert(sequence == 9); guarded = false; }
};
struct Engine { Guard getScopeGuard() { return Guard(); } };
struct Resource {
    int order;
    void reset() { assert(guarded); assert(++sequence == order); }
};
struct ScriptValue {
    ScriptValue& operator=(const ScriptValue&) {
        assert(guarded && ++sequence == 8); return *this;
    }
};
struct Deleted {
    Deleted& operator=(bool value) {
        assert(value && guarded && ++sequence == 9); return *this;
    }
};
class ScriptManager {
public:
    enum Type { OTHER, ENTITY_CLIENT };
    Type _type;
    QString _fileNameString = "https://private-world/script.js?token=canary";
    Engine backend;
    Engine* engine() { return &backend; }
    Resource _scriptingInterface{1}, _quatLibrary{2}, _vec3Library{3},
        _mat4Library{4}, _uuidLibrary{5}, _consoleScriptingInterface{6},
        _assetScriptingInterface{7};
    ScriptValue _returnValue;
    Deleted _isDeleted;
    ~ScriptManager();
};
'''
        checks = r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("*.debug=true");
    qInstallMessageHandler([](QtMsgType type, const QMessageLogContext&, const QString& msg) {
        if (type != QtDebugMsg) { fprintf(stderr, "%s\n", qPrintable(msg)); return; }
        assert(guarded && sequence == 0);
        output.append(msg);
    });
    for (auto type : {ScriptManager::OTHER, ScriptManager::ENTITY_CLIENT}) {
        sequence = 0;
        { ScriptManager manager; manager._type = type; }
        assert(!guarded && sequence == 9);
        assert(!output.last().contains("private-world"));
        assert(!output.last().contains("canary"));
    }
    assert(output.size() == 2);
}
'''
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-script-destructor-') as temporary:
            unit = Path(temporary) / 'test.cpp'
            unit.write_text(driver + method + checks)
            binary = Path(temporary) / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT),
                            str(unit), '-o', str(binary), *flags], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=8)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn('canary', result.stdout)
            self.assertNotIn('private-world', result.stdout)


if __name__ == '__main__':
    unittest.main()
