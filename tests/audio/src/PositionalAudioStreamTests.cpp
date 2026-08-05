//
//  PositionalAudioStreamTests.cpp
//  tests/audio/src
//
//  SPDX-License-Identifier: Apache-2.0
//

#include "PositionalAudioStreamTests.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <limits>

#include <QDataStream>

#include <InjectedAudioStream.h>
#include <PositionalAudioStream.h>
#include <ReceivedMessage.h>

QTEST_GUILESS_MAIN(PositionalAudioStreamTests)

namespace {

class TestPositionalAudioStream : public PositionalAudioStream {
public:
    TestPositionalAudioStream() : PositionalAudioStream(Microphone, false, 1) {}

    using PositionalAudioStream::parsePositionalData;
};

QByteArray positionalData(const glm::vec3& position = glm::vec3(1.0f, 2.0f, 3.0f),
                          const glm::quat& orientation = glm::quat(1.0f, 0.1f, 0.2f, 0.3f),
                          const glm::vec3& corner = glm::vec3(-1.0f, -2.0f, -3.0f),
                          const glm::vec3& scale = glm::vec3(0.5f, 1.5f, 0.75f)) {
    QByteArray result;
    result.append(reinterpret_cast<const char*>(&position), sizeof(position));
    result.append(reinterpret_cast<const char*>(&orientation), sizeof(orientation));
    result.append(reinterpret_cast<const char*>(&corner), sizeof(corner));
    result.append(reinterpret_cast<const char*>(&scale), sizeof(scale));
    return result;
}

void compareVec3(const glm::vec3& actual, const glm::vec3& expected) {
    QCOMPARE(actual.x, expected.x);
    QCOMPARE(actual.y, expected.y);
    QCOMPARE(actual.z, expected.z);
}

void compareQuat(const glm::quat& actual, const glm::quat& expected) {
    QCOMPARE(actual.x, expected.x);
    QCOMPARE(actual.y, expected.y);
    QCOMPARE(actual.z, expected.z);
    QCOMPARE(actual.w, expected.w);
}

QByteArray injectedProperties(const QByteArray& positional, quint8 stereoFlag = 0, quint8 loopbackFlag = 0,
                              float radius = 0.0f, quint8 ignorePenumbraFlag = 0) {
    QByteArray result;
    QDataStream stream(&result, QIODevice::WriteOnly);
    stream.writeRawData(QUuid::createUuid().toRfc4122().constData(), NUM_BYTES_RFC4122_UUID);
    stream << stereoFlag << loopbackFlag;
    stream.writeRawData(positional.constData(), positional.size());
    stream << radius << quint8(195) << ignorePenumbraFlag;
    return result;
}

QByteArray audioMessage(const QByteArray& properties, bool includeAudioSample = false) {
    QByteArray result;
    const quint16 sequence { 0 };
    const uint32_t codecSize { 0 };
    result.append(reinterpret_cast<const char*>(&sequence), sizeof(sequence));
    result.append(reinterpret_cast<const char*>(&codecSize), sizeof(codecSize));
    result.append(properties);
    if (includeAudioSample) {
        const int16_t sample { 42 };
        result.append(reinterpret_cast<const char*>(&sample), sizeof(sample));
    }
    return result;
}

} // namespace

void PositionalAudioStreamTests::testValidPositionalData() {
    TestPositionalAudioStream stream;
    const glm::vec3 position(1.0f, 2.0f, 3.0f);
    const glm::quat orientation(1.0f, 0.1f, 0.2f, 0.3f);
    const glm::vec3 corner(-1.0f, -2.0f, -3.0f);
    const glm::vec3 scale(0.5f, 1.5f, 0.75f);
    const QByteArray data = positionalData(position, orientation, corner, scale);

    QCOMPARE(stream.parsePositionalData(data), data.size());
    compareVec3(stream.getPosition(), position);
    compareQuat(stream.getOrientation(), orientation);
    compareVec3(stream.getAvatarBoundingBoxCorner(), corner);
    compareVec3(stream.getAvatarBoundingBoxScale(), scale);
}

void PositionalAudioStreamTests::testTruncatedPositionalData() {
    const QByteArray complete = positionalData();
    for (int size = 0; size < complete.size(); ++size) {
        TestPositionalAudioStream stream;
        QCOMPARE(stream.parsePositionalData(complete.left(size)), -1);
        compareVec3(stream.getPosition(), glm::vec3(0.0f));
        compareQuat(stream.getOrientation(), glm::quat(0.0f, 0.0f, 0.0f, 0.0f));
    }
}

void PositionalAudioStreamTests::testNonFinitePositionalData() {
    const QByteArray valid = positionalData();
    const std::array<int, 4> offsets {{
        0,
        static_cast<int>(sizeof(glm::vec3) + sizeof(float)),
        static_cast<int>(sizeof(glm::vec3) + sizeof(glm::quat) + 2 * sizeof(float)),
        static_cast<int>(sizeof(glm::vec3) + sizeof(glm::quat) + sizeof(glm::vec3))
    }};

    for (int offset : offsets) {
        TestPositionalAudioStream stream;
        QCOMPARE(stream.parsePositionalData(valid), valid.size());
        QByteArray invalid = valid;
        const float infinity = std::numeric_limits<float>::infinity();
        memcpy(invalid.data() + offset, &infinity, sizeof(infinity));
        QCOMPARE(stream.parsePositionalData(invalid), -1);
        compareVec3(stream.getPosition(), glm::vec3(1.0f, 2.0f, 3.0f));
    }
}

void PositionalAudioStreamTests::testInjectedAudioPropertyBounds() {
    const QByteArray properties = injectedProperties(positionalData());
    for (int size = 0; size < properties.size(); ++size) {
        InjectedAudioStream stream(QUuid::createUuid(), false, 1);
        ReceivedMessage message(audioMessage(properties.left(size)), PacketType::InjectAudio, 0, SockAddr());
        stream.parseData(message);
        QCOMPARE(stream.getPacketsReceived(), 0);
        QCOMPARE(stream.getSamplesAvailable(), 0);
        compareVec3(stream.getPosition(), glm::vec3(0.0f));
        QCOMPARE(stream.getRadius(), 0.0f);
    }

    InjectedAudioStream stream(QUuid::createUuid(), false, 1);
    ReceivedMessage message(audioMessage(properties, true), PacketType::InjectAudio, 0, SockAddr());
    stream.parseData(message);
    QCOMPARE(stream.getSamplesAvailable(), 1);
    compareVec3(stream.getPosition(), glm::vec3(1.0f, 2.0f, 3.0f));

    QByteArray truncatedCodec;
    const quint16 sequence { 0 };
    const uint32_t codecSize { 1 };
    truncatedCodec.append(reinterpret_cast<const char*>(&sequence), sizeof(sequence));
    truncatedCodec.append(reinterpret_cast<const char*>(&codecSize), sizeof(codecSize));
    ReceivedMessage truncatedCodecMessage(truncatedCodec, PacketType::InjectAudio, 0, SockAddr());
    InjectedAudioStream truncatedCodecStream(QUuid::createUuid(), false, 1);
    truncatedCodecStream.parseData(truncatedCodecMessage);
    QCOMPARE(truncatedCodecStream.getPacketsReceived(), 0);
    QCOMPARE(truncatedCodecStream.getSamplesAvailable(), 0);
}

void PositionalAudioStreamTests::testInvalidInjectedAudioProperties() {
    const std::array<QByteArray, 5> invalidProperties {{
        injectedProperties(positionalData(), 2, 0, 0.0f, 0),
        injectedProperties(positionalData(), 0, 2, 0.0f, 0),
        injectedProperties(positionalData(), 0, 0, -1.0f, 0),
        injectedProperties(positionalData(), 0, 0, std::numeric_limits<float>::infinity(), 0),
        injectedProperties(positionalData(), 0, 0, 0.0f, 2)
    }};

    for (const QByteArray& properties : invalidProperties) {
        InjectedAudioStream stream(QUuid::createUuid(), false, 1);
        ReceivedMessage message(audioMessage(properties, true), PacketType::InjectAudio, 0, SockAddr());
        stream.parseData(message);
        QCOMPARE(stream.getPacketsReceived(), 0);
        QCOMPARE(stream.getSamplesAvailable(), 0);
        compareVec3(stream.getPosition(), glm::vec3(0.0f));
        QCOMPARE(stream.getRadius(), 0.0f);
    }
}
