// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>

#include <cstring>
#include <limits>

#include <AvatarData.h>
#include <HeadData.h>

template<typename Section>
QByteArray packetWithSection(AvatarDataPacket::HasFlags flags, const Section& section) {
    QByteArray packet(sizeof(flags) + sizeof(section), '\0');
    memcpy(packet.data(), &flags, sizeof(flags));
    memcpy(packet.data() + sizeof(flags), &section, sizeof(section));
    return packet;
}

class AvatarDataTests : public QObject {
    Q_OBJECT

private slots:
    void parseTruncatedFlags();
    void parseTruncatedHandControllers();
    void parseCompleteHandControllers();
    void rejectNonFiniteGlobalPosition();
    void rejectNonFiniteBoundingBox();
    void rejectNonFiniteSensorTranslation();
    void rejectNonFiniteLookAtPosition();
    void rejectNonFiniteLocalPosition();
    void rejectNonFiniteFaceCoefficient();
    void rejectNonFiniteFarGrabTransform();
};

void AvatarDataTests::parseTruncatedFlags() {
    AvatarData avatar;
    const QByteArray emptyPacket;
    const QByteArray oneBytePacket(1, '\0');

    QCOMPARE(avatar.parseDataFromBuffer(emptyPacket), emptyPacket.size());
    QCOMPARE(avatar.parseDataFromBuffer(oneBytePacket), oneBytePacket.size());
}

void AvatarDataTests::parseTruncatedHandControllers() {
    const auto flags = AvatarDataPacket::PACKET_HAS_HAND_CONTROLLERS;
    const int headerSize = sizeof(flags);
    const int completeSize = headerSize + AvatarDataPacket::HAND_CONTROLLERS_SIZE;
    AvatarData avatar;

    for (int size = headerSize; size < completeSize; ++size) {
        QByteArray packet(size, '\0');
        memcpy(packet.data(), &flags, sizeof(flags));

        QCOMPARE(avatar.parseDataFromBuffer(packet), packet.size());
    }
}

void AvatarDataTests::parseCompleteHandControllers() {
    const auto flags = AvatarDataPacket::PACKET_HAS_HAND_CONTROLLERS;
    QByteArray packet(sizeof(flags) + AvatarDataPacket::HAND_CONTROLLERS_SIZE, '\0');
    memcpy(packet.data(), &flags, sizeof(flags));

    AvatarData avatar;
    QCOMPARE(avatar.parseDataFromBuffer(packet), packet.size());
}

void AvatarDataTests::rejectNonFiniteGlobalPosition() {
    AvatarDataPacket::AvatarGlobalPosition position {};
    position.globalPosition[0] = std::numeric_limits<float>::infinity();

    AvatarData avatar;
    const auto before = avatar.getClientGlobalPosition();
    const auto packet = packetWithSection(AvatarDataPacket::PACKET_HAS_AVATAR_GLOBAL_POSITION, position);
    avatar.parseDataFromBuffer(packet);

    QCOMPARE(avatar.getClientGlobalPosition(), before);
}

void AvatarDataTests::rejectNonFiniteBoundingBox() {
    AvatarDataPacket::AvatarBoundingBox box {};
    box.avatarDimensions[1] = std::numeric_limits<float>::quiet_NaN();

    AvatarData avatar;
    const auto before = avatar.getGlobalBoundingBox();
    const auto packet = packetWithSection(AvatarDataPacket::PACKET_HAS_AVATAR_BOUNDING_BOX, box);
    avatar.parseDataFromBuffer(packet);
    const auto after = avatar.getGlobalBoundingBox();

    QCOMPARE(after.getCorner(), before.getCorner());
    QCOMPARE(after.getDimensions(), before.getDimensions());
}

void AvatarDataTests::rejectNonFiniteSensorTranslation() {
    AvatarDataPacket::SensorToWorldMatrix sensor {};
    sensor.sensorToWorldTrans[2] = -std::numeric_limits<float>::infinity();

    AvatarData avatar;
    const auto before = avatar.getSensorToWorldMatrix();
    const auto packet = packetWithSection(AvatarDataPacket::PACKET_HAS_SENSOR_TO_WORLD_MATRIX, sensor);
    avatar.parseDataFromBuffer(packet);

    QCOMPARE(avatar.getSensorToWorldMatrix(), before);
}

void AvatarDataTests::rejectNonFiniteLookAtPosition() {
    AvatarDataPacket::LookAtPosition lookAt {};
    lookAt.lookAtPosition[0] = std::numeric_limits<float>::infinity();

    AvatarData avatar;
    const auto packet = packetWithSection(AvatarDataPacket::PACKET_HAS_LOOK_AT_POSITION, lookAt);
    avatar.parseDataFromBuffer(packet);

    QCOMPARE(avatar.getHeadData()->getLookAtPosition(), glm::vec3(0.0f));
}

void AvatarDataTests::rejectNonFiniteLocalPosition() {
    AvatarDataPacket::AvatarLocalPosition position {};
    position.localPosition[1] = std::numeric_limits<float>::quiet_NaN();

    AvatarData avatar;
    avatar.setParentID(QUuid("{00000000-0000-0000-0000-000000000001}"));
    const auto before = avatar.getLocalPosition();
    const auto packet = packetWithSection(AvatarDataPacket::PACKET_HAS_AVATAR_LOCAL_POSITION, position);
    avatar.parseDataFromBuffer(packet);

    QCOMPARE(avatar.getLocalPosition(), before);
}

void AvatarDataTests::rejectNonFiniteFaceCoefficient() {
    const auto flags = AvatarDataPacket::PACKET_HAS_FACE_TRACKER_INFO;
    AvatarDataPacket::FaceTrackerInfo info {};
    info.numBlendshapeCoefficients = 1;
    float coefficient = 0.5f;
    QByteArray packet(sizeof(flags) + sizeof(info) + sizeof(coefficient), '\0');
    memcpy(packet.data(), &flags, sizeof(flags));
    memcpy(packet.data() + sizeof(flags), &info, sizeof(info));
    memcpy(packet.data() + sizeof(flags) + sizeof(info), &coefficient, sizeof(coefficient));

    AvatarData avatar;
    avatar.parseDataFromBuffer(packet);
    QCOMPARE(avatar.getHeadData()->getBlendshapeCoefficients(), QVector<float> { coefficient });

    coefficient = std::numeric_limits<float>::quiet_NaN();
    memcpy(packet.data() + sizeof(flags) + sizeof(info), &coefficient, sizeof(coefficient));
    avatar.parseDataFromBuffer(packet);
    QCOMPARE(avatar.getHeadData()->getBlendshapeCoefficients(), QVector<float> { 0.5f });
}

void AvatarDataTests::rejectNonFiniteFarGrabTransform() {
    const AvatarDataPacket::HasFlags flags =
        AvatarDataPacket::PACKET_HAS_JOINT_DATA | AvatarDataPacket::PACKET_HAS_GRAB_JOINTS;
    AvatarDataPacket::FarGrabJoints farGrab {};
    farGrab.leftFarGrabPosition[0] = std::numeric_limits<float>::infinity();
    const uint8_t numJoints = 0;
    const float maxTranslationDimension = 1.0f;
    QByteArray packet(sizeof(flags) + sizeof(numJoints) + sizeof(maxTranslationDimension) + sizeof(farGrab), '\0');
    char* destination = packet.data();
    memcpy(destination, &flags, sizeof(flags));
    destination += sizeof(flags);
    memcpy(destination, &numJoints, sizeof(numJoints));
    destination += sizeof(numJoints);
    memcpy(destination, &maxTranslationDimension, sizeof(maxTranslationDimension));
    destination += sizeof(maxTranslationDimension);
    memcpy(destination, &farGrab, sizeof(farGrab));

    AvatarData avatar;
    avatar.parseDataFromBuffer(packet);
    QVERIFY(!avatar.isJointDataValid(FARGRAB_LEFTHAND_INDEX));
    QVERIFY(!avatar.isJointDataValid(FARGRAB_RIGHTHAND_INDEX));
    QVERIFY(!avatar.isJointDataValid(FARGRAB_MOUSE_INDEX));
}

QTEST_MAIN(AvatarDataTests)

#include "AvatarDataTests.moc"
