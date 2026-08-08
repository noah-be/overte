#!/usr/bin/env bash
set -Eeuo pipefail

readonly PACKAGE="org.overte.phone"
readonly LAUNCHER="org.overte.phone/.PermissionsActivity"
readonly QT_ACTIVITY="org.overte.phone/.PhoneInterfaceActivity"
readonly DEFAULT_APK="apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: ANDROID_SERIAL=<serial> ./tests/phone-device-test.sh [APK]

Installs and exercises the Overte phone APK and writes diagnostics to a
temporary directory. Without ANDROID_SERIAL, the test proceeds only when
exactly one authorized, non-Pico phone can be identified.

Environment:
  ANDROID_SERIAL       Exact ADB serial to use (recommended).
  PHONE_ADB            ADB executable (otherwise resolved automatically).
  PHONE_TEST_REPORT    Existing report directory (otherwise mktemp -d).
EOF
}

[[ "${1:-}" != "--help" && "${1:-}" != "-h" ]] || { usage; exit 0; }

find_adb() {
    local candidate
    for candidate in \
        "${PHONE_ADB:-}" \
        "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
        "${ANDROID_HOME:-}/platform-tools/adb" \
        "${HOME}/Android/Sdk/platform-tools/adb"; do
        [[ -n "$candidate" && -x "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    command -v adb 2>/dev/null || die "ADB was not found"
}

ADB="$(find_adb)"

adb_for() { "$ADB" -s "$SERIAL" "$@"; }

device_property() {
    "$ADB" -s "$1" shell getprop "$2" 2>/dev/null | tr -d '\r'
}

is_pico_device() {
    local serial="$1" identity characteristics
    identity="$(device_property "$serial" ro.product.manufacturer) $(device_property "$serial" ro.product.brand) $(device_property "$serial" ro.product.model) $(device_property "$serial" ro.product.device)"
    characteristics="$(device_property "$serial" ro.build.characteristics)"
    [[ "${identity,,}" =~ pico|bytedance ]] || [[ "${characteristics,,}" =~ (^|,)vr(,|$) ]]
}

select_serial() {
    local requested="${ANDROID_SERIAL:-}" serial state
    local -a authorized=() phones=()
    while read -r serial state _; do
        [[ -n "$serial" && "$serial" != "List" ]] || continue
        [[ "$state" == "device" ]] && authorized+=("$serial")
    done < <("$ADB" devices -l)

    if [[ -n "$requested" ]]; then
        for serial in "${authorized[@]}"; do
            if [[ "$serial" == "$requested" ]]; then
                is_pico_device "$serial" && die "refusing to run the phone test on a Pico/VR device"
                printf '%s\n' "$serial"
                return
            fi
        done
        die "ANDROID_SERIAL does not identify an authorized connected device"
    fi

    for serial in "${authorized[@]}"; do
        is_pico_device "$serial" || phones+=("$serial")
    done
    ((${#phones[@]} == 1)) || die "set ANDROID_SERIAL explicitly; found ${#phones[@]} unambiguous non-Pico phones"
    printf '%s\n' "${phones[0]}"
}

SERIAL="$(select_serial)"
APK="${1:-$DEFAULT_APK}"
[[ -f "$APK" ]] || die "APK not found: $APK"
APK="$(realpath "$APK")"

if [[ -n "${PHONE_TEST_REPORT:-}" ]]; then
    REPORT_DIR="$(realpath "$PHONE_TEST_REPORT")"
    [[ -d "$REPORT_DIR" ]] || die "PHONE_TEST_REPORT must name an existing directory"
else
    REPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-device-test.XXXXXX")"
fi

REPOSITORY_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$REPOSITORY_ROOT" && ( "$REPORT_DIR" == "$REPOSITORY_ROOT" || "$REPORT_DIR" == "$REPOSITORY_ROOT/"* ) ]]; then
    die "refusing to store device diagnostics inside the Git worktree"
fi

readonly SUMMARY="$REPORT_DIR/summary.txt"
readonly TEST_DEEP_LINK="overte://localhost"
printf 'package=%s\n' "$PACKAGE" | tee "$SUMMARY"

current_pid() {
    adb_for shell pidof -s "$PACKAGE" 2>/dev/null | tr -d '\r' || true
}

crash_exit_count() {
    { adb_for shell dumpsys activity exit-info "$PACKAGE" || true; } | awk '
        {
            line = tolower($0)
            if (line ~ /reason=[[:space:]]*(4|5)[[:space:]]*\(/ ||
                line ~ /reason=[[:space:]]*(crash|native_crash)/ ||
                line ~ /reason_(crash|crash_native)/) crashes++
        }
        END { print crashes + 0 }
    '
}

wait_for_pid() {
    local attempt observed
    for attempt in $(seq 1 10); do
        observed="$(current_pid)"
        [[ -n "$observed" ]] && { printf '%s\n' "$observed"; return; }
        sleep 1
    done
    return 1
}

require_stable_pid() {
    local phase="$1" expected="$2" seconds="$3" elapsed observed
    for elapsed in $(seq 1 "$seconds"); do
        sleep 1
        observed="$(current_pid)"
        [[ -n "$observed" ]] || die "$phase: app process exited; reports: $REPORT_DIR"
        [[ "$observed" == "$expected" ]] || die "$phase: app process restarted; reports: $REPORT_DIR"
    done
}

phone_activity_is_resumed() {
    adb_for shell dumpsys activity activities 2>/dev/null | \
        grep -Eq '(mResumedActivity|topResumedActivity).*org\.overte\.phone/(\.PhoneInterfaceActivity|org\.overte\.phone\.PhoneInterfaceActivity)'
}

printf '\nInstalling APK on the selected phone...\n'
adb_for install -r "$APK" >/dev/null

printf '\nLaunching %s...\n' "$LAUNCHER"
adb_for shell am force-stop "$PACKAGE"
baseline_exit_crash_count="$(crash_exit_count)"
adb_for shell am start -W -n "$LAUNCHER" >/dev/null
pid="$(wait_for_pid || true)"
[[ -n "$pid" ]] || die "app process did not start; reports: $REPORT_DIR"
require_stable_pid "launch" "$pid" 30
phone_activity_is_resumed || die "phone Qt activity is not resumed after launch; reports: $REPORT_DIR"
printf 'launch_survived=1\n' | tee -a "$SUMMARY"

printf '\nOpening neutral local test deep link...\n'
adb_for shell am start -W -a android.intent.action.VIEW \
    -d "$TEST_DEEP_LINK" "$PACKAGE" >/dev/null
require_stable_pid "deep link" "$pid" 5
phone_activity_is_resumed || die "phone Qt activity is not resumed after deep link; reports: $REPORT_DIR"

printf '\nTesting background/foreground transition...\n'
adb_for shell input keyevent KEYCODE_HOME
require_stable_pid "background" "$pid" 3
adb_for shell am start -W -n "$LAUNCHER" >/dev/null
require_stable_pid "foreground" "$pid" 5
phone_activity_is_resumed || die "phone Qt activity is not resumed after foregrounding; reports: $REPORT_DIR"
printf 'background_survived=1\nforeground_survived=1\n' | tee -a "$SUMMARY"

# Inspect raw process logs only in memory. Persisting them could retain visited
# locations, account identifiers, chat, or other user content.
read -r crash_count page_mismatch_count < <(
    adb_for logcat -d -v threadtime --pid="$pid" | awk '
        BEGIN { crashes = 0; pages = 0 }
        {
            line = tolower($0)
            if (line ~ /fatal exception|fatal signal|debug.*backtrace|am_crash|crash_dump/) crashes++
            if (line ~ /pagesizemismatch|page size mismatch|16[ -]?k(b|ib)|load segment.*align/) pages++
        }
        END { print crashes, pages }
    '
)
final_exit_crash_count="$(crash_exit_count)"
exit_crash_count=$((final_exit_crash_count - baseline_exit_crash_count))
((exit_crash_count >= 0)) || exit_crash_count=0
printf 'crash_log_matches=%s\nexit_crash_matches=%s\npage_size_mismatch_matches=%s\n' \
    "$crash_count" "$exit_crash_count" "$page_mismatch_count" | tee -a "$SUMMARY"

printf '\nDevice diagnostics complete: %s\n' "$REPORT_DIR"
if ((crash_count > 0 || exit_crash_count > 0 || page_mismatch_count > 0)); then
    printf 'Crash or page-size compatibility markers were detected.\n'
    exit 2
fi
