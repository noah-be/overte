"""Execute the complete production debugPrint with real Qt log capture.

Script engine/context and internal console are explicit fixture boundaries.
"""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class ScriptDebugPrint(unittest.TestCase):
    def test_public_logs_closed_internal_print_preserved(self):
        source = (ROOT / 'libraries/script-engine/src/ScriptManager.cpp').read_text()
        start = source.index('static ScriptValue debugPrint(')
        method = source[start:source.index('\n}', start) + 2]
        driver = r'''
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QStringList>
#include <memory>
#include <cassert>
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(scriptengine_script, "overte.test.script-print")
QStringList logs;
struct ScriptValue { QString text; QString repr() const { return text; } };
struct ScriptFunctionContext {
    enum Type { NativeFunction, ScriptFunction };
    Type type = ScriptFunction;
    QString file = "private-file?token=secret", function = "private-function";
    int line = 42;
    Type functionType() const { return type; }
    QString fileName() const { return file; }
    QString functionName() const { return function; }
    int lineNumber() const { return line; }
};
struct ScriptContext;
using ScriptContextPointer = std::shared_ptr<ScriptContext>;
struct ScriptContext {
    QStringList arguments { "private-message", "credential-canary" };
    ScriptFunctionContext info;
    ScriptContextPointer parent;
    int argumentCount() const { return arguments.size(); }
    ScriptValue argument(int i) const { return {arguments.at(i)}; }
    ScriptFunctionContext* functionContext() { return &info; }
    ScriptContextPointer parentContext() { return parent; }
};
struct ScriptManager {
    QStringList console;
    QString getFilename() { return "private-manager?token=secret"; }
    void print(const QString& message) { console.append(message); }
};
struct ScriptEngine {
    ScriptManager* owner = nullptr;
    ScriptManager* manager() { return owner; }
};
struct AbstractLoggerInterface {
    static AbstractLoggerInterface* instance;
    bool enabled = false;
    static AbstractLoggerInterface* get() { return instance; }
    bool showSourceDebugging() { return enabled; }
};
AbstractLoggerInterface* AbstractLoggerInterface::instance = nullptr;
'''
        checks = r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("overte.test.script-print.debug=true");
    qInstallMessageHandler([](QtMsgType type, const QMessageLogContext&, const QString& msg) {
        assert(type == QtDebugMsg); logs.append(msg);
    });
    ScriptEngine engine;
    ScriptContext context;
    ScriptManager manager;
    AbstractLoggerInterface logger;
    const QString expected = "private-message credential-canary";
    for (int route = 0; route != 8; ++route) {
        logs.clear(); manager.console.clear();
        engine.owner = route == 0 ? nullptr : &manager;
        AbstractLoggerInterface::instance = route < 2 ? nullptr : &logger;
        logger.enabled = route >= 3;
        context.info = ScriptFunctionContext(); context.parent.reset();
        context.arguments = QStringList { "private-message", "credential-canary" };
        if (route == 4) {
            context.info.type = ScriptFunctionContext::NativeFunction;
            context.parent = std::make_shared<ScriptContext>();
        }
        if (route == 5) { context.info.type = ScriptFunctionContext::NativeFunction; }
        if (route == 6) {
            context.info.file.clear(); context.info.function.clear(); context.info.line = -1;
        }
        if (route == 7) { context.arguments.clear(); }
        debugPrint(&context, &engine);
        assert(logs.size() == 1);
        assert(logs.front() == overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted));
        if (route == 0) { assert(manager.console.isEmpty()); }
        else { assert(manager.console == QStringList {route == 7 ? QString() : expected}); }
    }
}
'''
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-script-print-') as temporary:
            cpp = Path(temporary) / 'test.cpp'
            binary = Path(temporary) / 'test'
            cpp.write_text(driver + method + checks)
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT),
                            str(cpp), '-o', str(binary), *flags], check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
