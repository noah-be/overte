#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_dir="$(cd -- "$script_dir/../.." && pwd)"
temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-deploy-test.XXXXXXXX")"
trap 'rm -rf -- "$temp_dir"' EXIT INT TERM
touch "$temp_dir/test.apk"

sed 's/^+//' > "$temp_dir/adb" <<'MOCK'
+#!/usr/bin/env bash
+set -euo pipefail
+printf '%s\n' "$*" >> "$MOCK_ADB_LOG"
+if [[ ${1:-} == devices ]]; then
+    printf 'List of devices attached\n'
+    case "$MOCK_SCENARIO" in
+        phone) printf 'phone-serial device product:test\n' ;;
+        pico) printf 'pico-serial device product:test\n' ;;
+        two) printf 'phone-one device product:test\nphone-two device product:test\n' ;;
+    esac
+    exit
+fi
+[[ ${1:-} == -s ]] || { printf 'implicit ADB target used\n' >&2; exit 90; }
+serial=$2
+shift 2
+if [[ ${1:-} == shell && ${2:-} == getprop ]]; then
+    if [[ $serial == pico-serial ]]; then
+        case "${3:-}" in
+            ro.product.manufacturer) printf 'PICO\n' ;;
+            ro.build.characteristics) printf 'vr\n' ;;
+        esac
+    elif [[ ${3:-} == ro.build.characteristics ]]; then
+        printf 'phone\n'
+    fi
+    exit
+fi
+[[ ${1:-} == install || ( ${1:-} == shell && ${2:-} == am ) ]] || exit 91
MOCK
chmod +x "$temp_dir/adb"

run_install() {
    MOCK_ADB_LOG="$temp_dir/adb.log" MOCK_SCENARIO=$1 PHONE_ADB="$temp_dir/adb" \
        PHONE_APK="$temp_dir/test.apk" ANDROID_SERIAL="${2:-}" \
        "$android_dir/phone/build.sh" install
}

: > "$temp_dir/adb.log"
run_install phone
grep -q -- '-s phone-serial install' "$temp_dir/adb.log"
grep -q -- '-s phone-serial shell am start' "$temp_dir/adb.log"
if grep -Eq '^(install|shell)' "$temp_dir/adb.log"; then
    echo 'FAIL: deploy used an implicit ADB target' >&2
    exit 1
fi

if run_install pico pico-serial >/dev/null 2>&1; then
    echo 'FAIL: deploy accepted a Pico/VR target' >&2
    exit 1
fi
if run_install two >/dev/null 2>&1; then
    echo 'FAIL: deploy accepted an ambiguous device set' >&2
    exit 1
fi

echo 'Phone deploy safety checks passed.'
