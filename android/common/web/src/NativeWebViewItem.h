// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeResourceMapping.h"
#include <QImage>
#include <QJSValue>
#include <QHash>
#include <QJsonObject>
#include <QMutex>
#include <QPointer>
#include <QQuickItem>
#include <QWebChannel>
#include <QWebChannelAbstractTransport>

class NativeWebTransport final : public QWebChannelAbstractTransport {
    Q_OBJECT
public:
    using QWebChannelAbstractTransport::QWebChannelAbstractTransport;
    void sendMessage(const QJsonObject& message) override { emit outbound(message); }
    void receive(const QJsonObject& message) { emit messageReceived(message, this); }
signals:
    void outbound(const QJsonObject& message);
};
class NativeSurfaceBridge final : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
public slots:
    void emitWebEvent(const QVariant& message) { emit webEvent(message); }
    void forwardScriptEvent(const QVariant& message) { emit scriptEventReceived(message); }
signals:
    void scriptEventReceived(const QVariant& message);
    void webEvent(const QVariant& message);
};
class NativeBridgeWrapper final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QObject* eventBridge READ eventBridge CONSTANT)
public:
    NativeBridgeWrapper(QObject* bridge, QObject* parent) : QObject(parent), _bridge(bridge) { }
    QObject* eventBridge() const { return _bridge; }
private:
    QObject* _bridge;
};

class NativeWebViewItem : public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(QString currentUrl READ currentUrl NOTIFY stateChanged)
    Q_PROPERTY(QString url READ url WRITE setUrl NOTIFY urlChanged)
    Q_PROPERTY(QString scriptUrl READ scriptUrl WRITE setScriptUrl NOTIFY scriptUrlChanged)
    Q_PROPERTY(QString userAgent READ userAgent WRITE setUserAgent NOTIFY userAgentChanged)
    Q_PROPERTY(bool useBackground READ useBackground WRITE setUseBackground NOTIFY useBackgroundChanged)
    Q_PROPERTY(QString sourceIdentity READ sourceIdentity WRITE setSourceIdentity NOTIFY sourceIdentityChanged)
    Q_PROPERTY(Surface surface READ surface WRITE setSurface NOTIFY surfaceChanged)
    Q_PROPERTY(Presentation presentation READ presentation WRITE setPresentation NOTIFY presentationChanged)
    Q_PROPERTY(QString eventBridgeJavaScript READ eventBridgeJavaScript WRITE setEventBridgeJavaScript)
    Q_PROPERTY(bool loading READ loading NOTIFY stateChanged)
    Q_PROPERTY(bool canGoBack READ canGoBack NOTIFY stateChanged)
    Q_PROPERTY(bool canGoForward READ canGoForward NOTIFY stateChanged)
    Q_PROPERTY(QString error READ errorText NOTIFY stateChanged)
    Q_PROPERTY(QString warning READ warningText NOTIFY stateChanged)
    Q_PROPERTY(bool bridgeAvailable READ bridgeAvailable NOTIFY stateChanged)
    Q_PROPERTY(bool editorFocused READ editorFocused NOTIFY editorStateChanged)
    Q_PROPERTY(bool editorNumeric READ editorNumeric NOTIFY editorStateChanged)
    Q_PROPERTY(bool editorPassword READ editorPassword NOTIFY editorStateChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY stateChanged)
public:
    enum Surface { Tablet, WorldEntity }; Q_ENUM(Surface)
    enum Presentation { Texture, NativeOverlay }; Q_ENUM(Presentation)
    explicit NativeWebViewItem(QQuickItem* parent = nullptr);
    ~NativeWebViewItem() override;
    // Call from native product setup with its known resource/script directories.
    static void setPackagedResourceRoots(const QStringList& roots);
    QString currentUrl() const { return _currentUrl; }
    QString url() const { return _url; } void setUrl(const QString& value);
    QString scriptUrl() const { return _scriptUrl; } void setScriptUrl(const QString& value);
    QString userAgent() const { return _userAgent; } void setUserAgent(const QString& value);
    QString sourceIdentity() const { return _sourceIdentity; } void setSourceIdentity(const QString& value);
    QString eventBridgeJavaScript() const { return _bootstrap; } void setEventBridgeJavaScript(const QString& value) { _bootstrap = value; }
    bool useBackground() const { return _background; } void setUseBackground(bool value);
    Surface surface() const { return _surface; } void setSurface(Surface value);
    Presentation presentation() const { return _presentation; } void setPresentation(Presentation value);
    bool loading() const { return _loading; } bool canGoBack() const { return _canGoBack; }
    bool canGoForward() const { return _canGoForward; }
    bool editorFocused() const { return _editorActive; }
    bool editorNumeric() const { return _editorActive && (_editorKind == "number" || _editorKind == "tel"); }
    bool editorPassword() const { return _editorActive && _sensitive; }
    bool bridgeAvailable() const { return _bridgeAvailable; } QString statusText() const;
    QString errorText() const; QString warningText() const;
    void componentComplete() override;
    Q_INVOKABLE void stop(); Q_INVOKABLE void reload(); Q_INVOKABLE void goBack();
    Q_INVOKABLE void goForward(); Q_INVOKABLE void reloadAndBypassCache(); Q_INVOKABLE void unfocus();
    Q_INVOKABLE void openNative();
    Q_INVOKABLE bool runJavaScript(const QString& source, const QJSValue& callback = QJSValue());
    Q_INVOKABLE bool emitScriptEvent(const QVariant& message);
    // JNI entry points: registry lifetime is held by the caller; no Android call while locked.
    QRectF sceneBounds() const { return mapRectToScene(boundingRect()); }
    QRectF sceneClipBounds() const;
    quint64 generation() const;
    bool allowsBridgeDocument(quint64 grant, quint64 page, const QUrl& document) const;
    bool allowsFileChooser(quint64 grant, quint64 page, const QUrl& document) const;
    bool allowsNavigation(quint64 grant, const QUrl& target, bool mainFrame, const QString& method) const;
    bool acceptMessage(quint64 grant, quint64 page, const QUrl& document, const QUrl& origin,
                       bool mainFrame, const QString& type, const QByteArray& payload);
    void acceptPage(quint64 grant, quint64 page, const QUrl& document);
    void acceptState(quint64 grant, quint64 page, const QUrl& document, bool loading, bool back, bool forward, bool bridge, int status);
    void acceptFrame(quint64 grant, quint64 page, const void* pixels, qsizetype bytes, int width, int height);
    void acceptCreated(bool created);
    void acceptResult(quint64 grant, quint64 page, quint64 request, const QByteArray& json);
    void acceptForeground(bool active);
    QByteArray resource(quint64 grant, const QUrl& browser) const;
    QString resourceMime(quint64 grant, const QUrl& browser) const;
signals:
    void editorStateChanged(); void editorFocusChanged(bool active, bool numeric, bool password);
    void urlChanged(); void scriptUrlChanged(); void userAgentChanged(); void useBackgroundChanged();
    void webEventReceived(const QVariant& message);
    void sourceIdentityChanged(); void surfaceChanged(); void presentationChanged(); void stateChanged();
protected:
    void geometryChanged(const QRectF& geometry, const QRectF& old) override;
    QSGNode* updatePaintNode(QSGNode* node, UpdatePaintNodeData*) override;
    void mousePressEvent(QMouseEvent*) override; void mouseMoveEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override; void mouseUngrabEvent() override;
    void wheelEvent(QWheelEvent*) override; void keyPressEvent(QKeyEvent*) override;
    void inputMethodEvent(QInputMethodEvent*) override;
    QVariant inputMethodQuery(Qt::InputMethodQuery query) const override;
    void focusInEvent(QFocusEvent*) override; void focusOutEvent(QFocusEvent*) override;
private:
    void create(); void retryCreation(); void navigate(); void synchronizeVisibility(); void updateGeometry(); void trackGeometry();
    bool evaluate(const QString& script, quint64 grant, quint64 page);
    void pointer(int action, const QPointF& position);
    void editorCommand(const QJsonObject& command);
    void resetEditor();
    void updateEditor(const QJsonObject& state);
    void injectUserScript(quint64 grant, quint64 page, const QUrl& url, int redirects = 0);
    bool current(quint64 grant, quint64 page) const;
    QUrl sourceURL(const QUrl& browser) const;
    QString scriptRoot(const QUrl& source) const;
    QString _currentUrl, _url, _scriptUrl, _userAgent, _sourceIdentity, _bootstrap;
    bool _background { true }, _created { false }, _pending { false }, _retryPending { false }, _pressed { false };
    bool _tabletGrant { false };
    bool _loading { false }, _canGoBack { false }, _canGoForward { false }, _bridgeAvailable { false };
    int _status { 0 }, _attempts { 0 };
    Surface _surface { WorldEntity }; Presentation _presentation { Texture };
    qint64 _handle { 0 };
    quint64 _page { 0 }, _injectedPage { 0 }, _scriptVersion { 0 };
    mutable QMutex _mutex;
    overte::web::EmbeddedWebSession _session;
    overte::android::web::NativeResourceMapping _mapping;
    QUrl _document;
    QImage _image;
    bool _editorActive { false }, _sensitive { false };
    QString _editorText, _editorKind;
    int _cursor { 0 }, _anchor { 0 }, _surroundingStart { 0 };
    QRectF _cursorRect;
    quint64 _nextRequest { 1 };
    QHash<quint64, QJSValue> _callbacks;
    QVector<QMetaObject::Connection> _geometryConnections;
    NativeWebTransport* _transport;
    NativeSurfaceBridge* _bridge;
    QWebChannel* _channel;
};
