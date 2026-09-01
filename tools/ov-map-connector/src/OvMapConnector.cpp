#include "OvMapConnector.h"

#include <QCommandLineParser>
#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include <AddressManager.h>
#include <AccountManager.h>
#include <DependencyManager.h>
#include <DomainAccountManager.h>
#include <MetaverseAPI.h>
#include <OctreeHeadlessViewer.h>
#include <OctreeQuery.h>
#include <ScriptEngine.h>
#include <SettingHandle.h>

#include <AvatarData.h>
#include <shared/ConicalViewFrustum.h>
#include <NLPacket.h>
#include <ViewFrustum.h>
#include <platform/Platform.h>

namespace {
QJsonObject vec3ToJson(const glm::vec3& value) {
    return { { "x", value.x }, { "y", value.y }, { "z", value.z } };
}

QJsonObject quatToJson(const glm::quat& value) {
    return { { "x", value.x }, { "y", value.y }, { "z", value.z }, { "w", value.w } };
}
}

OvMapConnector::OvMapConnector(int argc, char* argv[]) : QCoreApplication(argc, argv) {
    setApplicationName("ov-map-connector");
    platform::create();
    platform::enumeratePlatform();

    QCommandLineParser parser;
    parser.setApplicationDescription("Headless Overte world connector for ov-map");
    parser.addHelpOption();
    parser.addOption({ { "d", "domain" }, "Overte place or domain address", "address", "overte_hub" });
    parser.addOption({ { "o", "output" }, "Write newline-delimited JSON to a file instead of stdout", "file" });
    parser.addOption({ "radius", "Entity query radius in metres", "metres", "32768" });
    parser.process(*this);

    bool validRadius { false };
    const auto parsedRadius = parser.value("radius").toFloat(&validRadius);
    if (validRadius && parsedRadius > 0.0f) {
        _radius = parsedRadius;
    }
    if (parser.isSet("output")) {
        _output.setFileName(parser.value("output"));
        if (!_output.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
            qFatal("Could not open output file");
        }
    }

    DependencyManager::registerInheritance<LimitedNodeList, NodeList>();
    DependencyManager::set<AccountManager>(false, [] { return QString("ov-map-connector/0.1"); });
    DependencyManager::set<DomainAccountManager>();
    auto addressManager = DependencyManager::set<AddressManager>();
    DependencyManager::set<NodeList>(NodeType::Agent, INVALID_PORT);
    DependencyManager::get<AccountManager>()->setIsAgent(true);
    DependencyManager::get<AccountManager>()->setAuthURL(MetaverseAPI::getCurrentMetaverseServerURL());

    connect(addressManager.data(), &AddressManager::locationChangeRequired, this,
        [this](const glm::vec3& position, bool hasOrientation, const glm::quat& orientation, bool) {
            _position = position;
            if (hasOrientation) {
                _orientation = orientation;
            }
            _entityViewer.setPosition(_position);
        });

    auto nodeList = DependencyManager::get<NodeList>();
    nodeList->addSetOfNodeTypesToNodeInterestSet({ NodeType::EntityServer, NodeType::AvatarMixer });
    connect(nodeList.data(), &NodeList::nodeActivated, this, &OvMapConnector::nodeActivated);
    connect(nodeList.data(), &NodeList::nodeKilled, this, &OvMapConnector::nodeKilled);
    connect(&nodeList->getDomainHandler(), &DomainHandler::domainConnectionRefused, this,
        [this](const QString& reason, int, const QString&) {
            writeEvent({ { "type", "connection.error" }, { "message", reason } });
        });

    auto& receiver = nodeList->getPacketReceiver();
    receiver.registerListenerForTypes(
        { PacketType::OctreeStats, PacketType::EntityData, PacketType::EntityErase },
        PacketReceiver::makeSourcedListenerReference<OvMapConnector>(this, &OvMapConnector::handleOctreePacket));

    _entityViewer.init();
    _entityViewer.setPosition(_position);
    _entityViewer.setCenterRadius(_radius);
    _entityViewer.setMaxPacketsPerSecond(6000);
    _entityViewer.getOctreeQuery().setOctreeSizeScale(_radius * 400.0f);
    _avatars = DependencyManager::set<AvatarHashMap>();

    auto checkInTimer = new QTimer(nodeList.data());
    connect(checkInTimer, &QTimer::timeout, nodeList.data(), &NodeList::sendDomainServerCheckIn);
    checkInTimer->start(DOMAIN_SERVER_CHECK_IN_MSECS);
    nodeList->startThread();

    connect(&_queryTimer, &QTimer::timeout, this, &OvMapConnector::queryWorld);
    _queryTimer.start(1000);
    connect(&_publishTimer, &QTimer::timeout, this, &OvMapConnector::publishState);
    _publishTimer.start(1000);

    writeEvent({ { "type", "connection.connecting" }, { "address", parser.value("domain") } });
    DependencyManager::get<AddressManager>()->handleLookupString(parser.value("domain"), false);
}

OvMapConnector::~OvMapConnector() {
    auto nodeList = DependencyManager::get<NodeList>();
    if (nodeList) {
        nodeList->getDomainHandler().disconnect("ov-map connector stopping");
        nodeList->setIsShuttingDown(true);
        nodeList->getPacketReceiver().setShouldDropPackets(true);
    }
    DependencyManager::destroy<AvatarHashMap>();
    DependencyManager::destroy<NodeList>();
    DependencyManager::destroy<DomainAccountManager>();
    platform::destroy();
}

void OvMapConnector::nodeActivated(const SharedNodePointer& node) {
    if (node->getType() == NodeType::EntityServer) {
        _entityServerConnected = true;
    } else if (node->getType() == NodeType::AvatarMixer) {
        _avatarMixerConnected = true;
    } else {
        return;
    }
    writeEvent({
        { "type", "connection.service" },
        { "service", QString(QChar(node->getType())) },
        { "connected", true },
    });
    queryWorld();
}

void OvMapConnector::nodeKilled(const SharedNodePointer& node) {
    if (node->getType() == NodeType::EntityServer) {
        _entityServerConnected = false;
    } else if (node->getType() == NodeType::AvatarMixer) {
        _avatarMixerConnected = false;
        _avatars->clearOtherAvatars();
    }
}

void OvMapConnector::handleOctreePacket(QSharedPointer<ReceivedMessage> message, SharedNodePointer senderNode) {
    auto packetType = message->getType();
    if (packetType == PacketType::OctreeStats) {
        const auto statsLength = OctreeHeadlessViewer::parseOctreeStats(message, senderNode);
        if (message->getSize() <= statsLength) {
            return;
        }
        const auto size = message->getSize() - statsLength;
        auto buffer = std::make_unique<char[]>(size);
        memcpy(buffer.get(), message->getRawMessage() + statsLength, size);
        auto packet = NLPacket::fromReceivedPacket(std::move(buffer), size, message->getSenderSockAddr());
        message = QSharedPointer<ReceivedMessage>::create(*packet);
        packetType = message->getType();
    }
    if (packetType == PacketType::EntityData) {
        _entityViewer.processDatagram(*message, senderNode);
    } else if (packetType == PacketType::EntityErase) {
        _entityViewer.processEraseMessage(*message, senderNode);
    }
}

void OvMapConnector::queryWorld() {
    if (_entityServerConnected) {
        _entityViewer.queryOctree();
        _entityViewer.update();
    }
    if (_avatarMixerConnected) {
        sendAvatarQuery();
    }
}

void OvMapConnector::sendAvatarQuery() {
    ViewFrustum view;
    view.setPosition(_position);
    view.setOrientation(glm::quat());
    view.setProjection(180.0f, 1.0f, 0.01f, _radius);
    view.calculate();
    ConicalViewFrustum conicalView { view };

    auto packet = NLPacket::create(PacketType::AvatarQuery);
    auto destination = reinterpret_cast<unsigned char*>(packet->getPayload());
    auto start = destination;
    const uint8_t numberOfFrustums = 1;
    memcpy(destination, &numberOfFrustums, sizeof(numberOfFrustums));
    destination += sizeof(numberOfFrustums);
    destination += conicalView.serialize(destination);
    packet->setPayloadSize(destination - start);
    DependencyManager::get<NodeList>()->broadcastToNodes(std::move(packet), { NodeType::AvatarMixer });
}

QJsonArray OvMapConnector::avatarsAsJson() const {
    QJsonArray result;
    for (const auto& avatar : _avatars->getHashCopy()) {
        if (!avatar) {
            continue;
        }
        result.append(QJsonObject {
            { "id", avatar->getSessionUUID().toString(QUuid::WithoutBraces) },
            { "displayName", avatar->getSessionDisplayName() },
            { "position", vec3ToJson(avatar->getWorldPosition()) },
            { "orientation", quatToJson(avatar->getWorldOrientation()) },
        });
    }
    return result;
}

void OvMapConnector::publishState() {
    QVariantMap entityMap;
    _entityViewer.getTree()->writeToMap(entityMap, nullptr, true, false);
    const auto entities = QJsonDocument::fromVariant(entityMap).object().value("Entities").toArray();
    writeEvent({
        { "type", "world.snapshot" },
        { "timestamp", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs) },
        { "connected", _entityServerConnected && _avatarMixerConnected },
        { "entities", entities },
        { "avatars", avatarsAsJson() },
        { "spawn", QJsonObject {
            { "position", vec3ToJson(_position) },
            { "orientation", quatToJson(_orientation) },
        } },
    });
}

void OvMapConnector::writeEvent(const QJsonObject& event) {
    const auto bytes = QJsonDocument(event).toJson(QJsonDocument::Compact) + '\n';
    if (_output.isOpen()) {
        _output.write(bytes);
        _output.flush();
    } else {
        fwrite(bytes.constData(), 1, bytes.size(), stdout);
        fflush(stdout);
    }
}
