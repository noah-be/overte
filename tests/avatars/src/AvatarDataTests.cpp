// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>

#include <cstring>

#include <AvatarData.h>

class AvatarDataTests : public QObject {
    Q_OBJECT

private slots:
    void parseTruncatedFlags();
    void parseTruncatedHandControllers();
    void parseCompleteHandControllers();
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

QTEST_MAIN(AvatarDataTests)

#include "AvatarDataTests.moc"
