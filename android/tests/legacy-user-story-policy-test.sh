#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output="$(mktemp -d "${TMPDIR:-/tmp}/overte-user-story-policy.XXXXXXXX")"
trap 'rm -rf -- "$output"' EXIT

javac -d "$output" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/HifiUtils.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicy.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicyStandaloneTest.java"
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.UserStoryDomainPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAssetTextPolicyStandaloneTest
