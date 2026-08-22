#!/usr/bin/env bash

# Resource guard shared by the long-running Android dependency builds. This file
# is sourced; callers must invoke phone_build_resource_guard before changing
# build output or cached sources.

readonly OVERTE_PHONE_MIN_SWAP_BYTES=32000000000
readonly OVERTE_PHONE_MEMORY_MAX_PROPERTY='16000000000'
readonly OVERTE_PHONE_MEMORY_MAX_BYTES=16000000000
readonly OVERTE_PHONE_RESOURCE_GUARD_MARKER='OVERTE_PHONE_RESOURCE_GUARD_ACTIVE'

phone_build_resource_guard_fail() {
    echo "ERROR: $*" >&2
    return 1
}

phone_build_require_swap() {
    local meminfo_path="${1:-/proc/meminfo}"
    local swap_kib
    swap_kib="$(awk '$1 == "SwapTotal:" { print $2; found=1; exit } END { if (!found) exit 1 }' "$meminfo_path")" \
        || { phone_build_resource_guard_fail "cannot read total swap from $meminfo_path"; return; }
    [[ "$swap_kib" =~ ^[0-9]+$ ]] \
        || { phone_build_resource_guard_fail 'the SwapTotal value is not numeric'; return; }
    (( swap_kib * 1024 >= OVERTE_PHONE_MIN_SWAP_BYTES )) \
        || phone_build_resource_guard_fail \
            "at least 32 GB of swap is required (found $((swap_kib * 1024)) bytes)"
}

phone_build_verify_memory_cgroup() {
    local proc_cgroup_path="${1:-/proc/self/cgroup}"
    local cgroup_root="${2:-/sys/fs/cgroup}"
    local cgroup_path current_path memory_max memory_max_path effective_max=''
    cgroup_path="$(awk -F: '$1 == "0" && $2 == "" { print $3; found=1; exit } END { if (!found) exit 1 }' "$proc_cgroup_path")" \
        || { phone_build_resource_guard_fail 'cannot determine the unified cgroup path'; return; }
    [[ "$cgroup_path" == /* && "$cgroup_path" != *'..'* ]] \
        || { phone_build_resource_guard_fail 'the active cgroup path is invalid'; return; }

    # cgroup v2 applies the smallest finite limit in the hierarchy. A nested
    # service may itself report "max" while its parent still enforces MemoryMax.
    current_path="${cgroup_path%/}"
    while :; do
        memory_max_path="${cgroup_root%/}${current_path}/memory.max"
        if [[ ! -r "$memory_max_path" ]]; then
            # A delegated cgroup namespace may not expose host ancestors above
            # the user manager. Once a finite descendant limit was verified,
            # inaccessible outer levels cannot weaken that descendant limit.
            [[ -n "$effective_max" ]] && break
            phone_build_resource_guard_fail 'cannot read the cgroup memory-limit hierarchy'
            return
        fi
        memory_max="$(<"$memory_max_path")" \
            || { phone_build_resource_guard_fail 'cannot read the cgroup memory-limit hierarchy'; return; }
        if [[ "$memory_max" != max ]]; then
            [[ "$memory_max" =~ ^[0-9]+$ ]] \
                || { phone_build_resource_guard_fail 'a cgroup memory limit is invalid'; return; }
            if [[ -z "$effective_max" ]] || (( memory_max < effective_max )); then
                effective_max="$memory_max"
            fi
        fi
        [[ -n "$current_path" ]] || break
        current_path="${current_path%/*}"
    done

    [[ -n "$effective_max" ]] \
        || { phone_build_resource_guard_fail 'the build cgroup hierarchy has no finite memory limit'; return; }
    (( effective_max <= OVERTE_PHONE_MEMORY_MAX_BYTES )) \
        || phone_build_resource_guard_fail \
            'the effective cgroup memory limit exceeds 16 GB decimal'
}

phone_build_resource_guard() {
    local script_path="$1"
    shift

    phone_build_require_swap || return
    if [[ "${!OVERTE_PHONE_RESOURCE_GUARD_MARKER:-}" == 1 ]]; then
        phone_build_verify_memory_cgroup
        return
    fi

    command -v systemd-run >/dev/null 2>&1 \
        || { phone_build_resource_guard_fail 'systemd-run is required to enforce the build memory limit'; return; }
    [[ "$script_path" == /* ]] \
        || { phone_build_resource_guard_fail 'the guarded script path must be absolute'; return; }

    echo 'Restarting build in a systemd user service (MemoryMax=16 GB decimal)'
    exec systemd-run --user --collect --wait --pipe --quiet --same-dir \
        --property="MemoryMax=${OVERTE_PHONE_MEMORY_MAX_PROPERTY}" \
        --setenv="PATH=${PATH}" \
        --setenv="${OVERTE_PHONE_RESOURCE_GUARD_MARKER}=1" \
        -- "$script_path" "$@"
}
