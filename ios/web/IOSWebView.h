// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QImage>
#include <QJSValue>
#include <QQuickPaintedItem>
#include <QUrl>
#include <QVariant>
#include <memory>

namespace overte::ios {
class IOSWebView : public QQuickPaintedItem {
    Q_OBJECT
    Q_PROPERTY(QUrl url READ url WRITE setUrl NOTIFY urlChanged)
    Q_PROPERTY(QUrl currentUrl READ currentUrl NOTIFY navigationChanged)
    Q_PROPERTY(QUrl scriptUrl READ scriptUrl WRITE setScriptUrl NOTIFY configurationChanged)
    Q_PROPERTY(QString userAgent READ userAgent WRITE setUserAgent NOTIFY configurationChanged)
    Q_PROPERTY(bool useBackground READ useBackground WRITE setUseBackground NOTIFY configurationChanged)
    Q_PROPERTY(QString surface READ surface WRITE setSurface NOTIFY configurationChanged)
    Q_PROPERTY(QString sourceIdentity READ sourceIdentity WRITE setSourceIdentity NOTIFY configurationChanged)
    Q_PROPERTY(QString eventBridgeJavaScript READ eventBridgeJavaScript WRITE setEventBridgeJavaScript NOTIFY configurationChanged)
    Q_PROPERTY(QString packagedScriptRoot READ packagedScriptRoot WRITE setPackagedScriptRoot NOTIFY configurationChanged)
    Q_PROPERTY(bool loading READ loading NOTIFY loadingChanged)
    Q_PROPERTY(bool canGoBack READ canGoBack NOTIFY navigationChanged)
    Q_PROPERTY(bool canGoForward READ canGoForward NOTIFY navigationChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QImage frameSource READ frameSource NOTIFY frameChanged)
    Q_PROPERTY(bool bridgeAvailable READ bridgeAvailable NOTIFY bridgeAvailableChanged)
public:
    explicit IOSWebView(QQuickItem* parent = nullptr);
    ~IOSWebView() override;
    QUrl url() const;
    QUrl currentUrl() const;
    void setUrl(const QUrl& value);
    QUrl scriptUrl() const;
    void setScriptUrl(const QUrl& value);
    QString userAgent() const;
    void setUserAgent(const QString& value);
    bool useBackground() const;
    void setUseBackground(bool value);
    QString surface() const;
    void setSurface(const QString& value);
    QString sourceIdentity() const;
    void setSourceIdentity(const QString& value);
    QString eventBridgeJavaScript() const;
    void setEventBridgeJavaScript(const QString& value);
    QString packagedScriptRoot() const;
    void setPackagedScriptRoot(const QString& value);
    bool loading() const;
    bool canGoBack() const;
    bool canGoForward() const;
    QString error() const;
    QImage frameSource() const;
    bool bridgeAvailable() const;
    void paint(QPainter* painter) override;
    Q_INVOKABLE void emitScriptEvent(const QVariant& message);
    Q_INVOKABLE bool openNative();
    Q_INVOKABLE void goBack();
    Q_INVOKABLE void goForward();
    Q_INVOKABLE void reload();
    Q_INVOKABLE void reloadAndBypassCache();
    Q_INVOKABLE void stop();
    Q_INVOKABLE void unfocus();
    Q_INVOKABLE void runJavaScript(const QString& code, const QJSValue& callback = QJSValue());
    Q_INVOKABLE void pointerEvent(const QString& type, double x, double y, int button = 0);
    Q_INVOKABLE void keyEvent(const QString& text, int key = 0, int modifiers = 0);
signals:
    void urlChanged();
    void configurationChanged();
    void loadingChanged();
    void navigationChanged();
    void errorChanged();
    void frameChanged();
    void bridgeAvailableChanged();
    void webEventReceived(const QVariant& message);
    void nativeClosed();
protected:
    void componentComplete() override;
    void geometryChange(const QRectF& next, const QRectF& previous) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void inputMethodEvent(QInputMethodEvent* event) override;
    QVariant inputMethodQuery(Qt::InputMethodQuery query) const override;
private:
    friend struct IOSWebViewNative;
    void scheduleOpen();
    void open();
    void tearDown();
    void fail(const QString& message);
    void setLoading(bool value);
    void updateNavigation();
    void nativeNavigationFinished();
    void verifyDocument();
    void nativeMessage(const QString& envelope, const QString& documentNonce, const QUrl& frame, bool mainFrame);
    void prepareDocument(const QUrl& frame);
    bool allowsNavigation(const QUrl& destination, bool mainFrame, const QString& method) const;
    bool active() const;
    void evaluate(const QString& code);
    void closePresentation();
    struct Private;
    std::unique_ptr<Private> _private;
};
} // namespace overte::ios
