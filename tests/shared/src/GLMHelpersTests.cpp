//
//  GLMHelpersTests.cpp
//  tests/shared/src
//
//  Created by Anthony Thibault on 2015.12.29
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "GLMHelpersTests.h"

#include <AudioHelpers.h>
#include <NumericalConstants.h>
#include <StreamUtils.h>

#include <test-utils/QTestExtensions.h>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/simd/matrix.h>

#include <array>
#include <cmath>
#include <limits>

QTEST_MAIN(GLMHelpersTests)

void GLMHelpersTests::testEulerDecomposition() {
    // quat to euler and back again....

    const glm::quat ROT_X_90 = glm::angleAxis(PI / 2.0f, glm::vec3(1.0f, 0.0f, 0.0f));
    const glm::quat ROT_Y_180 = glm::angleAxis(PI, glm::vec3(0.0f, 1.0, 0.0f));
    const glm::quat ROT_Z_30 = glm::angleAxis(PI / 6.0f, glm::vec3(1.0f, 0.0f, 0.0f));

    const float EPSILON = 0.00001f;

    std::vector<glm::quat> quatVec = {
        glm::quat(),
        ROT_X_90,
        ROT_Y_180,
        ROT_Z_30,
        ROT_X_90 * ROT_Y_180 * ROT_Z_30,
        ROT_X_90 * ROT_Z_30 * ROT_Y_180,
        ROT_Y_180 * ROT_Z_30 * ROT_X_90,
        ROT_Y_180 * ROT_X_90 * ROT_Z_30,
        ROT_Z_30 * ROT_X_90 * ROT_Y_180,
        ROT_Z_30 * ROT_Y_180 * ROT_X_90,
    };

    for (auto& q : quatVec) {
        glm::vec3 euler = safeEulerAngles(q);
        glm::quat r(euler);

        // when the axis and angle are flipped.
        if (glm::dot(q, r) < 0.0f) {
            r = -r;
        }

        QCOMPARE_WITH_ABS_ERROR(q, r, EPSILON);
    }
}

void GLMHelpersTests::testInvalidFixedPointInput() {
    const std::array<float, 3> invalidInputs {{
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()
    }};
    for (float input : invalidInputs) {
        uint8_t bytes[2];
        float result;
        packFloatScalarToSignedTwoByteFixed(bytes, input, 14);
        unpackFloatScalarFromSignedTwoByteFixed(reinterpret_cast<const int16_t*>(bytes), &result, 14);
        QCOMPARE(result, 0.0f);
    }

    uint8_t bytes[6];
    glm::vec3 result;
    packFloatVec3ToSignedTwoByteFixed(bytes,
        glm::vec3(0.5f, std::numeric_limits<float>::quiet_NaN(), -0.5f), 14);
    unpackFloatVec3FromSignedTwoByteFixed(bytes, result, 14);
    QCOMPARE(result, glm::vec3(0.5f, 0.0f, -0.5f));
}

void GLMHelpersTests::testInvalidAngleInput() {
    const std::array<float, 3> invalidInputs {{
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()
    }};
    for (float input : invalidInputs) {
        uint8_t bytes[2];
        float result;
        packFloatAngleToTwoByte(bytes, input);
        unpackFloatAngleFromTwoByte(reinterpret_cast<const uint16_t*>(bytes), &result);
        QVERIFY(std::abs(result) < 0.01f);
    }

    uint8_t bytes[2];
    float result;
    packFloatAngleToTwoByte(bytes, 1000.0f);
    unpackFloatAngleFromTwoByte(reinterpret_cast<const uint16_t*>(bytes), &result);
    QCOMPARE(result, 180.0f);

    packFloatAngleToTwoByte(bytes, -1000.0f);
    unpackFloatAngleFromTwoByte(reinterpret_cast<const uint16_t*>(bytes), &result);
    QCOMPARE(result, -180.0f);
}

void GLMHelpersTests::testInvalidAudioGainInput() {
    const std::array<float, 5> silentInputs {{
        0.0f,
        -1.0f,
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()
    }};
    for (float input : silentInputs) {
        QCOMPARE(packFloatGainToByte(input), uint8_t(0));
    }

    const uint8_t unity = packFloatGainToByte(1.0f);
    QCOMPARE(unpackFloatGainFromByte(unity), 1.0f);
}

void GLMHelpersTests::testInvalidRatioInput() {
    const std::array<float, 5> invalidInputs {{
        0.0f,
        -1.0f,
        std::numeric_limits<float>::quiet_NaN(),
        std::numeric_limits<float>::infinity(),
        -std::numeric_limits<float>::infinity()
    }};
    for (float input : invalidInputs) {
        uint8_t bytes[2];
        float result;
        packFloatRatioToTwoByte(bytes, input);
        unpackFloatRatioFromTwoByte(bytes, result);
        QVERIFY(std::abs(result - 1.0f) < 3.0e-4f);
    }

    uint8_t bytes[2];
    float result;
    packFloatRatioToTwoByte(bytes, std::numeric_limits<float>::min());
    unpackFloatRatioFromTwoByte(bytes, result);
    QVERIFY(result > 0.0f);
    QVERIFY(result < 0.001f);

    packFloatRatioToTwoByte(bytes, 2000.0f);
    unpackFloatRatioFromTwoByte(bytes, result);
    QVERIFY(std::abs(result - 1000.0f) < 0.1f);

    packFloatRatioToTwoByte(bytes, 10.0f);
    unpackFloatRatioFromTwoByte(bytes, result);
    QCOMPARE(result, 10.0f);
}

static void testQuatCompression(glm::quat testQuat) {

    float MAX_COMPONENT_ERROR = 4.3e-5f;

    glm::quat q;
    uint8_t bytes[6];
    packOrientationQuatToSixBytes(bytes, testQuat);
    unpackOrientationQuatFromSixBytes(bytes, q);
    if (glm::dot(q, testQuat) < 0.0f) {
        q = -q;
    }
    QCOMPARE_WITH_ABS_ERROR(q.x, testQuat.x, MAX_COMPONENT_ERROR);
    QCOMPARE_WITH_ABS_ERROR(q.y, testQuat.y, MAX_COMPONENT_ERROR);
    QCOMPARE_WITH_ABS_ERROR(q.z, testQuat.z, MAX_COMPONENT_ERROR);
    QCOMPARE_WITH_ABS_ERROR(q.w, testQuat.w, MAX_COMPONENT_ERROR);
}

void GLMHelpersTests::testInvalidOrientationInput() {
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float infinity = std::numeric_limits<float>::infinity();
    const std::array<glm::quat, 4> invalidInputs {{
        glm::quat(0.0f, 0.0f, 0.0f, 0.0f),
        glm::quat(1.0f, nan, 0.0f, 0.0f),
        glm::quat(infinity, 0.0f, 0.0f, 0.0f),
        glm::quat(2.0f, 0.0f, 0.0f, 0.0f)
    }};

    for (const auto& input : invalidInputs) {
        uint8_t bytes[8];
        glm::quat result;
        packOrientationQuatToBytes(bytes, input);
        unpackOrientationQuatFromBytes(bytes, result);

        QVERIFY(std::isfinite(result.w));
        QVERIFY(std::isfinite(result.x));
        QVERIFY(std::isfinite(result.y));
        QVERIFY(std::isfinite(result.z));
        QCOMPARE_WITH_ABS_ERROR(std::abs(glm::dot(result, Quaternions::IDENTITY)), 1.0f, 1.0e-6f);
    }
}

void GLMHelpersTests::testSixByteOrientationCompression() {
    const glm::quat ROT_X_90 = glm::angleAxis(PI / 2.0f, glm::vec3(1.0f, 0.0f, 0.0f));
    const glm::quat ROT_Y_180 = glm::angleAxis(PI, glm::vec3(0.0f, 1.0, 0.0f));
    const glm::quat ROT_Z_30 = glm::angleAxis(PI / 6.0f, glm::vec3(1.0f, 0.0f, 0.0f));

    testQuatCompression(ROT_X_90);
    testQuatCompression(ROT_Y_180);
    testQuatCompression(ROT_Z_30);
    testQuatCompression(ROT_X_90 * ROT_Y_180);
    testQuatCompression(ROT_Y_180 * ROT_X_90);
    testQuatCompression(ROT_Z_30 * ROT_X_90);
    testQuatCompression(ROT_X_90 * ROT_Z_30);
    testQuatCompression(ROT_Z_30 * ROT_Y_180);
    testQuatCompression(ROT_Y_180 * ROT_Z_30);
    testQuatCompression(ROT_X_90 * ROT_Y_180 * ROT_Z_30);
    testQuatCompression(ROT_Y_180 * ROT_Z_30 * ROT_X_90);
    testQuatCompression(ROT_Z_30 * ROT_X_90 * ROT_Y_180);

    testQuatCompression(-ROT_X_90);
    testQuatCompression(-ROT_Y_180);
    testQuatCompression(-ROT_Z_30);
    testQuatCompression(-(ROT_X_90 * ROT_Y_180));
    testQuatCompression(-(ROT_Y_180 * ROT_X_90));
    testQuatCompression(-(ROT_Z_30 * ROT_X_90));
    testQuatCompression(-(ROT_X_90 * ROT_Z_30));
    testQuatCompression(-(ROT_Z_30 * ROT_Y_180));
    testQuatCompression(-(ROT_Y_180 * ROT_Z_30));
    testQuatCompression(-(ROT_X_90 * ROT_Y_180 * ROT_Z_30));
    testQuatCompression(-(ROT_Y_180 * ROT_Z_30 * ROT_X_90));
    testQuatCompression(-(ROT_Z_30 * ROT_X_90 * ROT_Y_180));
}

void GLMHelpersTests::testMalformedSixByteOrientationCompression() {
    const std::array<std::array<uint8_t, 6>, 3> malformedInputs {{
        {{ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }},
        {{ 0x7f, 0xff, 0x7f, 0xff, 0x7f, 0xff }},
        {{ 0xff, 0xff, 0xff, 0xff, 0xff, 0xff }}
    }};

    for (const auto& bytes : malformedInputs) {
        glm::quat result;
        unpackOrientationQuatFromSixBytes(bytes.data(), result);

        QVERIFY(std::isfinite(result.w));
        QVERIFY(std::isfinite(result.x));
        QVERIFY(std::isfinite(result.y));
        QVERIFY(std::isfinite(result.z));
        QCOMPARE_WITH_ABS_ERROR(glm::length(result), 1.0f, 1.0e-6f);
    }
}

void GLMHelpersTests::testInvalidSixByteOrientationInput() {
    const float nan = std::numeric_limits<float>::quiet_NaN();
    const float infinity = std::numeric_limits<float>::infinity();
    const std::array<glm::quat, 4> invalidInputs {{
        glm::quat(0.0f, 0.0f, 0.0f, 0.0f),
        glm::quat(1.0f, nan, 0.0f, 0.0f),
        glm::quat(infinity, 0.0f, 0.0f, 0.0f),
        glm::quat(2.0f, 0.0f, 0.0f, 0.0f)
    }};

    for (const auto& input : invalidInputs) {
        uint8_t bytes[6];
        glm::quat result;
        packOrientationQuatToSixBytes(bytes, input);
        unpackOrientationQuatFromSixBytes(bytes, result);

        QVERIFY(std::isfinite(result.w));
        QVERIFY(std::isfinite(result.x));
        QVERIFY(std::isfinite(result.y));
        QVERIFY(std::isfinite(result.z));
        QCOMPARE_WITH_ABS_ERROR(std::abs(glm::dot(result, Quaternions::IDENTITY)), 1.0f, 1.0e-6f);
    }
}

#define LOOPS 500000

void GLMHelpersTests::testSimd() {
    glm::mat4 a = glm::translate(glm::mat4(), vec3(1, 4, 9));
    glm::mat4 b = glm::rotate(glm::mat4(), PI / 3, vec3(0, 1, 0));
    glm::mat4 a1, b1;
    glm::mat4 a2, b2;

    a1 = a * b;
    b1 = b * a;
    glm_mat4u_mul(a, b, a2);
    glm_mat4u_mul(b, a, b2);


    {
        QElapsedTimer timer;
        timer.start();
        for (size_t i = 0; i < LOOPS; ++i) {
            a1 = a * b;
            b1 = b * a;
        }
        qDebug() << "Native " << timer.elapsed();
    }

    {
        QElapsedTimer timer;
        timer.start();
        for (size_t i = 0; i < LOOPS; ++i) {
            glm_mat4u_mul(a, b, a2);
            glm_mat4u_mul(b, a, b2);
        }
        qDebug() << "SIMD " << timer.elapsed();
    }
    qDebug() << "Done ";
}

void GLMHelpersTests::testGenerateBasisVectors() {
    { // very simple case: primary along X, secondary is linear combination of X and Y
        glm::vec3 u(1.0f, 0.0f, 0.0f);
        glm::vec3 v(1.0f, 1.0f, 0.0f);
        glm::vec3 w;

        generateBasisVectors(u, v, u, v, w);

        QCOMPARE_WITH_ABS_ERROR(u, Vectors::UNIT_X, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(v, Vectors::UNIT_Y, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(w, Vectors::UNIT_Z, EPSILON);
    }

    { // point primary along Y instead of X
        glm::vec3 u(0.0f, 1.0f, 0.0f);
        glm::vec3 v(1.0f, 1.0f, 0.0f);
        glm::vec3 w;

        generateBasisVectors(u, v, u, v, w);

        QCOMPARE_WITH_ABS_ERROR(u, Vectors::UNIT_Y, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(v, Vectors::UNIT_X, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(w, -Vectors::UNIT_Z, EPSILON);
    }

    { // pass bad data (both vectors along Y).  The helper will guess X for secondary.
        glm::vec3 u(0.0f, 1.0f, 0.0f);
        glm::vec3 v(0.0f, 1.0f, 0.0f);
        glm::vec3 w;

        generateBasisVectors(u, v, u, v, w);

        QCOMPARE_WITH_ABS_ERROR(u, Vectors::UNIT_Y, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(v, Vectors::UNIT_X, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(w, -Vectors::UNIT_Z, EPSILON);
    }

    { // pass bad data (both vectors along X).  The helper will guess X for secondary, fail, then guess Y.
        glm::vec3 u(1.0f, 0.0f, 0.0f);
        glm::vec3 v(1.0f, 0.0f, 0.0f);
        glm::vec3 w;

        generateBasisVectors(u, v, u, v, w);

        QCOMPARE_WITH_ABS_ERROR(u, Vectors::UNIT_X, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(v, Vectors::UNIT_Y, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(w, Vectors::UNIT_Z, EPSILON);
    }

    { // general case for arbitrary rotation
        float angle = 1.234f;
        glm::vec3 axis = glm::normalize(glm::vec3(1.0f, 2.0f, 3.0f));
        glm::quat rotation = glm::angleAxis(angle, axis);

        // expected values
        glm::vec3 x = rotation * Vectors::UNIT_X;
        glm::vec3 y = rotation * Vectors::UNIT_Y;
        glm::vec3 z = rotation * Vectors::UNIT_Z;

        // primary is along x
        // secondary is linear combination of x and y
        // tertiary is unknown
        glm::vec3 u  = 1.23f * x;
        glm::vec3 v = 2.34f * x + 3.45f * y;
        glm::vec3 w;

        generateBasisVectors(u, v, u, v, w);

        QCOMPARE_WITH_ABS_ERROR(u, x, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(v, y, EPSILON);
        QCOMPARE_WITH_ABS_ERROR(w, z, EPSILON);
    }
}

void GLMHelpersTests::roundPerf() {
    const int NUM_VECS = 1000000;
    const float MAX_VEC = 500.0f;
    std::vector<glm::vec3> vecs;
    vecs.reserve(NUM_VECS);
    for (int i = 0; i < NUM_VECS; i++) {
        vecs.emplace_back(randFloatInRange(-MAX_VEC, MAX_VEC), randFloatInRange(-MAX_VEC, MAX_VEC), randFloatInRange(-MAX_VEC, MAX_VEC));
    }
    std::vector<glm::vec3> vecs2 = vecs;
    std::vector<glm::vec3> originalVecs = vecs;

    auto start = std::chrono::high_resolution_clock::now();
    for (auto& vec : vecs) {
        vec = glm::round(vec);
    }

    auto glmTime = std::chrono::high_resolution_clock::now() - start;
    start = std::chrono::high_resolution_clock::now();
    for (auto& vec : vecs2) {
        vec = glm::vec3(fastLrintf(vec.x), fastLrintf(vec.y), fastLrintf(vec.z));
    }
    auto manualTime = std::chrono::high_resolution_clock::now() - start;

    bool identical = true;
    for (decltype(vecs)::size_type i = 0; i < vecs.size(); i++) {
        identical &= vecs[i] == vecs2[i];
        if (vecs[i] != vecs2[i]) {
            qDebug() << "glm: " << vecs[i].x << vecs[i].y << vecs[i].z << ", manual: " << vecs2[i].x << vecs2[i].y << vecs2[i].z;
            qDebug() << "original: " << originalVecs[i].x << originalVecs[i].y << originalVecs[i].z;
            break;
        }
    }

    qDebug() << "ratio: " << (float)glmTime.count() / (float)manualTime.count() << ", identical: " << identical;
}
