#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/phone-apk-metadata.XXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT
printf placeholder >"$fixture/phone.apk"
cat >"$fixture/apkanalyzer" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == manifest ]] || exit 3
if [[ "${MOCK_ANALYZER_FAILURE:-0}" == 1 && "$2" == target-sdk ]]; then
    printf 'private analyzer failure: /private/sdk/tool\n' >&2
    exit 9
fi
case "$2" in
    application-id) printf '%s\n' "${MOCK_ID:-org.overte.phone}" ;;
    min-sdk) printf '%s\n' "${MOCK_MIN_SDK:-26}" ;;
    target-sdk) printf '%s\n' "${MOCK_TARGET_SDK:-36}" ;;
    version-code) printf '%s\n' "${MOCK_VERSION_CODE:-1}" ;;
    version-name) printf '%s\n' "${MOCK_VERSION_NAME:-2026.08.1-rc1}" ;;
    permissions)
        printf '%s\n' android.permission.ACCESS_NETWORK_STATE android.permission.INTERNET \
            android.permission.MODIFY_AUDIO_SETTINGS android.permission.RECORD_AUDIO \
            android.permission.VIBRATE
        [[ "${MOCK_EXTRA_PERMISSION:-0}" != 1 ]] || printf '%s\n' android.permission.CAMERA
        ;;
    debuggable) printf '%s\n' "${MOCK_DEBUGGABLE:-false}" ;;
    *) exit 3 ;;
esac
MOCK
chmod +x "$fixture/apkanalyzer"

PHONE_APK_ANALYZER="$fixture/apkanalyzer" "$script_dir/check-phone-apk-metadata.sh" \
    "$fixture/phone.apk" >/dev/null
PHONE_EXPECT_DEBUGGABLE=0 PHONE_APK_ANALYZER="$fixture/apkanalyzer" \
    "$script_dir/check-phone-apk-metadata.sh" "$fixture/phone.apk" >/dev/null
PHONE_EXPECT_DEBUGGABLE=1 MOCK_DEBUGGABLE=true PHONE_APK_ANALYZER="$fixture/apkanalyzer" \
    "$script_dir/check-phone-apk-metadata.sh" "$fixture/phone.apk" >/dev/null
if PHONE_EXPECT_DEBUGGABLE=1 PHONE_APK_ANALYZER="$fixture/apkanalyzer" \
        "$script_dir/check-phone-apk-metadata.sh" "$fixture/phone.apk" \
        >"$fixture/mode.out" 2>&1; then
    echo 'FAIL: release metadata was accepted for an expected debug variant' >&2
    exit 1
fi
grep -Fq 'does not match the expected variant' "$fixture/mode.out"
if MOCK_ANALYZER_FAILURE=1 PHONE_APK_ANALYZER="$fixture/apkanalyzer" \
        "$script_dir/check-phone-apk-metadata.sh" "$fixture/phone.apk" \
        >"$fixture/analyzer-failure.out" 2>&1; then
    echo 'FAIL: unavailable target-SDK analysis was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not read APK target SDK' "$fixture/analyzer-failure.out"
! grep -Fq '/private/sdk/tool' "$fixture/analyzer-failure.out"
for scenario in wrong-id old-sdk bad-code bad-name permission debug-state; do
    case "$scenario" in
        wrong-id) env_args=(MOCK_ID=example.invalid) ;;
        old-sdk) env_args=(MOCK_TARGET_SDK=35) ;;
        bad-code) env_args=(MOCK_VERSION_CODE=2147483648) ;;
        bad-name) env_args=('MOCK_VERSION_NAME=unsafe branch/name') ;;
        permission) env_args=(MOCK_EXTRA_PERMISSION=1) ;;
        debug-state) env_args=(MOCK_DEBUGGABLE=unknown) ;;
    esac
    if env "${env_args[@]}" PHONE_APK_ANALYZER="$fixture/apkanalyzer" \
            "$script_dir/check-phone-apk-metadata.sh" "$fixture/phone.apk" \
            >"$fixture/$scenario.out" 2>&1; then
        printf 'FAIL: APK metadata scenario %s was accepted\n' "$scenario" >&2
        exit 1
    fi
done
echo 'Phone APK metadata fixture checks passed.'
