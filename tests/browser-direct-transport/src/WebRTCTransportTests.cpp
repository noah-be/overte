// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0

#include <atomic>
#include <cstring>
#include <memory>
#include <thread>
#include <rtc/rtc.hpp>

#include <QtTest/QtTest>
#include <QElapsedTimer>
#include <QPointer>
#include <QWebSocket>
#include <QUdpSocket>

#include <LimitedNodeList.h>
#include <NLPacket.h>
#include <NLPacketList.h>
#include <webrtc/BrowserDatagramValidator.h>
#include <webrtc/WebRTCDataChannels.h>
#include <webrtc/WebRTCSignalingServer.h>
#include <webrtc/WebRTCSocket.h>
#include <udt/Constants.h>
#include <udt/NetworkSocket.h>

class WebRTCTransportTests : public QObject {
    Q_OBJECT
private slots:
    void socketBoundsAndReset();
    void browserDatagramHeaderBounds();
    void signalingAssignsSessionAndClosesTargets();
    void binaryDatagramRoundTripAndSessionIsolation();
    void admittedBrowserNodeCleanup();
    void queuedRepliesCannotCrossRtcGeneration();
    void nativeUdpCoexists();
};

class TestNodeList : public LimitedNodeList {
public:
    TestNodeList() : LimitedNodeList(0, INVALID_PORT) { }
    QObject* reliableQueueObject() { return &_nodeSocket; }
    qint64 sendPacketWithOverride(std::unique_ptr<NLPacket> packet, const Node& destination, const SockAddr& address) {
        return sendPacket(std::move(packet), destination, address);
    }
    void queueReliableDatagram(const SockAddr& address) {
        auto packet = NLPacket::create(PacketType::EntityQueryInitialResultsComplete, sizeof(quint16), true);
        packet->writePrimitive(quint16(7));
        _nodeSocket.writePacket(std::move(packet), address);
    }
    void queueReliableMessage(const SockAddr& address) {
        auto packets = NLPacketList::create(PacketType::BrowserEntityData, QByteArray(), true, true);
        packets->write(QByteArray("{}"));
        packets->closeCurrentPacket();
        _nodeSocket.writePacketList(std::move(packets), address);
    }
};

struct PeerCleanup {
    std::shared_ptr<rtc::PeerConnection> peer;
    std::shared_ptr<rtc::DataChannel> channel;
    ~PeerCleanup() {
        channel->resetCallbacks();
        peer->resetCallbacks();
        channel->close();
        peer->close();
    }
};

namespace {
class LocalSocketPeer {
public:
    LocalSocketPeer(WebRTCSocket& socket, const SockAddr& address, const QString& session) : _address(address) {
        rtc::Configuration config;
        config.bindAddress = "127.0.0.1";
        config.maxMessageSize = udt::MAX_PACKET_SIZE;
        peer = std::make_shared<rtc::PeerConnection>(config);
        const auto id = address.toShortString();
        QPointer<WebRTCSocket> guard(&socket);
        peer->onLocalDescription([context = &_relay, guard, id, session](rtc::Description description) {
            const auto sdp = QString::fromStdString(std::string(description));
            QMetaObject::invokeMethod(context, [guard, id, session, sdp] {
                if (guard) {
                    guard->onSignalingMessage({ { "from", id }, { "session", session }, { "to", "D" },
                        { "data", QJsonObject { { "description", QJsonObject { { "type", "offer" }, { "sdp", sdp } } } } } });
                }
            }, Qt::QueuedConnection);
        });
        peer->onLocalCandidate([context = &_relay, guard, id, session](rtc::Candidate candidate) {
            const auto value = QString::fromStdString(candidate.candidate());
            const auto mid = QString::fromStdString(candidate.mid());
            QMetaObject::invokeMethod(context, [guard, id, session, value, mid] {
                if (guard) {
                    guard->onSignalingMessage({ { "from", id }, { "session", session }, { "to", "D" },
                        { "data", QJsonObject { { "candidate", QJsonObject { { "candidate", value }, { "sdpMid", mid } } } } } });
                }
            }, Qt::QueuedConnection);
        });
        _signaling = QObject::connect(&socket, &WebRTCSocket::sendSignalingMessage, &_relay,
            [currentPeer = peer, id, session](const QJsonObject& message) {
                if (message.value("to").toString() != id || message.value("session").toString() != session) {
                    return;
                }
                const auto data = message.value("data").toObject();
                if (data.contains("description")) {
                    const auto description = data.value("description").toObject();
                    currentPeer->setRemoteDescription(rtc::Description(description.value("sdp").toString().toStdString(), "answer"));
                }
                if (data.contains("candidate")) {
                    const auto candidate = data.value("candidate").toObject();
                    currentPeer->addRemoteCandidate(rtc::Candidate(candidate.value("candidate").toString().toStdString(),
                        candidate.value("sdpMid").toString().toStdString()));
                }
            });
        rtc::DataChannelInit init;
        init.reliability.unordered = true;
        init.reliability.maxRetransmits = 0;
        channel = peer->createDataChannel("lifecycle", init);
        received = std::make_shared<std::atomic<int>>(0);
        channel->onMessage([count = received](rtc::message_variant) { ++*count; });
    }
    ~LocalSocketPeer() {
        QObject::disconnect(_signaling);
        channel->resetCallbacks();
        peer->resetCallbacks();
        channel->close();
        peer->close();
    }
    bool waitForOpenWithoutQueuedReliableWrites(WebRTCSocket& socket, int timeoutMS = 5000) {
        // Deliver only real SDP/ICE/library callbacks. In particular, leave
        // udt::Socket's worker-posted MetaCalls pending until the new peer opens.
        auto callbacks = socket.findChild<WebRTCDataChannels*>();
        if (!callbacks) {
            return false;
        }
        QElapsedTimer elapsed;
        elapsed.start();
        while (elapsed.elapsed() < timeoutMS) {
            QCoreApplication::sendPostedEvents(&_relay, QEvent::MetaCall);
            QCoreApplication::sendPostedEvents(callbacks, QEvent::MetaCall);
            if (channel->isOpen() && socket.isPeerOpen(_address)) {
                return true;
            }
            QThread::msleep(2);
        }
        return false;
    }
    std::shared_ptr<rtc::PeerConnection> peer;
    std::shared_ptr<rtc::DataChannel> channel;
    std::shared_ptr<std::atomic<int>> received;
private:
    SockAddr _address;
    QObject _relay;
    QMetaObject::Connection _signaling;
};

QByteArray datagramBytes(const udt::BasePacket& packet) {
    return QByteArray(packet.getData(), packet.getDataSize());
}

QByteArray wordBytes(uint32_t word) {
    QByteArray data(sizeof(word), '\0');
    std::memcpy(data.data(), &word, sizeof(word));
    return data;
}

QByteArray nativeHeader(PacketType type, bool reliable = false, bool message = false,
                       udt::Packet::ObfuscationLevel level = udt::Packet::NoObfuscation) {
    auto packet = NLPacket::create(type, -1, reliable, message);
    if (!PacketTypeEnum::getNonSourcedPackets().contains(type)) {
        packet->writeSourceID(7);
    }
    if (message) {
        packet->writeMessageNumber(1, udt::Packet::ONLY, 0);
    }
    packet->obfuscate(level);
    return datagramBytes(*packet);
}

QList<QByteArray> malformedDatagrams() {
    QList<QByteArray> datagrams { QByteArray(1, '\0'), QByteArray(2, '\0'), QByteArray(3, '\0'),
        wordBytes(0), wordBytes(udt::MESSAGE_BIT_MASK | udt::RELIABILITY_BIT_MASK) };
    const auto source = nativeHeader(PacketType::DomainDisconnectRequest);
    datagrams.append(source.left(source.size() - 1)); // Incomplete native LocalID.
    const auto verified = nativeHeader(PacketType::BrowserEntityQuery);
    datagrams.append(verified.left(verified.size() - 1)); // Incomplete native HMAC.
    const auto message = nativeHeader(PacketType::AvatarIdentity, true, true);
    datagrams.append(message.left(message.size() - 1));
    auto unsupportedMessage = message;
    uint32_t header;
    std::memcpy(&header, unsupportedMessage.constData(), sizeof(header));
    header &= ~udt::RELIABILITY_BIT_MASK;
    std::memcpy(unsupportedMessage.data(), &header, sizeof(header));
    datagrams.append(unsupportedMessage);
    auto unknownType = wordBytes(0);
    unknownType.append(char(255));
    unknownType.append(char(1));
    datagrams.append(unknownType);
    datagrams.append(wordBytes(udt::CONTROL_BIT_MASK | (4u << 16))); // Unknown control type.
    datagrams.append(wordBytes(udt::CONTROL_BIT_MASK | (3u << 16) | 1)); // Reserved control bits.
    auto handshake = udt::ControlPacket::create(udt::ControlPacket::Handshake, sizeof(udt::SequenceNumber));
    handshake->writePrimitive(udt::SequenceNumber(1));
    datagrams.append(datagramBytes(*handshake).left(handshake->getDataSize() - 1));
    auto invalidSequence = datagramBytes(*handshake);
    uint32_t outOfRangeSequence = ~uint32_t(0);
    std::memcpy(invalidSequence.data() + sizeof(uint32_t), &outOfRangeSequence, sizeof(outOfRangeSequence));
    datagrams.append(invalidSequence);
    return datagrams;
}
} // namespace

void WebRTCTransportTests::socketBoundsAndReset() {
    WebRTCSocket socket(nullptr);
    const SockAddr source(SocketType::WebRTC, QHostAddress::LocalHost, 48911);
    socket.onDataChannelReceivedMessage(source, QByteArray("ignored"));
    QVERIFY(!socket.hasPendingDatagrams());
    QVERIFY(socket.bind(QHostAddress::LocalHost));
    socket.onDataChannelReceivedMessage(source, QByteArray(udt::MAX_PACKET_SIZE + 1, 'x'));
    QVERIFY(!socket.hasPendingDatagrams());
    for (int i = 0; i < 2000; ++i) {
        socket.onDataChannelReceivedMessage(source, QByteArray(1024, 'q'));
    }
    QCOMPARE(socket.readDatagram(nullptr, -1), qint64(-1));
    QVERIFY(!socket.errorString().isEmpty());
    int count = 0;
    QByteArray buffer(1024, '\0');
    while (socket.hasPendingDatagrams()) {
        QHostAddress address;
        quint16 port = 0;
        QCOMPARE(socket.readDatagram(buffer.data(), buffer.size(), &address, &port), qint64(1024));
        QCOMPARE(address, source.getAddress());
        QCOMPARE(port, source.getPort());
        ++count;
    }
    QCOMPARE(count, udt::WEBRTC_RECEIVE_BUFFER_SIZE_BYTES / 1024);
    socket.onDataChannelReceivedMessage(source, QByteArray("old-session"));
    socket.abort();
    QVERIFY(!socket.hasPendingDatagrams());
    QCOMPARE(socket.state(), QAbstractSocket::UnconnectedState);
    QCOMPARE(socket.writeDatagram(QByteArray("unconnected"), source), qint64(-1));
    QVERIFY(!socket.errorString().isEmpty());
}

void WebRTCTransportTests::browserDatagramHeaderBounds() {
    QVERIFY(!isBrowserDatagramValid(nullptr, 4));
    const auto sample = nativeHeader(PacketType::Ping);
    QVERIFY(!isBrowserDatagramValid(sample.constData(), -1));
    QVERIFY(!isBrowserDatagramValid(sample.constData(), udt::MAX_PACKET_SIZE + 1));
    for (const auto& malformed : malformedDatagrams()) {
        QVERIFY(!isBrowserDatagramValid(malformed.constData(), malformed.size()));
    }
    // Native serialization supplies independent expected framing for every
    // supported type, source/hash classification and retransmission level.
    for (int value = 0; value < static_cast<int>(PacketType::NUM_PACKET_TYPE); ++value) {
        const auto type = static_cast<PacketType>(value);
        if (!isBrowserPacketAllowed(type)) {
            const auto forbidden = nativeHeader(type);
            QVERIFY(!isBrowserDatagramValid(forbidden.constData(), forbidden.size()));
            continue;
        }
        for (const bool message : { false, true }) {
            for (int level = 0; level < 4; ++level) {
                const auto bytes = nativeHeader(type, message, message,
                    static_cast<udt::Packet::ObfuscationLevel>(level));
                QVERIFY(isBrowserDatagramValid(bytes.constData(), bytes.size()));
                for (int size = 0; size < bytes.size(); ++size) {
                    QVERIFY(!isBrowserDatagramValid(bytes.constData(), size));
                }
                const auto unaligned = QByteArray("!") + bytes;
                QVERIFY(isBrowserDatagramValid(unaligned.constData() + 1, bytes.size()));
            }
        }
        const auto reliable = nativeHeader(type, true);
        QVERIFY(isBrowserDatagramValid(reliable.constData(), reliable.size()));
    }
    for (const auto type : { udt::ControlPacket::ACK, udt::ControlPacket::Handshake,
                            udt::ControlPacket::HandshakeACK, udt::ControlPacket::HandshakeRequest }) {
        const bool request = type == udt::ControlPacket::HandshakeRequest;
        auto control = udt::ControlPacket::create(type, request ? 0 : sizeof(udt::SequenceNumber));
        if (!request) {
            control->writePrimitive(udt::SequenceNumber(udt::SequenceNumber::MAX));
        }
        const auto bytes = datagramBytes(*control);
        QVERIFY(isBrowserDatagramValid(bytes.constData(), bytes.size()));
        for (int size = 0; size < bytes.size(); ++size) {
            QVERIFY(!isBrowserDatagramValid(bytes.constData(), size));
        }
        const auto trailing = bytes + QByteArray("x");
        QVERIFY(!isBrowserDatagramValid(trailing.constData(), trailing.size()));
    }
}

void WebRTCTransportTests::signalingAssignsSessionAndClosesTargets() {
    WebRTCSignalingServer server(nullptr, false);
    QVERIFY(server.bind(QHostAddress::LocalHost, 0));
    QSignalSpy received(&server, &WebRTCSignalingServer::messageReceived);
    QSignalSpy closed(&server, &WebRTCSignalingServer::sessionClosed);
    QWebSocket first;
    QWebSocket second;
    QSignalSpy replies(&first, &QWebSocket::textMessageReceived);
    const QUrl url(QString("ws://127.0.0.1:%1").arg(server.localPort()));
    first.open(url);
    second.open(url);
    QTRY_COMPARE_WITH_TIMEOUT(first.state(), QAbstractSocket::ConnectedState, 3000);
    QTRY_COMPARE_WITH_TIMEOUT(second.state(), QAbstractSocket::ConnectedState, 3000);
    first.sendTextMessage("{\"to\":\"D\",\"from\":\"203.0.113.12:9\",\"session\":\"forged\",\"data\":{\"candidate\":{}}}");
    second.sendTextMessage("{\"to\":\"D\",\"data\":{\"candidate\":{}}}");
    QTRY_COMPARE_WITH_TIMEOUT(received.count(), 2, 3000);
    const auto initial = received.at(0).at(0).toJsonObject();
    const auto other = received.at(1).at(0).toJsonObject();
    QVERIFY(initial.value("from").toString() != "203.0.113.12:9");
    QCOMPARE(initial.value("session").toString().size(), 36);
    QVERIFY(initial.value("session") != other.value("session"));
    const auto firstAddress = QString("127.0.0.1:%1").arg(first.localPort());
    // The two asynchronous arrivals need not have the same order as open().
    const auto firstMessage = initial.value("from").toString() == firstAddress ? initial : other;
    const auto session = firstMessage.value("session").toString();
    first.sendTextMessage("{\"to\":\"A\",\"data\":{\"candidate\":{}}}");
    QTRY_COMPARE_WITH_TIMEOUT(received.count(), 3, 3000);
    server.sendMessage({ { "to", firstAddress }, { "session", "stale" }, { "echo", true } });
    server.sendMessage({ { "to", firstAddress }, { "session", session }, { "echo", true } });
    QTRY_COMPARE_WITH_TIMEOUT(replies.count(), 1, 3000);
    first.close();
    QTRY_COMPARE_WITH_TIMEOUT(closed.count(), 1, 3000);
    QTRY_COMPARE_WITH_TIMEOUT(received.count(), 5, 3000);
    QSet<QString> closedTargets;
    for (int i = 3; i < received.count(); ++i) {
        const auto message = received.at(i).at(0).toJsonObject();
        QCOMPARE(message.value("from").toString(), firstAddress);
        QCOMPARE(message.value("session").toString(), session);
        QVERIFY(message.value("data").toObject().value("close").toBool());
        closedTargets.insert(message.value("to").toString());
    }
    QCOMPARE(closedTargets, QSet<QString>({ "D", "A" }));
    const auto address = qvariant_cast<SockAddr>(closed.at(0).at(0));
    QCOMPARE(address.getType(), SocketType::WebRTC);
    QCOMPARE(address.toShortString(), firstAddress);
    QCOMPARE(second.state(), QAbstractSocket::ConnectedState);
    second.close();
}

void WebRTCTransportTests::binaryDatagramRoundTripAndSessionIsolation() {
    WebRTCDataChannels server(nullptr);
    QObject relay;
    const QString id("127.0.0.1:48921");
    const QString session("134eed2b-9f58-460d-b780-7e4cedda6159");
    const SockAddr address(SocketType::WebRTC, QHostAddress::LocalHost, 48921);
    auto ping = NLPacket::create(PacketType::Ping);
    ping->writeSourceID(7);
    QCOMPARE(ping->write(QByteArray("native\0packet", 13)), qint64(13));
    const auto payload = datagramBytes(*ping);
    QByteArray received;
    QList<QByteArray> receivedDatagrams;
    bool correctThread = false;
    QSignalSpy closed(&server, &WebRTCDataChannels::peerClosed);
    connect(&server, &WebRTCDataChannels::dataMessage, &relay, [&](const SockAddr& source, const QByteArray& bytes) {
        received = bytes;
        receivedDatagrams.append(bytes);
        correctThread = QThread::currentThread() == server.thread() && source == address;
    });
    rtc::Configuration config;
    config.bindAddress = "127.0.0.1";
    config.maxMessageSize = udt::MAX_PACKET_SIZE;
    auto peer = std::make_shared<rtc::PeerConnection>(config);
    auto remoteReceived = std::make_shared<std::atomic<bool>>(false);
    peer->onLocalDescription([&relay, &server, id, session](rtc::Description description) {
        const auto sdp = QString::fromStdString(std::string(description));
        QMetaObject::invokeMethod(&relay, [&server, id, session, sdp] {
            server.onSignalingMessage({ { "from", id }, { "session", session }, { "to", "D" },
                { "data", QJsonObject { { "description", QJsonObject { { "type", "offer" }, { "sdp", sdp } } } } } });
        }, Qt::QueuedConnection);
    });
    peer->onLocalCandidate([&relay, &server, id, session](rtc::Candidate candidate) {
        const auto value = QString::fromStdString(candidate.candidate());
        const auto mid = QString::fromStdString(candidate.mid());
        QMetaObject::invokeMethod(&relay, [&server, id, session, value, mid] {
            server.onSignalingMessage({ { "from", id }, { "session", session }, { "to", "D" },
                { "data", QJsonObject { { "candidate", QJsonObject { { "candidate", value }, { "sdpMid", mid } } } } } });
        }, Qt::QueuedConnection);
    });
    connect(&server, &WebRTCDataChannels::signalingMessage, &relay, [peer](const QJsonObject& message) {
        const auto data = message.value("data").toObject();
        if (data.contains("description")) {
            const auto description = data.value("description").toObject();
            peer->setRemoteDescription(rtc::Description(description.value("sdp").toString().toStdString(), "answer"));
        }
        if (data.contains("candidate")) {
            const auto candidate = data.value("candidate").toObject();
            peer->addRemoteCandidate(rtc::Candidate(candidate.value("candidate").toString().toStdString(),
                                                    candidate.value("sdpMid").toString().toStdString()));
        }
    });
    rtc::DataChannelInit init;
    init.reliability.unordered = true;
    init.reliability.maxRetransmits = 0;
    auto channel = peer->createDataChannel("label", init);
    channel->onMessage([remoteReceived, payload](rtc::message_variant message) {
        const auto bytes = std::get_if<rtc::binary>(&message);
        if (bytes && QByteArray(reinterpret_cast<const char*>(bytes->data()), bytes->size()) == payload) {
            *remoteReceived = true;
        }
    });
    PeerCleanup cleanup { peer, channel };
    QTRY_VERIFY_WITH_TIMEOUT(channel->isOpen(), 5000);
    for (const auto& malformed : malformedDatagrams()) {
        channel->send(reinterpret_cast<const rtc::byte*>(malformed.constData()), malformed.size());
    }
    channel->send(reinterpret_cast<const rtc::byte*>(payload.constData()), payload.size());
    QTRY_COMPARE_WITH_TIMEOUT(received, payload, 3000);
    QTest::qWait(50);
    QCOMPARE(receivedDatagrams, QList<QByteArray>({ payload }));
    QVERIFY(correctThread);
    // Actual incoming RTC also passes native reliable ordered retransmissions
    // and every UDT control packet; malformed peers do not poison the channel.
    QList<QByteArray> validDatagrams;
    for (const auto type : { udt::ControlPacket::ACK, udt::ControlPacket::Handshake,
                            udt::ControlPacket::HandshakeACK, udt::ControlPacket::HandshakeRequest }) {
        const bool request = type == udt::ControlPacket::HandshakeRequest;
        auto control = udt::ControlPacket::create(type, request ? 0 : sizeof(udt::SequenceNumber));
        if (!request) {
            control->writePrimitive(udt::SequenceNumber(1));
        }
        validDatagrams.append(datagramBytes(*control));
    }
    for (int level = 0; level < 4; ++level) {
        validDatagrams.append(nativeHeader(PacketType::AssetMappingOperation, true, true,
            static_cast<udt::Packet::ObfuscationLevel>(level)));
    }
    for (const auto& bytes : validDatagrams) {
        channel->send(reinterpret_cast<const rtc::byte*>(bytes.constData()), bytes.size());
    }
    QTRY_COMPARE_WITH_TIMEOUT(receivedDatagrams.size(), 1 + validDatagrams.size(), 3000);
    for (const auto& bytes : validDatagrams) {
        QVERIFY(receivedDatagrams.contains(bytes));
    }
    server.onSignalingMessage({ { "from", id }, { "session", "ae46d65c-3a6f-433b-8078-56f56cba0293" }, { "to", "D" },
                                { "data", QJsonObject { { "close", true } } } });
    QVERIFY(server.sendDataMessage(address, payload));
    QTRY_VERIFY_WITH_TIMEOUT(remoteReceived->load(), 3000);
    *remoteReceived = false;
    bool workerWrite = false;
    std::thread writer([&] { workerWrite = server.sendDataMessage(address, payload); });
    writer.join();
    QVERIFY(workerWrite);
    QTRY_VERIFY_WITH_TIMEOUT(remoteReceived->load(), 3000);
    QCOMPARE(closed.count(), 0);
    received.clear();
    for (int i = 0; i < 32; ++i) {
        channel->send(reinterpret_cast<const rtc::byte*>(payload.constData()), payload.size());
    }
    server.onSignalingMessage({ { "from", id }, { "session", session }, { "to", "D" },
                                { "data", QJsonObject { { "close", true } } } });
    QCOMPARE(closed.count(), 1);
    QVERIFY(!server.sendDataMessage(address, payload));
    QTest::qWait(25);
    QVERIFY(received.isEmpty()); // Queued callbacks from the closed session are discarded.
}

void WebRTCTransportTests::admittedBrowserNodeCleanup() {
    TestNodeList nodes;
    auto socket = const_cast<WebRTCSocket*>(nodes.getWebRTCSocket());
    QUdpSocket receiver;
    QVERIFY(receiver.bind(QHostAddress(QHostAddress::LocalHost), quint16(0)));
    const SockAddr nativeAddress(SocketType::UDP, QHostAddress::LocalHost, receiver.localPort());
    const SockAddr browserAddress(SocketType::WebRTC, QHostAddress::LocalHost, receiver.localPort());
    const auto nativeID = QUuid::createUuid();
    const auto browserID = QUuid::createUuid();
    auto native = nodes.addOrUpdateNode(nativeID, NodeType::Agent, nativeAddress, nativeAddress, 1);
    native->activatePublicSocket();
    const QString firstSession("669ecfd2-9cc6-45ef-989e-ceb0cc272cf3");
    const QString secondSession("7d2c2435-54b4-4a1a-afc5-170c101e884a");
    const QString thirdSession("7e9c8401-43b9-4229-9252-cf9cba7a86cf");
    QSignalSpy closed(socket, &WebRTCSocket::peerClosed);
    const auto closeSession = [&](const QString& session) {
        socket->onSignalingMessage({ { "from", browserAddress.toShortString() }, { "session", session }, { "to", "D" },
                                    { "data", QJsonObject { { "close", true } } } });
    };
    LocalSocketPeer first(*socket, browserAddress, firstSession);
    QTRY_VERIFY_WITH_TIMEOUT(first.channel->isOpen() && socket->isPeerOpen(browserAddress), 5000);
    // This browser is admitted but has not completed native socket activation.
    nodes.addOrUpdateNode(browserID, NodeType::Agent, browserAddress, browserAddress, 2);
    nodes.queueReliableDatagram(nativeAddress);
    nodes.queueReliableDatagram(browserAddress);
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(2));
    QTRY_VERIFY_WITH_TIMEOUT(first.received->load() > 0, 1000);
    closeSession(firstSession);
    QCOMPARE(closed.count(), 1);
    QVERIFY(!socket->isPeerOpen(browserAddress));
    QVERIFY(!nodes.nodeWithUUID(browserID));
    QVERIFY(nodes.nodeWithUUID(nativeID));
    const auto remainingConnections = nodes.sampleStatsForAllConnections();
    QCOMPARE(remainingConnections.size(), size_t(1));
    QCOMPARE(remainingConnections.front().first, nativeAddress);

    const auto replacementID = QUuid::createUuid();
    LocalSocketPeer second(*socket, browserAddress, secondSession);
    QTRY_VERIFY_WITH_TIMEOUT(second.channel->isOpen() && socket->isPeerOpen(browserAddress), 5000);
    auto replacement = nodes.addOrUpdateNode(replacementID, NodeType::Agent, browserAddress, browserAddress, 3);
    nodes.queueReliableDatagram(browserAddress);
    nodes.queueReliableMessage(browserAddress);
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(2));
    socket->peerClosed(SockAddr(SocketType::WebRTC, QHostAddress::LocalHost, 1));
    socket->peerClosed(nativeAddress);
    QVERIFY(nodes.nodeWithUUID(replacementID));
    QVERIFY(nodes.nodeWithUUID(nativeID));
    // Domain removal can precede RTC close. This inactive Agent has a reliable
    // reply waiting for its UDT handshake, which handleNodeKill cannot identify
    // through an active socket. Close must still retire the exact connection.
    QVERIFY(!replacement->getActiveSocket());
    QVERIFY(nodes.killNodeWithUUID(replacementID));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(2));
    // Model an asset worker that posts both kinds of reliable replies before
    // close; they execute on the owning thread only after the channel is gone.
    std::thread writer([&] {
        nodes.queueReliableDatagram(browserAddress);
        nodes.queueReliableMessage(browserAddress);
    });
    writer.join();
    closeSession(secondSession);
    QVERIFY(!nodes.nodeWithUUID(replacementID));
    QVERIFY(nodes.nodeWithUUID(nativeID));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1));
    QCoreApplication::processEvents();
    nodes.queueReliableDatagram(browserAddress);
    nodes.queueReliableMessage(browserAddress);
    QCoreApplication::processEvents();
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1));

    const auto serverID = QUuid::createUuid();
    LocalSocketPeer third(*socket, browserAddress, thirdSession);
    QTRY_VERIFY_WITH_TIMEOUT(third.channel->isOpen() && socket->isPeerOpen(browserAddress), 5000);
    nodes.addOrUpdateNode(serverID, NodeType::EntityServer, browserAddress, browserAddress, 4);
    nodes.queueReliableDatagram(browserAddress);
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(2));
    // Old signaling and pending library callbacks cannot close a replacement
    // at the same address or clear that current generation's reliable state.
    closeSession(secondSession);
    QTest::qWait(25);
    QVERIFY(socket->isPeerOpen(browserAddress));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(2));
    // Two deliberately emitted invalid-address signals above do not represent
    // actual RTC closes; compare only the number of current-generation closes.
    QCOMPARE(closed.count(), 4);
    closeSession(thirdSession);
    QVERIFY(!socket->isPeerOpen(browserAddress));
    QVERIFY(nodes.nodeWithUUID(serverID)); // Browser lifecycle never kills a server node.
    QVERIFY(nodes.nodeWithUUID(nativeID));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1));
    nodes.reset("transport test complete");
}

void WebRTCTransportTests::queuedRepliesCannotCrossRtcGeneration() {
    TestNodeList nodes;
    nodes.setAuthenticatePackets(false); // Session ownership cannot rely on HMAC being enabled.
    auto socket = const_cast<WebRTCSocket*>(nodes.getWebRTCSocket());
    QUdpSocket receiver;
    QVERIFY(receiver.bind(QHostAddress(QHostAddress::LocalHost), quint16(0)));
    const SockAddr nativeAddress(SocketType::UDP, QHostAddress::LocalHost, receiver.localPort());
    const SockAddr browserAddress(SocketType::WebRTC, QHostAddress::LocalHost, receiver.localPort());
    auto native = nodes.addOrUpdateNode(QUuid::createUuid(), NodeType::Agent, nativeAddress, nativeAddress, 1);
    native->activatePublicSocket();
    nodes.queueReliableDatagram(nativeAddress);
    const auto browserID = QUuid::createUuid();
    const QString signalingSession("30d27652-71db-4810-9cfa-d3b4a1416a2b");
    const auto closePeer = [&] {
        socket->onSignalingMessage({ { "from", browserAddress.toShortString() }, { "session", signalingSession }, { "to", "D" },
                                    { "data", QJsonObject { { "close", true } } } });
    };
    auto first = std::make_unique<LocalSocketPeer>(*socket, browserAddress, signalingSession);
    QTRY_VERIFY_WITH_TIMEOUT(first->channel->isOpen() && socket->isPeerOpen(browserAddress), 5000);
    const auto firstGeneration = socket->peerGeneration(browserAddress);
    QVERIFY(!firstGeneration.isEmpty());
    auto retained = nodes.addOrUpdateNode(browserID, NodeType::Agent, browserAddress, browserAddress, 2);
    retained->activatePublicSocket();
    const auto packet = [](bool reliable) {
        auto result = NLPacket::create(PacketType::EntityQueryInitialResultsComplete, sizeof(quint16), reliable);
        result->writePrimitive(quint16(7));
        return result;
    };
    const auto message = [](bool reliable) {
        auto result = NLPacketList::create(PacketType::BrowserEntityData, QByteArray(), reliable, reliable);
        result->write(QByteArray("{}"));
        return result;
    };
    qint64 queuedPacket = -1;
    qint64 queuedMessage = -1;
    std::thread queuedWriter([&] {
        queuedPacket = nodes.sendPacket(packet(true), *retained);
        queuedMessage = nodes.sendPacketList(message(true), *retained);
    });
    queuedWriter.join();
    QVERIFY(queuedPacket > 0);
    QCOMPARE(queuedMessage, qint64(0));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1)); // Both RTC writes are still posted.
    closePeer();
    QVERIFY(!nodes.nodeWithUUID(browserID));
    QVERIFY(!socket->isPeerOpen(browserAddress));
    first.reset();
    // A browser may reoffer a service channel on the same WebSocket. Its
    // signaling session stays unchanged, but its native connection must not.
    LocalSocketPeer second(*socket, browserAddress, signalingSession);
    QVERIFY(second.waitForOpenWithoutQueuedReliableWrites(*socket));
    const auto secondGeneration = socket->peerGeneration(browserAddress);
    QVERIFY(!secondGeneration.isEmpty());
    QVERIFY(secondGeneration != firstGeneration);
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1));
    QCoreApplication::sendPostedEvents(nodes.reliableQueueObject(), QEvent::MetaCall);
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1)); // Old Packet and PacketList cannot create a new queue.
    QCOMPARE(second.received->load(), 0);

    // This models a retained SendAssetTask/mixer node that constructs its
    // reply only after reopen. Check every Node send overload on a worker.
    const auto expectRetainedReplyRejected = [&] {
        qint64 reliablePacket = 0, reliableMessage = 0, unreliablePacket = 0, unreliableMessage = 0, overriddenPacket = 0;
        std::thread lateWriter([&] {
            reliablePacket = nodes.sendPacket(packet(true), *retained);
            reliableMessage = nodes.sendPacketList(message(true), *retained);
            auto unreliable = packet(false);
            unreliablePacket = nodes.sendUnreliablePacket(*unreliable, *retained);
            auto packets = message(false);
            unreliableMessage = nodes.sendUnreliableUnorderedPacketList(*packets, *retained);
            overriddenPacket = nodes.sendPacketWithOverride(packet(true), *retained, browserAddress);
        });
        lateWriter.join();
        QCOMPARE(reliablePacket, qint64(-1));
        QCOMPARE(reliableMessage, qint64(-1));
        QCOMPARE(unreliablePacket, qint64(-1));
        QCOMPARE(unreliableMessage, qint64(-1));
        QCOMPARE(overriddenPacket, qint64(-1));
        QCoreApplication::sendPostedEvents(nodes.reliableQueueObject(), QEvent::MetaCall);
        QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1));
    };
    expectRetainedReplyRejected();
    // Even reusing the same native UUID cannot make the removed Node object
    // authoritative for a new generation at the same signaling address.
    auto current = nodes.addOrUpdateNode(browserID, NodeType::Agent, browserAddress, browserAddress, 3);
    current->activatePublicSocket();
    QVERIFY(current.data() != retained.data());
    expectRetainedReplyRejected();
    QVERIFY(nodes.sendPacket(packet(true), *current) > 0);
    QCOMPARE(nodes.sendPacketList(message(true), *current), qint64(0));
    QVERIFY(nodes.sendPacket(packet(true), *native) > 0);
    QCOMPARE(nodes.sendPacketList(message(true), *native), qint64(0));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(2));
    QTRY_VERIFY_WITH_TIMEOUT(second.received->load() > 0, 1000);
    closePeer();
    QVERIFY(!nodes.nodeWithUUID(browserID));
    QVERIFY(nodes.nodeWithUUID(native->getUUID()));
    QCOMPARE(nodes.sampleStatsForAllConnections().size(), size_t(1));
    nodes.reset("generation test complete");
}

void WebRTCTransportTests::nativeUdpCoexists() {
    NetworkSocket socket(nullptr);
    socket.bind(SocketType::UDP, QHostAddress::LocalHost, 0);
    socket.bind(SocketType::WebRTC, QHostAddress::LocalHost, 0);
    auto browserSocket = const_cast<WebRTCSocket*>(socket.getWebRTCSocket());
    const SockAddr browserAddress(SocketType::WebRTC, QHostAddress::LocalHost, 48931);
    browserSocket->onDataChannelReceivedMessage(browserAddress, QByteArray("browser"));
    QUdpSocket native;
    QCOMPARE(native.writeDatagram("native", QHostAddress::LocalHost, socket.localPort(SocketType::UDP)), qint64(6));
    QSet<int> types;
    for (int i = 0; i < 2; ++i) {
        QTRY_VERIFY_WITH_TIMEOUT(socket.hasPendingDatagrams(), 2000);
        QByteArray buffer(socket.pendingDatagramSize(), '\0');
        SockAddr source;
        QCOMPARE(socket.readDatagram(buffer.data(), buffer.size(), &source), qint64(buffer.size()));
        if (source.getType() == SocketType::WebRTC) {
            QCOMPARE(source, browserAddress);
            QCOMPARE(buffer, QByteArray("browser"));
        } else {
            QCOMPARE(source.getType(), SocketType::UDP);
            QCOMPARE(buffer, QByteArray("native"));
        }
        types.insert(static_cast<int>(source.getType()));
    }
    QCOMPARE(types.size(), 2);
}

QTEST_GUILESS_MAIN(WebRTCTransportTests)
#include "WebRTCTransportTests.moc"
