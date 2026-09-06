#!/usr/bin/env bash
set -euo pipefail

readonly phone_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly repo_root="$(cd -- "$phone_root/../.." && pwd)"
readonly subject="$phone_root/fdroid/scripts/build-release.sh"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-fdroid-prep.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT INT TERM

mkdir -p \
    "$fixture/jdk/bin" \
    "$fixture/sdk/platforms/android-36" \
    "$fixture/sdk/build-tools/36.0.0" \
    "$fixture/sdk/platform-tools" \
    "$fixture/sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin" \
    "$fixture/conan-home" \
    "$fixture/shared"

for name in source-graph bootstrap.lock hosttools.lock target.lock evidence identity; do
    printf 'opaque shared fixture: %s\n' "$name" >"$fixture/shared/$name"
done

digest() { sha256sum -- "$1" | cut -d' ' -f1; }

readonly runtime_path="$fixture/jdk/bin:$fixture/sdk/build-tools/36.0.0:$fixture/sdk/platform-tools:$fixture/sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin:/usr/bin:/bin"
readonly -a shared_args=(
    --input-map "$repo_root/android/phone/fdroid/profiles/input-map.json"
    --base-toolchain "$repo_root/android/phone/fdroid/manifests/base-toolchain.lock.json"
    --cmake-toolchain "$repo_root/android/common/cmake/overte-android-toolchain.cmake"
    --bootstrap-graph "$repo_root/android/phone/fdroid/conan/bootstrap.conanfile.py"
    --bootstrap-profile "$repo_root/android/phone/fdroid/profiles/linux-x86_64-bootstrap"
    --hosttools-profile "$repo_root/android/phone/fdroid/profiles/linux-x86_64-hosttools"
    --target-profile "$repo_root/android/phone/fdroid/profiles/android-arm64-v8a-api26-16k"
    --shared-source-graph "$fixture/shared/source-graph" "$(digest "$fixture/shared/source-graph")"
    --shared-lock "$fixture/shared/bootstrap.lock" "$(digest "$fixture/shared/bootstrap.lock")"
    --shared-lock "$fixture/shared/hosttools.lock" "$(digest "$fixture/shared/hosttools.lock")"
    --shared-lock "$fixture/shared/target.lock" "$(digest "$fixture/shared/target.lock")"
    --shared-evidence-contract "$fixture/shared/evidence" "$(digest "$fixture/shared/evidence")"
    --shared-artifact-identity "$fixture/shared/identity" "$(digest "$fixture/shared/identity")"
)
readonly -a runtime_env=(
    "PATH=$runtime_path"
    "JAVA_HOME=$fixture/jdk"
    "ANDROID_SDK_ROOT=$fixture/sdk"
    "ANDROID_NDK_HOME=$fixture/sdk/ndk/27.3.13750724"
    "CONAN_HOME=$fixture/conan-home"
)

env -i "${runtime_env[@]}" "$subject" preflight "${shared_args[@]}" \
    | grep -Fxq $'PHONE_FDROID_PREFLIGHT=PASS\tshared_locks=3'

# The public Phone wrapper must enter exactly the same isolated adapter.
env -i "${runtime_env[@]}" "$phone_root/build.sh" fdroid preflight "${shared_args[@]}" \
    | grep -Fxq $'PHONE_FDROID_PREFLIGHT=PASS\tshared_locks=3'

set +e
build_output="$(env -i "${runtime_env[@]}" "$subject" build "${shared_args[@]}" 2>&1)"
build_status=$?
set -e
[[ $build_status -eq 3 ]]
grep -Fq 'PHONE_FDROID_BUILD=DEFERRED_SHARED_BINDING' <<<"$build_output"

if env -i "${runtime_env[@]}" "$subject" preflight >/dev/null 2>&1; then
    echo 'FAIL: absent graph and lock inputs were accepted' >&2
    exit 1
fi

set +e
missing_lock_output="$(env -i "${runtime_env[@]}" "$subject" preflight \
    "${shared_args[@]:0:${#shared_args[@]}-12}" 2>&1)"
missing_lock_status=$?
set -e
[[ $missing_lock_status -eq 2 ]]

bad_args=("${shared_args[@]}")
for ((index = 0; index < ${#bad_args[@]}; ++index)); do
    if [[ "${bad_args[index]}" == --shared-source-graph ]]; then
        bad_args[index + 2]="$(printf '%064d' 0)"
        break
    fi
done
if env -i "${runtime_env[@]}" "$subject" preflight "${bad_args[@]}" >/dev/null 2>&1; then
    echo 'FAIL: stale source-graph digest was accepted' >&2
    exit 1
fi

ln -s "$fixture/shared/source-graph" "$fixture/shared/source-graph-link"
if env -i "${runtime_env[@]}" "$subject" preflight "${shared_args[@]}" \
        --shared-source-graph "$fixture/shared/source-graph" \
        "$(digest "$fixture/shared/source-graph")" >/dev/null 2>&1; then
    echo 'FAIL: duplicate singleton option was accepted' >&2
    exit 1
fi

ln "$fixture/shared/bootstrap.lock" "$fixture/shared/bootstrap-hardlink.lock"
for repeated_lock in "$fixture/shared/bootstrap.lock" "$fixture/shared/bootstrap-hardlink.lock"; do
    duplicate_locks=("${shared_args[@]}")
    for ((index = 0; index < ${#duplicate_locks[@]}; ++index)); do
        if [[ "${duplicate_locks[index]}" == "$fixture/shared/hosttools.lock" ]]; then
            duplicate_locks[index]="$repeated_lock"
            duplicate_locks[index + 1]="$(digest "$repeated_lock")"
            break
        fi
    done
    if env -i "${runtime_env[@]}" "$subject" preflight "${duplicate_locks[@]}" >/dev/null 2>&1; then
        echo 'FAIL: duplicate graph lock file was accepted' >&2
        exit 1
    fi
done

symlink_args=("${shared_args[@]}")
for ((index = 0; index < ${#symlink_args[@]}; ++index)); do
    if [[ "${symlink_args[index]}" == --shared-source-graph ]]; then
        symlink_args[index + 1]="$fixture/shared/source-graph-link"
        break
    fi
done
if env -i "${runtime_env[@]}" "$subject" preflight "${symlink_args[@]}" >/dev/null 2>&1; then
    echo 'FAIL: symlinked source-graph input was accepted' >&2
    exit 1
fi

for forbidden in \
        'PHONE_PREBUILT_BASE_URL=https://invalid.example.test' \
        'ARTIFACTORY_URL=https://invalid.example.test' \
        'CONAN_REMOTE=forbidden' \
        'CONAN_BUILD_POLICY=missing' \
        'CONAN_DEFAULT_PROFILE=default'; do
    if env -i "${runtime_env[@]}" "$forbidden" \
            "$subject" preflight "${shared_args[@]}" >/dev/null 2>&1; then
        printf 'FAIL: forbidden F-Droid input was accepted: %s\n' "${forbidden%%=*}" >&2
        exit 1
    fi
done

for forbidden_option in \
        '--prebuilt-archive=android-phone-16k-conan.tgz' \
        '--artifactory=https://invalid.example.test' \
        '--remote=implicit' \
        '--build=missing' \
        '--profile=default'; do
    if env -i "${runtime_env[@]}" "$subject" preflight \
            "${shared_args[@]}" "$forbidden_option" >/dev/null 2>&1; then
        printf 'FAIL: forbidden F-Droid option was accepted: %s\n' \
            "${forbidden_option%%=*}" >&2
        exit 1
    fi
done

touch "$fixture/conan-home/unexpected"
if env -i "${runtime_env[@]}" "$subject" preflight "${shared_args[@]}" >/dev/null 2>&1; then
    echo 'FAIL: nonempty Conan home was accepted' >&2
    exit 1
fi
rm "$fixture/conan-home/unexpected"

cp "$repo_root/android/phone/fdroid/profiles/android-arm64-v8a-api26-16k" \
    "$fixture/shared/substituted-target-profile"
substituted=("${shared_args[@]}")
for ((index = 0; index < ${#substituted[@]}; ++index)); do
    if [[ "${substituted[index]}" == --target-profile ]]; then
        substituted[index + 1]="$fixture/shared/substituted-target-profile"
        break
    fi
done
if env -i "${runtime_env[@]}" "$subject" preflight "${substituted[@]}" >/dev/null 2>&1; then
    echo 'FAIL: substituted SH-010 target profile was accepted' >&2
    exit 1
fi

[[ -z "$(find "$fixture/conan-home" -mindepth 1 -print -quit)" ]]

bash -n "$subject" "$phone_root/build.sh"
printf 'Phone F-Droid build-only preparation checks passed.\n'
