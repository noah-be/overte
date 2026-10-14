// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QJsonObject>
#include <QObject>
#include <QUrl>
#include <QVariant>
#include <QWebChannel>
#include <QWebChannelAbstractTransport>
#include <functional>
#include <memory>

namespace overte::ios {
class IOSPageEventBridge final : public QObject {
    Q_OBJECT
public:
    explicit IOSPageEventBridge(QObject* parent = nullptr) : QObject(parent) {}
    Q_INVOKABLE void emitWebEvent(const QVariant& message) { emit webEventReceived(message); }
signals:
    void webEventReceived(const QVariant& message);
    void scriptEventReceived(const QVariant& message);
};

class IOSWebTransport final : public QWebChannelAbstractTransport {
public:
    explicit IOSWebTransport(QObject* parent = nullptr) : QWebChannelAbstractTransport(parent) {}
    std::function<void(const QJsonObject&)> sender;
    void sendMessage(const QJsonObject& message) override { if (sender) { sender(message); } }
    void receive(const QJsonObject& message) { emit messageReceived(message, this); }
};

// Real Qt WebChannel server. The native delegate supplies the shared generation,
// origin, frame and payload gate for every incoming envelope.
class IOSWebChannel final : public QObject {
    Q_OBJECT
public:
    using Gate = std::function<bool(const QUrl&, bool, std::size_t)>;
    explicit IOSWebChannel(QObject* parent = nullptr);
    void reset(Gate gate = {});
    bool receiveEnvelope(const QString& envelope, const QUrl& frame, bool mainFrame);
    void publishScriptEvent(const QVariant& message);
    static QString transportJavaScript(const QString& documentNonce);
signals:
    void sendToPage(const QString& envelope);
    void webEventReceived(const QVariant& message);
    void bridgeInitialized();
private:
    Gate _gate;
    std::unique_ptr<QWebChannel> _channel;
    std::unique_ptr<IOSPageEventBridge> _bridge;
    std::unique_ptr<IOSWebTransport> _transport;
    bool _initializing { false }, _initialized { false };
    bool _receiving { false }, _resetPending { false };
    Gate _pendingGate;
};
} // namespace overte::ios
