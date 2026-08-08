#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/.." && pwd)"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-doctor.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT INT TERM

cp -- "$android_root/build-phone.sh" "$fixture/build-phone.sh"
sed 's/^+//' > "$fixture/build-pico.sh" <<'MOCK'
+#!/usr/bin/env bash
+printf 'Pico 4 build environment\n\n'
+printf '  [OK]   shared checker reached\n\n'
+printf 'Ready: all required build tools were found (0 warning(s)).\n'
+printf 'Next: ./build-pico.sh setup --download\n'
+exit "${MOCK_DOCTOR_STATUS:-0}"
MOCK
chmod +x "$fixture/build-phone.sh" "$fixture/build-pico.sh"

output="$($fixture/build-phone.sh doctor)"
grep -Fq 'Android phone build environment (shared toolchain)' <<< "$output"
grep -Fq 'Next: follow ANDROID_PHONE_BUILD.md 16 KiB setup order; then ./build-phone.sh build' \
    <<< "$output"
grep -Fq '[SETUP] verified 16 KiB dependencies are not prepared yet' <<< "$output"
if grep -Eq 'Pico 4 build environment|Next: ./build-pico[.]sh' <<< "$output"; then
    printf 'FAIL: Phone doctor leaks a Pico-specific heading or next step\n' >&2
    exit 1
fi

set +e
MOCK_DOCTOR_STATUS=7 "$fixture/build-phone.sh" doctor >/dev/null
status=$?
set -e
if [[ $status -ne 7 ]]; then
    printf 'FAIL: Phone doctor changed shared checker status 7 to %d\n' "$status" >&2
    exit 1
fi

mkdir -p "$fixture/conan/phone-nonqt-16k-debug"
touch "$fixture/conan/phone-nonqt-16k-debug/.phone-16k-dependencies.ready"
ready_output="$($fixture/build-phone.sh doctor)"
grep -Fq '[READY] verified 16 KiB dependency marker is present' <<< "$ready_output"
if grep -Fq '[SETUP]' <<< "$ready_output"; then
    echo 'FAIL: Phone doctor reports setup after finding the readiness marker' >&2
    exit 1
fi

printf 'Android phone doctor output checks passed.\n'
