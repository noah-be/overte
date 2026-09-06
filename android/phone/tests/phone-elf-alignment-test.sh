#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly checker="$script_dir/check-phone-elf-alignment.sh"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/phone-elf-alignment.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT

mkdir -p "$fixture/bin" "$fixture/package/lib/arm64-v8a"
printf 'not an ELF\n' >"$fixture/package/lib/arm64-v8a/libfixture.so"
cat >"$fixture/bin/readelf" <<'MOCK'
#!/usr/bin/env bash
printf 'private readelf failure: /private/sdk/tool\n' >&2
exit 9
MOCK
chmod +x "$fixture/bin/readelf"

if PATH="$fixture/bin:/usr/bin:/bin" "$checker" "$fixture/package" \
        >"$fixture/readelf.out" 2>&1; then
    echo 'FAIL: readelf failure was accepted' >&2
    exit 1
fi
grep -Fq 'lib/arm64-v8a/libfixture.so: readelf failed' "$fixture/readelf.out"
! grep -Fq '/private/sdk/tool' "$fixture/readelf.out"
! grep -Fq "$fixture" "$fixture/readelf.out"

if "$checker" "$fixture/private/missing.apk" >"$fixture/input.out" 2>&1; then
    echo 'FAIL: missing package input was accepted' >&2
    exit 1
fi
grep -Fq 'input is neither an Android package nor a directory' "$fixture/input.out"
! grep -Fq "$fixture" "$fixture/input.out"

printf 'not a ZIP\n' >"$fixture/private.apk"
if "$checker" "$fixture/private.apk" >"$fixture/archive.out" 2>&1; then
    echo 'FAIL: invalid package archive was accepted' >&2
    exit 1
fi
grep -Fq 'could not extract Android package' "$fixture/archive.out"
! grep -Fq "$fixture" "$fixture/archive.out"

mkdir "$fixture/empty-package"
if "$checker" "$fixture/empty-package" >"$fixture/empty.out" 2>&1; then
    echo 'FAIL: package without shared libraries was accepted' >&2
    exit 1
fi
grep -Fq 'package contains no inspectable shared libraries' "$fixture/empty.out"
! grep -Fq "$fixture" "$fixture/empty.out"

echo 'Phone ELF alignment error privacy checks passed.'

# Model NDK LLVM's rejection of -- and require an absolute single filename.
cat >"$fixture/bin/llvm-readelf" <<'MOCK'
#!/usr/bin/env bash
[[ $# == 2 && $1 == -lW && $2 == /* ]] || exit 9
printf '  LOAD 0x0 0x0 0x0 0x1 0x1 R %s\n' "${PHONE_TEST_ALIGNMENT:-0x4000}"
MOCK
chmod +x "$fixture/bin/llvm-readelf"
mkdir -p "$fixture/-relative package"
printf fixture > "$fixture/-relative package/libfixture.so"
(cd "$fixture"; PATH="$fixture/bin:/usr/bin:/bin" "$checker" '-relative package')     >"$fixture/llvm.out" 2>&1
grep -Fq 'All ELF LOAD segments meet' "$fixture/llvm.out"
if PHONE_TEST_ALIGNMENT=0x1000 PATH="$fixture/bin:/usr/bin:/bin"         "$checker" "$fixture/package" >"$fixture/unaligned.out" 2>&1; then
    echo 'FAIL: 4KiB library was accepted' >&2
    exit 1
fi
grep -Fq 'below 0x4000' "$fixture/unaligned.out"
ln -s "$fixture/private.apk" "$fixture/package/lib/arm64-v8a/libescape.so"
if PATH="$fixture/bin:/usr/bin:/bin" "$checker" "$fixture/package"         >"$fixture/escape.out" 2>&1; then
    echo 'FAIL: escaping library symlink was accepted' >&2
    exit 1
fi
grep -Fq 'symlink escapes the package directory' "$fixture/escape.out"
echo 'GNU/LLVM invocation, 16KiB rejection and symlink containment checks passed.'
