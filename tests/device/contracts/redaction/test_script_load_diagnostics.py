"""Actual loadURL and suffix methods, real Qt logs, explicit cache/signal seams."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class ScriptLoadDiagnostics(unittest.TestCase):
    def test_load_outcomes_preserve_internal_state_without_public_urls(self):
        source = (ROOT / 'libraries/script-engine/src/ScriptManager.cpp').read_text()
        methods = ''
        for signature in ('bool ScriptManager::hasValidScriptSuffix(', 'void ScriptManager::loadURL('):
            start = source.index(signature)
            methods += source[start:source.index('\n}', start) + 2] + '\n'
        driver = r'''
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QFileInfo>
#include <QtCore/QUrl>
#include <QtCore/QThread>
#include <QtCore/QStringList>
#include <functional>
#include <cassert>
#include "security/redaction/SafeDiagnostics.h"
Q_LOGGING_CATEGORY(scriptengine, "overte.test.script-load")
QStringList logs;
struct ScriptCache {
    using Callback = std::function<void(const QString&, const QString&, bool, bool, const QString&)>;
    Callback callback;
    QString requested;
    bool reload = false;
    int retries = -1, calls = 0;
    void getScriptContents(const QString& url, Callback fn, bool force, int count) {
        requested = url; callback = fn; reload = force; retries = count; ++calls;
    }
} cache;
struct DependencyManager { template<class T> static T* get() { return &cache; } };
QUrl expandScriptUrl(const QUrl& value) { return value; }
struct ScriptManager {
    bool _isRunning = false, _isReloading = false;
    QString _fileNameString, _scriptContents = "existing-script";
    QStringList errors, failed, loaded;
    bool hasValidScriptSuffix(const QString&);
    void loadURL(const QUrl&, bool);
    void scriptErrorMessage(const QString& message, const QString& file, int line) {
        assert(line == -1); errors.append(message); errors.append(file);
    }
    void errorLoadingScript(const QString& file) { failed.append(file); }
    void scriptLoaded(const QString& file) { loaded.append(file); }
};
'''
        checks = r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QLoggingCategory::setFilterRules("overte.test.script-load.debug=true");
    qInstallMessageHandler([](QtMsgType type, const QMessageLogContext&, const QString& message) {
        assert(type == QtDebugMsg); logs.append(message);
    });
    const QUrl url("https://private.example/private.js?token=credential-canary");
    const QString callbackUrl = "https://private-cache.example/script.js?token=cache-canary";
    const QString status = "private-server-error-canary";
    ScriptManager running; running._isRunning = true;
    running.loadURL(url, true);
    assert(cache.calls == 0 && running._fileNameString.isEmpty() && !running._isReloading);
    ScriptManager invalid;
    invalid.loadURL(QUrl("https://private.example/file.txt"), false);
    assert(cache.calls == 0 && invalid.failed.size() == 1 && invalid.errors.size() == 2);
    assert(invalid.loaded.isEmpty() && logs.isEmpty());
    for (bool success : {false, true}) {
        for (bool isUrl : {false, true}) {
            ScriptManager manager; logs.clear();
            manager.loadURL(url, success);
            assert(manager._fileNameString == url.toString());
            assert(manager._isReloading == success && cache.reload == success);
            assert(cache.requested == url.toString() && cache.retries == 0);
            assert(manager.loaded.isEmpty());
            cache.callback(callbackUrl, "private-script-contents", isUrl, success, status);
            assert(logs.size() == 1);
            assert(logs.front() == overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted));
            assert(manager.loaded == QStringList {callbackUrl});
            if (success) {
                assert(manager._scriptContents == "private-script-contents");
                assert(manager.failed.isEmpty() && manager.errors.isEmpty());
            } else {
                assert(manager._scriptContents == "existing-script");
                assert(manager.failed == QStringList {url.toString()});
                assert(manager.errors.size() == 2 && manager.errors.back() == callbackUrl);
                assert(manager.errors.front().contains(status));
            }
        }
    }
}
'''
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-script-load-') as temporary:
            cpp = Path(temporary) / 'test.cpp'
            binary = Path(temporary) / 'test'
            cpp.write_text(driver + methods + checks)
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), str(cpp),
                            '-o', str(binary), *flags], check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
