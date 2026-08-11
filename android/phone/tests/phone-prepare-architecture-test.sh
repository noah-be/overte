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
mkdir -p "$fixture/conan/phone-16k-debug" \
    "$fixture/conan/phone-nonqt-16k-debug" "$fixture/tests" \
    "$fixture/home/.conan2/p/host/p/lib" "$fixture/home/.conan2/p/android/p/lib"
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

make_archive "$fixture/home/.conan2/p/host/p" cc ""
printf '[settings]\narch=x86_64\nos=Linux\n' > "$fixture/home/.conan2/p/host/p/conaninfo.txt"
make_archive "$fixture/home/.conan2/p/android/p" "$android_clang" "--target=aarch64-linux-android26"
printf '[settings]\narch=armv8\nos=Android\n' > "$fixture/home/.conan2/p/android/p/conaninfo.txt"

sed 's/^+//' > "$fixture/build-pico.sh" <<'MOCK'
+#!/usr/bin/env bash
+[[ "$1" == prepare ]]
+[[ -n "${PICO_DRACO_PACKAGE_DIR:-}" ]]
+grep -Eq '^os=Android$' "$PICO_DRACO_PACKAGE_DIR/conaninfo.txt"
+grep -Eq '^arch=armv8$' "$PICO_DRACO_PACKAGE_DIR/conaninfo.txt"
+printf '%s\n' 'selected Android ARM64 Draco package'
MOCK
chmod +x "$fixture/build-pico.sh"

output="$(HOME="$fixture/home" "$fixture/build-phone.sh" prepare)"
grep -Fq 'verified Phone dependency graph' <<< "$output"
grep -Fq 'selected Android ARM64 Draco package' <<< "$output"

set +e
bad_output="$(HOME="$fixture/home" PICO_DRACO_PACKAGE_DIR="$fixture/home/.conan2/p/host/p" \
    "$fixture/build-phone.sh" prepare 2>&1)"
bad_status=$?
set -e
[[ $bad_status -eq 2 ]]
grep -Fq 'PICO_DRACO_PACKAGE_DIR is not an Android ARM64 Draco package' <<< "$bad_output"

printf 'Android phone prepare dependency and architecture checks passed.\n'
