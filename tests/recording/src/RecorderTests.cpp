//
//  RecorderTests.cpp
//  tests/recording/src
//
//  Created by Bradley Austin Davis on 11/06/15.
//  Copyright 2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-private-field"
#endif

#include <limits>

#include <QtGlobal>
#include <QtTest/QtTest>
#include <QtCore/QTemporaryFile>
#include <QtCore/QString>

#if defined(__clang__)
#pragma clang diagnostic pop
#endif

#ifdef Q_OS_WIN32
#include <Windows.h>
#endif

#include <recording/Clip.h>
#include <recording/Frame.h>

#include "Constants.h"
#include "RecorderTests.h"

using namespace recording;
FrameType TEST_FRAME_TYPE { Frame::TYPE_INVALID };

QTEST_MAIN(RecorderTests)

void RecorderTests::initTestCase() {
    TEST_FRAME_TYPE = Frame::registerFrameType(TEST_NAME);
    QVERIFY(TEST_FRAME_TYPE != Frame::TYPE_INVALID);
    QVERIFY(TEST_FRAME_TYPE != Frame::TYPE_HEADER);

    auto forwardMap = recording::Frame::getFrameTypes();
    QVERIFY(forwardMap.count(TEST_NAME) == 1);
    QVERIFY(forwardMap[TEST_NAME] == TEST_FRAME_TYPE);
    QVERIFY(forwardMap[HEADER_NAME] == recording::Frame::TYPE_HEADER);

    auto backMap = recording::Frame::getFrameTypeNames();
    QVERIFY(backMap.count(TEST_FRAME_TYPE) == 1);
    QVERIFY(backMap[TEST_FRAME_TYPE] == TEST_NAME);
    auto typeHeader = recording::Frame::TYPE_HEADER;
    QVERIFY(backMap[typeHeader] == HEADER_NAME);
}

void RecorderTests::filePersistence() {
    QTemporaryFile file;
    QVERIFY(file.open());
    const QString fileName = file.fileName();
    file.close();
    auto readClip = Clip::fromFile(fileName);
    QVERIFY(Clip::Pointer() == readClip);
    auto writeClip = Clip::newClip();
    writeClip->addFrame(std::make_shared<Frame>(
        TEST_FRAME_TYPE, Frame::secondsToFrameTime(5.0f), QByteArray()));
    QVERIFY(writeClip->frameCount() == 1);
    QVERIFY(writeClip->duration() == 5.0f);

    Clip::toFile(fileName, writeClip);
    readClip = Clip::fromFile(fileName);
    QVERIFY(readClip != Clip::Pointer());
    QVERIFY(readClip->frameCount() == 1);
    QVERIFY(readClip->duration() == 5.0f);
    readClip->seek(0);
    writeClip->seek(0);

    size_t count = 0;
    for (auto readFrame = readClip->nextFrame(), writeFrame = writeClip->nextFrame();
            readFrame && writeFrame;
            readFrame = readClip->nextFrame(), writeFrame = writeClip->nextFrame(), ++count) {
        QVERIFY(readFrame->type == writeFrame->type);
        QVERIFY(readFrame->timeOffset == writeFrame->timeOffset);
        QVERIFY(readFrame->data == writeFrame->data);
    }
    QVERIFY(readClip->frameCount() == count);

    writeClip = Clip::newClip();
    writeClip->addFrame(std::make_shared<Frame>(
        TEST_FRAME_TYPE, Frame::secondsToFrameTime(5.0f), QByteArray()));
    // Simulate an unknown frame type.
    writeClip->addFrame(std::make_shared<Frame>(
        Frame::TYPE_INVALID - 1, Frame::secondsToFrameTime(10.0f), QByteArray()));
    QVERIFY(writeClip->frameCount() == 2);
    QVERIFY(writeClip->duration() == 10.0f);
    Clip::toFile(fileName, writeClip);

    // Verify that the read version of the clip ignores the unknown frame type.
    readClip = Clip::fromFile(fileName);
    QVERIFY(readClip != Clip::Pointer());
    QVERIFY(readClip->frameCount() == 1);
    QVERIFY(readClip->duration() == 5.0f);
}

void RecorderTests::clipOrdering() {
    auto writeClip = Clip::newClip();
    // Simulate out-of-order addition of frames.
    writeClip->addFrame(std::make_shared<Frame>(
        TEST_FRAME_TYPE, Frame::secondsToFrameTime(10.0f), QByteArray()));
    writeClip->addFrame(std::make_shared<Frame>(
        TEST_FRAME_TYPE, Frame::secondsToFrameTime(5.0f), QByteArray()));
    QVERIFY(writeClip->frameCount() == 2);
    QVERIFY(writeClip->duration() == 10.0f);

    QVERIFY(std::numeric_limits<float>::max() == writeClip->position());
    writeClip->seek(0);
    QVERIFY(5.0f == writeClip->position());
    Frame::Time lastFrameTimeOffset { 0 };
    for (auto writeFrame = writeClip->nextFrame(); writeFrame;
            writeFrame = writeClip->nextFrame()) {
        QVERIFY(writeFrame->timeOffset >= lastFrameTimeOffset);
        lastFrameTimeOffset = writeFrame->timeOffset;
    }
}
