#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly build_dir="$android_root/build/jvm-coverage"
readonly classes_dir="$build_dir/classes"
readonly tests_dir="$build_dir/tests"
readonly report_dir="$android_root/build/reports/coverage/jvm-standalone"
readonly tools_dir="$android_root/build/tools/jacoco-0.8.13"
readonly agent_jar="$tools_dir/jacocoagent.jar"
readonly cli_jar="$tools_dir/jacococli.jar"
readonly execution_data="$build_dir/jacoco.exec"
readonly jacoco_base_url="https://repo.maven.apache.org/maven2/org/jacoco"

download_verified() {
    local url="$1"
    local destination="$2"
    local expected_sha256="$3"
    if [[ ! -f "$destination" ]]; then
        curl --fail --silent --show-error --location "$url" --output "$destination"
    fi
    printf '%s  %s\n' "$expected_sha256" "$destination" | sha256sum --check --status
}

mkdir -p "$classes_dir" "$tests_dir" "$report_dir" "$tools_dir"
find "$classes_dir" "$tests_dir" -type f -delete
find "$build_dir" -maxdepth 1 -type f -name 'jacoco.exec' -delete

download_verified \
    "$jacoco_base_url/org.jacoco.agent/0.8.13/org.jacoco.agent-0.8.13-runtime.jar" \
    "$agent_jar" \
    47e700ccb0fdb9e27c5241353f8161938f4e53c3561dd35e063c5fe88dc3349b
download_verified \
    "$jacoco_base_url/org.jacoco.cli/0.8.13/org.jacoco.cli-0.8.13-nodeps.jar" \
    "$cli_jar" \
    8f748683833d4dc4d72cea5d6b43f49344687b831e0582c97bcb9b984e3de0a3

javac -d "$classes_dir" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhoneLaunchState.java" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhonePermissionFlow.java" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhonePendingUrlPolicy.java" \
    "$android_root/libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java"

javac -cp "$classes_dir" -d "$tests_dir" \
    "$android_root/tests/java/org/overte/phone/PhoneDeepLinkNormalizerTest.java" \
    "$android_root/tests/java/org/overte/phone/PhoneLaunchStateStandaloneTest.java" \
    "$android_root/tests/java/org/overte/phone/PhonePermissionFlowStandaloneTest.java" \
    "$android_root/tests/java/org/overte/phone/PhonePendingUrlPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/utils/SafeAssetPathStandaloneTest.java"

for test_class in \
    org.overte.phone.PhoneDeepLinkNormalizerTest \
    org.overte.phone.PhoneLaunchStateStandaloneTest \
    org.overte.phone.PhonePermissionFlowStandaloneTest \
    org.overte.phone.PhonePendingUrlPolicyStandaloneTest \
    io.highfidelity.utils.SafeAssetPathStandaloneTest; do
    java -javaagent:"$agent_jar=destfile=$execution_data,append=true" \
        -cp "$classes_dir:$tests_dir" "$test_class"
done

java -jar "$cli_jar" report "$execution_data" \
    --classfiles "$classes_dir" \
    --sourcefiles "$android_root/apps/phoneInterface/src/main/java" \
    --sourcefiles "$android_root/libraries/qt/src/main/java" \
    --name "Overte dependency-free Phone JVM coverage" \
    --xml "$report_dir/report.xml" \
    --html "$report_dir/html"

exec python3 "$android_root/tests/coverage/verify-jvm-coverage.py" \
    "$report_dir/report.xml"
