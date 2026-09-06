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
        for signature in ('bool ScriptManager::hasValidScriptSuffix(', 'void ScriptManager::loadURL(', 'void ScriptManager::stop('):
            start = source.index(signature)
            methods += source[start:source.index('\n}', start) + 2] + '\n'
        driver = r'''
#include <QtCore/QCoreApplication>
#include <QtCore/QLoggingCategory>
#include <QtCore/QFileInfo>
#include <QtCore/QUrl>
#include <QtCore/QThread>
#include <QtCore/QSemaphore>
#include <QtCore/QStringList>
#include <functional>
#include <memory>
#include <cassert>
#include "security/redaction/SafeDiagnostics.h"
#include "libraries/networking/src/RequestCancellation.h"
Q_LOGGING_CATEGORY(scriptengine, "overte.test.script-load")
QStringList logs;
std::function<void()> onLog;
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
// VM execution is covered separately by the real V8 stop regression.
struct Engine { void abortEvaluation() {} };
struct ScriptManager : QObject, std::enable_shared_from_this<ScriptManager> {
    std::shared_ptr<Engine> _engine = std::make_shared<Engine>();
    bool _isRunning = false, _isReloading = false;
    std::atomic<bool> _isStopping {false}, _isFinished {false};
    int runningSignals = 0;
    void stop(bool);
    void runningStateChanged() { ++runningSignals; }
    overte::network::RequestScope _scriptLoadContext;
    QString _fileNameString, _scriptContents = "existing-script";
    QStringList errors, failed, loaded;
    std::function<void()> onError;
    bool hasValidScriptSuffix(const QString&);
    void loadURL(const QUrl&, bool);
    void scriptErrorMessage(const QString& message, const QString& file, int line) {
        if (onError) { auto action = onError; action(); }
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
        if (onLog) { auto action = onLog; action(); }
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
            auto ownedManager = std::make_shared<ScriptManager>();
            auto& manager = *ownedManager; logs.clear();
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
    auto owner = std::make_shared<ScriptManager>();
    std::weak_ptr<ScriptManager> weak = owner;
    owner->onError = [&] {
        owner.reset();
        // Callback must retain the real shared owner through reentrant signals.
        assert(!weak.expired());
    };
    owner->loadURL(url, false);
    cache.callback(callbackUrl, "", true, false, status);
    assert(weak.expired());
    // The cache retains only a weak reference, not an indefinitely live manager.
    owner = std::make_shared<ScriptManager>();
    weak = owner;
    owner->loadURL(url, false);
    owner.reset();
    assert(weak.expired());
    logs.clear();
    cache.callback(callbackUrl, "private-late-source", true, true, status);
    cache.callback(callbackUrl, "", true, false, status);
    assert(logs.isEmpty());
    auto ordered = std::make_shared<ScriptManager>();
    ordered->loadURL(url, false);
    auto oldCompletion = cache.callback;
    ordered->loadURL(url, true);
    auto currentCompletion = cache.callback;
    currentCompletion(callbackUrl, "new-source", true, true, status);
    logs.clear();
    oldCompletion(callbackUrl, "stale-source", true, true, status);
    assert(ordered->_scriptContents == "new-source");
    assert(ordered->loaded.size() == 1 && logs.isEmpty());
    currentCompletion(callbackUrl, "duplicate-source", true, true, status);
    assert(ordered->_scriptContents == "new-source" && ordered->loaded.size() == 1);
    ordered->loadURL(url, false);
    auto interrupted = cache.callback;
    ordered->onError = [&] { ordered->loadURL(url, true); };
    interrupted(callbackUrl, "", true, false, status);
    assert(ordered->failed.isEmpty() && ordered->loaded.size() == 1);
    ordered->onError = {};
    cache.callback(callbackUrl, "replacement-source", true, true, status);
    assert(ordered->_scriptContents == "replacement-source" && ordered->loaded.size() == 2);
    ordered->loadURL(url, false);
    auto invalidated = cache.callback;
    ordered->loadURL(QUrl("https://private.example/no-script.txt"), false);
    const auto loadedBefore = ordered->loaded.size();
    logs.clear();
    invalidated(callbackUrl, "invalidated-source", true, true, status);
    assert(ordered->_scriptContents == "replacement-source");
    assert(ordered->loaded.size() == loadedBefore && logs.isEmpty());
    ordered->loadURL(url, false);
    auto logInterrupted = cache.callback;
    onLog = [&] { onLog = {}; ordered->loadURL(url, true); };
    logInterrupted(callbackUrl, "log-superseded-source", true, true, status);
    assert(ordered->_scriptContents == "replacement-source");
    assert(ordered->loaded.size() == loadedBefore);
    cache.callback(callbackUrl, "after-log-replacement", true, true, status);
    assert(ordered->_scriptContents == "after-log-replacement");
    assert(ordered->loaded.size() == loadedBefore + 1);
    auto stopping = std::make_shared<ScriptManager>();
    stopping->loadURL(url, false);
    auto stoppedCompletion = cache.callback;
    stopping->stop(true);
    assert(stopping->_isStopping && stopping->_isFinished && stopping->runningSignals == 1);
    logs.clear();
    stoppedCompletion(callbackUrl, "stopped-source", true, true, status);
    stoppedCompletion(callbackUrl, "", true, false, status);
    assert(stopping->_scriptContents == "existing-script");
    assert(stopping->loaded.isEmpty() && stopping->failed.isEmpty() && logs.isEmpty());
    const auto callsBeforeStoppedLoad = cache.calls;
    stopping->loadURL(url, true);
    stopping->stop(false);
    assert(cache.calls == callsBeforeStoppedLoad && stopping->runningSignals == 1);
    // Hold the real target event loop before it can deliver the marshalled stop.
    struct HeldThread : QThread {
        QSemaphore entered, proceed;
        void run() override { entered.release(); proceed.acquire(); exec(); }
    } worker;
    auto queued = std::make_shared<ScriptManager>();
    queued->loadURL(url, false);
    auto queuedCompletion = cache.callback;
    queued->moveToThread(&worker);
    worker.start();
    assert(worker.entered.tryAcquire(1, 2000));
    queued->stop(true);
    assert(queued->_isStopping && !queued->_isFinished && queued->runningSignals == 0);
    logs.clear();
    queuedCompletion(callbackUrl, "queued-stop-source", true, true, status);
    queuedCompletion(callbackUrl, "", true, false, status);
    assert(queued->_scriptContents == "existing-script" && queued->loaded.isEmpty());
    assert(queued->failed.isEmpty() && logs.isEmpty());
    worker.proceed.release();
    auto mainThread = QThread::currentThread();
    // Runs behind the queued stop; then restore affinity for safe destruction.
    assert(QMetaObject::invokeMethod(queued.get(), [queued, mainThread] {
        queued->moveToThread(mainThread);
    }, Qt::BlockingQueuedConnection));
    assert(queued->_isFinished && queued->runningSignals == 1);
    worker.quit();
    assert(worker.wait(2000));
}
'''
        header = (ROOT / 'libraries/script-engine/src/ScriptManager.h').read_text()
        self.assertIn('overte::network::RequestScope _scriptLoadContext;', header)
        self.assertIn('#include <RequestCancellation.h>', header)
        self.assertIn('std::atomic<bool> _isStopping', header)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-script-load-') as temporary:
            cpp = Path(temporary) / 'test.cpp'
            binary = Path(temporary) / 'test'
            cpp.write_text(driver + methods + checks)
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), str(cpp),
                            '-o', str(binary), *flags], check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=10)
            # Moving invalidation onto the target thread must fail specifically
            # while that thread is held, despite passing direct-stop cases.
            late_invalidation = methods.replace('_scriptLoadContext.setActive(false);', '')
            late_invalidation = late_invalidation.replace(
                'if (!_isFinished) {',
                'if (!_isFinished) { _scriptLoadContext.setActive(false);')
            self.assertNotEqual(methods, late_invalidation)
            cpp.write_text(driver + late_invalidation + checks)
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), str(cpp),
                            '-o', str(binary), *flags], check=True, timeout=60)
            rejected = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn('queued->_scriptContents == "existing-script"', rejected.stderr)


if __name__ == '__main__':
    unittest.main()
