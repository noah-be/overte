#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../../.." && pwd)"
readonly profile_doctor="$repo_root/android/phone/fdroid/profiles/doctor.py"

fail() {
    printf 'PHONE_FDROID_PREFLIGHT=FAIL\t%s\n' "$*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: build-release.sh preflight|build \
  --input-map PATH \
  --base-toolchain PATH \
  --cmake-toolchain PATH \
  --bootstrap-graph PATH \
  --bootstrap-profile PATH \
  --hosttools-profile PATH \
  --target-profile PATH \
  --shared-source-graph PATH SHA256 \
  --shared-lock PATH SHA256  # exactly three times \
  --shared-evidence-contract PATH SHA256 \
  --shared-artifact-identity PATH SHA256

       build-release.sh verify-candidate [Phone SH-009 consumer flags] \
         [--build-evidence PATH --expected-artifact-sha256 SHA256]
       build-release.sh verify-candidate --help

preflight validates explicit, content-bound inputs without building. build is
deliberately disabled until the executable Phone SH-001 source build adapter
contract is published; it exits 3 after the same fail-closed validation. A
revision-09 implementation contract does not require an old admission record.
SH-002 tier evidence is a read-only join, not an executed build or producer proof.
EOF
}

require_value() {
    local option="$1" count="$2"
    (($# >= count + 2)) || fail "$option requires $count value(s)"
}

validate_digest_binding() {
    local role="$1" path="$2" expected="$3" actual
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || fail "$role digest is not lowercase SHA-256"
    [[ -f "$path" && ! -L "$path" ]] || fail "$role input is absent or is a symlink"
    actual="$(sha256sum -- "$path" 2>/dev/null | cut -d' ' -f1)" \
        || fail "$role input could not be hashed"
    [[ "$actual" == "$expected" ]] || fail "$role digest mismatch"
}

validate_exact_input() {
    local role="$1" supplied="$2" expected_relative="$3" supplied_real expected_real
    [[ -n "$supplied" ]] || fail "$role was not supplied explicitly"
    [[ -f "$supplied" && ! -L "$supplied" ]] || fail "$role input is not a regular file"
    supplied_real="$(realpath -e -- "$supplied" 2>/dev/null)" || fail "$role input does not exist"
    expected_real="$(realpath -e -- "$repo_root/$expected_relative" 2>/dev/null)" \
        || fail "$role SH-010 input does not exist"
    [[ "$supplied_real" == "$expected_real" ]] \
        || fail "$role does not resolve to the accepted SH-010 input"
}

mode="${1:-}"
case "$mode" in
    verify-candidate)
        shift
        exec python3 "$repo_root/android/phone/tests/candidate/verify_candidate.py" "$@"
        ;;
    preflight|build) shift ;;
    help|-h|--help) usage; exit 0 ;;
    *) usage >&2; fail "select preflight or build explicitly" ;;
esac

input_map=''
base_toolchain=''
cmake_toolchain=''
bootstrap_graph=''
bootstrap_profile=''
hosttools_profile=''
target_profile=''
source_graph_path=''
source_graph_digest=''
evidence_path=''
evidence_digest=''
identity_path=''
identity_digest=''
declare -a lock_paths=() lock_digests=()
declare -A seen_options=() seen_locks=()

while (($#)); do
    option="$1"
    shift
    [[ "$option" =~ ^--[a-z-]+$ ]] || fail "unknown option"
    if [[ "$option" != --shared-lock ]]; then
        [[ -z "${seen_options[$option]:-}" ]] || fail "duplicate option"
        seen_options["$option"]=1
    fi
    case "$option" in
        --input-map) require_value "$option" 1 "$@"; input_map="$1"; shift ;;
        --base-toolchain) require_value "$option" 1 "$@"; base_toolchain="$1"; shift ;;
        --cmake-toolchain) require_value "$option" 1 "$@"; cmake_toolchain="$1"; shift ;;
        --bootstrap-graph) require_value "$option" 1 "$@"; bootstrap_graph="$1"; shift ;;
        --bootstrap-profile) require_value "$option" 1 "$@"; bootstrap_profile="$1"; shift ;;
        --hosttools-profile) require_value "$option" 1 "$@"; hosttools_profile="$1"; shift ;;
        --target-profile) require_value "$option" 1 "$@"; target_profile="$1"; shift ;;
        --shared-source-graph)
            require_value "$option" 2 "$@"
            source_graph_path="$1"; source_graph_digest="$2"; shift 2
            ;;
        --shared-lock)
            require_value "$option" 2 "$@"
            lock_paths+=("$1"); lock_digests+=("$2"); shift 2
            ;;
        --shared-evidence-contract)
            require_value "$option" 2 "$@"
            evidence_path="$1"; evidence_digest="$2"; shift 2
            ;;
        --shared-artifact-identity)
            require_value "$option" 2 "$@"
            identity_path="$1"; identity_digest="$2"; shift 2
            ;;
        *) fail "unknown option" ;;
    esac
done

while IFS= read -r name; do
    case "$name" in
        PHONE_PREBUILT_*|PICO_*|ARTIFACTORY_*|OVERTE_ARTIFACTORY_*)
            fail "forbidden legacy selector is set"
            ;;
    esac
done < <(compgen -e)

validate_exact_input input-map "$input_map" \
    android/phone/fdroid/profiles/input-map.json
validate_exact_input base-toolchain "$base_toolchain" \
    android/phone/fdroid/manifests/base-toolchain.lock.json
validate_exact_input cmake-toolchain "$cmake_toolchain" \
    android/common/cmake/overte-android-toolchain.cmake
validate_exact_input bootstrap-graph "$bootstrap_graph" \
    android/phone/fdroid/conan/bootstrap.conanfile.py
validate_exact_input bootstrap-profile "$bootstrap_profile" \
    android/phone/fdroid/profiles/linux-x86_64-bootstrap
validate_exact_input hosttools-profile "$hosttools_profile" \
    android/phone/fdroid/profiles/linux-x86_64-hosttools
validate_exact_input target-profile "$target_profile" \
    android/phone/fdroid/profiles/android-arm64-v8a-api26-16k

[[ ${#lock_paths[@]} -eq 3 ]] \
    || fail "exactly three explicit Shared graph locks are required"
validate_digest_binding shared-source-graph "$source_graph_path" "$source_graph_digest"
for index in "${!lock_paths[@]}"; do
    validate_digest_binding "shared-lock-$((index + 1))" \
        "${lock_paths[index]}" "${lock_digests[index]}"
    lock_identity="$(stat -Lc '%d:%i' -- "${lock_paths[index]}" 2>/dev/null)" \
        || fail "Shared lock identity could not be read"
    [[ -z "${seen_locks[$lock_identity]:-}" ]] \
        || fail "Shared graph locks must be distinct files"
    seen_locks["$lock_identity"]=1
done
validate_digest_binding shared-evidence-contract "$evidence_path" "$evidence_digest"
validate_digest_binding shared-artifact-identity "$identity_path" "$identity_digest"

# SH-010 owns the schema and runtime allowlist. Reuse it directly rather than
# copying or weakening its checks in the Phone adapter.
python3 "$profile_doctor" --root "$repo_root" --runtime >/dev/null 2>&1 \
    || fail "SH-010 runtime input contract rejected the environment"

printf 'PHONE_FDROID_PREFLIGHT=PASS\tshared_locks=3\n'
if [[ "$mode" == build ]]; then
    printf '%s\n' \
        'PHONE_FDROID_BUILD=DEFERRED_SHARED_BINDING: executable Phone SH-001 build adapter is not published; SH-002 evidence join alone is not a build' >&2
    exit 3
fi
