#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-prepare.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT INT TERM
android_clang="$(find "${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}/ndk" \
    -path '*/toolchains/llvm/prebuilt/linux-x86_64/bin/clang' -print 2>/dev/null \
    | sort -V | tail -1)"
[[ -x "$android_clang" ]] || {
    printf 'SKIP: Android NDK clang is unavailable\n'
    exit 0
}

sed \
    -e 's|$android_root/vr/pico/build.sh|$script_dir/build-pico.sh|g' \
    -e 's|$android_root/common/conan|$script_dir/conan|g' \
    -e 's|$android_root/phone/tests|$script_dir/tests|g' \
    "$android_root/phone/build.sh" >"$fixture/build-phone.sh"
mkdir -p "$fixture/conan/phone-16k-debug/generators" \
    "$fixture/conan/phone-nonqt-16k-debug" "$fixture/tests" \
    "$fixture/private-conan/p/host/p/lib" "$fixture/private-conan/p/android/p/lib" \
    "$fixture/private-conan/p/other-android/p/lib"
cp "$android_root/common/conan/package-folder.py" "$fixture/conan/package-folder.py"
touch "$fixture/conan/phone-nonqt-16k-debug/.phone-16k-dependencies.ready"

sed 's/^+//' > "$fixture/tests/verify-phone-16k-dependencies.sh" <<'MOCK'
+#!/usr/bin/env bash
+set -euo pipefail
+[[ "$1" == */conan/phone-16k-debug ]]
+[[ "$2" == */conan/phone-nonqt-16k-debug ]]
+[[ "$3" == */conan/phone-nonqt-16k-debug/.phone-16k-dependencies.ready ]]
+[[ -f "$3" ]]
+printf '%s\n' 'verified Phone dependency graph'
MOCK
chmod +x "$fixture/build-phone.sh" "$fixture/tests/verify-phone-16k-dependencies.sh"

make_archive() {
    local package_dir="$1" compiler="$2" target="$3" source="$fixture/probe.c"
    printf 'int phone_draco_probe(void) { return 0; }\n' > "$source"
    if [[ -n "$target" ]]; then
        "$compiler" "$target" -c "$source" -o "$fixture/probe.o"
    else
        "$compiler" -c "$source" -o "$fixture/probe.o"
    fi
    ar rcs "$package_dir/lib/libdraco.a" "$fixture/probe.o"
}

make_archive "$fixture/private-conan/p/host/p" cc ""
printf '[settings]\narch=x86_64\nos=Linux\n' > "$fixture/private-conan/p/host/p/conaninfo.txt"
make_archive "$fixture/private-conan/p/android/p" "$android_clang" "--target=aarch64-linux-android26"
printf '[settings]\narch=armv8\nos=Android\n' > "$fixture/private-conan/p/android/p/conaninfo.txt"
make_archive "$fixture/private-conan/p/other-android/p" "$android_clang" "--target=aarch64-linux-android26"
printf '[settings]\narch=armv8\nos=Android\n' > "$fixture/private-conan/p/other-android/p/conaninfo.txt"
printf 'set(draco_PACKAGE_FOLDER_DEBUG "%s")\n' "$fixture/private-conan/p/android/p" \
    > "$fixture/conan/phone-16k-debug/generators/draco-debug-armv8-data.cmake"

sed 's/^+//' > "$fixture/build-pico.sh" <<'MOCK'
+#!/usr/bin/env bash
+set -euo pipefail
+[[ "$1" == prepare ]]
+[[ -n "${PICO_DRACO_PACKAGE_DIR:-}" ]]
+[[ "$PICO_DRACO_PACKAGE_DIR" == "$EXPECTED_CONAN_HOME/p/android/p" ]]
+[[ "$CONAN_HOME" == "$EXPECTED_CONAN_HOME" ]]
+grep -Eq '^os=Android$' "$PICO_DRACO_PACKAGE_DIR/conaninfo.txt"
+grep -Eq '^arch=armv8$' "$PICO_DRACO_PACKAGE_DIR/conaninfo.txt"
+printf '%s\n' 'selected Android ARM64 Draco package'
MOCK
chmod +x "$fixture/build-pico.sh"

export EXPECTED_CONAN_HOME="$fixture/private-conan"
export PHONE_SHARED_CONAN_HOME="$EXPECTED_CONAN_HOME"
output="$("$fixture/build-phone.sh" prepare)"
grep -Fq 'verified Phone dependency graph' <<< "$output"
grep -Fq 'selected Android ARM64 Draco package' <<< "$output"

output="$(PICO_DRACO_PACKAGE_DIR="$fixture/private-conan/p/android/p" \
    "$fixture/build-phone.sh" prepare)"
grep -Fq 'selected Android ARM64 Draco package' <<< "$output"

set +e
bad_output="$(EXPECTED_CONAN_HOME="$fixture/unexpected-cache" \
    "$fixture/build-phone.sh" prepare 2>&1)"
bad_status=$?
set -e
[[ $bad_status -ne 0 ]]
! grep -Fq 'selected Android ARM64 Draco package' <<< "$bad_output"

set +e
bad_output="$(PICO_DRACO_PACKAGE_DIR="$fixture/private-conan/p/host/p" \
    "$fixture/build-phone.sh" prepare 2>&1)"
bad_status=$?
set -e
[[ $bad_status -eq 2 ]]
grep -Fq 'PICO_DRACO_PACKAGE_DIR is not an Android ARM64 Draco package' <<< "$bad_output"

set +e
bad_output="$(PICO_DRACO_PACKAGE_DIR="$fixture/private-conan/p/other-android/p" \
    "$fixture/build-phone.sh" prepare 2>&1)"
bad_status=$?
set -e
[[ $bad_status -eq 2 ]]
grep -Fq 'does not match the prepared Phone Draco graph' <<< "$bad_output"

cat "$fixture/conan/phone-16k-debug/generators/draco-debug-armv8-data.cmake" \
    >> "$fixture/conan/phone-16k-debug/generators/draco-duplicate.cmake"
cat "$fixture/conan/phone-16k-debug/generators/draco-duplicate.cmake" \
    >> "$fixture/conan/phone-16k-debug/generators/draco-debug-armv8-data.cmake"
set +e
bad_output="$("$fixture/build-phone.sh" prepare 2>&1)"
bad_status=$?
set -e
[[ $bad_status -eq 2 ]]
grep -Fq 'prepared Phone Draco graph has no exact package binding' <<< "$bad_output"

rm "$fixture/conan/phone-16k-debug/generators/draco-debug-armv8-data.cmake"
set +e
bad_output="$("$fixture/build-phone.sh" prepare 2>&1)"
bad_status=$?
set -e
[[ $bad_status -eq 2 ]]
grep -Fq 'prepared Phone Draco graph has no exact package binding' <<< "$bad_output"

printf 'Android phone prepare exact graph and isolated cache checks passed.\n'
