//
//  CrashRecoveryPolicyTests.cpp
//  tests/crash-recovery-policy/src
//
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include <QtTest/QtTest>

#include <CrashRecoveryPolicy.h>

class CrashRecoveryPolicyTests : public QObject {
    Q_OBJECT

private slots:
    void compiledPlatformMatchesQtPlatform();
    void iosCrashMarkerDoesNotShowDialog();
    void iosCrashMarkerCannotResetSettings();
    void iosWithoutCrashMarkerStartsNormally();
    void nonIosCrashMarkerKeepsExistingRecovery();
};

void CrashRecoveryPolicyTests::compiledPlatformMatchesQtPlatform() {
#if defined(Q_OS_IOS)
    QCOMPARE(CrashRecoveryPolicy::currentPlatform(), CrashRecoveryPolicy::Platform::IOS);
#else
    QCOMPARE(CrashRecoveryPolicy::currentPlatform(), CrashRecoveryPolicy::Platform::OTHER);
#endif
}

void CrashRecoveryPolicyTests::iosCrashMarkerDoesNotShowDialog() {
    const auto decision = CrashRecoveryPolicy::evaluateStartup(CrashRecoveryPolicy::Platform::IOS, true);

    QVERIFY(decision.previousSessionCrashed);
    QVERIFY(!decision.shouldEvaluateSettingsReset());
}

void CrashRecoveryPolicyTests::iosCrashMarkerCannotResetSettings() {
    const auto decision = CrashRecoveryPolicy::evaluateStartup(CrashRecoveryPolicy::Platform::IOS, true);

    QVERIFY(!decision.settingsResetAllowed());
}

void CrashRecoveryPolicyTests::iosWithoutCrashMarkerStartsNormally() {
    const auto decision = CrashRecoveryPolicy::evaluateStartup(CrashRecoveryPolicy::Platform::IOS, false);

    QVERIFY(!decision.previousSessionCrashed);
    QVERIFY(!decision.shouldEvaluateSettingsReset());
    QVERIFY(!decision.settingsResetAllowed());
}

void CrashRecoveryPolicyTests::nonIosCrashMarkerKeepsExistingRecovery() {
    const auto decision = CrashRecoveryPolicy::evaluateStartup(CrashRecoveryPolicy::Platform::OTHER, true);

    QVERIFY(decision.previousSessionCrashed);
    QVERIFY(decision.shouldEvaluateSettingsReset());
    QVERIFY(decision.settingsResetAllowed());
}

QTEST_APPLESS_MAIN(CrashRecoveryPolicyTests)

#include "CrashRecoveryPolicyTests.moc"
