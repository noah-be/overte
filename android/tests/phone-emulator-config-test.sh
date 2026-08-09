#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_dir="$(cd -- "$script_dir/.." && pwd)"
gradle="$android_dir/apps/phoneInterface/build.gradle"
profile="$android_dir/conan/profiles/phone-emulator-x86_64"
resources="$android_dir/apps/phoneInterface/src/emulator/res/values/qt_dependencies.xml"
instrumentation_test="$android_dir/apps/phoneInterface/src/androidTest/java/org/overte/phone/EmulatorPackagingTest.java"
cold_launch_test="$android_dir/apps/phoneInterface/src/androidTest/java/org/overte/phone/PhoneColdLaunchInstrumentedTest.java"
root_dir="$(cd -- "$android_dir/.." && pwd)"

require_text() {
    local file="$1" pattern="$2" description="$3"
    grep -Eq -- "$pattern" "$file" || {
        echo "FAIL: $description" >&2
        exit 1
    }
}

bash -n "$android_dir/phone-emulator-test.sh"
bash -n "$android_dir/prepare-phone-emulator-deps.sh"
require_text "$profile" '^arch=x86_64$' 'Conan emulator profile must target x86_64'
require_text "$gradle" "emulator \{" 'dedicated emulator build type is missing'
require_text "$gradle" 'enableAndroidTestCoverage false' \
    'emulator build must not inherit unsupported offline JaCoCo instrumentation'
require_text "$gradle" 'ndk \{ abiFilters phoneTargetAbi \}' \
    'selected phone ABI must control the native build graph'
require_text "$gradle" "testBuildType isPhoneEmulatorBuild \? 'emulator' : 'debug'" \
    'instrumentation must target the selected product build type'
require_text "$gradle" "PHONE_EMULATOR_BUILD" 'emulator dependency gate is missing'
require_text "$gradle" 'testInstrumentationRunner.*AndroidJUnitRunner' \
    'Android instrumentation runner is missing'
require_text "$instrumentation_test" 'lib/x86_64/libphoneInterface\.so' \
    'emulator instrumentation test must verify the native x86_64 package'
require_text "$cold_launch_test" 'ActivityLifecycleMonitorRegistry' \
    'emulator instrumentation must observe the real Activity lifecycle'
require_text "$cold_launch_test" 'PhoneInterfaceActivity did not survive the stability window' \
    'emulator instrumentation must detect an immediate native startup crash'
if grep -Eq 'espresso\.intent|Intents\.(init|intending)' "$cold_launch_test"; then
    echo 'FAIL: cold-launch instrumentation intercepts the real native Activity' >&2
    exit 1
fi
require_text "$resources" '_x86_64\.so' 'Qt emulator resource mapping is missing'
if grep -q 'arm64-v8a' "$resources"; then
    echo 'FAIL: emulator Qt resource mapping contains ARM64 libraries' >&2
    exit 1
fi
require_text "$android_dir/ANDROID_PHONE_BUILD.md" 'phone-emulator-test\.sh all' \
    'emulator workflow is not documented'
require_text "$root_dir/cmake/macros/TargetBreakpad.cmake" \
    'if \(ANDROID AND USE_BREAKPAD\)' \
    'Android targets must not link Breakpad when USE_BREAKPAD is disabled'
require_text "$root_dir/cmake/macros/TargetDraco.cmake" \
    'ANDROID AND NOT TARGET draco::draco' \
    'Android emulator builds must accept the Conan Draco target'
require_text "$root_dir/cmake/macros/SetupHifiLibrary.cmake" \
    'CMAKE_ANDROID_ARCH_ABI STREQUAL "x86_64"' \
    'Android x86_64 audio sources must receive SIMD compiler flags'

fixture="$(mktemp -d "${TMPDIR:-/tmp}/phone-emulator-harness.XXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT
fixture_android="$fixture/android"
fixture_home="$fixture/home"
fixture_sdk="$fixture/sdk"
mkdir -p "$fixture_android" "$fixture_home/.android/avd/overte_api35.avd" \
    "$fixture_sdk/platform-tools" "$fixture_sdk/emulator" "$fixture/jdk/bin"
cp "$android_dir/phone-emulator-test.sh" "$fixture_android/phone-emulator-test.sh"
printf 'abi.type=x86_64\n' >"$fixture_home/.android/avd/overte_api35.avd/config.ini"

cat >"$fixture/jdk/bin/java" <<'EOF'
#!/usr/bin/env bash
echo 'openjdk version "21.0.1"' >&2
EOF
cat >"$fixture_sdk/emulator/emulator" <<'EOF'
#!/usr/bin/env bash
case "$1" in
    -list-avds) echo overte_api35 ;;
    -accel-check) echo 'acceleration is installed and usable' ;;
    *) exit 1 ;;
esac
EOF
cat >"$fixture_sdk/platform-tools/adb" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == devices ]]; then
    printf 'List of devices attached\nemulator-5554 device product:test\n'
elif [[ "$*" == *'emu avd name'* ]]; then
    echo overte_api35
elif [[ "$*" == *'logcat -b crash'* ]]; then
    echo 'native crash diagnostic'
elif [[ "$*" == *'logcat -d'* ]]; then
    echo 'logcat diagnostic'
elif [[ "$*" == *'dumpsys activity activities'* ]]; then
    echo 'instrumentation activity diagnostic'
elif [[ "$*" == *'dumpsys dropbox'* ]]; then
    echo 'native crash dropbox diagnostic'
elif [[ "$*" == *'/data/tombstones'* ]]; then
    echo 'tombstone diagnostic'
fi
EOF
cat >"$fixture_android/gradlew" <<'EOF'
#!/usr/bin/env bash
count=0
[[ ! -f "$FAKE_GRADLE_COUNT" ]] || count="$(<"$FAKE_GRADLE_COUNT")"
count=$((count + 1))
printf '%s\n' "$count" >"$FAKE_GRADLE_COUNT"
printf '%s\n' "$*" >>"$FAKE_GRADLE_ARGUMENTS"
echo "instrumentation output attempt $count"
[[ "${FAKE_GRADLE_FAIL_ATTEMPT:-}" != "$count" ]]
EOF
chmod +x "$fixture/jdk/bin/java" "$fixture_sdk/emulator/emulator" \
    "$fixture_sdk/platform-tools/adb" "$fixture_android/gradlew" \
    "$fixture_android/phone-emulator-test.sh"

common_environment=(
    HOME="$fixture_home"
    ANDROID_SDK_ROOT="$fixture_sdk"
    JAVA_HOME="$fixture/jdk"
    FAKE_GRADLE_COUNT="$fixture/gradle-count"
    FAKE_GRADLE_ARGUMENTS="$fixture/gradle-arguments"
)
test_class='org.overte.phone.PhoneColdLaunchInstrumentedTest#coldLaunchSurvives'
env "${common_environment[@]}" PHONE_EMULATOR_TEST_CLASS="$test_class" \
    PHONE_EMULATOR_TEST_REPETITIONS=3 "$fixture_android/phone-emulator-test.sh" test \
    >"$fixture/repeat.out"
[[ "$(<"$fixture/gradle-count")" == 3 ]] || {
    echo 'FAIL: emulator instrumentation class was not repeated exactly three times' >&2
    exit 1
}
[[ "$(grep -Fc -- "-Pandroid.testInstrumentationRunnerArguments.class=$test_class" \
    "$fixture/gradle-arguments")" == 3 ]] || {
    echo 'FAIL: repeated emulator instrumentation did not retain its class filter' >&2
    exit 1
}
grep -Fq -- '--rerun-tasks' "$fixture/gradle-arguments"

rm -f "$fixture/gradle-count" "$fixture/gradle-arguments"
set +e
env "${common_environment[@]}" FAKE_GRADLE_FAIL_ATTEMPT=2 \
    PHONE_EMULATOR_TEST_CLASS="$test_class" PHONE_EMULATOR_TEST_REPETITIONS=3 \
    "$fixture_android/phone-emulator-test.sh" test >"$fixture/failure.out" 2>&1
failure_status=$?
set -e
[[ "$failure_status" == 1 && "$(<"$fixture/gradle-count")" == 2 ]] || {
    echo 'FAIL: repeated emulator instrumentation did not stop at the first failure' >&2
    exit 1
}
diagnostic_dir="$(find "$fixture_android/build/phone-emulator/diagnostics" \
    -type d -name 'attempt-2' -print -quit)"
[[ -n "$diagnostic_dir" ]] || { echo 'FAIL: emulator failure diagnostics are missing' >&2; exit 1; }
grep -Fq 'instrumentation output attempt 2' "$diagnostic_dir/instrumentation.log"
grep -Fq 'logcat diagnostic' "$diagnostic_dir/logcat.txt"
grep -Fq 'native crash diagnostic' "$diagnostic_dir/native-crash-logcat.txt"
grep -Fq 'native crash dropbox diagnostic' "$diagnostic_dir/native-crash-dropbox.txt"
grep -Fq 'tombstone diagnostic' "$diagnostic_dir/tombstones.txt"

if PHONE_EMULATOR_TEST_REPETITIONS=26 "$fixture_android/phone-emulator-test.sh" test \
        >"$fixture/invalid-repeat.out" 2>&1; then
    echo 'FAIL: unbounded emulator instrumentation repetition was accepted' >&2
    exit 1
fi
grep -Fq 'must be an integer from 1 through 25' "$fixture/invalid-repeat.out"
if PHONE_EMULATOR_TEST_REPETITIONS=2 "$fixture_android/phone-emulator-test.sh" test \
        >"$fixture/missing-class.out" 2>&1; then
    echo 'FAIL: repeated full instrumentation suite was accepted' >&2
    exit 1
fi
grep -Fq 'PHONE_EMULATOR_TEST_CLASS is required' "$fixture/missing-class.out"

echo 'Phone x86_64 emulator configuration checks passed.'
