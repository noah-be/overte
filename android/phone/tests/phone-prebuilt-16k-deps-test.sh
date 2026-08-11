#!/usr/bin/env bash
set -euo pipefail

android_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
subject="$android_dir/phone-prebuilt-16k-deps.sh"
fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-prebuilt-test.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT
mkdir -p "$fixture/source" "$fixture/bin"
printf 'deterministic Phone dependency fixture\n' >"$fixture/source/android-phone-16k-conan.tgz"
(cd "$fixture/source" && sha256sum android-phone-16k-conan.tgz) >"$fixture/manifest.sha256"

cat >"$fixture/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
while (($#)); do
    if [[ "$1" == --output ]]; then output="$2"; shift 2; continue; fi
    shift
done
cp -- "$MOCK_ASSET" "$output"
MOCK
cat >"$fixture/bin/conan" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$MOCK_CALLS"
MOCK
cat >"$fixture/bin/finalize" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p -- "$(dirname -- "$MOCK_READY")"
touch "$MOCK_READY"
MOCK
chmod +x "$fixture/bin/curl" "$fixture/bin/conan" "$fixture/bin/finalize"

MOCK_ASSET="$fixture/source/android-phone-16k-conan.tgz" \
MOCK_CALLS="$fixture/calls" \
MOCK_READY="$fixture/ready/.phone-16k-dependencies.ready" \
PHONE_CURL="$fixture/bin/curl" PHONE_CONAN="$fixture/bin/conan" \
PHONE_PREBUILT_FINALIZER="$fixture/bin/finalize" \
PHONE_PREBUILT_READY_MARKER="$fixture/ready/.phone-16k-dependencies.ready" \
PHONE_PREBUILT_MANIFEST="$fixture/manifest.sha256" \
PHONE_PREBUILT_BASE_URL='https://invalid.example.test/release' \
PHONE_PREBUILT_TMPDIR="$fixture/large-download-temp" \
    "$subject" download >/dev/null

grep -Fq 'cache restore' "$fixture/calls"
[[ "$(grep -c 'install ' "$fixture/calls")" == 2 ]]
grep -Fq -- '--build=never' "$fixture/calls"
[[ -d "$fixture/large-download-temp" ]]
[[ -z "$(find "$fixture/large-download-temp" -mindepth 1 -print -quit)" ]]

printf '0  unexpected.tgz\n' >"$fixture/bad-manifest"
if PHONE_PREBUILT_MANIFEST="$fixture/bad-manifest" \
        PHONE_CONAN="$fixture/bin/conan" PHONE_CURL="$fixture/bin/curl" \
        "$subject" download >/dev/null 2>&1; then
    echo 'FAIL: malformed manifest was accepted' >&2
    exit 1
fi

printf '%064d  android-phone-16k-conan.tgz\n' 0 >"$fixture/wrong-checksum"
if MOCK_ASSET="$fixture/source/android-phone-16k-conan.tgz" \
        PHONE_PREBUILT_MANIFEST="$fixture/wrong-checksum" \
        PHONE_CONAN="$fixture/bin/conan" PHONE_CURL="$fixture/bin/curl" \
        PHONE_PREBUILT_TMPDIR="$fixture/failed-download-temp" \
        "$subject" download >/dev/null 2>&1; then
    echo 'FAIL: checksum mismatch was accepted' >&2
    exit 1
fi
[[ -d "$fixture/failed-download-temp" ]]
[[ -z "$(find "$fixture/failed-download-temp" -mindepth 1 -print -quit)" ]]

echo 'Phone prebuilt dependency tests passed.'
