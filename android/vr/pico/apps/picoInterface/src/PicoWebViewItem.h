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
    Q_PROPERTY(bool rendering READ rendering NOTIFY renderingChanged)
    Q_PROPERTY(bool editorFocused READ editorFocused NOTIFY editorStateChanged)
    Q_PROPERTY(bool editorNumeric READ editorNumeric NOTIFY editorStateChanged)
    Q_PROPERTY(bool editorPassword READ editorPassword NOTIFY editorStateChanged)

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
    void acceptFrame(qint64 epoch, const void* pixels, qsizetype byteCount, int width, int height);
    void acceptLifecycle(qint64 epoch, bool rendering);
    bool rendering() const;
    bool editorFocused() const;
    bool editorNumeric() const;
    bool editorPassword() const;
    void acceptEditorState(qint64 epoch, qint64 revision, bool focused, bool numeric, bool password);
    Q_INVOKABLE void unfocus();
    void acceptCreationResult(bool created);
    void componentComplete() override;

signals:
    void urlChanged();
    void useBackgroundChanged();
    void renderingChanged();
    void editorStateChanged();

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
    void keyPressEvent(QKeyEvent* event) override;
    void inputMethodEvent(QInputMethodEvent* event) override;
    QVariant inputMethodQuery(Qt::InputMethodQuery query) const override;
    void focusInEvent(QFocusEvent* event) override;
    void focusOutEvent(QFocusEvent* event) override;

private:
    void createWebView();
    void syncVisibility();
    void scheduleCreationRetry();
    void sendPointer(int action, const QPointF& position);
    bool canEditText() const;
    void clearEditorState();
    void sendEditorText(const QString& text, bool composing);
    int pixelWidth() const;
    int pixelHeight() const;

    QString _url;
    QString _scriptUrl;
    QString _userAgent;
    int64_t _nativeHandle { 0 };
    bool _useBackground { true };
    bool _webViewCreated { false };
    bool _webViewCreationPending { false };
    bool _webViewCreationRetryScheduled { false };
    uint8_t _webViewCreationRetries { 0 };
    bool _pointerPressed { false };
    mutable QMutex _imageMutex;
    QImage _image;
    quint64 _frameSerial { 0 };
    qint64 _nativeEpoch { -1 };
    bool _nativeRendering { false };
    bool _surfaceVisible { true };
    qint64 _editorRevision { 0 };
    bool _editorFocused { false }, _editorNumeric { false }, _editorPassword { false };
};
