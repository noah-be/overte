#pragma once

#include <QCoreApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonObject>
#include <QTimer>

#include <AvatarHashMap.h>
#include <NodeList.h>

#include "EntityTreeHeadlessViewer.h"

class OvMapConnector : public QCoreApplication {
    Q_OBJECT

public:
    OvMapConnector(int argc, char* argv[]);
    ~OvMapConnector() override;

private slots:
    void nodeActivated(const SharedNodePointer& node);
    void nodeKilled(const SharedNodePointer& node);
    void handleOctreePacket(QSharedPointer<ReceivedMessage> message, SharedNodePointer senderNode);
    void queryWorld();
    void publishState();

private:
    void sendAvatarQuery();
    void writeEvent(const QJsonObject& event);
    QJsonArray avatarsAsJson() const;

    EntityTreeHeadlessViewer _entityViewer;
    QSharedPointer<AvatarHashMap> _avatars;
    QFile _output;
    QTimer _queryTimer;
    QTimer _publishTimer;
    glm::vec3 _position { 0.0f };
    glm::quat _orientation {};
    float _radius { 32768.0f };
    bool _entityServerConnected { false };
    bool _avatarMixerConnected { false };
};
