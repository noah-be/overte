#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 && -f $1 ]] || { echo 'Usage: check-phone-apk-metadata.sh <apk>' >&2; exit 2; }
readonly apk=$1
readonly expected_permissions=$'android.permission.ACCESS_NETWORK_STATE\nandroid.permission.INTERNET\nandroid.permission.MODIFY_AUDIO_SETTINGS\nandroid.permission.RECORD_AUDIO\nandroid.permission.VIBRATE'

find_analyzer() {
    local candidate sdk_root="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    for candidate in "${PHONE_APK_ANALYZER:-}" "$sdk_root/cmdline-tools/latest/bin/apkanalyzer"; do
        [[ -n "$candidate" && -x "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    command -v apkanalyzer 2>/dev/null
}
analyzer="$(find_analyzer)" || { echo 'ERROR: apkanalyzer was not found' >&2; exit 2; }
manifest_value() { "$analyzer" manifest "$1" "$apk" 2>/dev/null | tr -d '\r'; }
metadata_error() { printf 'ERROR: could not read APK %s\n' "$1" >&2; exit 1; }

application_id="$(manifest_value application-id)" || metadata_error 'application ID'
min_sdk="$(manifest_value min-sdk)" || metadata_error 'minimum SDK'
target_sdk="$(manifest_value target-sdk)" || metadata_error 'target SDK'
version_code="$(manifest_value version-code)" || metadata_error 'version code'
version_name="$(manifest_value version-name)" || metadata_error 'version name'
permissions="$(manifest_value permissions | sed '/^[[:space:]]*$/d' | LC_ALL=C sort -u)" || \
    metadata_error 'permissions'
debuggable="$(manifest_value debuggable)" || metadata_error 'debuggable state'

[[ "$application_id" == org.overte.phone ]] || { echo 'ERROR: unexpected APK application ID' >&2; exit 1; }
[[ "$min_sdk" == 26 && "$target_sdk" == 36 ]] || { echo 'ERROR: unexpected APK SDK metadata' >&2; exit 1; }
[[ "$version_code" =~ ^[1-9][0-9]{0,9}$ ]] &&
    ((10#$version_code <= 2147483647)) || {
        echo 'ERROR: invalid APK version code' >&2
        exit 1
    }
[[ "$version_name" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,99}$ ]] || {
    echo 'ERROR: invalid APK version name' >&2
    exit 1
}
[[ "$permissions" == "$expected_permissions" ]] || { echo 'ERROR: unexpected APK permissions' >&2; exit 1; }
[[ "$debuggable" == true || "$debuggable" == false ]] || { echo 'ERROR: invalid APK debuggable state' >&2; exit 1; }
if [[ -n "${PHONE_EXPECT_DEBUGGABLE:-}" ]]; then
    [[ "$PHONE_EXPECT_DEBUGGABLE" =~ ^[01]$ ]] || {
        echo 'ERROR: PHONE_EXPECT_DEBUGGABLE must be 0 or 1' >&2
        exit 1
    }
    expected_debuggable=false
    [[ "$PHONE_EXPECT_DEBUGGABLE" == 1 ]] && expected_debuggable=true
    [[ "$debuggable" == "$expected_debuggable" ]] || {
        echo 'ERROR: APK debuggable state does not match the expected variant' >&2
        exit 1
    }
fi
echo 'Phone APK manifest metadata matches the minimal package contract.'
