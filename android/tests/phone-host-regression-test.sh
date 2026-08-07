#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
repo_root="$(cd -- "$android_root/.." && pwd)"
failures=0
checks=0

pass() {
    checks=$((checks + 1))
    printf 'PASS %s\n' "$1"
}

fail() {
    checks=$((checks + 1))
    failures=$((failures + 1))
    printf 'FAIL %s\n' "$1" >&2
}

require_file() {
    local relative_path="$1"
    if [[ -f "$android_root/$relative_path" ]]; then
        pass "file: $relative_path"
    else
        fail "missing file: $relative_path"
    fi
}

require_text() {
    local relative_path="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "$android_root/$relative_path" ]] &&
            grep -Eq -- "$pattern" "$android_root/$relative_path"; then
        pass "$description"
    else
        fail "$description"
    fi
}

reject_text() {
    local relative_path="$1"
    local pattern="$2"
    local description="$3"
    if [[ -f "$android_root/$relative_path" ]] &&
            ! grep -Eiq -- "$pattern" "$android_root/$relative_path"; then
        pass "$description"
    else
        fail "$description"
    fi
}

manifest='apps/phoneInterface/src/main/AndroidManifest.xml'
gradle='apps/phoneInterface/build.gradle'
cmake='apps/phoneInterface/CMakeLists.txt'
permissions_activity='apps/phoneInterface/src/main/java/org/overte/phone/PermissionsActivity.java'
interface_activity='apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java'
url_handler='apps/phoneInterface/src/PhoneUrlHandler.cpp'
phone_defaults='../scripts/+android_phoneInterface/defaultScripts.js'

for source_file in \
        build-phone.sh \
        build-phone.gradle \
        settings-phone.gradle \
        "$gradle" \
        "$cmake" \
        "$manifest" \
        "$permissions_activity" \
        "$interface_activity" \
        "$url_handler" \
        "$phone_defaults"; do
    require_file "$source_file"
done

require_text settings-phone.gradle \
    "include[[:space:]]+['\"]:phoneInterface['\"]" \
    'settings include the independent phoneInterface module'
require_text settings-phone.gradle \
    "project\(['\"]:phoneInterface['\"]\)\.projectDir[[:space:]]*=[[:space:]]*file\(['\"]apps/phoneInterface['\"]\)" \
    'phoneInterface resolves to apps/phoneInterface'
require_text settings-phone.gradle \
    "rootProject\.name[[:space:]]*=[[:space:]]*['\"]overte-phone['\"]" \
    'phone build has an independent Gradle root name'

require_text "$gradle" "namespace[[:space:]]+['\"]org\.overte\.phone['\"]" \
    'Gradle namespace is org.overte.phone'
require_text "$gradle" "applicationId[[:space:]]+['\"]org\.overte\.phone['\"]" \
    'application ID is org.overte.phone'
require_text "$gradle" 'minSdk[[:space:]]+26([^0-9]|$)' \
    'minimum Android API is 26'
require_text "$gradle" 'targetSdk[[:space:]]+36([^0-9]|$)' \
    'target Android API is 36'
require_text "$gradle" "abiFilters[[:space:]]+['\"]arm64-v8a['\"]" \
    'APK is restricted to ARM64'
require_text "$gradle" "HIFI_ANDROID_APP=phoneInterface" \
    'native configure selects the phone application'
require_text "$gradle" "targets[[:space:]]+['\"]phoneInterface['\"]" \
    'Gradle builds the phone native target'
require_text "$gradle" 'ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON' \
    'native build opts into flexible Android page sizes'
require_text "$cmake" 'set\(TARGET_NAME[[:space:]]+phoneInterface\)' \
    'CMake declares the phone native target'
require_text "$cmake" 'add_subdirectory\("\$\{CMAKE_SOURCE_DIR\}/interface"' \
    'phone native target includes the main Interface client'
require_text "$cmake" 'src/PhoneUrlHandler\.cpp' \
    'CMake includes the runtime deep-link bridge'

require_text "$manifest" 'android\.hardware\.touchscreen' \
    'manifest requires a touchscreen'
require_text "$manifest" 'android:glEsVersion="0x00030002"' \
    'manifest declares the OpenGL ES requirement'
require_text "$manifest" 'android\.permission\.INTERNET' \
    'manifest allows network access'
require_text "$manifest" 'android\.permission\.RECORD_AUDIO' \
    'manifest declares microphone access'
require_text "$manifest" 'android:name="\.PermissionsActivity"' \
    'manifest declares the permission launcher activity'
require_text "$manifest" 'android\.intent\.action\.MAIN' \
    'manifest has a MAIN launcher action'
require_text "$manifest" 'android\.intent\.category\.LAUNCHER' \
    'manifest has a LAUNCHER category'
require_text "$manifest" 'android:scheme="overte"' \
    'manifest accepts overte deep links'
require_text "$manifest" 'android:scheme="hifi"' \
    'manifest accepts legacy hifi deep links'
require_text "$manifest" 'android:name="\.PhoneInterfaceActivity"' \
    'manifest declares the Qt client activity'
require_text "$manifest" 'android:screenOrientation="landscape"' \
    'manifest fixes the phone UI to landscape'
require_text "$manifest" 'android\.app\.lib_name"[[:space:]]+android:value="phoneInterface"' \
    'Qt loads the phoneInterface native library'
reject_text "$manifest" 'openxr|pico|headtracking|vr\.headtracking' \
    'phone manifest contains no Pico/OpenXR feature requirement'

require_text "$permissions_activity" \
    'requestPermissions\(' \
    'launcher requests runtime permission'
require_text "$permissions_activity" \
    'Manifest\.permission\.RECORD_AUDIO' \
    'launcher requests RECORD_AUDIO specifically'
require_text "$permissions_activity" \
    'new Intent\(this,[[:space:]]*PhoneInterfaceActivity\.class\)' \
    'launcher transfers control to the Qt activity'
reject_text "$permissions_activity" \
    'getStringExtra\([^)]*args' \
    'exported launcher rejects arbitrary external native arguments'
require_text "$interface_activity" \
    'extends[[:space:]]+QtActivity' \
    'phone activity hosts QtActivity'
require_text "$interface_activity" \
    'FLAG_KEEP_SCREEN_ON' \
    'phone activity keeps the display awake'
require_text "$interface_activity" \
    'nativeProcessUrl\(destination\.toString\(\)\)' \
    'warm deep links cross the Java/native bridge'
require_text "$url_handler" \
    'processURL\(url\)' \
    'native deep links use the existing URL validation path'

if grep -Eq -- 'extraSelectors[[:space:]]*<<[[:space:]]*"android_interface"' \
        "$repo_root/libraries/shared/src/shared/FileUtils.cpp"; then
    pass 'phone file selector falls back to the existing Android touch scripts'
else
    fail 'phone file selector falls back to the existing Android touch scripts'
fi
require_text "$phone_defaults" 'touchscreenvirtualpad\.js' \
    'phone defaults load the touchscreen virtual pad'
require_text "$phone_defaults" '/audio\.js' \
    'phone defaults load Android audio controls'
require_text "$phone_defaults" '/modes\.js' \
    'phone defaults load mobile view modes'
reject_text "$phone_defaults" 'actionbar|openAndroidActivity' \
    'phone defaults avoid the unavailable legacy Home activity'

require_text build-phone.sh \
    ':phoneInterface:assembleDebug' \
    'wrapper builds the phone debug variant'
require_text build-phone.sh \
    'phoneInterface-debug\.apk' \
    'wrapper installs the documented APK path'
for command_name in doctor prepare build install all deploy setup; do
    require_text build-phone.sh \
        "(^|[[:space:]])${command_name}\)" \
        "wrapper exposes the ${command_name} command"
done
reject_text build-phone.sh \
    'curl|wget|git[[:space:]]+(clone|fetch|pull)' \
    'normal phone wrapper contains no implicit network or Git command'

printf 'Checks: %s total, %s failed\n' "$checks" "$failures"
(( failures == 0 ))
