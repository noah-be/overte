// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
#include <QtTest/QtTest>
#include <QFile>
#include <QJsonDocument>
#include <QDataStream>
#include <QEvent>
#include <QSettings>
#include <QTemporaryDir>
#include <QTimer>
#include <QUdpSocket>
#include <LimitedNodeList.h>
#include <NodeList.h>
#include <NLPacketList.h>
#include <NLPacket.h>
#include <ReceivedMessage.h>
#include <ByteRange.h>
#include <BrowserPacketPolicy.h>
#include <NodeSocketAddress.h>
#include <ObservedLoopbackSocketPolicy.h>
#include <udt/ControlPacket.h>
#include <udt/Socket.h>
#include "../../../../assignment-client/src/AssignmentMonitorPolicy.h"
#include "../../../../assignment-client/src/entities/BrowserEntityProjection.h"
#include "../../../../domain-server/src/LocalUserPolicy.h"
#include <initializer_list>
#include <cstring>
#include <thread>

namespace {
class ScopedEnvironment {
public:
    ScopedEnvironment(const char* name, const QByteArray& value) :
        _name(name), _previous(qgetenv(name)), _wasSet(qEnvironmentVariableIsSet(name)) {
        qputenv(_name, value);
    }
    ~ScopedEnvironment() {
        if (_wasSet) { qputenv(_name, _previous); }
        else { qunsetenv(_name); }
    }
private:
    const char* _name;
    QByteArray _previous;
    bool _wasSet;
};

class ProjectionNodeList : public LimitedNodeList {
public:
    ProjectionNodeList() : LimitedNodeList(0, INVALID_PORT) { }
    using LimitedNodeList::setLocalSocket;
};

class ScopedNativeNodeList {
public:
    ScopedNativeNodeList() {
        DependencyManager::registerInheritance<LimitedNodeList, NodeList>();
        nodes = DependencyManager::set<NodeList>(NodeType::EntityServer, 0);
        nodes->setClientTransportVisibility(false);
        // The loopback fixture needs neither STUN nor periodic discovery. Stop
        // constructor timers and disconnect pending STUN lookup callbacks so
        // this test never sends a datagram to an external service.
        QObject::disconnect(&nodes->getSTUNSockAddr(), nullptr, nullptr, nullptr);
        for (auto timer : nodes->findChildren<QTimer*>()) {
            timer->stop();
        }
    }
    ~ScopedNativeNodeList() {
        nodes->reset("loopback endpoint regression", true);
        nodes.clear();
        DependencyManager::destroy<NodeList>();
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    }
    QSharedPointer<NodeList> nodes;
};
}

class BrowserEntityProjectionTests : public QObject {
    Q_OBJECT
private:
    QTemporaryDir _settingsDirectory;
private slots:
    void initTestCase() {
        QVERIFY(_settingsDirectory.isValid());
        QCoreApplication::setOrganizationName("OverteBrowserDirectTests");
        QCoreApplication::setApplicationName("BrowserEntityProjectionTests");
        // This process does not initialize Setting::Manager. Also isolate any
        // QSettings path so the production port setter cannot touch user config.
        for (const auto format : { QSettings::NativeFormat, QSettings::IniFormat }) {
            QSettings::setPath(format, QSettings::UserScope, _settingsDirectory.path());
            QSettings::setPath(format, QSettings::SystemScope, _settingsDirectory.path());
        }
        qRegisterMetaType<SockAddr>();
    }
    void explicitUdpAddressDoesNotFallBackToAny() {
        QCOMPARE(nodeUdpBindAddress(QString()), QHostAddress(QHostAddress::AnyIPv4));
        QCOMPARE(nodeUdpBindAddress("127.0.0.3"), QHostAddress("127.0.0.3"));
        QCOMPARE(nodeUdpBindAddress("0.0.0.0"), QHostAddress(QHostAddress::AnyIPv4));
        for (const auto& invalid : {"localhost", "not-an-address", "::1", "192.0.2.999"}) {
            QVERIFY(nodeUdpBindAddress(invalid).isNull());
        }
    }
    void monitorTargetFollowsExplicitBindOnly() {
        const QHostAddress localhost(QHostAddress::LocalHost);
        QCOMPARE(nodeMonitorAddress(QString()), localhost);
        QCOMPARE(nodeMonitorAddress("0.0.0.0"), localhost);
        QCOMPARE(nodeMonitorAddress("127.0.0.3"), QHostAddress("127.0.0.3"));
        QCOMPARE(nodeMonitorAddress("192.0.2.3"), QHostAddress("192.0.2.3"));
        QVERIFY(nodeMonitorAddress("not-an-address").isNull());
        QVERIFY(nodeMonitorAddress("::1").isNull());
    }
    void sameAddressPortUpdateDoesNotResetTheNativeSocket() {
        ScopedEnvironment environment("OVERTE_NODE_UDP_ADDRESS", "127.0.0.3");
        const QHostAddress alias("127.0.0.3");
        ProjectionNodeList nodes;
        const auto boundPort = nodes.getSocketLocalPort(SocketType::UDP);
        QVERIFY(boundPort != 0);
        QCOMPARE(nodes.getLocalSockAddr().getAddress(), alias);
        QCOMPARE(nodes.getLocalSockAddr().getPort(), boundPort);
        QSignalSpy changed(&nodes, &LimitedNodeList::localSockAddrChanged);
        const auto replacement = quint16(boundPort == 65535 ? boundPort - 1 : boundPort + 1);
        nodes.setLocalSocket(SockAddr(SocketType::UDP, alias, replacement));
        QCOMPARE(nodes.getLocalSockAddr().getPort(), replacement);
        QCOMPARE(nodes.getSocketLocalPort(SocketType::UDP), boundPort);
        QCOMPARE(changed.count(), 1);
        QCOMPARE(qvariant_cast<SockAddr>(changed.at(0).at(0)), nodes.getLocalSockAddr());
        nodes.updateLocalSocket();
        QCOMPARE(nodes.getLocalSockAddr().getPort(), boundPort);
        QCOMPARE(changed.count(), 2);
        nodes.updateLocalSocket();
        QCOMPARE(changed.count(), 2);
    }
    void explicitRebindRefreshesTheAdvertisedPortOnTheOwningThread() {
        ScopedEnvironment environment("OVERTE_NODE_UDP_ADDRESS", "127.0.0.3");
        const QHostAddress alias("127.0.0.3");
        ProjectionNodeList nodes;
        const auto originalPort = nodes.getSocketLocalPort(SocketType::UDP);
        QVERIFY(originalPort != 0);
        QUdpSocket reservation;
        QVERIFY(reservation.bind(alias, quint16(0)));
        const auto nextPort = reservation.localPort();
        QVERIFY(nextPort != originalPort);
        reservation.close();
        QSignalSpy changed(&nodes, &LimitedNodeList::localSockAddrChanged);
        std::thread caller([&] { nodes.setSocketLocalPort(SocketType::UDP, nextPort); });
        caller.join();
        QCOMPARE(nodes.getSocketLocalPort(SocketType::UDP), originalPort);
        QCOMPARE(changed.count(), 0);
        QTRY_COMPARE_WITH_TIMEOUT(nodes.getSocketLocalPort(SocketType::UDP), nextPort, 1000);
        QCOMPARE(nodes.getLocalSockAddr().getAddress(), alias);
        QCOMPARE(nodes.getLocalSockAddr().getPort(), nextPort);
        QCOMPARE(changed.count(), 1);
        QCOMPARE(qvariant_cast<SockAddr>(changed.at(0).at(0)), nodes.getLocalSockAddr());
        nodes.updateLocalSocket();
        QCOMPARE(changed.count(), 1);
    }
    void explicitUdpSourceSurvivesRebind() {
        const QHostAddress alias("127.0.0.3");
        udt::Socket socket;
        socket.bind(SocketType::UDP, alias, 0);
        QVERIFY(socket.localPort(SocketType::UDP) != 0);
        QUdpSocket receiver;
        QVERIFY(receiver.bind(QHostAddress(QHostAddress::LocalHost), quint16(0)));
        const auto destination = SockAddr(SocketType::UDP, QHostAddress::LocalHost, receiver.localPort());
        for (int attempt = 0; attempt < 2; ++attempt) {
            QCOMPARE(socket.writeDatagram(QByteArray("native-source"), destination), qint64(13));
            QVERIFY(receiver.waitForReadyRead(1000));
            QHostAddress source;
            QByteArray bytes(static_cast<int>(receiver.pendingDatagramSize()), Qt::Uninitialized);
            QCOMPARE(receiver.readDatagram(bytes.data(), bytes.size(), &source), qint64(13));
            QCOMPARE(bytes, QByteArray("native-source"));
            QCOMPARE(source, alias);
            if (attempt == 0) {
                socket.rebind(SocketType::UDP, 0);
                QVERIFY(socket.localPort(SocketType::UDP) != 0);
            }
        }
    }
    void browserFixturesMatchNativeWireFormats() {
        QFile file(QFINDTESTDATA("../../../browser-direct-client/tests/fixtures/native-wire.json"));
        QVERIFY(file.open(QIODevice::ReadOnly));
        const auto fixtures = QJsonDocument::fromJson(file.readAll()).object();
        const auto stringFixture = fixtures.value("packetString").toObject();
        auto strings = NLPacketList::create(PacketType::AssetMappingOperation, {}, true, true);
        strings->writeString(stringFixture.value("text").toString());
        strings->closeCurrentPacket();
        QCOMPARE(strings->getMessage().toHex(), stringFixture.value("hex").toString().toUtf8());

        const auto assetFixture = fixtures.value("assetGet").toObject();
        auto asset = NLPacket::create(PacketType::AssetGet, 52, true);
        asset->writePrimitive(static_cast<quint32>(assetFixture.value("id").toDouble()));
        asset->write(QByteArray::fromHex(assetFixture.value("hash").toString().toUtf8()));
        ByteRange range;
        QVERIFY(range.isValid());
        QVERIFY(!range.isSet());
        asset->writePrimitive(range.fromInclusive);
        asset->writePrimitive(range.toExclusive);
        QCOMPARE(QByteArray(asset->getPayload(), asset->getPayloadSize()).toHex(),
            assetFixture.value("hex").toString().toUtf8());

        const auto identity = fixtures.value("avatarIdentity").toObject();
        QByteArray identityBytes;
        QDataStream stream(&identityBytes, QIODevice::WriteOnly);
        stream << QUuid(identity.value("uuid").toString())
            << static_cast<quint32>(identity.value("sequence").toDouble())
            << identity.value("displayName").toString()
            << identity.value("sessionDisplayName").toString() << quint32(0);
        QCOMPARE(identityBytes.toHex(), identity.value("hex").toString().toUtf8());

        // Exercise the actual production Node/SockAddr operators, including
        // Qt's short null/Any QHostAddress records after STUN fallback.
        for (const auto value : fixtures.value("nodeRecords").toArray()) {
            const auto record = value.toObject();
            const auto address = [](const QString& text) {
                return text == "null" ? QHostAddress() : text == "any"
                    ? QHostAddress(QHostAddress::Any) : QHostAddress(text);
            };
            const auto port = static_cast<quint16>(record.value("port").toInt());
            Node node(QUuid(record.value("uuid").toString()), NodeType::EntityServer,
                SockAddr(SocketType::UDP, address(record.value("public").toString()), port),
                SockAddr(SocketType::UDP, address(record.value("local").toString()), port));
            NodePermissions permissions;
            permissions.permissions = static_cast<NodePermissions::Permission>(record.value("permissions").toInt());
            node.setPermissions(permissions);
            node.setLocalID(static_cast<Node::LocalID>(record.value("localID").toInt()));
            node.setConnectionSecret(QUuid(record.value("secret").toString()));
            QByteArray nodeBytes;
            QDataStream nodeStream(&nodeBytes, QIODevice::WriteOnly);
            nodeStream << node << node.getConnectionSecret();
            QCOMPARE(nodeStream.status(), QDataStream::Ok);
            QCOMPARE(nodeBytes.toHex(), record.value("hex").toString().toUtf8());
        }
        const auto domain = fixtures.value("domainList").toObject();
        QByteArray domainHeader;
        QDataStream headerStream(&domainHeader, QIODevice::WriteOnly);
        NodePermissions domainPermissions;
        domainPermissions.permissions = NodePermissions::Permission::canConnectToDomain |
            NodePermissions::Permission::canViewAssetURLs;
        headerStream << QUuid(domain.value("domainUUID").toString())
            << static_cast<Node::LocalID>(domain.value("domainLocalID").toInt())
            << QUuid(domain.value("newUUID").toString())
            << static_cast<Node::LocalID>(domain.value("newLocalID").toInt()) << domainPermissions << true
            << quint64(0x0102030405060708ULL) << quint64(0x1112131415161718ULL)
            << quint64(0x2122232425262728ULL) << true;
        QCOMPARE(domainHeader.size(), 66);
        QCOMPARE(domainHeader.toHex(), domain.value("headerHex").toString().toUtf8());
    }
    void browserLoopbackDoesNotGrantLocalhostPrivileges() {
        const QHostAddress local("127.0.0.3");
        QVERIFY(isLocalUserConnection(SockAddr(SocketType::UDP, local, 4000), local));
        QVERIFY(isLocalUserConnection(SockAddr(SocketType::UDP, QHostAddress::LocalHost, 4000), local));
        QVERIFY(!isLocalUserConnection(SockAddr(SocketType::UDP, QHostAddress("192.0.2.5"), 4000), local));
        QVERIFY(!isLocalUserConnection(SockAddr(SocketType::WebRTC, local, 4000), local));
        QVERIFY(!isLocalUserConnection(SockAddr(SocketType::WebRTC, QHostAddress::LocalHost, 4000), local));
    }
    void browserTransportCannotRequestOrClaimNativeAssignments() {
        const std::initializer_list<NodeType_t> nodeTypes{
            NodeType::Agent, NodeType::AudioMixer, NodeType::AvatarMixer, NodeType::AssetServer,
            NodeType::EntityServer, NodeType::MessagesMixer, NodeType::EntityScriptServer
        };
        for (const auto address : { QHostAddress(QHostAddress::LocalHost),
                                     QHostAddress("127.0.0.3"), QHostAddress("192.0.2.5") }) {
            const SockAddr native(SocketType::UDP, address, 4000);
            const SockAddr browser(SocketType::WebRTC, address, 4000);
            const SockAddr unknown(SocketType::Unknown, address, 4000);
            QVERIFY(isNativeAssignmentTransport(native));
            QVERIFY(!isNativeAssignmentTransport(browser));
            QVERIFY(!isNativeAssignmentTransport(unknown));
            for (const auto nodeType : nodeTypes) {
                QVERIFY(isNodeConnectTransportAllowed(native, nodeType));
                QCOMPARE(isNodeConnectTransportAllowed(browser, nodeType), nodeType == NodeType::Agent);
                QVERIFY(!isNodeConnectTransportAllowed(unknown, nodeType));
            }
        }
    }
    void stopNodeRequiresNativeLocalhostOrTheExactConfiguredMonitor() {
        const QHostAddress alias("127.0.0.3");
        const SockAddr monitor(SocketType::UDP, alias, 46120);
        // Legacy native localhost control remains available without a monitor.
        for (const auto address : { QHostAddress(QHostAddress::LocalHost),
                                     QHostAddress(QHostAddress::LocalHostIPv6) }) {
            QVERIFY(isAssignmentMonitorStopSender(SockAddr(SocketType::UDP, address, 4000), SockAddr()));
            QVERIFY(isAssignmentMonitorStopSender(SockAddr(SocketType::UDP, address, 4000), monitor));
            QVERIFY(!isAssignmentMonitorStopSender(SockAddr(SocketType::WebRTC, address, 4000), monitor));
            QVERIFY(!isAssignmentMonitorStopSender(SockAddr(SocketType::Unknown, address, 4000), monitor));
        }
        QVERIFY(isAssignmentMonitorStopSender(monitor, monitor));
        QVERIFY(!isAssignmentMonitorStopSender(SockAddr(SocketType::UDP, alias, 46121), monitor));
        QVERIFY(!isAssignmentMonitorStopSender(monitor, SockAddr()));
        QVERIFY(!isAssignmentMonitorStopSender(SockAddr(SocketType::WebRTC, alias, 46120), monitor));
        QVERIFY(!isAssignmentMonitorStopSender(SockAddr(SocketType::UDP, QHostAddress("192.0.2.5"), 46120), monitor));
        QVERIFY(!isAssignmentMonitorStopSender(monitor, SockAddr(SocketType::WebRTC, alias, 46120)));
    }
    void childStatusRequiresNativeLocalhostOrTheConfiguredBindAddress() {
        const QHostAddress alias("127.0.0.3");
        const SockAddr child(SocketType::UDP, alias, 46110);
        QVERIFY(isAssignmentChildStatusSender(child, alias));
        QVERIFY(!isAssignmentChildStatusSender(SockAddr(SocketType::UDP, QHostAddress("127.0.0.4"), 46110), alias));
        QVERIFY(!isAssignmentChildStatusSender(SockAddr(SocketType::UDP, QHostAddress("192.0.2.5"), 46110), alias));
        QVERIFY(!isAssignmentChildStatusSender(child, QHostAddress()));
        QVERIFY(!isAssignmentChildStatusSender(child, QHostAddress(QHostAddress::AnyIPv4)));
        for (const auto address : { QHostAddress(QHostAddress::LocalHost),
                                     QHostAddress(QHostAddress::LocalHostIPv6), alias }) {
            const SockAddr native(SocketType::UDP, address, 46110);
            QVERIFY(isAssignmentChildStatusSender(native, alias));
            QVERIFY(!isAssignmentChildStatusSender(SockAddr(SocketType::WebRTC, address, 46110), alias));
            QVERIFY(!isAssignmentChildStatusSender(SockAddr(SocketType::Unknown, address, 46110), alias));
            QVERIFY(!isAssignmentChildStatusSender(SockAddr(SocketType::UDP, address, 0), alias));
        }
        // Default/Any binds retain the legacy localhost behavior.
        for (const auto bind : { QHostAddress(), QHostAddress(QHostAddress::AnyIPv4) }) {
            QVERIFY(isAssignmentChildStatusSender(SockAddr(SocketType::UDP, QHostAddress::LocalHost, 46110), bind));
            QVERIFY(isAssignmentChildStatusSender(SockAddr(SocketType::UDP, QHostAddress::LocalHostIPv6, 46110), bind));
        }
    }
    void browserPacketPolicyAllowsAuditedAgentTrafficAndRejectsNativeControls() {
        const SockAddr browser(SocketType::WebRTC, QHostAddress::LocalHost, 46140);
        const SockAddr native(SocketType::UDP, QHostAddress::LocalHost, 46140);
        const SockAddr unknown(SocketType::Unknown, QHostAddress::LocalHost, 46140);
        for (const auto type : {
                PacketType::DomainConnectRequest, PacketType::DomainConnectRequestPending,
                PacketType::DomainListRequest, PacketType::DomainDisconnectRequest, PacketType::DomainServerPathQuery,
                PacketType::Ping, PacketType::PingReply, PacketType::AvatarData, PacketType::AvatarIdentity,
                PacketType::AvatarQuery, PacketType::SetAvatarTraits, PacketType::BulkAvatarTraitsAck,
                PacketType::RequestsDomainListData, PacketType::NodeIgnoreRequest, PacketType::NodeKickRequest,
                PacketType::NodeMuteRequest, PacketType::PerAvatarGainSet, PacketType::NegotiateAudioFormat,
                PacketType::MicrophoneAudioNoEcho, PacketType::SilentAudioFrame, PacketType::MessagesData,
                PacketType::MessagesSubscribe, PacketType::MessagesUnsubscribe, PacketType::EntityQuery,
                PacketType::BrowserEntityQuery, PacketType::EntityScriptCallMethod,
                PacketType::AssetMappingOperation, PacketType::AssetGet }) {
            QVERIFY(isBrowserPacketAllowed(type));
            QVERIFY(isPacketTransportAllowed(browser, type));
            QVERIFY(!isPacketTransportAllowed(unknown, type));
        }
        for (const auto type : {
                PacketType::OctreeDataPersist, PacketType::OctreeDataFileRequest, PacketType::OctreeFileReplacement,
                PacketType::DomainContentReplacementFromUrl, PacketType::StopNode, PacketType::AssignmentClientStatus,
                PacketType::RequestAssignment, PacketType::CreateAssignment, PacketType::WebRTCSignaling,
                PacketType::DomainSettingsRequest, PacketType::ICEServerHeartbeatACK,
                PacketType::ICEServerHeartbeatDenied, PacketType::ICEServerPeerInformation,
                PacketType::ReplicatedAvatarIdentity, PacketType::AssetUpload, PacketType::AssetGetReply,
                PacketType::BrowserEntityData, PacketType::MixedAudio, PacketType::Unknown }) {
            QVERIFY(!isBrowserPacketAllowed(type));
            QVERIFY(!isPacketTransportAllowed(browser, type));
        }
        // The native UDP packet set and its existing verification are unchanged.
        for (int type = 0; type < int(PacketType::NUM_PACKET_TYPE); ++type) {
            QVERIFY(isPacketTransportAllowed(native, static_cast<PacketType>(type)));
            QVERIFY(!isPacketTransportAllowed(unknown, static_cast<PacketType>(type)));
        }
    }
    void rtcSourceAddressesRequireTheExactCurrentEndpoint() {
        const SockAddr browser(SocketType::WebRTC, QHostAddress::LocalHost, 46140);
        const SockAddr wrongPort(SocketType::WebRTC, QHostAddress::LocalHost, 46141);
        const SockAddr native(SocketType::UDP, QHostAddress::LocalHost, 46140);
        const SockAddr otherNative(SocketType::UDP, QHostAddress("127.0.0.3"), 46110);
        QVERIFY(isPacketSourceAddressAllowed(browser, browser));
        QVERIFY(!isPacketSourceAddressAllowed(browser, wrongPort));
        QVERIFY(!isPacketSourceAddressAllowed(browser, native));
        QVERIFY(!isPacketSourceAddressAllowed(native, browser));
        QVERIFY(!isPacketSourceAddressAllowed(otherNative, browser));
        QVERIFY(isPacketSourceAddressAllowed(native, otherNative));
        QVERIFY(!isPacketSourceAddressAllowed(native, SockAddr(SocketType::UDP, QHostAddress("192.0.2.5"), 46140)));
        QVERIFY(!isPacketSourceAddressAllowed(SockAddr(), SockAddr()));

        Node agent(QUuid::createUuid(), NodeType::Agent, browser, wrongPort);
        QVERIFY(isBrowserAgentPacketSource(browser, &agent));
        QVERIFY(isBrowserAgentPacketSource(wrongPort, &agent));
        QVERIFY(!isBrowserAgentPacketSource(browser, nullptr));
        QVERIFY(!isBrowserAgentPacketSource(native, &agent));
        agent.activatePublicSocket();
        QVERIFY(isBrowserAgentPacketSource(browser, &agent));
        QVERIFY(!isBrowserAgentPacketSource(wrongPort, &agent));
        Node service(QUuid::createUuid(), NodeType::EntityServer, browser, browser);
        QVERIFY(!isBrowserAgentPacketSource(browser, &service));
    }
    void actualVerifierRejectsForgedNonverifiedSourceIdsAndPreservesHmacChecks() {
        ScopedEnvironment environment("OVERTE_NODE_UDP_ADDRESS", "127.0.0.3");
        ProjectionNodeList nodes;
        const SockAddr browser(SocketType::WebRTC, QHostAddress::LocalHost, 46140);
        const SockAddr wrongPort(SocketType::WebRTC, QHostAddress::LocalHost, 46141);
        const SockAddr native(SocketType::UDP, QHostAddress("127.0.0.3"), 46112);
        constexpr Node::LocalID browserID = 31, serverID = 32, unknownID = 33;
        const auto agent = nodes.addOrUpdateNode(QUuid::createUuid(), NodeType::Agent, browser, browser, browserID);
        QVERIFY(agent);
        QVERIFY(nodes.addOrUpdateNode(QUuid::createUuid(), NodeType::EntityServer, native, native, serverID));
        agent->setConnectionSecret(QUuid::createUuid());
        const auto verify = [&](PacketType type, Node::LocalID id, const SockAddr& sender, bool authenticate = false) {
            auto packet = NLPacket::create(type, 0);
            packet->writeSourceID(id);
            if (authenticate) {
                packet->writeVerificationHash(*agent->getAuthenticateHash());
            }
            auto bytes = std::make_unique<char[]>(packet->getDataSize());
            std::memcpy(bytes.get(), packet->getData(), packet->getDataSize());
            auto received = NLPacket::fromReceivedPacket(std::move(bytes), packet->getDataSize(), sender);
            return nodes.isPacketVerified(*received);
        };
        for (const bool authenticationEnabled : { true, false }) {
            nodes.setAuthenticatePackets(authenticationEnabled);
            QVERIFY(verify(PacketType::DomainDisconnectRequest, browserID, browser));
            QVERIFY(!verify(PacketType::DomainDisconnectRequest, serverID, browser));
            QVERIFY(!verify(PacketType::DomainDisconnectRequest, unknownID, browser));
            QVERIFY(!verify(PacketType::DomainDisconnectRequest, browserID, wrongPort));
            QVERIFY(!verify(PacketType::DomainDisconnectRequest, browserID,
                SockAddr(SocketType::UDP, browser.getAddress(), browser.getPort())));
            QVERIFY(verify(PacketType::DomainDisconnectRequest, serverID, native));
        }
        nodes.setAuthenticatePackets(true);
        QVERIFY(!verify(PacketType::BrowserEntityQuery, browserID, browser));
        QVERIFY(verify(PacketType::BrowserEntityQuery, browserID, browser, true));
        QVERIFY(!verify(PacketType::BrowserEntityQuery, browserID, wrongPort, true));
    }
    void preservesRenderingAndRemovesPrivateState() {
        const QJsonObject original{{"id", "actual-entity"}, {"type", "Model"},
            {"modelURL", "atp:/scene/model.fbx"}, {"textures", "{\"albedo\":\"https://assets.example/texture.png\"}"},
            {"materialData", "{\"materials\":[{\"roughness\":0.5}]}"},
            {"privateUserData", "private"}, {"serverScripts", "private-script"},
            {"simulationOwner", "private-owner"}, {"certificateID", "private-id"}, {"marketplaceID", "private-market"}};
        const auto projected = browserEntityProjection(QJsonArray{original});
        QCOMPARE(projected.size(), 1);
        const auto visible = projected[0].toObject();
        for (const auto& key : {"id", "type", "modelURL", "textures", "materialData"}) {
            QCOMPARE(visible.value(key), original.value(key));
        }
        for (const auto& key : {"privateUserData", "serverScripts", "simulationOwner", "certificateID", "marketplaceID"}) {
            QVERIFY(!visible.contains(key));
        }
        QCOMPARE(original.value("privateUserData").toString(), QString("private"));
    }
    void excludesNonDomainHosts() {
        const auto projected = browserEntityProjection(QJsonArray{
            QJsonObject{{"id", "domain"}, {"entityHostType", "domain"}},
            QJsonObject{{"id", "legacy"}}, QJsonObject{{"id", "avatar"}, {"entityHostType", "avatar"}},
            QJsonObject{{"id", "local"}, {"entityHostType", "local"}}, 12, "invalid"});
        QCOMPARE(projected.size(), 2);
        QCOMPARE(projected[0].toObject().value("id").toString(), QString("domain"));
        QCOMPARE(projected[1].toObject().value("id").toString(), QString("legacy"));
    }
    void observedEndpointPolicyRequiresExplicitNativeLoopback() {
        const QHostAddress bound("127.0.0.3");
        const SockAddr sender(SocketType::UDP, QHostAddress::LocalHost, 46116);
        const SockAddr advertised(SocketType::UDP, QHostAddress("192.0.2.7"), 46116);
        const SockAddr publicSocket(SocketType::UDP, bound, 46116);
        Node peer(QUuid::createUuid(), NodeType::Agent, publicSocket, advertised);
        QVERIFY(shouldUseObservedNativeLoopbackSocket(bound, sender, &peer, advertised));
        QVERIFY(shouldUseObservedNativeLoopbackSocket(bound, sender, &peer, publicSocket));
        peer.activateLocalSocket();
        QVERIFY(shouldUseObservedNativeLoopbackSocket(bound, sender, &peer, advertised));
        for (const auto& bindAddress : { QHostAddress(), QHostAddress(QHostAddress::AnyIPv4),
                                       QHostAddress("192.0.2.3") }) {
            QVERIFY(!shouldUseObservedNativeLoopbackSocket(bindAddress, sender, &peer, advertised));
        }
        for (const auto& otherSender : {
                SockAddr(SocketType::WebRTC, sender.getAddress(), sender.getPort()),
                SockAddr(SocketType::Unknown, sender.getAddress(), sender.getPort()),
                SockAddr(SocketType::UDP, QHostAddress("192.0.2.8"), sender.getPort()),
                SockAddr(SocketType::UDP, sender.getAddress(), quint16(sender.getPort() + 1)),
                SockAddr(SocketType::UDP, sender.getAddress(), 0) }) {
            QVERIFY(!shouldUseObservedNativeLoopbackSocket(bound, otherSender, &peer, advertised));
        }
        QVERIFY(!shouldUseObservedNativeLoopbackSocket(bound, sender, nullptr, advertised));
        QVERIFY(!shouldUseObservedNativeLoopbackSocket(bound, sender, &peer, sender));
        const SockAddr browser(SocketType::WebRTC, sender.getAddress(), sender.getPort());
        QVERIFY(!shouldUseObservedNativeLoopbackSocket(bound, sender, &peer, browser));
        Node browserPeer(QUuid::createUuid(), NodeType::Agent, browser, browser);
        QVERIFY(!shouldUseObservedNativeLoopbackSocket(bound, sender, &browserPeer, advertised));
        Node mixedPeer(QUuid::createUuid(), NodeType::Agent, publicSocket, browser);
        mixedPeer.activateLocalSocket();
        QVERIFY(!shouldUseObservedNativeLoopbackSocket(bound, sender, &mixedPeer, advertised));
    }
    void actualNativePingSelectsObservedEndpointAndCompletesReliableHandshake() {
        ScopedEnvironment environment("OVERTE_NODE_UDP_ADDRESS", "127.0.0.3");
        ScopedNativeNodeList fixture;
        auto& nodes = *fixture.nodes;
        const QHostAddress serverAddress("127.0.0.3");
        const auto serverPort = nodes.getSocketLocalPort(SocketType::UDP);
        QVERIFY(serverPort != 0);
        QUdpSocket visitor;
        QVERIFY(visitor.bind(QHostAddress(QHostAddress::AnyIPv4), quint16(0)));
        const auto port = visitor.localPort();
        const SockAddr observed(SocketType::UDP, QHostAddress::LocalHost, port);
        const SockAddr advertised(SocketType::UDP, QHostAddress("127.0.0.4"), port);
        const auto peer = nodes.addOrUpdateNode(QUuid::createUuid(), NodeType::Agent,
            SockAddr(SocketType::UDP, serverAddress, port), advertised, 7);
        QVERIFY(peer);
        peer->setConnectionSecret(QUuid::createUuid());
        nodes.setSessionLocalID(31);

        // A different native source port does not receive the address-only
        // exception, even with a valid peer HMAC. Retain normal local-ping
        // activation until the known client's advertised port replies.
        QUdpSocket otherEndpoint;
        QVERIFY(otherEndpoint.bind(QHostAddress(QHostAddress::LocalHost), quint16(0)));
        QVERIFY(otherEndpoint.localPort() != port);
        const auto previousLastHeard = peer->getLastHeardMicrostamp();
        auto otherPing = nodes.constructPingPacket(peer->getUUID(), PingType::Local);
        QVERIFY(otherPing->seek(0));
        ReceivedMessage otherOriginal(*otherPing);
        QCOMPARE(otherOriginal.getSize(), otherPing->getPayloadSize());
        auto otherReply = nodes.constructPingReplyPacket(otherOriginal);
        otherReply->writeSourceID(peer->getLocalID());
        otherReply->writeVerificationHash(*peer->getAuthenticateHash());
        QCOMPARE(otherEndpoint.writeDatagram(otherReply->getData(), otherReply->getDataSize(), serverAddress, serverPort),
                 otherReply->getDataSize());
        QTRY_VERIFY_WITH_TIMEOUT(peer->getLastHeardMicrostamp() > previousLastHeard
            && peer->getActiveSocket() && *peer->getActiveSocket() == advertised, 1000);

        // Use the production ping/reply serializers and the real socket,
        // verification, PacketReceiver and NodeList listener path. A wildcard
        // native client replies from 127.0.0.1 to the explicitly bound alias.
        for (const auto pingType : { PingType::Local, PingType::Public, PingType::Local }) {
            const auto previousLastHeard = peer->getLastHeardMicrostamp();
            auto ping = nodes.constructPingPacket(peer->getUUID(), pingType);
            QVERIFY(ping->seek(0));
            ReceivedMessage original(*ping);
            QCOMPARE(original.getSize(), ping->getPayloadSize());
            auto reply = nodes.constructPingReplyPacket(original);
            reply->writeSourceID(peer->getLocalID());
            reply->writeVerificationHash(*peer->getAuthenticateHash());
            QCOMPARE(visitor.writeDatagram(reply->getData(), reply->getDataSize(), serverAddress, serverPort),
                     reply->getDataSize());
            QTRY_VERIFY_WITH_TIMEOUT(peer->getLastHeardMicrostamp() > previousLastHeard
                && peer->getActiveSocket() && *peer->getActiveSocket() == observed, 1000);
            QCOMPARE(peer->getSymmetricSocket(), observed);
        }

        // This native octree completion packet is reliable. The old advertised
        // destination received its handshake but could never consume the ACK
        // from the client's actual loopback source, so this payload never left
        // the native UDT send queue.
        auto completion = NLPacket::create(PacketType::EntityQueryInitialResultsComplete, sizeof(quint16), true);
        completion->writePrimitive(quint16(7));
        QVERIFY(nodes.sendPacket(std::move(completion), *peer) > 0);
        QTRY_VERIFY_WITH_TIMEOUT(visitor.hasPendingDatagrams(), 1000);
        QHostAddress source;
        quint16 sourcePort = 0;
        auto handshakeBytes = std::make_unique<char[]>(visitor.pendingDatagramSize());
        const auto handshakeSize = visitor.readDatagram(handshakeBytes.get(), visitor.pendingDatagramSize(),
                                                       &source, &sourcePort);
        QCOMPARE(source, serverAddress);
        QCOMPARE(sourcePort, serverPort);
        QCOMPARE(handshakeSize, qint64(udt::ControlPacket::totalHeaderSize() + sizeof(udt::SequenceNumber)));
        const SockAddr serverSocket(SocketType::UDP, source, sourcePort);
        auto handshake = udt::ControlPacket::fromReceivedPacket(std::move(handshakeBytes), handshakeSize, serverSocket);
        QCOMPARE(handshake->getType(), udt::ControlPacket::Handshake);
        udt::SequenceNumber initialSequence;
        QCOMPARE(handshake->readPrimitive(&initialSequence), qint64(sizeof(initialSequence)));
        auto handshakeAck = udt::ControlPacket::create(udt::ControlPacket::HandshakeACK, sizeof(initialSequence));
        handshakeAck->writePrimitive(initialSequence);
        QCOMPARE(visitor.writeDatagram(handshakeAck->getData(), handshakeAck->getDataSize(), source, sourcePort),
                 handshakeAck->getDataSize());

        QByteArray reliableBytes;
        QElapsedTimer deadline;
        deadline.start();
        while (reliableBytes.isEmpty() && deadline.elapsed() < 2000) {
            QCoreApplication::processEvents();
            while (visitor.hasPendingDatagrams()) {
                QByteArray bytes(int(visitor.pendingDatagramSize()), Qt::Uninitialized);
                QCOMPARE(visitor.readDatagram(bytes.data(), bytes.size(), &source, &sourcePort), qint64(bytes.size()));
                quint32 header = 0;
                QVERIFY(bytes.size() >= int(sizeof(header)));
                std::memcpy(&header, bytes.constData(), sizeof(header));
                if (header & quint32(0x80000000)) {
                    // A handshake already in flight before the ACK is harmless.
                    QCOMPARE(visitor.writeDatagram(handshakeAck->getData(), handshakeAck->getDataSize(), source, sourcePort),
                             handshakeAck->getDataSize());
                } else {
                    reliableBytes = bytes;
                    break;
                }
            }
            if (reliableBytes.isEmpty()) { QTest::qWait(1); }
        }
        QVERIFY(!reliableBytes.isEmpty());
        auto bytes = std::make_unique<char[]>(reliableBytes.size());
        std::memcpy(bytes.get(), reliableBytes.constData(), reliableBytes.size());
        auto received = NLPacket::fromReceivedPacket(std::move(bytes), reliableBytes.size(), serverSocket);
        QVERIFY(received->isReliable());
        QCOMPARE(received->getType(), PacketType::EntityQueryInitialResultsComplete);
        QCOMPARE(received->getSourceID(), Node::LocalID(31));
        QCOMPARE(NLPacket::verificationHashInHeader(*received),
                 NLPacket::hashForPacketAndHMAC(*received, *peer->getAuthenticateHash()));
        quint16 querySequence = 0;
        QCOMPARE(received->readPrimitive(&querySequence), qint64(sizeof(querySequence)));
        QCOMPARE(querySequence, quint16(7));
        auto ack = udt::ControlPacket::create(udt::ControlPacket::ACK, sizeof(udt::SequenceNumber));
        ack->writePrimitive(received->getSequenceNumber());
        QCOMPARE(visitor.writeDatagram(ack->getData(), ack->getDataSize(), source, sourcePort), ack->getDataSize());
        QCoreApplication::processEvents();
    }
};
QTEST_GUILESS_MAIN(BrowserEntityProjectionTests)
#include "BrowserEntityProjectionTests.moc"
