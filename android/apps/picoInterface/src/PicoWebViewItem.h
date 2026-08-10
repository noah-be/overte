#pragma once

#include <QImage>
#include <QMutex>
#include <QQuickItem>

#include <cstdint>

class PicoWebViewItem : public QQuickItem {
    Q_OBJECT
    Q_PROPERTY(QString url READ url WRITE setUrl NOTIFY urlChanged)
    Q_PROPERTY(QString scriptUrl MEMBER _scriptUrl)
    Q_PROPERTY(bool useBackground READ useBackground WRITE setUseBackground NOTIFY useBackgroundChanged)
    Q_PROPERTY(QString userAgent READ userAgent WRITE setUserAgent)
    Q_PROPERTY(QString frameSource READ frameSource)

public:
    explicit PicoWebViewItem(QQuickItem* parent = nullptr);
    ~PicoWebViewItem() override;
    QString url() const { return _url; }
    void setUrl(const QString& value);
    QString userAgent() const { return _userAgent; }
    void setUserAgent(const QString& value);
    bool useBackground() const { return _useBackground; }
    void setUseBackground(bool value);
    QString frameSource() const;
    QImage frameImage() const;
    void acceptFrame(const void* pixels, qsizetype byteCount, int width, int height);
    void acceptCreationResult(bool created);
    void componentComplete() override;

signals:
    void urlChanged();
    void useBackgroundChanged();

protected:
    void geometryChanged(const QRectF& newGeometry, const QRectF& oldGeometry) override;
    void hoverEnterEvent(QHoverEvent* event) override;
    void hoverMoveEvent(QHoverEvent* event) override;
    void hoverLeaveEvent(QHoverEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void mouseUngrabEvent() override;
    void wheelEvent(QWheelEvent* event) override;

private:
    void createWebView();
    void scheduleCreationRetry();
    void sendPointer(int action, const QPointF& position);
    int pixelWidth() const;
    int pixelHeight() const;

    QString _url;
    QString _scriptUrl;
    QString _userAgent;
    bool _useBackground { true };
    bool _webViewCreated { false };
    bool _webViewCreationPending { false };
    bool _webViewCreationRetryScheduled { false };
    uint8_t _webViewCreationRetries { 0 };
    bool _pointerPressed { false };
    mutable QMutex _imageMutex;
    QImage _image;
    quint64 _frameSerial { 0 };
};
