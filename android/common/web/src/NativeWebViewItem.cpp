// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#include "NativeWebViewItem.h"
#include <QCoreApplication>
#include <QFile>
#include <QFocusEvent>
#include <QHash>
#include <QInputMethod>
#include <QInputMethodEvent>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QKeyEvent>
#include <QJSEngine>
#include <QMimeDatabase>
#include <QMouseEvent>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QQmlContext>
#include <QQuickWindow>
#include <QSGSimpleTextureNode>
#include <QTimer>
#include <QWheelEvent>
#include <QtQml>
#include <jni.h>
#include <atomic>
#include <limits>

namespace {
QMutex registryMutex;
QHash<jlong, NativeWebViewItem*> registry;
jlong nextHandle { 1 };
QStringList packagedRoots;
std::atomic<bool> foreground { false };
std::atomic<JavaVM*> vm { nullptr };
std::atomic<jclass> backend { nullptr };
struct Jni {
    JNIEnv* env { nullptr }; bool attached { false };
    Jni() { auto* machine = vm.load(); if (!machine) return;
        if (machine->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
            #if defined(Q_OS_ANDROID)
            attached = machine->AttachCurrentThread(&env, nullptr) == JNI_OK;
#else
            attached = machine->AttachCurrentThread(reinterpret_cast<void**>(&env), nullptr) == JNI_OK;
#endif
        }
    }
    ~Jni() { if (attached && vm.load()) vm.load()->DetachCurrentThread(); }
    jstring string(const QString& value) const {
        return env ? env->NewString(reinterpret_cast<const jchar*>(value.utf16()), value.size()) : nullptr;
    }
};
QString string(JNIEnv* env, jstring value) {
    if (!value) return {};
    const auto* text = env->GetStringChars(value, nullptr);
    if (!text) return {};
    QString result = QString::fromUtf16(reinterpret_cast<const ushort*>(text), env->GetStringLength(value));
    env->ReleaseStringChars(value, text); return result;
}
bool call(const char* method, const char* signature, jvalue* args) {
    Jni jni; if (!jni.env || !backend.load()) return false;
    auto id = jni.env->GetStaticMethodID(backend.load(), method, signature);
    if (id) jni.env->CallStaticVoidMethodA(backend.load(), id, args);
    bool valid = id && !jni.env->ExceptionCheck();
    if (jni.env->ExceptionCheck()) jni.env->ExceptionClear();
    return valid;
}
QString resourceText(const QString& path) { QFile file(path); return file.open(QFile::ReadOnly) ? QString::fromUtf8(file.readAll()) : QString(); }
void registerType() { qmlRegisterType<NativeWebViewItem>("Overte.Android", 1, 0, "NativeWebView"); }
}
Q_COREAPP_STARTUP_FUNCTION(registerType)

NativeWebViewItem::NativeWebViewItem(QQuickItem* parent) : QQuickItem(parent),
    _transport(new NativeWebTransport(this)), _bridge(new NativeSurfaceBridge(this)), _channel(new QWebChannel(this)) {
    { QMutexLocker guard(&registryMutex);
      if (nextHandle > 0) { _handle = nextHandle; nextHandle = nextHandle == std::numeric_limits<jlong>::max() ? 0 : nextHandle + 1; registry.insert(_handle, this); } }
    _session.setForeground(foreground.load());
    setFlag(ItemHasContents, true); setFlag(ItemAcceptsInputMethod, true); setAcceptedMouseButtons(Qt::LeftButton); setAcceptHoverEvents(true);
    _channel->registerObject("eventBridge", _bridge);
    _channel->registerObject("eventBridgeWrapper", new NativeBridgeWrapper(_bridge, this));
    _channel->connectTo(_transport);
    connect(_bridge, &NativeSurfaceBridge::webEvent, this, &NativeWebViewItem::webEventReceived);
    connect(_transport, &NativeWebTransport::outbound, this, [this](const QJsonObject& message) {
        quint64 grant, page; { QMutexLocker guard(&_mutex); grant = _session.generation(); page = _page; }
        const auto payload = QJsonDocument(message).toJson(QJsonDocument::Compact);
        { QMutexLocker guard(&_mutex); if (!_session.allowsBridge(grant, sourceURL(_document), true, payload.size())) return; }
        const auto data = QString::fromUtf8(QJsonDocument(QJsonArray { QString::number(grant), QString::number(page), message }).toJson(QJsonDocument::Compact));
        evaluate("window.__overteTransport&&window.__overteTransport.receive.apply(null," + data + ");", grant, page);
    });
    connect(this, &QQuickItem::visibleChanged, this, &NativeWebViewItem::synchronizeVisibility);
    connect(this, &QQuickItem::enabledChanged, this, &NativeWebViewItem::synchronizeVisibility);
    connect(this, &QQuickItem::xChanged, this, &NativeWebViewItem::updateGeometry);
    connect(this, &QQuickItem::yChanged, this, &NativeWebViewItem::updateGeometry);
    connect(this, &QQuickItem::scaleChanged, this, &NativeWebViewItem::updateGeometry);
    connect(this, &QQuickItem::rotationChanged, this, &NativeWebViewItem::updateGeometry);
    connect(this, &QQuickItem::transformOriginChanged, this, &NativeWebViewItem::updateGeometry);
    connect(this, &QQuickItem::parentChanged, this, &NativeWebViewItem::trackGeometry);
    trackGeometry();
}
NativeWebViewItem::~NativeWebViewItem() {
    { QMutexLocker guard(&registryMutex); registry.remove(_handle); }
    { QMutexLocker guard(&_mutex); _session.close(); }
    jvalue args[1]; args[0].j = _handle; call("destroy", "(J)V", args);
}
void NativeWebViewItem::setPackagedResourceRoots(const QStringList& roots) { QMutexLocker guard(&registryMutex); packagedRoots = roots; }
void NativeWebViewItem::setUrl(const QString& value) { if (_url == value) return; _url = value; emit urlChanged(); navigate(); }
void NativeWebViewItem::setScriptUrl(const QString& value) {
    if (_scriptUrl == value) return; _scriptUrl = value; ++_scriptVersion; _injectedPage = 0; emit scriptUrlChanged();
    quint64 grant, page; { QMutexLocker guard(&_mutex); grant = _session.generation(); page = _page; }
    if (!_loading) injectUserScript(grant, page, QUrl(value));
}
void NativeWebViewItem::setSourceIdentity(const QString& value) { if (_sourceIdentity == value) return; _sourceIdentity = value; emit sourceIdentityChanged(); navigate(); }
void NativeWebViewItem::setSurface(Surface value) { if (_surface == value) return; _surface = value; emit surfaceChanged(); navigate(); }
void NativeWebViewItem::setPresentation(Presentation value) { if (_presentation == value) return; _presentation = value; emit presentationChanged();
    if (_created) { jvalue args[1]; args[0].j = _handle; call("destroy", "(J)V", args); _created = false; } navigate(); }
void NativeWebViewItem::setUseBackground(bool value) { if (_background == value) return; _background = value; emit useBackgroundChanged();
    if (_created) { jvalue args[2]; args[0].j = _handle; args[1].z = value; call("background", "(JZ)V", args); } }
void NativeWebViewItem::setUserAgent(const QString& value) { if (_userAgent == value) return; _userAgent = value; emit userAgentChanged();
    if (_created) { Jni jni; if (!jni.env) return; jstring text = jni.string(value); jvalue args[2]; args[0].j = _handle; args[1].l = text;
        call("userAgent", "(JLjava/lang/String;)V", args); jni.env->DeleteLocalRef(text); } }
void NativeWebViewItem::componentComplete() {
    QQuickItem::componentComplete();
    if (auto* context = qmlContext(this)) {
        if (_bootstrap.isEmpty()) _bootstrap = context->contextProperty("eventBridgeJavaScriptToInject").toString();

    }
    navigate();
}
QString NativeWebViewItem::scriptRoot(const QUrl& source) const {
    QMutexLocker guard(&registryMutex);
    for (const auto& root : packagedRoots) if (overte::web::EmbeddedWebSession::isPackagedURL(source, root)) return root;
    return {};
}
void NativeWebViewItem::navigate() {
    if (!isComponentComplete()) return;
    _callbacks.clear(); resetEditor();
    if (_created || _pending) { jvalue a[1]; a[0].j = _handle; call("revoke", "(J)V", a); }
    _resumeDocument = QUrl();
    if (_suspendedDocument) { { QMutexLocker guard(&_mutex); _suspendedDocument = false; } _created = false; jvalue a[1]; a[0].j = _handle; call("destroy", "(J)V", a); }
    QUrl source(_url); const auto root = scriptRoot(source); QUrl browser;
    { QMutexLocker guard(&_mutex);
      _mapping = overte::android::web::NativeResourceMapping(root, _handle);
      source = _mapping.canonicalSource(source);
      _tabletGrant = _surface == Tablet;
      _session.open(source, _surface == Tablet ? overte::web::Surface::Tablet : overte::web::Surface::WorldEntity, _sourceIdentity, root);
      _session.setVisible(isVisible() && isEnabled()); _page = 0; _document = QUrl(); browser = _mapping.toBrowser(source); }
    const bool authorized = !_sourceIdentity.trimmed().isEmpty() &&
        (overte::web::EmbeddedWebSession::isNetworkURL(source) || overte::web::EmbeddedWebSession::isPackagedURL(source, root));
    _sourceAuthorized = authorized;
    if (!authorized) {
        _status = 6; { QMutexLocker guard(&_mutex); _image = QImage(); } update(); emit stateChanged();
        if (_created) {
            Jni jni; if (jni.env) { jstring blank = jni.string("about:blank"); jvalue args[3]; args[0].j = _handle; args[1].j = 0; args[2].l = blank;
                call("load", "(JJLjava/lang/String;)V", args); jni.env->DeleteLocalRef(blank); }
        }
        return;
    }
    if (!generation()) { retryCreation(); return; }
    if (!_created) { _attempts = 0; create(); return; }
    Jni jni; if (!jni.env) return; jstring url = jni.string(browser.toString(QUrl::FullyEncoded));
    jvalue args[3]; args[0].j = _handle; args[1].j = generation(); args[2].l = url;
    call("load", "(JJLjava/lang/String;)V", args); jni.env->DeleteLocalRef(url);
}
void NativeWebViewItem::create() {
    if (_suspendedDocument || !_handle || !isComponentComplete() || _created || _pending || width() <= 1 || height() <= 1 || !isVisible() || !isEnabled()) return;
    Jni jni; if (!jni.env || !backend.load() || !generation()) { retryCreation(); return; }
    QUrl source; { QMutexLocker guard(&_mutex); source = _session.url(); }
    const QString root = scriptRoot(source);
    QUrl browser; { QMutexLocker guard(&_mutex);
        // Each new WebView has a fresh source revision even if its URL is unchanged.
        _session.open(source, _surface == Tablet ? overte::web::Surface::Tablet : overte::web::Surface::WorldEntity, _sourceIdentity, root);
        _page = 0; _document = QUrl();
        browser = _resumeDocument.isEmpty() ? _mapping.toBrowser(source) : _resumeDocument;
    }
    const QString script = resourceText(":/overte/android/web/resources/transport.js") + '\n' + _bootstrap;
    const QString editorScript = resourceText(":/overte/android/web/resources/editor-transport.js") + '\n' + resourceText(":/overte/android/web/resources/editor.js");
    jstring url = jni.string(browser.toString(QUrl::FullyEncoded)), agent = jni.string(_userAgent), bootstrap = jni.string(script);
    if (!url || !agent || !bootstrap) { if (jni.env->ExceptionCheck()) jni.env->ExceptionClear(); retryCreation(); return; }
    jstring editorBootstrap = jni.string(editorScript);
    if (!editorBootstrap) { if (jni.env->ExceptionCheck()) jni.env->ExceptionClear(); jni.env->DeleteLocalRef(url); jni.env->DeleteLocalRef(agent); jni.env->DeleteLocalRef(bootstrap); retryCreation(); return; }
    const auto bounds = sceneBounds().toAlignedRect(), clip = sceneClipBounds().toAlignedRect(); jvalue args[16]; args[0].j = _handle; args[1].j = generation();
    _creationRevision = args[1].j; _creationIdentity = _sourceIdentity;
    _creationSurface = _surface; _creationPresentation = _presentation;
    { QMutexLocker guard(&_mutex); _creationSource = _session.url(); } args[2].l = url; args[3].l = agent;
    args[4].z = _background; args[5].z = _presentation == NativeOverlay; args[6].i = bounds.x(); args[7].i = bounds.y();
    args[8].i = bounds.width(); args[9].i = bounds.height();
    args[10].i = clip.x(); args[11].i = clip.y(); args[12].i = clip.width(); args[13].i = clip.height(); args[14].l = bootstrap;
    args[15].l = editorBootstrap;
    _pending = call("create", "(JJLjava/lang/String;Ljava/lang/String;ZZIIIIIIIILjava/lang/String;Ljava/lang/String;)V", args);
    jni.env->DeleteLocalRef(editorBootstrap);
    jni.env->DeleteLocalRef(url); jni.env->DeleteLocalRef(agent); jni.env->DeleteLocalRef(bootstrap);
    if (!_pending) retryCreation();
}
void NativeWebViewItem::retryCreation() { if (_retryPending) return; if (++_attempts > 30) { _status = 3; emit stateChanged(); return; } _retryPending = true;
    QTimer::singleShot(250, this, [this] { _retryPending = false; create(); }); }
quint64 NativeWebViewItem::generation() const { QMutexLocker guard(&_mutex); const auto value = _session.generation();
    return _session.active() && value <= static_cast<quint64>(std::numeric_limits<jlong>::max()) ? value : 0; }
quint64 NativeWebViewItem::lifecycleRevision() const { QMutexLocker guard(&_mutex);
    const auto value = _session.generation(); return value <= quint64(std::numeric_limits<jlong>::max()) ? value : 0; }
bool NativeWebViewItem::current(quint64 grant, quint64 page) const { return !_suspendedDocument && _session.active() && grant && grant == _session.generation() && page && page == _page; }
QUrl NativeWebViewItem::sourceURL(const QUrl& browser) const { return _mapping.toSource(browser); }
bool NativeWebViewItem::allowsNavigation(quint64 grant, const QUrl& target, bool mainFrame, const QString& method) const {
    QMutexLocker guard(&_mutex); return _session.allowsNavigation(grant, sourceURL(target), mainFrame, method);
}
bool NativeWebViewItem::allowsBridgeDocument(quint64 grant, quint64 page, const QUrl& document) const {
    QMutexLocker guard(&_mutex);
    return current(grant, page) && sourceURL(document) == sourceURL(_document)
        && _session.allowsBridge(grant, sourceURL(document), true, 1);
}
bool NativeWebViewItem::allowsEditorDocument(quint64 grant, quint64 page, const QUrl& document) const {
    QMutexLocker guard(&_mutex);
    return current(grant, page) && document.adjusted(QUrl::RemoveFragment) == _document.adjusted(QUrl::RemoveFragment)
        && _session.allowsNavigation(grant, sourceURL(document), true, "GET");
}
bool NativeWebViewItem::allowsFileChooser(quint64 grant, quint64 page, const QUrl& document) const {
    QMutexLocker guard(&_mutex);
    return _tabletGrant && current(grant, page) && sourceURL(document) == sourceURL(_document)
        && _session.allowsNavigation(grant, sourceURL(document), true, "GET");
}
void NativeWebViewItem::acceptPage(quint64 grant, quint64 page, const QUrl& document) {
    QMutexLocker guard(&_mutex);
    if (!_session.allowsNavigation(grant, sourceURL(document), true, "GET") || !page || page <= _page) return;
    _page = page; _document = document;
    QMetaObject::invokeMethod(this, [this] { _callbacks.clear(); resetEditor();
        if (auto* input = QGuiApplication::inputMethod()) input->update(Qt::ImQueryInput); }, Qt::QueuedConnection);
}
bool NativeWebViewItem::acceptMessage(quint64 grant, quint64 page, const QUrl& document, const QUrl& origin,
                                     bool mainFrame, const QString& type, const QByteArray& payload) {
    { QMutexLocker guard(&_mutex);
      if (!current(grant, page) || !mainFrame || payload.isEmpty() || payload.size() > int(overte::web::EmbeddedWebSession::MAX_BRIDGE_BYTES)
          || !overte::web::EmbeddedWebSession::sameOrigin(document, origin)
          || (type == "channel" ? !_session.allowsBridge(grant, sourceURL(document), mainFrame, payload.size())
                                : !_session.allowsNavigation(grant, sourceURL(document), true, "GET"))
          || document.adjusted(QUrl::RemoveFragment) != _document.adjusted(QUrl::RemoveFragment)
          || (type != "channel" && type != "editor")) return false; }
    const auto parsed = QJsonDocument::fromJson(payload); if (!parsed.isObject()) return false;
    if (type == "channel") {
        const auto object = parsed.object(); const int messageType = object.value("type").toInt(-1);
        if (messageType == 6) {
            const auto method = object.value("method");
            const int allowed = _bridge->metaObject()->indexOfMethod("emitWebEvent(QVariant)");
            if (object.value("object").toString() != "eventBridge" || object.value("args").toArray().size() != 1
                || !((method.isDouble() && method.toInt(-1) == allowed) || (method.isString() && method.toString() == "emitWebEvent"))) return false;
        } else if (messageType == 7 || messageType == 8) {
            if (object.value("object").toString() != "eventBridge"
                || object.value("signal").toInt(-1) != _bridge->metaObject()->indexOfSignal("scriptEventReceived(QVariant)")) return false;
        } else if (messageType != 3 && messageType != 4) return false;
    }
    QPointer<NativeWebViewItem> self(this); QMetaObject::invokeMethod(this, [self, grant, page, document, type, object = parsed.object()] {
        if (!self) return;
        if (type == "editor" ? !self->allowsEditorDocument(grant, page, document) : !self->allowsBridgeDocument(grant, page, document)) return;
        if (type == "channel") self->_transport->receive(object); else self->updateEditor(object);
    }, Qt::QueuedConnection); return true;
}
void NativeWebViewItem::acceptState(quint64 grant, quint64 page, const QUrl& document, bool loading, bool back, bool forward, bool bridge, int status) {
    QPointer<NativeWebViewItem> self(this); QMetaObject::invokeMethod(this, [self, grant, page, document, loading, back, forward, bridge, status] {
        if (!self) return;
        { QMutexLocker guard(&self->_mutex); if (!self->current(grant, page)) return;
          self->_document = document; self->_currentUrl = self->sourceURL(document).toString();
          self->_bridgeAvailable = bridge && self->_session.allowsBridge(grant, self->sourceURL(document), true, 1); }
        self->_loading = loading; self->_canGoBack = back; self->_canGoForward = forward; self->_status = status;
        if (bridge && !self->_bridgeAvailable) self->_status = 9;
        emit self->stateChanged();
        if (!loading && self->_injectedPage != page) { self->_injectedPage = page; self->injectUserScript(grant, page, QUrl(self->_scriptUrl)); }
    }, Qt::QueuedConnection);
}
void NativeWebViewItem::acceptFrame(quint64 grant, quint64 page, const void* pixels, qsizetype bytes, int width, int height) {
    if (!pixels || width <= 0 || height <= 0 || width > 2048 || height > 2048 || bytes < qsizetype(width) * height * 4) return;
    { QMutexLocker guard(&_mutex); if (!current(grant, page)) return; _image = QImage(static_cast<const uchar*>(pixels), width, height, QImage::Format_ARGB32_Premultiplied).copy(); }
    QMetaObject::invokeMethod(this, [this] { update(); }, Qt::QueuedConnection);
}
void NativeWebViewItem::acceptCreated(bool created, quint64 revision) {
    QPointer<NativeWebViewItem> self(this); QMetaObject::invokeMethod(this, [self, created, revision] {
        if (!self || revision != self->_creationRevision) return;
        self->_pending = false;
        bool sameSource; { QMutexLocker guard(&self->_mutex);
            sameSource = self->_creationSource == self->_session.url() && self->_creationIdentity == self->_sourceIdentity
                && self->_creationSurface == self->_surface && self->_creationPresentation == self->_presentation; }
        if (!sameSource) {
            self->_created = false;
            { QMutexLocker guard(&self->_mutex); self->_suspendedDocument = false; }
            jvalue args[2]; args[0].j = self->_handle; args[1].j = revision; call("destroyExpected", "(JJ)V", args);
            if (self->generation()) self->create();
            return;
        }
        self->_created = created;
        if (created) { self->_injectedPage = 0; self->_attempts = 0; self->updateGeometry(); self->synchronizeVisibility(); self->_resumeDocument = QUrl(); }
        else if (!self->_suspendedDocument && self->generation()) self->retryCreation();
        if (!created) { self->_canGoBack = false; self->_canGoForward = false; }
    }, Qt::QueuedConnection);
}
void NativeWebViewItem::acceptSuspended(quint64 revision, const QUrl& document, bool back, bool forward, quint64 birth) {
    QPointer<NativeWebViewItem> self(this); QMetaObject::invokeMethod(this, [self, revision, document, back, forward, birth] {
        if (!self || birth != self->_creationRevision || !self->_sourceAuthorized || self->lifecycleRevision() != revision) return;
        { QMutexLocker guard(&self->_mutex); self->_suspendedDocument = true; } self->_loading = false; self->_bridgeAvailable = false;
        self->_currentUrl = document.toString(); self->_canGoBack = back; self->_canGoForward = forward;
        self->_status = 10; self->_callbacks.clear(); self->resetEditor();
        { QMutexLocker guard(&self->_mutex); self->_image = QImage(); }
        self->update(); emit self->stateChanged();
    }, Qt::QueuedConnection);
}
void NativeWebViewItem::requestResume(quint64 revision, const QUrl& document, quint64 birth) {
    QPointer<NativeWebViewItem> self(this); QMetaObject::invokeMethod(this, [self, revision, document, birth] {
        if (!self || birth != self->_creationRevision || !self->_suspendedDocument || self->lifecycleRevision() != revision || !self->generation()
            || !self->allowsNavigation(revision, document, true, "GET")) return;
        QUrl source; { QMutexLocker guard(&self->_mutex); source = self->_session.url(); }
        const QString root = self->scriptRoot(source);
        { QMutexLocker guard(&self->_mutex);
            self->_session.open(source, self->_surface == Tablet ? overte::web::Surface::Tablet : overte::web::Surface::WorldEntity, self->_sourceIdentity, root);
            self->_page = 0; self->_document = QUrl(); self->_suspendedDocument = false;
        }
        self->_callbacks.clear(); self->_resumeDocument = document; self->_created = false;
        self->create();
    }, Qt::QueuedConnection);
}
void NativeWebViewItem::acceptForeground(bool active) {
    { QMutexLocker guard(&_mutex); _session.setForeground(active); }
    if (!active) QMetaObject::invokeMethod(this, [this] { _callbacks.clear(); _bridgeAvailable = false; _loading = false; emit stateChanged(); resetEditor();
        if (auto* input = QGuiApplication::inputMethod()) { input->update(Qt::ImQueryInput); input->hide(); } }, Qt::QueuedConnection);
    if (active) QMetaObject::invokeMethod(this, [this] { if (!_created) create(); }, Qt::QueuedConnection);
}
QByteArray NativeWebViewItem::resource(quint64 grant, const QUrl& browser) const {
    QUrl source; { QMutexLocker guard(&_mutex); source = sourceURL(browser);
      if (!_session.allowsNavigation(grant, source, false, "GET") || !_mapping.accepts(source)) return {}; }
    QFile file(source.scheme() == "qrc" ? ':' + source.path() : source.toLocalFile());
    if (!file.open(QFile::ReadOnly) || file.size() > 8 * 1024 * 1024) return {};
    return file.readAll();
}
QString NativeWebViewItem::resourceMime(quint64 grant, const QUrl& browser) const {
    QMutexLocker guard(&_mutex); const auto source = sourceURL(browser);
    if (!_session.allowsNavigation(grant, source, false, "GET") || !_mapping.accepts(source)) return "text/plain";
    return QMimeDatabase().mimeTypeForFile(source.path(), QMimeDatabase::MatchExtension).name();
}
void NativeWebViewItem::synchronizeVisibility() {
    quint64 grant; { QMutexLocker guard(&_mutex); _session.setVisible(isVisible() && isEnabled()); grant = _session.generation(); }
    if (!isVisible() || !isEnabled()) { _callbacks.clear(); _bridgeAvailable = false; resetEditor(); emit stateChanged(); }
    if (!_created) { create(); return; } jvalue args[3]; args[0].j = _handle; args[1].j = grant; args[2].z = isVisible() && isEnabled();
    call("visibility", "(JJZ)V", args);
}
void NativeWebViewItem::trackGeometry() {
    for (const auto& connection : _geometryConnections) disconnect(connection); _geometryConnections.clear();
    for (auto* ancestor = parentItem(); ancestor; ancestor = ancestor->parentItem()) {
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::xChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::yChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::scaleChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::rotationChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::widthChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::heightChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::clipChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::transformOriginChanged, this, &NativeWebViewItem::updateGeometry));
        _geometryConnections.push_back(connect(ancestor, &QQuickItem::parentChanged, this, &NativeWebViewItem::trackGeometry));
    }
    updateGeometry();
}
QRectF NativeWebViewItem::sceneClipBounds() const {
    auto bounds = sceneBounds();
    for (auto* ancestor = parentItem(); ancestor; ancestor = ancestor->parentItem()) {
        if (ancestor->clip()) bounds = bounds.intersected(ancestor->mapRectToScene(ancestor->boundingRect()));
    }
    return bounds;
}
void NativeWebViewItem::updateGeometry() { if (!_created) { create(); return; }
    const auto bounds = sceneBounds().toAlignedRect(), clip = sceneClipBounds().toAlignedRect();
    jvalue args[9]; args[0].j = _handle; args[1].i = bounds.x(); args[2].i = bounds.y(); args[3].i = bounds.width(); args[4].i = bounds.height();
    args[5].i = clip.x(); args[6].i = clip.y(); args[7].i = clip.width(); args[8].i = clip.height();
    call("resize", "(JIIIIIIII)V", args); }
void NativeWebViewItem::geometryChanged(const QRectF& geometry, const QRectF& old) { QQuickItem::geometryChanged(geometry, old); updateGeometry(); }
QSGNode* NativeWebViewItem::updatePaintNode(QSGNode* old, UpdatePaintNodeData*) {
    auto* node = static_cast<QSGSimpleTextureNode*>(old); if (_presentation == NativeOverlay) { delete node; return nullptr; }
    QImage frame; { QMutexLocker guard(&_mutex); frame = _image; } if (frame.isNull() || !window()) return node;
    if (!node) node = new QSGSimpleTextureNode;
    auto* previous = node->texture(); node->setOwnsTexture(false); node->setTexture(window()->createTextureFromImage(frame)); node->setOwnsTexture(true); delete previous; node->setRect(boundingRect()); return node;
}
bool NativeWebViewItem::evaluate(const QString& script, quint64 grant, quint64 page) {
    { QMutexLocker guard(&_mutex); if (!current(grant, page) || !_session.allowsBridge(grant, sourceURL(_document), true, 1)) return false; }
    Jni jni; if (!jni.env || !backend.load()) return false; auto text = jni.string(script);
    if (!text) { if (jni.env->ExceptionCheck()) jni.env->ExceptionClear(); return false; } jvalue args[4]; args[0].j = _handle; args[1].j = grant; args[2].j = page; args[3].l = text;
    const auto posted = call("evaluate", "(JJJLjava/lang/String;)V", args); jni.env->DeleteLocalRef(text); return posted;
}
bool NativeWebViewItem::emitScriptEvent(const QVariant& message) {
    const auto bytes = QJsonDocument(QJsonArray { QJsonValue::fromVariant(message) }).toJson(QJsonDocument::Compact).size();
    { QMutexLocker guard(&_mutex); if (!_session.allowsBridge(_session.generation(), sourceURL(_document), true, bytes)) return false; }
    _bridge->forwardScriptEvent(message); return true;
}
bool NativeWebViewItem::runJavaScript(const QString& source, const QJSValue& callback) {
    quint64 grant, page; { QMutexLocker guard(&_mutex); grant = _session.generation(); page = _page;
        if (!current(grant, page) || !_session.allowsBridge(grant, sourceURL(_document), true, 1)) return false; }
    if (source.toUtf8().size() > 1024 * 1024 || _callbacks.size() >= 32 || !_nextRequest) return false;
    if (!callback.isCallable()) return evaluate(source, grant, page);
    Jni jni; if (!jni.env || !backend.load()) return false;
    const auto request = _nextRequest; _nextRequest = request == quint64(std::numeric_limits<jlong>::max()) ? 0 : request + 1;
    auto text = jni.string(source); if (!text) { if (jni.env->ExceptionCheck()) jni.env->ExceptionClear(); return false; }
    jvalue args[5]; args[0].j = _handle; args[1].j = grant; args[2].j = page; args[3].j = request; args[4].l = text;
    _callbacks.insert(request, callback); const bool posted = call("evaluateResult", "(JJJJLjava/lang/String;)V", args); jni.env->DeleteLocalRef(text);
    if (!posted) { _callbacks.remove(request); return false; }
    QTimer::singleShot(10000, this, [this, grant, page, request] {
        auto expired = _callbacks.take(request);
        { QMutexLocker guard(&_mutex); if (!current(grant, page)) return; }
        if (expired.isCallable()) expired.call({ QJSValue(QJSValue::UndefinedValue) });
    }); return true;
}
void NativeWebViewItem::acceptResult(quint64 grant, quint64 page, quint64 request, const QByteArray& json) {
    if (json.size() > int(overte::web::EmbeddedWebSession::MAX_BRIDGE_BYTES)) return;
    QPointer<NativeWebViewItem> self(this); QMetaObject::invokeMethod(this, [self, grant, page, request, json] {
        if (!self) return; { QMutexLocker guard(&self->_mutex); if (!self->current(grant, page)) return; }
        auto callback = self->_callbacks.take(request); if (!callback.isCallable()) return;
        const auto parsed = QJsonDocument::fromJson('[' + json + ']'); auto* engine = qjsEngine(self);
        QJSValue result(QJSValue::UndefinedValue);
        if (engine && parsed.isArray() && parsed.array().size() == 1) result = parsed.array()[0].isNull() ? QJSValue(QJSValue::NullValue) : engine->toScriptValue(parsed.array()[0].toVariant());
        callback.call({ result });
    }, Qt::QueuedConnection);
}
void NativeWebViewItem::stop() { jvalue args[1]; args[0].j = _handle; call("stop", "(J)V", args); }
void NativeWebViewItem::reload() { if (_suspendedDocument) { requestResume(lifecycleRevision(), QUrl(_currentUrl), _creationRevision); return; } jvalue args[1]; args[0].j = _handle; call("reload", "(J)V", args); }
void NativeWebViewItem::goForward() { jvalue args[1]; args[0].j = _handle; call("goForward", "(J)V", args); }
void NativeWebViewItem::reloadAndBypassCache() { if (_suspendedDocument) { reload(); return; } jvalue args[1]; args[0].j = _handle; call("reloadAndBypassCache", "(J)V", args); }
void NativeWebViewItem::unfocus() { setFocus(false); resetEditor(); jvalue args[2]; args[0].j = _handle; args[1].z = false; call("focus", "(JZ)V", args); }
void NativeWebViewItem::openNative() { jvalue args[1]; args[0].j = _handle; call("openNative", "(J)V", args); }
void NativeWebViewItem::goBack() { jvalue args[1]; args[0].j = _handle; call("goBack", "(J)V", args); }
void NativeWebViewItem::pointer(int action, const QPointF& position) {
    QPointF pixel = position; { QMutexLocker guard(&_mutex); if (!_image.isNull() && width() > 0 && height() > 0) pixel = QPointF(position.x() * _image.width()/width(), position.y() * _image.height()/height()); }
    jvalue args[4]; args[0].j = _handle; args[1].i = action; args[2].f = pixel.x(); args[3].f = pixel.y(); call("pointer", "(JIFF)V", args);
}
void NativeWebViewItem::mousePressEvent(QMouseEvent* event) { forceActiveFocus(Qt::MouseFocusReason); if (_pressed) pointer(3, {}); _pressed = true; pointer(0, event->localPos()); event->accept(); }
void NativeWebViewItem::mouseMoveEvent(QMouseEvent* event) { if (!_pressed) { event->ignore(); return; } pointer(2, event->localPos()); event->accept(); }
void NativeWebViewItem::mouseReleaseEvent(QMouseEvent* event) { if (!_pressed) { event->ignore(); return; } pointer(1, event->localPos()); _pressed = false; event->accept(); }
void NativeWebViewItem::mouseUngrabEvent() { if (_pressed) { pointer(3, {}); _pressed = false; } }
void NativeWebViewItem::hoverEnterEvent(QHoverEvent* event) { pointer(9, event->posF()); event->accept(); }
void NativeWebViewItem::hoverMoveEvent(QHoverEvent* event) { pointer(7, event->posF()); event->accept(); }
void NativeWebViewItem::hoverLeaveEvent(QHoverEvent* event) { pointer(10, event->posF()); event->accept(); }
void NativeWebViewItem::wheelEvent(QWheelEvent* event) {
    const auto dy = event->angleDelta().y(); runJavaScript(QStringLiteral("window.scrollBy(0,%1);").arg(-dy)); event->accept();
}
void NativeWebViewItem::editorCommand(const QJsonObject& command) { if (!_editorActive || !hasActiveFocus()) return;
    quint64 grant, page; QUrl document;
    { QMutexLocker guard(&_mutex); grant = _session.generation(); page = _page; document = _document; }
    if (!allowsEditorDocument(grant, page, document)) return;
    Jni jni; if (!jni.env || !backend.load()) return;
    jstring url = jni.string(document.toString(QUrl::FullyEncoded));
    jstring data = jni.string(QString::fromUtf8(QJsonDocument(command).toJson(QJsonDocument::Compact)));
    if (url && data) { jvalue args[5]; args[0].j = _handle; args[1].j = grant; args[2].j = page; args[3].l = url; args[4].l = data;
        call("edit", "(JJJLjava/lang/String;Ljava/lang/String;)V", args); }
    if (jni.env->ExceptionCheck()) jni.env->ExceptionClear();
    if (url) jni.env->DeleteLocalRef(url); if (data) jni.env->DeleteLocalRef(data);
}
void NativeWebViewItem::keyPressEvent(QKeyEvent* event) {
    if (!_editorActive || (event->modifiers() & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier))) { event->ignore(); return; }
    if (event->key() == Qt::Key_Backspace) editorCommand({{"action", "backspace"}});
    else if (event->key() == Qt::Key_Delete) editorCommand({{"action", "delete"}});
    else if (event->key() == Qt::Key_Left || event->key() == Qt::Key_Right || event->key() == Qt::Key_Home || event->key() == Qt::Key_End) {
        const auto action = event->key() == Qt::Key_Left ? "left" : event->key() == Qt::Key_Right ? "right" : event->key() == Qt::Key_Home ? "home" : "end";
        editorCommand({{"action", action}, {"extend", bool(event->modifiers() & Qt::ShiftModifier)}});
    }
    else if (!event->text().isEmpty()) editorCommand({{"text", event->text()}}); else { event->ignore(); return; }
    event->accept();
}
void NativeWebViewItem::inputMethodEvent(QInputMethodEvent* event) {
    if (!_editorActive || !hasActiveFocus() || event->commitString().size() > 16384 || event->preeditString().size() > 16384) { event->ignore(); return; }
    QJsonObject command {{"action", "ime"}, {"commit", event->commitString()}, {"preedit", event->preeditString()},
        {"replaceStart", event->replacementStart()}, {"replaceLength", event->replacementLength()}, {"cursor", event->preeditString().size()}};
    for (const auto& attribute : event->attributes()) {
        if (attribute.type == QInputMethodEvent::Cursor) command["cursor"] = qBound(0, attribute.start, event->preeditString().size());
        if (attribute.type == QInputMethodEvent::Selection) command["selection"] = QJsonObject {{"start", _surroundingStart + attribute.start}, {"length", attribute.length}};
    }
    editorCommand(command); event->accept();
}
void NativeWebViewItem::resetEditor() {
    const bool changed = _editorActive; _editorActive = false; _editorText.clear();
    if (changed) { emit editorStateChanged(); emit editorFocusChanged(false, false, false); }
}
void NativeWebViewItem::updateEditor(const QJsonObject& state) {
    const bool previousActive = editorFocused(), previousNumeric = editorNumeric(), previousPassword = editorPassword();
    _editorActive = state.value("active").toBool(); _sensitive = state.value("sensitive").toBool();
    _editorText = _sensitive ? QString() : state.value("text").toString().left(16384);
    _cursor = qBound(0, state.value("cursor").toInt(), _editorText.size()); _anchor = qBound(0, state.value("anchor").toInt(), _editorText.size());
    _surroundingStart = qMax(0, state.value("absoluteCursor").toInt() - state.value("cursor").toInt());
    _editorKind = state.value("kind").toString(); _cursorRect = QRectF(state.value("x").toDouble(), state.value("y").toDouble(), state.value("width").toDouble(), state.value("height").toDouble());
    if (previousActive != editorFocused() || previousNumeric != editorNumeric() || previousPassword != editorPassword()) {
        emit editorStateChanged(); emit editorFocusChanged(editorFocused(), editorNumeric(), editorPassword());
    }
    if (_presentation == NativeOverlay) return; // The native WebView owns its OS input connection.
    if (auto* input = QGuiApplication::inputMethod()) { input->update(Qt::ImQueryInput); if (_editorActive && hasActiveFocus()) input->show(); else input->hide(); }
}
QVariant NativeWebViewItem::inputMethodQuery(Qt::InputMethodQuery query) const {
    if (query == Qt::ImEnabled) return _presentation == Texture && generation() && _editorActive && isVisible() && isEnabled() && hasActiveFocus();
    if (query == Qt::ImSurroundingText) return _editorText;
    if (query == Qt::ImAbsolutePosition) return _surroundingStart + _cursor;
    if (query == Qt::ImTextBeforeCursor) return _editorText.left(_cursor);
    if (query == Qt::ImTextAfterCursor) return _editorText.mid(_cursor);
    if (query == Qt::ImCursorPosition) return _cursor;
    if (query == Qt::ImAnchorPosition) return _anchor;
    if (query == Qt::ImCurrentSelection) return _editorText.mid(qMin(_cursor, _anchor), qAbs(_cursor - _anchor));
    if (query == Qt::ImCursorRectangle) {
        if (_presentation == Texture && !_image.isNull()) {
            const auto x = width() / _image.width(), y = height() / _image.height();
            return QRectF(_cursorRect.x() * x, _cursorRect.y() * y, _cursorRect.width() * x, _cursorRect.height() * y);
        }
        return _cursorRect;
    }
    if (query == Qt::ImHints) return int(_sensitive ? Qt::ImhHiddenText | Qt::ImhSensitiveData | Qt::ImhNoPredictiveText :
        _editorKind == "number" ? Qt::ImhFormattedNumbersOnly : _editorKind == "tel" ? Qt::ImhDialableCharactersOnly :
        _editorKind == "email" ? Qt::ImhEmailCharactersOnly : _editorKind == "url" ? Qt::ImhUrlCharactersOnly : Qt::ImhNone);
    return QQuickItem::inputMethodQuery(query);
}
void NativeWebViewItem::focusInEvent(QFocusEvent* event) { QQuickItem::focusInEvent(event); jvalue args[2]; args[0].j = _handle; args[1].z = true; call("focus", "(JZ)V", args); }
void NativeWebViewItem::focusOutEvent(QFocusEvent* event) { resetEditor(); QQuickItem::focusOutEvent(event); jvalue args[2]; args[0].j = _handle; args[1].z = false; call("focus", "(JZ)V", args); }
QString NativeWebViewItem::errorText() const {
    return (_status == 2 || _status == 3 || _status == 4 || _status == 6) ? statusText() : QString();
}
QString NativeWebViewItem::warningText() const { return errorText().isEmpty() ? statusText() : QString(); }
QString NativeWebViewItem::statusText() const { switch (_status) {
    case 10: return tr("This page was closed to stop audio. Reload to continue with a new GET request; unsaved forms and running page state were lost.");
    case 1: return tr("This WebView provider cannot provide this page's Overte bridge. Update Android System WebView.");
    case 2: return tr("The page could not be loaded."); case 3: return tr("The WebView stopped. Reopen the page.");
    case 4: return tr("Native tablet presentation is unavailable on this client."); case 5: return tr("File selection is unavailable on this client.");
    case 9: return tr("This navigated page cannot access this surface’s Overte bridge.");
    case 8: return tr("An external browser is unavailable on this client.");
    case 6: return tr("This document has no authorized source or packaged resource root."); case 7: return tr("The page's script could not be loaded."); default: return {}; } }
void NativeWebViewItem::injectUserScript(quint64 grant, quint64 page, const QUrl& url, int redirects) {
    if (url.isEmpty()) return; QString root = scriptRoot(url);
    { QMutexLocker guard(&_mutex); if (!current(grant, page) || !_session.allowsBridge(grant, sourceURL(_document), true, 1) || !_session.allowsScriptURL(url, root)) return; }
    if (!root.isEmpty()) {
        QFile file(url.scheme() == "qrc" ? ':' + url.path() : url.toLocalFile());
        if (file.open(QFile::ReadOnly) && file.size() <= 1024 * 1024) evaluate(QString::fromUtf8(file.readAll()), grant, page);
        else { _status = 7; emit stateChanged(); } return;
    }
    if (redirects > 5) { _status = 7; emit stateChanged(); return; }
    auto* network = new QNetworkAccessManager(this); QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    auto* reply = network->get(request); auto* timeout = new QTimer(reply); timeout->setSingleShot(true); timeout->start(10000);
    connect(timeout, &QTimer::timeout, reply, &QNetworkReply::abort);
    connect(reply, &QIODevice::readyRead, reply, [reply] { if (reply->bytesAvailable() > 1024 * 1024) reply->abort(); });
    const auto revision = _scriptVersion;
    connect(reply, &QNetworkReply::finished, this, [this, grant, page, url, redirects, reply, network, revision] {
        { QMutexLocker guard(&_mutex); if (!current(grant, page) || revision != _scriptVersion) { reply->deleteLater(); network->deleteLater(); return; } }
        const auto redirect = reply->attribute(QNetworkRequest::RedirectionTargetAttribute).toUrl();
        if (!redirect.isEmpty()) injectUserScript(grant, page, url.resolved(redirect), redirects + 1);
        else if (reply->error() == QNetworkReply::NoError && reply->bytesAvailable() <= 1024 * 1024) evaluate(QString::fromUtf8(reply->readAll()), grant, page);
        else { _status = 7; emit stateChanged(); }
        reply->deleteLater(); network->deleteLater();
    });
}

extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeInitialize(JNIEnv* env, jclass type) {
    JavaVM* machine = nullptr; if (env->GetJavaVM(&machine) != JNI_OK) return;
    jclass value = static_cast<jclass>(env->NewGlobalRef(type)); if (!value) return;
    vm.store(machine); jclass expected = nullptr; if (!backend.compare_exchange_strong(expected, value)) env->DeleteGlobalRef(value);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeForeground(JNIEnv*, jclass, jboolean active) {
    foreground.store(active); QMutexLocker guard(&registryMutex); for (auto* item : registry) item->acceptForeground(active);
}
extern "C" JNIEXPORT jlong JNICALL Java_org_overte_web_EmbeddedWebView_nativeGeneration(JNIEnv*, jclass, jlong handle) {
    QMutexLocker guard(&registryMutex); auto* item = registry.value(handle); return item ? item->generation() : 0;
}
extern "C" JNIEXPORT jlong JNICALL Java_org_overte_web_EmbeddedWebView_nativeLifecycleRevision(JNIEnv*, jclass, jlong handle) {
    QMutexLocker guard(&registryMutex); auto* item = registry.value(handle); return item ? item->lifecycleRevision() : 0;
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeSuspended(JNIEnv* env, jclass, jlong handle, jlong birth, jlong revision, jstring url, jboolean back, jboolean forward) {
    const QUrl document(string(env, url)); QMutexLocker guard(&registryMutex);
    if (auto* item = registry.value(handle)) item->acceptSuspended(revision, document, back, forward, birth);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeResumeRequest(JNIEnv* env, jclass, jlong handle, jlong birth, jlong revision, jstring url) {
    const QUrl document(string(env, url)); QMutexLocker guard(&registryMutex);
    if (auto* item = registry.value(handle)) item->requestResume(revision, document, birth);
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_web_EmbeddedWebView_nativeNavigation(JNIEnv* env, jclass, jlong handle, jlong grant, jstring url, jboolean mainFrame, jstring method) {
    auto target = QUrl(string(env, url)); auto verb = string(env, method); QMutexLocker guard(&registryMutex); auto* item = registry.value(handle);
    return item && item->allowsNavigation(grant, target, mainFrame, verb);
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_web_EmbeddedWebView_nativeBridgeAllowed(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jstring document) {
    auto target = QUrl(string(env, document)); QMutexLocker guard(&registryMutex); auto* item = registry.value(handle);
    return item && item->allowsBridgeDocument(grant, page, target);
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_web_EmbeddedWebView_nativeEditorAllowed(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jstring document) {
    auto target = QUrl(string(env, document)); QMutexLocker guard(&registryMutex); auto* item = registry.value(handle);
    return item && item->allowsEditorDocument(grant, page, target);
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_web_EmbeddedWebView_nativeFileChooserAllowed(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jstring document) {
    auto target = QUrl(string(env, document)); QMutexLocker guard(&registryMutex); auto* item = registry.value(handle);
    return item && item->allowsFileChooser(grant, page, target);
}
extern "C" JNIEXPORT jboolean JNICALL Java_org_overte_web_EmbeddedWebView_nativeMessage(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jstring document, jstring origin, jboolean mainFrame, jstring type, jstring payload) {
    auto target = QUrl(string(env, document)); auto source = QUrl(string(env, origin)); auto kind = string(env, type); auto data = string(env, payload).toUtf8();
    QMutexLocker guard(&registryMutex); auto* item = registry.value(handle); return item && item->acceptMessage(grant, page, target, source, mainFrame, kind, data);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativePage(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jstring document) {
    auto url = QUrl(string(env, document)); QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) item->acceptPage(grant, page, url);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeState(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jstring document, jboolean loading, jboolean back, jboolean forward, jboolean bridge, jint status) {
    auto url = QUrl(string(env, document)); QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) item->acceptState(grant, page, url, loading, back, forward, bridge, status);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeCreated(JNIEnv*, jclass, jlong handle, jlong revision, jboolean created) {
    QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) item->acceptCreated(created, revision);
}
extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeFrame(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jobject pixels, jint width, jint height) {
    auto* bytes = env->GetDirectBufferAddress(pixels); const auto capacity = env->GetDirectBufferCapacity(pixels);
    QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) item->acceptFrame(grant, page, bytes, capacity, width, height);
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_overte_web_EmbeddedWebView_nativeResource(JNIEnv* env, jclass, jlong handle, jlong grant, jstring url) {
    auto target = QUrl(string(env, url)); QByteArray data; { QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) data = item->resource(grant, target); }
    if (data.isNull()) return nullptr; auto result = env->NewByteArray(data.size()); if (result) env->SetByteArrayRegion(result, 0, data.size(), reinterpret_cast<const jbyte*>(data.constData())); return result;
}
extern "C" JNIEXPORT jstring JNICALL Java_org_overte_web_EmbeddedWebView_nativeResourceMime(JNIEnv* env, jclass, jlong handle, jlong grant, jstring url) {
    auto target = QUrl(string(env, url)); QString mime; { QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) mime = item->resourceMime(grant, target); }
    return env->NewString(reinterpret_cast<const jchar*>(mime.utf16()), mime.size());
}

extern "C" JNIEXPORT void JNICALL Java_org_overte_web_EmbeddedWebView_nativeResult(JNIEnv* env, jclass, jlong handle, jlong grant, jlong page, jlong request, jstring result) {
    auto json = string(env, result).toUtf8(); QMutexLocker guard(&registryMutex); if (auto* item = registry.value(handle)) item->acceptResult(grant, page, request, json);
}
