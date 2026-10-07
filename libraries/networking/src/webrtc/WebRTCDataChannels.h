// Created by David Rowe on 21 May 2021.
// Copyright 2021 Vircadia contributors.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Modified in 2026 for the optional direct browser transport.

#ifndef overte_WebRTCDataChannels_h
#define overte_WebRTCDataChannels_h

#include <shared/WebRTC.h>

#if defined(WEBRTC_DATA_CHANNELS)

#include <functional>
#include <memory>
#include <mutex>

#include <QObject>
#include <QHash>
#include <QJsonObject>
#include <QTimer>

#include "../NodeType.h"
#include "../SockAddr.h"

namespace rtc { class DataChannel; }

/// Datagram transport inside the domain server and each assignment client.
/// The browser's signaling address identifies its native-protocol socket;
/// admission, packet verification and native UDT reliability remain unchanged.
class WebRTCDataChannels : public QObject {
    Q_OBJECT
public:
    explicit WebRTCDataChannels(QObject* parent);
    ~WebRTCDataChannels() override;

    NodeType_t getNodeType() const { return _nodeType; }
    void reset();
    bool sendDataMessage(const SockAddr& destination, const QByteArray& message);
    bool isPeerOpen(const SockAddr& address) const;
    QString peerGeneration(const SockAddr& address) const;
    qint64 getBufferedAmount(const SockAddr& address) const;

public slots:
    void onSignalingMessage(const QJsonObject& message);

signals:
    void signalingMessage(const QJsonObject& message);
    void dataMessage(const SockAddr& address, const QByteArray& message);
    void peerClosed(const SockAddr& address);

private:
    struct Connection;
    struct CallbackGuard;
    struct PendingDatagram;
    struct PendingCallback;
    using ConnectionPtr = std::shared_ptr<Connection>;
    using Callback = std::function<void(WebRTCDataChannels*, const ConnectionPtr&)>;

    static bool post(const std::shared_ptr<CallbackGuard>& guard,
                     const std::weak_ptr<Connection>& connection, Callback callback);
    ConnectionPtr createConnection(const QString& id, const QString& session, NodeType_t nodeType);
    ConnectionPtr findConnection(const QString& id) const;
    static void installDataChannel(const std::shared_ptr<CallbackGuard>& guard,
                                   const std::weak_ptr<Connection>& connection,
                                   const std::shared_ptr<rtc::DataChannel>& channel);
    void closeConnection(const ConnectionPtr& connection);
    void sendSignal(const ConnectionPtr& connection, const QJsonObject& data);
    void expireConnections();

    NodeType_t _nodeType { NodeType::Unassigned };
    QHash<QString, ConnectionPtr> _connections;
    mutable std::mutex _connectionsMutex;
    std::shared_ptr<CallbackGuard> _guard;
    QTimer _expiryTimer;
};

#endif // WEBRTC_DATA_CHANNELS
#endif // overte_WebRTCDataChannels_h
