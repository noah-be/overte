#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu
# Called inside a pinned, network-isolated container with a fresh /attempt.
cd /attempt/source
android/phone/fdroid/scripts/build-dependencies.sh --prepare
android/phone/fdroid/scripts/build-dependencies.sh --build
export OVERTE_FDROID_CONAN_DIR=/attempt/target
export GRADLE_USER_HOME=/attempt/gradle-home
android/common/gradlew --offline --no-daemon --no-build-cache \
    --settings-file /attempt/source/android/phone/settings.gradle \
    -p /attempt/source/android/phone \
    --init-script /attempt/source/android/phone/quality-gate/release.init.gradle \
    "-PVERSION_CODE=$GATE_VERSION_CODE" "-PRELEASE_NUMBER=$GATE_VERSION_NAME" \
    -PRELEASE_TYPE=RELEASE -PSTABLE_BUILD=1 \
    -Pandroid.aapt2FromMavenOverride=/opt/android-sdk/build-tools/36.0.0/aapt2 \
    :phoneInterface:assembleRelease :phoneInterface:bundleRelease \
    :phoneInterface:qualityGateDependencies
