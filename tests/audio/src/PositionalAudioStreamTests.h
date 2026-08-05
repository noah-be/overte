//
//  PositionalAudioStreamTests.h
//  tests/audio/src
//
//  SPDX-License-Identifier: Apache-2.0
//

#ifndef hifi_PositionalAudioStreamTests_h
#define hifi_PositionalAudioStreamTests_h

#include <QtTest/QtTest>

class PositionalAudioStreamTests : public QObject {
    Q_OBJECT
private slots:
    void testValidPositionalData();
    void testTruncatedPositionalData();
    void testNonFinitePositionalData();
    void testInjectedAudioPropertyBounds();
    void testInvalidInjectedAudioProperties();
};

#endif // hifi_PositionalAudioStreamTests_h
