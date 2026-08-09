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
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyUserPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/LegacyCrashDumpPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/LegacyLatestRequestGate.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryRetrievalCoordinator.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/UserStoryDomainPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/LegacyLatestRequestGateStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/provider/UserStoryRetrievalCoordinatorStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAssetTextPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyAdapterPositionPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyDomainLocationPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyUserPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/LegacyCrashDumpPolicyStandaloneTest.java"
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.UserStoryDomainPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.LegacyLatestRequestGateStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.provider.UserStoryRetrievalCoordinatorStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAssetTextPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyAdapterPositionPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyDomainLocationPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyUserPolicyStandaloneTest
java -Djava.io.tmpdir="$output" -cp "$output" \
    io.highfidelity.hifiinterface.LegacyCrashDumpPolicyStandaloneTest

if grep -Eq 'Log\.[A-Za-z]+\([^;]*accessToken|accessToken[^;]*Log\.' \
        "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/fragment/FriendsFragment.java"; then
    printf 'FAIL: legacy Friends UI must not log its access token\n' >&2
    exit 1
fi

main_activity="$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/MainActivity.java"
grep -Fq 'if (LegacyUserPolicy.hasText(username))' "$main_activity" || {
    printf 'FAIL: legacy profile header must validate nullable usernames\n' >&2
    exit 1
}
if grep -Fq 'username.isEmpty()' "$main_activity"; then
    printf 'FAIL: legacy profile header directly dereferences a nullable username\n' >&2
    exit 1
fi

provider="$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/provider/UserStoryDomainProvider.java"
grep -Fq 'long requestTicket = requestGate.begin();' "$provider" || {
    printf 'FAIL: legacy Places requests do not establish a latest-request ticket\n' >&2
    exit 1
}
grep -Fq 'forceRefresh || requestInFlight' "$provider" || {
    printf 'FAIL: the latest Places request can be starved behind an older request\n' >&2
    exit 1
}
[[ "$(grep -Fc 'requestGate.isCurrent(requestTicket)' "$provider")" -ge 3 ]] || {
    printf 'FAIL: legacy Places completions are not gated before mutation\n' >&2
    exit 1
}
