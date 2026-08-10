#!/usr/bin/env bash
set -euo pipefail

mode=plan
tag=""
revision=""
apk=""
checksums=""
apk_manifest=""
output=""
confirmation=""
adb_bin="${PICO_ADB:-adb}"

fail() { echo "error: $*" >&2; exit 2; }
usage() {
    cat <<'EOF'
Usage: pico4-device-acceptance.sh --tag TAG --revision COMMIT --apk FILE
       --checksums FILE --apk-manifest FILE --output FILE
       [--execute --confirmation "INSTALL TAG"] [--adb FILE]

The default plan mode validates the immutable candidate without invoking ADB.
Execute mode installs/updates the verified APK and performs a minimal launch
smoke test. It must run through pico-device-lock.sh.
EOF
}

while (( $# )); do
    case "$1" in
        --tag) tag="${2:-}"; shift 2 ;;
        --revision) revision="${2:-}"; shift 2 ;;
        --apk) apk="${2:-}"; shift 2 ;;
        --checksums) checksums="${2:-}"; shift 2 ;;
        --apk-manifest) apk_manifest="${2:-}"; shift 2 ;;
        --output) output="${2:-}"; shift 2 ;;
        --adb) adb_bin="${2:-}"; shift 2 ;;
        --execute) mode=execute; shift ;;
        --confirmation) confirmation="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unsupported argument: $1" ;;
    esac
done

[[ "$tag" =~ ^pico4-v[0-9]+\.[0-9]+\.[0-9]+-rc\.[1-9][0-9]?$ ]] || fail "invalid Pico RC tag"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || fail "revision must be a lowercase 40-character commit"
for value in "$apk" "$checksums" "$apk_manifest"; do
    [[ -f "$value" ]] || fail "required file is missing: $value"
done
[[ -n "$output" ]] || fail "--output is required"

apk_name="$(basename -- "$apk")"
expected_digest="$(awk -v name="$apk_name" '$2 == name { print $1 }' "$checksums")"
[[ "$expected_digest" =~ ^[0-9a-f]{64}$ ]] || fail "SHA256SUMS has no unique digest for $apk_name"
[[ "$(awk -v name="$apk_name" '$2 == name { count++ } END { print count + 0 }' "$checksums")" == 1 ]] \
    || fail "SHA256SUMS must contain exactly one APK digest"
actual_digest="$(sha256sum "$apk" | awk '{print $1}')"
[[ "$actual_digest" == "$expected_digest" ]] || fail "APK digest does not match SHA256SUMS"

python3 - "$apk_manifest" "$apk_name" "$expected_digest" "$revision" <<'PY'
import json, sys
path, apk, digest, revision = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    manifest = json.load(stream)
expected = {"apk": apk, "sha256": digest, "source_revision": revision, "signature_verified": True}
for key, value in expected.items():
    if manifest.get(key) != value:
        raise SystemExit(f"error: APK manifest {key} mismatch")
PY

mkdir -p "$(dirname -- "$output")"
device_serial=""
device_model=""
install_result="not-run"
launch_result="not-run"

if [[ "$mode" == execute ]]; then
    [[ "$confirmation" == "INSTALL $tag" ]] || fail "execute mode requires exact confirmation: INSTALL $tag"
    [[ "${PICO_DEVICE_LOCK_HELD:-0}" == 1 ]] || fail "execute mode requires pico-device-lock.sh"
    [[ -x "$adb_bin" ]] || command -v "$adb_bin" >/dev/null 2>&1 || fail "ADB is unavailable"

    adb_devices="$("$adb_bin" devices)" || fail "ADB device enumeration failed"
    mapfile -t devices < <(printf '%s\n' "$adb_devices" | awk 'NR > 1 && $2 == "device" { print $1 }')
    (( ${#devices[@]} == 1 )) || fail "expected exactly one authorized ADB device"
    device_serial="${devices[0]}"
    [[ "$device_serial" != *:* ]] || fail "wireless ADB is not permitted for release acceptance"
    device_model="$("$adb_bin" -s "$device_serial" shell getprop ro.product.model | tr -d '\r')"
    [[ "$device_model" == *PICO* || "$device_model" == *Pico* ]] || fail "connected device is not identified as a Pico"

    "$adb_bin" -s "$device_serial" install -r "$apk"
    install_result=passed
    "$adb_bin" -s "$device_serial" shell am force-stop org.overte.pico
    "$adb_bin" -s "$device_serial" shell monkey -p org.overte.pico -c android.intent.category.LAUNCHER 1 >/dev/null
    sleep 5
    "$adb_bin" -s "$device_serial" shell pidof org.overte.pico >/dev/null || fail "Pico application did not remain running"
    launch_result=passed
fi

python3 - "$output" "$mode" "$tag" "$revision" "$expected_digest" \
    "$device_serial" "$device_model" "$install_result" "$launch_result" <<'PY'
import hashlib, json, sys
path, mode, tag, revision, digest, serial, model, installed, launched = sys.argv[1:]
report = {
    "apk_sha256": digest,
    "device_model": model or None,
    "device_serial_sha256": hashlib.sha256(serial.encode()).hexdigest() if serial else None,
    "install": installed,
    "launch": launched,
    "mode": mode,
    "source_revision": revision,
    "tag": tag,
}
with open(path, "w", encoding="utf-8", newline="\n") as stream:
    json.dump(report, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY

echo "Pico device acceptance $mode report: $output"
