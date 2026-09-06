#include <QCoreApplication>
#include <QHash>
#include <QLoggingCategory>
#include <QReadWriteLock>
#include <QThread>
#include <cassert>
#include <memory>
#include <thread>

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
    bool rejectEntityScriptWithoutConsent(const EntityItemID&, const QString&);
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
    assert(!captured.contains("private-secret") && !captured.contains("private-entity") && !captured.contains("secret-token"));
}
