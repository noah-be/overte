#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-download-parity.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT INT TERM

sed 's|$android_root/vr/pico/build.sh|$script_dir/build-pico.sh|g' \
    "$android_root/phone/build.sh" >"$fixture/build-phone.sh"
for helper in build-pico.sh phone-prebuilt-16k-deps.sh build-phone-qt-16k.sh \
        prepare-phone-16k-conan-deps.sh; do
    sed "s|HELPER|$helper|g" > "$fixture/$helper" <<'MOCK'
#!/usr/bin/env bash
if [[ 'HELPER' == build-pico.sh && "$*" == 'deps --download' ]]; then
    [[ "${CONAN_HOME:-}" == "${PHONE_EXPECT_SHARED_CONAN_HOME:-}" ]]
    [[ "${PICO_PREBUILT_RESTORE_ONLY:-}" == 1 ]]
    [[ -z "${PICO_QT_FALLBACK_PATCH:-}" ]]
fi
if [[ 'HELPER' == build-pico.sh && "$*" == deps ]]; then
    [[ -z "${PICO_QT_FALLBACK_PATCH:-}" ]]
fi
printf '%s' 'HELPER' >> "$PHONE_PARITY_LOG"
printf ' <%s>\n' "$*" >> "$PHONE_PARITY_LOG"
MOCK
    chmod +x "$fixture/$helper"
done
chmod +x "$fixture/build-phone.sh"

log="$fixture/calls.log"
CONAN_HOME="$fixture/phone-conan-home" PHONE_SHARED_CONAN_HOME="$fixture/shared-conan-home" \
    PHONE_EXPECT_SHARED_CONAN_HOME="$fixture/shared-conan-home" \
    PHONE_PARITY_LOG="$log" "$fixture/build-phone.sh" deps --download
mapfile -t calls < "$log"
[[ "${calls[0]}" == 'build-pico.sh <deps --download>' ]]
[[ "${calls[1]}" == 'phone-prebuilt-16k-deps.sh <download>' ]]
[[ ${#calls[@]} -eq 2 ]]
[[ -d "$fixture/build/prebuilt-tmp" ]]

: > "$log"
PHONE_PARITY_LOG="$log" "$fixture/build-phone.sh" deps
mapfile -t calls < "$log"
[[ "${calls[0]}" == 'build-pico.sh <deps>' ]]
[[ "${calls[1]}" == 'build-phone-qt-16k.sh <>' ]]
[[ "${calls[2]}" == 'prepare-phone-16k-conan-deps.sh <>' ]]
[[ ${#calls[@]} -eq 3 ]]

set +e
PHONE_PARITY_LOG="$log" "$fixture/build-phone.sh" deps --unknown >/dev/null 2>&1
status=$?
set -e
[[ $status -eq 2 ]]

printf 'Phone/Pico dependency command parity checks passed.\n'
