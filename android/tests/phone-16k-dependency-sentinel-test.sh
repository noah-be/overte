#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly verifier="$script_dir/verify-phone-16k-dependencies.sh"
fixture=$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-16k-sentinel-test.XXXXXXXX")
trap 'rm -rf -- "$fixture"' EXIT INT TERM

test_root="$fixture/test-root"
mkdir -p -- "$test_root/tests"
cp -- "$verifier" "$test_root/tests/verify-phone-16k-dependencies.sh"
cat > "$test_root/tests/check-phone-elf-alignment.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ $(basename -- "$1") == staged-nonqt \
    && -n ${PHONE_TEST_MUTATE_STAGED:-} && -f $PHONE_TEST_MUTATE_STAGED ]]; then
    printf 'mutated-after-snapshot\n' > "$PHONE_TEST_MUTATE_STAGED"
fi
find "$1" -type f \( -name '*.so' -o -name '*.so.*' \) -print -quit | grep -q .
EOF
chmod +x "$test_root/tests/check-phone-elf-alignment.sh"

qt="$fixture/qt"
nonqt="$fixture/nonqt"
sentinel="$nonqt/.phone-16k-dependencies.ready"
mkdir -p -- "$qt/generators" "$nonqt/generators" "$nonqt/conanlibs/Debug"

make_package() {
    local label=$1
    local generator=$2
    local package_dir="$fixture/packages/$label"
    mkdir -p -- "$package_dir/lib"
    printf 'fake ELF for %s\n' "$label" > "$package_dir/lib/lib$label.so"
    printf 'set(%s_PACKAGE_FOLDER_DEBUG "%s")\n' \
        "${label//-/_}" "$package_dir" > "$generator"
}

make_package qt "$qt/generators/Qt5-debug-armv8-data.cmake"
make_package openssl "$nonqt/generators/OpenSSL-debug-armv8-data.cmake"
make_package tbb "$nonqt/generators/TBB-debug-armv8-data.cmake"
make_package libnode "$nonqt/generators/libnode-debug-armv8-data.cmake"
make_package webrtc-audio-processing \
    "$nonqt/generators/webrtc-audio-processing-debug-armv8-data.cmake"
printf crypto > "$nonqt/conanlibs/Debug/libcrypto.so.1.1"
printf ssl > "$nonqt/conanlibs/Debug/libssl.so.1.1"

verify() {
    "$test_root/tests/verify-phone-16k-dependencies.sh" "$qt" "$nonqt" "$sentinel"
}

expect_failure() {
    local description=$1
    shift
    if "$@" > "$fixture/failure.out" 2>&1; then
        echo "FAIL: $description unexpectedly succeeded" >&2
        exit 1
    fi
}

"$test_root/tests/verify-phone-16k-dependencies.sh" --write-sentinel \
    "$qt" "$nonqt" "$sentinel"
verify

printf tampered > "$sentinel"
expect_failure 'tampered sentinel' verify
"$test_root/tests/verify-phone-16k-dependencies.sh" --write-sentinel \
    "$qt" "$nonqt" "$sentinel"

generator="$nonqt/generators/TBB-debug-armv8-data.cmake"
mv -- "$generator" "$generator.real"
ln -s -- "$(basename -- "$generator.real")" "$generator"
expect_failure 'generator symlink' verify
rm -- "$generator"
mv -- "$generator.real" "$generator"

staged="$nonqt/conanlibs/Debug/libssl.so.1.1"
mv -- "$staged" "$staged.real"
ln -s -- "$(basename -- "$staged.real")" "$staged"
expect_failure 'staged library symlink' verify
rm -- "$staged"
mv -- "$staged.real" "$staged"

package="$fixture/packages/tbb"
ln -s -- missing.so "$package/lib/libbroken.so"
expect_failure 'broken package symlink' verify
rm -- "$package/lib/libbroken.so"
ln -s -- /etc/passwd "$package/lib/libescape.so"
expect_failure 'escaping package symlink' verify
rm -- "$package/lib/libescape.so"

# The fake alignment checker mutates the staged source after the verifier has
# copied it. A fresh sentinel must describe the checked snapshot, so the next
# verification against the changed source must reject it as stale.
PHONE_TEST_MUTATE_STAGED="$nonqt/conanlibs/Debug/libcrypto.so.1.1" \
    "$test_root/tests/verify-phone-16k-dependencies.sh" --write-sentinel \
    "$qt" "$nonqt" "$sentinel"
expect_failure 'source mutation after snapshot' verify

echo 'All phone 16 KiB dependency sentinel fixture tests passed.'
