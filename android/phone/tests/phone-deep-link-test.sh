#!/usr/bin/env bash
set -euo pipefail

ANDROID_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_OUTPUT="$(mktemp -d)"
trap 'rm -rf "${TEST_OUTPUT}"' EXIT

javac -d "${TEST_OUTPUT}" \
    "${ANDROID_ROOT}/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java" \
    "${ANDROID_ROOT}/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneLaunchState.java" \
    "${ANDROID_ROOT}/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhonePermissionFlow.java" \
    "${ANDROID_ROOT}/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhonePendingUrlPolicy.java" \
    "${ANDROID_ROOT}/phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneTouchUiMetricsPolicy.java" \
    "${ANDROID_ROOT}/common/tests/java/org/overte/phone/PhoneDeepLinkNormalizerTest.java" \
    "${ANDROID_ROOT}/common/tests/java/org/overte/phone/PhoneLaunchStateStandaloneTest.java" \
    "${ANDROID_ROOT}/common/tests/java/org/overte/phone/PhonePermissionFlowStandaloneTest.java" \
    "${ANDROID_ROOT}/common/tests/java/org/overte/phone/PhonePendingUrlPolicyStandaloneTest.java" \
    "${ANDROID_ROOT}/common/tests/java/org/overte/phone/PhoneTouchUiMetricsPolicyStandaloneTest.java"

java -cp "${TEST_OUTPUT}" org.overte.phone.PhoneDeepLinkNormalizerTest
java -cp "${TEST_OUTPUT}" org.overte.phone.PhoneLaunchStateStandaloneTest
java -cp "${TEST_OUTPUT}" org.overte.phone.PhonePermissionFlowStandaloneTest
java -cp "${TEST_OUTPUT}" org.overte.phone.PhonePendingUrlPolicyStandaloneTest
java -cp "${TEST_OUTPUT}" org.overte.phone.PhoneTouchUiMetricsPolicyStandaloneTest
