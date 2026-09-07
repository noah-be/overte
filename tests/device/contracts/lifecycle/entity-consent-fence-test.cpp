#include <QCoreApplication>
#include <QHash>
#include <QLoggingCategory>
#include <QReadWriteLock>
#include <QThread>
#include <QSharedPointer>
#include <QWeakPointer>
#include <QEvent>
#include <QUrl>
#include <cassert>
#include <memory>
#include <thread>
#include <functional>
#include "EntityScriptConsent.h"

Q_LOGGING_CATEGORY(scriptengine, "consent-fence-test")
using EntityItemID = QString;
enum class EntityScriptStatus { PENDING, ERROR_LOADING_SCRIPT };
struct EntityScriptDetails {
    EntityScriptStatus status { EntityScriptStatus::PENDING };
    QString errorInfo;
};

// Real manager ownership/dispatch and Qt lock/map. Only unrelated engine,
// networking and signal receivers are replaced at the explicit test boundary.
class ScriptManager : public QObject, public std::enable_shared_from_this<ScriptManager> {
public:
#include "context.inc"
    explicit ScriptManager(Context context) : _context(context) {}
    void loadEntityScript(const EntityItemID&, const QString&, bool);
    void entityScriptContentAvailable(const EntityItemID&, const QString&, const QString&, bool, bool, const QString&);
    using EntityScriptConsentPrompt = std::function<void(const EntityItemID&,
        const std::shared_ptr<EntityScriptConsentRequest>&, std::function<void(bool)>)>;
    bool bindEntityScriptConsent(std::shared_ptr<EntityScriptConsentScope>, EntityScriptConsentPrompt);
    bool rejectEntityScriptWithoutConsent(const EntityItemID&, const QString&, bool = false, bool = false);
    std::function<void(std::function<void()>)> captureScriptEnvironment();
    EntityItemID currentEntityIdentifier;
    QUrl currentSandboxURL;
    std::shared_ptr<EntityScriptConsentRequest> _currentEntityScriptConsentRequest;
    bool entityScriptInvocationAllowed(const EntityItemID&, const std::shared_ptr<EntityScriptConsentRequest>&) const;
    void doWithEnvironment(const EntityItemID&, const QUrl&, std::function<void()>, const std::shared_ptr<EntityScriptConsentRequest>& = {});
    bool isStopping() const { return stopping; }
    int stopCalls { 0 };
    std::function<void()> onStop;
    void stop() { stopping = true; ++stopCalls; if (onStop) { auto callback = std::move(onStop); onStop = {}; callback(); } }
    bool stopping { false }, _isFinished { false };
    std::atomic<bool> _hasRunStarted { false };
    std::shared_ptr<EntityScriptConsentScope> _entityScriptConsentScope;
    EntityScriptConsentPrompt _entityScriptConsentPrompt;
    QHash<EntityItemID, QHash<QString, std::shared_ptr<EntityScriptConsentRequest>>> _entityScriptConsentRequests;
    void updateEntityScriptStatus(const EntityItemID&, const QString&, const EntityScriptStatus&, const QString&);
    void entityScriptDetailsUpdated() {
        assert(QThread::currentThread() == thread());
        ++updates;
    }
    const Context _context;
    int _type { 0 }; // Mutable script-facing type must not grant consent.
    QReadWriteLock _entityScriptsLock;
    QHash<EntityItemID, QHash<QString, EntityScriptDetails>> _entityScripts;
    int updates { 0 }, afterLoadFence { 0 }, afterCallbackFence { 0 };
};
#include "consent-fence.inc"
#include "entity-consent-renderer-test.inc"

static QString captured;
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext&, const QString& message) { captured += message; });
    qputenv("UNSAFE_ENTITY_SCRIPTS", "1");
    qputenv("EXTRA_ALLOWLIST", "https://private-secret.invalid/");
    const QString entity = QStringLiteral("private-entity-canary");
    const QStringList inputs { QStringLiteral("https://private-secret.invalid/script?token=secret-token"),
                              QStringLiteral("file:///private-secret/script.js"),
                              QStringLiteral("cache:private-secret"),
                              QStringLiteral("(function(){ throw 'private-secret'; })") };
    for (auto context : {ScriptManager::CLIENT_SCRIPT, ScriptManager::ENTITY_CLIENT_SCRIPT}) {
        auto manager = std::make_shared<ScriptManager>(context);
        manager->_type = ScriptManager::ENTITY_SERVER_SCRIPT;
        for (const auto& input : inputs) {
            manager->loadEntityScript(entity, input, true);
            for (bool success : {false, true}) {
                manager->entityScriptContentAvailable(entity, input, "private-secret-js", true, success, "private-secret-status");
            }
            const auto detail = manager->_entityScripts[entity][input];
            assert(detail.status == EntityScriptStatus::ERROR_LOADING_SCRIPT);
            assert(detail.errorInfo == "ENTITY_SCRIPT_CONSENT_UNAVAILABLE");
        }
        assert(manager->afterLoadFence == 0 && manager->afterCallbackFence == 0);
        assert(manager->updates == 12);
        assert(manager->_entityScriptsLock.tryLockForWrite());
        manager->_entityScriptsLock.unlock();
        // The original entry lambdas retain the manager and queue to its owner.
        std::thread caller([manager, entity, inputs] {
            manager->loadEntityScript(entity, inputs[0], false);
            manager->entityScriptContentAvailable(entity, inputs[0], "private-secret-js", true, true, "private-secret-status");
        });
        caller.join();
        assert(manager->updates == 12);
        QCoreApplication::processEvents();
        assert(manager->updates == 14);
        assert(manager->afterLoadFence == 0 && manager->afterCallbackFence == 0);
    }
    for (auto context : {ScriptManager::ENTITY_SERVER_SCRIPT, ScriptManager::AGENT_SCRIPT,
                         ScriptManager::NETWORKLESS_TEST_SCRIPT}) {
        auto manager = std::make_shared<ScriptManager>(context);
        manager->loadEntityScript(entity, inputs[0], false);
        manager->entityScriptContentAvailable(entity, inputs[0], "", true, true, "");
        assert(manager->updates == 0 && manager->afterLoadFence == 1 && manager->afterCallbackFence == 1);
    }
    {
        auto manager = std::make_shared<ScriptManager>(ScriptManager::ENTITY_CLIENT_SCRIPT);
        auto scope = std::make_shared<EntityScriptConsentScope>("fixture-origin");
        std::vector<std::function<void(bool)>> decisions;
        assert(manager->bindEntityScriptConsent(scope, [&](const EntityItemID& id,
            const std::shared_ptr<EntityScriptConsentRequest>& request, std::function<void(bool)> decide) {
            assert(id == entity && request->origin() == "fixture-origin");
            assert(!request->allowed());
            decisions.push_back(std::move(decide));
        }));
        assert(!manager->bindEntityScriptConsent(scope, [](auto&, auto&, auto) {}));
        manager->loadEntityScript(entity, inputs[0], false);
        manager->loadEntityScript(entity, inputs[0], false);
        assert(decisions.size() == 1 && manager->afterLoadFence == 0);
        decisions[0](false); decisions[0](true);
        QCoreApplication::processEvents();
        assert(manager->afterLoadFence == 0);
        assert(manager->_entityScripts[entity][inputs[0]].errorInfo == "ENTITY_SCRIPT_CONSENT_DECLINED");
        manager->loadEntityScript(entity, inputs[1], false);
        assert(decisions.size() == 2);
        decisions[1](true); decisions[1](true);
        QCoreApplication::processEvents();
        assert(manager->afterLoadFence == 1);
        manager->entityScriptContentAvailable(entity, inputs[1], "", true, true, "");
        assert(manager->afterCallbackFence == 1);
        auto approved = manager->_entityScriptConsentRequests.value(entity).value(inputs[1]);
        int calls = 0;
        std::function<void(std::function<void()>)> heldSignal;
        manager->doWithEnvironment(entity, QUrl(inputs[1]), [&] {
            ++calls;
            heldSignal = manager->captureScriptEnvironment();
            assert(manager->_currentEntityScriptConsentRequest == approved);
            manager->doWithEnvironment(entity, QUrl(), [&] { ++calls; }, {});
            assert(manager->_currentEntityScriptConsentRequest == approved);
        }, approved);
        assert(calls == 1 && !manager->_currentEntityScriptConsentRequest);
        // A held callback cannot borrow a later approval of the same spelling.
        manager->_entityScriptConsentRequests[entity].remove(inputs[1]);
        manager->loadEntityScript(entity, inputs[1], false);
        decisions.back()(true); QCoreApplication::processEvents();
        auto replacement = manager->_entityScriptConsentRequests.value(entity).value(inputs[1]);
        assert(replacement != approved && replacement->allowed());
        manager->doWithEnvironment(entity, QUrl(inputs[1]), [&] { ++calls; }, approved);
        heldSignal([&] { ++calls; });
        assert(calls == 1);
        manager->doWithEnvironment(entity, QUrl(inputs[1]), [&] { ++calls; }, replacement);
        assert(calls == 2);
        scope->invalidate(); scope->invalidate();
        manager->doWithEnvironment(entity, QUrl(inputs[1]), [&] { ++calls; }, replacement);
        assert(calls == 2);
        assert(manager->stopCalls == 1 && manager->stopping);
        manager->entityScriptContentAvailable(entity, inputs[1], "", true, true, "");
        assert(manager->afterCallbackFence == 1);
        manager.reset(); decisions[1](true); QCoreApplication::processEvents();
    }
    testRendererConsent();
    assert(!captured.contains("private-secret") && !captured.contains("private-entity") && !captured.contains("secret-token"));
}
