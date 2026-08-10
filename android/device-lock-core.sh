#!/usr/bin/env bash

# Shared implementation for device-specific lock wrappers. Wrappers define a
# usage function and DEVICE_LOCK_* configuration before sourcing this file.

device_lock_fail() {
    printf 'error: %s\n' "$*" >&2
    exit 2
}

device_lock_open() {
    local lock_directory
    lock_directory="$(dirname -- "$DEVICE_LOCK_FILE")"
    [[ -d "$lock_directory" && -w "$lock_directory" ]] ||
        device_lock_fail "$DEVICE_LOCK_LABEL lock directory is not writable: $lock_directory"
    exec {DEVICE_LOCK_FD}>"$DEVICE_LOCK_FILE"
}

device_lock_describe_owner() {
    if [[ -s "$DEVICE_LOCK_OWNER_FILE" ]]; then
        tr '\n' ' ' <"$DEVICE_LOCK_OWNER_FILE" | sed 's/[[:space:]]*$//'
    else
        printf 'owner details unavailable'
    fi
}

device_lock_acquire() {
    device_lock_open
    if ! flock -n "$DEVICE_LOCK_FD"; then
        printf '%s is in use; waiting: %s\n' \
            "$DEVICE_LOCK_LABEL" "$(device_lock_describe_owner)" >&2
        flock "$DEVICE_LOCK_FD"
    fi
}

device_lock_release_metadata() {
    if (( DEVICE_LOCK_OWNS_METADATA )); then
        if [[ "$DEVICE_LOCK_PHASE_METADATA" == 1 ]]; then
            printf 'pid=%s since=%s branch=%s phase=cooldown\n' \
                "$$" "$DEVICE_LOCK_STARTED" "$DEVICE_LOCK_BRANCH" \
                >"$DEVICE_LOCK_OWNER_FILE"
        fi
        sleep "$DEVICE_LOCK_RELEASE_DELAY_SECONDS"
        rm -f -- "$DEVICE_LOCK_OWNER_FILE"
        DEVICE_LOCK_OWNS_METADATA=0
    fi
}

device_lock_run() {
    device_lock_acquire

    local branch_root="$DEVICE_LOCK_SCRIPT_DIR"
    if [[ "$DEVICE_LOCK_BRANCH_MODE" == caller ]] &&
            git -C "$PWD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        branch_root="$PWD"
    fi
    DEVICE_LOCK_BRANCH="$(git -C "$branch_root" symbolic-ref --quiet --short HEAD 2>/dev/null || printf detached)"
    DEVICE_LOCK_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    DEVICE_LOCK_OWNS_METADATA=1
    trap device_lock_release_metadata EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP

    if [[ "$DEVICE_LOCK_PHASE_METADATA" == 1 ]]; then
        printf 'pid=%s since=%s branch=%s phase=active\n' \
            "$$" "$DEVICE_LOCK_STARTED" "$DEVICE_LOCK_BRANCH" \
            >"$DEVICE_LOCK_OWNER_FILE"
    else
        printf 'pid=%s since=%s branch=%s\n' \
            "$$" "$DEVICE_LOCK_STARTED" "$DEVICE_LOCK_BRANCH" \
            >"$DEVICE_LOCK_OWNER_FILE"
    fi
    export "$DEVICE_LOCK_HELD_VARIABLE=1"

    set +e
    "$@" {DEVICE_LOCK_FD}>&-
    local command_status=$?
    set -e
    return "$command_status"
}

device_lock_main() {
    local command="${1:-status}"
    shift || true
    case "$command" in
        -h|--help|help)
            (( $# == 0 )) || { usage >&2; return 2; }
            usage
            ;;
        status)
            (( $# == 0 )) || { usage >&2; return 2; }
            device_lock_open
            if flock -n "$DEVICE_LOCK_FD"; then
                printf '%s is available\n' "$DEVICE_LOCK_LABEL"
            else
                printf '%s is in use: %s\n' \
                    "$DEVICE_LOCK_LABEL" "$(device_lock_describe_owner)"
                return 1
            fi
            ;;
        wait)
            (( $# == 0 )) || { usage >&2; return 2; }
            device_lock_acquire
            printf '%s is available\n' "$DEVICE_LOCK_LABEL"
            ;;
        run)
            [[ "${1:-}" == -- ]] || { usage >&2; return 2; }
            shift
            (( $# > 0 )) || { usage >&2; return 2; }
            device_lock_run "$@"
            ;;
        *)
            usage >&2
            return 2
            ;;
    esac
}
