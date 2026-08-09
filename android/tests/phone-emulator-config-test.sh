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

echo 'Phone x86_64 emulator configuration checks passed.'
