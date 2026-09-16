// SPDX-License-Identifier: Apache-2.0
#include <QtCore/QtCore>
#include <atomic>
#include <cassert>
#include <chrono>
#include <functional>
#include <memory>
#include "libraries/shared/src/Finally.h"
#include "libraries/shared/src/shared/LocalFileAccessGate.h"
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
#define PROFILE_RANGE(...)
#define PROFILE_SET_THREAD_NAME(...)
constexpr int USECS_PER_SECOND = 1000000, SCRIPT_FPS = 60;
qint64 usecTimestampNow() { return QDateTime::currentMSecsSinceEpoch() * 1000; }
std::function<void()> threadNameHook;
void setThreadName(const std::string&) { if (threadNameHook) threadNameHook(); }
Q_LOGGING_CATEGORY(scriptengine, "overte.test.script-run")
struct ScriptEngines { bool stopped = false; bool isStopped() const { return stopped; } };
struct Engine {
    int scopes = 0, evaluations = 0, disconnects = 0, aborts = 0, threadAssignments = 0;
    std::function<void()> onEvaluate, onDisconnect;
    std::unique_ptr<int> getScopeGuard() { ++scopes; return std::make_unique<int>(0); }
    int evaluate(const QString&, const QString&) { ++evaluations; if (onEvaluate) onEvaluate(); return 0; }
    void abortEvaluation() { ++aborts; }
    void setThread(QThread*) { ++threadAssignments; }
    bool hasUncaughtException() { return false; }
    bool isEvaluating() { return false; }
    QString uncaughtException() { return {}; }
    void clearExceptions() {}
    void processEvents() {}
    void perManagerLoopIterationCleanup() {}
    void disconnectSignalProxies() { ++disconnects; if (onDisconnect) onDisconnect(); }
};
class ScriptManager : public QObject, public std::enable_shared_from_this<ScriptManager> {
    Q_OBJECT
public:
    enum Context { CLIENT_SCRIPT, NETWORKLESS_TEST_SCRIPT };
    Context _context = CLIENT_SCRIPT;
    std::shared_ptr<Engine> _engine = std::make_shared<Engine>();
    QWeakPointer<ScriptEngines> _scriptEngines;
    std::shared_ptr<QObject> _assetScriptingInterface = std::make_shared<QObject>();
    std::atomic<bool> _isStopping { false }, _isFinished { false }, _isRunning { false }, _isDoneRunning { false };
#include "run-state.inc"
    bool _isInitialized = false, _isThreaded = false, _abortOnUncaughtException = false;
    QString _fileNameString = "fixture.js", _scriptContents = "fixture";
    int _returnValue = 0, initializations = 0, timerStops = 0;
    qint64 _lastUpdate = 0;
    std::chrono::microseconds _totalTimerExecution { 0 };
    overte::network::RequestScope _scriptLoadContext;
    std::function<void()> onInit;
    bool _emitScriptUpdates() { return true; }
    bool isStopping() const { return _isStopping; }
    QString getFilename() const { return _fileNameString; }
    void init() { ++initializations; _isInitialized = true; if (onInit) onInit(); }
    void stopAllTimers() { ++timerStops; }
    void scriptInfoMessage(const QString&, const QString&, int) {}
    bool isStopped() const;
    void run();
    void runInThread();
    void disconnectNonEssentialSignals();
    void stop(bool marshal = true);
    void waitTillDoneRunning(bool);
signals:
    void runningStateChanged();
    void scriptEnding();
    void releaseEntityPacketSenderMessages(bool);
    void finished(QString, std::shared_ptr<ScriptManager>);
    void doneRunning();
    void update(float);
    void unhandledException(QString);
};
#include "run.inc"
#include "run.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const std::string mode(argv[1]);
    const bool threadlaunch = mode.rfind("threadlaunch", 0) == 0;
    auto engines = QSharedPointer<ScriptEngines>::create();
    auto owner = threadlaunch ? std::shared_ptr<ScriptManager>(new ScriptManager,
        [](ScriptManager* manager) { manager->deleteLater(); }) : std::make_shared<ScriptManager>();
    QPointer<ScriptManager> observed(owner.get());
    owner->_scriptEngines = engines;
    auto engine = owner->_engine;
    std::weak_ptr<ScriptManager> weak = owner;
    engine->onEvaluate = [weak] {
        if (auto manager = weak.lock()) {
            QTimer::singleShot(0, manager.get(), [weak] { if (auto m = weak.lock()) m->stop(false); });
        }
    };
    int finished = 0, done = 0, ending = 0, releases = 0;
    auto attachObservers = [&] {
    QObject::connect(owner.get(), &ScriptManager::finished, [&](const QString&, std::shared_ptr<ScriptManager> value) {
        assert(value.get() == observed); ++finished;
        if (mode == "release") owner.reset();
        if (mode == "reentrant") value->run();
    });
    QObject::connect(owner.get(), &ScriptManager::doneRunning, [&] { ++done; });
    QObject::connect(owner.get(), &ScriptManager::scriptEnding, [&] { ++ending; });
    QObject::connect(owner.get(), &ScriptManager::releaseEntityPacketSenderMessages, [&](bool last) { if (last) ++releases; });
    engine->onDisconnect = [&] { assert(observed && finished == 1 && done == 1); };
    QObject::connect(owner.get(), &ScriptManager::runningStateChanged, [&] {
        if (!observed || !observed->_isRunning) return;
        if (mode == "runningstop") observed->stop(false);
        if (mode == "reentrant") observed->run();
    });
    };
    attachObservers();
    if (mode == "prestop") owner->stop(false);
    if (mode == "globalstop") engines->stopped = true;
    if (mode == "initstop") owner->onInit = [weak] { if (auto m = weak.lock()) m->stop(false); };
    hifi::scripting::setLocalAccessSafeThread(true);
    if (mode == "threaded") {
        QSemaphore entered, proceed;
        auto mainThread = app.thread();
        auto manager = owner;
        std::unique_ptr<QThread> worker(QThread::create([&, manager] {
            entered.release(); proceed.acquire();
            manager->run();
            assert(!hifi::scripting::isLocalAccessSafeThread());
            manager->_assetScriptingInterface->moveToThread(mainThread);
            manager->moveToThread(mainThread);
        }));
        manager->_isThreaded = true;
        manager->_assetScriptingInterface->moveToThread(worker.get());
        manager->moveToThread(worker.get());
        worker->start(); assert(entered.tryAcquire(1, 1000));
        manager->stop(true); // Direct stop intent, queued completion target held.
        proceed.release();
        manager->waitTillDoneRunning(false);
        assert(worker->wait(1000));
        assert(manager->_isDoneRunning && manager->initializations == 0 && engine->evaluations == 0);
    } else if (threadlaunch) {
        QSemaphore entered, proceed;
        if (mode == "threadlaunch-disconnect") {
            threadNameHook = [&] { entered.release(); proceed.acquire(); };
        }
        owner->runInThread();
        auto worker = owner->thread();
        QPointer<QThread> workerObject(worker);
        assert(worker != app.thread() && engine->threadAssignments == 1);
        if (mode == "threadlaunch-disconnect") {
            assert(entered.tryAcquire(1, 1000) && !owner->_isRunning);
            owner->disconnectNonEssentialSignals();
            attachObservers();
            proceed.release();
        }
        owner->waitTillDoneRunning(false);
        assert(owner->_isDoneRunning);
        owner.reset(); // Same deferred QObject deleter as the production factory.
        assert(worker->wait(1000));
        QCoreApplication::processEvents();
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!workerObject);
    } else {
        owner->run();
    }
    assert(finished == 1 && done == 1 && releases == 1 && engine->disconnects == 1);
    if (mode == "release" || threadlaunch) { assert(!observed && weak.expired()); }
    else {
        assert(owner->_isDoneRunning && owner->_isFinished && owner->_isStopping && !owner->_isRunning);
        const bool noInit = mode == "prestop" || mode == "globalstop" || mode == "threaded";
        const bool noEval = noInit || mode == "initstop" || mode == "runningstop";
        assert(owner->initializations == int(!noInit) && ending == int(!noInit));
        assert(engine->evaluations == int(!noEval) && owner->timerStops == 1);
        const int scopes = engine->scopes;
        owner->run(); // Exactly one admitted lifecycle, including rejected starts.
        owner->runInThread(); // A completed direct run cannot create a new worker.
        assert(finished == 1 && done == 1 && engine->scopes == scopes);
        assert(engine->threadAssignments == 0);
    }
    assert(hifi::scripting::isLocalAccessSafeThread());
}
