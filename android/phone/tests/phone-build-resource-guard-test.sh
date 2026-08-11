#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
guard="$script_dir/phone-build-resource-guard.sh"
failures=0

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; failures=$((failures + 1)); }

bash -n "$guard" "$script_dir/build-phone-qt-16k.sh" \
    "$script_dir/prepare-phone-16k-conan-deps.sh" && pass 'guarded scripts parse' || fail 'guarded scripts parse'

for script in build-phone-qt-16k.sh prepare-phone-16k-conan-deps.sh; do
    if grep -Eq '^phone_build_resource_guard ' "$script_dir/$script"; then
        pass "$script invokes resource guard"
    else
        fail "$script invokes resource guard"
    fi
done

if grep -Fq 'tools.build:jobs=16' "$android_root/common/conan/profiles/phone-arm64-16k" \
        && grep -Fq 'tools.build:jobs=16' "$android_root/common/conan/profiles/phone-nonqt-arm64-16k"; then
    pass 'both profiles cap build parallelism at j16'
else
    fail 'both profiles cap build parallelism at j16'
fi

# Exercise the dispatch path without starting a build. The mock verifies that
# enforcing the scope is mandatory and that the requested limit is exact.
mock_dir="$(mktemp -d "${TMPDIR:-/tmp}/overte-resource-guard-test.XXXXXXXX")"
trap 'rm -rf -- "$mock_dir"' EXIT
if grep -Fq 'MAKEFLAGS= {self._make_program()} -j1 install' \
        "$android_root/common/conan/patches/qt-phone-serial-install.patch" \
        && grep -Fq 'qt-phone-serial-install.patch' "$script_dir/build-phone-qt-16k.sh"; then
    pass 'Qt recipe patch serializes package installation'
else
    fail 'Qt recipe patch serializes package installation'
fi
printf 'SwapTotal: 31250000 kB\n' >"$mock_dir/swap-at-limit"
printf 'SwapTotal: 31249999 kB\n' >"$mock_dir/swap-under-limit"
if bash -c 'source "$1"; phone_build_require_swap "$2"' \
        _ "$guard" "$mock_dir/swap-at-limit"; then
    pass 'exactly 32 GB decimal swap is accepted'
else
    fail 'exactly 32 GB decimal swap is accepted'
fi
if bash -c 'source "$1"; ! phone_build_require_swap "$2"' \
        _ "$guard" "$mock_dir/swap-under-limit"; then
    pass 'swap below 32 GB decimal is rejected'
else
    fail 'swap below 32 GB decimal is rejected'
fi

mkdir -p "$mock_dir/cgroup/user.slice/build.scope"
printf '0::/user.slice/build.scope\n' >"$mock_dir/proc-cgroup"
printf 'max\n' >"$mock_dir/cgroup/user.slice/build.scope/memory.max"
printf '20000000000\n' >"$mock_dir/cgroup/user.slice/memory.max"
printf 'max\n' >"$mock_dir/cgroup/memory.max"
if bash -c 'source "$1"; phone_build_verify_memory_cgroup "$2" "$3"' \
        _ "$guard" "$mock_dir/proc-cgroup" "$mock_dir/cgroup"; then
    pass 'finite ancestor limit governs an unlimited nested cgroup'
else
    fail 'finite ancestor limit governs an unlimited nested cgroup'
fi
rm "$mock_dir/cgroup/memory.max"
if bash -c 'source "$1"; phone_build_verify_memory_cgroup "$2" "$3"' \
        _ "$guard" "$mock_dir/proc-cgroup" "$mock_dir/cgroup"; then
    pass 'finite delegated limit permits inaccessible host ancestors'
else
    fail 'finite delegated limit permits inaccessible host ancestors'
fi
printf 'max\n' >"$mock_dir/cgroup/memory.max"
printf '20000000001\n' >"$mock_dir/cgroup/user.slice/memory.max"
if bash -c 'source "$1"; ! phone_build_verify_memory_cgroup "$2" "$3"' \
        _ "$guard" "$mock_dir/proc-cgroup" "$mock_dir/cgroup"; then
    pass 'effective cgroup limit above 20 GB decimal is rejected'
else
    fail 'effective cgroup limit above 20 GB decimal is rejected'
fi
printf 'max\n' >"$mock_dir/cgroup/user.slice/memory.max"
if bash -c 'source "$1"; ! phone_build_verify_memory_cgroup "$2" "$3"' \
        _ "$guard" "$mock_dir/proc-cgroup" "$mock_dir/cgroup"; then
    pass 'fully unlimited cgroup hierarchy is rejected'
else
    fail 'fully unlimited cgroup hierarchy is rejected'
fi

cat >"$mock_dir/systemd-run" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
expected=(--user --collect --wait --pipe --quiet --same-dir --property=MemoryMax=20000000000
    "--setenv=PATH=$PATH" --setenv=OVERTE_PHONE_RESOURCE_GUARD_ACTIVE=1 -- /absolute/mock-build
    'argument with spaces' '*' '')
actual=("$@")
[[ "$#" -eq "${#expected[@]}" ]]
for ((i = 0; i < ${#expected[@]}; ++i)); do
    [[ "${actual[i]}" == "${expected[i]}" ]]
done
exit 0
MOCK
chmod +x "$mock_dir/systemd-run"

if PATH="$mock_dir:$PATH" bash -c '
    source "$1"
    phone_build_require_swap() { return 0; }
    phone_build_resource_guard /absolute/mock-build "argument with spaces" "*" ""
' _ "$guard"; then
    pass 'systemd service dispatch preserves arguments and requests 20 GB decimal'
else
    fail 'systemd service dispatch preserves arguments and requests 20 GB decimal'
fi

if bash -c '
    source "$1"
    phone_build_require_swap() { return 0; }
    phone_build_verify_memory_cgroup() { return 0; }
    OVERTE_PHONE_RESOURCE_GUARD_ACTIVE=1 phone_build_resource_guard /absolute/mock-build
' _ "$guard"; then
    pass 'recursion marker verifies the active cgroup without redispatch'
else
    fail 'recursion marker verifies the active cgroup without redispatch'
fi

(( failures == 0 )) || exit 1
printf 'Resource guard tests passed.\n'
