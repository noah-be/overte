// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <QObject>

class IOSTouchUiMetrics final : public QObject {
    Q_OBJECT
    Q_PROPERTY(qreal safeInsetLeft READ safeInsetLeft NOTIFY metricsChanged)
    Q_PROPERTY(qreal safeInsetTop READ safeInsetTop NOTIFY metricsChanged)
    Q_PROPERTY(qreal safeInsetRight READ safeInsetRight NOTIFY metricsChanged)
    Q_PROPERTY(qreal safeInsetBottom READ safeInsetBottom NOTIFY metricsChanged)
    Q_PROPERTY(qreal imeInsetBottom READ imeInsetBottom NOTIFY metricsChanged)
    Q_PROPERTY(bool keyboardVisible READ keyboardVisible NOTIFY metricsChanged)
    Q_PROPERTY(qreal surfaceWidth READ surfaceWidth NOTIFY metricsChanged)
    Q_PROPERTY(qreal surfaceHeight READ surfaceHeight NOTIFY metricsChanged)
    Q_PROPERTY(qreal density READ density NOTIFY metricsChanged)
    Q_PROPERTY(qreal fontScale READ fontScale NOTIFY metricsChanged)

public:
    explicit IOSTouchUiMetrics(QObject* parent = nullptr);
    ~IOSTouchUiMetrics() override;

    qreal safeInsetLeft() const { return _safeInsetLeft; }
    qreal safeInsetTop() const { return _safeInsetTop; }
    qreal safeInsetRight() const { return _safeInsetRight; }
    qreal safeInsetBottom() const { return _safeInsetBottom; }
    qreal imeInsetBottom() const { return _imeInsetBottom; }
    bool keyboardVisible() const { return _keyboardVisible; }
    qreal surfaceWidth() const { return _surfaceWidth; }
    qreal surfaceHeight() const { return _surfaceHeight; }
    qreal density() const { return _density; }
    qreal fontScale() const { return _fontScale; }

signals:
    void metricsChanged();

private:
    void refresh(void* keyboardNotification = nullptr);

    qreal _safeInsetLeft { 0.0 };
    qreal _safeInsetTop { 0.0 };
    qreal _safeInsetRight { 0.0 };
    qreal _safeInsetBottom { 0.0 };
    qreal _imeInsetBottom { 0.0 };
    bool _keyboardVisible { false };
    qreal _surfaceWidth { 0.0 };
    qreal _surfaceHeight { 0.0 };
    qreal _density { 1.0 };
    qreal _fontScale { 1.0 };
    void* _notificationTokens { nullptr };
};

void registerIOSTouchUiMetricsQmlType();
