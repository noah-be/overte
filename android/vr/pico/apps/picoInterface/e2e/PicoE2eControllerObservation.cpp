#include "PicoE2eControllerObservation.h"

#include <cmath>
#include <QCoreApplication>
#include <QDateTime>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QUrl>
#include <QVariant>
#include <controllers/StandardControls.h>
#include <controllers/Actions.h>
#include <controllers/UserInputMapper.h>
#include <shared/GlobalAppProperties.h>
#include <avatar/AvatarManager.h>
#include <PointerManager.h>
#include <NodeList.h>

namespace overte::pico::e2e {
namespace {
bool controlledProbeActive() {
    auto app = QCoreApplication::instance();
    if (!app) {
        return false;
    }
    const QUrl script = app->property(hifi::properties::TEST).toUrl();
    const QString expected = QFileInfo(QStringLiteral(
        "/data/user/0/org.overte.pico/files/overte-e2e/overte_e2e_probe.js"))
        .canonicalFilePath();
    return script.isLocalFile() && !expected.isEmpty()
        && QFileInfo(script.toLocalFile()).canonicalFilePath() == expected;
}

QJsonObject vector(const glm::vec3& value) {
    return {{"x", value.x}, {"y", value.y}, {"z", value.z}};
}

QJsonObject pose(const controller::Pose& value) {
    if (!value.valid || !std::isfinite(value.translation.x)
            || !std::isfinite(value.translation.y) || !std::isfinite(value.translation.z)
            || !std::isfinite(value.rotation.x) || !std::isfinite(value.rotation.y)
            || !std::isfinite(value.rotation.z) || !std::isfinite(value.rotation.w)) {
        return {{"valid", false}, {"translation", QJsonValue::Null},
                {"rotation", QJsonValue::Null}};
    }
    return {{"valid", true}, {"translation", vector(value.translation)},
            {"rotation", QJsonObject{{"x", value.rotation.x}, {"y", value.rotation.y},
                                     {"z", value.rotation.z}, {"w", value.rotation.w}}}};
}
}

void observeControllerFrame(const controller::UserInputMapper& mapper) {
    static qint64 previousEpochMs { 0 };
    static quint64 sequence { 0 };
    static QJsonArray history;
    static QJsonArray motionHistory;
    static QJsonArray interactionHistory;
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    if (now - previousEpochMs < 100 || !controlledProbeActive()) {
        return;
    }
    previousEpochMs = now;
    // Read actual handshake gates in their owning thread. No packet, timer,
    // connection state or acceptance result is changed by this observer.
    static qint64 previousNetworkEpochMs { 0 };
    if (now - previousNetworkEpochMs >= 1000 && DependencyManager::isSet<NodeList>()) {
        previousNetworkEpochMs = now;
        const auto nodeList = DependencyManager::get<NodeList>();
        QMetaObject::invokeMethod(nodeList.data(), [nodeList] {
            auto& domain = nodeList->getDomainHandler();
            QSaveFile output(QStringLiteral(
                "/data/user/0/org.overte.pico/files/overte-e2e/network-handshake-observation.json"));
            if (output.open(QIODevice::WriteOnly)) {
                output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
                output.write(QJsonDocument(QJsonObject{
                    {"schemaVersion", 1}, {"source", "native-domain-handshake"},
                    {"processId", QCoreApplication::applicationPid()},
                    {"updatedEpochMs", QDateTime::currentMSecsSinceEpoch()},
                    {"connected", domain.isConnected()},
                    {"serverless", domain.isServerless()},
                    {"domainSocketKnown", domain.isSocketKnown()},
                    {"publicSocketKnown", !nodeList->getPublicSockAddr().isNull()},
                    {"checkInEnabled", nodeList->getSendDomainServerCheckInEnabled()},
                    {"transportSuspended", nodeList->isClientTransportSuspended()},
                    {"shuttingDown", nodeList->isShuttingDown()},
                    {"pendingCheckIns", domain.getCheckInPacketsSinceLastReply()},
                    {"hasSettings", domain.hasSettings()},
                    {"domainUuidPresent", !domain.getUUID().isNull()},
                    {"connectionTokenPresent", !domain.getConnectionToken().isNull()},
                    {"inErrorState", domain.isInErrorState()},
                    {"connectionError", domain.getLastDomainConnectionError()},
                    {"avatarEntitiesAllowed", nodeList->getThisNodeCanRezAvatarEntities()}
                }).toJson(QJsonDocument::Compact));
                output.commit();
            }
        }, Qt::QueuedConnection);
    }
    const auto device = mapper.getStandardDeviceID();
    auto value = [&mapper, device](uint16_t channel, controller::ChannelType type) {
        return mapper.getValue(controller::Input(device, channel, type)).value;
    };
    auto button = [&value](uint16_t channel) {
        return value(channel, controller::ChannelType::BUTTON) > 0.5f;
    };
    auto axis = [&value](uint16_t channel) {
        return value(channel, controller::ChannelType::AXIS);
    };
    using namespace controller;
    auto rawValue = [&mapper](const QString& name) -> QJsonValue {
        const Input input = mapper.findDeviceInput(name);
        return input.isValid() ? QJsonValue(mapper.getValue(input).value)
                               : QJsonValue(QJsonValue::Null);
    };
    const QJsonObject controls {
        {"openxr", QJsonObject{
            {"leftTriggerClick", rawValue(QStringLiteral("OpenXR.LTClick"))},
            {"rightTriggerClick", rawValue(QStringLiteral("OpenXR.RTClick"))},
            {"menu", rawValue(QStringLiteral("OpenXR.Start"))}}},
        {"actions", QJsonObject{
            {"contextMenu", mapper.getActionState(Action::CONTEXT_MENU)}}},
        {"buttons", QJsonObject{
            {"menu", button(START)}, {"leftPrimary", button(LEFT_PRIMARY_THUMB)},
            {"leftSecondary", button(LEFT_SECONDARY_THUMB)}, {"leftThumbstick", button(LS)},
            {"leftTrigger", button(LT_CLICK)}, {"rightPrimary", button(RIGHT_PRIMARY_THUMB)},
            {"rightSecondary", button(RIGHT_SECONDARY_THUMB)}, {"rightThumbstick", button(RS)},
            {"rightTrigger", button(RT_CLICK)}}},
        {"axes", QJsonObject{
            {"lx", axis(LX)}, {"ly", axis(LY)}, {"rx", axis(RX)}, {"ry", axis(RY)},
            {"leftTrigger", axis(LT)}, {"rightTrigger", axis(RT)},
            {"leftGrip", axis(LEFT_GRIP)}, {"rightGrip", axis(RIGHT_GRIP)}}},
        {"poses", QJsonObject{
            {"left", pose(mapper.getPose(Input(device, LEFT_HAND, ChannelType::POSE)))},
            {"right", pose(mapper.getPose(Input(device, RIGHT_HAND, ChannelType::POSE)))}}}
    };
    const auto avatar = DependencyManager::get<AvatarManager>()->getMyAvatar();
    const auto sensorToWorld = avatar->getSensorToWorldMatrix();
    QJsonArray matrix;
    for (int column = 0; column < 4; ++column) {
        for (int row = 0; row < 4; ++row) {
            matrix.append(sensorToWorld[column][row]);
        }
    }
    QSaveFile geometryOutput(QStringLiteral(
        "/data/user/0/org.overte.pico/files/overte-e2e/input-geometry-observation.json"));
    if (geometryOutput.open(QIODevice::WriteOnly)) {
        geometryOutput.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
        geometryOutput.write(QJsonDocument(QJsonObject{
            {"schemaVersion", 1}, {"source", "native-avatar-input-geometry"},
            {"processId", QCoreApplication::applicationPid()}, {"updatedEpochMs", now},
            {"sensorToWorld", matrix}, {"avatarPosition", vector(avatar->getWorldPosition())}
        }).toJson(QJsonDocument::Compact));
        geometryOutput.commit();
    }
    if (axis(RT) > 0.01f && DependencyManager::isSet<PointerManager>()) {
        const auto pointers = DependencyManager::get<PointerManager>();
        QJsonArray results;
        for (auto identifier : pointers->getPointers()) {
            if (pointers->isRightHand(identifier)) {
                const auto pick = pointers->getPrevPickResult(identifier);
                if (pick) {
                    results.append(QJsonObject{{"pointerId", static_cast<double>(identifier)},
                        {"pick", QJsonObject::fromVariantMap(pick->toVariantMap())}});
                }
            }
        }
        interactionHistory.append(QJsonObject{{"sampleEpochMs", now},
            {"controller", controls}, {"rightPointers", results}});
        while (interactionHistory.size() > 64) { interactionHistory.removeAt(0); }
        QSaveFile interactionOutput(QStringLiteral(
            "/data/user/0/org.overte.pico/files/overte-e2e/native-interaction-observation.json"));
        if (interactionOutput.open(QIODevice::WriteOnly)) {
            interactionOutput.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
            interactionOutput.write(QJsonDocument(QJsonObject{{"schemaVersion", 1},
                {"source", "native-pointer-manager"}, {"processId", QCoreApplication::applicationPid()},
                {"updatedEpochMs", now}, {"samples", interactionHistory}}).toJson(QJsonDocument::Compact));
            interactionOutput.commit();
        }
    }
    // Observe physics on the application thread, independently of a busy script
    // engine. These are actual avatar states, never injected command values.
    const QJsonObject motion {{"position", vector(avatar->getWorldPosition())},
                              {"inAir", avatar->isInAir()}, {"flying", avatar->isFlying()}};
    history.append(QJsonObject{{"sampleSequence", static_cast<double>(++sequence)},
                              {"sampleEpochMs", now}, {"controller", controls},
                              {"avatarMotion", motion}});
    motionHistory.append(QJsonObject{{"sampleSequence", static_cast<double>(sequence)},
                                    {"sampleEpochMs", now}, {"avatarMotion", motion}});
    while (history.size() > 64) {
        history.removeAt(0);
        motionHistory.removeAt(0);
    }
    const QJsonObject observation {
        {"schemaVersion", 1}, {"processId", QCoreApplication::applicationPid()},
        {"updatedEpochMs", now}, {"source", "native-user-input-mapper"},
        {"samples", history}
    };
    QSaveFile output(QStringLiteral(
        "/data/user/0/org.overte.pico/files/overte-e2e/controller-observation.json"));
    if (output.open(QIODevice::WriteOnly)) {
        output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
        output.write(QJsonDocument(observation).toJson(QJsonDocument::Compact));
        output.commit();
    }
    // The script observer needs only motion. Avoid repeatedly converting the
    // much larger controller directory while retaining identical live samples.
    const QJsonObject motionObservation {
        {"schemaVersion", 1}, {"processId", QCoreApplication::applicationPid()},
        {"updatedEpochMs", now}, {"source", "native-avatar-motion"}, {"samples", motionHistory}
    };
    QSaveFile motionOutput(QStringLiteral(
        "/data/user/0/org.overte.pico/files/overte-e2e/avatar-motion-observation.json"));
    if (motionOutput.open(QIODevice::WriteOnly)) {
        motionOutput.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
        motionOutput.write(QJsonDocument(motionObservation).toJson(QJsonDocument::Compact));
        motionOutput.commit();
    }
}
}
