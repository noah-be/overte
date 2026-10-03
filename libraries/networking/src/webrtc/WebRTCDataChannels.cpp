// Created by David Rowe on 21 May 2021.
// Copyright 2021 Vircadia contributors.
// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Modified in 2026 for the optional direct browser transport.

#include "WebRTCDataChannels.h"

#if defined(WEBRTC_DATA_CHANNELS)

#include <atomic>
#include <chrono>
#include <mutex>
#include <utility>
#include <rtc/rtc.hpp>

#include <QJsonDocument>
#include <QThread>
#include <QUuid>

#include "BrowserDatagramValidator.h"
#include "../NetworkLogging.h"
#include "../udt/Constants.h"

namespace {
constexpr int MAX_PEERS = 256;
constexpr int MAX_SIGNAL_BYTES = 65536;
constexpr int MAX_SDP_BYTES = 49152;
constexpr int MAX_CANDIDATE_BYTES = 2048;
constexpr int MAX_CANDIDATES = 64;
constexpr int MAX_PENDING_DATAGRAMS = 4096;
constexpr int MAX_PENDING_PEER_DATAGRAMS = 256;
constexpr int PEER_TIMEOUT_MS = 30000;

qint64 monotonicMilliseconds() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

QString addressID(const SockAddr& address) {
    return address.getAddress().toString() + ":" + QString::number(address.getPort());
}

bool parseAddress(const QString& id, SockAddr& address) {
    int separator = id.lastIndexOf(':');
    if (separator <= 0) {
        return false;
    }
    QHostAddress host(id.left(separator));
    bool validPort = false;
    uint port = id.mid(separator + 1).toUInt(&validPort);
    if (host.isNull() || !validPort || !port || port > 65535) {
        return false;
    }
    address = SockAddr(SocketType::WebRTC, host, static_cast<quint16>(port));
    return addressID(address) == id;
}

rtc::Configuration configuration() {
    rtc::Configuration config;
    // Empty by default. Operators may point this at their own STUN servers.
    const auto servers = qEnvironmentVariable("OVERTE_BROWSER_STUN_SERVERS").split(';', Qt::SkipEmptyParts);
    if (servers.size() > 8) {
        throw std::invalid_argument("Too many configured STUN servers");
    }
    for (const auto& server : servers) {
        if (!server.startsWith("stun:") || server.size() > 512) {
            throw std::invalid_argument("Expected a STUN URI");
        }
        config.iceServers.emplace_back(server.toStdString());
    }
    const auto bindAddress = qEnvironmentVariable("OVERTE_BROWSER_ICE_BIND_ADDRESS");
    if (!bindAddress.isEmpty()) {
        QHostAddress host(bindAddress);
        if (host.isNull()) {
            throw std::invalid_argument("Invalid ICE bind address");
        }
        config.bindAddress = host.toString().toStdString();
    }
    const std::pair<const char*, uint16_t*> portSettings[] = {
        { "OVERTE_BROWSER_ICE_PORT_MIN", &config.portRangeBegin },
        { "OVERTE_BROWSER_ICE_PORT_MAX", &config.portRangeEnd }
    };
    for (const auto& setting : portSettings) {
        const auto value = qEnvironmentVariable(setting.first);
        if (!value.isEmpty()) {
            bool ok = false;
            uint port = value.toUInt(&ok);
            if (!ok || !port || port > 65535) {
                throw std::invalid_argument("Invalid ICE port range");
            }
            *setting.second = static_cast<uint16_t>(port);
        }
    }
    if (config.portRangeBegin > config.portRangeEnd) {
        throw std::invalid_argument("Invalid ICE port range");
    }
    config.maxMessageSize = udt::MAX_PACKET_SIZE;
    return config;
}
} // namespace

struct WebRTCDataChannels::Connection {
    QString id;
    QString session;
    const QString generation { QUuid::createUuid().toString(QUuid::WithoutBraces) };
    SockAddr address;
    NodeType_t nodeType;
    std::shared_ptr<rtc::PeerConnection> peer;
    std::shared_ptr<rtc::DataChannel> channel;
    std::atomic<qint64> lastActivity { 0 };
    int remoteCandidateCount { 0 };
    std::atomic<int> pendingDatagrams { 0 };
    std::atomic<int> pendingCallbacks { 0 };
    std::atomic<bool> channelRequested { false };
    std::mutex sendMutex;
};

// A worker holds this mutex only while posting to the QObject. Destruction
// invalidates the owner before closing the library objects, preventing a race
// between QObject destruction and a libdatachannel callback.
struct WebRTCDataChannels::CallbackGuard {
    std::mutex mutex;
    WebRTCDataChannels* owner { nullptr };
    std::atomic<int> pendingDatagrams { 0 };
    std::atomic<int> pendingBytes { 0 };
    std::atomic<int> pendingCallbacks { 0 };
};

struct WebRTCDataChannels::PendingCallback {
    std::shared_ptr<CallbackGuard> guard;
    std::shared_ptr<Connection> connection;
    ~PendingCallback() {
        guard->pendingCallbacks.fetch_sub(1);
        connection->pendingCallbacks.fetch_sub(1);
    }
};

// Accounting also releases if Qt discards a queued event during destruction.
struct WebRTCDataChannels::PendingDatagram {
    std::shared_ptr<CallbackGuard> guard;
    std::shared_ptr<Connection> connection;
    int size;
    ~PendingDatagram() {
        guard->pendingBytes.fetch_sub(size);
        guard->pendingDatagrams.fetch_sub(1);
        connection->pendingDatagrams.fetch_sub(1);
    }
};

WebRTCDataChannels::WebRTCDataChannels(QObject* parent) : QObject(parent), _guard(std::make_shared<CallbackGuard>()) {
    _guard->owner = this;
    _expiryTimer.setParent(this);
    _expiryTimer.setInterval(1000);
    connect(&_expiryTimer, &QTimer::timeout, this, &WebRTCDataChannels::expireConnections);
    _expiryTimer.start();
}

WebRTCDataChannels::~WebRTCDataChannels() {
    {
        std::lock_guard<std::mutex> lock(_guard->mutex);
        _guard->owner = nullptr;
    }
    reset();
}

bool WebRTCDataChannels::post(const std::shared_ptr<CallbackGuard>& guard,
                             const std::weak_ptr<Connection>& connection, Callback callback) {
    auto current = connection.lock();
    if (!current) {
        return false;
    }
    std::lock_guard<std::mutex> lock(guard->mutex);
    auto owner = guard->owner;
    if (!owner || guard->pendingCallbacks >= MAX_PENDING_DATAGRAMS ||
        current->pendingCallbacks >= MAX_PENDING_PEER_DATAGRAMS) {
        return false;
    }
    auto ticket = std::make_shared<PendingCallback>();
    ticket->guard = guard;
    ticket->connection = current;
    guard->pendingCallbacks.fetch_add(1);
    current->pendingCallbacks.fetch_add(1);
    return QMetaObject::invokeMethod(owner, [owner, connection, ticket, callback = std::move(callback)] {
        auto current = connection.lock();
        if (current && owner->findConnection(current->id) == current) {
            callback(owner, current);
        }
    }, Qt::QueuedConnection);
}

WebRTCDataChannels::ConnectionPtr WebRTCDataChannels::createConnection(const QString& id, const QString& session,
                                                                       NodeType_t nodeType) {
    auto connection = std::make_shared<Connection>();
    connection->id = id;
    connection->session = session;
    connection->nodeType = nodeType;
    parseAddress(id, connection->address);
    connection->lastActivity = monotonicMilliseconds();
    connection->peer = std::make_shared<rtc::PeerConnection>(configuration());
    {
        std::lock_guard<std::mutex> lock(_connectionsMutex);
        _connections.insert(id, connection);
    }
    auto guard = _guard;
    std::weak_ptr<Connection> weak = connection;
    connection->peer->onLocalDescription([guard, weak](rtc::Description description) {
        auto sdp = QString::fromStdString(std::string(description));
        auto type = QString::fromStdString(description.typeString());
        post(guard, weak, [sdp, type](WebRTCDataChannels* owner, const ConnectionPtr& current) {
            owner->sendSignal(current, { { "description", QJsonObject { { "type", type }, { "sdp", sdp } } } });
        });
    });
    connection->peer->onLocalCandidate([guard, weak](rtc::Candidate candidate) {
        auto value = QString::fromStdString(candidate.candidate());
        auto mid = QString::fromStdString(candidate.mid());
        post(guard, weak, [value, mid](WebRTCDataChannels* owner, const ConnectionPtr& current) {
            owner->sendSignal(current, { { "candidate", QJsonObject { { "candidate", value }, { "sdpMid", mid },
                                                                        { "sdpMLineIndex", 0 } } } });
        });
    });
    connection->peer->onStateChange([guard, weak](rtc::PeerConnection::State state) {
        if (state == rtc::PeerConnection::State::Failed || state == rtc::PeerConnection::State::Closed ||
            state == rtc::PeerConnection::State::Disconnected) {
            post(guard, weak, [](WebRTCDataChannels* owner, const ConnectionPtr& current) {
                owner->closeConnection(current);
            });
        }
    });
    connection->peer->onDataChannel([guard, weak](std::shared_ptr<rtc::DataChannel> channel) {
        const auto current = weak.lock();
        const auto reliability = channel->reliability();
        // Limit DCEP channels before queueing to Qt. UDT owns reliability.
        if (!current || current->channelRequested.exchange(true) || !reliability.unordered ||
            !reliability.maxRetransmits || *reliability.maxRetransmits != 0 || reliability.maxPacketLifeTime) {
            channel->close();
            return;
        }
        if (!post(guard, weak, [channel](WebRTCDataChannels*, const ConnectionPtr& current) {
            std::atomic_store(&current->channel, channel);
        })) {
            channel->close();
            return;
        }
        // Install receive callbacks immediately on this worker. Deferring
        // them to Qt would let SCTP build an unbounded incoming channel queue.
        installDataChannel(guard, weak, channel);
    });
    return connection;
}

WebRTCDataChannels::ConnectionPtr WebRTCDataChannels::findConnection(const QString& id) const {
    std::lock_guard<std::mutex> lock(_connectionsMutex);
    return _connections.value(id);
}

void WebRTCDataChannels::installDataChannel(const std::shared_ptr<CallbackGuard>& guard,
                                          const std::weak_ptr<Connection>& weak,
                                          const std::shared_ptr<rtc::DataChannel>& channel) {
    channel->onClosed([guard, weak] {
        post(guard, weak, [](WebRTCDataChannels* owner, const ConnectionPtr& current) { owner->closeConnection(current); });
    });
    channel->onError([guard, weak](const std::string&) {
        post(guard, weak, [](WebRTCDataChannels* owner, const ConnectionPtr& current) { owner->closeConnection(current); });
    });
    channel->onMessage([guard, weak](rtc::message_variant message) {
        const auto bytes = std::get_if<rtc::binary>(&message);
        if (!bytes || !isBrowserDatagramValid(reinterpret_cast<const char*>(bytes->data()), bytes->size())) {
            return;
        }
        auto current = weak.lock();
        if (!current) {
            return;
        }
        const auto size = static_cast<int>(bytes->size());
        {
            std::lock_guard<std::mutex> lock(guard->mutex);
            if (!guard->owner || guard->pendingDatagrams >= MAX_PENDING_DATAGRAMS ||
                guard->pendingBytes + size > udt::WEBRTC_RECEIVE_BUFFER_SIZE_BYTES ||
                current->pendingDatagrams >= MAX_PENDING_PEER_DATAGRAMS) {
                return; // Native UDT handles datagram loss for reliable packet types.
            }
            guard->pendingDatagrams.fetch_add(1);
            guard->pendingBytes.fetch_add(size);
            current->pendingDatagrams.fetch_add(1);
        }
        auto ticket = std::make_shared<PendingDatagram>();
        ticket->guard = guard;
        ticket->connection = current;
        ticket->size = size;
        QByteArray payload(reinterpret_cast<const char*>(bytes->data()), size);
        post(guard, weak, [payload, ticket](WebRTCDataChannels* owner, const ConnectionPtr& current) {
            current->lastActivity = monotonicMilliseconds();
            emit owner->dataMessage(current->address, payload);
        });
    });
}

void WebRTCDataChannels::sendSignal(const ConnectionPtr& connection, const QJsonObject& data) {
    emit signalingMessage({ { "to", connection->id }, { "from", QString(QChar(connection->nodeType)) },
                            { "session", connection->session }, { "data", data } });
}

void WebRTCDataChannels::onSignalingMessage(const QJsonObject& message) {
    Q_ASSERT(QThread::currentThread() == thread());
    if (QJsonDocument(message).toJson(QJsonDocument::Compact).size() > MAX_SIGNAL_BYTES) {
        return;
    }
    const auto id = message.value("from").toString();
    const auto session = message.value("session").toString();
    const auto target = message.value("to").toString();
    SockAddr address;
    if (!parseAddress(id, address) || target.size() != 1 || session.size() != 36) {
        return;
    }
    const auto nodeType = NodeType::fromChar(target.front());
    if (nodeType == NodeType::Unassigned || (_nodeType != NodeType::Unassigned && _nodeType != nodeType) ||
        !message.value("data").isObject()) {
        return;
    }
    _nodeType = nodeType;
    const auto data = message.value("data").toObject();
    auto connection = findConnection(id);
    if (data.value("close").toBool()) {
        if (connection && connection->session == session) {
            closeConnection(connection);
        }
        return;
    }
    try {
        if (data.value("description").isObject()) {
            const auto description = data.value("description").toObject();
            const auto sdp = description.value("sdp").toString();
            if (description.value("type").toString() != "offer" || sdp.isEmpty() ||
                sdp.toUtf8().size() > MAX_SDP_BYTES || !sdp.contains("m=application ") ||
                sdp.contains("m=audio ") || sdp.contains("m=video ")) {
                return;
            }
            // Renegotiation is intentionally bounded to one offer per socket.
            // Reconnection creates a new signaling session and native node.
            if (connection) {
                return;
            }
            {
                std::lock_guard<std::mutex> lock(_connectionsMutex);
                if (_connections.size() >= MAX_PEERS) {
                    return;
                }
            }
            connection = createConnection(id, session, nodeType);
            connection->peer->setRemoteDescription(rtc::Description(sdp.toStdString(), "offer"));
        } else if (!connection || connection->session != session) {
            return; // Candidates cannot allocate unauthenticated peer contexts.
        }
        if (data.value("candidate").isObject()) {
            const auto candidate = data.value("candidate").toObject();
            const auto value = candidate.value("candidate").toString();
            const auto mid = candidate.value("sdpMid").toString();
            if (value.isEmpty()) {
                return; // End-of-candidates notification.
            }
            if (value.toUtf8().size() > MAX_CANDIDATE_BYTES || mid.size() > 64 ||
                connection->remoteCandidateCount >= MAX_CANDIDATES) {
                closeConnection(connection);
                return;
            }
            ++connection->remoteCandidateCount;
            connection->peer->addRemoteCandidate(rtc::Candidate(value.toStdString(), mid.toStdString()));
        }
    } catch (const std::exception&) {
        // SDP/ICE can contain private addresses and credentials; do not dump
        // their contents or library exception text.
        qCWarning(networking_webrtc) << "Rejected browser transport negotiation";
        if (connection) {
            closeConnection(connection);
        }
    }
}

bool WebRTCDataChannels::sendDataMessage(const SockAddr& destination, const QByteArray& message) {
    // Native audio/avatar mixers and UDT SendQueue may write from workers.
    const auto connection = findConnection(addressID(destination));
    if (!connection) {
        return false;
    }
    std::lock_guard<std::mutex> sendLock(connection->sendMutex);
    const auto channel = std::atomic_load(&connection->channel);
    if (!channel || !channel->isOpen() || message.isEmpty() ||
        message.size() > udt::MAX_PACKET_SIZE ||
        channel->bufferedAmount() + message.size() > udt::WEBRTC_SEND_BUFFER_SIZE_BYTES) {
        return false;
    }
    try {
        // A false library return means accepted but buffered, still a successful write.
        channel->send(reinterpret_cast<const rtc::byte*>(message.constData()), message.size());
        connection->lastActivity = monotonicMilliseconds();
        return true;
    } catch (const std::exception&) {
        post(_guard, connection, [](WebRTCDataChannels* owner, const ConnectionPtr& current) {
            owner->closeConnection(current);
        });
        return false;
    }
}

bool WebRTCDataChannels::isPeerOpen(const SockAddr& address) const {
    return !peerGeneration(address).isEmpty();
}

QString WebRTCDataChannels::peerGeneration(const SockAddr& address) const {
    if (address.getType() != SocketType::WebRTC) {
        return {};
    }
    const auto connection = findConnection(addressID(address));
    const auto channel = connection ? std::atomic_load(&connection->channel) : nullptr;
    return channel && channel->isOpen() ? connection->generation : QString();
}

qint64 WebRTCDataChannels::getBufferedAmount(const SockAddr& address) const {
    const auto connection = findConnection(addressID(address));
    const auto channel = connection ? std::atomic_load(&connection->channel) : nullptr;
    return channel ? static_cast<qint64>(channel->bufferedAmount()) : 0;
}

void WebRTCDataChannels::closeConnection(const ConnectionPtr& connection) {
    {
        std::lock_guard<std::mutex> lock(_connectionsMutex);
        if (_connections.value(connection->id) != connection) {
            return;
        }
        _connections.remove(connection->id);
    }
    if (const auto channel = std::atomic_load(&connection->channel)) {
        channel->resetCallbacks();
        channel->close();
    }
    connection->peer->resetCallbacks();
    connection->peer->close();
    emit peerClosed(connection->address);
}

void WebRTCDataChannels::reset() {
    QList<ConnectionPtr> connections;
    {
        std::lock_guard<std::mutex> lock(_connectionsMutex);
        connections = _connections.values();
    }
    for (const auto& connection : connections) {
        closeConnection(connection);
    }
}

void WebRTCDataChannels::expireConnections() {
    QList<ConnectionPtr> connections;
    {
        std::lock_guard<std::mutex> lock(_connectionsMutex);
        connections = _connections.values();
    }
    for (const auto& connection : connections) {
        if (monotonicMilliseconds() - connection->lastActivity > PEER_TIMEOUT_MS) {
            closeConnection(connection);
        }
    }
}

#endif // WEBRTC_DATA_CHANNELS
