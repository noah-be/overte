#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
mkdir -p "$android_root/build"
readonly build_dir="$(mktemp -d "$android_root/build/.pico-audio-input-policy-test.XXXXXX")"
cleanup() {
    [[ "$(basename -- "$build_dir")" == .pico-audio-input-policy-test.* ]] &&
        rm -rf -- "$build_dir"
}
trap cleanup EXIT

javac -d "$build_dir" \
    "$android_root/vr/pico/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInputPolicy.java" \
    "$android_root/common/tests/java/org/overte/pico/AndroidAudioInputPolicyStandaloneTest.java"
java -cp "$build_dir" org.overte.pico.AndroidAudioInputPolicyStandaloneTest
