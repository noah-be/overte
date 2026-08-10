#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/pico-device-acceptance-test.XXXXXX")"
trap 'rm -rf -- "$ROOT"' EXIT

apk="$ROOT/picoInterface-release.apk"
checksums="$ROOT/SHA256SUMS"
manifest="$ROOT/apk-manifest.json"
report="$ROOT/report.json"
adb_log="$ROOT/adb.log"
revision=0123456789abcdef0123456789abcdef01234567
tag=pico4-v1.2.3-rc.4
printf 'verified fixture\n' >"$apk"
digest="$(sha256sum "$apk" | awk '{print $1}')"
printf '%s  picoInterface-release.apk\n' "$digest" >"$checksums"
printf '{"apk":"picoInterface-release.apk","sha256":"%s","signature_verified":true,"source_revision":"%s"}\n' \
    "$digest" "$revision" >"$manifest"

cat >"$ROOT/adb" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$MOCK_ADB_LOG"
if [[ "${1:-}" == devices ]]; then
    printf 'List of devices attached\nPICOUSB123\tdevice\n'
elif [[ "$*" == *'getprop ro.product.model'* ]]; then
    printf 'PICO 4\r\n'
elif [[ "$*" == *'pidof org.overte.pico'* ]]; then
    printf '1234\n'
else
    printf 'Success\n'
fi
EOF
chmod +x "$ROOT/adb"

common=(--tag "$tag" --revision "$revision" --apk "$apk" --checksums "$checksums"
        --apk-manifest "$manifest" --output "$report" --adb "$ROOT/adb")

MOCK_ADB_LOG="$adb_log" "$SCRIPT_DIR/../ci/pico4-device-acceptance.sh" "${common[@]}"
[[ ! -e "$adb_log" ]] || { echo "plan mode invoked ADB" >&2; exit 1; }
python3 - "$report" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["mode"] == "plan" and data["install"] == "not-run"
PY

if MOCK_ADB_LOG="$adb_log" PICO_DEVICE_LOCK_HELD=1 \
    "$SCRIPT_DIR/../ci/pico4-device-acceptance.sh" --execute --confirmation wrong "${common[@]}" \
    >"$ROOT/wrong.out" 2>&1; then
    echo "invalid confirmation unexpectedly succeeded" >&2
    exit 1
fi
[[ ! -e "$adb_log" ]] || { echo "invalid confirmation invoked ADB" >&2; exit 1; }

printf 'tampered\n' >>"$apk"
if "$SCRIPT_DIR/../ci/pico4-device-acceptance.sh" "${common[@]}" >"$ROOT/digest.out" 2>&1; then
    echo "digest mismatch unexpectedly succeeded" >&2
    exit 1
fi
printf 'verified fixture\n' >"$apk"

MOCK_ADB_LOG="$adb_log" PICO_DEVICE_LOCK_HELD=1 \
    "$SCRIPT_DIR/../ci/pico4-device-acceptance.sh" --execute \
    --confirmation "INSTALL $tag" "${common[@]}"
grep -q '^devices$' "$adb_log"
grep -q 'install -r' "$adb_log"
grep -q 'monkey -p org.overte.pico' "$adb_log"
python3 - "$report" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["mode"] == "execute"
assert data["install"] == data["launch"] == "passed"
assert data["device_model"] == "PICO 4"
assert data["device_serial_sha256"] and "device_serial" not in data
PY

echo "Pico device acceptance contract tests passed"
