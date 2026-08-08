#!/usr/bin/env bash
set -Eeuo pipefail

readonly PACKAGE="org.overte.phone"
readonly LAUNCHER="org.overte.phone/.PermissionsActivity"
readonly QT_ACTIVITY="org.overte.phone/.PhoneInterfaceActivity"
readonly DEFAULT_APK="apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk"
readonly -a EXPECTED_PERMISSIONS=(
    android.permission.ACCESS_NETWORK_STATE
    android.permission.INTERNET
    android.permission.MODIFY_AUDIO_SETTINGS
    android.permission.RECORD_AUDIO
    android.permission.VIBRATE
)

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
  PHONE_APK_ANALYZER   apkanalyzer executable (otherwise SDK-resolved).
  PHONE_APK_PREFLIGHT  Package gate executable (otherwise repository gate).
  PHONE_EXPECT_DEBUGGABLE  Optional expected APK state: 0 or 1.
  PHONE_TEST_REPORT    Existing report directory (otherwise mktemp -d).
EOF
}

[[ "${1:-}" != "--help" && "${1:-}" != "-h" ]] || { usage; exit 0; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${PHONE_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$SCRIPT_DIR/../phone-device-lock.sh" run -- "$0" "$@"
fi

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

find_apk_analyzer() {
    local candidate sdk_root
    sdk_root="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    for candidate in \
        "${PHONE_APK_ANALYZER:-}" \
        "$sdk_root/cmdline-tools/latest/bin/apkanalyzer"; do
        [[ -n "$candidate" && -x "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    command -v apkanalyzer 2>/dev/null || die "apkanalyzer was not found"
}

ADB="$(find_adb)"
APK_ANALYZER="$(find_apk_analyzer)"
APK_PREFLIGHT="${PHONE_APK_PREFLIGHT:-$SCRIPT_DIR/check-phone-apk-16k.sh}"
[[ -x "$APK_PREFLIGHT" ]] || die "Phone APK package preflight was not found"

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

is_supported_phone_device() {
    local serial="$1" qemu characteristics abis features sdk gles
    qemu="$(device_property "$serial" ro.kernel.qemu)"
    characteristics="$(device_property "$serial" ro.build.characteristics)"
    abis="$(device_property "$serial" ro.product.cpu.abilist)"
    sdk="$(device_property "$serial" ro.build.version.sdk)"
    gles="$(device_property "$serial" ro.opengles.version)"
    features="$("$ADB" -s "$serial" shell pm list features 2>/dev/null | tr -d '\r')"
    [[ "$qemu" != 1 ]] &&
        [[ ! "${characteristics,,}" =~ (^|,)(watch|tv|automotive|vr)(,|$) ]] &&
        [[ ",$abis," == *,arm64-v8a,* ]] &&
        [[ "$sdk" =~ ^[0-9]+$ ]] && ((10#$sdk >= 26)) &&
        [[ "$gles" =~ ^[0-9]+$ ]] && ((10#$gles >= 196610)) &&
        grep -Fxq 'feature:android.hardware.touchscreen' <<<"$features"
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
                is_supported_phone_device "$serial" || \
                    die "ANDROID_SERIAL does not meet the physical Phone runtime contract"
                printf '%s\n' "$serial"
                return
            fi
        done
        die "ANDROID_SERIAL does not identify an authorized connected device"
    fi

    for serial in "${authorized[@]}"; do
        if ! is_pico_device "$serial" && is_supported_phone_device "$serial"; then
            phones+=("$serial")
        fi
    done
    ((${#phones[@]} == 1)) || \
        die "set ANDROID_SERIAL explicitly; found ${#phones[@]} supported physical ARM64 touchscreen phones"
    printf '%s\n' "${phones[0]}"
}

APK="${1:-$DEFAULT_APK}"
[[ -f "$APK" ]] || die "APK not found: $APK"
APK="$(realpath "$APK")"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum was not found"
APK_SHA256="$(sha256sum -- "$APK" | awk '{ print $1 }')"
[[ "$APK_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "could not identify the APK by SHA-256"
APK_APPLICATION_ID="$("$APK_ANALYZER" manifest application-id "$APK" 2>/dev/null \
    | tr -d '\r')" || die "could not read the APK application ID"
[[ "$APK_APPLICATION_ID" == "$PACKAGE" ]] || \
    die "APK application ID does not match the Phone package"
APK_MIN_SDK="$("$APK_ANALYZER" manifest min-sdk "$APK" 2>/dev/null | tr -d '\r')" || \
    die "could not read the APK minimum SDK"
APK_TARGET_SDK="$("$APK_ANALYZER" manifest target-sdk "$APK" 2>/dev/null | tr -d '\r')" || \
    die "could not read the APK target SDK"
[[ "$APK_MIN_SDK" == 26 && "$APK_TARGET_SDK" == 36 ]] || \
    die "APK SDK metadata does not match the Phone build contract"
APK_PERMISSIONS="$("$APK_ANALYZER" manifest permissions "$APK" 2>/dev/null \
    | sed '/^[[:space:]]*$/d' | LC_ALL=C sort -u)" || \
    die "could not read APK permissions"
EXPECTED_APK_PERMISSIONS="$(printf '%s\n' "${EXPECTED_PERMISSIONS[@]}" | LC_ALL=C sort)"
[[ "$APK_PERMISSIONS" == "$EXPECTED_APK_PERMISSIONS" ]] || \
    die "APK permissions do not match the minimal Phone allowlist"
APK_DEBUGGABLE_TEXT="$("$APK_ANALYZER" manifest debuggable "$APK" 2>/dev/null \
    | tr -d '\r')" || die "could not read APK debuggable state"
case "$APK_DEBUGGABLE_TEXT" in
    true) APK_DEBUGGABLE=1 ;;
    false) APK_DEBUGGABLE=0 ;;
    *) die "APK debuggable state is invalid" ;;
esac
if [[ -n "${PHONE_EXPECT_DEBUGGABLE:-}" ]]; then
    [[ "$PHONE_EXPECT_DEBUGGABLE" =~ ^[01]$ ]] || \
        die "PHONE_EXPECT_DEBUGGABLE must be 0 or 1"
    [[ "$APK_DEBUGGABLE" == "$PHONE_EXPECT_DEBUGGABLE" ]] || \
        die "APK debuggable state does not match the requested test mode"
fi
"$APK_PREFLIGHT" "$APK" >/dev/null 2>&1 || \
    die "APK failed the Phone content, ELF, alignment, or padding preflight"

# Do not query a connected device until every host-only artifact contract has
# passed. Invalid input must be side-effect free even at the ADB read level.
SERIAL="$(select_serial)"

if [[ -n "${PHONE_TEST_REPORT:-}" ]]; then
    REPORT_DIR="$(realpath "$PHONE_TEST_REPORT")"
    REPORT_KIND="caller-provided"
    [[ -d "$REPORT_DIR" ]] || die "PHONE_TEST_REPORT must name an existing directory"
else
    REPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-device-test.XXXXXX")"
    REPORT_KIND="temporary"
fi

REPOSITORY_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$REPOSITORY_ROOT" && ( "$REPORT_DIR" == "$REPOSITORY_ROOT" || "$REPORT_DIR" == "$REPOSITORY_ROOT/"* ) ]]; then
    die "refusing to store device diagnostics inside the Git worktree"
fi

readonly SUMMARY="$REPORT_DIR/summary.txt"
readonly TEST_DEEP_LINK="overte://localhost"
[[ -w "$REPORT_DIR" && -x "$REPORT_DIR" ]] || \
    die "PHONE_TEST_REPORT must be writable and searchable"
[[ ! -e "$SUMMARY" && ! -L "$SUMMARY" ]] || \
    die "refusing to overwrite an existing device-test summary"
(set -o noclobber; umask 077; : >"$SUMMARY") || \
    die "could not create a fresh device-test summary"
chmod 600 "$SUMMARY"
printf 'package=%s\napk_sha256=%s\napk_debuggable=%s\nruntime_permissions_auto_granted=1\n' \
    "$PACKAGE" "$APK_SHA256" "$APK_DEBUGGABLE" | tee -a "$SUMMARY"

current_pid() {
    adb_for shell pidof -s "$PACKAGE" 2>/dev/null | tr -d '\r' || true
}

crash_exit_count() {
    adb_for shell dumpsys activity exit-info "$PACKAGE" | awk '
        {
            line = tolower($0)
            if (line ~ /process exit info/) valid = 1
            if (line ~ /reason=[[:space:]]*(4|5)[[:space:]]*\(/ ||
                line ~ /reason=[[:space:]]*(crash|native_crash)/ ||
                line ~ /reason_(crash|crash_native)/) crashes++
        }
        END {
            if (!valid) exit 2
            print crashes + 0
        }
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
        [[ -n "$observed" ]] || die "$phase: app process exited; inspect the private $REPORT_KIND report"
        [[ "$observed" == "$expected" ]] || die "$phase: app process restarted; inspect the private $REPORT_KIND report"
    done
}

phone_activity_is_resumed() {
    adb_for shell dumpsys activity activities 2>/dev/null | \
        grep -Eq '(mResumedActivity|topResumedActivity).*org\.overte\.phone/(\.PhoneInterfaceActivity|org\.overte\.phone\.PhoneInterfaceActivity)'
}

phone_activity_is_backgrounded() {
    local activity_state
    activity_state="$(adb_for shell dumpsys activity activities 2>/dev/null)" || return 1
    grep -Eq '(mResumedActivity|topResumedActivity)' <<<"$activity_state" &&
        ! grep -Eq '(mResumedActivity|topResumedActivity).*org\.overte\.phone/' <<<"$activity_state"
}

printf '\nInstalling APK on the selected phone...\n'
# Keep the smoke test entirely unattended. Permission denial/revocation is a
# separate lifecycle matrix; this main launch path grants declared runtime
# permissions at install time so it cannot wait on Android permission UI.
adb_for install -r -g "$APK" >/dev/null

# Verify the installed package itself, not merely the input passed to adb. Keep
# its private on-device path out of output and reports.
mapfile -t installed_base_apks < <(
    adb_for shell pm path "$PACKAGE" 2>/dev/null \
        | tr -d '\r' \
        | sed -n 's/^package:\(\/.*\/base[.]apk\)$/\1/p'
)
((${#installed_base_apks[@]} == 1)) || \
    die "installed package did not expose exactly one base APK"
installed_base_apk="${installed_base_apks[0]}"
[[ "$installed_base_apk" =~ ^/[A-Za-z0-9_./+=~-]+/base[.]apk$ ]] || \
    die "installed package returned an unsafe base APK path"
installed_apk_sha256="$(adb_for exec-out cat "$installed_base_apk" | sha256sum | awk '{ print $1 }')"
[[ "$installed_apk_sha256" == "$APK_SHA256" ]] || \
    die "installed APK content does not match the requested APK"
printf 'installed_apk_verified=1\n' | tee -a "$SUMMARY"

printf '\nLaunching %s...\n' "$LAUNCHER"
logcat_start_epoch="$(adb_for shell date +%s.%3N 2>/dev/null | tr -d '\r')"
[[ "$logcat_start_epoch" =~ ^[0-9]+[.][0-9]{3}$ ]] || \
    die "device does not provide a precise logcat test cursor"
adb_for shell am force-stop "$PACKAGE"
baseline_exit_crash_count="$(crash_exit_count)"
adb_for shell am start -W -n "$LAUNCHER" >/dev/null
pid="$(wait_for_pid || true)"
[[ -n "$pid" ]] || die "app process did not start; inspect the private $REPORT_KIND report"
require_stable_pid "launch" "$pid" 30
phone_activity_is_resumed || die "phone Qt activity is not resumed after launch; inspect the private $REPORT_KIND report"
printf 'launch_survived=1\n' | tee -a "$SUMMARY"

printf '\nOpening neutral local test deep link...\n'
adb_for shell am start -W -a android.intent.action.VIEW \
    -d "$TEST_DEEP_LINK" "$PACKAGE" >/dev/null
require_stable_pid "deep link" "$pid" 5
phone_activity_is_resumed || die "phone Qt activity is not resumed after deep link; inspect the private $REPORT_KIND report"

printf '\nTesting repeated background/foreground transitions...\n'
for lifecycle_cycle in 1 2 3; do
    adb_for shell input keyevent KEYCODE_HOME
    require_stable_pid "background cycle $lifecycle_cycle" "$pid" 2
    phone_activity_is_backgrounded || \
        die "cycle $lifecycle_cycle: phone activity remained resumed in background; inspect the private $REPORT_KIND report"
    adb_for shell am start -W -n "$LAUNCHER" >/dev/null
    require_stable_pid "foreground cycle $lifecycle_cycle" "$pid" 3
    phone_activity_is_resumed || \
        die "cycle $lifecycle_cycle: phone Qt activity is not resumed; inspect the private $REPORT_KIND report"
done
printf 'background_foreground_cycles=3\n' | tee -a "$SUMMARY"

printf '\nTesting unconsumed Back lifecycle...\n'
adb_for shell input keyevent KEYCODE_BACK
require_stable_pid "Back background" "$pid" 3
phone_activity_is_backgrounded || \
    die "Back did not background the phone activity; inspect the private $REPORT_KIND report"
adb_for shell am start -W -n "$LAUNCHER" >/dev/null
require_stable_pid "Back recovery" "$pid" 5
phone_activity_is_resumed || \
    die "phone Qt activity is not resumed after Back recovery; inspect the private $REPORT_KIND report"
printf 'back_background_survived=1\nback_recovery_survived=1\n' | tee -a "$SUMMARY"

# Inspect raw process logs only in memory. Persisting them could retain visited
# locations, account identifiers, chat, or other user content.
log_marker_counts="$(
    adb_for logcat -d -T "$logcat_start_epoch" -v threadtime --pid="$pid" | awk '
        BEGIN { crashes = 0; pages = 0 }
        {
            line = tolower($0)
            if (line ~ /fatal exception|fatal signal|debug.*backtrace|am_crash|crash_dump/) crashes++
            explicit_mismatch = line ~ /pagesizemismatch|page size mismatch|load segment.*(not|mis).*align/
            has_16k_size = line ~ /16[ -]?k(b|ib)/
            has_failure_context = line ~ /error|fail|incompat|invalid|mismatch|misalign|not .*align|unsupported/
            if (explicit_mismatch || (has_16k_size && has_failure_context)) pages++
        }
        END { print crashes, pages }
    '
)" || die "could not read process-scoped log diagnostics"
[[ "$log_marker_counts" =~ ^[0-9]+[[:space:]][0-9]+$ ]] || \
    die "process-scoped log diagnostics returned invalid counters"
read -r crash_count page_mismatch_count <<<"$log_marker_counts"
final_exit_crash_count="$(crash_exit_count)"
exit_crash_count=$((final_exit_crash_count - baseline_exit_crash_count))
((exit_crash_count >= 0)) || \
    die "package exit diagnostics moved backwards during the test"
printf 'crash_log_matches=%s\nexit_crash_matches=%s\npage_size_mismatch_matches=%s\n' \
    "$crash_count" "$exit_crash_count" "$page_mismatch_count" | tee -a "$SUMMARY"

printf '\nDevice diagnostics complete (%s private report).\n' "$REPORT_KIND"
if ((crash_count > 0 || exit_crash_count > 0 || page_mismatch_count > 0)); then
    printf 'Crash or page-size compatibility markers were detected.\n'
    exit 2
fi
