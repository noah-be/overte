// Entity lookup and renderer ownership are explicit seams; both production
// renderer functions and the production ScriptManager fence are compiled below.
class FixtureEntity {
public:
    QString script;
    bool local { false };
    QString getScript() const { return script; }
    bool isLocalEntity() const { return local; }
    bool isMyAvatarEntity() const { return false; }
};
class FixtureTree {
public:
    QHash<EntityItemID, std::shared_ptr<FixtureEntity>> entities;
    std::shared_ptr<FixtureEntity> findEntityByEntityItemID(const EntityItemID& id) { return entities.value(id); }
};
using ScriptManagerPointer = std::shared_ptr<ScriptManager>;
QString resolveScriptURL(const QString& source) { return source; } // URL resolution seam
class EntityTreeRenderer : public QObject {
public:
    using EntityScriptConsentPrompt = ScriptManager::EntityScriptConsentPrompt;
    QWeakPointer<EntityTreeRenderer> self;
    QSharedPointer<EntityTreeRenderer> getSharedFromThis() { return self.toStrongRef(); }
    FixtureTree tree;
    FixtureTree* _tree { &tree };
    FixtureTree* getTree() { return _tree; }
    bool _shuttingDown { false }, _wantScripts { true };
    quint64 _entityScriptConsentGeneration { 0 };
    int resets { 0 }, reloads { 0 };
    void resetPersistentEntitiesScriptEngine() {
        ++resets; _persistentEntitiesScriptManager = std::make_shared<ScriptManager>(ScriptManager::ENTITY_CLIENT_SCRIPT);
        bindEntityScriptConsent(_persistentEntitiesScriptManager);
    }
    void resetNonPersistentEntitiesScriptEngine() {
        ++resets; _nonPersistentEntitiesScriptManager = std::make_shared<ScriptManager>(ScriptManager::ENTITY_CLIENT_SCRIPT);
        bindEntityScriptConsent(_nonPersistentEntitiesScriptManager);
    }
    void reloadEntityScripts() { ++reloads; }
    void beginEntityScriptConsent(std::shared_ptr<EntityScriptConsentScope>, EntityScriptConsentPrompt);
    void endEntityScriptConsent();
    ScriptManagerPointer _persistentEntitiesScriptManager, _nonPersistentEntitiesScriptManager;
    std::shared_ptr<EntityScriptConsentScope> _entityScriptConsentScope;
    EntityScriptConsentPrompt _entityScriptConsentPrompt;
    bool isCurrentEntityScriptConsentRequest(const ScriptManagerPointer&, const EntityItemID&,
        const std::shared_ptr<EntityScriptConsentRequest>&);
    void bindEntityScriptConsent(const ScriptManagerPointer&);
};
#include "consent-renderer.inc"
static void deliverConsentEvents() {
    for (int i = 0; i != 6; ++i) { QCoreApplication::sendPostedEvents(nullptr, QEvent::MetaCall); }
}
static void testRendererConsent() {
    {
        QSharedPointer<EntityTreeRenderer> renderer(new EntityTreeRenderer); renderer->self=renderer;
        renderer->_persistentEntitiesScriptManager=std::make_shared<ScriptManager>(ScriptManager::ENTITY_CLIENT_SCRIPT);
        renderer->_nonPersistentEntitiesScriptManager=std::make_shared<ScriptManager>(ScriptManager::ENTITY_CLIENT_SCRIPT);
        const auto prompt=[](const auto&,const auto&,auto){};
        auto first=std::make_shared<EntityScriptConsentScope>("first");
        renderer->beginEntityScriptConsent(first,prompt);
        auto persistent=renderer->_persistentEntitiesScriptManager;
        auto nonpersistent=renderer->_nonPersistentEntitiesScriptManager;
        first->invalidate();
        assert(persistent->stopCalls==1&&nonpersistent->stopCalls==1);
        assert(renderer->resets==2&&renderer->reloads==1);
        auto second=std::make_shared<EntityScriptConsentScope>("second");
        renderer->beginEntityScriptConsent(second,prompt);
        persistent=renderer->_persistentEntitiesScriptManager;
        nonpersistent=renderer->_nonPersistentEntitiesScriptManager;
        auto newest=std::make_shared<EntityScriptConsentScope>("newest");
        persistent->onStop=[&]{renderer->beginEntityScriptConsent(newest,prompt);};
        auto superseded=std::make_shared<EntityScriptConsentScope>("superseded");
        renderer->beginEntityScriptConsent(superseded,prompt);
        assert(renderer->_entityScriptConsentScope==newest&&newest->active());
        assert(!second->active()&&nonpersistent->stopCalls==1);
        renderer->endEntityScriptConsent();
        assert(!newest->active()&&!renderer->_entityScriptConsentScope&&!renderer->_entityScriptConsentPrompt);
        const auto resets=renderer->resets;
        renderer->beginEntityScriptConsent(newest,prompt);assert(renderer->resets==resets);
    }
    for (int scenario = 0; scenario != 7; ++scenario) {
        QSharedPointer<EntityTreeRenderer> renderer(new EntityTreeRenderer);
        renderer->self = renderer;
        auto manager = std::make_shared<ScriptManager>(ScriptManager::ENTITY_CLIENT_SCRIPT);
        renderer->_nonPersistentEntitiesScriptManager = manager;
        renderer->_entityScriptConsentScope = std::make_shared<EntityScriptConsentScope>("fixture-origin");
        auto entity = std::make_shared<FixtureEntity>(); entity->script = "https://source.invalid/entity.js";
        renderer->tree.entities["entity"] = entity;
        std::function<void(bool)> respond;
        int prompts = 0;
        renderer->_entityScriptConsentPrompt = [&](const auto&, const auto&, auto callback) {
            ++prompts; respond = std::move(callback);
        };
        renderer->bindEntityScriptConsent(manager);
        manager->loadEntityScript("entity", entity->script, false);
        if (scenario == 1) { entity->script = "https://replacement.invalid/new.js"; }
        deliverConsentEvents();
        if (scenario == 1) { assert(prompts == 0 && manager->afterLoadFence == 0); continue; }
        assert(prompts == 1 && respond && manager->afterLoadFence == 0);
        switch (scenario) {
            case 2: entity->script = "https://replacement.invalid/new.js"; break;
            case 3: renderer->_entityScriptConsentScope->invalidate(); break;
            case 4: renderer->_nonPersistentEntitiesScriptManager.reset(); break;
            case 5: renderer->tree.entities.clear(); break;
            case 6: renderer.clear(); break;
        }
        // The eventual UI callback may arrive from another thread.
        std::thread input([&] { respond(true); }); input.join();
        deliverConsentEvents();
        assert(manager->afterLoadFence == (scenario == 0 ? 1 : 0));
        respond(true); deliverConsentEvents();
        assert(manager->afterLoadFence == (scenario == 0 ? 1 : 0));
    }
}
