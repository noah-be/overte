#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly build_dir="${OVERTE_JVM_COVERAGE_BUILD_DIR:-$android_root/build/jvm-coverage}"
readonly classes_dir="$build_dir/classes"
readonly tests_dir="$build_dir/tests"
readonly report_dir="${OVERTE_JVM_COVERAGE_REPORT_DIR:-$android_root/build/reports/coverage/jvm-standalone}"
readonly tools_dir="${OVERTE_JVM_COVERAGE_TOOLS_DIR:-$android_root/build/tools/jacoco-0.8.13}"
readonly agent_jar="$tools_dir/jacocoagent.jar"
readonly cli_jar="$tools_dir/jacococli.jar"
readonly execution_data="$build_dir/jacoco.exec"
readonly java_tmp_dir="$build_dir/tmp"
readonly jacoco_base_url="https://repo.maven.apache.org/maven2/org/jacoco"
readonly javac_command="${OVERTE_JAVAC_COMMAND:-javac}"
readonly java_command="${OVERTE_JAVA_COMMAND:-java}"
readonly curl_command="${OVERTE_CURL_COMMAND:-curl}"
readonly sha256sum_command="${OVERTE_SHA256SUM_COMMAND:-sha256sum}"
readonly verify_command="${OVERTE_JVM_COVERAGE_VERIFY_COMMAND:-}"
readonly mktemp_command="${OVERTE_JVM_COVERAGE_MKTEMP_COMMAND:-mktemp}"

download_verified() {
    local url="$1"
    local destination="$2"
    local expected_sha256="$3"
    if [[ -f "$destination" ]] &&
            printf '%s  %s\n' "$expected_sha256" "$destination" \
                | "$sha256sum_command" --check --status; then
        return
    fi
    local temporary="${destination}.download.$$"
    trap 'rm -f -- "$temporary"' RETURN
    "$curl_command" --fail --silent --show-error --location \
        --retry 4 --retry-all-errors --connect-timeout 20 --max-time 300 \
        "$url" --output "$temporary"
    printf '%s  %s\n' "$expected_sha256" "$temporary" \
        | "$sha256sum_command" --check --status
    mv -f -- "$temporary" "$destination"
    trap - RETURN
}

lock_timeout="${OVERTE_JVM_COVERAGE_LOCK_TIMEOUT_SECONDS:-600}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf 'FAIL: invalid standalone JVM coverage lock timeout: %s\n' "$lock_timeout" >&2
    exit 2
fi
readonly lock_file="${OVERTE_JVM_COVERAGE_LOCK_FILE:-${build_dir}.lock}"
mkdir -p -- "$(dirname -- "$lock_file")" "$report_dir" "$tools_dir"
exec {coverage_lock_fd}>>"$lock_file"
if ! flock -x -w "$lock_timeout" "$coverage_lock_fd"; then
    printf 'FAIL: timed out waiting for standalone JVM coverage lock: %s\n' \
        "$lock_file" >&2
    exit 1
fi
staging_dir=''
cleanup() {
    [[ -z "$staging_dir" ]] || rm -rf -- "$staging_dir"
    flock -u "$coverage_lock_fd" 2>/dev/null || true
    exec {coverage_lock_fd}>&-
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rm -f -- "$report_dir/report.xml"
rm -rf -- "$report_dir/html"
staging_dir="$("$mktemp_command" -d "$report_dir/.jvm-coverage.XXXXXXXX")"
mkdir -p "$classes_dir" "$tests_dir" "$java_tmp_dir"
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

"$javac_command" -d "$classes_dir" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhoneLaunchState.java" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhonePermissionFlow.java" \
    "$android_root/apps/phoneInterface/src/main/java/org/overte/phone/PhonePendingUrlPolicy.java" \
    "$android_root/apps/interface/src/main/java/io/highfidelity/hifiinterface/HifiUtils.java" \
    "$android_root/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInputPolicy.java" \
    "$android_root/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivityPolicy.java" \
    "$android_root/apps/picoInterface/src/main/java/org/overte/pico/PicoActivityInstancePolicy.java" \
    "$android_root/libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java" \
    "$android_root/libraries/qt/src/main/java/io/highfidelity/utils/AssetCacheExtractor.java"

"$javac_command" -cp "$classes_dir" -d "$tests_dir" \
    "$android_root/tests/java/org/overte/phone/PhoneDeepLinkNormalizerTest.java" \
    "$android_root/tests/java/org/overte/phone/PhoneLaunchStateStandaloneTest.java" \
    "$android_root/tests/java/org/overte/phone/PhonePermissionFlowStandaloneTest.java" \
    "$android_root/tests/java/org/overte/phone/PhonePendingUrlPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/hifiinterface/HifiUtilsStandaloneTest.java" \
    "$android_root/tests/java/org/overte/pico/AndroidAudioInputPolicyStandaloneTest.java" \
    "$android_root/tests/java/org/overte/pico/PicoInterfaceActivityPolicyStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/utils/SafeAssetPathStandaloneTest.java" \
    "$android_root/tests/java/io/highfidelity/utils/AssetCacheExtractorStandaloneTest.java"

for test_class in \
    org.overte.phone.PhoneDeepLinkNormalizerTest \
    org.overte.phone.PhoneLaunchStateStandaloneTest \
    org.overte.phone.PhonePermissionFlowStandaloneTest \
    org.overte.phone.PhonePendingUrlPolicyStandaloneTest \
    io.highfidelity.hifiinterface.HifiUtilsStandaloneTest \
    org.overte.pico.AndroidAudioInputPolicyStandaloneTest \
    org.overte.pico.PicoInterfaceActivityPolicyStandaloneTest \
    io.highfidelity.utils.SafeAssetPathStandaloneTest \
    io.highfidelity.utils.AssetCacheExtractorStandaloneTest; do
    "$java_command" -Djava.io.tmpdir="$java_tmp_dir" \
        -javaagent:"$agent_jar=destfile=$execution_data,append=true" \
        -cp "$classes_dir:$tests_dir" "$test_class"
done

"$java_command" -jar "$cli_jar" report "$execution_data" \
    --classfiles "$classes_dir" \
    --sourcefiles "$android_root/apps/phoneInterface/src/main/java" \
    --sourcefiles "$android_root/apps/interface/src/main/java" \
    --sourcefiles "$android_root/apps/picoInterface/src/main/java" \
    --sourcefiles "$android_root/libraries/qt/src/main/java" \
    --name "Overte dependency-free Phone and legacy Interface JVM coverage" \
    --xml "$staging_dir/report.xml" \
    --html "$staging_dir/html"

if [[ -n "$verify_command" ]]; then
    "$verify_command" "$staging_dir/report.xml"
else
    python3 "$android_root/tests/coverage/verify-jvm-coverage.py" \
        "$staging_dir/report.xml"
fi

mv -- "$staging_dir/html" "$report_dir/html"
mv -- "$staging_dir/report.xml" "$report_dir/report.xml"
