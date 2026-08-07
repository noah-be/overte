#!/usr/bin/env bash
set -euo pipefail

ANDROID_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_OUTPUT="$(mktemp -d)"
trap 'rm -rf "${TEST_OUTPUT}"' EXIT

javac -d "${TEST_OUTPUT}" \
    "${ANDROID_ROOT}/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java" \
    "${ANDROID_ROOT}/tests/java/org/overte/phone/PhoneDeepLinkNormalizerTest.java"

java -cp "${TEST_OUTPUT}" org.overte.phone.PhoneDeepLinkNormalizerTest
