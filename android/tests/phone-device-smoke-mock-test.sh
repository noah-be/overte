#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly test_root="$(mktemp -d "${TMPDIR:-/tmp}/phone-device-smoke-mock.XXXXXX")"
readonly real_sha256sum="$(command -v sha256sum)"
readonly real_tee="$(command -v tee)"
readonly real_chmod="$(command -v chmod)"
readonly real_mktemp="$(command -v mktemp)"
export PHONE_MOCK_REAL_SHA256SUM="$real_sha256sum"
export PHONE_MOCK_REAL_TEE="$real_tee"
export PHONE_MOCK_REAL_CHMOD="$real_chmod"
export PHONE_MOCK_REAL_MKTEMP="$real_mktemp"
cleanup() {
    [[ "$(basename -- "$test_root")" == phone-device-smoke-mock.* ]] && rm -rf -- "$test_root"
}
trap cleanup EXIT

mkdir -p "$test_root/bin"
printf 'mock phone APK bytes\n' >"$test_root/phone.apk"
printf resumed >"$test_root/activity-state"
: >"$test_root/adb-commands"

cat >"$test_root/bin/adb" <<'MOCK_ADB'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >>"$MOCK_ROOT/adb-commands"
printf '\n' >>"$MOCK_ROOT/adb-commands"

if [[ "${1:-}" == devices ]]; then
    printf 'List of devices attached\nmock-phone device product:mock\n'
    exit 0
fi
[[ "${1:-}" == -s && "${2:-}" == mock-phone ]] || exit 3
shift 2

case "$*" in
    'shell getprop ro.product.manufacturer') printf 'Example\n' ;;
    'shell getprop ro.product.brand') printf 'Example\n' ;;
    'shell getprop ro.product.model') printf 'Phone\n' ;;
    'shell getprop ro.product.device') printf 'phone\n' ;;
    'shell getprop ro.build.characteristics') printf 'default\n' ;;
    'shell getprop ro.kernel.qemu') printf '%s\n' "${MOCK_QEMU:-0}" ;;
    'shell getprop ro.product.cpu.abilist') printf 'arm64-v8a,armeabi-v7a\n' ;;
    'shell getprop ro.build.version.sdk') printf '%s\n' "${MOCK_SDK:-36}" ;;
    'shell getprop ro.opengles.version') printf '196610\n' ;;
    'shell pm list features') printf 'feature:android.hardware.touchscreen\n' ;;
    install\ -r\ -g\ *)
        if [[ "${MOCK_INSTALL_FAILURE:-0}" == 1 ]]; then
            printf 'private adb detail: mock-phone %s\n' "$MOCK_ROOT/phone.apk" >&2
            exit 10
        fi
        ;;
    'shell pm path org.overte.phone')
        printf 'package:/data/app/~~mock/org.overte.phone-mock/base.apk\n'
        ;;
    'shell date +%s.%3N') printf '1786212000.123\n' ;;
    'exec-out cat /data/app/~~mock/org.overte.phone-mock/base.apk')
        if [[ "${MOCK_INSTALLED_READ_FAILURE:-0}" == 1 ]]; then
            printf 'private installed path read failure for mock-phone\n' >&2
            exit 12
        elif [[ "${MOCK_APK_MISMATCH:-0}" == 1 ]]; then
            printf 'different installed bytes\n'
        else
            cat "$MOCK_ROOT/phone.apk"
        fi
        ;;
    'shell am force-stop org.overte.phone')
        if [[ "${MOCK_FINAL_CLEANUP_FAILURE:-0}" == 1 ]]; then
            force_stop_count=0
            [[ ! -f "$MOCK_ROOT/force-stop-count" ]] || \
                force_stop_count="$(<"$MOCK_ROOT/force-stop-count")"
            force_stop_count=$((force_stop_count + 1))
            printf '%s' "$force_stop_count" >"$MOCK_ROOT/force-stop-count"
            ((force_stop_count < 2)) || exit 13
        fi
        ;;
    shell\ am\ start\ *)
        if [[ "${MOCK_START_FAILURE:-0}" == 1 ]]; then
            printf 'private start failure for mock-phone\n' >&2
            exit 11
        fi
        printf resumed >"$MOCK_ROOT/activity-state"
        ;;
    'shell pidof -s org.overte.phone')
        if [[ "${MOCK_PROCESS_RESTART:-0}" == 1 &&
                "$(<"$MOCK_ROOT/activity-state")" == background ]]; then
            printf '4343\n'
        else
            printf '4242\n'
        fi
        ;;
    'shell input keyevent KEYCODE_HOME'|'shell input keyevent KEYCODE_BACK')
        if [[ "${MOCK_STICKY_FOREGROUND:-0}" != 1 ]]; then
            printf background >"$MOCK_ROOT/activity-state"
        fi
        ;;
    'shell dumpsys activity activities')
        if [[ "$(<"$MOCK_ROOT/activity-state")" == resumed ]]; then
            printf 'mResumedActivity: org.overte.phone/.PhoneInterfaceActivity\n'
        else
            printf 'mResumedActivity: com.android.launcher/.Launcher\n'
        fi
        ;;
    'shell dumpsys activity exit-info org.overte.phone')
        [[ "${MOCK_EXIT_INFO_FAILURE:-0}" != 1 ]] || exit 8
        if [[ "${MOCK_FINAL_EXIT_INFO_FAILURE:-0}" == 1 ]]; then
            exit_info_count=0
            [[ ! -f "$MOCK_ROOT/exit-info-count" ]] || \
                exit_info_count="$(<"$MOCK_ROOT/exit-info-count")"
            exit_info_count=$((exit_info_count + 1))
            printf '%s' "$exit_info_count" >"$MOCK_ROOT/exit-info-count"
            ((exit_info_count < 2)) || exit 8
        fi
        printf 'ACTIVITY MANAGER PROCESS EXIT INFO\n'
        ;;
    logcat\ -d\ -T\ *\ -v\ threadtime\ --pid=4242)
        [[ "${MOCK_LOGCAT_FAILURE:-0}" != 1 ]] || exit 9
        case "${MOCK_LOGCAT_FIXTURE:-}" in
            benign-16k) printf 'Phone dependencies verified for 16 KiB page size\n' ;;
            bad-16k) printf 'linker error: library has incompatible 16 KB page alignment\n' ;;
        esac
        ;;
    *) printf 'unexpected mock adb command: %s\n' "$*" >&2; exit 4 ;;
esac
MOCK_ADB

cat >"$test_root/bin/sleep" <<'MOCK_SLEEP'
#!/usr/bin/env bash
exit 0
MOCK_SLEEP
cat >"$test_root/bin/sha256sum" <<'MOCK_SHA256'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_SHA256_FAILURE:-0}" == 1 ]]; then
    printf 'private hash failure: %s\n' "${2:-unknown}" >&2
    exit 7
fi
exec "$PHONE_MOCK_REAL_SHA256SUM" "$@"
MOCK_SHA256
cat >"$test_root/bin/tee" <<'MOCK_TEE'
#!/usr/bin/env bash
set -euo pipefail
tee_count=0
if [[ -f "$MOCK_ROOT/tee-count" ]]; then
    tee_count="$(<"$MOCK_ROOT/tee-count")"
fi
tee_count=$((tee_count + 1))
printf '%s' "$tee_count" >"$MOCK_ROOT/tee-count"
if [[ "${MOCK_TEE_FAILURE:-0}" == 1 ]]; then
    printf 'private summary write failure: %s\n' "${*: -1}" >&2
    exit 8
fi
if [[ -n "${MOCK_TEE_FAIL_ON_CALL:-}" &&
        "$tee_count" == "$MOCK_TEE_FAIL_ON_CALL" ]]; then
    printf 'private late summary failure: %s\n' "${*: -1}" >&2
    exit 8
fi
exec "$PHONE_MOCK_REAL_TEE" "$@"
MOCK_TEE
cat >"$test_root/bin/chmod" <<'MOCK_CHMOD'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_CHMOD_FAILURE:-0}" == 1 ]]; then
    printf 'private chmod failure: %s\n' "${*: -1}" >&2
    exit 9
fi
exec "$PHONE_MOCK_REAL_CHMOD" "$@"
MOCK_CHMOD
cat >"$test_root/bin/mktemp" <<'MOCK_MKTEMP'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_MKTEMP_FAILURE:-0}" == 1 ]]; then
    printf 'private mktemp failure: %s\n' "${*: -1}" >&2
    exit 10
fi
exec "$PHONE_MOCK_REAL_MKTEMP" "$@"
MOCK_MKTEMP
cat >"$test_root/bin/apkanalyzer" <<'MOCK_ANALYZER'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == manifest ]] || exit 3
case "$2" in
    application-id) printf '%s\n' "${MOCK_APK_ID:-org.overte.phone}" ;;
    min-sdk) printf '26\n' ;;
    target-sdk) printf '%s\n' "${MOCK_APK_TARGET_SDK:-36}" ;;
    permissions)
        printf '%s\n' android.permission.INTERNET \
            android.permission.ACCESS_NETWORK_STATE \
            android.permission.RECORD_AUDIO \
            android.permission.MODIFY_AUDIO_SETTINGS \
            android.permission.VIBRATE
        [[ "${MOCK_EXTRA_PERMISSION:-0}" != 1 ]] || \
            printf '%s\n' android.permission.CAMERA
        ;;
    debuggable) printf '%s\n' "${MOCK_APK_DEBUGGABLE:-true}" ;;
    *) exit 3 ;;
esac
MOCK_ANALYZER
cat >"$test_root/bin/apk-preflight" <<'MOCK_PREFLIGHT'
#!/usr/bin/env bash
set -euo pipefail
[[ -f "$1" ]] || exit 3
[[ "${MOCK_PREFLIGHT_FAILURE:-0}" != 1 ]]
MOCK_PREFLIGHT
chmod +x "$test_root/bin/adb" "$test_root/bin/sleep" "$test_root/bin/sha256sum" \
    "$test_root/bin/tee" "$test_root/bin/chmod" "$test_root/bin/mktemp" \
    "$test_root/bin/apkanalyzer" "$test_root/bin/apk-preflight"

mkdir "$test_root/unguarded-override-report"
: >"$test_root/adb-commands"
if env PATH="$test_root/bin:$PATH" MOCK_ROOT="$test_root" \
        PHONE_DEVICE_LOCK_HELD=1 PHONE_ADB="$test_root/bin/adb" \
        PHONE_APK_ANALYZER="$test_root/bin/apkanalyzer" \
        PHONE_APK_PREFLIGHT="$test_root/bin/apk-preflight" \
        ANDROID_SERIAL=mock-phone PHONE_TEST_REPORT="$test_root/unguarded-override-report" \
        "$script_dir/phone-device-test.sh" "$test_root/phone.apk" \
        >"$test_root/unguarded-override.out" 2>&1; then
    echo 'FAIL: nonstandard package gate was accepted without test override' >&2
    exit 1
fi
grep -Fq 'nonstandard APK preflight requires explicit host-test override' \
    "$test_root/unguarded-override.out"
[[ ! -s "$test_root/adb-commands" ]]

run_smoke() {
    local report_dir="$1"
    shift
    env PATH="$test_root/bin:$PATH" MOCK_ROOT="$test_root" \
        PHONE_DEVICE_LOCK_HELD=1 PHONE_ADB="$test_root/bin/adb" \
        PHONE_APK_ANALYZER="$test_root/bin/apkanalyzer" \
        PHONE_APK_PREFLIGHT="$test_root/bin/apk-preflight" \
        PHONE_ALLOW_TEST_OVERRIDES=1 \
        ANDROID_SERIAL=mock-phone PHONE_TEST_REPORT="$report_dir" "$@" \
        "$script_dir/phone-device-test.sh" "$test_root/phone.apk"
}

mkdir "$test_root/missing-apk-report"
: >"$test_root/adb-commands"
if env PATH="$test_root/bin:$PATH" MOCK_ROOT="$test_root" \
        PHONE_DEVICE_LOCK_HELD=1 PHONE_ADB="$test_root/bin/adb" \
        PHONE_APK_ANALYZER="$test_root/bin/apkanalyzer" \
        PHONE_APK_PREFLIGHT="$test_root/bin/apk-preflight" \
        PHONE_ALLOW_TEST_OVERRIDES=1 ANDROID_SERIAL=mock-phone \
        PHONE_TEST_REPORT="$test_root/missing-apk-report" \
        "$script_dir/phone-device-test.sh" "$test_root/private/missing.apk" \
        >"$test_root/missing-apk.out" 2>&1; then
    echo 'FAIL: missing APK input was accepted by device smoke' >&2
    exit 1
fi
grep -Fxq 'ERROR: APK was not found' "$test_root/missing-apk.out"
! grep -Fq "$test_root" "$test_root/missing-apk.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/hash-failure-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/hash-failure-report" env MOCK_SHA256_FAILURE=1 \
        >"$test_root/hash-failure.out" 2>&1; then
    echo 'FAIL: unreadable APK content was accepted by device smoke' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not read APK for SHA-256' "$test_root/hash-failure.out"
! grep -Fq 'private hash failure' "$test_root/hash-failure.out"
! grep -Fq "$test_root" "$test_root/hash-failure.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/summary-write-failure-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/summary-write-failure-report" env MOCK_TEE_FAILURE=1 \
        >"$test_root/summary-write-failure.out" 2>&1; then
    echo 'FAIL: failed initial summary write was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not update device-test summary' \
    "$test_root/summary-write-failure.out"
! grep -Fq 'private summary write failure' "$test_root/summary-write-failure.out"
! grep -Fq "$test_root" "$test_root/summary-write-failure.out"
[[ ! -s "$test_root/adb-commands" ]]
grep -Fxq 'test_status=failed' \
    "$test_root/summary-write-failure-report/summary.txt"

mkdir "$test_root/late-summary-failure-report"
rm -f -- "$test_root/tee-count" "$test_root/force-stop-count"
: >"$test_root/adb-commands"
if run_smoke "$test_root/late-summary-failure-report" \
        env MOCK_TEE_FAIL_ON_CALL=2 \
        >"$test_root/late-summary-failure.out" 2>&1; then
    echo 'FAIL: failed post-install summary write was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not update device-test summary' \
    "$test_root/late-summary-failure.out"
! grep -Fq 'private late summary failure' "$test_root/late-summary-failure.out"
! grep -Fq "$test_root" "$test_root/late-summary-failure.out"
grep -Fxq 'test_status=failed' \
    "$test_root/late-summary-failure-report/summary.txt"
! grep -Fq 'installed_apk_verified=1' \
    "$test_root/late-summary-failure-report/summary.txt"
[[ "$(grep -c ' install -r ' "$test_root/adb-commands")" -eq 1 ]]
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' \
    "$test_root/adb-commands")" -eq 1 ]]

mkdir "$test_root/chmod-failure-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/chmod-failure-report" env MOCK_CHMOD_FAILURE=1 \
        >"$test_root/chmod-failure.out" 2>&1; then
    echo 'FAIL: failed summary permission hardening was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not secure device-test summary' \
    "$test_root/chmod-failure.out"
! grep -Fq 'private chmod failure' "$test_root/chmod-failure.out"
! grep -Fq "$test_root" "$test_root/chmod-failure.out"
[[ ! -s "$test_root/adb-commands" ]]

: >"$test_root/adb-commands"
if run_smoke "" env MOCK_MKTEMP_FAILURE=1 \
        >"$test_root/mktemp-failure.out" 2>&1; then
    echo 'FAIL: failed temporary report creation was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not create device-test report directory' \
    "$test_root/mktemp-failure.out"
! grep -Fq 'private mktemp failure' "$test_root/mktemp-failure.out"
! grep -Fq "$test_root" "$test_root/mktemp-failure.out"
[[ ! -s "$test_root/adb-commands" ]]

: >"$test_root/adb-commands"
if env PATH="$test_root/bin:$PATH" MOCK_ROOT="$test_root" \
        PHONE_DEVICE_LOCK_HELD=1 PHONE_ADB="$test_root/bin/adb" \
        PHONE_APK_ANALYZER="$test_root/bin/apkanalyzer" \
        PHONE_APK_PREFLIGHT="$test_root/bin/apk-preflight" \
        PHONE_ALLOW_TEST_OVERRIDES=1 ANDROID_SERIAL=mock-phone \
        PHONE_TEST_REPORT="$test_root/private/missing-report" \
        "$script_dir/phone-device-test.sh" "$test_root/phone.apk" \
        >"$test_root/missing-report.out" 2>&1; then
    echo 'FAIL: missing device-report directory was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not resolve device-test report directory' \
    "$test_root/missing-report.out"
! grep -Fq "$test_root" "$test_root/missing-report.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/success-report"
run_smoke "$test_root/success-report" env >"$test_root/success.out"
! grep -Fq "$test_root" "$test_root/success.out"
summary="$test_root/success-report/summary.txt"
grep -Fxq 'installed_apk_verified=1' "$summary"
grep -Fxq 'apk_debuggable=1' "$summary"
grep -Fxq 'background_foreground_cycles=3' "$summary"
grep -Fxq 'back_recovery_survived=1' "$summary"
grep -Fxq 'crash_log_matches=0' "$summary"
grep -Fxq 'test_status=passed' "$summary"
grep -Fxq 'cleanup_force_stopped=1' "$summary"
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' "$test_root/adb-commands")" -eq 2 ]]
[[ "$(stat -c %a "$summary")" == 600 ]]
! grep -Eq 'mock-phone|/data/app|4242' "$summary"

mkdir "$test_root/cleanup-failure-report"
rm -f -- "$test_root/force-stop-count"
: >"$test_root/adb-commands"
if run_smoke "$test_root/cleanup-failure-report" env MOCK_FINAL_CLEANUP_FAILURE=1 \
        >"$test_root/cleanup-failure.out" 2>&1; then
    echo 'FAIL: failed final app cleanup was accepted' >&2
    exit 1
fi
grep -Fq 'final app cleanup failed' "$test_root/cleanup-failure.out"
grep -Fxq 'test_status=failed' "$test_root/cleanup-failure-report/summary.txt"
! grep -Fq 'cleanup_force_stopped=1' "$test_root/cleanup-failure-report/summary.txt"
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' "$test_root/adb-commands")" -eq 3 ]]

mkdir "$test_root/mismatch-report"
if run_smoke "$test_root/mismatch-report" env MOCK_APK_MISMATCH=1 \
        >"$test_root/mismatch.out" 2>&1; then
    echo 'FAIL: installed APK digest mismatch was accepted' >&2
    exit 1
fi
grep -Fq 'installed APK content does not match' "$test_root/mismatch.out"
! grep -Fq '/data/app/' "$test_root/mismatch.out"
! grep -Fq "$test_root" "$test_root/mismatch.out"

mkdir "$test_root/read-failure-report"
if run_smoke "$test_root/read-failure-report" env MOCK_INSTALLED_READ_FAILURE=1 \
        >"$test_root/read-failure.out" 2>&1; then
    echo 'FAIL: unavailable installed APK content was accepted' >&2
    exit 1
fi
grep -Fq 'could not read the installed APK for provenance verification' \
    "$test_root/read-failure.out"
! grep -Eq 'mock-phone|private installed path' "$test_root/read-failure.out"
! grep -Fq 'installed_apk_verified=1' "$test_root/read-failure-report/summary.txt"
grep -Fxq 'test_status=failed' "$test_root/read-failure-report/summary.txt"

mkdir "$test_root/wrong-package-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/wrong-package-report" env MOCK_APK_ID=example.unrelated \
        >"$test_root/wrong-package.out" 2>&1; then
    echo 'FAIL: unrelated APK application ID was accepted' >&2
    exit 1
fi
grep -Fq 'APK application ID does not match the Phone package' "$test_root/wrong-package.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/old-apk-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/old-apk-report" env MOCK_APK_TARGET_SDK=35 \
        >"$test_root/old-apk.out" 2>&1; then
    echo 'FAIL: APK with stale target SDK was accepted' >&2
    exit 1
fi
grep -Fq 'APK SDK metadata does not match the Phone build contract' "$test_root/old-apk.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/extra-permission-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/extra-permission-report" env MOCK_EXTRA_PERMISSION=1 \
        >"$test_root/extra-permission.out" 2>&1; then
    echo 'FAIL: APK with an unexpected dangerous permission was accepted' >&2
    exit 1
fi
grep -Fq 'APK permissions do not match the minimal Phone allowlist' \
    "$test_root/extra-permission.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/debug-mode-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/debug-mode-report" env PHONE_EXPECT_DEBUGGABLE=0 \
        >"$test_root/debug-mode.out" 2>&1; then
    echo 'FAIL: debuggable APK was accepted for a release-mode smoke' >&2
    exit 1
fi
grep -Fq 'APK debuggable state does not match the requested test mode' \
    "$test_root/debug-mode.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/package-preflight-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/package-preflight-report" env MOCK_PREFLIGHT_FAILURE=1 \
        >"$test_root/package-preflight.out" 2>&1; then
    echo 'FAIL: APK rejected by the package gate was accepted for installation' >&2
    exit 1
fi
grep -Fq 'APK failed the Phone content, ELF, alignment, or padding preflight' \
    "$test_root/package-preflight.out"
[[ ! -s "$test_root/adb-commands" ]]

mkdir "$test_root/emulator-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/emulator-report" env MOCK_QEMU=1 \
        >"$test_root/emulator.out" 2>&1; then
    echo 'FAIL: emulator was accepted as a physical phone target' >&2
    exit 1
fi
grep -Fq 'does not meet the physical Phone runtime contract' "$test_root/emulator.out"
! grep -q ' install -r ' "$test_root/adb-commands"

mkdir "$test_root/approved-emulator-report"
: >"$test_root/adb-commands"
run_smoke "$test_root/approved-emulator-report" env MOCK_QEMU=1 \
    PHONE_ALLOW_EMULATOR=1 >"$test_root/approved-emulator.out" 2>&1
grep -q ' install -r ' "$test_root/adb-commands"

mkdir "$test_root/old-sdk-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/old-sdk-report" env MOCK_SDK=25 \
        >"$test_root/old-sdk.out" 2>&1; then
    echo 'FAIL: device below the APK minimum SDK was accepted' >&2
    exit 1
fi
grep -Fq 'does not meet the physical Phone runtime contract' "$test_root/old-sdk.out"
! grep -q ' install -r ' "$test_root/adb-commands"

mkdir "$test_root/restart-report"
if run_smoke "$test_root/restart-report" env MOCK_PROCESS_RESTART=1 \
        >"$test_root/restart.out" 2>&1; then
    echo 'FAIL: background process restart was accepted' >&2
    exit 1
fi
grep -Fq 'app process restarted' "$test_root/restart.out"
! grep -Fq "$test_root" "$test_root/restart.out"
! grep -Fq 'background_foreground_cycles=3' "$test_root/restart-report/summary.txt"

mkdir "$test_root/install-failure-report"
if run_smoke "$test_root/install-failure-report" env MOCK_INSTALL_FAILURE=1 \
        >"$test_root/install-failure.out" 2>&1; then
    echo 'FAIL: failed ADB installation was accepted' >&2
    exit 1
fi
grep -Fq 'APK installation failed' "$test_root/install-failure.out"
! grep -Eq 'mock-phone|private adb detail|phone[.]apk' "$test_root/install-failure.out"

mkdir "$test_root/start-failure-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/start-failure-report" env MOCK_START_FAILURE=1 \
        >"$test_root/start-failure.out" 2>&1; then
    echo 'FAIL: failed Activity start was accepted' >&2
    exit 1
fi
grep -Fq 'launcher start failed' "$test_root/start-failure.out"
! grep -Fq 'private start failure for mock-phone' "$test_root/start-failure.out"
! grep -Fq 'launch_survived=1' "$test_root/start-failure-report/summary.txt"
grep -Fxq 'test_status=failed' "$test_root/start-failure-report/summary.txt"
[[ "$(grep -c 'shell am force-stop org[.]overte[.]phone' "$test_root/adb-commands")" -eq 2 ]]

mkdir "$test_root/sticky-report"
if run_smoke "$test_root/sticky-report" env MOCK_STICKY_FOREGROUND=1 \
        >"$test_root/sticky.out" 2>&1; then
    echo 'FAIL: activity remaining resumed after Home was accepted' >&2
    exit 1
fi
grep -Fq 'phone activity remained resumed in background' "$test_root/sticky.out"
! grep -Fq "$test_root" "$test_root/sticky.out"
! grep -Fq 'background_foreground_cycles=3' "$test_root/sticky-report/summary.txt"

mkdir "$test_root/logcat-failure-report"
if run_smoke "$test_root/logcat-failure-report" env MOCK_LOGCAT_FAILURE=1 \
        >"$test_root/logcat-failure.out" 2>&1; then
    echo 'FAIL: unavailable process log diagnostics were accepted' >&2
    exit 1
fi
grep -Fq 'could not read process-scoped log diagnostics' "$test_root/logcat-failure.out"
! grep -Fq 'crash_log_matches=' "$test_root/logcat-failure-report/summary.txt"

mkdir "$test_root/benign-16k-report"
run_smoke "$test_root/benign-16k-report" env MOCK_LOGCAT_FIXTURE=benign-16k \
    >"$test_root/benign-16k.out"
grep -Fxq 'page_size_mismatch_matches=0' "$test_root/benign-16k-report/summary.txt"

mkdir "$test_root/bad-16k-report"
set +e
run_smoke "$test_root/bad-16k-report" env MOCK_LOGCAT_FIXTURE=bad-16k \
    >"$test_root/bad-16k.out" 2>&1
bad_16k_status=$?
set -e
[[ $bad_16k_status -eq 2 ]] || {
    printf 'FAIL: incompatible 16 KiB marker returned status %d instead of 2\n' \
        "$bad_16k_status" >&2
    exit 1
}
grep -Fxq 'page_size_mismatch_matches=1' "$test_root/bad-16k-report/summary.txt"

mkdir "$test_root/exit-info-failure-report"
if run_smoke "$test_root/exit-info-failure-report" env MOCK_EXIT_INFO_FAILURE=1 \
        >"$test_root/exit-info-failure.out" 2>&1; then
    echo 'FAIL: unavailable exit diagnostics were accepted' >&2
    exit 1
fi
grep -Fq 'could not read baseline package exit diagnostics' \
    "$test_root/exit-info-failure.out"
! grep -Fq 'launch_survived=1' "$test_root/exit-info-failure-report/summary.txt"

mkdir "$test_root/final-exit-info-failure-report"
rm -f -- "$test_root/exit-info-count"
if run_smoke "$test_root/final-exit-info-failure-report" env MOCK_FINAL_EXIT_INFO_FAILURE=1 \
        >"$test_root/final-exit-info-failure.out" 2>&1; then
    echo 'FAIL: unavailable final exit diagnostics were accepted' >&2
    exit 1
fi
grep -Fq 'could not read final package exit diagnostics' \
    "$test_root/final-exit-info-failure.out"
grep -Fxq 'test_status=failed' "$test_root/final-exit-info-failure-report/summary.txt"
! grep -Fq 'exit_crash_matches=' "$test_root/final-exit-info-failure-report/summary.txt"

mkdir "$test_root/existing-report"
printf preserve >"$test_root/existing-report/summary.txt"
: >"$test_root/adb-commands"
if run_smoke "$test_root/existing-report" env >"$test_root/existing.out" 2>&1; then
    echo 'FAIL: existing summary was overwritten' >&2
    exit 1
fi
[[ "$(<"$test_root/existing-report/summary.txt")" == preserve ]]
! grep -q ' install -r ' "$test_root/adb-commands"
! grep -Fq "$test_root" "$test_root/existing.out"

mkdir "$test_root/symlink-report"
printf protected >"$test_root/protected-target"
ln -s "$test_root/protected-target" "$test_root/symlink-report/summary.txt"
: >"$test_root/adb-commands"
if run_smoke "$test_root/symlink-report" env >"$test_root/symlink.out" 2>&1; then
    echo 'FAIL: summary symlink was followed' >&2
    exit 1
fi
[[ "$(<"$test_root/protected-target")" == protected ]]
[[ -L "$test_root/symlink-report/summary.txt" ]]
! grep -q ' install -r ' "$test_root/adb-commands"
! grep -Fq "$test_root" "$test_root/symlink.out"

printf 'PASS: unattended phone device smoke mock\n'
