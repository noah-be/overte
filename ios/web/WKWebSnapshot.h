// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QImage>
#include <QObject>
#include <QSize>
#include <memory>

namespace overte::ios {
// Capture only: the endpoint owns WKWebView configuration/navigation, its
// originating window, policy grant and input. attach never loads a URL.
class WKWebSnapshot final : public QObject {
    Q_OBJECT
public:
    explicit WKWebSnapshot(QObject* parent = nullptr);
    ~WKWebSnapshot() override;
    // Native WKWebView pointer; UIKit/Qt GUI thread only. Logical pixels are
    // capped independently of Retina scale. An unattached view is rejected.
    bool attach(void* webView, QSize logicalSize);
    void detach();
signals:
    void imageReady(const QImage& image);
    void failed();
private:
    void capture();
    void fail();
    struct Private;
    std::unique_ptr<Private> _private;
};
} // namespace overte::ios
