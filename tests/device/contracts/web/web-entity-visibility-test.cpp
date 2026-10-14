// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Actual renderer update/build/release bodies with real Qt Quick visibility.
// Entity properties, surface acquisition/cache and rendering are explicit
// boundaries. The shared native document policy below is production code.
#include <QGuiApplication>
#include <QQuickItem>
#include <QQuickWindow>
#include <QSharedPointer>
#include <QWeakPointer>
#include <QPointer>
#include <QThread>
#include <QSize>
#include <QVariant>
#include <QDebug>
#include <atomic>
#include <cassert>
#include <functional>
#include <iostream>
#include <vector>
#include "libraries/shared/src/EmbeddedWebPolicy.h"

using overte::web::EmbeddedWebSession;
const QUrl DOCUMENT("https://world.example/app.html");
namespace glm { struct vec2 { float x { 64 }, y { 64 }; }; }
namespace hifi { namespace scripting { void setLocalAccessSafeThread(bool) {} }
namespace qml {
class OffscreenSurface : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
signals:
    void rootItemCreated(QQuickItem* item);
};
} }

class DocumentProbe : public QQuickItem {
public:
    EmbeddedWebSession session;
    DocumentProbe(QQuickItem* parent) : QQuickItem(parent) {
        session.open(DOCUMENT, overte::web::Surface::WorldEntity, "native-document-boundary");
        session.setVisible(isVisible());
        connect(this, &QQuickItem::visibleChanged, this, [this] { session.setVisible(isVisible()); });
    }
};
struct ContextBoundary { void setContextProperty(const char*, const QVariant&) {} };
class OffscreenQmlSurface : public hifi::qml::OffscreenSurface {
    Q_OBJECT
public:
    QPointer<QQuickItem> root;
    QQuickWindow window;
    DocumentProbe* document {};
    ContextBoundary context;
    QQuickItem* getRootItem() const { return root; }
    ContextBoundary* getSurfaceContext() { return &context; }
    void resume() {}
    void resize(const QSize&) {}
    void setMaxFps(int) {}
    void createRoot() {
        delete root;
        root = new QQuickItem(window.contentItem());
        root->QObject::setParent(this);
        document = new DocumentProbe(root);
        emit rootItemCreated(root);
    }
signals:
    void webEventReceived(const QVariant& message);
public slots:
    void emitScriptEvent(const QVariant&) {}
};
struct EntityBoundary {
    bool visible { true };
    QString url { DOCUMENT.toString() };
    bool getVisible() const { return visible; }
    QString getSourceUrl() const { return url; }
    int getInputMode() const { return 0; }
    int getDpi() const { return 30; }
    int getColor() const { return 1; }
    float getAlpha() const { return 1; }
    bool getWantsKeyboardFocus() const { return true; }
    int getPulseProperties() const { return 0; }
    bool getLocalSafeContext() const { return false; }
    QString getScriptURL() const { return {}; }
    int getMaxFPS() const { return 10; }
    bool getUseBackground() const { return false; }
    QString getUserAgent() const { return {}; }
    int getWorldPosition() const { return 0; }
    int getScaledDimensions() const { return 1; }
    QString getID() const { return "entity-boundary"; }
};
using EntityItemPointer = QSharedPointer<EntityBoundary>;
using EntityItemID = QString;
using ScenePointer = void*;
struct Transaction {};
struct TransformBoundary { void setScale(float) {} void postScale(int) {} };
QVariant vec3toVariant(int value) { return value; }
struct AbstractViewStateInterface {
    static AbstractViewStateInterface* instance() { static AbstractViewStateInterface value; return &value; }
    void pushPostUpdateLambda(void*, const std::function<void()>&) {} // GPU sizing boundary.
};
class EntityScriptingInterface : public QObject {
    Q_OBJECT
signals:
    void webEventReceived(const QString&, const QVariant&);
};
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() { static auto value = QSharedPointer<T>::create(); return value; }
};
const QString HIFI_URL_SCHEME_ABOUT("about"), HIFI_URL_SCHEME_HTTP("http"),
    HIFI_URL_SCHEME_HTTPS("https"), URL_SCHEME_DATA("data");
static std::atomic<uint32_t> _currentWebCount(0);
static const uint32_t MAX_CONCURRENT_WEB_VIEWS = 20;
static uint8_t YOUTUBE_MAX_FPS = 30;

class WebEntityRenderer : public QObject {
    Q_OBJECT
public:
    using TypedEntityPointer = EntityItemPointer;
    enum class ContentType { NoContent, HtmlContent, QmlContent };
    ContentType _contentType { ContentType::HtmlContent };
    QSharedPointer<OffscreenQmlSurface> _webSurface;
#include "production-visibility-members.inc"
    bool _cachedWebSurface {};
    QString _tryingToBuildURL, _sourceURL, _scriptURL, _userAgent;
    int _inputMode {}, _dpi {}, _color {}, _pulseProperties {}, _maxFPS {}, _contextPosition {};
    float _alpha {};
    bool _wantsKeyboardFocus {}, _useBackground {};
    TransformBoundary _renderTransform;
    std::vector<QMetaObject::Connection> _connections;
    static QSharedPointer<OffscreenQmlSurface> nextSurface;
    static const char* URL_PROPERTY;
    static const char* SCRIPT_URL_PROPERTY;
    static const char* USE_BACKGROUND_PROPERTY;
    static const char* USER_AGENT_PROPERTY;
    static const char* GLOBAL_POSITION_PROPERTY;
    static ContentType getContentType(const QString&);
    static void acquireWebSurface(const QString&, bool, QSharedPointer<OffscreenQmlSurface>& surface, bool& cached) {
        assert(nextSurface); surface = nextSurface; cached = true;
    }
    static void releaseWebSurface(QSharedPointer<OffscreenQmlSurface>& surface, bool& cached,
                                 std::vector<QMetaObject::Connection>& connections) {
        for (const auto& connection : connections) QObject::disconnect(connection);
        connections.clear(); surface.reset(); cached = false;
    }
    template<class F> void withWriteLock(F body) {
        assert(QThread::currentThread() == thread()); body(); // Scene lock boundary.
    }
    template<class F> void withReadLock(F body) {
        assert(QThread::currentThread() == thread()); body();
    }
    glm::vec2 getWindowSize(const TypedEntityPointer&) const { return {}; }
    TransformBoundary getModelTransform() const { return {}; }
    void doRenderUpdateSynchronousTyped(const ScenePointer&, Transaction&, const TypedEntityPointer&);
    void buildWebSurface(const EntityItemPointer&, const QString&);
    void destroyWebSurface();
    void synchronizeWebVisibility(bool);
    ~WebEntityRenderer() { destroyWebSurface(); }
signals:
    void scriptEventReceived(const QVariant&);
    void webEventReceived(const QVariant&);
    void requestRenderUpdate();
};
QSharedPointer<OffscreenQmlSurface> WebEntityRenderer::nextSurface;
const char* WebEntityRenderer::URL_PROPERTY = "url";
const char* WebEntityRenderer::SCRIPT_URL_PROPERTY = "scriptURL";
const char* WebEntityRenderer::USE_BACKGROUND_PROPERTY = "useBackground";
const char* WebEntityRenderer::USER_AGENT_PROPERTY = "userAgent";
const char* WebEntityRenderer::GLOBAL_POSITION_PROPERTY = "globalPosition";
#include "web-entity-visibility-test.moc"
#include "production-visibility-methods.inc"

static auto makeSurface(bool createRoot = true) {
    auto surface = QSharedPointer<OffscreenQmlSurface>::create();
    if (createRoot) surface->createRoot();
    WebEntityRenderer::nextSurface = surface;
    return surface;
}
static void update(WebEntityRenderer& renderer, const EntityItemPointer& entity) {
    Transaction transaction;
    renderer.doRenderUpdateSynchronousTyped(nullptr, transaction, entity);
}

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    {
        auto surface = makeSurface();
        auto entity = EntityItemPointer::create(); entity->visible = false;
        WebEntityRenderer renderer;
        renderer.buildWebSurface(entity, entity->url);
        assert(!surface->root->isVisible() && !surface->document->isVisible());
        assert(!surface->document->session.active());
        entity->visible = true; update(renderer, entity);
        auto grant = surface->document->session.generation();
        assert(surface->root->isVisible() && surface->document->session.active());
        assert(surface->document->session.allowsBridge(grant, DOCUMENT, true, 10));
        entity->visible = false; update(renderer, entity);
        assert(!surface->document->session.active());
        entity->visible = true; update(renderer, entity);
        assert(surface->document->session.active());
        assert(!surface->document->session.allowsBridge(grant, DOCUMENT, true, 10));
    }
    {
        auto surface = makeSurface(false);
        auto entity = EntityItemPointer::create();
        WebEntityRenderer renderer; renderer.buildWebSurface(entity, entity->url);
        surface->createRoot(); // Real queued root-creation signal.
        entity->visible = false; update(renderer, entity);
        QCoreApplication::processEvents();
        assert(!surface->root->isVisible() && !surface->document->session.active());
    }
    {
        auto surface = makeSurface(false);
        auto oldEntity = EntityItemPointer::create(); oldEntity->visible = false;
        auto newEntity = EntityItemPointer::create();
        WebEntityRenderer oldOwner; oldOwner.buildWebSurface(oldEntity, oldEntity->url);
        surface->createRoot(); // Old callback is queued before disconnect/cache return.
        oldOwner.destroyWebSurface();
        WebEntityRenderer newOwner; newOwner.buildWebSurface(newEntity, newEntity->url);
        const auto grant = surface->document->session.generation();
        QCoreApplication::processEvents();
        assert(surface->root->isVisible() && surface->document->session.active());
        assert(surface->document->session.allowsBridge(grant, DOCUMENT, true, 10));
        // Reuse by the same renderer establishes a fresh lease as well.
        newOwner.destroyWebSurface(); newEntity->visible = false;
        newOwner.buildWebSurface(newEntity, newEntity->url); QCoreApplication::processEvents();
        assert(!surface->root->isVisible() && !surface->document->session.active());
        // Hidden surfaces can expire. A subsequent visible entity update with
        // the same source URL must acquire and activate its current surface.
        newOwner.destroyWebSurface(); newEntity->visible = true;
        auto restored = makeSurface(); update(newOwner, newEntity);
        assert(newOwner._webSurface == restored && restored->root->isVisible());
        assert(restored->document->session.active());
    }
    {
        auto surface = makeSurface(false);
        auto entity = EntityItemPointer::create(); entity->visible = false;
        auto* destroyed = new WebEntityRenderer; destroyed->buildWebSurface(entity, entity->url);
        surface->createRoot(); delete destroyed;
        WebEntityRenderer owner; entity->visible = true; owner.buildWebSurface(entity, entity->url);
        QCoreApplication::processEvents();
        assert(surface->root->isVisible() && surface->document->session.active());
        // Full production URL/content-type replacement must preserve Entity.visible.
        auto replacement = makeSurface(); entity->visible = false; entity->url = "qrc:/world.qml";
        update(owner, entity); QCoreApplication::processEvents();
        assert(owner._webSurface == replacement && !replacement->root->isVisible());
        assert(!replacement->document->session.active());
    }
    WebEntityRenderer::nextSurface.reset(); // All Qt windows precede QApplication teardown.
    assert(_currentWebCount == 0);
    std::cout << "PASS actual Entity.visible, Qt descendants/native policy, late root, cache reuse, deletion and source replacement\n";
}
