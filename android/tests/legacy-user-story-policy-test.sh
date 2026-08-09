#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly output="$(mktemp -d "${TMPDIR:-/tmp}/overte-user-story-policy.XXXXXXXX")"
trap 'rm -rf -- "$output"' EXIT

javac -d "$output" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/HifiUtils.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyAdapterPositionPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyDomainLocationPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicy.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAdapterPositionPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyDomainLocationPolicyStandaloneTest.java"
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.UserStoryDomainPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAssetTextPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAdapterPositionPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyDomainLocationPolicyStandaloneTest

if grep -Eq 'Log\.[A-Za-z]+\([^;]*accessToken|accessToken[^;]*Log\.' \
        "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/fragment/FriendsFragment.java"; then
    printf 'FAIL: legacy Friends UI must not log its access token\n' >&2
    exit 1
fi
