// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>

#include <cmath>
#include <cstring>
#include <limits>

#include <AvatarData.h>
#include <AvatarHashMap.h>
#include <HeadData.h>

template<typename Section>
QByteArray packetWithSection(AvatarDataPacket::HasFlags flags, const Section& section) {
    QByteArray packet(sizeof(flags) + sizeof(section), '\0');
    memcpy(packet.data(), &flags, sizeof(flags));
    memcpy(packet.data() + sizeof(flags), &section, sizeof(section));
    return packet;
}

AvatarSkeletonTrait::UnpackedJointData skeletonJoint(const QString& name, const glm::vec3& translation,
                                                     float scale, int boneType) {
    AvatarSkeletonTrait::UnpackedJointData joint {};
    joint.jointName = name;
    joint.defaultTranslation = translation;
    joint.defaultRotation = Quaternions::IDENTITY;
    joint.defaultScale = scale;
    joint.boneType = boneType;
    joint.parentIndex = boneType == AvatarSkeletonTrait::BoneType::SkeletonRoot ? -1 : 0;
    return joint;
}

class AvatarDataTests : public QObject {
    Q_OBJECT

private slots:
    void parseTruncatedFlags();
    void parseTruncatedSections();
    void parseTruncatedHandControllers();
    void parseCompleteHandControllers();
    void rejectNonFiniteGlobalPosition();
    void rejectNonFiniteBoundingBox();
    void rejectNonFiniteSensorTranslation();
    void rejectNonFiniteLookAtPosition();
    void rejectNonFiniteLocalPosition();
    void rejectNonFiniteFaceCoefficient();
    void rejectNonFiniteFarGrabTransform();
    void roundTripSkeletonTrait();
    void limitSkeletonTraitJointCount();
    void rejectMalformedSkeletonTrait();
    void rejectTruncatedAvatarIdentity();
    void replicateAvatarIdentity();
    void validateAvatarTraitWireFields();
};

void AvatarDataTests::parseTruncatedFlags() {
    AvatarData avatar;
    const QByteArray emptyPacket;
    const QByteArray oneBytePacket(1, '\0');

    QCOMPARE(avatar.parseDataFromBuffer(emptyPacket), emptyPacket.size());
    QCOMPARE(avatar.parseDataFromBuffer(oneBytePacket), oneBytePacket.size());
}

void AvatarDataTests::parseTruncatedSections() {
    using namespace AvatarDataPacket;

    const QVector<QPair<HasFlags, int>> fixedSections {
        { PACKET_HAS_AVATAR_GLOBAL_POSITION, int(sizeof(AvatarGlobalPosition)) },
        { PACKET_HAS_AVATAR_BOUNDING_BOX, int(sizeof(AvatarBoundingBox)) },
        { PACKET_HAS_AVATAR_ORIENTATION, int(sizeof(SixByteQuat)) },
        { PACKET_HAS_AVATAR_SCALE, int(sizeof(AvatarScale)) },
        { PACKET_HAS_LOOK_AT_POSITION, int(sizeof(LookAtPosition)) },
        { PACKET_HAS_AUDIO_LOUDNESS, int(sizeof(AudioLoudness)) },
        { PACKET_HAS_SENSOR_TO_WORLD_MATRIX, int(sizeof(SensorToWorldMatrix)) },
        { PACKET_HAS_ADDITIONAL_FLAGS, int(sizeof(AdditionalFlags)) },
        { PACKET_HAS_PARENT_INFO, int(sizeof(ParentInfo)) },
        { PACKET_HAS_AVATAR_LOCAL_POSITION, int(sizeof(AvatarLocalPosition)) },
        { PACKET_HAS_HAND_CONTROLLERS, int(HAND_CONTROLLERS_SIZE) },
    };

    QVector<QByteArray> packets;
    for (const auto& section : fixedSections) {
        QByteArray packet(sizeof(HasFlags) + section.second, '\0');
        memcpy(packet.data(), &section.first, sizeof(HasFlags));
        packets.push_back(packet);
    }

    FaceTrackerInfo faceInfo {};
    faceInfo.numBlendshapeCoefficients = 2;
    QByteArray facePacket(sizeof(HasFlags) + sizeof(faceInfo) + 2 * sizeof(float), '\0');
    const HasFlags faceFlags = PACKET_HAS_FACE_TRACKER_INFO;
    memcpy(facePacket.data(), &faceFlags, sizeof(faceFlags));
    memcpy(facePacket.data() + sizeof(faceFlags), &faceInfo, sizeof(faceInfo));
    packets.push_back(facePacket);

    constexpr uint8_t numJoints = 8;
    constexpr int validityBytes = 1;
    constexpr int compressedJointBytes = numJoints * 6;
    const HasFlags jointFlags = PACKET_HAS_JOINT_DATA;
    QByteArray jointPacket(sizeof(HasFlags) + sizeof(numJoints) + validityBytes + compressedJointBytes +
                               validityBytes + sizeof(float) + compressedJointBytes,
                           '\0');
    char* jointCursor = jointPacket.data();
    memcpy(jointCursor, &jointFlags, sizeof(jointFlags));
    jointCursor += sizeof(jointFlags);
    memcpy(jointCursor, &numJoints, sizeof(numJoints));
    jointCursor += sizeof(numJoints);
    *jointCursor++ = static_cast<char>(0xff);
    jointCursor += compressedJointBytes;
    *jointCursor++ = static_cast<char>(0xff);
    const float maxTranslationDimension = 1.0f;
    memcpy(jointCursor, &maxTranslationDimension, sizeof(maxTranslationDimension));
    packets.push_back(jointPacket);

    QByteArray farGrabPacket = jointPacket;
    const HasFlags farGrabFlags = jointFlags | PACKET_HAS_GRAB_JOINTS;
    memcpy(farGrabPacket.data(), &farGrabFlags, sizeof(farGrabFlags));
    FarGrabJoints farGrab {};
    farGrab.leftFarGrabRotation[0] = 1.0f;
    farGrab.rightFarGrabRotation[0] = 1.0f;
    farGrab.mouseFarGrabRotation[0] = 1.0f;
    farGrabPacket.append(reinterpret_cast<const char*>(&farGrab), sizeof(farGrab));
    packets.push_back(farGrabPacket);

    const HasFlags defaultPoseFlags = PACKET_HAS_JOINT_DEFAULT_POSE_FLAGS;
    QByteArray defaultPosePacket(sizeof(HasFlags) + sizeof(numJoints) + 2 * validityBytes, '\0');
    memcpy(defaultPosePacket.data(), &defaultPoseFlags, sizeof(defaultPoseFlags));
    memcpy(defaultPosePacket.data() + sizeof(defaultPoseFlags), &numJoints, sizeof(numJoints));
    packets.push_back(defaultPosePacket);

    for (const auto& completePacket : packets) {
        HasFlags packetFlags;
        memcpy(&packetFlags, completePacket.constData(), sizeof(packetFlags));
        const bool containsJointState = packetFlags &
            (PACKET_HAS_JOINT_DATA | PACKET_HAS_JOINT_DEFAULT_POSE_FLAGS);
        for (int size = sizeof(HasFlags); size < completePacket.size(); ++size) {
            AvatarData avatar;
            QVector<JointData> previousJointData;
            if (containsJointState) {
                avatar.setJointData(0, glm::quat(1.0f, 0.0f, 0.0f, 0.0f), glm::vec3(1.0f, 2.0f, 3.0f));
                previousJointData = avatar.getJointData();
            }
            const auto truncatedPacket = completePacket.left(size);
            QCOMPARE(avatar.parseDataFromBuffer(truncatedPacket), truncatedPacket.size());
            if (containsJointState) {
                const auto jointData = avatar.getJointData();
                QCOMPARE(jointData.size(), previousJointData.size());
                QVERIFY(jointData[0].rotation == previousJointData[0].rotation);
                QVERIFY(jointData[0].translation == previousJointData[0].translation);
                QCOMPARE(jointData[0].rotationIsDefaultPose, previousJointData[0].rotationIsDefaultPose);
                QCOMPARE(jointData[0].translationIsDefaultPose, previousJointData[0].translationIsDefaultPose);
            }
        }

        AvatarData avatar;
        QCOMPARE(avatar.parseDataFromBuffer(completePacket), completePacket.size());
    }
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
    avatar.setJointData(0, glm::quat(1.0f, 0.0f, 0.0f, 0.0f), glm::vec3(1.0f, 2.0f, 3.0f));
    const auto previousJointData = avatar.getJointData();
    avatar.parseDataFromBuffer(packet);
    const auto jointData = avatar.getJointData();
    QCOMPARE(jointData.size(), previousJointData.size());
    QVERIFY(jointData[0].rotation == previousJointData[0].rotation);
    QVERIFY(jointData[0].translation == previousJointData[0].translation);
    QVERIFY(!avatar.isJointDataValid(FARGRAB_LEFTHAND_INDEX));
    QVERIFY(!avatar.isJointDataValid(FARGRAB_RIGHTHAND_INDEX));
    QVERIFY(!avatar.isJointDataValid(FARGRAB_MOUSE_INDEX));
}

void AvatarDataTests::roundTripSkeletonTrait() {
    const QString firstName = QString::fromUtf8("Hüfte");
    const QString secondName = QString::fromUtf8("右手");
    const QString invalidName = QStringLiteral("invalid");
    auto invalidJoint = skeletonJoint(invalidName,
        glm::vec3(std::numeric_limits<float>::quiet_NaN()), std::numeric_limits<float>::infinity(),
        AvatarSkeletonTrait::BoneType::SkeletonChild);
    invalidJoint.defaultRotation = glm::quat(0.0f, 0.0f, 0.0f, 0.0f);
    std::vector<AvatarSkeletonTrait::UnpackedJointData> sourceJoints {
        skeletonJoint(firstName, glm::vec3(-0.25f, -2.0f, -0.5f), 0.0f,
            AvatarSkeletonTrait::BoneType::SkeletonRoot),
        skeletonJoint(secondName, glm::vec3(0.5f, 1.0f, -1.5f), 0.5f,
            AvatarSkeletonTrait::BoneType::SkeletonChild),
        invalidJoint
    };
    AvatarData source;
    source.setSkeletonData(sourceJoints);

    const QByteArray packed = source.packTrait(AvatarTraits::SkeletonData);
    AvatarSkeletonTrait::Header header;
    memcpy(&header, packed.constData(), sizeof(header));
    QCOMPARE(header.numJoints, uint8_t(3));
    QCOMPARE(header.maxTranslationDimension, 2.0f);
    QCOMPARE(header.maxScaleDimension, 1.0f);
    QCOMPARE(header.stringTableLength,
        uint16_t(firstName.toUtf8().size() + secondName.toUtf8().size() + invalidName.toUtf8().size()));

    AvatarData destination;
    destination.processTrait(AvatarTraits::SkeletonData, packed);
    const auto result = destination.getSkeletonData();
    QCOMPARE(result.size(), size_t(3));
    QCOMPARE(result[0].jointName, firstName);
    QCOMPARE(result[1].jointName, secondName);
    QVERIFY(std::abs(result[0].defaultTranslation.x + 0.25f) < 2.0e-4f);
    QVERIFY(std::abs(result[0].defaultTranslation.y + 2.0f) < 2.0e-4f);
    QVERIFY(std::abs(result[0].defaultTranslation.z + 0.5f) < 2.0e-4f);
    QVERIFY(std::abs(result[0].defaultScale - 1.0f) < 3.0e-4f);
    QVERIFY(std::abs(result[1].defaultScale - 0.5f) < 2.0e-4f);
    QCOMPARE(result[2].jointName, invalidName);
    QCOMPARE(result[2].defaultTranslation, glm::vec3(0.0f));
    QVERIFY(std::abs(result[2].defaultScale - 1.0f) < 3.0e-4f);
    QVERIFY(std::abs(glm::dot(result[2].defaultRotation, Quaternions::IDENTITY)) > 1.0f - 1.0e-6f);
}

void AvatarDataTests::limitSkeletonTraitJointCount() {
    std::vector<AvatarSkeletonTrait::UnpackedJointData> sourceJoints;
    for (int i = 0; i < 300; ++i) {
        sourceJoints.push_back(skeletonJoint(QString(), glm::vec3(0.0f), 1.0f,
            i == 0 ? AvatarSkeletonTrait::BoneType::SkeletonRoot : AvatarSkeletonTrait::BoneType::SkeletonChild));
    }
    AvatarData source;
    source.setSkeletonData(sourceJoints);

    const QByteArray packed = source.packTrait(AvatarTraits::SkeletonData);
    AvatarSkeletonTrait::Header header;
    memcpy(&header, packed.constData(), sizeof(header));
    QCOMPARE(header.numJoints, std::numeric_limits<uint8_t>::max());
    QCOMPARE(packed.size(), static_cast<int>(sizeof(header) +
        size_t(header.numJoints) * sizeof(AvatarSkeletonTrait::JointData)));

    AvatarData destination;
    destination.processTrait(AvatarTraits::SkeletonData, packed);
    QCOMPARE(destination.getSkeletonData().size(), size_t(std::numeric_limits<uint8_t>::max()));
}

void AvatarDataTests::rejectMalformedSkeletonTrait() {
    AvatarData source;
    source.setSkeletonData({ skeletonJoint(QStringLiteral("joint"), glm::vec3(1.0f), 1.0f,
        AvatarSkeletonTrait::BoneType::SkeletonRoot) });
    const QByteArray packed = source.packTrait(AvatarTraits::SkeletonData);

    AvatarData destination;
    const auto sentinel = skeletonJoint(QStringLiteral("sentinel"), glm::vec3(0.0f), 1.0f,
        AvatarSkeletonTrait::BoneType::SkeletonRoot);
    destination.setSkeletonData({ sentinel });
    for (int size = 0; size < packed.size(); ++size) {
        destination.processTrait(AvatarTraits::SkeletonData, packed.left(size));
        const auto unchanged = destination.getSkeletonData();
        QCOMPARE(unchanged.size(), size_t(1));
        QCOMPARE(unchanged[0].jointName, sentinel.jointName);
    }

    QByteArray malformed = packed;
    auto jointData = reinterpret_cast<AvatarSkeletonTrait::JointData*>(
        malformed.data() + sizeof(AvatarSkeletonTrait::Header));
    jointData->stringStart = std::numeric_limits<uint16_t>::max();
    destination.processTrait(AvatarTraits::SkeletonData, malformed);
    QCOMPARE(destination.getSkeletonData()[0].jointName, sentinel.jointName);

    malformed = packed;
    auto header = reinterpret_cast<AvatarSkeletonTrait::Header*>(malformed.data());
    header->maxTranslationDimension = std::numeric_limits<float>::quiet_NaN();
    destination.processTrait(AvatarTraits::SkeletonData, malformed);
    QCOMPARE(destination.getSkeletonData()[0].jointName, sentinel.jointName);
}

void AvatarDataTests::rejectTruncatedAvatarIdentity() {
    AvatarData source;
    source.setDisplayName(QStringLiteral("complete identity"));
    const QByteArray identity = source.identityByteArray();

    for (int size = 0; size < identity.size(); ++size) {
        QDataStream stream(identity.left(size));
        AvatarData destination;
        bool identityChanged { false };
        bool displayNameChanged { false };
        destination.processAvatarIdentity(stream, identityChanged, displayNameChanged);

        QVERIFY(!destination.hasProcessedFirstIdentity());
        QVERIFY(!identityChanged);
        QVERIFY(!displayNameChanged);
        QVERIFY(destination.getDisplayName().isEmpty());
    }

    QDataStream stream(identity);
    AvatarData destination;
    bool identityChanged { false };
    bool displayNameChanged { false };
    destination.processAvatarIdentity(stream, identityChanged, displayNameChanged);
    QVERIFY(destination.hasProcessedFirstIdentity());
    QCOMPARE(destination.getDisplayName(), source.getDisplayName());
    QVERIFY(identityChanged);
    QVERIFY(displayNameChanged);
}

void AvatarDataTests::replicateAvatarIdentity() {
    AvatarData source;
    source.setDisplayName(QStringLiteral("replicated identity"));
    const QByteArray identity = source.identityByteArray();

    const QUuid parentID = QUuid::createUuid();
    auto firstReplica = std::make_shared<AvatarData>();
    auto secondReplica = std::make_shared<AvatarData>();
    AvatarReplicas replicas;
    replicas.addReplica(parentID, firstReplica);
    replicas.addReplica(parentID, secondReplica);

    bool identityChanged { false };
    bool displayNameChanged { false };
    replicas.processAvatarIdentity(parentID, identity, identityChanged, displayNameChanged);

    QCOMPARE(firstReplica->getDisplayName(), source.getDisplayName());
    QCOMPARE(secondReplica->getDisplayName(), source.getDisplayName());
    QVERIFY(firstReplica->hasProcessedFirstIdentity());
    QVERIFY(secondReplica->hasProcessedFirstIdentity());
}

void AvatarDataTests::validateAvatarTraitWireFields() {
    QVERIFY(AvatarTraits::isValidTrait(AvatarTraits::SkeletonModelURL));
    QVERIFY(AvatarTraits::isValidTrait(AvatarTraits::SkeletonData));
    QVERIFY(AvatarTraits::isValidTrait(AvatarTraits::AvatarEntity));
    QVERIFY(AvatarTraits::isValidTrait(AvatarTraits::Grab));
    QVERIFY(!AvatarTraits::isValidTrait(AvatarTraits::NullTrait));
    QVERIFY(!AvatarTraits::isValidTrait(static_cast<AvatarTraits::TraitType>(AvatarTraits::TotalTraitTypes)));
    QVERIFY(!AvatarTraits::isValidTrait(static_cast<AvatarTraits::TraitType>(-2)));

    QVERIFY(AvatarTraits::isValidTraitWireSize(0, 0, false));
    QVERIFY(AvatarTraits::isValidTraitWireSize(4, 4, false));
    QVERIFY(!AvatarTraits::isValidTraitWireSize(5, 4, false));
    QVERIFY(!AvatarTraits::isValidTraitWireSize(-1, 4, false));
    QVERIFY(AvatarTraits::isValidTraitWireSize(AvatarTraits::DELETED_TRAIT_SIZE, 0, true));
    QVERIFY(!AvatarTraits::isValidTraitWireSize(-2, 100, true));
}

QTEST_MAIN(AvatarDataTests)

#include "AvatarDataTests.moc"
