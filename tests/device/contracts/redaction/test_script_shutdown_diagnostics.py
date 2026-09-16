"""Original shutdown/info methods: public logs versus retained internal console."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class ScriptShutdownDiagnostics(unittest.TestCase):
    def test_shutdown_paths_do_not_emit_private_script_names(self):
        source = (ROOT / 'libraries/script-engine/src/ScriptManager.cpp').read_text()
        start = source.index('void ScriptManager::waitTillDoneRunning(')
        method = source[start:source.index('\n}', start) + 2]
        start = source.index('void ScriptManager::scriptInfoMessage(')
        method += '\n' + source[start:source.index('\n}', start) + 2]
        for name in ('scriptErrorMessage', 'scriptWarningMessage', 'scriptPrintedMessage'):
            start = source.index('void ScriptManager::' + name + '(')
            method += '\n' + source[start:source.index('\n}', start) + 2]
        driver = r'''
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QThread>
#include <QtCore/QStringList>
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>
Q_LOGGING_CATEGORY(scriptengine, "overte.test.script-shutdown")
QStringList output;
QStringList console;
struct EntityItemID { bool invalid = true; bool isInvalidID() const { return invalid; } };
class ScriptManager {
public:
    bool _isThreaded = false, _isDoneRunning = true;
    int stops = 0, filenameReads = 0;
    QThread* worker = QThread::currentThread();
    struct Engine { int getScopeGuard() { return 0; } void processEvents() {} } engine;
    Engine* _engine = &engine;
    QThread* thread() { return worker; }
    void stop() { ++stops; }
    QString getFilename() { ++filenameReads; return "private-world-secret.js?token=canary"; }
    EntityItemID currentEntityIdentifier;
    bool server = false;
    int entitySignals = 0;
    int errorSignals = 0, warningSignals = 0, printSignals = 0;
    bool isEntityServerScript() const { return server; }
    void infoMessage(const QString& message, const QString& filename) { console.append(message + filename); }
    void infoEntityMessage(const QString& message, const QString& filename, int line, EntityItemID entity, bool isServer) {
        ++entitySignals;
        assert(message == "entity-canary" && filename == "private-entity-file" && line == 9);
        assert(entity.invalid == currentEntityIdentifier.invalid && isServer == server);
    }
    void scriptInfoMessage(const QString& message, const QString&, int);
    void scriptErrorMessage(const QString&, const QString&, int);
    void scriptWarningMessage(const QString&, const QString&, int);
    void scriptPrintedMessage(const QString&, const QString&, int);
    void errorMessage(const QString& msg, const QString& file) { ++errorSignals; infoMessage(msg, file); }
    void warningMessage(const QString& msg, const QString& file) { ++warningSignals; infoMessage(msg, file); }
    void printedMessage(const QString& msg, const QString& file) { ++printSignals; infoMessage(msg, file); }
    void errorEntityMessage(const QString& msg, const QString& file, int line, EntityItemID id, bool server) {
        infoEntityMessage(msg, file, line, id, server);
    }
    void warningEntityMessage(const QString& msg, const QString& file, int line, EntityItemID id, bool server) {
        infoEntityMessage(msg, file, line, id, server);
    }
    void printedEntityMessage(const QString& msg, const QString& file, int line, EntityItemID id, bool server) {
        infoEntityMessage(msg, file, line, id, server);
    }
    void waitTillDoneRunning(bool shutdown);
};
'''
        checks = r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("overte.test.script-shutdown.debug=true");
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext&, const QString& msg) { output.append(msg); });
    ScriptManager sameThread;
    sameThread.waitTillDoneRunning(false);
    assert(sameThread.stops == 1 && output.size() == 1);
    QThread other;
    ScriptManager stopped;
    stopped.worker = &other; stopped._isThreaded = true;
    stopped.waitTillDoneRunning(true);
    assert(stopped.stops == 1 && output.size() == 2);
    for (const auto& message : output) {
        assert(!message.contains("private-world") && !message.contains("canary"));
    }
    assert(sameThread.filenameReads == 0);
    // The actual JSConsole/ScriptEngines signal route is retained, not a public log.
    assert(console.size() == 1 && console[0].contains("private-world-secret.js?token=canary"));
    stopped.scriptInfoMessage("console-payload-canary", "internal-source", 7);
    assert(console.size() == 2 && console[1].contains("console-payload-canary"));
    assert(output.size() == 3 && !output.last().contains("canary"));
    for (bool server : {false, true}) {
        stopped.server = server;
        stopped.currentEntityIdentifier.invalid = server;
        stopped.scriptInfoMessage("entity-canary", "private-entity-file", 9);
        assert(!output.last().contains("canary") && !output.last().contains("private-entity"));
    }
    assert(stopped.entitySignals == 2);
    for (auto method : {&ScriptManager::scriptErrorMessage, &ScriptManager::scriptWarningMessage,
                        &ScriptManager::scriptPrintedMessage}) {
        for (int route = 0; route < 3; ++route) {
            stopped.server = route == 2;
            stopped.currentEntityIdentifier.invalid = route != 1;
            const auto before = output.size();
            (stopped.*method)("entity-canary", "private-entity-file", 9);
            assert(output.size() == before + 1);
            assert(!output.last().contains("canary") && !output.last().contains("private-entity"));
            assert(console.last().contains("entity-canary") && console.last().contains("private-world"));
        }
    }
    assert(stopped.errorSignals == 3 && stopped.warningSignals == 3 && stopped.printSignals == 3);
    assert(stopped.entitySignals == 8);
}
'''
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-script-shutdown-') as temporary:
            unit = Path(temporary) / 'test.cpp'
            unit.write_text(driver + method + checks)
            binary = Path(temporary) / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), str(unit), '-o', str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
