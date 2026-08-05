// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>

#include <cstdint>
#include <cstring>

#include <ReceivedMessage.h>

class ReceivedMessageTests : public QObject {
    Q_OBJECT

private slots:
    void readWithoutCopyBounds();
    void copiedReadBounds();
    void negativeSizesDoNotAdvance();
    void seekBounds();
    void stringReadBounds();
};

static ReceivedMessage makeMessage() {
    return ReceivedMessage(QByteArray("data"), PacketType::Unknown, 0, SockAddr());
}

void ReceivedMessageTests::readWithoutCopyBounds() {
    auto message = makeMessage();

    QCOMPARE(message.readWithoutCopy(100), QByteArray("data"));
    QCOMPARE(message.getPosition(), 4);
    QCOMPARE(message.getBytesLeftToRead(), 0);
    QVERIFY(message.readWithoutCopy(1).isEmpty());
    QCOMPARE(message.getPosition(), 4);
}

void ReceivedMessageTests::copiedReadBounds() {
    auto message = makeMessage();

    QCOMPARE(message.peek(100), QByteArray("data"));
    QCOMPARE(message.getPosition(), 0);
    QCOMPARE(message.read(100), QByteArray("data"));
    QCOMPARE(message.getPosition(), 4);
    QCOMPARE(message.getBytesLeftToRead(), 0);

    auto rawMessage = makeMessage();
    char destination[10] {};
    QCOMPARE(rawMessage.peek(destination, sizeof(destination)), 4);
    QCOMPARE(QByteArray(destination, 4), QByteArray("data"));
    QCOMPARE(rawMessage.getPosition(), 0);
    QCOMPARE(rawMessage.read(destination, sizeof(destination)), 4);
    QCOMPARE(rawMessage.getPosition(), 4);

    auto headMessage = makeMessage();
    QCOMPARE(headMessage.readHead(sizeof(destination)), QByteArray("data"));
    QCOMPARE(headMessage.getPosition(), 4);
}

void ReceivedMessageTests::negativeSizesDoNotAdvance() {
    auto message = makeMessage();
    char destination[4] {};

    QVERIFY(message.peek(-1).isEmpty());
    QVERIFY(message.read(-1).isEmpty());
    QVERIFY(message.readWithoutCopy(-1).isEmpty());
    QCOMPARE(message.peek(destination, -1), 0);
    QCOMPARE(message.read(destination, -1), 0);
    QCOMPARE(message.readHead(destination, -1), 0);
    QCOMPARE(message.getPosition(), 0);
}

void ReceivedMessageTests::seekBounds() {
    auto message = makeMessage();

    message.seek(-1);
    QCOMPARE(message.getPosition(), 0);
    message.seek(100);
    QCOMPARE(message.getPosition(), 4);
    QCOMPARE(message.getBytesLeftToRead(), 0);
}

void ReceivedMessageTests::stringReadBounds() {
    auto truncatedHeader = ReceivedMessage(QByteArray(2, '\0'), PacketType::Unknown, 0, SockAddr());
    QVERIFY(truncatedHeader.readString().isEmpty());
    QCOMPARE(truncatedHeader.getPosition(), 2);

    const uint32_t declaredSize = 100;
    QByteArray data(sizeof(declaredSize), '\0');
    memcpy(data.data(), &declaredSize, sizeof(declaredSize));
    data.append("text");
    auto truncatedBody = ReceivedMessage(data, PacketType::Unknown, 0, SockAddr());
    QCOMPARE(truncatedBody.readString(), QString("text"));
    QCOMPARE(truncatedBody.getPosition(), data.size());
    QCOMPARE(truncatedBody.getBytesLeftToRead(), 0);
}

QTEST_MAIN(ReceivedMessageTests)

#include "ReceivedMessageTests.moc"
