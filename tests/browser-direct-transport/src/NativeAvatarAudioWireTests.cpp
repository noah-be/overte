// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include <AvatarData.h>
#include <AvatarTraits.h>
#include <AudioConstants.h>
#include <GLMHelpers.h>
#include <NLPacket.h>

namespace {
glm::vec3 vector(const QJsonObject& value) {
    return glm::vec3(value.value("x").toDouble(), value.value("y").toDouble(), value.value("z").toDouble());
}
glm::quat orientation(const QJsonObject& value) {
    return glm::quat(value.value("w").toDouble(), value.value("x").toDouble(),
                     value.value("y").toDouble(), value.value("z").toDouble());
}
QByteArray payload(const NLPacket& packet) {
    return QByteArray(packet.getPayload(), packet.getPayloadSize());
}
class FixtureAvatar : public AvatarData {
public:
    void setGlobalPositionForWire(const glm::vec3& value) { _globalPosition = value; }
    QByteArray skeletonBytes() const { return packSkeletonData(); }
};
} // namespace

class NativeAvatarAudioWireTests : public QObject {
    Q_OBJECT
private:
    QJsonObject _fixtures;
private slots:
    void initTestCase() {
        QFile file(QFINDTESTDATA("../../../browser-direct-client/tests/fixtures/native-avatar-audio.json"));
        QVERIFY(file.open(QIODevice::ReadOnly));
        _fixtures = QJsonDocument::fromJson(file.readAll()).object();
        QVERIFY(!_fixtures.isEmpty());
    }
    void productionAvatarPoseMatchesBrowserFixture() {
        const auto fixture = _fixtures.value("avatar").toObject();
        FixtureAvatar avatar;
        avatar.setSessionUUID(QUuid(fixture.value("uuid").toString()));
        avatar.setGlobalPositionForWire(vector(fixture.value("position").toObject()));
        avatar.setLocalOrientation(orientation(fixture.value("orientation").toObject()));
        avatar.setTargetScale(fixture.value("scale").toDouble());
        avatar.setAudioLoudness(fixture.value("loudness").toDouble());
        avatar.setJointData(0, orientation(fixture.value("orientation").toObject()),
                           vector(fixture.value("jointTranslation").toObject()));
        AvatarDataPacket::SendStatus status;
        status.itemFlags = AvatarDataPacket::PACKET_HAS_AVATAR_GLOBAL_POSITION
            | AvatarDataPacket::PACKET_HAS_AVATAR_ORIENTATION | AvatarDataPacket::PACKET_HAS_AVATAR_SCALE
            | AvatarDataPacket::PACKET_HAS_AUDIO_LOUDNESS | AvatarDataPacket::PACKET_HAS_JOINT_DATA
            | AvatarDataPacket::PACKET_HAS_JOINT_DEFAULT_POSE_FLAGS;
        const auto state = avatar.toByteArray(AvatarData::SendAllData, 0, QVector<JointData>(1), status,
                                             true, false, glm::vec3(0), nullptr, 0);
        auto packet = NLPacket::create(PacketType::AvatarData);
        packet->writePrimitive(static_cast<quint16>(fixture.value("sequence").toInt()));
        packet->write(state);
        QCOMPARE(payload(*packet).toHex(), fixture.value("hex").toString().toUtf8());

        AvatarData decoded;
        QCOMPARE(decoded.parseDataFromBuffer(state), state.size());
        const auto joints = decoded.getJointData();
        QCOMPARE(joints.size(), 1);
        QVERIFY(joints[0].translation == vector(fixture.value("jointTranslation").toObject()));
        QVERIFY(!joints[0].rotationIsDefaultPose && !joints[0].translationIsDefaultPose);
    }
    void productionSkeletonTraitMatchesBrowserFixture() {
        const auto fixture = _fixtures.value("skeleton").toObject();
        std::vector<AvatarSkeletonTrait::UnpackedJointData> joints;
        for (const auto& value : fixture.value("joints").toArray()) {
            const auto input = value.toObject();
            AvatarSkeletonTrait::UnpackedJointData joint {};
            joint.jointName = input.value("jointName").toString();
            joint.jointIndex = input.value("jointIndex").toInt();
            joint.parentIndex = input.value("parentIndex").toInt();
            joint.boneType = input.value("boneType").toInt();
            joint.defaultTranslation = vector(input.value("defaultTranslation").toObject());
            joint.defaultRotation = orientation(input.value("defaultRotation").toObject());
            joint.defaultScale = input.value("defaultScale").toDouble();
            joints.push_back(joint);
        }
        FixtureAvatar avatar;
        avatar.setSkeletonData(joints);
        QCOMPARE(avatar.skeletonBytes().toHex(), fixture.value("bodyHex").toString().toUtf8());
    }
    void nativeAudioPacketsMatchBrowserFixture() {
        const auto microphone = _fixtures.value("microphone").toObject();
        auto mic = NLPacket::create(PacketType::MicrophoneAudioNoEcho);
        mic->writePrimitive(static_cast<quint16>(microphone.value("sequence").toInt()));
        mic->writeString(microphone.value("codec").toString());
        mic->writePrimitive(quint8(0));
        mic->writePrimitive(vector(microphone.value("audioPosition").toObject()));
        mic->writePrimitive(orientation(microphone.value("audioOrientation").toObject()));
        mic->writePrimitive(vector(microphone.value("avatarBoundingBoxCorner").toObject()));
        mic->writePrimitive(vector(microphone.value("avatarBoundingBoxScale").toObject()));
        for (int i = 0; i < AudioConstants::NETWORK_FRAME_SAMPLES_PER_CHANNEL; ++i) {
            mic->writePrimitive(static_cast<int16_t>((i % 16) * 1024 - 8192));
        }
        QCOMPARE(payload(*mic).toHex(), microphone.value("hex").toString().toUtf8());
        QCOMPARE(mic->getPayloadSize(), qint64(542));

        const auto mixed = _fixtures.value("mixedAudio").toObject();
        auto mix = NLPacket::create(PacketType::MixedAudio);
        mix->writePrimitive(static_cast<quint16>(mixed.value("sequence").toInt()));
        mix->writeString(mixed.value("codec").toString());
        for (int i = 0; i < AudioConstants::NETWORK_FRAME_SAMPLES_PER_CHANNEL; ++i) {
            auto sample = static_cast<int16_t>((i % 16) * 1024 - 8192);
            mix->writePrimitive(sample);
            mix->writePrimitive(static_cast<int16_t>(-sample));
        }
        QCOMPARE(payload(*mix).toHex(), mixed.value("hex").toString().toUtf8());

        const auto silent = _fixtures.value("silentMixer").toObject();
        auto silence = NLPacket::create(PacketType::SilentAudioFrame);
        silence->writePrimitive(static_cast<quint16>(silent.value("sequence").toInt()));
        silence->writeString(silent.value("codec").toString());
        // Preserve the mixer's existing int32 sample count, unlike client uint16.
        silence->writePrimitive(AudioConstants::NETWORK_FRAME_SAMPLES_STEREO);
        QCOMPARE(payload(*silence).toHex(), silent.value("hex").toString().toUtf8());
    }
    void productionQuaternionPackingMatchesBrowserFixture() {
        for (const auto& value : _fixtures.value("quaternions").toArray()) {
            const auto fixture = value.toObject();
            unsigned char bytes[6];
            QCOMPARE(packOrientationQuatToSixBytes(bytes, orientation(fixture.value("input").toObject())), 6);
            QCOMPARE(QByteArray(reinterpret_cast<const char*>(bytes), sizeof(bytes)).toHex(),
                     fixture.value("hex").toString().toUtf8());
        }
    }
};

QTEST_GUILESS_MAIN(NativeAvatarAudioWireTests)
#include "NativeAvatarAudioWireTests.moc"
