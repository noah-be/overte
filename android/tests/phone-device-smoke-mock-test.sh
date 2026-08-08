#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly test_root="$(mktemp -d "${TMPDIR:-/tmp}/phone-device-smoke-mock.XXXXXX")"
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
    'shell pm list features') printf 'feature:android.hardware.touchscreen\n' ;;
    install\ -r\ -g\ *) ;;
    'shell pm path org.overte.phone')
        printf 'package:/data/app/~~mock/org.overte.phone-mock/base.apk\n'
        ;;
    'shell date +%s.%3N') printf '1786212000.123\n' ;;
    'exec-out cat /data/app/~~mock/org.overte.phone-mock/base.apk')
        if [[ "${MOCK_APK_MISMATCH:-0}" == 1 ]]; then
            printf 'different installed bytes\n'
        else
            cat "$MOCK_ROOT/phone.apk"
        fi
        ;;
    'shell am force-stop org.overte.phone') ;;
    shell\ am\ start\ *) printf resumed >"$MOCK_ROOT/activity-state" ;;
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
chmod +x "$test_root/bin/adb" "$test_root/bin/sleep"

run_smoke() {
    local report_dir="$1"
    shift
    env PATH="$test_root/bin:$PATH" MOCK_ROOT="$test_root" \
        PHONE_DEVICE_LOCK_HELD=1 PHONE_ADB="$test_root/bin/adb" \
        ANDROID_SERIAL=mock-phone PHONE_TEST_REPORT="$report_dir" "$@" \
        "$script_dir/phone-device-test.sh" "$test_root/phone.apk"
}

mkdir "$test_root/success-report"
run_smoke "$test_root/success-report" env >"$test_root/success.out"
! grep -Fq "$test_root" "$test_root/success.out"
summary="$test_root/success-report/summary.txt"
grep -Fxq 'installed_apk_verified=1' "$summary"
grep -Fxq 'background_foreground_cycles=3' "$summary"
grep -Fxq 'back_recovery_survived=1' "$summary"
grep -Fxq 'crash_log_matches=0' "$summary"
[[ "$(stat -c %a "$summary")" == 600 ]]
! grep -Eq 'mock-phone|/data/app|4242' "$summary"

mkdir "$test_root/mismatch-report"
if run_smoke "$test_root/mismatch-report" env MOCK_APK_MISMATCH=1 \
        >"$test_root/mismatch.out" 2>&1; then
    echo 'FAIL: installed APK digest mismatch was accepted' >&2
    exit 1
fi
grep -Fq 'installed APK content does not match' "$test_root/mismatch.out"
! grep -Fq '/data/app/' "$test_root/mismatch.out"
! grep -Fq "$test_root" "$test_root/mismatch.out"

mkdir "$test_root/emulator-report"
: >"$test_root/adb-commands"
if run_smoke "$test_root/emulator-report" env MOCK_QEMU=1 \
        >"$test_root/emulator.out" 2>&1; then
    echo 'FAIL: emulator was accepted as a physical phone target' >&2
    exit 1
fi
grep -Fq 'not a physical ARM64 touchscreen phone target' "$test_root/emulator.out"
! grep -q '^install ' "$test_root/adb-commands"

mkdir "$test_root/restart-report"
if run_smoke "$test_root/restart-report" env MOCK_PROCESS_RESTART=1 \
        >"$test_root/restart.out" 2>&1; then
    echo 'FAIL: background process restart was accepted' >&2
    exit 1
fi
grep -Fq 'app process restarted' "$test_root/restart.out"
! grep -Fq "$test_root" "$test_root/restart.out"
! grep -Fq 'background_foreground_cycles=3' "$test_root/restart-report/summary.txt"

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
! grep -Fq 'launch_survived=1' "$test_root/exit-info-failure-report/summary.txt"

mkdir "$test_root/existing-report"
printf preserve >"$test_root/existing-report/summary.txt"
: >"$test_root/adb-commands"
if run_smoke "$test_root/existing-report" env >"$test_root/existing.out" 2>&1; then
    echo 'FAIL: existing summary was overwritten' >&2
    exit 1
fi
[[ "$(<"$test_root/existing-report/summary.txt")" == preserve ]]
! grep -q '^install ' "$test_root/adb-commands"

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
! grep -q '^install ' "$test_root/adb-commands"

printf 'PASS: unattended phone device smoke mock\n'
